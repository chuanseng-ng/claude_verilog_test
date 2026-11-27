# ruff: noqa: E501
"""Tests for tools/dft/atpg/pattern_map.py: Quaigh pattern bit -> scan chain position / pin mapping (pure logic, toy netlist).

Doc: tm:ch:dft-architecture
"""

import json
import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))

import pattern_map as pm  # type: ignore[import-not-found]  # noqa: E402
from netlist_lib import iter_cells  # type: ignore[import-not-found]  # noqa: E402

NETLIST = """\
module soc_top (clk_i, scan_in_i, scan_out_o, d_i, y_o);
  input clk_i;
  input [1:0] scan_in_i;
  output [1:0] scan_out_o;
  input d_i;
  output y_o;
 sky130_fd_sc_hd__sdfxtp_1 f0 (.CLK(clk_i), .D(d_i), .SCD(scan_in_i[0]), .SCE(se), .Q(q0));
 sky130_fd_sc_hd__dlygate4sd3_1 hb (.A(q0), .X(q0b));
 sky130_fd_sc_hd__sdfxtp_1 f1 (.CLK(clk_i), .D(d_i), .SCD(q0b), .SCE(se), .Q(q1));
 sky130_fd_sc_hd__sdfrtp_1 f2 (.CLK(clk_i), .D(d_i), .SCD(q1), .SCE(se), .RESET_B(rn), .Q(q2));
 sky130_fd_sc_hd__sdfxtp_1 g0 (.CLK(clk_i), .D(d_i), .SCD(scan_in_i[1]), .SCE(se), .Q(r0));
 sky130_fd_sc_hd__dfxtp_1 u0 (.CLK(clk_i), .D(d_i), .Q(free_q));
 rv32i_cpu_top u_cpu (.a_o(bbo), .b_i(y));
endmodule
"""

BLIF = """\
.model cut_top
.inputs clk_i d_i scan_in_i[0] scan_in_i[1] u_dut.u_cpu.a_o scan_mode_i
.outputs y_o u_dut.u_cpu.b_i
.latch dd0 u_dut.f0.cvtpin_Q re clk_i 2
.latch dd1 u_dut.f1.cvtpin_Q re clk_i 2
.latch dd2 $auto$async2sync.cc:228:execute$9 re clk_i 2
.latch dd3 u_dut.g0.cvtpin_Q re clk_i 2
.latch dd4 u_dut.u0.cvtpin_Q re clk_i 2
.names $false $auto$async2sync.cc:228:execute$9 u_dut.f2.cvtpin_RESET_B u_dut.f2.cvtpin_Q
1-0 1
-11 1
.names d_i y_o
1 1
.end
"""


def cells():
    return {c.inst: c for c in iter_cells(NETLIST)}


def test_parse_blif_keeps_port_order_latch_order_and_the_async_restore_gate():
    b = pm.parse_blif(BLIF.splitlines(True))
    assert b.inputs[:3] == ["clk_i", "d_i", "scan_in_i[0]"]
    assert [q for _, q in b.latches][:2] == ["u_dut.f0.cvtpin_Q", "u_dut.f1.cvtpin_Q"]
    assert b.qgates == {"$auto$async2sync.cc:228:execute$9": "f2"}
    assert pm.latch_instance("$auto$async2sync.cc:228:execute$9", b.qgates) == "f2"
    assert pm.latch_instance("u_dut.f0.cvtpin_Q", b.qgates) == "f0"
    assert pm.latch_instance("$auto$unknown", b.qgates) is None


def test_chain_walk_goes_through_the_hold_buffer_and_orders_from_scan_in():
    chains, problems = pm.walk_chains(cells(), 2)
    assert chains == [["f0", "f1", "f2"], ["g0"]]
    assert problems == []


def test_chain_walk_reports_a_flop_on_no_chain_and_a_fanout_of_two():
    c = cells()
    c["f1"].pins["SCD"] = "q0"  # f1 now bypasses the buffer: still fine
    c["g0"].pins["SCD"] = "q0"  # g0 and f1 both hang on q0: a tree, not a chain
    chains, problems = pm.walk_chains(c, 2)
    assert any("Q feeds 2 SCD" in p for p in problems)


def test_shift_streams_round_trip_through_a_model_of_the_shift_register():
    vals = [1, 0, 0, 1, 1]
    for max_len in (5, 8):
        flops = [0] * len(vals)
        for bit in pm.chain_load_stream(vals, max_len):  # one shift edge per bit; position 0 takes scan-in
            flops = [bit] + flops[:-1]
        assert flops == vals
        seen = []
        for _ in range(max_len):  # unload: read scan-out (last position) before each edge
            seen.append(flops[-1])
            flops = [0] + flops[:-1]
        assert seen == pm.chain_unload_stream(vals, max_len)


def test_unequal_chains_pad_in_front_and_do_not_disturb_the_longer_chain():
    short, long_ = [1, 1, 0], [0, 1, 0, 1, 1, 0]
    s = pm.chain_load_stream(short, len(long_))
    assert s[:3] == [0, 0, 0] and s[3:] == [0, 1, 1]
    assert pm.chain_load_stream(long_, 6) == list(reversed(long_))


def build(blif_text=BLIF, masked=(), clocks=("clk_i",), consts=None):
    b = pm.parse_blif(blif_text.splitlines(True), track_edges=True)
    return pm.build_map(b, cells(), NETLIST, top="soc_top", consts=consts or {"scan_mode_i": 1}, clocks=clocks, n_ports=2,
                        in_fmt="scan_in_i[%d]", out_fmt="scan_out_o[%d]", masked=set(masked))


def test_full_map_of_the_toy_cut():
    m = build(masked={"f1"})
    assert m["unmapped"] == []
    kinds = [x["kind"] for x in m["inputs"]]
    assert kinds == ["clock", "pin", "scan_in", "scan_in", "bb", "fixed"]
    lat = {x["q"]: x for x in m["latches"]}
    assert (lat["u_dut.f0.cvtpin_Q"]["chain"], lat["u_dut.f0.cvtpin_Q"]["pos"]) == (0, 0)
    assert lat["u_dut.f1.cvtpin_Q"]["pos"] == 1 and lat["u_dut.f1.cvtpin_Q"]["masked"] is True
    assert (lat["$auto$async2sync.cc:228:execute$9"]["inst"], lat["$auto$async2sync.cc:228:execute$9"]["pos"]) == ("f2", 2)
    assert lat["u_dut.g0.cvtpin_Q"]["chain"] == 1
    assert lat["u_dut.u0.cvtpin_Q"]["kind"] == "free"
    assert [x["kind"] for x in m["outputs"]] == ["pin", "bb"]
    assert m["summary"]["scan_flops_on_chains_not_in_cut"] == 0


def test_unmapped_bits_are_refused_not_guessed():
    bad = BLIF.replace("u_dut.u_cpu.a_o", "u_dut.u_gpu.a_o").replace(".latch dd3 u_dut.g0.cvtpin_Q", ".latch dd3 $auto$x")
    m = build(bad)
    whys = {(u["list"], u["name"] if "name" in u else u["q"]) for u in m["unmapped"]}
    assert ("inputs", "u_dut.u_gpu.a_o") in whys and ("latches", "$auto$x") in whys
    m2 = build(BLIF.replace(" d_i ", " not_a_port_i "))
    assert any(u["list"] == "inputs" and "top-level" in u["why"] for u in m2["unmapped"])


def test_a_clock_that_reaches_a_data_endpoint_is_refused_but_a_clock_sink_is_not():
    data = BLIF.replace(".names d_i y_o\n1 1", ".names clk_i y_o\n1 1")
    m = build(data)
    assert any(u["name"] == "clk_i" and "observable" in u["why"] for u in m["unmapped"])
    sink = BLIF.replace(".outputs y_o u_dut.u_cpu.b_i", ".outputs y_o u_dut.u_cpu.clk0").replace(".names d_i y_o", ".names clk_i u_dut.u_cpu.clk0")
    m = build(sink)
    assert [x["kind"] for x in m["inputs"]][0] == "clock"


def test_negative_control_a_swapped_chain_order_changes_the_position():
    m = build()
    pos = {x["inst"]: x["pos"] for x in m["latches"] if x["kind"] == "scan"}
    c = cells()
    c["f0"].pins["SCD"], c["g0"].pins["SCD"] = "scan_in_i[1]", "scan_in_i[0]"
    chains, _ = pm.walk_chains(c, 2)
    assert chains[0] == ["g0"] and chains[1][0] == "f0"
    assert pos["f0"] == 0 and json.dumps(chains) != json.dumps(m["chains"])


def test_top_ports_reads_names_and_directions():
    ins, outs = pm.top_ports(NETLIST, "soc_top")
    assert {"clk_i", "scan_in_i", "d_i"} <= ins and {"scan_out_o", "y_o"} <= outs
    with pytest.raises(SystemExit):
        pm.top_ports(NETLIST, "nope")
