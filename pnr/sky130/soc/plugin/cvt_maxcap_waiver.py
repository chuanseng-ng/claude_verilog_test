"""Named max-capacitance waiver check for the Sky130 SoC flow (bead claude_verilog_test-e45j).

Why this exists
---------------
LibreLane's stock ``Checker.MaxCapViolations`` counts violations per corner and has no notion of *which*
net violates, so the only waiver it offers is "ignore the checker".  On the RC-calibrated Sky130 SoC flow
exactly one net violates max-cap, at six tt/ss corners: a driver whose only functional load is the CPU
macro input ``axi_rdata_i[12]``, whose Liberty pin capacitance (0.2464 pF) alone is 46 % of the 0.5301 pF
driver limit.  This module gates the flow on max-cap with that one exception named explicitly, and fails on
anything else.

Honesty properties (each one is unit-tested in tb/tests/test_cvt_maxcap_waiver.py)
---------------------------------------------------------------------------------
* The waiver is keyed on the **load**: a macro instance glob plus an exact macro pin
  (``u_cpu*`` / ``axi_rdata_i[12]``).  The violating *driver* name (``_078722_``) is synthesis-generated and
  changes whenever the design is re-synthesised, so it is never part of the key.  A violation is waived only
  if its net, looked up in the final netlist, feeds that macro pin.
* Each waiver carries a mandatory justification and a ``max_cap_pf`` ceiling.  A waived net that gets
  *worse* than the ceiling fails; the waiver cannot silently absorb a regression.
* A waiver that waives nothing (the violation went away, or the macro pin moved) is reported as STALE
  (``strict_stale`` turns that into a failure) so dead exceptions do not accumulate.
* Nothing is inferred from a missing or truncated input: a report without its summary line, a report whose
  row count disagrees with its own summary or with the flow's per-corner metric, a corner that has a metric
  but no report, a violation whose driver is not in the netlist, or violations with no netlist at all are
  errors / failures, never passes.
* The empty waiver list is the strict mode and the negative control: with it the known violation fails.

The module is pure Python (no LibreLane import) so it runs in unit tests, as a CLI on a finished run
directory, and inside the ``CVT.MaxCapViolations`` flow step of this plugin.

CLI::

    python3 cvt_maxcap_waiver.py <run_dir> [--waivers max_cap_waivers.json] [--netlist X.nl.v] [--strict-stale]

Exit codes: 0 pass, 1 unwaived violation (or strict stale waiver), 2 input / format error.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

WAIVER_FORMAT_VERSION = 1
STD_CELL_PREFIX = "sky130_fd_sc_"
METRIC_PREFIX = "design__max_cap_violation__count__corner:"
STA_DIR_GLOB = "[0-9]*-openroad-stapostpnr"
_NETLIST_KEYWORDS = frozenset(
    {
        "module",
        "endmodule",
        "input",
        "output",
        "inout",
        "wire",
        "reg",
        "assign",
        "supply0",
        "supply1",
        "tri",
        "parameter",
        "localparam",
    }
)


class ReportError(Exception):
    """An input is missing, truncated or internally inconsistent (exit code 2)."""


class WaiverError(Exception):
    """The waiver file is malformed (exit code 2)."""


# --------------------------------------------------------------------------- report parsing
@dataclass(frozen=True)
class Violation:
    pin: str
    limit_pf: float
    cap_pf: float
    slack_pf: float

    @property
    def instance(self) -> str:
        return _norm_name(self.pin.rsplit("/", 1)[0])

    @property
    def port(self) -> str:
        return self.pin.rsplit("/", 1)[1] if "/" in self.pin else ""


@dataclass(frozen=True)
class ReportResult:
    declared_count: int
    violations: tuple[Violation, ...]


_NUM = r"[-+]?\d+(?:\.\d*)?(?:[eE][-+]?\d+)?"
_ROW_RE = re.compile(rf"^(\S+)\s+({_NUM})\s+({_NUM})\s+({_NUM})\s+\(VIOLATED\)\s*$")
_SUMMARY_RE = re.compile(r"^max cap violation count\s+(\d+)\s*$", re.MULTILINE)


def parse_checks_report(text: str) -> ReportResult:
    """Parse the max-capacitance part of an OpenSTA ``report_check_types -violators`` report."""
    summaries = _SUMMARY_RE.findall(text)
    if len(summaries) != 1:
        raise ReportError(
            f"expected exactly one 'max cap violation count N' summary line, found {len(summaries)} "
            "(truncated or wrong report?)"
        )
    declared = int(summaries[0])
    violations: list[Violation] = []
    in_cap = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped == "max capacitance":
            in_cap = True
            continue
        if in_cap and (stripped in ("max slew", "max fanout") or stripped.startswith("=====")):
            in_cap = False
        if not in_cap:
            continue
        m = _ROW_RE.match(line)
        if m:
            pin, limit, cap, slack = m.groups()
            violations.append(Violation(pin, float(limit), float(cap), float(slack)))
    if len(violations) != declared:
        raise ReportError(
            f"report declares {declared} max-cap violations but {len(violations)} rows were parsed"
        )
    return ReportResult(declared, tuple(violations))


# --------------------------------------------------------------------------- waiver file
@dataclass(frozen=True)
class Waiver:
    id: str
    instance_glob: str
    pin: str
    max_cap_pf: float
    justification: str
    bead: str = ""
    corners: tuple[str, ...] = ("*",)


def load_waivers(path: "str | Path") -> tuple[Waiver, ...]:
    p = Path(path)
    try:
        data = json.loads(p.read_text())
    except (OSError, ValueError) as exc:
        raise WaiverError(f"cannot read waiver file {p}: {exc}") from exc
    if not isinstance(data, dict) or data.get("version") != WAIVER_FORMAT_VERSION:
        raise WaiverError(f"{p}: unsupported waiver file version (expected {WAIVER_FORMAT_VERSION})")
    raw = data.get("waivers")
    if not isinstance(raw, list):
        raise WaiverError(f"{p}: 'waivers' must be a list")
    waivers: list[Waiver] = []
    seen: set[str] = set()
    for i, w in enumerate(raw):
        where = f"{p}: waivers[{i}]"
        if not isinstance(w, dict):
            raise WaiverError(f"{where}: must be an object")
        wid = w.get("id")
        if not isinstance(wid, str) or not wid.strip():
            raise WaiverError(f"{where}: 'id' is required")
        if wid in seen:
            raise WaiverError(f"{where}: duplicate waiver id {wid!r}")
        seen.add(wid)
        lp = w.get("load_pin")
        if not isinstance(lp, dict):
            raise WaiverError(f"{where} ({wid}): 'load_pin' object is required")
        inst, pin = lp.get("instance"), lp.get("pin")
        if not isinstance(inst, str) or not inst.strip():
            raise WaiverError(f"{where} ({wid}): load_pin.instance is required")
        if not isinstance(pin, str) or not pin.strip():
            raise WaiverError(f"{where} ({wid}): load_pin.pin is required")
        ceiling = w.get("max_cap_pf")
        if isinstance(ceiling, bool) or not isinstance(ceiling, (int, float)) or ceiling <= 0:
            raise WaiverError(f"{where} ({wid}): max_cap_pf must be a positive number")
        just = w.get("justification")
        if not isinstance(just, str) or not just.strip():
            raise WaiverError(f"{where} ({wid}): a non-empty justification is required")
        corners = w.get("corners", ["*"])
        if not (isinstance(corners, list) and corners and all(isinstance(c, str) for c in corners)):
            raise WaiverError(f"{where} ({wid}): corners must be a non-empty list of strings")
        waivers.append(
            Waiver(
                id=wid,
                instance_glob=inst,
                pin=pin,
                max_cap_pf=float(ceiling),
                justification=just.strip(),
                bead=str(w.get("bead", "")),
                corners=tuple(corners),
            )
        )
    return tuple(waivers)


# --------------------------------------------------------------------------- netlist
def _norm_name(name: str) -> str:
    return name.replace("\\", "").strip()


def _read_escaped(text: str, i: int) -> int:
    """text[i] == '\\': return the index just past the escaped identifier (ends at whitespace)."""
    j = i + 1
    while j < len(text) and not text[j].isspace():
        j += 1
    return j


def _split_top_level(text: str) -> list[str]:
    """Split on commas outside braces / parentheses, treating escaped identifiers atomically."""
    parts: list[str] = []
    depth = 0
    start = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i = _read_escaped(text, i)
            continue
        if ch in "{(":
            depth += 1
        elif ch in "})":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def _parse_connections(body: str) -> dict[str, "str | list[str]"]:
    """Parse ``.PIN(expr), .PIN({a, b, ...}), ...`` into {pin: net | [msb..lsb nets]}."""
    conns: dict[str, "str | list[str]"] = {}
    i, n = 0, len(body)
    while i < n:
        if body[i] != ".":
            i += 1
            continue
        j = i + 1
        while j < n and (body[j].isalnum() or body[j] in "_$"):
            j += 1
        name = body[i + 1 : j]
        while j < n and body[j].isspace():
            j += 1
        if j >= n or body[j] != "(":
            i = j
            continue
        depth = 0
        k = j
        while k < n:
            ch = body[k]
            if ch == "\\":
                k = _read_escaped(body, k)
                continue
            if ch in "({":
                depth += 1
            elif ch in ")}":
                depth -= 1
                if depth == 0:
                    break
            k += 1
        expr = body[j + 1 : k].strip()
        if expr.startswith("{") and expr.endswith("}"):
            conns[name] = [_norm_name(e) for e in _split_top_level(expr[1:-1])]
        elif expr:
            conns[name] = _norm_name(expr)
        i = k + 1
    return conns


_HEAD_RE = re.compile(r"^\s*(\\\S+|[A-Za-z_][\w$]*)\s+(\\\S+|[A-Za-z_][\w$]*)\s*\(", re.DOTALL)


@dataclass
class NetlistIndex:
    """Driver connections for requested instances and macro (non-std-cell) loads per net."""

    driver_conns: dict[str, dict[str, "str | list[str]"]] = field(default_factory=dict)
    _macro_loads: dict[str, list[tuple[str, str]]] = field(default_factory=dict)

    def net_of(self, instance: str, port: str) -> Optional[str]:
        conns = self.driver_conns.get(_norm_name(instance))
        if conns is None:
            return None
        net = conns.get(port)
        return net if isinstance(net, str) else None

    def macro_loads(self, net: str) -> list[tuple[str, str]]:
        return list(self._macro_loads.get(net, ()))

    def _add_macro(self, inst: str, conns: Mapping[str, "str | list[str]"]) -> None:
        for port, expr in conns.items():
            if isinstance(expr, str):
                self._macro_loads.setdefault(expr, []).append((inst, port))
                continue
            width = len(expr)
            for k, net in enumerate(expr):
                bit = width - 1 - k  # first element of a concatenation is the MSB
                self._macro_loads.setdefault(net, []).append((inst, f"{port}[{bit}]"))
                if width == 1:
                    self._macro_loads[net].append((inst, port))


def scan_netlist(
    path: "str | Path", driver_instances: Iterable[str], *, std_cell_prefix: str = STD_CELL_PREFIX
) -> NetlistIndex:
    """One streaming pass over a structural Verilog netlist.

    Records the connections of every instance named in ``driver_instances`` and of every instance whose
    cell type does not start with ``std_cell_prefix`` (hard macros).  Bus ports on macros appear in
    OpenROAD netlists as concatenations ``.port({n31, n30, ..., n0})``; the first element is bit width-1.
    """
    wanted = {_norm_name(d) for d in driver_instances}
    idx = NetlistIndex()
    buf: list[str] = []
    try:
        fh = open(path, "r", errors="replace")
    except OSError as exc:
        raise ReportError(f"cannot read netlist {path}: {exc}") from exc
    with fh:
        for line in fh:
            buf.append(line)
            if not line.rstrip().endswith(";"):
                continue
            stmt = "".join(buf)
            buf.clear()
            m = _HEAD_RE.match(stmt)
            if not m:
                continue
            celltype = m.group(1)
            if celltype in _NETLIST_KEYWORDS:
                continue
            inst = _norm_name(m.group(2))
            is_macro = not celltype.startswith(std_cell_prefix)
            if inst not in wanted and not is_macro:
                continue
            lparen = m.end() - 1
            rparen = stmt.rstrip().rstrip(";").rstrip().rfind(")")
            conns = _parse_connections(stmt[lparen + 1 : rparen])
            if inst in wanted:
                idx.driver_conns[inst] = conns
            if is_macro:
                idx._add_macro(inst, conns)
    return idx


# --------------------------------------------------------------------------- evaluation
@dataclass(frozen=True)
class WaivedViolation:
    corner: str
    violation: Violation
    net: str
    waiver_id: str


@dataclass(frozen=True)
class UnwaivedViolation:
    corner: str
    violation: Violation
    net: Optional[str]
    reason: str


@dataclass(frozen=True)
class Verdict:
    ok: bool
    corners_checked: int
    waived: tuple[WaivedViolation, ...]
    unwaived: tuple[UnwaivedViolation, ...]
    stale_waivers: tuple[Waiver, ...]
    strict_stale: bool = False

    def format(self) -> str:
        lines = [
            f"max-cap check: {self.corners_checked} corner report(s); "
            f"{len(self.waived)} waived, {len(self.unwaived)} unwaived violation(s), "
            f"{len(self.stale_waivers)} stale waiver(s)"
        ]
        for w in self.waived:
            v = w.violation
            lines.append(
                f"  WAIVED   {w.corner}: {v.pin} net {w.net} cap {v.cap_pf:.4f} pF "
                f"(limit {v.limit_pf:.4f}) by waiver '{w.waiver_id}'"
            )
        for u in self.unwaived:
            v = u.violation
            lines.append(
                f"  UNWAIVED {u.corner}: {v.pin} cap {v.cap_pf:.4f} pF (limit {v.limit_pf:.4f}): {u.reason}"
            )
        for s in self.stale_waivers:
            lines.append(
                f"  STALE    waiver '{s.id}' ({s.instance_glob}/{s.pin}) waived nothing at any corner; "
                "remove it or re-check it" + (" [strict: counts as failure]" if self.strict_stale else "")
            )
        lines.append("max-cap check: " + ("PASS" if self.ok else "FAIL"))
        return "\n".join(lines)


def find_sta_dir(run_dir: Path) -> Path:
    candidates = sorted(Path(run_dir).glob(STA_DIR_GLOB))
    if not candidates:
        raise ReportError(f"no *-openroad-stapostpnr step directory under {run_dir}")
    return candidates[-1]


def find_netlist(run_dir: Path) -> Optional[Path]:
    """The netlist of the highest-numbered step that wrote a ``*.nl.v``."""
    best: Optional[Path] = None
    for step in sorted(p for p in Path(run_dir).iterdir() if p.is_dir() and p.name[:2].isdigit()):
        nls = sorted(step.glob("*.nl.v"))
        if nls:
            best = nls[0]
    return best


def _metric_counts(sta_dir: Path) -> dict[str, int]:
    state = sta_dir / "state_out.json"
    if not state.is_file():
        return {}
    try:
        metrics = json.loads(state.read_text()).get("metrics", {})
    except (OSError, ValueError) as exc:
        raise ReportError(f"cannot read {state}: {exc}") from exc
    return {
        k[len(METRIC_PREFIX) :]: int(v) for k, v in metrics.items() if k.startswith(METRIC_PREFIX)
    }


def evaluate_sta_dir(
    sta_dir: "str | Path",
    netlist: "str | Path | None",
    waivers: Sequence[Waiver],
    *,
    strict_stale: bool = False,
) -> Verdict:
    sta = Path(sta_dir)
    corner_dirs = sorted(d for d in sta.iterdir() if d.is_dir() and (d / "checks.rpt").is_file())
    if not corner_dirs:
        raise ReportError(f"no per-corner checks.rpt under {sta}")
    metric_counts = _metric_counts(sta)
    present = {d.name for d in corner_dirs}
    for corner in sorted(metric_counts):
        if corner not in present:
            raise ReportError(f"corner {corner} has a flow metric but no checks.rpt under {sta}")

    per_corner: list[tuple[str, Violation]] = []
    for d in corner_dirs:
        try:
            res = parse_checks_report((d / "checks.rpt").read_text(errors="replace"))
        except ReportError as exc:
            raise ReportError(f"{d.name}/checks.rpt: {exc}") from exc
        if d.name in metric_counts and metric_counts[d.name] != res.declared_count:
            raise ReportError(
                f"{d.name}: report declares {res.declared_count} max-cap violations but the flow metric "
                f"says {metric_counts[d.name]}"
            )
        per_corner.extend((d.name, v) for v in res.violations)

    waived: list[WaivedViolation] = []
    unwaived: list[UnwaivedViolation] = []
    used: set[str] = set()
    if per_corner:
        if netlist is None or not Path(netlist).is_file():
            raise ReportError(
                "max-cap violations exist but no netlist is available to resolve their nets "
                f"(looked for {netlist}); cannot prove any waiver"
            )
        idx = scan_netlist(netlist, {v.instance for _, v in per_corner})
        for corner, v in per_corner:
            net = idx.net_of(v.instance, v.port)
            if net is None:
                unwaived.append(
                    UnwaivedViolation(
                        corner, v, None, f"driver {v.instance}/{v.port} not found in netlist; cannot prove waiver"
                    )
                )
                continue
            loads = idx.macro_loads(net)
            decision: Optional[object] = None
            reason = f"no waiver covers net {net} (macro loads: {loads or 'none'})"
            for w in waivers:
                if not any(fnmatch.fnmatchcase(corner, c) for c in w.corners):
                    continue
                if not any(fnmatch.fnmatchcase(inst, w.instance_glob) and pin == w.pin for inst, pin in loads):
                    continue
                used.add(w.id)
                if v.cap_pf > w.max_cap_pf:
                    reason = (
                        f"net {net} matches waiver '{w.id}' but cap {v.cap_pf:.4f} pF exceeds its "
                        f"ceiling {w.max_cap_pf:.4f} pF"
                    )
                    continue
                decision = w
                break
            if isinstance(decision, Waiver):
                waived.append(WaivedViolation(corner, v, net, decision.id))
            else:
                unwaived.append(UnwaivedViolation(corner, v, net, reason))

    stale = tuple(w for w in waivers if w.id not in used)
    ok = not unwaived and not (strict_stale and stale)
    return Verdict(ok, len(corner_dirs), tuple(waived), tuple(unwaived), stale, strict_stale)


def evaluate_run(
    run_dir: "str | Path",
    waivers: Sequence[Waiver],
    *,
    netlist: "str | Path | None" = None,
    strict_stale: bool = False,
) -> Verdict:
    run = Path(run_dir)
    sta = find_sta_dir(run)
    return evaluate_sta_dir(
        sta, netlist if netlist is not None else find_netlist(run), waivers, strict_stale=strict_stale
    )


# --------------------------------------------------------------------------- CLI
def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="Named max-cap waiver check on a finished LibreLane run.")
    ap.add_argument("run_dir", type=Path)
    ap.add_argument("--waivers", type=Path, default=None, help="waiver JSON; omitted = strict, no waivers")
    ap.add_argument("--netlist", type=Path, default=None, help="override the netlist (default: latest *.nl.v)")
    ap.add_argument("--strict-stale", action="store_true", help="a waiver that waives nothing is a failure")
    args = ap.parse_args(argv)
    try:
        waivers = load_waivers(args.waivers) if args.waivers else ()
        verdict = evaluate_run(args.run_dir, waivers, netlist=args.netlist, strict_stale=args.strict_stale)
    except (ReportError, WaiverError) as exc:
        print(f"max-cap check: ERROR: {exc}", file=sys.stderr)
        return 2
    print(verdict.format())
    return 0 if verdict.ok else 1


if __name__ == "__main__":
    sys.exit(main())
