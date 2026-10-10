"""Tests for tools/verif/check_cpu_netlist_census.py (bead gc0y deliverable 4)."""

# pylint: disable=missing-function-docstring
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "check_cpu_netlist_census", REPO_ROOT / "tools" / "verif" / "check_cpu_netlist_census.py"
)
assert _SPEC and _SPEC.loader
census = importlib.util.module_from_spec(_SPEC)
sys.modules["check_cpu_netlist_census"] = census
_SPEC.loader.exec_module(census)

_FF = "  sky130_fd_sc_hd__dfxtp_2 \\ff{i} (.CLK(clk), .D(d), .Q(q));\n"


def _netlist(with_fwd_b: bool, flops: int) -> str:
    s = "module rv32i_cpu_top (clk);\n  input clk;\n  wire \\u_core.fwd_a_sel_r[1] ;\n"
    if with_fwd_b:
        s += "  wire \\u_core.fwd_b_sel_r[1] ;\n  wire \\u_core.fwd_b_ex1c_r ;\n"
        s += "  wire \\u_core.fwd_b_ex1b2_r ;\n"
    s += "".join(_FF.format(i=i) for i in range(flops))
    return s + "endmodule\n"


def _run(tmp_path, text, *extra):
    p = tmp_path / "n.v"
    p.write_text(text)
    return census.main([str(p), *extra])


def test_good_netlist_passes(tmp_path):
    assert _run(tmp_path, _netlist(True, 4868)) == 0


def test_missing_fwd_b_nets_fire(tmp_path):
    assert _run(tmp_path, _netlist(False, 4863)) == 1


def test_flop_count_outside_band_fires(tmp_path):
    assert _run(tmp_path, _netlist(True, 4000)) == 1


def test_empty_or_non_verilog_input_is_not_a_pass(tmp_path):
    assert _run(tmp_path, "") == 2
    assert census.main([str(tmp_path / "missing.v")]) == 2
