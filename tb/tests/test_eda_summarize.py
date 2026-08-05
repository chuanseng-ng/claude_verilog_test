"""Unit tests for tools/eda/summarize.py — the EDA log -> JSON verdict layer.

The behaviour under test that matters most is the ERROR verdict: a tool that
exits 0 while producing an empty or unreadable report must never be reported as
PASS. This repo shipped a CDC timing gate that passed for exactly that reason
(bead `dwp`), so each parser has an explicit "nothing to parse" case here.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SPEC = importlib.util.spec_from_file_location(
    "eda_summarize", REPO_ROOT / "tools" / "eda" / "summarize.py"
)
assert _SPEC and _SPEC.loader
summarize = importlib.util.module_from_spec(_SPEC)
sys.modules["eda_summarize"] = summarize
_SPEC.loader.exec_module(summarize)

PASS, FAIL, ERROR = summarize.PASS, summarize.FAIL, summarize.ERROR


# ---------------------------------------------------------------- verilator


def test_verilator_clean_is_pass() -> None:
    """A lint run with no errors or warnings is PASS."""
    status, summary = summarize.parse_verilator("- Verilator: Built from 1 MB\n", 0)
    assert status == PASS
    assert summary["error_count"] == 0
    assert summary["warning_count"] == 0


def test_verilator_groups_warnings_by_code() -> None:
    """Warnings are tallied per Verilator code, errors are kept verbatim."""
    log = (
        "%Warning-WIDTHTRUNC: rtl/a.sv:1:1: truncation\n"
        "%Warning-WIDTHTRUNC: rtl/b.sv:2:2: truncation\n"
        "%Warning-UNUSEDSIGNAL: rtl/c.sv:3:3: unused\n"
        "%Error: Exiting due to 3 warning(s)\n"
    )
    status, summary = summarize.parse_verilator(log, 1)
    assert status == FAIL
    assert summary["warnings_by_code"] == {"WIDTHTRUNC": 2, "UNUSEDSIGNAL": 1}
    assert summary["error_count"] == 1


def test_verilator_nonzero_exit_fails_even_without_error_lines() -> None:
    """A non-zero tool exit fails even when the log looks unremarkable."""
    status, _ = summarize.parse_verilator("nothing interesting\n", 1)
    assert status == FAIL


# -------------------------------------------------------------------- yosys


def test_yosys_extracts_cells_and_area() -> None:
    """Cell count and chip area are lifted out of the statistics section."""
    log = (
        "Printing statistics.\n"
        "   Number of cells:               4058\n"
        "Chip area for module '\\soc_top': 3844.000000\n"
    )
    status, summary = summarize.parse_yosys(log, 0)
    assert status == PASS
    assert summary["cell_count"] == 4058
    assert summary["chip_area"] == pytest.approx(3844.0)


def test_yosys_error_line_fails() -> None:
    """An ERROR: line fails and is echoed in the summary."""
    status, summary = summarize.parse_yosys("ERROR: syntax error in rtl/x.v\n", 1)
    assert status == FAIL
    assert summary["errors"] == ["ERROR: syntax error in rtl/x.v"]


def test_yosys_without_statistics_is_error_not_pass() -> None:
    """Exit 0 with no statistics means synthesis never really ran."""
    status, summary = summarize.parse_yosys("Yosys 0.62\n", 0)
    assert status == ERROR
    assert "note" in summary


# ------------------------------------------------------------------ opensta


def test_opensta_clean_report_passes() -> None:
    """A report with only MET paths and non-negative wns is PASS."""
    status, summary = summarize.parse_opensta(
        "   0.0130   slack (MET)\nwns 0.0130\ntns 0.0000\n", 0
    )
    assert status == PASS
    assert summary["violated_endpoints"] == 0
    assert summary["wns"] == pytest.approx(0.013)


def test_opensta_violated_endpoint_fails_despite_exit_zero() -> None:
    """A VIOLATED path fails even though OpenSTA itself exited 0."""
    log = "   -0.0421   slack (VIOLATED)\n   0.0130   slack (MET)\nwns -0.0421\ntns -0.0850\n"
    status, summary = summarize.parse_opensta(log, 0)
    assert status == FAIL
    assert summary["violated_endpoints"] == 1
    assert summary["wns"] == pytest.approx(-0.0421)
    assert summary["tns"] == pytest.approx(-0.085)


def test_opensta_empty_report_is_error_not_pass() -> None:
    """The bead `dwp` failure mode: nothing reported, tool exited 0."""
    status, summary = summarize.parse_opensta("", 0)
    assert status == ERROR
    assert "dwp" in summary["note"]


def test_opensta_derives_wns_from_slacks_when_report_wns_absent() -> None:
    """Without report_wns, wns falls back to the smallest reported slack."""
    status, summary = summarize.parse_opensta(
        "   0.0500   slack (MET)\n   0.0100   slack (MET)\n", 0
    )
    assert status == PASS
    assert summary["wns"] == pytest.approx(0.01)


def test_opensta_error_line_fails() -> None:
    """An Error: line from OpenSTA fails the verdict."""
    status, _ = summarize.parse_opensta("Error: no such file rtl.v\n", 0)
    assert status == FAIL


def test_opensta_zero_wns_tns_with_positive_worst_slack_is_pass() -> None:
    """A clean design: wns/tns read 0.00 (no negative slack), but the real
    margin only shows up in worst_slack. This is the report_wns_tns shape of
    the signed-off rv32i_cpu_top ASAP7 run — wns/tns=0.00 must not be mistaken
    for "nothing reported" and must still surface worst_slack in the summary.
    """
    status, summary = summarize.parse_opensta("wns 0.00\ntns 0.00\nworst slack 24.01\n", 0)
    assert status == PASS
    assert summary["wns"] == pytest.approx(0.0)
    assert summary["tns"] == pytest.approx(0.0)
    assert summary["worst_slack"] == pytest.approx(24.01)
    assert "note" not in summary


def test_opensta_worst_slack_only_is_not_empty_report_error() -> None:
    """A report with only a 'worst slack' line (no slack paths, no wns/tns)
    must not fall into the empty-report ERROR case (bead `dwp`) -- worst_slack
    alone is enough evidence that report_worst_slack actually ran.
    """
    status, summary = summarize.parse_opensta("worst slack 24.01\n", 0)
    assert status == PASS
    assert summary["worst_slack"] == pytest.approx(24.01)
    assert "note" not in summary


# ------------------------------------------------------------------- cocotb

_XML_PASS = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="soc">
    <testcase classname="test_uart" name="test_tx"/>
    <testcase classname="test_uart" name="test_rx"/>
  </testsuite>
</testsuites>
"""

_XML_FAIL = """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="soc">
    <testcase classname="test_uart" name="test_tx"/>
    <testcase classname="test_uart" name="test_rx">
      <failure message="AssertionError: expected 0x2a, got 0x00">trace</failure>
    </testcase>
    <testcase classname="test_uart" name="test_skipped"><skipped/></testcase>
  </testsuite>
</testsuites>
"""


def test_cocotb_results_xml_pass(tmp_path: Path) -> None:
    """A results.xml with only passing cases is PASS."""
    xml = tmp_path / "results.xml"
    xml.write_text(_XML_PASS, encoding="utf-8")
    status, summary = summarize.parse_cocotb("", 0, xml)
    assert status == PASS
    assert (summary["passed"], summary["failed"], summary["skipped"]) == (2, 0, 0)


def test_cocotb_results_xml_failure_names_the_test(tmp_path: Path) -> None:
    """A failing case is counted and named with its assertion message."""
    xml = tmp_path / "results.xml"
    xml.write_text(_XML_FAIL, encoding="utf-8")
    status, summary = summarize.parse_cocotb("", 0, xml)
    assert status == FAIL
    assert summary["failed"] == 1
    assert summary["skipped"] == 1
    assert summary["failures"] == ["test_uart.test_rx: AssertionError: expected 0x2a, got 0x00"]


def test_cocotb_unparsable_xml_is_error(tmp_path: Path) -> None:
    """A corrupt results.xml is ERROR, never PASS."""
    xml = tmp_path / "results.xml"
    xml.write_text("<not-xml", encoding="utf-8")
    status, _ = summarize.parse_cocotb("", 0, xml)
    assert status == ERROR


def test_cocotb_falls_back_to_log_tally() -> None:
    """With no results.xml, the cocotb TESTS= tally line is used."""
    log = "  ** TESTS=26 PASS=26 FAIL=0 SKIP=0     79352.03   6.03  13160.23 **\n"
    status, summary = summarize.parse_cocotb(log, 0, None)
    assert status == PASS
    assert summary["total"] == 26
    assert summary["source"] == "log tally"


def test_cocotb_log_tally_with_failures_fails() -> None:
    """A tally reporting FAIL>0 fails and names the failing rows."""
    log = (
        "  ** test_soc_boot.test_uart_tx   FAIL   120.00  0.01  9000.00 **\n"
        "  ** TESTS=2 PASS=1 FAIL=1 SKIP=0   690.00  0.03  20000.00 **\n"
    )
    status, summary = summarize.parse_cocotb(log, 2, None)
    assert status == FAIL
    assert summary["failed"] == 1
    assert summary["failures"] == ["test_soc_boot.test_uart_tx"]


def test_cocotb_no_results_and_no_tally_is_error() -> None:
    """Simulator died before the regression finished — must not read as PASS."""
    log = "ERROR: results.xml was not written by the simulation!\n"
    status, summary = summarize.parse_cocotb(log, 0, None)
    assert status == ERROR
    assert summary["errors"] == ["ERROR: results.xml was not written by the simulation!"]


# --------------------------------------------------------------------- misc


def test_cap_marks_truncation_instead_of_dropping_silently() -> None:
    """A capped list carries an explicit '... N more' marker, never a silent cut."""
    items = [f"item{i}" for i in range(summarize.MAX_ITEMS + 5)]
    capped = summarize._cap(items)  # pylint: disable=protected-access
    assert len(capped) == summarize.MAX_ITEMS + 1
    assert "5 more" in capped[-1]
