# ruff: noqa: E501
"""Tests for tools/dft/atpg/atpg_coverage_report.py (bead j41m.15).

Facts about Quaigh 0.0.6 these tests rely on (read from its source, DFT_ARCHITECTURE 18.1):
* `unobservable=N` in the progress line counts faults whose SAT miter is UNSAT (proven untestable in the cut);
* the fault universe is the collapsed ("unique") list unless --with-redundant-faults;
* detected + unobservable may be smaller than the universe: the remainder is "unresolved" and stays undetected.
The fixture is the real Stage 0 `timer` run (known answer 4336/4692 = 92.41 %, unobservable=351).
"""

import json
import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))

import atpg_coverage_report as cr  # type: ignore[import-not-found]  # noqa: E402

FIX = Path(__file__).resolve().parent / "fixtures" / "dft_atpg"


def timer_log() -> str:
    return (FIX / "quaigh_timer.log").read_text()


def test_parse_real_timer_log_known_answer():
    p = cr.parse_log(timer_log())
    assert p["complete"]
    assert (p["inputs"], p["outputs"], p["gates"]) == (554, 976, 2925)
    assert p["faults_all"] == 14112 and p["faults_universe"] == 4692
    assert p["detected"] == 4336 and p["total"] == 4692
    assert p["untestable_proven"] == 351
    assert p["patterns_kept"] == 358


def test_coverage_arithmetic():
    c = cr.coverage(detected=4336, total=4692, untestable=351)
    assert c["unresolved"] == 4692 - 4336 - 351 == 5
    assert c["fault_coverage_pct"] == pytest.approx(92.41, abs=0.005)
    assert c["test_coverage_pct"] == pytest.approx(99.88, abs=0.005)  # 4336 / 4341
    # nothing proven untestable -> test coverage equals fault coverage
    c0 = cr.coverage(detected=90, total=100, untestable=0)
    assert c0["test_coverage_pct"] == c0["fault_coverage_pct"] == 90.0


def test_only_proven_untestable_is_subtracted():
    # unresolved faults (neither detected nor proven) must stay in the test-coverage denominator
    c = cr.coverage(detected=50, total=100, untestable=10)
    assert c["test_coverage_pct"] == pytest.approx(50 / 90 * 100)
    assert c["unresolved"] == 40


def test_incomplete_log_is_not_a_result():
    truncated = (
        "Analyzing network with 4 inputs, 2 outputs, 10 gates, 60 possible faults, 40 unique faults\n"
        "Generated 128 random patterns, detecting 20/40 faults (50.00% coverage)\n"
    )
    p = cr.parse_log(truncated)
    assert not p["complete"]
    rep = cr.build_report(
        truncated,
        metrics={"completed": False, "rc": 137, "killed_by_cap": True},
        exclusions=None,
        label="x",
    )
    assert rep["status"] == "INCOMPLETE"
    assert rep["test_coverage_pct"] is None and rep["fault_coverage_pct"] is None


def test_inconsistent_detected_counts_are_flagged():
    log = timer_log().replace(
        "Kept 358 patterns, detecting 4336/4692", "Kept 358 patterns, detecting 4300/4692"
    )
    p = cr.parse_log(log)
    assert p["inconsistent"]
    rep = cr.build_report(log, metrics={"completed": True, "rc": 0}, exclusions=None, label="x")
    assert rep["status"] == "INCONSISTENT"


def test_report_carries_exclusion_manifest_and_statement():
    excl = {
        "tck_flops": 664,
        "scan_clk_flops": 2,
        "crypto_key_flops": 256,
        "hold_masked_flops": 94,
        "blackboxes": ["u_cpu"],
    }
    metrics = json.loads((FIX / "quaigh_timer.metrics.json").read_text())
    rep = cr.build_report(timer_log(), metrics=metrics, exclusions=excl, label="timer")
    assert rep["status"] == "OK"
    assert rep["exclusions"] == excl
    s = rep["exclusion_statement"]
    # the user decision of 2026-10-26: this statement travels with every coverage number
    assert "664" in s and "256" in s and "94" in s and "JTAG" in s
    md = cr.render_markdown(rep)
    assert "92.41" in md and "99.88" in md and "664" in md


def test_cli_roundtrip(tmp_path):
    log = tmp_path / "run.log"
    log.write_text(timer_log())
    met = tmp_path / "metrics.json"
    met.write_text((FIX / "quaigh_timer.metrics.json").read_text())
    out = tmp_path / "report.json"
    assert cr.main([str(log), "--metrics", str(met), "--label", "timer", "--out", str(out)]) == 0
    rep = json.loads(out.read_text())
    assert rep["detected"] == 4336 and rep["label"] == "timer"
    # a run killed by the memory cap is reported and exits non-zero
    met.write_text(
        json.dumps({"completed": False, "rc": 137, "killed_by_cap": True, "oom_kill": 1})
    )
    assert cr.main([str(log), "--metrics", str(met), "--label", "timer", "--out", str(out)]) == 1
    assert json.loads(out.read_text())["status"] == "INCOMPLETE"
