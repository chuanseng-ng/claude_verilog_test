"""Tests for tools/dft/atpg/regrade.py (bead j41m.15): the independent bit-parallel fault re-grader."""

import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))

import regrade as rg  # type: ignore[import-not-found]  # noqa: E402

QUAIGH = Path("/nobackup/claude_sim_build/j41m15/bin/quaigh")

# y = a & b ; z = a ^ b ; w = ~y (redundant observation path: w only feeds output o3)
BLIF = """\
.model t
.inputs a b
.outputs y z w
.names a b y
11 1
.names a b z
10 1
01 1
.names y w
0 1
.end
"""


def test_good_simulation_truth_table():
    s = rg.Sim(BLIF)
    s.load(["00", "01", "10", "11"])  # bit k of each net = pattern k
    assert s.good["y"] == 0b1000 and s.good["z"] == 0b0110 and s.good["w"] == 0b0111


def test_detect_known_faults():
    s = rg.Sim(BLIF)
    s.load(["00", "01", "10", "11"])
    assert s.detect("y", 0) == 3          # y sa0 needs a=b=1: pattern index 3
    assert s.detect("y", 1) == 0          # y sa1 visible at pattern 0
    assert s.detect("z", 1) == 0
    s.load(["11"])
    assert s.detect("z", 1) == 0          # z is 0 at 11, stuck-at-1 flips it
    assert s.detect("z", 0) is None       # stuck-at-0 equals the good value: not detected by this set
    s.load(["00", "11"])
    assert s.detect("a", 1) == 0          # a sa1 at 00 changes y? y=0 either way, z flips: detected on z


def test_fault_blif_replaces_the_driver():
    f = rg.fault_blif(BLIF, "y", 1)
    s = rg.Sim(f)
    s.load(["00"])
    assert s.good["y"] == 1 and s.good["w"] == 0
    with pytest.raises(ValueError):
        rg.fault_blif(BLIF, "a", 1)


def test_all_zero_pattern_control():
    s = rg.Sim(BLIF)
    s.load(["00"])
    # an all-zero input vector cannot detect y sa0 (y is already 0) : the control relies on this
    assert s.detect("y", 0) is None


@pytest.mark.skipif(not QUAIGH.exists(), reason="quaigh binary not available")
def test_regrade_agrees_with_quaigh_simulate(tmp_path):
    blif = tmp_path / "t.blif"
    blif.write_text(BLIF)
    pats = tmp_path / "t.test"
    pats.write_text("1: 01\n2: 10\n3: 11\n")
    rep = rg.regrade(blif, pats, str(QUAIGH), samples=20, n_undet=5, seed=1, tmp=tmp_path)
    assert rep["mismatches"] == []
    assert rep["ok"]
    assert rep["sampled_detected"] > 0


@pytest.mark.skipif(not QUAIGH.exists(), reason="quaigh binary not available")
def test_injected_mismatch_is_caught(tmp_path, monkeypatch):
    blif = tmp_path / "t.blif"
    blif.write_text(BLIF)
    pats = tmp_path / "t.test"
    pats.write_text("1: 00\n")
    real = rg.Sim.detect
    # corrupt our own simulator: claim every fault is undetected
    monkeypatch.setattr(rg.Sim, "detect", lambda self, net, v: None)
    rep = rg.regrade(blif, pats, str(QUAIGH), samples=5, n_undet=5, seed=1, tmp=tmp_path)
    monkeypatch.setattr(rg.Sim, "detect", real)
    # with a wrong "mine" there are no detected samples to compare, so use the opposite corruption too
    monkeypatch.setattr(rg.Sim, "detect", lambda self, net, v: 0)
    rep2 = rg.regrade(blif, pats, str(QUAIGH), samples=5, n_undet=5, seed=1, tmp=tmp_path)
    assert rep2["mismatches"], "a simulator that claims detection everywhere must disagree with quaigh on some fault"
    assert not rep2["ok"]
    assert rep is not None
