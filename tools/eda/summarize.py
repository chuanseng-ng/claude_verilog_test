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
import hashlib
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
    # The -CODE suffix is optional: Verilator also emits bare "%Warning: ..."
    # lines (SystemVerilog $warning, some driver messages). Requiring the code
    # dropped those from both the count and the list, under-reporting the run.
    warns = [
        (code or "UNCODED", msg)
        for code, msg in re.findall(r"^%Warning(?:-([A-Z0-9_]+))?:\s*(.*)$", text, re.M)
    ]

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

    # worst_slack is checked alongside wns/tns: a truncated report, or a run_tcl
    # call that only issued report_worst_slack, can carry a negative slack with
    # no VIOLATED row and no wns/tns line at all. Leaving it out of the verdict
    # made "worst slack -1.5" read as PASS — exactly the false pass this module
    # exists to prevent.
    if (
        summary["violated_endpoints"]
        or summary.get("wns", 0.0) < 0
        or summary.get("tns", 0.0) < 0
        or summary.get("worst_slack", 0.0) < 0
    ):
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
    if failed or exit_code != 0:
        return FAIL, summary
    # Same guard the results.xml path applies: a clean exit with nothing run is
    # not a pass. "TESTS=0 PASS=0 FAIL=0 SKIP=0" means the suite selected no
    # tests, which is a setup fault, not success.
    if passed == 0:
        summary["note"] = "the tally reports no passing test — did the suite select anything?"
        return ERROR, summary
    return PASS, summary


# Bambu echoes its own full invocation back on the first line of the log:
#   ==  Bambu executed with: /nix/store/.../bambu --top-fname=sum ... --simulate ...
# Parsing that one line is what lets this verdict tell a generation-only run
# (which legitimately has no co-simulation results) apart from a --simulate run
# whose results are missing. Without it the parser would have to either demand
# cycles unconditionally (failing every valid generation run) or never demand
# them (letting a silently-dead cosim read as PASS).
_BAMBU_CMDLINE_RE = re.compile(r"^\s*==\s+Bambu executed with:\s*(.+)$", re.M)
_BAMBU_TOP_RE = re.compile(r"--top-fname=(\S+)")
_BAMBU_DEVICE_RE = re.compile(r"--device-name=(\S+)")
_BAMBU_PERIOD_RE = re.compile(r"--clock-period=(\S+)")
# `  Total number of flip-flops in function sum: 1183` — the end of the HLS phase,
# and the marker that proves synthesis actually ran rather than dying at startup.
_BAMBU_FF_RE = re.compile(r"^\s*Total number of flip-flops in function\s+\S+?:\s*(\d+)", re.M)
_BAMBU_AREA_RE = re.compile(r"^\s*Total estimated area:\s*(\d+)", re.M)
# The co-simulation result block, printed only when --simulate ran to completion.
_BAMBU_CYCLES_RE = re.compile(r"^\s*Total cycles\s*:\s*(\d+)", re.M)
_BAMBU_EXECS_RE = re.compile(r"^\s*Number of executions\s*:\s*(\d+)", re.M)
_BAMBU_AVG_RE = re.compile(r"^\s*Average execution\s*:\s*(\d+)", re.M)
# Bambu's own terminal error line, e.g. "error -> Co-simulation main aborted".
_BAMBU_ERR_RE = re.compile(r"^error -> .*$", re.M)
# The MDPI co-simulation driver's per-parameter mismatch report. These appear
# only under -v4; the plain log carries just the "error ->" line above, so the
# ladder must never depend on finding them.
_BAMBU_MDPI_RE = re.compile(r"^ERROR: MDPI driver: .*$", re.M)
# Bambu stamps the generation time into a header comment of every .v:
#   // Code created using PandA - Version: ... - Date 2026-09-06T01:13:19
# That timestamp is the ONLY thing that varies between two runs of identical
# input (verified: 3 back-to-back runs differed in exactly this one line and
# nowhere else). Hashing the raw bytes therefore yields a different digest every
# time, which would make a committed "expected sha256" fail on every
# regeneration. verilog_sha256_normalized blanks the date and is the digest to
# pin; verilog_sha256 stays as the identity of the exact file on disk.
_BAMBU_DATE_RE = re.compile(rb"(// Code created using PandA .* - Date )\S+")


def parse_bambu(text: str, exit_code: int, verilog: Path | None) -> tuple[int, dict]:
    """Verdict a Bambu HLS run; a missing .v or an absent cosim block is ERROR, not PASS."""
    cmdline_m = _BAMBU_CMDLINE_RE.search(text)
    cmdline = cmdline_m.group(1) if cmdline_m else ""
    simulated = "--simulate" in cmdline

    ff = _BAMBU_FF_RE.findall(text)
    cycles = _BAMBU_CYCLES_RE.findall(text)
    execs = _BAMBU_EXECS_RE.findall(text)
    avg = _BAMBU_AVG_RE.findall(text)
    area = _BAMBU_AREA_RE.findall(text)

    errors = [e.strip() for e in _BAMBU_ERR_RE.findall(text)]
    errors += [e.strip() for e in _BAMBU_MDPI_RE.findall(text)]
    if "Warning: Returned error code!" in text:
        errors.append("Warning: Returned error code!")

    summary: dict = {
        "simulated": simulated,
        "errors": _cap(errors),
    }
    for key, pattern in (
        ("top", _BAMBU_TOP_RE),
        ("device", _BAMBU_DEVICE_RE),
        ("clock_period_ns", _BAMBU_PERIOD_RE),
    ):
        found = pattern.search(cmdline)
        if found:
            summary[key] = found.group(1)
    if ff:
        summary["flip_flops"] = int(ff[-1])
    if area:
        summary["estimated_area"] = int(area[-1])
    if cycles:
        summary["cycles"] = int(cycles[-1])
    if execs:
        summary["executions"] = int(execs[-1])
    if avg:
        summary["avg_cycles"] = int(avg[-1])
    if verilog:
        summary["verilog"] = str(verilog)

    if exit_code != 0 or errors:
        return FAIL, summary

    # Bambu prints its banner before doing any work, so the banner alone proves
    # nothing. The flip-flop line is the first marker that only appears once
    # synthesis has actually finished; without it the log is truncated, the run
    # died at startup, or this is not a Bambu log at all.
    if not ff:
        summary["note"] = (
            "no 'Total number of flip-flops' line — the HLS phase never "
            "completed, or the log is truncated. Treated as ERROR, not PASS "
            "(bead dwp)."
        )
        return ERROR, summary

    # A --simulate run that produced no cosim block did not verify anything.
    # Exit code 0 here would otherwise report an unverified design as PASS.
    if simulated and not cycles:
        summary["note"] = (
            "--simulate was requested but the log has no 'Total cycles' block — "
            "the co-simulation did not run to completion. Treated as ERROR, not "
            "PASS (bead dwp)."
        )
        return ERROR, summary

    # The generated Verilog is the artefact the whole run exists to produce.
    # An absent or empty .v with a clean exit is the exit-0-empty-report shape.
    if verilog is not None:
        if not verilog.is_file():
            summary["note"] = f"expected Verilog not found: {verilog}"
            return ERROR, summary
        data = verilog.read_bytes()
        if not data:
            summary["note"] = f"generated Verilog is empty: {verilog}"
            return ERROR, summary
        summary["verilog_sha256"] = hashlib.sha256(data).hexdigest()
        summary["verilog_bytes"] = len(data)
        normalized = _BAMBU_DATE_RE.sub(rb"\1<normalized>", data)
        summary["verilog_sha256_normalized"] = hashlib.sha256(normalized).hexdigest()

    return PASS, summary


PARSERS = {
    "verilator": parse_verilator,
    "yosys": parse_yosys,
    "opensta": parse_opensta,
}


def main() -> int:
    """Parse args, summarise the log, print the JSON verdict, return the status."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--tool", required=True, choices=sorted(set(PARSERS) | {"cocotb", "bambu"}))
    ap.add_argument("--log", help="raw log file (also echoed in the JSON)")
    ap.add_argument("--exit-code", type=int, default=0, help="exit status of the wrapped tool")
    ap.add_argument("--results-xml", help="cocotb JUnit results.xml, if any")
    ap.add_argument("--verilog", help="Verilog the bambu run should have produced")
    args = ap.parse_args()

    # An unreadable log is ERROR (2), not a traceback. An uncaught
    # FileNotFoundError exits 1, which a gate reads as FAIL — the very
    # distinction this script exists to keep.
    try:
        text = (
            Path(args.log).read_text(encoding="utf-8", errors="replace")
            if args.log
            else sys.stdin.read()
        )
    except OSError as exc:
        print(
            json.dumps(
                {
                    "tool": args.tool,
                    "status": "ERROR",
                    "exit_code": args.exit_code,
                    "summary": {"errors": [f"could not read log: {exc}"]},
                    "raw_log": args.log,
                },
                indent=2,
            )
        )
        return ERROR

    # cocotb and bambu each need an artefact path, so they take a third argument
    # and stay out of PARSERS (which only holds the 2-arg parsers).
    if args.tool == "cocotb":
        xml_path = Path(args.results_xml) if args.results_xml else None
        status, summary = parse_cocotb(text, args.exit_code, xml_path)
    elif args.tool == "bambu":
        v_path = Path(args.verilog) if args.verilog else None
        status, summary = parse_bambu(text, args.exit_code, v_path)
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
