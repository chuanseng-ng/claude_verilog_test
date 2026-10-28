"""Tests for tools/dft/atpg/derive_hold_mask.py (bead j41m.15, DFT Stage 3 ATPG spike).

The mask lists the scanned capture flops whose D pin is NOT observed in the ATPG cut because the scan-view
hold check fails on them (34 gray-pointer stage-0 D pins + 60 MBIST tck->destination rows, DFT_ARCHITECTURE
14.13).  It must be derived from STABLE synchroniser Q-net names, never from instance ids.

Two kinds of test:
* synthetic miniature netlists (always run);
* the real-data check against the run-10-26 exempt list (skipped when /nobackup is not mounted):
  94/94 and a negative control.
"""

import sys
from pathlib import Path

import pytest

ATPG_DIR = Path(__file__).resolve().parents[2] / "tools" / "dft" / "atpg"
sys.path.insert(0, str(ATPG_DIR))

import derive_hold_mask as dhm  # type: ignore[import-not-found]  # noqa: E402

EXEMPT = Path("/nobackup/claude_sim_build/j41m8_sta/new_nom_tt_exempt.d/exempt_pins.txt")
NET_1026 = Path("/nobackup/sky130_soc_runs/RUN_2026-10-26_09-59-03/49-openroad-fillinsertion/soc_top.nl.v")


def flop(inst: str, qnet: str, typ: str = "sdfrtp_1") -> str:
    return (
        f" sky130_fd_sc_hd__{typ} {inst} (.CLK(clk),\n    .D(d_{inst}),\n    .RESET_B(rst),\n"
        f"    .SCD(scd),\n    .SCE(sce),\n    .Q({qnet}));\n"
    )


def mini_netlist(extra: str = "") -> str:
    body = ""
    body += flop("_1_", r"\u_cpu_axi_cdc.u_aw_fifo.u_wr_ptr_to_rd.sync_q[0][0] ")
    body += flop("_2_", r"\u_cpu_axi_cdc.u_aw_fifo.u_wr_ptr_to_rd.sync_q[1][0] ")  # stage 1: NOT masked
    body += flop("_3_", r"\u_cpu_axi_cdc.u_r_fifo.u_rd_ptr_to_wr.sync_q[0][3] ")
    body += flop("_4_", r"\u_mbist.u_xing_core.u_fifo.u_wr_ptr_to_rd.sync_q[0][1] ")
    body += flop("_5_", r"\u_mbist.g_cpu.u_xing_cpu.ctl_w[1] ")
    body += flop("_6_", r"\u_mbist.core_cfg_w[7] ")
    body += flop("_7_", r"\mb_cpu_cfg[25] ")
    body += flop("_8_", r"\u_uart.baud_cnt_q[0] ")  # unrelated
    body += flop("_9_", r"\u_other.sync_q[0][0] ")  # looks like a sync but is not a listed crossing
    body += " sky130_fd_sc_hd__buf_1 _10_ (.A(a), .X(x));\n"
    return "module soc_top (a);\n input a;\n" + body + extra + "endmodule\n"


def test_match_rules_use_net_names_only():
    assert dhm.rule_for(r"u_cpu_axi_cdc.u_ar_fifo.u_wr_ptr_to_rd.sync_q[0][2]") == "cdc_gray_axi"
    assert dhm.rule_for(r"u_mbist.u_xing_core.u_fifo.u_wr_ptr_to_rd.sync_q[0][0]") == "mbist_ptr_sync"
    assert dhm.rule_for(r"u_mbist.g_cpu.u_xing_cpu.ctl_w[0]") == "mbist_ctl_hold"
    assert dhm.rule_for(r"u_mbist.core_cfg_w[25]") == "mbist_core_cfg"
    assert dhm.rule_for(r"mb_cpu_cfg[0]") == "mbist_cpu_cfg"
    # stage 1 of the same synchroniser is NOT masked: only stage 0 has the hold exposure
    assert dhm.rule_for(r"u_cpu_axi_cdc.u_aw_fifo.u_wr_ptr_to_rd.sync_q[1][0]") is None
    assert dhm.rule_for(r"u_other.sync_q[0][0]") is None


def test_derive_selects_exactly_the_named_flops(tmp_path):
    p = tmp_path / "n.v"
    p.write_text(mini_netlist())
    mask = dhm.derive(dhm.read_flops(p))
    assert sorted(m["inst"] for m in mask) == ["_1_", "_3_", "_4_", "_5_", "_6_", "_7_"]
    assert {m["rule"] for m in mask} == {
        "cdc_gray_axi", "mbist_ptr_sync", "mbist_ctl_hold", "mbist_core_cfg", "mbist_cpu_cfg"}


def test_instance_ids_are_irrelevant(tmp_path):
    a = tmp_path / "a.v"
    b = tmp_path / "b.v"
    a.write_text(mini_netlist())
    b.write_text(mini_netlist().replace("_1_", "_900001_").replace("_4_", "_a_b_").replace("_7_", "_zz_"))
    qa = sorted(m["qnet"] for m in dhm.derive(dhm.read_flops(a)))
    qb = sorted(m["qnet"] for m in dhm.derive(dhm.read_flops(b)))
    assert qa == qb and len(qa) == 6


def test_only_flops_are_masked(tmp_path):
    # a buffer whose output net carries a masked name is not a flop and must not be selected
    extra = " sky130_fd_sc_hd__buf_1 _11_ (.A(a), .X(\\mb_cpu_cfg[3] ));\n"
    p = tmp_path / "n.v"
    p.write_text(mini_netlist(extra))
    assert "_11_" not in {m["inst"] for m in dhm.derive(dhm.read_flops(p))}


def test_validate_reports_missing_and_extra(tmp_path):
    p = tmp_path / "n.v"
    p.write_text(mini_netlist())
    flops = dhm.read_flops(p)
    mask = dhm.derive(flops)
    good = tmp_path / "exempt.txt"
    good.write_text("\n".join(f"{m['inst']}/D" for m in mask) + "\n")
    rep = dhm.validate(mask, good)
    assert rep["ok"] and rep["matched"] == 6 and rep["expected"] == 6

    # negative control: one expected pin that the derivation does not produce, and one the derivation produces that is not expected
    bad = tmp_path / "exempt_bad.txt"
    bad.write_text("\n".join([f"{m['inst']}/D" for m in mask if m["inst"] != "_7_"] + ["_8_/D"]) + "\n")
    rep = dhm.validate(mask, bad)
    assert not rep["ok"]
    assert rep["missing"] == ["_8_"] and rep["extra"] == ["_7_"]


def test_dropping_a_rule_is_detected(tmp_path):
    p = tmp_path / "n.v"
    p.write_text(mini_netlist())
    full = dhm.derive(dhm.read_flops(p))
    exempt = tmp_path / "e.txt"
    exempt.write_text("\n".join(f"{m['inst']}/D" for m in full) + "\n")
    reduced = dhm.derive(dhm.read_flops(p), drop_rules={"mbist_cpu_cfg"})
    rep = dhm.validate(reduced, exempt)
    assert not rep["ok"] and rep["missing"] == ["_7_"]


def test_cli_exit_codes(tmp_path):
    p = tmp_path / "n.v"
    p.write_text(mini_netlist())
    exempt = tmp_path / "e.txt"
    exempt.write_text("\n".join(f"{m['inst']}/D" for m in dhm.derive(dhm.read_flops(p))) + "\n")
    out = tmp_path / "mask.json"
    assert dhm.main([str(p), "--validate", str(exempt), "--out", str(out)]) == 0
    assert out.exists()
    assert dhm.main([str(p), "--validate", str(exempt), "--drop-rule", "mbist_cpu_cfg"]) == 1


@pytest.mark.skipif(not (EXEMPT.exists() and NET_1026.exists()), reason="run-10-26 artifacts not mounted")
def test_real_run_1026_matches_94_of_94():
    flops = dhm.read_flops(NET_1026)
    mask = dhm.derive(flops)
    rep = dhm.validate(mask, EXEMPT)
    assert rep["expected"] == 94
    assert rep["ok"], rep
    assert rep["matched"] == 94 and not rep["missing"] and not rep["extra"]


@pytest.mark.skipif(not (EXEMPT.exists() and NET_1026.exists()), reason="run-10-26 artifacts not mounted")
def test_real_run_1026_negative_control():
    flops = dhm.read_flops(NET_1026)
    reduced = dhm.derive(flops, drop_rules={"mbist_cpu_cfg"})
    rep = dhm.validate(reduced, EXEMPT)
    assert not rep["ok"] and len(rep["missing"]) == 26
