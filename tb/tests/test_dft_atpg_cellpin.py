# ruff: noqa: E501
"""Tests for the cell-pin fault universe of tools/dft/atpg/mk_cut.py --cellpin.

The cell-pin cut wraps every Liberty cell model so each port passes through a kept `$_BUF_`, lowers Yosys' primitive gates
to `.names` covers itself (abc is not run) and lists the output net of every surviving pin buffer in cut_sites.txt.  A Quaigh
output stuck-at fault on such a buffer (`quaigh atpg --fault-sites`, patch 0002) is the pin fault.  These tests pin:
* the wrapper (one buffer per port, direction-correct, port-less cells copied, a port without a direction refused);
* every gate cover against an independent truth table, the flop lowering and the refusal of an unknown `$` primitive;
* end to end on a hand-written Sky130 netlist (needs Yosys and the tt Liberty, else skipped): the pin-buffer count equals the
  instance pins counted independently from the netlist, the clock pin is the only pin dropped, and the site list is exact.
"""

import itertools
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))

import cellpin_report  # type: ignore[import-not-found]  # noqa: E402
import mk_cut  # type: ignore[import-not-found]  # noqa: E402
import pin_inject  # type: ignore[import-not-found]  # noqa: E402

LIBV = """\
module cellA(Y, A, B);
  wire _0_;
  input A;
  wire A;
  input B;
  wire B;
  output Y;
  wire Y;
  \\$_AND_ _1_ (.A(A), .B(B), .Y(Y));
endmodule
module tapcell();
endmodule
"""


def test_wrap_cellpin_one_buffer_per_port_with_direction():
    text, n = mk_cut.wrap_cellpin(LIBV)
    assert n == 1
    assert "module cellA__core(Y, A, B);" in text
    assert "module tapcell();" in text and "tapcell__core" not in text
    bufs = re.findall(r"\\\$_BUF_ cvtpinbuf_(\w+) \(\.A\((\w+)\), \.Y\((\w+)\)\);", text)
    assert sorted(bufs) == [("A", "A", "cvtpin_A"), ("B", "B", "cvtpin_B"), ("Y", "cvtpin_Y", "Y")]
    assert text.count("(* keep *)") == 3
    assert "cellA__core u_core(.Y(cvtpin_Y), .A(cvtpin_A), .B(cvtpin_B));" in text


def test_wrap_cellpin_leaves_clock_pins_unbuffered():
    text, _ = mk_cut.wrap_cellpin(
        "module ff(CLK, D, Q);\n  input CLK;\n  input D;\n  output Q;\nendmodule\n"
    )
    assert "cvtpinbuf_CLK" not in text and "wire cvtpin_CLK = CLK;" in text
    assert "cvtpinbuf_D" in text and "cvtpinbuf_Q" in text


def test_undefined_cone_outputs_and_drop():
    b = ".model m\n.inputs a\n.outputs y u.clk_i w\n.names a y\n1 1\n.names g c1\n1 1\n.names c1 u.clk_i\n1 1\n.names a c1 w\n11 1\n.end\n"
    assert mk_cut.undefined_cone_outputs(b) == ["u.clk_i", "w"]
    assert ".outputs y w\n" in mk_cut.drop_outputs(b, ["u.clk_i"])


def test_lower_gates_global_clock_flop():
    assert mk_cut.lower_gates(".gate \\$_FF_ D=a Q=b")[0] == ".latch a b 2"


def test_wrap_cellpin_refuses_port_without_direction():
    with pytest.raises(SystemExit, match="no direction"):
        mk_cut.wrap_cellpin("module bad(A, Q);\n  input A;\nendmodule\n")


ORACLE = {
    "$_BUF_": lambda a: a,
    "$_NOT_": lambda a: 1 - a,
    "$_AND_": lambda a, b: a & b,
    "$_OR_": lambda a, b: a | b,
    "$_NAND_": lambda a, b: 1 - (a & b),
    "$_NOR_": lambda a, b: 1 - (a | b),
    "$_XOR_": lambda a, b: a ^ b,
    "$_XNOR_": lambda a, b: 1 - (a ^ b),
    "$_ANDNOT_": lambda a, b: a & (1 - b),
    "$_ORNOT_": lambda a, b: a | (1 - b),
    "$_MUX_": lambda a, b, s: b if s else a,
}


def eval_cover(rows, bits):
    for r in rows:
        cube, out = r.split()
        assert out == "1"
        if all(c == "-" or int(c) == v for c, v in zip(cube, bits)):
            return 1
    return 0


@pytest.mark.parametrize("typ", sorted(ORACLE))
def test_gate_cover_matches_truth_table(typ):
    ins, rows = mk_cut.GATE_COVERS[typ]
    for bits in itertools.product((0, 1), repeat=len(ins)):
        assert eval_cover(rows, bits) == ORACLE[typ](*bits), (typ, bits)


def test_every_cover_has_an_oracle():
    assert set(mk_cut.GATE_COVERS) == set(ORACLE)


def test_lower_gates_names_latches_and_sites():
    blif = "\n".join(
        [
            ".model m",
            ".inputs a b c",
            ".gate \\$_BUF_ A=a Y=u.cvtpin_A",
            ".gate \\$_AND_ A=u.cvtpin_A B=b Y=n1",
            ".gate \\$_DFF_P_ C=c D=n1 Q=q",
            ".gate \\$_DFF_N_ C=c D=q Q=q2",
            ".gate sky130_fd_sc_hd__dlclkp_1 CLK=c GATE=a GCLK=g",
            ".end",
        ]
    )
    text, sites, census = mk_cut.lower_gates(blif)
    assert sites == ["u.cvtpin_A"]
    assert census == {"$_BUF_": 1, "$_AND_": 1, "$_DFF_P_": 1, "$_DFF_N_": 1}
    assert ".names a u.cvtpin_A\n1 1" in text
    assert ".names u.cvtpin_A b n1\n11 1" in text
    assert ".latch n1 q re c 2" in text and ".latch q q2 fe c 2" in text
    assert (
        ".gate sky130_fd_sc_hd__dlclkp_1" in text
    )  # a function-less cell is left for dce_blif to count


def test_lower_gates_refuses_unknown_primitive():
    with pytest.raises(SystemExit, match="no cover"):
        mk_cut.lower_gates(".gate \\$_AOI3_ A=a B=b C=c Y=y")


YOSYS = os.environ.get("YOSYS", mk_cut.DEFAULT_YOSYS)
LIB = os.environ.get("SKY130_TT_LIB", mk_cut.DEFAULT_LIB)
NETLIST = """\
module top(clk, a, b, c, y, q);
  input clk;
  input a;
  input b;
  input c;
  output y;
  output q;
  wire n1;
  wire n2;
  sky130_fd_sc_hd__nand2_1 g1 (.A(a), .B(b), .Y(n1));
  sky130_fd_sc_hd__a21oi_1 g2 (.A1(n1), .A2(c), .B1(a), .Y(n2));
  sky130_fd_sc_hd__inv_1 g3 (.A(n2), .Y(y));
  sky130_fd_sc_hd__dfxtp_1 f1 (.CLK(clk), .D(n2), .Q(q));
endmodule
"""


@pytest.mark.skipif(
    not (Path(YOSYS).exists() and Path(LIB).exists()),
    reason="needs Yosys and the Sky130 tt Liberty",
)
def test_cellpin_cut_end_to_end(tmp_path):
    nl = tmp_path / "top.v"
    nl.write_text(NETLIST)
    out = tmp_path / "cut"
    r = subprocess.run(
        [
            sys.executable,
            str(ATPG_DIR / "mk_cut.py"),
            str(nl),
            "--top",
            "top",
            "--out",
            str(out),
            "--cellpin",
            "--yosys",
            YOSYS,
            "--lib",
            LIB,
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    info = json.loads((out / "cut_info.json").read_text())
    # independent count: every named pin connection of every instance in the netlist
    pins = len(re.findall(r"\.\w+\(\w+\)", NETLIST))
    assert pins == 12  # nand2 3 + a21oi 4 + inv 2 + dfxtp 3
    assert info["pin_buffers"] == pins - 1  # the flop CLK pin is not wrapped (mk_cut.CLOCK_PINS)
    assert info["flops"] == 1
    sites = (out / "cut_sites.txt").read_text().split()
    # every non-clock pin is a fault site
    assert info["fault_sites"] == pins - 1 == len(sites) == len(set(sites))
    assert info["pin_buffers_dead_dropped"] == 0
    assert info["pin_faults"] == 2 * len(sites)
    assert not any(s.endswith("cvtpin_CLK") for s in sites)
    blif = (out / "cut.blif").read_text()
    for s in sites:
        assert re.search(rf"^\.names \S+ {re.escape(s)}\n1 1$", blif, re.M), s


# --- cellpin_report.py: coverage arithmetic and the scan-path credit --------------------------------------------------------
SITES = ["u_dut.f1.cvtpin_D", "u_dut.f1.cvtpin_SCD", "u_dut.f1.cvtpin_SCE", "u_dut.n1"]
#        fault: 0 1          2 3                    4 5                    6 7


def test_cellpin_report_raw_and_credited():
    st = ["D", "D", "U", "U", "U", "D", "D", "R"]
    r = cellpin_report.summarise(SITES, st, whole_faults=10)
    assert (r["faults"], r["detected"], r["untestable_proven"], r["unresolved"]) == (8, 4, 3, 1)
    assert r["fault_coverage_pct"] == 50.0 and r["test_coverage_pct"] == 80.0
    # SCD (faults 2, 3) and SCE (4, 5) credited: detected outside them = 0, 1, 6 -> 3, plus 4 credited = 7 of 8
    assert r["scan_path_pin_faults"] == 4 and r["scan_path_detected_in_capture"] == 1
    assert r["credited_fault_coverage_pct"] == 87.5
    assert (
        r["credited_test_coverage_pct"] == 100.0 * 7 / 8
    )  # no untestable fault outside the scan-path pins
    assert r["whole_fault_coverage_pct"] == 40.0 and r["whole_credited_fault_coverage_pct"] == 70.0
    assert r["by_pin"]["SCD"] == {"faults": 2, "detected": 0, "untestable": 2}
    assert r["by_pin"]["<output>"] == {"faults": 2, "detected": 1, "untestable": 0}


def test_cellpin_report_report_mode_has_no_test_coverage():
    r = cellpin_report.summarise(SITES[:1], ["D", "N"])
    assert r["fault_coverage_pct"] == 50.0 and r["test_coverage_pct"] is None


def test_cellpin_report_refuses_a_short_report(tmp_path):
    f = tmp_path / "r.txt"
    f.write_text("0 D\n")
    with pytest.raises(SystemExit, match="missing"):
        cellpin_report.load_report(f, 2)


# --- pin_inject.py: mapping a site back to its pin and rewriting the netlist ------------------------------------------------
PIN_NETLIST = """\
module top(a, b, y);
  input a;
  input b;
  output y;
  wire n1;
  sky130_fd_sc_hd__nand2_1 g1 (
    .A(a),
    .B(b),
    .Y(n1)
  );
  sky130_fd_sc_hd__inv_1 \\g2.x  (
    .A(n1),
    .Y(y)
  );
endmodule
"""


def test_site_pins_maps_input_and_output_sites():
    blif = ".names u_dut.g1.cvtpin_Y u_dut.n1\n1 1\n.names u_dut.n1 u_dut.g2.x.cvtpin_A\n1 1\n"
    m = pin_inject.site_pins(blif, ["u_dut.n1", "u_dut.g2.x.cvtpin_A"])
    assert m == {"u_dut.n1": ("g1", "Y", "out"), "u_dut.g2.x.cvtpin_A": ("g2.x", "A", "in")}
    with pytest.raises(SystemExit, match="cannot map"):
        pin_inject.site_pins(blif, ["u_dut.nowhere"])


def test_inject_rewrites_branch_and_stem():
    t = pin_inject.inject(PIN_NETLIST, "top", [("g2.x", "A", "in", 1), ("g1", "Y", "out", 0)])
    assert "module top(a, b, y, fsel_0, fsel_1);" in t
    assert "input fsel_0;" in t and "input fsel_1;" in t
    assert ".A(cvtf_0)" in t and ".Y(cvtf_1)" in t
    assert "assign cvtf_0 = fsel_0 ? 1'b1 : n1;" in t  # branch: only g2.x sees the fault
    assert "assign n1 = fsel_1 ? 1'b0 : cvtf_1;" in t  # stem: every load of n1 sees it
    assert t.count(".A(a)") == 1  # g1's own pins untouched
    with pytest.raises(SystemExit, match="not found"):
        pin_inject.inject(PIN_NETLIST, "top", [("g9", "A", "in", 0)])
    with pytest.raises(SystemExit, match="twice"):
        pin_inject.inject(PIN_NETLIST, "top", [("g1", "A", "in", 0), ("g1", "A", "in", 1)])


def test_unwrap_cts_cells_only_clock_tree_drivers():
    nl = (
        "  sky130_fd_sc_hd__clkbuf_16 clkbuf_0_tck_i (\n    .A(tck_i),\n    .X(clknet_0_tck_i)\n  );\n"
        "  sky130_fd_sc_hd__clkinv_16 _075649_ (\n    .A(d),\n    .Y(e)\n  );\n"
        "  sky130_fd_sc_hd__dfxtp_1 \\f1  (\n    .CLK(clknet_0_tck_i),\n    .D(a),\n    .Q(b)\n  );\n"
    )
    out, n = mk_cut.unwrap_cts_cells(nl)
    assert n == 1
    assert "sky130_fd_sc_hd__clkbuf_16__core clkbuf_0_tck_i (" in out
    assert (
        "sky130_fd_sc_hd__clkinv_16 _075649_ (" in out
    )  # a clock cell type on a data net stays wrapped
    assert "sky130_fd_sc_hd__dfxtp_1 \\f1  (" in out  # a flop clocked by the tree stays wrapped
    # the OpenROAD netlist format: first pin on the header line
    out2, n2 = mk_cut.unwrap_cts_cells(
        " sky130_fd_sc_hd__clkbuf_16 clkbuf_0_tck_i (.A(tck_i),\n    .X(clknet_0_tck_i));\n"
        " sky130_fd_sc_hd__inv_2 _1_ (.A(a),\n    .Y(b));\n"
    )
    assert n2 == 1 and " sky130_fd_sc_hd__clkbuf_16__core clkbuf_0_tck_i (.A(tck_i)," in out2
    assert " sky130_fd_sc_hd__inv_2 _1_ (.A(a)," in out2


def test_match_port_order():
    t = ".model m\n.inputs b a\n.outputs y z\n.names a b y\n11 1\n.names a z\n1 1\n.end\n"
    ref = ".model r\n.inputs a b\n.outputs z y\n.end\n"
    out = mk_cut.match_port_order(t, ref)
    assert ".inputs a b\n" in out and ".outputs z y\n" in out
    with pytest.raises(SystemExit, match="differ"):
        mk_cut.match_port_order(t, ".model r\n.inputs a c\n.outputs z y\n.end\n")
