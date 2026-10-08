"""Unit tests for the Sky130 SoC named max-cap waiver check (bead e45j).

The module under test (pnr/sky130/soc/plugin/cvt_maxcap_waiver.py) is pure Python with no LibreLane
dependency, so these tests run outside the nix-shell.  Fixtures are synthetic: a miniature
run directory with per-corner ``checks.rpt`` files in OpenSTA's
``report_check_types -violators`` layout and a miniature structural netlist in the layout
OpenROAD writes (escaped names, concatenated bus ports).
"""

import json
import sys
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parents[2] / "pnr" / "sky130" / "soc" / "plugin"
sys.path.insert(0, str(PLUGIN_DIR))

import cvt_maxcap_waiver as mw  # type: ignore[import-not-found]  # noqa: E402

CORNERS = ("nom_tt_025C_1v80", "max_ss_100C_1v60", "min_ff_n40C_1v95")

PIN_LIMIT = 0.5301
SS_LIMIT = 0.333262

NO_VIOLATION = """\
 report_check_types -max_slew -max_cap -max_fanout -violators
============================================================================
======================= {corner} Corner ===================================

max slew

Pin                                        Limit        Slew       Slack
------------------------------------------------------------------------
ANTENNA_3908/DIODE                      1.500000    1.600000   -0.100000 (VIOLATED)


===========================================================================
max slew violation count 1
max fanout violation count 0
max cap violation count 0
============================================================================
"""

WITH_VIOLATION = """\
 report_check_types -max_slew -max_cap -max_fanout -violators
============================================================================
======================= {corner} Corner ===================================

max slew

Pin                                        Limit        Slew       Slack
------------------------------------------------------------------------
ANTENNA_3908/DIODE                      1.500000    1.600000   -0.100000 (VIOLATED)

max capacitance

Pin                                        Limit         Cap       Slack
------------------------------------------------------------------------
{rows}


===========================================================================
max slew violation count 1
max fanout violation count 0
max cap violation count {count}
============================================================================
"""


def row(pin: str, limit: float, cap: float) -> str:
    return f"{pin:<38}{limit:>10.6f}{cap:>12.6f}{limit - cap:>12.6f} (VIOLATED)"


NETLIST = r"""
module soc_top (clk_i);
 input clk_i;
 wire \cpu_bridge_s_rdata[12] ;
 wire \cpu_bridge_s_rdata[3] ;
 wire net_other;
 sky130_fd_sc_hd__o22a_4 _078722_ (.A1(_022398_),
    .X(\cpu_bridge_s_rdata[12] ));
 sky130_fd_sc_hd__buf_8 _renamed_buf_ (.A(_x_),
    .X(\cpu_bridge_s_rdata[12] ));
 sky130_fd_sc_hd__nand2_1 _000001_ (.A(a), .B(b), .Y(net_other));
 sky130_fd_sc_hd__o22a_2 \u_fifo.mux[3]  (.A1(a),
    .X(\cpu_bridge_s_rdata[3] ));
 sky130_fd_sc_hd__diode_2 ANTENNA_3908 (.DIODE(\cpu_bridge_s_rdata[12] ));
 rv32i_cpu_top u_cpu (.apb_penable_i(dbg_penable),
    .axi_rdata_i({net2480,
    \cpu_bridge_s_rdata[3] ,
    net2481,
    \cpu_bridge_s_rdata[12] ,
    net2482,
    net2483}),
    .clk_i(clk_i));
 sky130_sram_4kbyte_1rw1r_32x1024_8 u_sram_macro (.din0({n_a,
    net_other,
    n_b}),
    .csb0(csb));
endmodule
"""
# axi_rdata_i is 6 wide here: entry k has bit index 5-k, so
#   net2480 -> [5], \cpu_bridge_s_rdata[3] -> [4], net2481 -> [3],
#   \cpu_bridge_s_rdata[12] -> [2], net2482 -> [1], net2483 -> [0].
# The waiver key therefore uses axi_rdata_i[2] in the synthetic netlist.

WAIVER_JSON = {
    "version": 1,
    "waivers": [
        {
            "id": "cpu-axi-rdata-pin-cap",
            "load_pin": {"instance": "u_cpu*", "pin": "axi_rdata_i[2]"},
            "max_cap_pf": 0.70,
            "bead": "e45j",
            "justification": (
                "Macro Liberty pin cap 0.2464 pF vs 0.0083 pF median; long wire; tracked in e45j."
            ),
        }
    ],
}


def write_run(
    root: Path,
    rows_by_corner: dict[str, list[str]],
    netlist: str = NETLIST,
    metrics: bool = True,
) -> Path:
    """Build a miniature run dir.

    rows_by_corner maps corner -> list of violation rows ([] = clean).
    """
    run = root / "RUN_synthetic"
    sta = run / "51-openroad-stapostpnr"
    counts = {}
    for corner, rows in rows_by_corner.items():
        d = sta / corner
        d.mkdir(parents=True)
        if rows:
            text = WITH_VIOLATION.format(corner=corner, rows="\n".join(rows), count=len(rows))
        else:
            text = NO_VIOLATION.format(corner=corner)
        (d / "checks.rpt").write_text(text)
        counts[f"design__max_cap_violation__count__corner:{corner}"] = len(rows)
    if metrics:
        (sta / "state_out.json").write_text(json.dumps({"metrics": counts}))
    fill = run / "48-openroad-fillinsertion"
    fill.mkdir(parents=True)
    (fill / "soc_top.nl.v").write_text(netlist)
    return run


def waiver_file(root: Path, data: dict | None = None) -> Path:
    p = root / "waivers.json"
    p.write_text(json.dumps(WAIVER_JSON if data is None else data))
    return p


def all_corners_violating(driver="_078722_/X"):
    return {
        "nom_tt_025C_1v80": [row(driver, PIN_LIMIT, 0.614297)],
        "max_ss_100C_1v60": [row(driver, SS_LIMIT, 0.642689)],
        "min_ff_n40C_1v95": [],
    }


# --------------------------------------------------------------------------- report parsing
class TestParseChecksReport:
    def test_clean_report_has_no_cap_violations_and_ignores_slew_rows(self):
        res = mw.parse_checks_report(NO_VIOLATION.format(corner="c"))
        assert res.declared_count == 0
        assert res.violations == ()

    def test_single_violation_fields(self):
        text = WITH_VIOLATION.format(
            corner="c", rows=row("_078722_/X", PIN_LIMIT, 0.614297), count=1
        )
        res = mw.parse_checks_report(text)
        assert res.declared_count == 1
        (v,) = res.violations
        assert v.pin == "_078722_/X"
        assert v.limit_pf == pytest.approx(PIN_LIMIT)
        assert v.cap_pf == pytest.approx(0.614297)
        assert v.slack_pf == pytest.approx(PIN_LIMIT - 0.614297)
        assert v.instance == "_078722_"
        assert v.port == "X"

    def test_slew_violations_are_never_counted_as_cap(self):
        res = mw.parse_checks_report(NO_VIOLATION.format(corner="c"))
        assert all("ANTENNA" not in v.pin for v in res.violations)

    def test_row_count_must_match_declared_count(self):
        text = WITH_VIOLATION.format(corner="c", rows=row("_a_/X", 1.0, 2.0), count=2)
        with pytest.raises(mw.ReportError, match="declares 2"):
            mw.parse_checks_report(text)

    def test_missing_summary_line_is_an_error_not_a_pass(self):
        truncated = NO_VIOLATION.format(corner="c").replace("max cap violation count 0", "")
        with pytest.raises(mw.ReportError, match="summary"):
            mw.parse_checks_report(truncated)

    def test_empty_report_is_an_error(self):
        with pytest.raises(mw.ReportError):
            mw.parse_checks_report("")

    def test_multiple_rows(self):
        rows = "\n".join([row("_a_/X", 0.5, 0.6), row("_b_/Y", 0.5, 0.7)])
        res = mw.parse_checks_report(WITH_VIOLATION.format(corner="c", rows=rows, count=2))
        assert [v.pin for v in res.violations] == ["_a_/X", "_b_/Y"]


# --------------------------------------------------------------------------- waiver file
class TestLoadWaivers:
    def test_valid(self, tmp_path):
        (w,) = mw.load_waivers(waiver_file(tmp_path))
        assert w.id == "cpu-axi-rdata-pin-cap"
        assert w.instance_glob == "u_cpu*"
        assert w.pin == "axi_rdata_i[2]"
        assert w.max_cap_pf == pytest.approx(0.70)

    def test_empty_list_is_valid_strict_mode(self, tmp_path):
        assert mw.load_waivers(waiver_file(tmp_path, {"version": 1, "waivers": []})) == ()

    @pytest.mark.parametrize(
        "mutation",
        [
            lambda w: w.pop("justification"),
            lambda w: w.update(justification="   "),
            lambda w: w.pop("id"),
            lambda w: w.update(max_cap_pf=0),
            lambda w: w.update(max_cap_pf="big"),
            lambda w: w.pop("load_pin"),
            lambda w: w["load_pin"].pop("pin"),
            lambda w: w["load_pin"].update(instance=""),
        ],
    )
    def test_invalid_waiver_rejected(self, tmp_path, mutation):
        data = json.loads(json.dumps(WAIVER_JSON))
        mutation(data["waivers"][0])
        with pytest.raises(mw.WaiverError):
            mw.load_waivers(waiver_file(tmp_path, data))

    def test_duplicate_ids_rejected(self, tmp_path):
        data = json.loads(json.dumps(WAIVER_JSON))
        data["waivers"].append(json.loads(json.dumps(data["waivers"][0])))
        with pytest.raises(mw.WaiverError, match="duplicate"):
            mw.load_waivers(waiver_file(tmp_path, data))

    def test_unknown_version_rejected(self, tmp_path):
        with pytest.raises(mw.WaiverError, match="version"):
            mw.load_waivers(waiver_file(tmp_path, {"version": 99, "waivers": []}))

    def test_missing_file_rejected(self, tmp_path):
        with pytest.raises(mw.WaiverError):
            mw.load_waivers(tmp_path / "nope.json")


# --------------------------------------------------------------------------- netlist
class TestNetlistIndex:
    def test_driver_net_found_for_plain_and_escaped_instance(self, tmp_path):
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, {"_078722_", "u_fifo.mux[3]"})
        assert idx.net_of("_078722_", "X") == "cpu_bridge_s_rdata[12]"
        assert idx.net_of("u_fifo.mux[3]", "X") == "cpu_bridge_s_rdata[3]"

    def test_unknown_driver_returns_none(self, tmp_path):
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, {"does_not_exist"})
        assert idx.net_of("does_not_exist", "X") is None

    def test_macro_concat_bit_indices(self, tmp_path):
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, set())
        loads = idx.macro_loads("cpu_bridge_s_rdata[12]")
        assert ("u_cpu", "axi_rdata_i[2]") in loads
        assert ("u_cpu", "axi_rdata_i[4]") not in loads
        assert ("u_cpu", "axi_rdata_i[4]") in idx.macro_loads("cpu_bridge_s_rdata[3]")

    def test_scalar_macro_port(self, tmp_path):
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, set())
        assert ("u_cpu", "clk_i") in idx.macro_loads("clk_i")
        assert ("u_sram_macro", "csb0") in idx.macro_loads("csb")

    def test_std_cells_are_not_macro_loads(self, tmp_path):
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, set())
        instances = {inst for inst, _ in idx.macro_loads("cpu_bridge_s_rdata[12]")}
        assert instances == {"u_cpu"}


# --------------------------------------------------------------------------- evaluate
class TestEvaluate:
    def test_waived_at_every_corner_passes(self, tmp_path):
        run = write_run(tmp_path, all_corners_violating())
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert v.ok
        assert v.unwaived == ()
        assert len(v.waived) == 2
        assert {w.waiver_id for w in v.waived} == {"cpu-axi-rdata-pin-cap"}
        assert v.stale_waivers == ()
        assert v.corners_checked == 3

    def test_negative_control_empty_waiver_list_fails(self, tmp_path):
        run = write_run(tmp_path, all_corners_violating())
        v = mw.evaluate_run(run, ())
        assert not v.ok
        assert len(v.unwaived) == 2

    def test_waiver_survives_driver_rename(self, tmp_path):
        """Keyed on the macro pin, not on the synthesis-generated driver name."""
        run = write_run(tmp_path, all_corners_violating(driver="_renamed_buf_/X"))
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert v.ok
        assert len(v.waived) == 2

    def test_violation_on_other_net_is_not_waived(self, tmp_path):
        rows = all_corners_violating()
        rows["nom_tt_025C_1v80"].append(row("_000001_/Y", PIN_LIMIT, 0.9))
        run = write_run(tmp_path, rows)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert not v.ok
        assert [u.violation.pin for u in v.unwaived] == ["_000001_/Y"]

    def test_unknown_driver_cannot_be_proven_and_fails(self, tmp_path):
        rows = {
            "nom_tt_025C_1v80": [row("_ghost_/X", PIN_LIMIT, 0.9)],
            "max_ss_100C_1v60": [],
            "min_ff_n40C_1v95": [],
        }
        run = write_run(tmp_path, rows)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert not v.ok
        assert "not found" in v.unwaived[0].reason

    def test_cap_above_waiver_ceiling_fails(self, tmp_path):
        rows = {
            "nom_tt_025C_1v80": [row("_078722_/X", PIN_LIMIT, 0.95)],
            "max_ss_100C_1v60": [],
            "min_ff_n40C_1v95": [],
        }
        run = write_run(tmp_path, rows)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert not v.ok
        assert "ceiling" in v.unwaived[0].reason

    def test_instance_glob_must_match_the_macro(self, tmp_path):
        data = json.loads(json.dumps(WAIVER_JSON))
        data["waivers"][0]["load_pin"]["instance"] = "u_sram*"
        run = write_run(tmp_path, all_corners_violating())
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, data)))
        assert not v.ok

    def test_pin_must_match_exactly(self, tmp_path):
        data = json.loads(json.dumps(WAIVER_JSON))
        data["waivers"][0]["load_pin"]["pin"] = "axi_rdata_i[3]"
        run = write_run(tmp_path, all_corners_violating())
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, data)))
        assert not v.ok

    def test_stale_waiver_warns_but_passes(self, tmp_path):
        clean = {c: [] for c in CORNERS}
        run = write_run(tmp_path, clean)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert v.ok
        assert [w.id for w in v.stale_waivers] == ["cpu-axi-rdata-pin-cap"]

    def test_stale_waiver_fails_in_strict_mode(self, tmp_path):
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)), strict_stale=True)
        assert not v.ok

    def test_clean_design_with_no_waivers_passes(self, tmp_path):
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        v = mw.evaluate_run(run, ())
        assert v.ok
        assert v.waived == ()

    def test_no_corner_reports_is_an_error(self, tmp_path):
        run = tmp_path / "RUN_empty"
        (run / "51-openroad-stapostpnr").mkdir(parents=True)
        with pytest.raises(mw.ReportError, match="no per-corner"):
            mw.evaluate_run(run, ())

    def test_no_sta_dir_is_an_error(self, tmp_path):
        run = tmp_path / "RUN_nothing"
        run.mkdir()
        with pytest.raises(mw.ReportError, match="stapostpnr"):
            mw.evaluate_run(run, ())

    def test_metric_mismatch_is_an_error(self, tmp_path):
        run = write_run(tmp_path, all_corners_violating())
        sta = run / "51-openroad-stapostpnr"
        metrics = json.loads((sta / "state_out.json").read_text())
        metrics["metrics"]["design__max_cap_violation__count__corner:nom_tt_025C_1v80"] = 0
        (sta / "state_out.json").write_text(json.dumps(metrics))
        with pytest.raises(mw.ReportError, match="metric"):
            mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))

    def test_missing_corner_report_for_a_metric_corner_is_an_error(self, tmp_path):
        run = write_run(tmp_path, all_corners_violating())
        sta = run / "51-openroad-stapostpnr"
        metrics = json.loads((sta / "state_out.json").read_text())
        metrics["metrics"]["design__max_cap_violation__count__corner:nom_ff_n40C_1v95"] = 0
        (sta / "state_out.json").write_text(json.dumps(metrics))
        with pytest.raises(mw.ReportError, match="nom_ff_n40C_1v95"):
            mw.evaluate_run(run, ())

    def test_violations_but_no_netlist_fails_not_passes(self, tmp_path):
        run = write_run(tmp_path, all_corners_violating())
        (run / "48-openroad-fillinsertion" / "soc_top.nl.v").unlink()
        with pytest.raises(mw.ReportError, match="netlist"):
            mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))

    def test_no_violations_does_not_need_a_netlist(self, tmp_path):
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        (run / "48-openroad-fillinsertion" / "soc_top.nl.v").unlink()
        assert mw.evaluate_run(run, ()).ok

    def test_latest_netlist_step_is_preferred(self, tmp_path):
        run = write_run(tmp_path, all_corners_violating())
        stale = run / "42-openroad-detailedrouting"
        stale.mkdir()
        (stale / "soc_top.nl.v").write_text("module soc_top (); endmodule\n")
        assert mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path))).ok


# --------------------------------------------------------------------------- CLI
class TestCli:
    def test_exit_0_when_waived(self, tmp_path, capsys):
        run = write_run(tmp_path, all_corners_violating())
        rc = mw.main([str(run), "--waivers", str(waiver_file(tmp_path))])
        out = capsys.readouterr().out
        assert rc == 0
        assert "WAIVED" in out
        assert "cpu-axi-rdata-pin-cap" in out

    def test_exit_1_without_waivers(self, tmp_path, capsys):
        run = write_run(tmp_path, all_corners_violating())
        rc = mw.main([str(run)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "UNWAIVED" in out

    def test_exit_2_on_report_error(self, tmp_path, capsys):
        run = tmp_path / "RUN_nothing"
        run.mkdir()
        assert mw.main([str(run)]) == 2

    def test_exit_2_on_bad_waiver_file(self, tmp_path):
        run = write_run(tmp_path, all_corners_violating())
        assert mw.main([str(run), "--waivers", str(tmp_path / "missing.json")]) == 2

    def test_stale_is_warned_in_output(self, tmp_path, capsys):
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        rc = mw.main([str(run), "--waivers", str(waiver_file(tmp_path))])
        assert rc == 0
        assert "STALE" in capsys.readouterr().out

    def test_strict_stale_flag(self, tmp_path):
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        assert mw.main([str(run), "--waivers", str(waiver_file(tmp_path)), "--strict-stale"]) == 1

    def test_explicit_netlist_override(self, tmp_path):
        run = write_run(tmp_path, all_corners_violating())
        nl = tmp_path / "other.nl.v"
        nl.write_text(NETLIST)
        (run / "48-openroad-fillinsertion" / "soc_top.nl.v").unlink()
        rc = mw.main([str(run), "--waivers", str(waiver_file(tmp_path)), "--netlist", str(nl)])
        assert rc == 0
