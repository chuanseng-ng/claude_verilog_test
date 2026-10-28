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
    """Row."""
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
    """Waiver file."""
    p = root / "waivers.json"
    p.write_text(json.dumps(WAIVER_JSON if data is None else data))
    return p


def all_corners_violating(driver="_078722_/X"):
    """All corners violating."""
    return {
        "nom_tt_025C_1v80": [row(driver, PIN_LIMIT, 0.614297)],
        "max_ss_100C_1v60": [row(driver, SS_LIMIT, 0.642689)],
        "min_ff_n40C_1v95": [],
    }


# --------------------------------------------------------------------------- report parsing
class TestParseChecksReport:
    def test_clean_report_has_no_cap_violations_and_ignores_slew_rows(self):
        """Clean report has no cap violations and ignores slew rows."""
        res = mw.parse_checks_report(NO_VIOLATION.format(corner="c"))
        assert res.declared_count == 0
        assert res.violations == ()

    def test_single_violation_fields(self):
        """Single violation fields."""
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
        """Slew violations are never counted as cap."""
        res = mw.parse_checks_report(NO_VIOLATION.format(corner="c"))
        assert all("ANTENNA" not in v.pin for v in res.violations)

    def test_row_count_must_match_declared_count(self):
        """Row count must match declared count."""
        text = WITH_VIOLATION.format(corner="c", rows=row("_a_/X", 1.0, 2.0), count=2)
        with pytest.raises(mw.ReportError, match="declares 2"):
            mw.parse_checks_report(text)

    def test_missing_summary_line_is_an_error_not_a_pass(self):
        """Missing summary line is an error not a pass."""
        truncated = NO_VIOLATION.format(corner="c").replace("max cap violation count 0", "")
        with pytest.raises(mw.ReportError, match="summary"):
            mw.parse_checks_report(truncated)

    def test_empty_report_is_an_error(self):
        """Empty report is an error."""
        with pytest.raises(mw.ReportError):
            mw.parse_checks_report("")

    def test_multiple_rows(self):
        """Multiple rows."""
        rows = "\n".join([row("_a_/X", 0.5, 0.6), row("_b_/Y", 0.5, 0.7)])
        res = mw.parse_checks_report(WITH_VIOLATION.format(corner="c", rows=rows, count=2))
        assert [v.pin for v in res.violations] == ["_a_/X", "_b_/Y"]


# --------------------------------------------------------------------------- waiver file
class TestLoadWaivers:
    def test_valid(self, tmp_path):
        """Valid."""
        (w,) = mw.load_waivers(waiver_file(tmp_path))
        assert w.id == "cpu-axi-rdata-pin-cap"
        assert w.instance_glob == "u_cpu*"
        assert w.pin == "axi_rdata_i[2]"
        assert w.max_cap_pf == pytest.approx(0.70)

    def test_empty_list_is_valid_strict_mode(self, tmp_path):
        """Empty list is valid strict mode."""
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
        """Invalid waiver rejected."""
        data = json.loads(json.dumps(WAIVER_JSON))
        mutation(data["waivers"][0])
        with pytest.raises(mw.WaiverError):
            mw.load_waivers(waiver_file(tmp_path, data))

    def test_duplicate_ids_rejected(self, tmp_path):
        """Duplicate ids rejected."""
        data = json.loads(json.dumps(WAIVER_JSON))
        data["waivers"].append(json.loads(json.dumps(data["waivers"][0])))
        with pytest.raises(mw.WaiverError, match="duplicate"):
            mw.load_waivers(waiver_file(tmp_path, data))

    def test_unknown_version_rejected(self, tmp_path):
        """Unknown version rejected."""
        with pytest.raises(mw.WaiverError, match="version"):
            mw.load_waivers(waiver_file(tmp_path, {"version": 99, "waivers": []}))

    def test_missing_file_rejected(self, tmp_path):
        """Missing file rejected."""
        with pytest.raises(mw.WaiverError):
            mw.load_waivers(tmp_path / "nope.json")


# --------------------------------------------------------------------------- netlist
class TestNetlistIndex:
    def test_driver_net_found_for_plain_and_escaped_instance(self, tmp_path):
        """Driver net found for plain and escaped instance."""
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, {"_078722_", "u_fifo.mux[3]"})
        assert idx.net_of("_078722_", "X") == "cpu_bridge_s_rdata[12]"
        assert idx.net_of("u_fifo.mux[3]", "X") == "cpu_bridge_s_rdata[3]"

    def test_unknown_driver_returns_none(self, tmp_path):
        """Unknown driver returns none."""
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, {"does_not_exist"})
        assert idx.net_of("does_not_exist", "X") is None

    def test_macro_concat_bit_indices(self, tmp_path):
        """Macro concat bit indices."""
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, set())
        loads = idx.macro_loads("cpu_bridge_s_rdata[12]")
        assert ("u_cpu", "axi_rdata_i[2]") in loads
        assert ("u_cpu", "axi_rdata_i[4]") not in loads
        assert ("u_cpu", "axi_rdata_i[4]") in idx.macro_loads("cpu_bridge_s_rdata[3]")

    def test_scalar_macro_port(self, tmp_path):
        """Scalar macro port."""
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, set())
        assert ("u_cpu", "clk_i") in idx.macro_loads("clk_i")
        assert ("u_sram_macro", "csb0") in idx.macro_loads("csb")

    def test_std_cells_are_not_macro_loads(self, tmp_path):
        """Std cells are not macro loads."""
        nl = tmp_path / "n.v"
        nl.write_text(NETLIST)
        idx = mw.scan_netlist(nl, set())
        instances = {inst for inst, _ in idx.macro_loads("cpu_bridge_s_rdata[12]")}
        assert instances == {"u_cpu"}


# --------------------------------------------------------------------------- evaluate
class TestEvaluate:
    def test_waived_at_every_corner_passes(self, tmp_path):
        """Waived at every corner passes."""
        run = write_run(tmp_path, all_corners_violating())
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert v.ok
        assert v.unwaived == ()
        assert len(v.waived) == 2
        assert {w.waiver_id for w in v.waived} == {"cpu-axi-rdata-pin-cap"}
        assert v.stale_waivers == ()
        assert v.corners_checked == 3

    def test_negative_control_empty_waiver_list_fails(self, tmp_path):
        """Negative control empty waiver list fails."""
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
        """Violation on other net is not waived."""
        rows = all_corners_violating()
        rows["nom_tt_025C_1v80"].append(row("_000001_/Y", PIN_LIMIT, 0.9))
        run = write_run(tmp_path, rows)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert not v.ok
        assert [u.violation.pin for u in v.unwaived] == ["_000001_/Y"]

    def test_unknown_driver_cannot_be_proven_and_fails(self, tmp_path):
        """Unknown driver cannot be proven and fails."""
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
        """Cap above waiver ceiling fails."""
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
        """Instance glob must match the macro."""
        data = json.loads(json.dumps(WAIVER_JSON))
        data["waivers"][0]["load_pin"]["instance"] = "u_sram*"
        run = write_run(tmp_path, all_corners_violating())
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, data)))
        assert not v.ok

    def test_pin_must_match_exactly(self, tmp_path):
        """Pin must match exactly."""
        data = json.loads(json.dumps(WAIVER_JSON))
        data["waivers"][0]["load_pin"]["pin"] = "axi_rdata_i[3]"
        run = write_run(tmp_path, all_corners_violating())
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, data)))
        assert not v.ok

    def test_stale_waiver_warns_but_passes(self, tmp_path):
        """Stale waiver warns but passes."""
        clean = {c: [] for c in CORNERS}
        run = write_run(tmp_path, clean)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))
        assert v.ok
        assert [w.id for w in v.stale_waivers] == ["cpu-axi-rdata-pin-cap"]

    def test_stale_waiver_fails_in_strict_mode(self, tmp_path):
        """Stale waiver fails in strict mode."""
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)), strict_stale=True)
        assert not v.ok

    def test_clean_design_with_no_waivers_passes(self, tmp_path):
        """Clean design with no waivers passes."""
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        v = mw.evaluate_run(run, ())
        assert v.ok
        assert v.waived == ()

    def test_no_corner_reports_is_an_error(self, tmp_path):
        """No corner reports is an error."""
        run = tmp_path / "RUN_empty"
        (run / "51-openroad-stapostpnr").mkdir(parents=True)
        with pytest.raises(mw.ReportError, match="no per-corner"):
            mw.evaluate_run(run, ())

    def test_no_sta_dir_is_an_error(self, tmp_path):
        """No sta dir is an error."""
        run = tmp_path / "RUN_nothing"
        run.mkdir()
        with pytest.raises(mw.ReportError, match="stapostpnr"):
            mw.evaluate_run(run, ())

    def test_metric_mismatch_is_an_error(self, tmp_path):
        """Metric mismatch is an error."""
        run = write_run(tmp_path, all_corners_violating())
        sta = run / "51-openroad-stapostpnr"
        metrics = json.loads((sta / "state_out.json").read_text())
        metrics["metrics"]["design__max_cap_violation__count__corner:nom_tt_025C_1v80"] = 0
        (sta / "state_out.json").write_text(json.dumps(metrics))
        with pytest.raises(mw.ReportError, match="metric"):
            mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))

    def test_missing_corner_report_for_a_metric_corner_is_an_error(self, tmp_path):
        """Missing corner report for a metric corner is an error."""
        run = write_run(tmp_path, all_corners_violating())
        sta = run / "51-openroad-stapostpnr"
        metrics = json.loads((sta / "state_out.json").read_text())
        metrics["metrics"]["design__max_cap_violation__count__corner:nom_ff_n40C_1v95"] = 0
        (sta / "state_out.json").write_text(json.dumps(metrics))
        with pytest.raises(mw.ReportError, match="nom_ff_n40C_1v95"):
            mw.evaluate_run(run, ())

    def test_violations_but_no_netlist_fails_not_passes(self, tmp_path):
        """Violations but no netlist fails not passes."""
        run = write_run(tmp_path, all_corners_violating())
        (run / "48-openroad-fillinsertion" / "soc_top.nl.v").unlink()
        with pytest.raises(mw.ReportError, match="netlist"):
            mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path)))

    def test_no_violations_does_not_need_a_netlist(self, tmp_path):
        """No violations does not need a netlist."""
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        (run / "48-openroad-fillinsertion" / "soc_top.nl.v").unlink()
        assert mw.evaluate_run(run, ()).ok

    def test_latest_netlist_step_is_preferred(self, tmp_path):
        """Latest netlist step is preferred."""
        run = write_run(tmp_path, all_corners_violating())
        stale = run / "42-openroad-detailedrouting"
        stale.mkdir()
        (stale / "soc_top.nl.v").write_text("module soc_top (); endmodule\n")
        assert mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path))).ok


# --------------------------------------------------------------------------- CLI
class TestCli:
    def test_exit_0_when_waived(self, tmp_path, capsys):
        """Exit 0 when waived."""
        run = write_run(tmp_path, all_corners_violating())
        rc = mw.main([str(run), "--waivers", str(waiver_file(tmp_path))])
        out = capsys.readouterr().out
        assert rc == 0
        assert "WAIVED" in out
        assert "cpu-axi-rdata-pin-cap" in out

    def test_exit_1_without_waivers(self, tmp_path, capsys):
        """Exit 1 without waivers."""
        run = write_run(tmp_path, all_corners_violating())
        rc = mw.main([str(run)])
        out = capsys.readouterr().out
        assert rc == 1
        assert "UNWAIVED" in out

    def test_exit_2_on_report_error(self, tmp_path, capsys):
        """Exit 2 on report error."""
        run = tmp_path / "RUN_nothing"
        run.mkdir()
        assert mw.main([str(run)]) == 2

    def test_exit_2_on_bad_waiver_file(self, tmp_path):
        """Exit 2 on bad waiver file."""
        run = write_run(tmp_path, all_corners_violating())
        assert mw.main([str(run), "--waivers", str(tmp_path / "missing.json")]) == 2

    def test_stale_is_warned_in_output(self, tmp_path, capsys):
        """Stale is warned in output."""
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        rc = mw.main([str(run), "--waivers", str(waiver_file(tmp_path))])
        assert rc == 0
        assert "STALE" in capsys.readouterr().out

    def test_strict_stale_flag(self, tmp_path):
        """Strict stale flag."""
        run = write_run(tmp_path, {c: [] for c in CORNERS})
        assert mw.main([str(run), "--waivers", str(waiver_file(tmp_path)), "--strict-stale"]) == 1

    def test_explicit_netlist_override(self, tmp_path):
        """Explicit netlist override."""
        run = write_run(tmp_path, all_corners_violating())
        nl = tmp_path / "other.nl.v"
        nl.write_text(NETLIST)
        (run / "48-openroad-fillinsertion" / "soc_top.nl.v").unlink()
        rc = mw.main([str(run), "--waivers", str(waiver_file(tmp_path)), "--netlist", str(nl)])
        assert rc == 0


# ------------------------------------------------------------- driver (run-pinned) waivers
DRIVER_WAIVERS = {
    "version": 1,
    "waivers": [
        {
            "id": "drv-a",
            "driver": {"instance": "_000001_", "pin": "Y"},
            "run_id": "RUN_synthetic",
            "max_cap_pf": 0.60,
            "justification": "synthetic: 0.5 percent over the limit, pinned to one run",
        }
    ],
}


def driver_rows():
    """Driver rows."""
    return {
        "nom_tt_025C_1v80": [row("_000001_/Y", PIN_LIMIT, 0.5330)],
        "max_ss_100C_1v60": [],
        "min_ff_n40C_1v95": [],
    }


class TestDriverWaivers:
    def test_driver_waiver_covers_exact_driver_on_its_run(self, tmp_path):
        """Driver waiver covers exact driver on its run."""
        run = write_run(tmp_path, driver_rows())
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, DRIVER_WAIVERS)))
        assert v.ok
        assert len(v.waived) == 1 and v.unwaived == ()

    def test_driver_waiver_does_not_apply_to_another_run(self, tmp_path):
        """Driver waiver does not apply to another run."""
        run = write_run(tmp_path, driver_rows())
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, DRIVER_WAIVERS)))
        other = tmp_path / "RUN_other"
        run.rename(other)
        v = mw.evaluate_run(other, mw.load_waivers(waiver_file(tmp_path, DRIVER_WAIVERS)))
        assert not v.ok
        assert [w.id for w in v.stale_waivers] == ["drv-a"]

    def test_driver_waiver_needs_run_id_when_called_without_one(self, tmp_path):
        """Driver waiver needs run id when called without one."""
        run = write_run(tmp_path, driver_rows())
        sta = mw.find_sta_dir(run)
        v = mw.evaluate_sta_dir(
            sta, mw.find_netlist(run), mw.load_waivers(waiver_file(tmp_path, DRIVER_WAIVERS))
        )
        assert not v.ok

    def test_driver_waiver_ceiling_still_enforced(self, tmp_path):
        """Driver waiver ceiling still enforced."""
        rows = {
            "nom_tt_025C_1v80": [row("_000001_/Y", PIN_LIMIT, 0.6500)],
            "max_ss_100C_1v60": [],
            "min_ff_n40C_1v95": [],
        }
        run = write_run(tmp_path, rows)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, DRIVER_WAIVERS)))
        assert not v.ok
        assert "ceiling" in v.unwaived[0].reason

    def test_other_driver_is_not_covered(self, tmp_path):
        """Other driver is not covered."""
        rows = {
            "nom_tt_025C_1v80": [row("_999999_/Y", PIN_LIMIT, 0.5330)],
            "max_ss_100C_1v60": [],
            "min_ff_n40C_1v95": [],
        }
        nl = NETLIST.replace(" _000001_ ", " _999999_ ")
        run = write_run(tmp_path, rows, netlist=nl)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, DRIVER_WAIVERS)))
        assert not v.ok

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda w: w.pop("run_id"),
            lambda w: w.update(load_pin={"instance": "u_cpu*", "pin": "p"}),
            lambda w: w["driver"].update(instance="_0000*"),
            lambda w: w.pop("driver"),
        ],
    )
    def test_malformed_driver_waivers_are_rejected(self, tmp_path, mutate):
        """Malformed driver waivers are rejected."""
        data = json.loads(json.dumps(DRIVER_WAIVERS))
        mutate(data["waivers"][0])
        with pytest.raises(mw.WaiverError):
            mw.load_waivers(waiver_file(tmp_path, data))


# ---------------------------------------------- stable hand-instantiated driver waivers (no run_id)
STABLE_NETLIST = NETLIST.replace(
    " sky130_fd_sc_hd__nand2_1 _000001_ (.A(a), .B(b), .Y(net_other));",
    " sky130_fd_sc_hd__nand2_1 _000001_ (.A(a), .B(b), .Y(net_other));\n"
    " sky130_fd_sc_hd__mux2_4 \\u_cpu_pll_sub.u_ref_cm.u_mux  "
    "(.A0(a), .A1(b), .S(s), .X(mux_clk));",
)
STABLE_WAIVERS = {
    "version": 1,
    "waivers": [
        {
            "id": "stable-mux",
            "driver": {"instance": "u_cpu_pll_sub.u_ref_cm.u_mux", "pin": "X", "stable": True},
            "corners": ["max_ss_100C_1v60"],
            "max_cap_pf": 0.45,
            "justification": "synthetic: hand-instantiated clock mux, survives re-synthesis",
        }
    ],
}


def stable_rows(cap=0.40):
    """Stable rows."""
    return {
        "nom_tt_025C_1v80": [],
        "max_ss_100C_1v60": [row("u_cpu_pll_sub.u_ref_cm.u_mux/X", SS_LIMIT, cap)],
        "min_ff_n40C_1v95": [],
    }


class TestStableDriverWaivers:
    def test_stable_driver_waiver_applies_without_run_id_on_any_run(self, tmp_path):
        """Stable driver waiver applies without run id on any run."""
        run = write_run(tmp_path, stable_rows(), netlist=STABLE_NETLIST)
        w = mw.load_waivers(waiver_file(tmp_path, STABLE_WAIVERS))
        assert w[0].stable_driver and w[0].run_id == ""
        assert mw.evaluate_run(run, w).ok
        other = tmp_path / "RUN_a_completely_different_run"
        run.rename(other)
        v = mw.evaluate_run(other, w)
        assert v.ok and len(v.waived) == 1 and v.stale_waivers == ()

    def test_stable_driver_waiver_applies_to_evaluate_sta_dir_without_run_id(self, tmp_path):
        """Stable driver waiver applies to evaluate sta dir without run id."""
        run = write_run(tmp_path, stable_rows(), netlist=STABLE_NETLIST)
        v = mw.evaluate_sta_dir(
            mw.find_sta_dir(run),
            mw.find_netlist(run),
            mw.load_waivers(waiver_file(tmp_path, STABLE_WAIVERS)),
        )
        assert v.ok

    def test_stable_driver_waiver_ceiling_still_binds(self, tmp_path):
        """Stable driver waiver ceiling still binds."""
        run = write_run(tmp_path, stable_rows(cap=0.50), netlist=STABLE_NETLIST)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, STABLE_WAIVERS)))
        assert not v.ok and "ceiling" in v.unwaived[0].reason

    def test_stable_driver_waiver_corner_scope_binds(self, tmp_path):
        """Stable driver waiver corner scope binds."""
        rows = stable_rows()
        rows["nom_tt_025C_1v80"] = [row("u_cpu_pll_sub.u_ref_cm.u_mux/X", PIN_LIMIT, 0.60)]
        run = write_run(tmp_path, rows, netlist=STABLE_NETLIST)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, STABLE_WAIVERS)))
        assert not v.ok
        assert [u.corner for u in v.unwaived] == ["nom_tt_025C_1v80"]

    def test_stable_driver_waiver_is_stale_when_the_driver_does_not_violate(self, tmp_path):
        """Stable driver waiver is stale when the driver does not violate."""
        run = write_run(tmp_path, {c: [] for c in CORNERS}, netlist=STABLE_NETLIST)
        waivers = mw.load_waivers(waiver_file(tmp_path, STABLE_WAIVERS))
        v = mw.evaluate_run(run, waivers)
        assert v.ok and [s.id for s in v.stale_waivers] == ["stable-mux"]
        assert "u_cpu_pll_sub.u_ref_cm.u_mux/X" in v.format()
        assert not mw.evaluate_run(run, waivers, strict_stale=True).ok

    def test_stable_driver_waiver_does_not_cover_another_driver(self, tmp_path):
        """Stable driver waiver does not cover another driver."""
        rows = {
            "nom_tt_025C_1v80": [],
            "max_ss_100C_1v60": [row("_000001_/Y", SS_LIMIT, 0.40)],
            "min_ff_n40C_1v95": [],
        }
        run = write_run(tmp_path, rows, netlist=STABLE_NETLIST)
        assert not mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, STABLE_WAIVERS))).ok

    @pytest.mark.parametrize(
        "name",
        [
            "_078722_",
            "net4101",
            "max_cap7259",
            "wire6998",
            "load_slew6964",
            "rebuffer12",
            "clkbuf_3_6_0_tck_i",
            "u_x._000123_",
        ],
    )
    def test_stable_flag_rejects_a_tool_generated_name(self, tmp_path, name):
        """Stable flag rejects a tool generated name."""
        data = json.loads(json.dumps(STABLE_WAIVERS))
        data["waivers"][0]["driver"]["instance"] = name
        with pytest.raises(mw.WaiverError, match="tool-generated"):
            mw.load_waivers(waiver_file(tmp_path, data))
        assert mw.looks_generated(name)

    @pytest.mark.parametrize(
        "name",
        ["u_cpu_pll_sub.u_ref_cm.u_mux", "u_pll_sub.u_ref_cm.u_root_buf", "u_cpu_cg.g_cell.u_icg"],
    )
    def test_hand_instantiated_names_are_not_flagged(self, name):
        """Hand instantiated names are not flagged."""
        assert not mw.looks_generated(name)

    def test_run_pinned_path_is_unchanged_for_synthesis_names(self, tmp_path):
        """Run pinned path is unchanged for synthesis names."""
        data = json.loads(json.dumps(DRIVER_WAIVERS))
        data["waivers"][0]["driver"]["stable"] = False
        assert mw.load_waivers(waiver_file(tmp_path, data))[0].run_id == "RUN_synthetic"
        data["waivers"][0].pop("run_id")
        with pytest.raises(mw.WaiverError, match="run_id"):
            mw.load_waivers(waiver_file(tmp_path, data))

    @pytest.mark.parametrize("bad", ["yes", 1, None])
    def test_stable_must_be_boolean(self, tmp_path, bad):
        """Stable must be boolean."""
        data = json.loads(json.dumps(STABLE_WAIVERS))
        data["waivers"][0]["driver"]["stable"] = bad
        with pytest.raises(mw.WaiverError):
            mw.load_waivers(waiver_file(tmp_path, data))

    def test_stable_with_run_id_still_pins_to_that_run(self, tmp_path):
        """Stable with run id still pins to that run."""
        data = json.loads(json.dumps(STABLE_WAIVERS))
        data["waivers"][0]["run_id"] = "RUN_somewhere_else"
        run = write_run(tmp_path, stable_rows(), netlist=STABLE_NETLIST)
        assert not mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, data))).ok


# ------------------------------------------------------------- load-class waivers (bead j41m.17, user decision 2026-10-27)  # noqa: E501
# "hold dlygate whose only non-diode load is an SCD pin": the hold-buffer scan-link nets
CLASS_NETLIST = NETLIST.replace(
    " sky130_fd_sc_hd__nand2_1 _000001_ (.A(a), .B(b), .Y(net_other));",
    " sky130_fd_sc_hd__nand2_1 _000001_ (.A(a), .B(b), .Y(net_other));\n"
    " sky130_fd_sc_hd__dlygate4sd3_1 hold19396 (.A(q_prev), .X(scd_net));\n"
    " sky130_fd_sc_hd__sdfxtp_2 _flop_ (.CLK(clk), .D(d), .Q(q), .SCD(scd_net), .SCE(se));\n"
    " sky130_fd_sc_hd__diode_2 ANTENNA_1 (.DIODE(scd_net));\n"
    " sky130_fd_sc_hd__diode_2 ANTENNA_2 (.DIODE(scd_net));\n",
)
CLASS_WAIVERS = {
    "version": 1,
    "waivers": [
        {
            "id": "hold-scd-link",
            "driver_class": {
                "cell_prefix": "sky130_fd_sc_hd__dlygate4sd3_",
                "sole_non_diode_load": {"cell_prefix": "sky130_fd_sc_hd__sdf", "pin": "SCD"},
            },
            "corners": ["max_ss_100C_1v60"],
            "max_cap_pf": 0.115,
            "justification": "synthetic: hold dlygate on a scan link carrying antenna diodes",
        }
    ],
}
DLY_LIMIT = 0.1007


def class_rows(cap=0.1113, driver="hold19396/X"):
    """Class rows."""
    return {
        "nom_tt_025C_1v80": [],
        "max_ss_100C_1v60": [row(driver, DLY_LIMIT, cap)],
        "min_ff_n40C_1v95": [],
    }


class TestLoadClassWaivers:
    def test_accepts_a_hold_dlygate_whose_only_non_diode_load_is_an_scd_pin(self, tmp_path):
        """Accepts a hold dlygate whose only non diode load is an scd pin."""
        run = write_run(tmp_path, class_rows(), netlist=CLASS_NETLIST)
        v = mw.evaluate_run(
            run, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS)), strict_stale=True
        )
        assert v.ok, v.format()
        assert len(v.waived) == 1 and v.waived[0].waiver_id == "hold-scd-link"
        assert v.unwaived == () and v.stale_waivers == ()

    def test_applies_to_any_run_and_any_generated_driver_name(self, tmp_path):
        """Applies to any run and any generated driver name."""
        nl = CLASS_NETLIST.replace("hold19396", "hold77777")
        run = write_run(tmp_path, class_rows(driver="hold77777/X"), netlist=nl)
        other = tmp_path / "RUN_anything_else"
        run.rename(other)
        assert mw.evaluate_run(other, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS))).ok

    def test_rejects_when_another_non_diode_load_other_than_scd_is_present(self, tmp_path):
        """Rejects when another non diode load other than scd is present."""
        nl = CLASS_NETLIST.replace(
            " sky130_fd_sc_hd__diode_2 ANTENNA_1 (.DIODE(scd_net));",
            " sky130_fd_sc_hd__nand2_1 _extra_ (.A(scd_net), .B(b), .Y(zz));\n"
            " sky130_fd_sc_hd__diode_2 ANTENNA_1 (.DIODE(scd_net));",
        )
        run = write_run(tmp_path, class_rows(), netlist=nl)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS)))
        assert not v.ok and len(v.unwaived) == 1

    def test_rejects_a_second_scd_load_and_a_non_scd_pin_on_the_flop(self, tmp_path):
        """Rejects a second scd load and a non scd pin on the flop."""
        two = CLASS_NETLIST.replace(
            " sky130_fd_sc_hd__diode_2 ANTENNA_1 (.DIODE(scd_net));",
            " sky130_fd_sc_hd__sdfxtp_2 _flop2_ (.CLK(clk), .D(d), .Q(q2), .SCD(scd_net), .SCE(se));\n"  # noqa: E501
            " sky130_fd_sc_hd__diode_2 ANTENNA_1 (.DIODE(scd_net));",
        )
        run = write_run(tmp_path, class_rows(), netlist=two)
        assert not mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS))).ok
        wrong_pin = CLASS_NETLIST.replace(".SCD(scd_net)", ".D(scd_net)").replace(
            ".D(d)", ".SCD(d)"
        )
        run2 = write_run(tmp_path / "b", class_rows(), netlist=wrong_pin)
        assert not mw.evaluate_run(run2, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS))).ok

    def test_rejects_a_macro_load(self, tmp_path):
        """Rejects a macro load."""
        nl = CLASS_NETLIST.replace(
            " sky130_fd_sc_hd__diode_2 ANTENNA_1 (.DIODE(scd_net));",
            " sky130_sram_4kbyte_1rw1r_32x1024_8 u_m2 (.csb0(scd_net));\n"
            " sky130_fd_sc_hd__diode_2 ANTENNA_1 (.DIODE(scd_net));",
        )
        run = write_run(tmp_path, class_rows(), netlist=nl)
        assert not mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS))).ok

    def test_rejects_a_different_cell_type_on_the_driver(self, tmp_path):
        """Rejects a different cell type on the driver."""
        nl = CLASS_NETLIST.replace(
            "sky130_fd_sc_hd__dlygate4sd3_1 hold19396", "sky130_fd_sc_hd__buf_4 hold19396"
        )
        run = write_run(tmp_path, class_rows(), netlist=nl)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS)))
        assert not v.ok and len(v.unwaived) == 1
        nl2 = CLASS_NETLIST.replace(
            "sky130_fd_sc_hd__dlygate4sd3_1 hold19396", "sky130_fd_sc_hd__dlygate4sd1_1 hold19396"
        )
        run2 = write_run(tmp_path / "b", class_rows(), netlist=nl2)
        assert not mw.evaluate_run(run2, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS))).ok

    def test_ceiling_and_corner_scope_still_bind(self, tmp_path):
        """Ceiling and corner scope still bind."""
        run = write_run(tmp_path, class_rows(cap=0.120), netlist=CLASS_NETLIST)
        v = mw.evaluate_run(run, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS)))
        assert not v.ok and "ceiling" in v.unwaived[0].reason
        rows = class_rows()
        rows["nom_tt_025C_1v80"] = [row("hold19396/X", PIN_LIMIT, 0.60)]
        run2 = write_run(tmp_path / "b", rows, netlist=CLASS_NETLIST)
        v2 = mw.evaluate_run(run2, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS)))
        assert [u.corner for u in v2.unwaived] == ["nom_tt_025C_1v80"]

    def test_stale_when_no_violation_matches_and_strict_fails(self, tmp_path):
        """Stale when no violation matches and strict fails."""
        run = write_run(tmp_path, {c: [] for c in CORNERS}, netlist=CLASS_NETLIST)
        waivers = mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS))
        v = mw.evaluate_run(run, waivers)
        assert v.ok and [s.id for s in v.stale_waivers] == ["hold-scd-link"]
        text = v.format()
        assert "STALE" in text and "dlygate4sd3_" in text and "SCD" in text
        assert not mw.evaluate_run(run, waivers, strict_stale=True).ok

    def test_stale_when_the_class_does_not_match_the_violation(self, tmp_path):
        """Stale when the class does not match the violation."""
        nl = CLASS_NETLIST.replace(
            "sky130_fd_sc_hd__dlygate4sd3_1 hold19396", "sky130_fd_sc_hd__buf_4 hold19396"
        )
        run = write_run(tmp_path, class_rows(), netlist=nl)
        v = mw.evaluate_run(
            run, mw.load_waivers(waiver_file(tmp_path, CLASS_WAIVERS)), strict_stale=True
        )
        assert not v.ok and [s.id for s in v.stale_waivers] == ["hold-scd-link"]

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda w: w["driver_class"].update(cell_prefix="dlygate4sd3_"),
            lambda w: w["driver_class"].update(cell_prefix="sky130_fd_sc_hd__dly*"),
            lambda w: w["driver_class"].pop("sole_non_diode_load"),
            lambda w: w["driver_class"]["sole_non_diode_load"].update(pin=""),
            lambda w: w["driver_class"]["sole_non_diode_load"].update(cell_prefix="sdf"),
            lambda w: w.update(load_pin={"instance": "u_cpu*", "pin": "p"}),
            lambda w: w.update(justification=" "),
            lambda w: w.update(max_cap_pf=0),
        ],
    )
    def test_malformed_class_waivers_are_rejected(self, tmp_path, mutate):
        """Malformed class waivers are rejected."""
        data = json.loads(json.dumps(CLASS_WAIVERS))
        mutate(data["waivers"][0])
        with pytest.raises(mw.WaiverError):
            mw.load_waivers(waiver_file(tmp_path, data))

    def test_empty_waiver_list_is_still_strict(self, tmp_path):
        """Empty waiver list is still strict."""
        run = write_run(tmp_path, class_rows(), netlist=CLASS_NETLIST)
        assert not mw.evaluate_run(run, ()).ok


# ------------------------------------------------------------- the committed waiver file (bead j41m.17)  # noqa: E501
COMMITTED = (
    Path(__file__).resolve().parents[2]
    / "pnr"
    / "sky130"
    / "soc"
    / "constraints"
    / "max_cap_waivers.json"
)


def test_committed_waiver_file_loads_and_has_the_expected_kinds():
    """Committed waiver file loads and has the expected kinds."""
    ws = mw.load_waivers(COMMITTED)
    by_id = {w.id: w for w in ws}
    assert (
        by_id["u-ref-cm-mux-clk-cpu-pll-sub"].stable_driver
        and by_id["u-ref-cm-mux-clk-cpu-pll-sub"].max_cap_pf == 0.55
    )
    cls = by_id["hold-dlygate-scd-link"]
    assert (
        cls.cls_driver_prefix == "sky130_fd_sc_hd__dlygate4sd3_"
        and cls.cls_load_pin == "SCD"
        and cls.max_cap_pf == 0.12  # 0.115 -> 0.120 (user decision 2026-10-28)
    )
    # the two waivers pinned to RUN_2026-10-27_05-40-27 were deleted (stale on the next run)
    for k in ("gen-a21oi-107570-run-2026-10-27", "gen-or4-076179-run-2026-10-27"):
        assert k not in by_id
    assert not any(i.startswith("sram-din0-") for i in by_id)  # stale ones deleted
    assert not any(w.run_id for w in ws)  # nothing in the committed file is pinned to a run
    assert all(w.justification for w in ws)
