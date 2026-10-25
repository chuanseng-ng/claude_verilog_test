"""Tests for the CVT.ScanInsert LibreLane step (bead j41m.8): catch plugin Python bugs in pytest, not in a 3 h harden.

Three launches of the CPU macro scan run were lost to bugs that no unit test covered:
  1. the step returned pathlib.Path where LibreLane's State needs librelane.common.Path,
  2. insert_dft's dangling ports survived into the netlist,
  3. a call to a Step method that does not exist (self.info).
Fast tests below pin each of those without LibreLane. The end-to-end test runs the real step in isolation (about 30 s) and
is skipped when LibreLane / OpenROAD 26Q2 / a baseline synthesis state are not present.
"""
import ast
import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "pnr" / "sky130" / "soc" / "plugin" / "cvt_scan_step.py"
SRC = PLUGIN.read_text()
TREE = ast.parse(SRC)

# Step members this module may legitimately use through ``self`` (verified against librelane/steps/step.py).
KNOWN_SELF = {"config", "step_dir", "toolbox", "run_subprocess", "warn", "err", "_binary", "_libs_and_lefs"}


def _load_strip():
    nodes = [
        n
        for n in TREE.body
        if (isinstance(n, ast.FunctionDef) and n.name == "strip_tool_ports")
        or (isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "_TOOL_PORT_RE" for t in n.targets))
    ]
    assert len(nodes) == 2
    ns = {"re": re, "Tuple": tuple, "List": list, "StepError": RuntimeError}
    exec(compile(ast.Module(nodes, []), str(PLUGIN), "exec"), ns)  # noqa: S102 - our own source
    return ns["strip_tool_ports"]


def test_path_comes_from_librelane_not_pathlib():
    """Bug 1: State rejects pathlib.Path ('Value at .nl is not a Path')."""
    assert re.search(r"^from librelane\.common import Path\b", SRC, re.M)
    assert not re.search(r"^from pathlib import Path\b", SRC, re.M)
    assert not re.search(r"^import pathlib\b", SRC, re.M)


def test_step_only_uses_known_self_members():
    """Bug 3: self.info does not exist on a Step."""
    cls = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == "CVTScanInsert")
    used = {
        n.attr
        for n in ast.walk(cls)
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == "self"
    }
    defined = {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}
    unknown = used - KNOWN_SELF - defined - {"id", "name", "long_name", "inputs", "outputs", "config_vars"}
    assert not unknown, f"CVTScanInsert uses unknown Step member(s) {sorted(unknown)}"


def test_logging_goes_through_librelane_logging():
    assert "from librelane.logging import info as _log_info" in SRC
    assert "_log_info(" in SRC


HEADER = """module top (clk,
    a,
    scan_in_i,
    scan_out_o,
    scan_enable_0,
    scan_in_0,
    scan_out_0);
 input clk;
 input a;
 input [1:0] scan_in_i;
 output [1:0] scan_out_o;
 input scan_enable_0;
 input scan_in_0;
 output scan_out_0;
 wire x;
endmodule
"""


def test_strip_removes_tool_ports_and_keeps_the_rest():
    out, dropped = _load_strip()(HEADER)
    assert dropped == ["scan_enable_0", "scan_in_0", "scan_out_0"]
    assert "scan_enable_0" not in out and "scan_in_0" not in out and "scan_out_0" not in out
    assert "scan_in_i" in out and "scan_out_o" in out
    assert re.search(r"scan_out_o\);", out)  # header still closes properly


def test_strip_refuses_a_still_referenced_tool_port():
    bad = HEADER.replace(" wire x;", " wire x;\n sky130_fd_sc_hd__buf_2 b (.A(scan_in_0), .X(x));")
    with pytest.raises(RuntimeError):
        _load_strip()(bad)


def test_flow_inserts_the_step_after_the_assign_checker():
    assert "idx = steps.index(NetlistAssignStatements)" in SRC
    assert "steps[: idx + 1] + [CVTScanInsert] + steps[idx + 1 :]" in SRC


# ------------------------------------------------------------------ end to end (real LibreLane, 30 s)
SOC_STATE = Path("/nobackup/sky130_soc_runs/RUN_2026-10-25_08-28-45/06-checker-netlistassignstatements/state_out.json")
OPENROAD = Path("/nix/store/hgqrwa4687mf7n0y2x6lcgx1kj42sfga-openroad-26Q2/bin/openroad")
LIBRELANE = Path.home() / "Downloads" / "Github" / "librelane"


@pytest.mark.skipif(
    not (SOC_STATE.is_file() and OPENROAD.is_file() and LIBRELANE.is_dir()),
    reason="needs LibreLane checkout, OpenROAD 26Q2 and the 08-28-45 synthesis state",
)
def test_step_runs_end_to_end_in_isolation():
    r = subprocess.run(
        [
            "bash",
            str(ROOT / "tools" / "dft" / "run_scan_step_isolated.sh"),
            str(ROOT / "pnr" / "sky130" / "soc" / "config_rccal.json"),
            str(SOC_STATE),
            "pytest_scan_iso",
            "/nobackup/sky130_soc_runs",
        ],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    nl = next(line.split(" ", 1)[1] for line in r.stdout.splitlines() if line.startswith("NETLIST "))
    chk = subprocess.run(
        ["python3", str(ROOT / "tools" / "dft" / "check_scan_chains.py"), nl, "--en-net", "dft_scan_en",
         "--expect-chains", "6", "--expect-unscanned", "922"],
        capture_output=True,
        text=True,
    )
    assert chk.returncode == 0, chk.stdout


def test_run_strips_tool_ports_before_writing_the_netlist():
    """Bug 2: the strip must be applied to the netlist the step hands on (killed mutant: call removed)."""
    run = next(
        n for n in ast.walk(next(c for c in TREE.body if isinstance(c, ast.ClassDef) and c.name == "CVTScanInsert"))
        if isinstance(n, ast.FunctionDef) and n.name == "run"
    )
    calls = [n.func.id for n in ast.walk(run) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    assert "strip_tool_ports" in calls
