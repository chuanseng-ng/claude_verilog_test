#!/usr/bin/env python3
"""tools/formal/run_eqy.py — EQY sv2v-vs-RTL equivalence runner (bead claude_verilog_test-q7n).

Compares individual modules from the sv2v-converted ASAP7 SoC netlist
(pnr/asap7/soc/soc_top_sv2v.v -- the netlist the ASAP7 SoC synth flow actually
consumes, see pnr/Makefile SOC_SV2V_DEFINES) against the original SystemVerilog
RTL, module by module, using Yosys EQY. Registry: tools/formal/modules.json.

MUST run with eqy/yosys/sby on PATH -- i.e. inside the librelane nix devshell.
Use run_eqy.sh, which wraps this script in a single `nix develop` session so
the devshell's startup cost is paid once, not once per module.

Same verdict discipline as tools/eda/summarize.py (bead dwp): a tool exiting 0
with an empty/unparsable report must never read as PASS. Here that means: EQY
"DONE (PASS...)" is necessary but not sufficient -- the workdir's matched.ids
must also exist and be non-empty, or the run is downgraded to ERROR (a proof
that matched zero points proved nothing).

Exit codes (whole invocation, across all requested modules):
    0  PASS   every requested module PASSED
    1  FAIL   at least one module's EQY run reported FAIL (a real inequivalence
               was found, or eqy's own partitions did not all prove)
    2  ERROR  at least one module could not be evaluated (setup error, empty
               match set, tool crash) and none FAILed
    3  no modules matched the given selector
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PASS, FAIL, ERROR = 0, 1, 2

TOOLS_FORMAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = TOOLS_FORMAL_DIR.parent.parent
REGISTRY_PATH = TOOLS_FORMAL_DIR / "modules.json"
FIXTURES_DIR = TOOLS_FORMAL_DIR / "fixtures"
DEFAULT_WORKDIR_ROOT = REPO_ROOT / "sim/build/formal-eqy"

MODULE_RE_TMPL = r"^module\s+{name}\b.*?^endmodule\b"


def load_registry() -> dict:
    return json.loads(REGISTRY_PATH.read_text())


def extract_module(netlist_text: str, module_name: str) -> str | None:
    """Pull one `module NAME ... endmodule` block out of the flat sv2v netlist.

    sv2v/Yosys output places `module`/`endmodule` at column 0 with no nesting
    (Verilog modules cannot nest), so a straightforward anchored regex is
    reliable here -- confirmed by manual inspection of all 28 module
    boundaries in pnr/asap7/soc/soc_top_sv2v.v before this script was written.
    """
    pattern = re.compile(MODULE_RE_TMPL.format(name=re.escape(module_name)), re.M | re.S)
    m = pattern.search(netlist_text)
    return (m.group(0) + "\n") if m else None


def build_eqy_config(entry: dict, gate_file: Path, extra_defines: list[str] | None = None) -> str:
    defines = list(entry.get("defines", [])) + list(extra_defines or [])
    def_flags = " ".join(f"-D {d}" for d in defines)

    gold_lines = []
    for f in entry["gold_files"]:
        gold_lines.append(f"read_verilog -sv {def_flags} {REPO_ROOT / f}".rstrip())
    for f in entry.get("common_fixtures", []):
        gold_lines.append(f"read_verilog {FIXTURES_DIR / f}")
    gold_lines.append(f"prep -top {entry['top']}")

    gate_lines = [f"read_verilog {gate_file}"]
    for f in entry.get("common_fixtures", []):
        gate_lines.append(f"read_verilog {FIXTURES_DIR / f}")
    gate_lines.append(f"prep -top {entry['top']}")

    depth = entry.get("depth", 5)
    return (
        "[gold]\n" + "\n".join(gold_lines) + "\n\n"
        "[gate]\n" + "\n".join(gate_lines) + "\n\n"
        "[strategy simple]\nuse sat\ndepth " + str(depth) + "\n"
    )


def run_eqy_case(config_path: Path, workdir: Path) -> tuple[int, str]:
    if workdir.exists():
        shutil.rmtree(workdir)
    t0 = time.time()
    proc = subprocess.run(
        ["eqy", "-f", "-d", str(workdir), str(config_path)],
        cwd=config_path.parent,
        capture_output=True,
        text=True,
        timeout=900,
    )
    elapsed = time.time() - t0
    log = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode, log, elapsed  # type: ignore[return-value]


def parse_verdict(rc: int, log: str, workdir: Path, module: str) -> dict:
    """Turn eqy's raw exit code + logfile.txt + workdir artifacts into a verdict.

    eqy's own exit codes observed empirically (2026-08, eqy bundled with the
    librelane nix devshell's Yosys 0.46): 0 on "DONE (PASS...)", 2 on
    "DONE (FAIL...)", 1 when source-reading/setup fails before any partition
    is attempted (no matched.ids, no PASS file ever written).
    """
    matched_ids_path = workdir / "matched.ids"
    pass_file = workdir / "PASS"
    logfile_path = workdir / "logfile.txt"
    full_log = log
    if logfile_path.exists():
        full_log += "\n" + logfile_path.read_text()

    matched_count = 0
    matched_lines: list[str] = []
    if matched_ids_path.exists():
        matched_lines = [
            l for l in matched_ids_path.read_text().splitlines() if l.strip() and not l.startswith("#")
        ]
        matched_count = len(matched_lines)

    proved = re.findall(r"Successfully proved equivalence of partition (\S+)", full_log)
    failed_partitions = re.findall(r"Failed to prove equivalence of partition (\S+)", full_log)
    partitions_total = len(set(proved) | set(failed_partitions))

    done_pass = "DONE (PASS" in full_log
    done_fail = "DONE (FAIL" in full_log

    if done_pass:
        if matched_count == 0 or not pass_file.exists():
            status = "ERROR"
            reason = (
                "eqy reported DONE (PASS) but matched.ids is empty or the PASS marker is "
                "missing -- treating as a proof of nothing, not a proof of equivalence "
                "(bead dwp discipline: empty match != PASS)."
            )
        else:
            status = "PASS"
            reason = f"eqy proved equivalence; {matched_count} matched gold/gate points, {partitions_total} partition(s) proved."
    elif done_fail:
        status = "FAIL"
        reason = f"eqy found {len(failed_partitions)} unproved/failed partition(s): {failed_partitions or 'see log'}."
    else:
        status = "ERROR"
        err_lines = [l for l in full_log.splitlines() if "ERROR" in l]
        reason = "eqy did not reach a DONE verdict (setup/read failure)." + (
            f" First error: {err_lines[0]}" if err_lines else ""
        )

    return {
        "module": module,
        "status": status,
        "eqy_exit_code": rc,
        "reason": reason,
        "matched_points": matched_count,
        "partitions_proved": sorted(set(proved)),
        "partitions_failed": sorted(set(failed_partitions)),
        "workdir": str(workdir),
    }


def run_one(entry: dict, gate_netlist_text: str, workdir_root: Path, extra_defines=None, tag="") -> dict:
    module = entry["name"]
    gate_module_names = entry.get("gate_modules", [entry["top"]])
    gate_blocks = []
    missing = []
    for gm in gate_module_names:
        block = extract_module(gate_netlist_text, gm)
        if block is None:
            missing.append(gm)
        else:
            gate_blocks.append(block)
    if missing:
        return {
            "module": module,
            "status": "ERROR",
            "eqy_exit_code": None,
            "reason": f"module(s) {missing} not found in gate netlist (extraction failed)",
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": None,
        }

    case_dir = workdir_root / (module + (f"_{tag}" if tag else ""))
    case_dir.mkdir(parents=True, exist_ok=True)
    gate_file = case_dir / f"gate_{entry['top']}.v"
    gate_file.write_text("\n".join(gate_blocks))

    config_text = build_eqy_config(entry, gate_file, extra_defines=extra_defines)
    config_path = case_dir / f"{module}.eqy"
    config_path.write_text(config_text)

    workdir = case_dir / "run"
    t0 = time.time()
    try:
        rc, log, elapsed = run_eqy_case(config_path, workdir)
    except FileNotFoundError:
        return {
            "module": module,
            "status": "ERROR",
            "eqy_exit_code": 3,
            "reason": "eqy not found on PATH -- run inside `nix develop ~/Downloads/Github/librelane --command ...` (see run_eqy.sh)",
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": str(workdir),
        }
    except subprocess.TimeoutExpired:
        return {
            "module": module,
            "status": "ERROR",
            "eqy_exit_code": None,
            "reason": "eqy timed out after 900s",
            "matched_points": 0,
            "partitions_proved": [],
            "partitions_failed": [],
            "workdir": str(workdir),
        }

    verdict = parse_verdict(rc, log, workdir, module)
    verdict["elapsed_s"] = round(elapsed, 1)
    verdict["tier"] = entry.get("tier")
    verdict["config"] = str(config_path)
    return verdict


def select_modules(registry: dict, args) -> list[dict]:
    mods = registry["modules"]
    if args.module:
        mods = [m for m in mods if m["name"] in args.module]
    elif args.tier:
        mods = [m for m in mods if m["tier"] == args.tier]
    return mods


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--module", action="append", help="run only this module (repeatable)")
    ap.add_argument("--tier", type=int, help="run only this tier")
    ap.add_argument("--all", action="store_true", help="run every module in the registry")
    ap.add_argument("--workdir-root", default=str(DEFAULT_WORKDIR_ROOT))
    ap.add_argument("--json-out", help="write the aggregate JSON summary to this path")
    args = ap.parse_args()

    if not (args.module or args.tier or args.all):
        ap.error("pass --module NAME, --tier N, or --all")

    registry = load_registry()
    gate_netlist_path = REPO_ROOT / registry["gate_netlist"]
    if not gate_netlist_path.exists():
        print(json.dumps({"status": "ERROR", "reason": f"gate netlist not found: {gate_netlist_path}"}))
        return ERROR
    gate_netlist_text = gate_netlist_path.read_text()

    mods = select_modules(registry, args)
    if not mods:
        print(json.dumps({"status": "ERROR", "reason": "no modules matched selector"}))
        return 3

    workdir_root = Path(args.workdir_root)
    workdir_root.mkdir(parents=True, exist_ok=True)

    results = []
    for entry in mods:
        verdict = run_one(entry, gate_netlist_text, workdir_root)
        results.append(verdict)
        print(json.dumps(verdict, indent=2))

    summary = {
        "run_id": "q7n_eqy_sv2v_equivalence",
        "gate_netlist": str(gate_netlist_path),
        "results": results,
        "pass": sum(1 for r in results if r["status"] == "PASS"),
        "fail": sum(1 for r in results if r["status"] == "FAIL"),
        "error": sum(1 for r in results if r["status"] == "ERROR"),
    }
    if args.json_out:
        Path(args.json_out).write_text(json.dumps(summary, indent=2))

    print("\n=== SUMMARY ===")
    for r in results:
        print(f"  {r['module']:<24} tier={r.get('tier')}  {r['status']:<6} matched={r['matched_points']:<4} {r['reason']}")

    if summary["fail"] > 0:
        return FAIL
    if summary["error"] > 0:
        return ERROR
    return PASS


if __name__ == "__main__":
    sys.exit(main())
