"""Tests for tools/verif/check_upf.py (bead h3lm): the UPF-vs-RTL structural gate.

The clean case runs the checker on the committed UPF + facts + pmu.sv.  Every other test is a
NEGATIVE CONTROL: a deliberately broken UPF (or facts file) must produce a finding with the
expected id, proving the check can fail.  The drift test regenerates the facts from the RTL with
pyslang and is skipped (not passed) when pyslang is not installed.
"""

# pylint: disable=missing-function-docstring

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "verif"))

import check_upf as chk  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error

UPF_TEXT = chk.DEFAULT_UPF.read_text(encoding="utf-8")
FACTS: dict[str, Any] = json.loads(chk.DEFAULT_FACTS.read_text(encoding="utf-8"))
PMU = chk.parse_pmu(chk.DEFAULT_PMU.read_text(encoding="utf-8"))
DFT_TEXT = chk.DEFAULT_DFT.read_text(encoding="utf-8")


def run(upf_text: str = UPF_TEXT, facts: dict[str, Any] | None = None) -> list[str]:
    """Return 'ID message' strings for every finding (syntax + semantic)."""
    up = chk.parse_upf(upf_text)
    chk.check(up, FACTS if facts is None else facts, PMU, DFT_TEXT, [])
    return [f"{f.fid} {f.msg}" for f in up.findings]


def mutate(old: str, new: str, count: int = 1) -> str:
    assert UPF_TEXT.count(old) >= 1, f"mutation anchor not in the UPF: {old!r}"
    return str(UPF_TEXT.replace(old, new, count))


def expect(findings: list[str], fid: str, needle: str) -> None:
    assert any(f.startswith(fid) and needle in f for f in findings), (fid, needle, findings)


# ----------------------------------------------------------------------------- the committed files


def test_committed_upf_is_clean() -> None:
    assert run() == []


def test_cli_passes_on_committed_files(capsys: pytest.CaptureFixture[str]) -> None:
    assert chk.main([]) == 0
    assert "PASS" in capsys.readouterr().out


def test_clamp_sets_are_the_rtl_sets() -> None:
    for arm in FACTS["arms"].values():
        els = {c["element"] for c in arm["clamps"]}
        assert len(els) == 14
        assert "u_gpu/m_axil_if_rready" in els  # added by h3lm; was the one missed handshake
        assert all(c["clamp"] == 0 and c["sense"] == "high" for c in arm["clamps"])


def test_pmu_modes_parse() -> None:
    assert PMU["modes"] == {"NORMAL": 0, "CPU_OFF": 1, "GPU_OFF": 2, "IDLE": 3}
    assert PMU["targets"]["CPU_OFF"] == {"cpu": 0, "gpu": 1}
    assert PMU["targets"]["IDLE"] == {"cpu": 0, "gpu": 0}


# ------------------------------------------------------------------- negative controls: the UPF


def test_nonexistent_isolation_net_fails() -> None:
    # The old UPF's actual defect: cpu_iso_en does not exist in soc_top.
    expect(run(mutate("pmu_cpu_iso_en_sync", "cpu_iso_en", -1)), "U08", "cpu_iso_en")


def test_clamp_missing_from_upf_fails() -> None:
    bad = mutate("        u_gpu/m_axil_if_rready \\\n", "")
    expect(run(bad), "U05", "soc_top clamps u_gpu/m_axil_if_rready")


def test_clamp_not_in_rtl_fails() -> None:
    bad = mutate(
        "        u_cpu/axi_arvalid_o \\\n",
        "        u_cpu/axi_arvalid_o \\\n        u_cpu/axi_awaddr_o \\\n",
    )
    expect(run(bad), "U05", "UPF isolates u_cpu/axi_awaddr_o but soc_top does not clamp it")


def test_wrong_clamp_value_fails() -> None:
    expect(run(mutate("-clamp_value 0", "-clamp_value 1", 1)), "U05", "clamp_value")


def test_wrong_sense_fails() -> None:
    expect(
        run(mutate("-isolation_sense high", "-isolation_sense low", 1)), "U05", "isolation_sense"
    )


def test_input_port_cannot_be_isolated() -> None:
    bad = mutate(
        "        u_cpu/axi_arvalid_o \\\n",
        "        u_cpu/axi_arvalid_o \\\n        u_cpu/clk_i \\\n",
    )
    expect(run(bad), "U05", "u_cpu/clk_i is an input")


def test_missing_instance_fails() -> None:
    expect(run(mutate("-elements {u_cpu}", "-elements {u_cpux}", 1)), "U02", "u_cpux")


def test_isolation_supply_must_be_always_on() -> None:
    expect(
        run(mutate("-isolation_supply_set SS_AON", "-isolation_supply_set SS_CPU", 1)),
        "U05",
        "always-on",
    )


def test_isolation_supply_must_be_a_supply_set_not_a_domain() -> None:
    expect(
        run(mutate("-isolation_supply_set SS_AON", "-isolation_supply_set PD_PERIPH", 1)),
        "U05",
        "not a supply set",
    )


def test_nonstandard_switch_options_fail() -> None:
    # Exactly the old file's syntax.
    bad = UPF_TEXT + (
        "create_power_switch PSW_CPU -domain PD_CPU -output_supply_port {vout VDD_CPU} "
        "-input_supply_port {vin VDD} -control_port {ctrl cpu_pg_ctrl} -on_value 0 -off_value 1\n"
    )
    expect(run(bad), "U01", "-on_value")


def test_switch_with_nonexistent_control_net_fails() -> None:
    bad = UPF_TEXT + (
        "create_power_switch PSW_CPU -domain PD_CPU -input_supply_port {vin VDD} "
        "-output_supply_port {vout VDD_CPU} -control_port {sleep_n cpu_pg_ctrl} "
        "-on_state {on vin {sleep_n}} -off_state {off {!sleep_n}}\n"
    )
    expect(run(bad), "U08", "cpu_pg_ctrl")


def test_retention_is_refused() -> None:
    expect(run(UPF_TEXT + "set_retention RET -domain PD_CPU\n"), "U01", "no retention state")


def test_wrong_upf_version_fails() -> None:
    expect(run(mutate("upf_version 3.0", "upf_version 2.1")), "U01", "upf_version")


def test_unknown_option_and_command_fail() -> None:
    expect(run(mutate("-location parent", "-locaton parent", -1)), "U01", "-locaton")
    expect(run(UPF_TEXT + "set_frobnicate PD_CPU\n"), "U01", "set_frobnicate")


def test_roster_must_list_every_top_level_instance() -> None:
    bad = mutate("# upf-check aon u_pmu ", "# upf-check-x aon u_pmu ")
    expect(run(bad), "U03", "u_pmu")


def test_roster_rejects_unknown_instance() -> None:
    expect(run(UPF_TEXT + "# upf-check aon u_ghost\n"), "U03", "u_ghost")


def test_instance_in_two_domains_fails() -> None:
    bad = mutate("-elements {u_sram}", "-elements {u_sram u_cpu}", 1)
    expect(run(bad), "U03", "u_cpu")


def test_unclassified_output_fails() -> None:
    bad = mutate(" u_cpu/axi_awlen_o", "", 1)
    expect(run(bad), "U05", "u_cpu/axi_awlen_o")


def test_supply_net_without_source_fails() -> None:
    bad = mutate("connect_supply_net VDD_GPU -ports {VDD_GPU}\n", "")
    expect(run(bad), "U04", "VDD_GPU")


def test_off_state_without_off_port_state_fails() -> None:
    bad = mutate(
        "add_port_state VDD_GPU -state {ON 0.7} -state {OFF off}",
        "add_port_state VDD_GPU -state {ON 0.7}",
    )
    expect(run(bad), "U04", "SS_GPU")


# ------------------------------------------------- negative controls: the power-state table


def test_state_encoding_mismatch_fails() -> None:
    bad = mutate("u_pmu/pmu_mode_req == 2'b01", "u_pmu/pmu_mode_req == 2'b10", 1)
    expect(run(bad), "U07", "CPU_OFF")


def test_state_rail_mismatch_fails() -> None:
    bad = mutate(
        "SS_CPU == OFF && SS_GPU == ON  && u_pmu/pmu_mode_req == 2'b01",
        "SS_CPU == ON && SS_GPU == ON  && u_pmu/pmu_mode_req == 2'b01",
    )
    expect(run(bad), "U07", "dom_target_on")


def test_unknown_state_name_fails() -> None:
    bad = mutate("-state {IDLE ", "-state {SLEEP ", 1)
    expect(run(bad), "U07", "SLEEP")
    expect(run(bad), "U07", "IDLE")


def test_scan_must_be_exclusive_with_functional_states() -> None:
    bad = mutate(
        "&& scan_mode_i == 1'b0}} \\\n    -state {CPU_OFF", "}} \\\n    -state {CPU_OFF", 1
    )
    expect(run(bad), "U07", "NORMAL")


def test_scan_state_claim_is_checked_against_rtl() -> None:
    facts = copy.deepcopy(FACTS)
    facts["arms"]["asap7"]["clock_gates"]["u_gpu_cg"]["test_en"] = "1'b0"
    expect(run(facts=facts), "U07", "u_gpu_cg")


# ---------------------------------------------------------- negative controls: the facts (RTL side)


def test_rtl_clamp_added_without_upf_fails() -> None:
    facts = copy.deepcopy(FACTS)
    facts["arms"]["sky130"]["clamps"].append(
        {"element": "u_gpu/s_axil_rvalid", "iso": "pmu_gpu_iso_en", "clamp": 0, "sense": "high"}
    )
    expect(run(facts=facts), "U05", "soc_top clamps u_gpu/s_axil_rvalid")


def test_rtl_clamp_removed_fails() -> None:
    facts = copy.deepcopy(FACTS)
    facts["arms"]["asap7"]["clamps"] = [
        c for c in facts["arms"]["asap7"]["clamps"] if c["element"] != "u_cpu/commit_valid_o"
    ]
    expect(run(facts=facts), "U05", "UPF isolates u_cpu/commit_valid_o")


def test_rtl_clamp_net_change_fails() -> None:
    facts = copy.deepcopy(FACTS)
    facts["arms"]["asap7"]["clamps"][0]["iso"] = "some_other_net"
    expect(run(facts=facts), "U05", "some_other_net")


def test_new_top_level_instance_forces_roster_update() -> None:
    facts = copy.deepcopy(FACTS)
    facts["arms"]["asap7"]["instances"]["u_new_sync"] = "cdc_sync"
    expect(run(facts=facts), "U03", "u_new_sync")


def test_unresolved_net_in_facts_fails() -> None:
    facts = copy.deepcopy(FACTS)
    facts["arms"]["asap7"]["nets"]["pmu_gpu_iso_en"] = None
    expect(run(facts=facts), "U05", "pmu_gpu_iso_en")


# ------------------------------------------------------------------------------------- the reader


def test_tokenizer_handles_comments_continuations_and_braces() -> None:
    cmds = chk.tokenize("# c\nfoo -a {x {y z}} \\\n  -b 1 ; bar\n")
    assert [c.name for c in cmds] == ["foo", "bar"]
    assert cmds[0].line == 2
    assert [w.text for w in cmds[0].words] == ["-a", "x {y z}", "-b", "1"]


def test_split_list_keeps_braced_groups() -> None:
    assert chk.split_list("a {b c} d") == ["a", "b c", "d"]


def test_unbalanced_brace_is_a_finding() -> None:
    up = chk.parse_upf("create_supply_set X -function {power VDD\n")
    assert up.findings and up.findings[0].fid == "U01"


# --------------------------------------------------------------------------------- drift (pyslang)


def test_facts_file_matches_fresh_elaboration() -> None:
    pytest.importorskip("pyslang")
    up = chk.parse_upf(UPF_TEXT)
    assert chk.dump_facts(chk.build_facts(up)) == chk.DEFAULT_FACTS.read_text(encoding="utf-8")
