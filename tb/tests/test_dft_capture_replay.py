"""Capture-replay helpers: idle clocks, scan_in capture values, primary-output compare mask.

Doc: tm:ch:dft-architecture:1812-scan-replay
"""

import json
import sys
from pathlib import Path

import pytest

ATPG = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG))
import idle_clocks  # type: ignore[import-not-found]  # noqa: E402
import replay_vectors as rv  # type: ignore[import-not-found]  # noqa: E402

INPUTS = [
    {"kind": "pin", "name": "a"},
    {"kind": "clock", "name": "clk_i"},
    {"kind": "scan_in", "name": "scan_in_i[1]", "chain": 1},
    {"kind": "scan_in", "name": "scan_in_i[0]", "chain": 0},
    {"kind": "clock", "name": "scan_clk_i"},
]
OUTPUTS = [
    {"kind": "pin", "port": "scan_out_o", "bit": 0},
    {"kind": "pin", "port": "gpio_o", "bit": 0},
    {"kind": "bb", "port": "clk0"},
]


def test_clock_inputs_are_cleared_and_data_inputs_kept():
    plan = {"inputs": INPUTS}
    idx = idle_clocks.clock_indices(plan)
    assert idx == [1, 4]
    assert idle_clocks.clear_bits("11111", idx) == "10110"


def test_idle_clocks_changes_a_pattern_that_has_a_clock_high(tmp_path):
    # negative control: a pattern with both clocks at 1 must differ afterwards
    plan = tmp_path / "m.json"
    plan.write_text(json.dumps({"inputs": INPUTS}))
    pat = tmp_path / "p.test"
    pat.write_text("* h\n1: 11111\n2: 00000\n")
    out = tmp_path / "o.test"
    assert idle_clocks.main(["--map", str(plan), "--patterns", str(pat), "--out", str(out)]) == 0
    got = {n: b for n, b in (ln.split(": ") for ln in out.read_text().splitlines() if ln[0] != "*")}
    assert got == {"1": "10110", "2": "00000"}


def test_first_limits_the_patterns(tmp_path):
    plan = tmp_path / "m.json"
    plan.write_text(json.dumps({"inputs": INPUTS}))
    pat = tmp_path / "p.test"
    pat.write_text("1: 11111\n2: 11111\n3: 11111\n")
    out = tmp_path / "o.test"
    idle_clocks.main(
        ["--map", str(plan), "--patterns", str(pat), "--out", str(out), "--first", "2"]
    )
    assert len([ln for ln in out.read_text().splitlines() if ln[0] != "*"]) == 2


def test_scan_in_index_in_chain_order():
    assert rv.scan_in_index({"inputs": [INPUTS[0], INPUTS[3], INPUTS[2]]}) == 1
    assert rv.scan_in_index({"inputs": INPUTS[:2]}) == -1


def test_scan_in_index_refuses_a_gap():
    gap = [INPUTS[3], INPUTS[0], INPUTS[2]]
    with pytest.raises(SystemExit):
        rv.scan_in_index({"inputs": gap})


def test_po_mask_clears_only_the_named_port():
    words = rv.po_mask_words({"outputs": OUTPUTS}, {"scan_out_o"})
    assert words == [0b110]
    assert rv.po_mask_words({"outputs": OUTPUTS}, set()) == [0b111]
