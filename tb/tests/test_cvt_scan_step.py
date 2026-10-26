"""Tests for the CVT.ScanInsert LibreLane step (bead j41m.8).

Catch plugin Python bugs in pytest, not in a 3 h harden.

Three launches of the CPU macro scan run were lost to bugs that no unit test covered:
  1. the step returned pathlib.Path where LibreLane's State needs librelane.common.Path,
  2. insert_dft's dangling ports survived into the netlist,
  3. a call to a Step method that does not exist (self.info).
Fast tests below pin each of those without LibreLane. The end-to-end test runs the real step in
isolation (about 30 s) and is skipped when LibreLane, OpenROAD 26Q2 or a baseline synthesis
state are not present.
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

# Step members this module may use through ``self`` (verified against librelane/steps/step.py).
KNOWN_SELF = {
    "config",
    "step_dir",
    "toolbox",
    "run_subprocess",
    "warn",
    "err",
    "_binary",
    "_libs_and_lefs",
}


def _load_strip():
    nodes = [
        n
        for n in TREE.body
        if (isinstance(n, ast.FunctionDef) and n.name == "strip_tool_ports")
        or (
            isinstance(n, ast.Assign)
            and any(getattr(t, "id", "") == "_TOOL_PORT_RE" for t in n.targets)
        )
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
    unknown = (
        used
        - KNOWN_SELF
        - defined
        - {"id", "name", "long_name", "inputs", "outputs", "config_vars"}
    )
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


# ------------------------------------------------------------ end to end (real LibreLane, 30 s)
SOC_STATE = Path(
    "/nobackup/sky130_soc_runs/RUN_2026-10-25_08-28-45/06-checker-netlistassignstatements/state_out.json"
)
OPENROAD = Path("/nix/store/hgqrwa4687mf7n0y2x6lcgx1kj42sfga-openroad-26Q2/bin/openroad")
LIBRELANE = Path.home() / "Downloads" / "Github" / "librelane"


def test_run_strips_tool_ports_before_writing_the_netlist():
    """Bug 2: the strip must be applied to the netlist the step hands on (mutant: call removed)."""
    run = next(
        n
        for n in ast.walk(
            next(c for c in TREE.body if isinstance(c, ast.ClassDef) and c.name == "CVTScanInsert")
        )
        if isinstance(n, ast.FunctionDef) and n.name == "run"
    )
    calls = [
        n.func.id for n in ast.walk(run) if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    ]
    assert "strip_tool_ports" in calls


# ------------------------------------------------------------ scan_out wipe-done gate (bead j41m.17, decision 5a)
import sys  # noqa: E402

TCL = ROOT / "pnr" / "sky130" / "soc" / "plugin" / "librelane_plugin_cvt_sky130" / "tcl" / "scan_insert.tcl"
TCL_SRC = TCL.read_text()
CHECKER = ROOT / "tools" / "dft" / "check_scan_chains.py"
SOC_CFG = ROOT / "pnr" / "sky130" / "soc" / "config_rccal.json"
CPU_CFG = ROOT / "pnr" / "sky130" / "cpu" / "config.json"

# Two chains: one ends in an ordinary flop, one ends in a "crypto" flop. Both ports are ANDed with crypto_wipe_done,
# the way CVT.ScanInsert builds them (and2 A = chain last Q, B = wipe-done net).
GATED = """module m (clk, se, scan_in_i, scan_out_o);
  input clk; input se; input [1:0] scan_in_i; output [1:0] scan_out_o;
  wire q0, q1, q2, q3, h, crypto_wipe_done, wd_b, mid;
  sky130_fd_sc_hd__sdfxtp_2 f0 (.CLK(clk), .D(q3), .Q(q0), .SCD(scan_in_i[0]), .SCE(se));
  sky130_fd_sc_hd__sdfxtp_2 f1 (.CLK(clk), .D(q0), .Q(q1), .SCD(q0), .SCE(se));
  sky130_fd_sc_hd__sdfxtp_2 f2 (.CLK(clk), .D(q1), .Q(q2), .SCD(scan_in_i[1]), .SCE(se));
  sky130_fd_sc_hd__dfxtp_2 skipped (.CLK(clk), .D(q2), .Q(q3));
  sky130_fd_sc_hd__dfxtp_2 wd (.CLK(clk), .D(q3), .Q(crypto_wipe_done));
  sky130_fd_sc_hd__and2_2 g0 (.A(q1), .B(crypto_wipe_done), .X(scan_out_o[0]));
  sky130_fd_sc_hd__buf_2 wb (.A(crypto_wipe_done), .X(wd_b));
  sky130_fd_sc_hd__and2_2 g1 (.A(wd_b), .B(q2), .X(mid));
  sky130_fd_sc_hd__buf_2 pb (.A(mid), .X(scan_out_o[1]));
endmodule
"""


def _check(tmp_path, text, *extra):
    nl = tmp_path / "n.v"
    nl.write_text(text)
    return subprocess.run(
        [sys.executable, str(CHECKER), str(nl), "--chains", "2", "--en-net", "se", *extra],
        capture_output=True,
        text=True,
    )


def test_checker_accepts_gated_scan_outs_through_buffers_either_pin_order(tmp_path):
    r = _check(tmp_path, GATED, "--out-gate-net", "crypto_wipe_done", "--expect-chains", "2")
    assert r.returncode == 0, r.stdout


def test_checker_mutation_buffer_instead_of_and_fails(tmp_path):
    """Mutation: the AND replaced by a buffer (the pre-j41m.17 netlist) must be an error."""
    bad = GATED.replace(
        "sky130_fd_sc_hd__and2_2 g0 (.A(q1), .B(crypto_wipe_done), .X(scan_out_o[0]));",
        "sky130_fd_sc_hd__buf_2 g0 (.A(q1), .X(scan_out_o[0]));",
    )
    r = _check(tmp_path, bad, "--out-gate-net", "crypto_wipe_done")
    assert r.returncode == 1 and "no wipe-done gate" in r.stdout, r.stdout


def test_checker_gate_on_the_wrong_net_fails(tmp_path):
    bad = GATED.replace(".B(crypto_wipe_done), .X(scan_out_o[0])", ".B(q3), .X(scan_out_o[0])")
    r = _check(tmp_path, bad, "--out-gate-net", "crypto_wipe_done")
    assert r.returncode == 1 and "must trace to" in r.stdout, r.stdout


def test_checker_gate_on_the_wrong_flop_fails(tmp_path):
    bad = GATED.replace(".A(q1), .B(crypto_wipe_done)", ".A(q2), .B(crypto_wipe_done)")
    r = _check(tmp_path, bad, "--out-gate-net", "crypto_wipe_done")
    assert r.returncode == 1, r.stdout


def test_checker_other_gate_type_fails(tmp_path):
    bad = GATED.replace("sky130_fd_sc_hd__and2_2 g0", "sky130_fd_sc_hd__or2_2 g0")
    r = _check(tmp_path, bad, "--out-gate-net", "crypto_wipe_done")
    assert r.returncode == 1, r.stdout


def test_checker_without_the_option_still_checks_the_plain_buffer_form(tmp_path):
    """CPU macro mode: no crypto, plain buffer from the last flop."""
    plain = GATED.replace(
        "sky130_fd_sc_hd__and2_2 g0 (.A(q1), .B(crypto_wipe_done), .X(scan_out_o[0]));",
        "sky130_fd_sc_hd__buf_2 g0 (.A(q1), .X(scan_out_o[0]));",
    ).replace(
        "sky130_fd_sc_hd__and2_2 g1 (.A(wd_b), .B(q2), .X(mid));\n  sky130_fd_sc_hd__buf_2 pb (.A(mid), .X(scan_out_o[1]));",
        "sky130_fd_sc_hd__buf_2 pb (.A(q2), .X(scan_out_o[1]));",
    )
    assert _check(tmp_path, plain).returncode == 0
    assert _check(tmp_path, GATED).returncode == 1  # an AND is not a plain-buffer end


def test_soc_config_selects_the_gate_and_cpu_config_does_not():
    import json

    soc = json.loads(SOC_CFG.read_text())
    assert soc["CVT_SCAN_OUT_GATE_NET"] == "crypto_wipe_done"
    assert soc["CVT_SCAN_OUT_GATE_CELL"].startswith("sky130_fd_sc_hd__and2_")
    cpu = json.loads(CPU_CFG.read_text())
    assert "CVT_SCAN_OUT_GATE_NET" not in cpu  # no crypto in the macro


def test_plugin_declares_and_forwards_the_gate_variables():
    assert '"CVT_SCAN_OUT_GATE_NET"' in SRC and '"CVT_SCAN_OUT_GATE_CELL"' in SRC
    assert 'CVT_SCAN_OUT_GATE_NET=cfg["CVT_SCAN_OUT_GATE_NET"] or ""' in SRC
    # the step re-checks the Tcl report: a configured gate that was not built is an error, not a silent buffer
    assert 'kv.get("scan_out_gate_net") != cfg["CVT_SCAN_OUT_GATE_NET"]' in SRC


def test_tcl_fails_loudly_when_the_net_is_missing_and_never_falls_back_to_a_buffer():
    i_find = TCL_SRC.index("[$block findNet $gate_net_nm]")
    i_err = TCL_SRC.index("scan_out gate net '$gate_net_nm' not found")
    i_exit = TCL_SRC.index("exit 2", i_err)
    i_first_port_edit = TCL_SRC.index("odb::dbBTerm_destroy $sin")
    assert i_find < i_err < i_exit < i_first_port_edit  # resolved and rejected before any port is touched
    assert "Refusing to fall back to a buffer" in TCL_SRC
    # exactly one place creates the buffer, and it is the else-arm of the gate test
    assert TCL_SRC.count('"u_cvt_scan_out_buf_$idx"') == 1
    assert re.search(r"if \{\$gate_net ne \"NULL\"\} \{[^}]*u_cvt_scan_out_gate_\$idx[^}]*\} else \{[^}]*u_cvt_scan_out_buf_\$idx", TCL_SRC, re.S)


GATE_STATE = Path("/nobackup/sky130_soc_runs/j41m17_synth_keep/06-checker-netlistassignstatements/state_out.json")


@pytest.mark.skipif(
    not (SOC_STATE.is_file() and OPENROAD.is_file() and LIBRELANE.is_dir()),
    reason="needs LibreLane checkout, OpenROAD 26Q2 and the 08-28-45 synthesis state",
)
def test_step_fails_loudly_when_the_net_was_optimised_away():
    """The 08-28-45 netlist predates crypto_wipe_done: the gated config must fail, not fall back to a buffer."""
    r = subprocess.run(
        ["bash", str(ROOT / "tools" / "dft" / "run_scan_step_isolated.sh"), str(SOC_CFG), str(SOC_STATE),
         "pytest_scan_gate_missing", "/nobackup/sky130_soc_runs"],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 1, r.stdout + r.stderr
    log = Path(__import__("os").environ.get("TMPDIR", "/tmp")) / "run_scan_step_isolated.pytest_scan_gate_missing.log"
    assert "CVT-SCAN-ERROR: scan_out gate net 'crypto_wipe_done' not found" in log.read_text()


@pytest.mark.skipif(
    not (GATE_STATE.is_file() and OPENROAD.is_file() and LIBRELANE.is_dir()),
    reason="needs a synthesis state whose netlist keeps crypto_wipe_done",
)
def test_step_builds_the_gate_end_to_end_and_the_checker_accepts_it():
    r = subprocess.run(
        ["bash", str(ROOT / "tools" / "dft" / "run_scan_step_isolated.sh"), str(SOC_CFG), str(GATE_STATE),
         "pytest_scan_gate_ok", "/nobackup/sky130_soc_runs"],
        capture_output=True,
        text=True,
        timeout=900,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    nl = next(line.split(" ", 1)[1] for line in r.stdout.splitlines() if line.startswith("NETLIST "))
    ok = subprocess.run(
        [sys.executable, str(CHECKER), nl, "--chains", "6", "--en-net", "dft_scan_en", "--out-gate-net",
         "crypto_wipe_done", "--expect-chains", "6", "--expect-unscanned", "922"],
        capture_output=True,
        text=True,
    )
    assert ok.returncode == 0, ok.stdout
    # mutation on the real netlist: swap one AND for a buffer -> must fail
    text = Path(nl).read_text()
    m = re.search(r"sky130_fd_sc_hd__and2_2 u_cvt_scan_out_gate_0 \(\s*\.A\(([^)]*)\),\s*\.B\([^)]*\),\s*\.X\(([^)]*)\)\);", text)
    assert m, "no gate instance for chain 0"
    mutant = text.replace(m.group(0), f"sky130_fd_sc_hd__buf_2 u_cvt_scan_out_gate_0 (.A({m.group(1)}), .X({m.group(2)}));")
    mpath = Path(nl).with_name("mutant.nl.v")
    mpath.write_text(mutant)
    bad = subprocess.run(
        [sys.executable, str(CHECKER), str(mpath), "--chains", "6", "--en-net", "dft_scan_en", "--out-gate-net", "crypto_wipe_done"],
        capture_output=True,
        text=True,
    )
    assert bad.returncode == 1 and "no wipe-done gate" in bad.stdout


def test_rtl_keeps_the_wipe_done_net_through_synthesis():
    """crypto_wipe_done feeds only one AND; without (* keep *) yosys/ABC merges it away and the scan_out gate cannot find it."""
    rtl = (ROOT / "rtl" / "soc" / "soc_top.sv").read_text()
    assert re.search(r"\(\*\s*keep\s*\*\)\s*logic\s+crypto_wipe_done\s*;", rtl)
    assert "assign dft_scan_en = dft_scan_en_req & crypto_wipe_done;" in rtl
