"""Unit tests for tools/verif/stuck_bits_waivers.py and the filters of stuck_bits_formal.py.

The waiver regexes are generated, so they are checked the way the coverage report applies them: a
generated pattern must match every direction of every bit it was built from and nothing else.
"""

from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

# pylint: disable=missing-function-docstring

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load(name: str) -> ModuleType:
    path = REPO_ROOT / "tools" / "verif" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(REPO_ROOT / "tools" / "verif"))
sbf = _load("stuck_bits_formal")
sbw = _load("stuck_bits_waivers")


def _points(sig: str, elems: list[tuple[int, ...]], bits: range) -> list[str]:
    names = []
    for elem in elems:
        for bit in bits:
            idx = "".join(f"[{e}]" for e in elem) + f"[{bit}]"
            names += [f"{sig}{idx}:0->1", f"{sig}{idx}:1->0"]
    return names


def test_ranges_collapses_runs():
    assert sbw.ranges([5, 3, 4, 9]) == "3-5, 9"
    assert sbw.ranges([7]) == "7"


def test_regex_matches_exactly_the_proven_bits():
    by_elem = {(0,): [4, 5, 6], (2,): [4, 5, 6], (3,): [0, 1]}
    pattern = re.compile(sbw.regex_for("regs_o", by_elem))
    proven = _points("regs_o", [(0,), (2,)], range(4, 7)) + _points("regs_o", [(3,)], range(0, 2))
    assert all(pattern.search(n) for n in proven)
    others = _points("regs_o", [(1,)], range(4, 7)) + _points("regs_o", [(0,)], range(0, 4))
    others += _points("regs_o", [(3,)], range(2, 4)) + _points("prdata", [()], range(4, 7))
    assert not any(pattern.search(n) for n in others)


def test_regex_for_a_plain_vector_and_for_a_non_product_set():
    pattern = re.compile(sbw.regex_for("prdata", {(): [16, 17, 31]}))
    assert pattern.search("prdata[16]:0->1") and pattern.search("prdata[31]:1->0")
    assert not pattern.search("prdata[18]:0->1")
    # elements (0, 1) x (0, 1) minus (1, 1): the set is not a product, so it must not over-match
    pattern = re.compile(sbw.regex_for("hw", {(0, 0): [1], (0, 1): [1], (1, 0): [1]}))
    assert pattern.search("hw[1][0][1]:0->1")
    assert not pattern.search("hw[1][1][1]:0->1")


def test_regex_has_no_field_separator():
    # the waiver file splits fields on ' | ': an alternation bar must never be space-padded
    assert " | " not in sbw.regex_for("regs_o", {(0,): [1, 2], (5,): [9]})


def test_candidates_need_both_directions_unhit_and_skip_waived_and_named_bits():
    def pt(name: str, count: int):
        return SimpleNamespace(module="m", kind="toggle", name=name, count=count)

    points = [
        pt("a[0]:0->1", 0),
        pt("a[0]:1->0", 0),  # never moved: candidate
        pt("a[1]:0->1", 3),
        pt("a[1]:1->0", 0),  # rose once: not stuck
        pt("cnt[2]:0->1", 0),
        pt("cnt[2]:1->0", 0),  # skipped by name
        pt("w[0]:0->1", 0),
        pt("w[0]:1->0", 0),  # already waived
    ]
    waiver = SimpleNamespace(matches=lambda module, kind, text: text.startswith("w["))
    got = sbf.candidate_bits(points, "m", [waiver], re.compile(r"^cnt"))
    assert got == ["a[0]"]


def test_wrapper_ties_inputs_and_hierarchical_refs():
    ports = [
        ("clk", "input", 1),
        ("rst_n", "input", 1),
        ("scan_mode_i", "input", 1),
        ("d", "input", 8),
    ]
    sbf.TIES["scan_mode_i"] = "0"
    try:
        text = sbf.wrapper_text("dut_mod", {}, ports, ["regs_o[2][5]", "x"])
    finally:
        sbf.TIES.clear()
    assert ".scan_mode_i(1'd0)" in text
    assert "dut.regs_o[2][5]" in text and "dut.x" in text
    assert "input logic [7:0] d_in" in text
