#!/usr/bin/env python3
"""Turn a raw EDA tool log into a compact JSON verdict.

Companion to the wrap-*.sh drivers in this directory. Reads the raw log on stdin
(or from a file), emits one JSON object on stdout, and exits with the verdict:

    0  PASS   tool succeeded and no violation was found
    1  FAIL   tool failed, or the log shows a real violation
    2  ERROR  the log could not be interpreted (missing/empty report, no
              recognisable result) -- deliberately distinct from FAIL so an
              unparsed report can never masquerade as a clean run

That last case is the point of this script. OpenSTA in particular exits 0 while
reporting violated paths, and an empty report reads exactly like a clean one;
this repo has already shipped a gate that passed for that reason (bead `dwp`).

Stdlib only: these wrappers run outside the repo virtualenv, inside nix shells.

Usage:
    summarize.py --tool opensta [--log path] [--exit-code N] [< raw.log]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

PASS, FAIL, ERROR = 0, 1, 2

MAX_ITEMS = 20  # cap every list in the summary; the raw log always holds the rest


def _cap(items: list) -> list:
    """Cap a list and mark the truncation inline so it is never silent."""
    if len(items) <= MAX_ITEMS:
        return items
    return items[:MAX_ITEMS] + [f"... {len(items) - MAX_ITEMS} more (see raw log)"]


# --------------------------------------------------------------------------
# per-tool parsers: each returns (status_code, summary_dict)
# --------------------------------------------------------------------------


def parse_verilator(text: str, exit_code: int) -> tuple[int, dict]:
    """Count %Error/%Warning lines and group the warnings by Verilator code."""
    errors = re.findall(r"^%Error.*$", text, re.M)
    warns = re.findall(r"^%Warning-([A-Z0-9_]+):\s*(.*)$", text, re.M)

    by_code: dict[str, int] = {}
    for code, _ in warns:
        by_code[code] = by_code.get(code, 0) + 1

    summary = {
        "errors": _cap([e.strip() for e in errors]),
        "error_count": len(errors),
        "warning_count": len(warns),
        "warnings_by_code": dict(sorted(by_code.items(), key=lambda kv: -kv[1])),
        "warnings": _cap([f"{c}: {m.strip()}" for c, m in warns]),
    }
    status = FAIL if (errors or exit_code != 0) else PASS
    return status, summary


def parse_yosys(text: str, exit_code: int) -> tuple[int, dict]:
    """Extract cell count and chip area; a run with no statistics is ERROR."""
    errors = re.findall(r"^ERROR:.*$", text, re.M)
    warns = re.findall(r"^Warning:.*$", text, re.M)

    summary: dict = {
        "errors": _cap([e.strip() for e in errors]),
        "error_count": len(errors),
        "warning_count": len(warns),
        "warnings": _cap([w.strip() for w in warns]),
    }

    cells = re.findall(r"^\s*Number of cells:\s+(\d+)", text, re.M)
    if cells:
        summary["cell_count"] = int(cells[-1])  # last = top module
    area = re.findall(r"^\s*Chip area for(?: module)? .*?:\s*([\d.]+)", text, re.M)
    if area:
        summary["chip_area"] = float(area[-1])

    if exit_code != 0 or errors:
        return FAIL, summary
    # A synthesis run that produced no statistics at all did not really run.
    if "cell_count" not in summary and "Printing statistics" not in text:
        summary["note"] = "no cell statistics in log — did synthesis actually run?"
        return ERROR, summary
    return PASS, summary


# `  -0.0123   slack (VIOLATED)` / `   0.0456   slack (MET)`
_SLACK_RE = re.compile(r"^\s*(-?[\d.]+)\s+slack\s+\((MET|VIOLATED)\)", re.M)
# `wns -12.34` / `tns 0.00` / `worst slack 24.01`, as printed by report_wns,
# report_tns and report_worst_slack. Note wns is worst *negative* slack: it reads
# 0.00 on a clean design, so worst_slack is the one that carries the margin.
_WNS_RE = re.compile(r"^\s*wns\s+(-?[\d.]+)", re.M | re.I)
_TNS_RE = re.compile(r"^\s*tns\s+(-?[\d.]+)", re.M | re.I)
_WORST_RE = re.compile(r"^\s*worst slack\s+(-?[\d.]+)", re.M | re.I)


def parse_opensta(text: str, exit_code: int) -> tuple[int, dict]:
    """Extract wns/tns and violated endpoints; an empty report is ERROR, not PASS."""
    slacks = _SLACK_RE.findall(text)
    violated = [s for s, verdict in slacks if verdict == "VIOLATED"]

    summary: dict = {
        "paths_reported": len(slacks),
        "violated_endpoints": len(violated),
        "errors": _cap([e.strip() for e in re.findall(r"^Error:.*$", text, re.M)]),
        "warnings_count": len(re.findall(r"^Warning:.*$", text, re.M)),
    }

    wns = _WNS_RE.findall(text)
    tns = _TNS_RE.findall(text)
    worst = _WORST_RE.findall(text)
    if wns:
        summary["wns"] = float(wns[-1])
    elif slacks:
        summary["wns"] = min(float(s) for s, _ in slacks)
    if tns:
        summary["tns"] = float(tns[-1])
    if worst:
        summary["worst_slack"] = float(worst[-1])

    if summary["errors"] or exit_code != 0:
        return FAIL, summary

    # OpenSTA exits 0 on an empty report. Refuse to call that a pass.
    if not slacks and not wns and not tns and not worst:
        summary["note"] = (
            "no slack, wns or tns found — empty report or the design/SDC never "
            "loaded. Treated as ERROR, not PASS (bead dwp)."
        )
        return ERROR, summary

    if summary["violated_endpoints"] or summary.get("wns", 0.0) < 0 or summary.get("tns", 0.0) < 0:
        return FAIL, summary
    return PASS, summary


def _classify_testcase(case: ET.Element) -> tuple[str, str]:
    """Classify one JUnit <testcase> as pass/fail/skip; return (verdict, label)."""
    name = f"{case.get('classname', '')}.{case.get('name', '')}".strip(".")
    node = case.find("failure")
    if node is None:
        node = case.find("error")
    if node is not None:
        msg = (node.get("message") or node.text or "").strip()
        return "fail", (f"{name}: {msg.splitlines()[0][:200]}" if msg else name)
    if case.find("skipped") is not None:
        return "skip", name
    return "pass", name


def _parse_results_xml(results_xml: Path, exit_code: int) -> tuple[int, dict]:
    """Read a cocotb JUnit results.xml into the verdict + summary pair."""
    root = ET.parse(results_xml).getroot()
    suites = root.iter("testsuite") if root.tag != "testsuite" else [root]
    tally = {"pass": 0, "fail": 0, "skip": 0}
    failures: list[str] = []
    for suite in suites:
        for case in suite.iter("testcase"):
            verdict, label = _classify_testcase(case)
            tally[verdict] += 1
            if verdict == "fail":
                failures.append(label)

    summary = {
        "source": str(results_xml),
        "passed": tally["pass"],
        "failed": tally["fail"],
        "skipped": tally["skip"],
        "failures": _cap(failures),
    }
    if tally["fail"] or exit_code != 0:
        return FAIL, summary
    if tally["pass"] == 0:
        summary["note"] = "results.xml contains no passing test"
        return ERROR, summary
    return PASS, summary


def parse_cocotb(text: str, exit_code: int, results_xml: Path | None) -> tuple[int, dict]:
    """Prefer the JUnit results.xml; fall back to cocotb's TESTS= tally line."""
    if results_xml and results_xml.is_file():
        try:
            return _parse_results_xml(results_xml, exit_code)
        except ET.ParseError as exc:
            return ERROR, {"errors": [f"unparsable {results_xml}: {exc}"]}

    tally = re.search(r"TESTS=(\d+)\s+PASS=(\d+)\s+FAIL=(\d+)\s+SKIP=(\d+)", text)
    if not tally:
        return ERROR, {
            "note": "no results.xml and no 'TESTS=' tally in the log — the "
            "simulation did not reach the end of the regression",
            "errors": _cap([e.strip() for e in re.findall(r"^ERROR:.*$", text, re.M)]),
        }

    total, passed, failed, skipped = (int(g) for g in tally.groups())
    rows = re.findall(r"^\s*\*\*\s+(\S+)\s+(FAIL|ERROR)\s", text, re.M)
    summary = {
        "source": "log tally",
        "total": total,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "failures": _cap([name for name, _ in rows]),
    }
    return (FAIL if (failed or exit_code != 0) else PASS), summary


PARSERS = {
    "verilator": parse_verilator,
    "yosys": parse_yosys,
    "opensta": parse_opensta,
}


def main() -> int:
    """Parse args, summarise the log, print the JSON verdict, return the status."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", required=True, choices=sorted(set(PARSERS) | {"cocotb"}))
    ap.add_argument("--log", help="raw log file (also echoed in the JSON)")
    ap.add_argument("--exit-code", type=int, default=0, help="exit status of the wrapped tool")
    ap.add_argument("--results-xml", help="cocotb JUnit results.xml, if any")
    args = ap.parse_args()

    text = (
        Path(args.log).read_text(encoding="utf-8", errors="replace")
        if args.log
        else sys.stdin.read()
    )

    if args.tool == "cocotb":
        xml_path = Path(args.results_xml) if args.results_xml else None
        status, summary = parse_cocotb(text, args.exit_code, xml_path)
    else:
        status, summary = PARSERS[args.tool](text, args.exit_code)

    out = {
        "tool": args.tool,
        "status": {PASS: "PASS", FAIL: "FAIL", ERROR: "ERROR"}[status],
        "exit_code": args.exit_code,
        "summary": summary,
        "raw_log": args.log or "(stdin)",
    }
    print(json.dumps(out, indent=2))
    return status


if __name__ == "__main__":
    sys.exit(main())
