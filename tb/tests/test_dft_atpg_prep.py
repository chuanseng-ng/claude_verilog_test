"""Tests for tools/dft/atpg/netlist_prep.py and the cut wrapper helpers in mk_cut.py (bead j41m.15)."""

import json
import re
import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))

import mk_cut  # type: ignore[import-not-found]  # noqa: E402
import netlist_prep as npp  # type: ignore[import-not-found]  # noqa: E402

NETLIST = r"""module soc_top (tck_i, scan_clk_i, clk_i, d_i, q_o);
 input tck_i;
 input scan_clk_i;
 input clk_i;
 input d_i;
 output q_o;
 sky130_fd_sc_hd__clkbuf_4 _b0_ (.A(tck_i), .X(tck_buf));
 sky130_fd_sc_hd__clkinv_2 _i0_ (.A(tck_buf), .Y(tck_n));
 sky130_fd_sc_hd__dfrtp_1 _tapA_ (.CLK(tck_buf), .D(d_i), .RESET_B(rstn), .Q(tapA_q));
 sky130_fd_sc_hd__dfxtp_1 _tapB_ (.CLK(tck_n), .D(d_i), .Q(tapB_q));
 sky130_fd_sc_hd__dfstp_1 _tapC_ (.CLK(tck_buf), .D(d_i), .SET_B(rstn), .Q(tapC_q));
 sky130_fd_sc_hd__dfxtp_1 _sck_ (.CLK(scan_clk_i), .D(d_i), .Q(sck_q));
 sky130_fd_sc_hd__dfxtp_1 _key_ (.CLK(clk_buf), .D(d_i), .Q(\u_crypto.key_q[3] ));
 sky130_fd_sc_hd__dfxtp_1 _odd_ (.CLK(clk_i), .D(d_i), .Q(odd_q));
 sky130_fd_sc_hd__sdfrtp_1 _s1_ (.CLK(clk_i), .D(d_i), .RESET_B(rstn), .SCD(a), .SCE(b),
    .Q(\u_cpu_axi_cdc.u_aw_fifo.u_wr_ptr_to_rd.sync_q[0][0] ));
 sky130_fd_sc_hd__sdfxtp_1 _s2_ (.CLK(clk_i), .D(d_i), .SCD(a), .SCE(b), .Q(plain_q));
 sky130_fd_sc_hd__fill_4 FILLER_1 ();
 sky130_fd_sc_hd__tapvpwrvgnd_1 TAP_1 ();
 sky130_fd_sc_hd__diode_2 ANTENNA_1 (.DIODE(d_i));
endmodule
"""
KEY = r"u_crypto\.(key_q|g_aes\.u_aes\.rk_q)\["


def run(tmp_path, **kw):
    src = tmp_path / "n.v"
    src.write_text(NETLIST)
    out = tmp_path / "p.v"
    man = npp.prep(src, out, kw.get("key_qrx", KEY), ["tck_i", "scan_clk_i"], kw.get("hold_mask", True),
                   kw.get("keep_unscanned", False), kw.get("full_scan", False))
    return man, out.read_text()


def test_classification_counts(tmp_path):
    man, _ = run(tmp_path)
    assert man["flops_scan_cells"] == 2 and man["flops_unscanned"] == 6
    assert man["tck_flops"] == 3 and man["scan_clk_flops"] == 1 and man["crypto_key_flops"] == 1
    assert man["other_unscanned_flops"] == 1 and man["other_unscanned_examples"] == ["_odd_"]
    assert man["hold_masked_flops"] == 1
    assert man["physical_cells_deleted"] == 3


def test_reset_flops_tied_to_reset_value_and_removed(tmp_path):
    _, txt = run(tmp_path)
    assert "_tapA_" not in txt and "_tapC_" not in txt and "_key_" not in txt
    assert re.search(r"assign tapA_q\s+= 1'b0;", txt)      # dfrtp: reset value 0
    assert re.search(r"assign tapC_q\s+= 1'b1;", txt)      # dfstp: set value 1
    assert re.search(r"assign \\u_crypto\.key_q\[3\]\s+= 1'b0;", txt)  # key masked in scan mode


def test_no_reset_unscanned_flop_becomes_free_input_with_unobserved_d(tmp_path):
    man, txt = run(tmp_path)
    assert man["free_init_x_flops"] == 2          # _tapB_ (negedge tck) and _sck_
    m = re.search(r"_tapB_ \((.*?)\);", txt, re.S)
    assert m and ".D(1'b0)" in m.group(1) and ".Q(tapB_q)" in m.group(1)


def test_hold_masked_flop_keeps_q_and_drops_d(tmp_path):
    _, txt = run(tmp_path)
    m = re.search(r"_s1_ \((.*?)\);", txt, re.S)
    assert m and ".D(1'b0)" in m.group(1) and "sync_q[0][0]" in m.group(1)
    assert ".D(d_i)" in re.search(r"_s2_ \((.*?)\);", txt, re.S).group(1)  # an ordinary scan flop is untouched


def test_physical_cells_are_deleted(tmp_path):
    _, txt = run(tmp_path)
    assert "FILLER_1" not in txt and "TAP_1" not in txt and "ANTENNA_1" not in txt


def test_keep_unscanned_leaves_them_as_ordinary_flops(tmp_path):
    man, txt = run(tmp_path, keep_unscanned=True)
    assert "_tapA_" in txt and "_key_" in txt
    assert man["unscanned_applied"] is False


def test_full_scan_mode_excludes_only_the_key(tmp_path):
    man, txt = run(tmp_path, full_scan=True)
    assert man["crypto_key_flops"] == 1 and man["tck_flops"] == 0 and man["other_unscanned_flops"] == 0
    assert "_tapA_" in txt


def test_cut_wrapper_ties_constants_and_passes_the_rest():
    ports = mk_cut.read_ports(NETLIST, "soc_top")
    w = mk_cut.wrapper("soc_top", ports, {"tck_i": 0})
    assert "module cut_top(scan_clk_i, clk_i, d_i, q_o);" in w
    assert "wire tck_i = 1'b0;" in w and "soc_top u_dut(" in w
    with pytest.raises(SystemExit):
        mk_cut.wrapper("soc_top", ports, {"nope": 1})


def test_bbox_stub_resolves_parameter_widths(tmp_path):
    hdr = tmp_path / "m.v"
    hdr.write_text("module sram(clk0, addr0, dout0);\n parameter ADDR_WIDTH = 10 ;\n parameter DATA_WIDTH = 32 ;\n"
                   " inout vccd1;\n input clk0;\n input [ADDR_WIDTH-1:0] addr0;\n output [DATA_WIDTH-1:0] dout0;\nendmodule\n")
    stub = mk_cut.bbox_stub(hdr, "sram")
    assert "(* blackbox *)" in stub and "input [9:0] addr0;" in stub and "output [31:0] dout0;" in stub
    assert "vccd1" not in stub


def test_dce_drops_logic_that_reaches_no_output_or_flop_d():
    blif = (".model m\n.inputs a b\n.outputs y\n.names a b y\n11 1\n.names a dead\n1 1\n"
            ".latch y q re clk 2\n.names q n\n0 1\n.end\n")
    out, kept, dropped = mk_cut.dce_blif(blif)
    assert dropped == 2 and kept == 1 and ".names a dead" not in out and ".latch y q re clk 2" in out
    assert json.dumps(out)  # parseable text
