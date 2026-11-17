# ruff: noqa: E501
"""Tests for tools/dft/atpg/regrade_vl.py: Verilator + Yosys re-grade, independent of Quaigh.

Doc: cr:suite:test-dft-atpg-regrade-vl
"""

import shutil
import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))

import regrade_vl as rv  # type: ignore[import-not-found]  # noqa: E402

BLIF = """\
.model t
.inputs a b
.outputs y z q w
.names a w
0 1
.names a b y
11 1
.names a b z
10 1
01 1
.latch y q re clk 2
.end
"""


def test_multi_fault_blif_inserts_one_select_per_fault_and_skips_a_repeated_net():
    text, kept = rv.multi_fault_blif(rv.to_comb_blif(BLIF), [("y", 0), ("z", 1), ("y", 1)])
    assert kept == [0, 1]
    assert "fsel_0" in text and "fsel_1" in text and "fsel_2" not in text
    assert ".names y__g0 fsel_0 y" in text and ".names z__g1 fsel_1 z" in text


def test_comb_view_moves_latches_to_ports():
    c = rv.to_comb_blif(BLIF)
    assert ".latch" not in c and ".inputs a b q" in c and "y z q w y" in c.replace("\n", " ")


needs_env = pytest.mark.skipif(
    not (shutil.which("nix") and Path(rv.DEFAULT_YOSYS).exists()),
    reason="needs nix (verilator) and the pinned yosys",
)


@needs_env
def test_verilator_agrees_and_injected_mismatch_is_caught(tmp_path):
    blif = tmp_path / "t.blif"
    blif.write_text(BLIF)
    pats = tmp_path / "p.test"
    pats.write_text("1: 000\n2: 110\n")  # inputs a b q
    faults = [
        {"net": "y", "value": 0, "own_sim_detects": True},  # needs a=b=1: pattern 2
        {
            "net": "z",
            "value": 0,
            "own_sim_detects": False,
        },  # z is 0 on both patterns: undetected, but testable
        {"net": "w", "value": 1, "own_sim_detects": True},
    ]  # w = ~a is 0 at pattern 2
    work = tmp_path / "w"
    work.mkdir()
    rep = rv.run(blif, pats, faults, rv.DEFAULT_YOSYS, rv.DEFAULT_VL_SHELL, work)
    assert rep["ok"] and rep["disagreements"] == []
    assert rep["detected"] == 2 and rep["undetected"] == 1
    assert (
        rep["undetected_testable_hole"] == 1 and rep["undetected_proven_untestable_yosys_sat"] == 0
    )
    # injected mismatch: claim z sa0 is detected -> the comparison must fail
    faults[1]["own_sim_detects"] = True
    work2 = tmp_path / "w2"
    work2.mkdir()
    rep2 = rv.run(blif, pats, faults, rv.DEFAULT_YOSYS, rv.DEFAULT_VL_SHELL, work2)
    assert not rep2["ok"] and len(rep2["disagreements"]) == 1


# Yosys `miter -equiv` + `sat -prove` called y = a & q EQUIVALENT to y = 0 when q is listed in both .inputs and
# .outputs (a flop Q feeding the next flop's D after to_comb_blif).  Measured with Yosys 0.46; the same pair without the dual
# port fails as it should.  dealias_dual_ports gives the output its own net.
DUAL_GOOD = ".model g\n.inputs a q\n.outputs q y\n.names a q y\n11 1\n.end\n"
DUAL_FAULT = ".model f\n.inputs a q\n.outputs q y\n.names y\n.end\n"


def test_dealias_dual_ports_gives_each_dual_output_its_own_net():
    t = rv.dealias_dual_ports(DUAL_GOOD)
    assert ".outputs q__po y" in t
    assert ".names q q__po\n1 1\n.end" in t
    assert (
        rv.dealias_dual_ports(".model m\n.inputs a\n.outputs y\n.names a y\n1 1\n.end\n").count(
            "__po"
        )
        == 0
    )


@pytest.mark.skipif(not Path(rv.DEFAULT_YOSYS).exists(), reason="needs Yosys")
def test_sat_does_not_prove_a_detectable_fault_through_a_dual_port(tmp_path):
    good, bad = tmp_path / "good.blif", tmp_path / "bad.blif"
    good.write_text(DUAL_GOOD)
    bad.write_text(DUAL_FAULT)
    assert rv.yosys_sat_equiv(rv.DEFAULT_YOSYS, good, bad, tmp_path) is False  # a=q=1 detects it
    assert rv.yosys_sat_equiv(rv.DEFAULT_YOSYS, good, good, tmp_path) is True
