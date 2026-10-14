#!/usr/bin/env python3
"""Summarise one tools/fpga/vivado_fmax.sh run (bead hlrm).

Per clock: WNS and estimated fmax; also the worst paths and the utilisation.

usage: vivado_fmax_report.py <out-dir>/<gpu>/<tag> [--json]

Reads <run>/timing_summary.rpt, <run>/paths_setup_to_<clock>.rpt, <run>/utilization.rpt and
<run>.time (one level up). Estimated fmax = 1 / (period - WNS) per clock, using the period of
that clock's own constraint (a WNS >= 0 only gives a lower bound: the placer stops optimising
once the target is met). Stdlib only.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

PERIOD_RE = re.compile(r"^(\S+)\s+([\d.]+)\s+\{")  # pre.clocks.rpt rows: name period {wave}
ROW_RE = re.compile(
    r"^(\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)"
)
INTER_RE = re.compile(r"^(\S+)\s+(\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s*$")
PATH_FIELDS = {
    "slack": re.compile(r"^Slack \((?:VIOLATED|MET)\)\s*:\s*(-?[\d.]+)ns"),
    "source": re.compile(r"^\s+Source:\s+(\S+)"),
    "dest": re.compile(r"^\s+Destination:\s+(\S+)"),
    "requirement": re.compile(r"^\s+Requirement:\s+(-?[\d.]+)ns\s+\((.*)\)"),
    "delay": re.compile(
        r"^\s+Data Path Delay:\s+(-?[\d.]+)ns\s+\(logic (-?[\d.]+)ns \([\d.]+%\)"
        r"\s+route (-?[\d.]+)ns"
    ),
    "levels": re.compile(r"^\s+Logic Levels:\s+(\d+)\s+\((.*)\)"),
    "skew": re.compile(r"^\s+Clock Path Skew:\s+(-?[\d.]+)ns"),
}
UTIL_KEYS = (
    "Slice LUTs",
    "LUT as Logic",
    "LUT as Memory",
    "LUT as Distributed RAM",
    "Slice Registers",
    "Register as Latch",
    "F7 Muxes",
    "F8 Muxes",
    "Block RAM Tile",
    "RAMB36/FIFO*",
    "RAMB18",
    "DSPs",
    "Bonded IOB",
    "BUFGCTRL",
)


def _periods(run: Path) -> dict[str, float]:
    out: dict[str, float] = {}
    path = run / "pre.clocks.rpt"
    if path.exists():
        for line in path.read_text().splitlines():
            m = PERIOD_RE.match(line)
            if m:
                out[m.group(1)] = float(m.group(2))
    return out


def _summary(run: Path, periods: dict[str, float]) -> dict[str, Any]:
    text = (run / "timing_summary.rpt").read_text().splitlines()
    intra: dict[str, dict[str, Any]] = {}
    inter: list[dict[str, Any]] = []
    section = ""
    overall: dict[str, float] = {}
    for i, line in enumerate(text):
        if line.startswith("| Design Timing Summary"):
            m = next(
                (
                    mm
                    for mm in (
                        re.match(
                            r"\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(\d+)\s+(\d+)",
                            t,
                        )
                        for t in text[i + 1 : i + 12]
                    )
                    if mm
                ),
                None,
            )
            if m:
                overall = {
                    "wns": float(m.group(1)),
                    "tns": float(m.group(2)),
                    "whs": float(m.group(5)),
                    "ths": float(m.group(6)),
                }
        if line.startswith("| Intra Clock Table"):
            section = "intra"
        elif line.startswith("| Inter Clock Table"):
            section = "inter"
        elif line.startswith("| Other Path Groups"):
            section = ""
        elif section == "intra":
            m = ROW_RE.match(line)
            if m:
                name = m.group(1)
                wns = float(m.group(2))
                per = periods.get(name)
                intra[name] = {
                    "wns": wns,
                    "tns": float(m.group(3)),
                    "failing": int(m.group(4)),
                    "endpoints": int(m.group(5)),
                    "whs": float(m.group(6)),
                    "period": per,
                    "fmax_mhz": round(1000.0 / (per - wns), 1) if per else None,
                }
        elif section == "inter":
            m = INTER_RE.match(line)
            if m:
                inter.append(
                    {
                        "from": m.group(1),
                        "to": m.group(2),
                        "wns": float(m.group(3)),
                        "tns": float(m.group(4)),
                        "failing": int(m.group(5)),
                        "endpoints": int(m.group(6)),
                    }
                )
    return {"overall": overall, "intra": intra, "inter": inter}


def _critical_paths(run: Path) -> dict[str, list[dict[str, Any]]]:
    res: dict[str, list[dict[str, Any]]] = {}
    for rpt in sorted(run.glob("paths_setup_to_*.rpt")):
        clk = rpt.stem.removeprefix("paths_setup_to_")
        paths: list[dict[str, Any]] = []
        cur: dict[str, Any] = {}
        for line in rpt.read_text().splitlines():
            for key, rx in PATH_FIELDS.items():
                m = rx.match(line)
                if not m:
                    continue
                if key == "slack":
                    if cur:
                        paths.append(cur)
                    cur = {"slack": float(m.group(1))}
                elif key in ("source", "dest"):
                    cur.setdefault(key, m.group(1))
                elif key == "requirement":
                    cur.setdefault("requirement_ns", float(m.group(1)))
                    cur.setdefault("requirement_kind", m.group(2))
                elif key == "delay":
                    cur.setdefault("path_delay", float(m.group(1)))
                    cur.setdefault("logic_ns", float(m.group(2)))
                    cur.setdefault("route_ns", float(m.group(3)))
                elif key == "levels":
                    cur.setdefault("levels", int(m.group(1)))
                    cur.setdefault("cells", m.group(2))
                else:
                    cur.setdefault(key, float(m.group(1)))
        if cur:
            paths.append(cur)
        res[clk] = paths
    return res


def _utilisation(run: Path) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    path = run / "utilization.rpt"
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[0] in UTIL_KEYS and cells[0] not in out:
            try:
                out[cells[0]] = {
                    "used": float(cells[1]),
                    "available": float(cells[4]),
                    "pct": float(cells[5].lstrip("<")),
                }
            except (ValueError, IndexError):
                continue
    return out


def _rss_wall(run: Path) -> dict[str, str]:
    path = run.parent / f"{run.name}.time"
    out: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if "Maximum resident" in line:
                out["peak_rss_kb"] = line.split(":")[-1].strip()
            if "Elapsed (wall clock)" in line:
                out["wall"] = line.split("):")[-1].strip()
    return out


def summarise(run: Path) -> dict[str, Any]:
    periods = _periods(run)
    return {
        "run": str(run),
        "periods_ns": periods,
        "timing": _summary(run, periods),
        "critical_paths": _critical_paths(run),
        "utilisation": _utilisation(run),
        "runtime": _rss_wall(run),
    }


def main(argv: list[str]) -> int:
    args = [a for a in argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__)
        return 2
    run = Path(args[0])
    try:
        data = summarise(run)
    except FileNotFoundError as exc:
        print(f"missing report: {exc}")
        return 2
    if "--json" in argv:
        print(json.dumps(data, indent=1))
        return 0
    t = data["timing"]
    print(f"run {run}  overall {t['overall']}")
    for name, row in t["intra"].items():
        print(
            f"  {name:11s} period {row['period']} WNS {row['wns']:+.3f} TNS {row['tns']:.1f}"
            f" failing {row['failing']}/{row['endpoints']} WHS {row['whs']:+.3f}"
            f" fmax~{row['fmax_mhz']} MHz"
        )
    for row in t["inter"]:
        print(
            f"  cross {row['from']} -> {row['to']}: WNS {row['wns']:+.3f} TNS {row['tns']:.1f}"
            f" failing {row['failing']}/{row['endpoints']}"
        )
    for clk, paths in data["critical_paths"].items():
        for p in paths[:1]:
            print(f"  worst -> {clk}: {p}")
    print(f"  utilisation {data['utilisation']}")
    print(f"  runtime {data['runtime']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
