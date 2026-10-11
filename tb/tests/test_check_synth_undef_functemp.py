"""Tests for the sv2v function-temporary exemption of tools/verif/check_synth_undef.py (bead j1b7).

yosys inlines every function call; the function's own argument/local/result wires
(``<func>$func$<file>:<line>$<n>.<name>``) get a constant-x ``update`` that nothing reads.  The
structural ``x-driven-net`` rule reported them all on the SoC (509 hits, bead j1b7).  The exemption
must be as narrow as that mechanism: a net is exempt only if the PRE-``proc`` RTLIL of the same
elaboration shows no reader of the wire.  Fixtures are real yosys 0.46 output
(``fixtures/synth_undef/functemp_*``: ``.v`` source, ``.pre.il`` = ``write_rtlil`` before ``proc``,
``.h.json`` = ``write_json`` after ``proc``, exactly the view the flow's JsonHeader step writes).
"""

# pylint: disable=missing-function-docstring,protected-access
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "verif" / "check_synth_undef.py"
FIX = Path(__file__).resolve().parent / "fixtures" / "synth_undef"
_SPEC = importlib.util.spec_from_file_location("check_synth_undef_ft", SCRIPT)
assert _SPEC and _SPEC.loader
gate = importlib.util.module_from_spec(_SPEC)
sys.modules["check_synth_undef_ft"] = gate
_SPEC.loader.exec_module(gate)


def _proof(name: str):
    return gate.load_func_temp_proof([FIX / f"{name}.pre.il"])


def _fails(findings):
    return [f for f in findings if f.severity == "FAIL"]


def _exempt(findings):
    return [f for f in findings if f.rule == "func-temp-dead-init"]


# --------------------------------------------------------------------------- proof parsing


def test_clean_functions_have_unread_dead_init_temps():
    proof = _proof("functemp_clean")
    funcs = {k[1] for k in proof}
    assert funcs == {"init_then_cond", "loop_acc", "pick", "sv2v_cast_4"}
    assert all(g.dead_init for g in proof.values()), {k: g.reads for k, g in proof.items()}


def test_unassigned_result_is_read_and_not_dead():
    proof = _proof("functemp_unassigned")
    by_func = {k[1]: g for k, g in proof.items() if k[3] == "$result"}
    assert by_func["fine"].dead_init
    assert not by_func["leaky"].dead_init
    assert by_func["leaky"].reads, "the read of the unassigned result must be recorded"


def test_proof_keys_do_not_depend_on_autoidx_or_directories():
    # The flow elaborates with absolute paths and a different autoidx than the proof run, so the key
    # must be (module base name, function, file basename:line, variable).
    keys = list(_proof("functemp_clean"))
    assert ("functemp_clean", "pick", "functemp_clean.v:42", "kk") in keys
    il = (
        "module \\m\n  wire width 4 \\f$func$/some/dir/x.v:7$99.t\n"
        "  process $p\n    sync always\n      update \\f$func$/some/dir/x.v:7$99.t 4'x\n  end\nend\n"
    )
    assert ("m", "f", "x.v:7", "t") in gate.parse_func_temps(il)


def test_module_name_is_base_name_of_paramod():
    il = (
        "module $paramod$deadbeef\\axi_lite_interconnect\n"
        "  wire \\decode$func$a.v:1$2.$result\n  process $p\n    sync always\n"
        "      update \\decode$func$a.v:1$2.$result 1'x\n  end\nend\n"
    )
    assert ("axi_lite_interconnect", "decode", "a.v:1", "$result") in gate.parse_func_temps(il)


def _il(body: str) -> str:
    return (
        "module \\m\n  wire width 4 \\f$func$a.v:1$2.t\n  wire width 4 \\y\n"
        "  process $p\n    sync always\n      update \\f$func$a.v:1$2.t 4'x\n  end\n" + body + "end\n"
    )


def _group(body: str):
    return gate.parse_func_temps(_il(body))[("m", "f", "a.v:1", "t")]


def test_read_in_cell_connection_is_a_read():
    g = _group("  cell $mux $m\n    connect \\A \\f$func$a.v:1$2.t\n    connect \\Y \\y\n  end\n")
    assert g.reads and not g.dead_init


def test_read_in_process_assign_rhs_and_switch_is_a_read():
    body = (
        "  process $q\n    assign \\y \\f$func$a.v:1$2.t\n"
        "    switch \\f$func$a.v:1$2.t [0]\n      case 1'1\n    end\n  end\n"
    )
    g = _group(body)
    assert len(g.reads) == 2


def test_read_in_module_connect_rhs_is_a_read():
    assert _group("  connect \\y \\f$func$a.v:1$2.t\n").reads


def test_another_driver_defeats_dead_init():
    g = _group("  connect \\f$func$a.v:1$2.t \\y\n")
    assert g.other_driver and not g.dead_init


def test_partial_x_update_is_not_dead_init():
    il = _il("").replace("update \\f$func$a.v:1$2.t 4'x", "update \\f$func$a.v:1$2.t [1:0] 2'x")
    g = gate.parse_func_temps(il)[("m", "f", "a.v:1", "t")]
    assert g.partial and not g.dead_init


def test_non_x_update_is_a_real_driver():
    il = _il("").replace("update \\f$func$a.v:1$2.t 4'x", "update \\f$func$a.v:1$2.t \\y")
    assert gate.parse_func_temps(il)[("m", "f", "a.v:1", "t")].other_driver


def test_wire_without_x_update_is_not_a_candidate():
    il = "module \\m\n  wire \\f$func$a.v:1$2.t\nend\n"
    assert not gate.parse_func_temps(il)[("m", "f", "a.v:1", "t")].dead_init


def test_similarly_named_proc_temporaries_are_not_reads():
    # `$0\f$func$...t$17` is a proc temporary whose name merely contains the wire name.
    g = _group("  process $q\n    assign $0\\f$func$a.v:1$2.t[3:0]$17 \\y\n  end\n")
    assert g.dead_init


def test_missing_rtlil_file_is_an_input_error(tmp_path):
    try:
        gate.load_func_temp_proof([tmp_path / "nope.il"])
    except gate.InputError:
        return
    raise AssertionError("expected InputError")


# --------------------------------------------------------------------------- exemption in the structural check


def test_without_proof_every_function_temp_still_fails():
    findings = gate.scan_header_json(FIX / "functemp_clean.h.json")
    assert len([f for f in findings if f.rule == "x-driven-net"]) == 13
    assert not _exempt(findings)


def test_with_proof_clean_functions_are_exempt_and_reported():
    findings = gate.scan_header_json(FIX / "functemp_clean.h.json", _proof("functemp_clean"))
    assert not _fails(findings)
    assert len(_exempt(findings)) == 13
    assert gate.summarise_exemptions(findings) == {
        "init_then_cond": 4,
        "loop_acc": 4,
        "pick": 3,
        "sv2v_cast_4": 2,
    }


def test_unassigned_result_is_still_a_failure_but_the_clean_function_is_exempt():
    findings = gate.scan_header_json(FIX / "functemp_unassigned.h.json", _proof("functemp_unassigned"))
    bad = [f for f in _fails(findings) if f.rule == "x-driven-net"]
    assert bad, "a function result left unassigned on a path must not be hidden"
    assert all("leaky" in f.text for f in bad)
    assert any("read" in f.text for f in bad)
    assert gate.summarise_exemptions(findings) == {"fine": 4}


def test_proof_from_another_design_exempts_nothing():
    findings = gate.scan_header_json(FIX / "functemp_unassigned.h.json", _proof("functemp_clean"))
    assert not _exempt(findings), "groups absent from the proof must fail closed"
    assert len(_fails(findings)) == 7


def test_group_size_mismatch_fails_closed(tmp_path):
    h = json.loads((FIX / "functemp_clean.h.json").read_text())
    mod = h["modules"]["functemp_clean"]
    extra = "pick$func$functemp_clean.v:42$77.kk"
    mod["netnames"][extra] = {"hide_name": 0, "bits": ["x", "x"], "attributes": {}}
    p = tmp_path / "h.json"
    p.write_text(json.dumps(h))
    findings = gate.scan_header_json(p, _proof("functemp_clean"))
    assert any(f.rule == "x-driven-net" and "pick" in f.text for f in _fails(findings))


def test_partially_x_function_temp_is_not_exempt(tmp_path):
    h = json.loads((FIX / "functemp_clean.h.json").read_text())
    nets = h["modules"]["functemp_clean"]["netnames"]
    name = "sv2v_cast_4$func$functemp_clean.v:43$9.inp"
    nets[name]["bits"] = ["x", "x", 2, 3]
    p = tmp_path / "h.json"
    p.write_text(json.dumps(h))
    findings = gate.scan_header_json(p, _proof("functemp_clean"))
    assert any(f.rule == "x-driven-net" and "sv2v_cast_4" in f.text for f in _fails(findings))


def test_name_alone_never_exempts_a_user_net(tmp_path):
    # A user net that merely looks like a function temporary, absent from the proof.
    h = {"modules": {"m": {"cells": {}, "ports": {}, "netnames": {
        "mine$func$a.v:1$2.t": {"bits": ["x"], "attributes": {}}}}}}
    p = tmp_path / "h.json"
    p.write_text(json.dumps(h))
    assert [f.rule for f in _fails(gate.scan_header_json(p, {}))] == ["x-driven-net"]


def test_other_rules_stay_active_with_a_proof():
    findings = gate.scan_header_json(FIX / "header_undef.h.json", _proof("functemp_clean"))
    assert "x-driven-instance-input" in {f.rule for f in _fails(findings)}


def test_instance_input_tied_to_x_is_never_exempt(tmp_path):
    h = json.loads((FIX / "functemp_clean.h.json").read_text())
    mod = h["modules"]["functemp_clean"]
    mod["cells"]["u_bad"] = {
        "type": "functemp_clean",
        "port_directions": {"a": "input"},
        "connections": {"a": ["x", "x", "x", "x"]},
    }
    p = tmp_path / "h.json"
    p.write_text(json.dumps(h))
    findings = gate.scan_header_json(p, _proof("functemp_clean"))
    assert [f.rule for f in _fails(findings)] == ["x-driven-instance-input"]


# --------------------------------------------------------------------------- evaluate() + CLI


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True, check=False
    )


def _log(tmp_path: Path) -> Path:
    p = tmp_path / "y.log"
    p.write_text("Yosys 0.46\n1. Executing Verilog-2005 frontend: x.v\n")
    return p


def test_cli_exempts_with_proof_and_prints_per_function_counts(tmp_path):
    r = _run(
        "--header-json", str(FIX / "functemp_clean.h.json"),
        "--pre-rtlil", str(FIX / "functemp_clean.pre.il"),
        str(_log(tmp_path)),
    )  # fmt: skip
    assert r.returncode == 0, r.stdout + r.stderr
    assert "func-temp-dead-init" in r.stdout
    for fn, n in (("init_then_cond", 4), ("loop_acc", 4), ("pick", 3), ("sv2v_cast_4", 2)):
        assert f"{fn}={n}" in r.stdout
    assert "13 net(s)" in r.stdout


def test_cli_without_pre_rtlil_still_fails(tmp_path):
    r = _run("--header-json", str(FIX / "functemp_clean.h.json"), str(_log(tmp_path)))
    assert r.returncode == 1
    assert "x-driven-net" in r.stdout


def test_cli_fails_on_unassigned_result_even_with_proof(tmp_path):
    r = _run(
        "--header-json", str(FIX / "functemp_unassigned.h.json"),
        "--pre-rtlil", str(FIX / "functemp_unassigned.pre.il"),
        str(_log(tmp_path)),
    )  # fmt: skip
    assert r.returncode == 1
    assert "leaky" in r.stdout and "fine=4" in r.stdout


def test_cli_json_lists_exemptions(tmp_path):
    r = _run(
        "--json", "--header-json", str(FIX / "functemp_clean.h.json"),
        "--pre-rtlil", str(FIX / "functemp_clean.pre.il"), str(_log(tmp_path)),
    )  # fmt: skip
    out = json.loads(r.stdout)
    assert out["verdict"] == "PASS"
    assert out["exempt_by_function"]["pick"] == 3
    assert out["exempt_total"] == 13


def test_cli_bad_pre_rtlil_is_exit_2(tmp_path):
    r = _run(
        "--header-json", str(FIX / "functemp_clean.h.json"),
        "--pre-rtlil", str(tmp_path / "missing.il"), str(_log(tmp_path)),
    )  # fmt: skip
    assert r.returncode == 2


def test_the_exemption_cannot_be_allowlisted_into_existence(tmp_path):
    # The allowlist applies to FAIL findings by rule+text; with no proof the nets stay FAIL even
    # when no allowlist entry exists, and the exemption is not a rule an allowlist can create.
    r = _run(
        "--no-allowlist", "--header-json", str(FIX / "functemp_unassigned.h.json"),
        str(_log(tmp_path)),
    )  # fmt: skip
    assert r.returncode == 1
