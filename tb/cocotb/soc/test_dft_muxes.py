"""
test_dft_muxes.py -- bead claude_verilog_test-j41m.2 (DFT Stage 1a).

DUT: tb_dft_muxes -> dft_clk_mux, dft_rst_mux, dft_ctrl_ports
(rtl/soc/dft/). Each is combinational, so every check is exhaustive over the
input space (3 and 3 and 4 inputs).

  test_clk_mux_selects_exhaustively      clk_o = sel ? test_clk : func_clk
  test_rst_mux_selects_exhaustively      rst_n_o = scan_mode ? scan_rst_n : func_rst_n
  test_ctrl_ports_is_a_passthrough       the Stage 1a seam: outputs follow inputs,
                                         test_en == scan_mode
"""

import itertools

import cocotb
from cocotb.triggers import Timer


@cocotb.test()
async def test_clk_mux_selects_exhaustively(dut):
    for f, t, s in itertools.product((0, 1), repeat=3):
        dut.cm_func_clk.value = f
        dut.cm_test_clk.value = t
        dut.cm_sel.value = s
        await Timer(1, units="ns")
        assert int(dut.cm_clk_o.value) == (t if s else f), (f, t, s)


@cocotb.test()
async def test_rst_mux_selects_exhaustively(dut):
    for f, r, m in itertools.product((0, 1), repeat=3):
        dut.rm_func_rst_n.value = f
        dut.rm_scan_rst_n.value = r
        dut.rm_scan_mode.value = m
        await Timer(1, units="ns")
        assert int(dut.rm_rst_n_o.value) == (r if m else f), (f, r, m)


@cocotb.test()
async def test_ctrl_ports_is_a_passthrough(dut):
    for m, e, r, c in itertools.product((0, 1), repeat=4):
        dut.cp_scan_mode_i.value = m
        dut.cp_scan_en_i.value = e
        dut.cp_scan_rst_ni.value = r
        dut.cp_test_clk_i.value = c
        await Timer(1, units="ns")
        assert int(dut.cp_scan_mode_o.value) == m
        assert int(dut.cp_scan_en_o.value) == e
        assert int(dut.cp_scan_rst_no.value) == r
        assert int(dut.cp_test_clk_o.value) == c
        assert int(dut.cp_test_en_o.value) == m, "test_en must equal scan_mode in Stage 1a"
