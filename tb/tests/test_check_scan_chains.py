"""Unit tests for tools/dft/check_scan_chains.py (bead j41m.8).

A good 2-chain netlist passes, and each defect fails.
"""

import subprocess
import sys
from pathlib import Path

import pytest

TOOL = Path(__file__).resolve().parents[2] / "tools" / "dft" / "check_scan_chains.py"

GOOD = """module m (clk, se, scan_in_i, scan_out_o);
  input clk; input se; input [1:0] scan_in_i; output [1:0] scan_out_o;
  wire q0, q1, q2, q3, h;
  sky130_fd_sc_hd__sdfxtp_2 f0 (.CLK(clk), .D(q3), .Q(q0), .SCD(scan_in_i[0]), .SCE(se));
  sky130_fd_sc_hd__sdfxtp_2 f1 (.CLK(clk), .D(q0), .Q(q1), .SCD(h), .SCE(se));
  sky130_fd_sc_hd__dlygate4sd3_1 hb (.A(q0), .X(h));
  sky130_fd_sc_hd__sdfxtp_2 f2 (.CLK(clk), .D(q1), .Q(q2), .SCD(scan_in_i[1]), .SCE(se));
  sky130_fd_sc_hd__dfxtp_2 skipped (.CLK(clk), .D(q2), .Q(q3));
  sky130_fd_sc_hd__buf_2 ob0 (.A(q1), .X(scan_out_o[0]));
  sky130_fd_sc_hd__buf_2 ob1 (.A(q2), .X(scan_out_o[1]));
endmodule
"""


def run(tmp_path, text, *args):
    """Run."""
    nl = tmp_path / "n.v"
    nl.write_text(text)
    return subprocess.run(
        [sys.executable, str(TOOL), str(nl), "--chains", "2", "--en-net", "se", *args],
        capture_output=True,
        text=True,
    )


def test_good_netlist_passes_and_reports_lengths(tmp_path):
    """Good netlist passes and reports lengths."""
    r = run(
        tmp_path, GOOD, "--expect-chains", "2", "--expect-unscanned", "1", "--expect-length", "2,1"
    )
    assert r.returncode == 0, r.stdout
    assert "lengths [2, 1]" in r.stdout


def test_broken_link_is_an_orphan(tmp_path):
    """Broken link is an orphan."""
    r = run(tmp_path, GOOD.replace(".SCD(h)", ".SCD(q2)"))
    assert r.returncode == 1 and "FAIL" in r.stdout


def test_two_sce_nets_fail(tmp_path):
    """Two sce nets fail."""
    r = run(
        tmp_path,
        GOOD.replace(
            "f2 (.CLK(clk), .D(q1), .Q(q2), .SCD(scan_in_i[1]), .SCE(se))",
            "f2 (.CLK(clk), .D(q1), .Q(q2), .SCD(scan_in_i[1]), .SCE(clk))",
        ),
    )
    assert r.returncode == 1 and "SCE" in r.stdout


def test_wrong_scan_out_driver_fails(tmp_path):
    """Wrong scan out driver fails."""
    r = run(tmp_path, GOOD.replace(".A(q2), .X(scan_out_o[1])", ".A(q3), .X(scan_out_o[1])"))
    assert r.returncode == 1


def test_unscanned_count_mismatch_fails(tmp_path):
    """Unscanned count mismatch fails."""
    r = run(tmp_path, GOOD, "--expect-unscanned", "0")
    assert r.returncode == 1


@pytest.mark.parametrize("bad", ["--expect-chains 3", "--expect-length 1,2"])
def test_expectation_mismatch_fails(tmp_path, bad):
    """Expectation mismatch fails."""
    r = run(tmp_path, GOOD, *bad.split())
    assert r.returncode == 1


def test_leftover_tool_port_fails(tmp_path):
    """Leftover tool port fails."""
    r = run(
        tmp_path,
        GOOD.replace("output [1:0] scan_out_o;", "output [1:0] scan_out_o; input scan_in_0;"),
    )
    assert r.returncode == 1 and "own ports" in r.stdout


EXPLAIN = GOOD.replace(
    "sky130_fd_sc_hd__dfxtp_2 skipped (.CLK(clk), .D(q2), .Q(q3));",
    "sky130_fd_sc_hd__dfxtp_2 skipped (.CLK(tck_buf), .D(q2), .Q(q3));\n"
    "  sky130_fd_sc_hd__clkbuf_4 cb (.A(tck_i), .X(tck_buf));\n"
    "  sky130_fd_sc_hd__mux2_8 enmux (.A0(a0), .A1(a1), .S(s), .X(se));",
)


def test_unscanned_flop_explained_by_clock_root_and_sce_root_stops_at_named_net(tmp_path):
    """Unscanned flop explained by clock root and sce root stops at named net."""
    r = run(tmp_path, EXPLAIN, "--explain-clk", "tck_i", "--expect-unscanned", "1")
    assert r.returncode == 0, r.stdout
    assert "clock:tck_i" in r.stdout


def test_unexplained_unscanned_flop_fails(tmp_path):
    """Unexplained unscanned flop fails."""
    r = run(tmp_path, EXPLAIN, "--explain-clk", "scan_clk_i")
    assert r.returncode == 1 and "not explained" in r.stdout


CLONE = """module m (clk, req, scan_in_i, scan_out_o);
  input clk; input req; input [1:0] scan_in_i; output [1:0] scan_out_o;
  wire q0, q1, q2, h, dft_scan_en, en2, done, done_b, other;
  sky130_fd_sc_hd__dfxtp_2 wd (.CLK(clk), .D(q2), .Q(done));
  sky130_fd_sc_hd__buf_2 db (.A(done), .X(done_b));
  sky130_fd_sc_hd__and2_4 en (.A(req), .B(done_b), .X(dft_scan_en));
  sky130_fd_sc_hd__and2_2 clone1 (.A(req), .B(done_b), .X(en2));
  sky130_fd_sc_hd__sdfxtp_2 f0 (.CLK(clk), .D(q2), .Q(q0), .SCD(scan_in_i[0]), .SCE(dft_scan_en));
  sky130_fd_sc_hd__sdfxtp_2 f1 (.CLK(clk), .D(q0), .Q(q1), .SCD(q0), .SCE(en2));
  sky130_fd_sc_hd__sdfxtp_2 f2 (.CLK(clk), .D(q1), .Q(q2), .SCD(scan_in_i[1]), .SCE(dft_scan_en));
  sky130_fd_sc_hd__and2_2 g0 (.A(q1), .B(done), .X(scan_out_o[0]));
  sky130_fd_sc_hd__and2_2 g1 (.A(q2), .B(done_b), .X(scan_out_o[1]));
endmodule
"""


def run_en(tmp_path, text):
    """Run en."""
    nl = tmp_path / "n.v"
    nl.write_text(text)
    return subprocess.run(
        [
            sys.executable,
            str(TOOL),
            str(nl),
            "--chains",
            "2",
            "--en-net",
            "dft_scan_en",
            "--out-gate-net",
            "done",
        ],
        capture_output=True,
        text=True,
    )


def test_resizer_clone_of_the_enable_gate_is_the_same_root(tmp_path):
    """Resizer clone of the enable gate is the same root."""
    r = run_en(tmp_path, CLONE)
    assert r.returncode == 0, r.stdout


def test_a_gate_with_different_inputs_is_a_different_root(tmp_path):
    """A gate with different inputs is a different root."""
    bad = CLONE.replace("clone1 (.A(req), .B(done_b)", "clone1 (.A(req), .B(q0)")
    r = run_en(tmp_path, bad)
    assert r.returncode == 1 and "different roots" in r.stdout, r.stdout


def test_clone_of_a_different_function_is_a_different_root(tmp_path):
    """Clone of a different function is a different root."""
    bad = CLONE.replace("and2_2 clone1", "or2_2 clone1")
    r = run_en(tmp_path, bad)
    assert r.returncode == 1 and "different roots" in r.stdout, r.stdout
