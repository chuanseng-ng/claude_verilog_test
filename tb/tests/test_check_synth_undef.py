"""Tests for tools/verif/check_synth_undef.py (bead gc0y).

The scanner exists because a synthesis frontend (Synlig/UHDM) replaced two hazard-unit port
connections with ``5'x`` and logged only a Warning (bead dud4).  Every fixture under
``fixtures/synth_undef`` is a REAL excerpt of a yosys 0.46 log or of the pre-synthesis JSON
header, taken from the dud4 synthesis runs or from the wording probes (see the README there).
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "verif" / "check_synth_undef.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "synth_undef"
_SPEC = importlib.util.spec_from_file_location("check_synth_undef", SCRIPT)
assert _SPEC and _SPEC.loader
gate = importlib.util.module_from_spec(_SPEC)
sys.modules["check_synth_undef"] = gate
_SPEC.loader.exec_module(gate)


def _fail_ids(findings):
    return sorted({f.rule for f in findings if f.severity == "FAIL"})


# --------------------------------------------------------------------------- log scanner


def test_real_dud4_warning_lines_fail():
    findings = gate.scan_log(FIX / "synlig_cpu_undef.log")
    fails = [f for f in findings if f.rule == "undef-range-select"]
    assert [f.line for f in fails] and len(fails) == 2
    texts = " ".join(f.text for f in fails)
    assert "[639:608]" in texts and "[799:768]" in texts
    assert all("rv32i_core.sv" in f.text for f in fails)


def test_sv2v_clean_log_has_no_failures():
    assert _fail_ids(gate.scan_log(FIX / "sv2v_cpu_clean.log")) == []


def test_benign_synlig_warnings_are_not_failures_without_allowlist_for_undef_class():
    findings = gate.scan_log(FIX / "synlig_cpu_benign_only.log")
    assert "undef-range-select" not in _fail_ids(findings)


@pytest.mark.parametrize(
    "probe,rule",
    [
        ("probe_p02_const_bitsel_oob.log", "undef-range-select"),
        ("probe_p03_const_range_partial.log", "undef-range-select"),
        ("probe_p05_undriven_used.log", "no-driver"),
        ("probe_p06_multidrive.log", "multi-driver"),
        ("probe_p08_portwidth_trunc.log", "port-resize"),
    ],
)
def test_probe_wording_is_recognised(probe, rule):
    assert rule in _fail_ids(gate.scan_log(FIX / probe))


def test_tool_error_line_fails():
    findings = gate.scan_log(FIX / "probe_p16_latch_ctrl.log")
    assert "tool-error" in _fail_ids(findings)


def test_postincrement_is_flagged_and_classified_warn():
    findings = gate.scan_log(FIX / "synlig_cpu_benign_only.log")
    post = [f for f in findings if f.rule == "post-increment"]
    assert post and all(f.severity == "WARN" for f in post)


def test_value_used_postincrement_is_a_tool_error_not_a_pass():
    assert "tool-error" in _fail_ids(gate.scan_log(FIX / "probe_p13_postinc_used.log"))


def test_findings_carry_file_and_line():
    f = gate.scan_log(FIX / "synlig_cpu_undef.log")[0]
    assert f.path.name == "synlig_cpu_undef.log" and f.line > 0


# --------------------------------------------------------------------------- allowlist


def test_allowlist_requires_justification(tmp_path):
    al = tmp_path / "al.txt"
    al.write_text("implicit-decl | _unused_ |\n")
    with pytest.raises(gate.AllowlistError):
        gate.load_allowlist(al)


def test_allowlist_rejects_unknown_rule(tmp_path):
    al = tmp_path / "al.txt"
    al.write_text("no-such-rule | foo | because\n")
    with pytest.raises(gate.AllowlistError):
        gate.load_allowlist(al)


def test_allowlist_downgrades_matching_finding_and_reports_use(tmp_path):
    al = tmp_path / "al.txt"
    al.write_text("undef-range-select | rv32i_core.sv:436 | test only\n")
    entries = gate.load_allowlist(al)
    findings = gate.apply_allowlist(gate.scan_log(FIX / "synlig_cpu_undef.log"), entries)
    by_line = {f.text: f for f in findings if f.rule == "undef-range-select"}
    allowed = [f for f in by_line.values() if f.allowed]
    assert len(allowed) == 1 and "436" in allowed[0].text
    assert any(not f.allowed and f.severity == "FAIL" for f in by_line.values())


def test_stale_allowlist_entry_is_reported(tmp_path):
    al = tmp_path / "al.txt"
    al.write_text("no-driver | never_matches | stale on purpose\n")
    entries = gate.load_allowlist(al)
    gate.apply_allowlist(gate.scan_log(FIX / "sv2v_cpu_clean.log"), entries)
    assert [e.rule for e in gate.stale_entries(entries)] == ["no-driver"]


def test_repo_allowlist_parses_and_every_entry_is_justified():
    entries = gate.load_allowlist(REPO_ROOT / "tools" / "verif" / "synth_undef_allowlist.txt")
    assert entries and all(len(e.justification) >= 20 for e in entries)


# --------------------------------------------------------------------------- structural


def test_header_json_undef_instance_input_is_found():
    findings = gate.scan_header_json(FIX / "header_undef.h.json")
    hits = [f for f in findings if f.rule == "x-driven-instance-input"]
    assert {h.text.split()[0] for h in hits} >= {"u_hazard"}
    assert len(hits) == 2
    assert any("if_id_rs1_addr" in h.text for h in hits)
    assert all(h.severity == "FAIL" for h in hits)


def test_header_json_clean_has_no_findings():
    assert gate.scan_header_json(FIX / "header_clean.h.json") == []


def test_header_json_fully_undef_named_net_is_found(tmp_path):
    j = {
        "modules": {
            "top": {
                "ports": {},
                "cells": {},
                "netnames": {
                    "y": {"bits": ["x", "x"]},
                    "$tmp": {"bits": ["x"]},
                    "ok": {"bits": [2]},
                },
            }
        }
    }
    p = tmp_path / "h.json"
    p.write_text(json.dumps(j))
    hits = gate.scan_header_json(p)
    assert [h.rule for h in hits] == ["x-driven-net"]
    assert "y" in hits[0].text


def test_removed_module_without_paramod_copy_fails(tmp_path):
    j = {"modules": {"other": {"ports": {}, "cells": {}, "netnames": {}}}}
    p = tmp_path / "h.json"
    p.write_text(json.dumps(j))
    log = tmp_path / "l.log"
    log.write_text(
        " Yosys 0.46 (git sha1 x)\n1. Executing Verilog with UHDM frontend.\n"
        "Warning: Removing unelaborated module: \\rv32i_core from the design.\n"
    )
    f = gate.cross_check_removed_modules(gate.scan_log(log), p)
    assert [x.rule for x in f] == ["removed-module-missing"]


def test_removed_module_with_paramod_copy_is_accepted(tmp_path):
    j = {"modules": {"$paramod$abc\\rv32i_core": {"ports": {}, "cells": {}, "netnames": {}}}}
    p = tmp_path / "h.json"
    p.write_text(json.dumps(j))
    log = tmp_path / "l.log"
    log.write_text(
        " Yosys 0.46 (git sha1 x)\n1. Executing Verilog with UHDM frontend.\n"
        "Warning: Removing unelaborated module: \\rv32i_core from the design.\n"
    )
    assert gate.cross_check_removed_modules(gate.scan_log(log), p) == []


def test_removed_module_with_parameter_suffixed_paramod_copy_is_accepted(tmp_path):
    # Real naming from the dud4 header JSON: "$paramod\rv32i_pipeline_if\RESET_PC=32'0..."
    name = "$paramod\\rv32i_pipeline_if\\RESET_PC=32'00000000000000000000000000000000"
    p = tmp_path / "h.json"
    p.write_text(json.dumps({"modules": {name: {"ports": {}, "cells": {}, "netnames": {}}}}))
    log = tmp_path / "l.log"
    log.write_text(
        " Yosys 0.46 (sha1 x)\n1. Executing Verilog with UHDM frontend.\n"
        "Warning: Removing unelaborated module: \\rv32i_pipeline_if from the design.\n"
    )
    assert gate.cross_check_removed_modules(gate.scan_log(log), p) == []


# --------------------------------------------------------------------------- CLI / never vacuous


def _run(*args):
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def test_cli_exit_1_on_undef_and_names_file_and_message():
    r = _run(str(FIX / "synlig_cpu_undef.log"))
    assert r.returncode == 1
    assert "synlig_cpu_undef.log:" in r.stdout
    assert "out of bounds on signal" in r.stdout


def test_cli_exit_0_on_clean_log():
    r = _run(str(FIX / "sv2v_cpu_clean.log"))
    assert r.returncode == 0, r.stdout + r.stderr


def test_cli_exit_2_on_missing_log(tmp_path):
    assert _run(str(tmp_path / "nope.log")).returncode == 2


def test_cli_exit_2_on_empty_log(tmp_path):
    p = tmp_path / "e.log"
    p.write_text("")
    assert _run(str(p)).returncode == 2


def test_cli_exit_2_on_log_without_synthesis_banner(tmp_path):
    p = tmp_path / "x.log"
    p.write_text("hello world\nnothing yosys-like here\n")
    assert _run(str(p)).returncode == 2


def test_cli_exit_2_when_run_dir_has_no_synthesis_logs(tmp_path):
    assert _run("--run-dir", str(tmp_path)).returncode == 2


def test_cli_run_dir_finds_logs_and_header(tmp_path):
    step = tmp_path / "05-yosys-jsonheader"
    step.mkdir()
    (step / "yosys-jsonheader.log").write_text((FIX / "sv2v_cpu_clean.log").read_text())
    (step / "rv32i_cpu_top.h.json").write_text((FIX / "header_undef.h.json").read_text())
    r = _run("--run-dir", str(tmp_path))
    assert r.returncode == 1 and "x-driven-instance-input" in r.stdout


def test_cli_allowlist_makes_known_hit_pass(tmp_path):
    al = tmp_path / "al.txt"
    al.write_text("undef-range-select | rv32i_core.sv | allowlisted for this unit test only\n")
    r = _run("--allowlist", str(al), str(FIX / "synlig_cpu_undef.log"))
    assert r.returncode == 0, r.stdout


def test_cli_json_output_is_parseable():
    r = _run("--json", str(FIX / "synlig_cpu_undef.log"))
    data = json.loads(r.stdout)
    assert data["verdict"] == "FAIL" and data["fail_count"] == 2
