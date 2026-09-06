"""Unit tests for tools/eda/summarize.py — the EDA log -> JSON verdict layer.

The behaviour under test that matters most is the ERROR verdict: a tool that
exits 0 while producing an empty or unreadable report must never be reported as
PASS. This repo shipped a CDC timing gate that passed for exactly that reason
(bead `dwp`), so each parser has an explicit "nothing to parse" case here.
"""

from __future__ import annotations

import importlib.util
import json
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


# ------------------------------------------- CodeRabbit PR #134 regressions


def test_opensta_negative_worst_slack_alone_fails() -> None:
    """A report carrying only a negative `worst slack` must FAIL, not PASS.

    Reachable via run_tcl or a truncated timing report: no VIOLATED row, no
    wns/tns line, so every other violation signal reads clean.
    """
    status, summary = summarize.parse_opensta("worst slack -1.5\n", 0)
    assert status == FAIL
    assert summary["worst_slack"] == pytest.approx(-1.5)


def test_verilator_counts_uncoded_warning_lines() -> None:
    """Bare `%Warning:` lines (SystemVerilog $warning) are counted too."""
    log = "%Warning: rtl/a.sv:3: user warning via $warning\n%Warning-WIDTHTRUNC: rtl/b.sv:4: x\n"
    status, summary = summarize.parse_verilator(log, 0)
    assert status == PASS
    assert summary["warning_count"] == 2
    assert summary["warnings_by_code"] == {"UNCODED": 1, "WIDTHTRUNC": 1}


def test_cocotb_zero_test_tally_is_error_not_pass() -> None:
    """`TESTS=0 PASS=0 FAIL=0 SKIP=0` with a clean exit means nothing ran."""
    status, summary = summarize.parse_cocotb("** TESTS=0 PASS=0 FAIL=0 SKIP=0 **\n", 0, None)
    assert status == ERROR
    assert "note" in summary


# -------------------------------------------------------------------- bambu

# Bambu echoes its own invocation on line 1; the parser reads --simulate from it
# to decide whether co-simulation results are required. Everything below is
# trimmed from real Gate A/B logs (GH #119).
_BAMBU_HEAD = (
    " ==  Bambu executed with: /nix/store/xx/bambu --top-fname=coal_shape "
    "--generate-interface=INFER {sim}--device-name=asap7-TC --clock-period=0.705 gate_b.c \n"
)
_BAMBU_HLS_DONE = (
    "    Total estimated area: 352744\n  Total number of flip-flops in function coal_shape: 820\n"
)
_BAMBU_COSIM_OK = (
    "  Total cycles             : 58 cycles\n"
    "  Number of executions     : 2\n"
    "  Average execution        : 29 cycles\n"
)


def _bambu_log(*, simulate: bool, hls_done: bool = True, cosim: bool = True) -> str:
    """Build a Bambu log with the requested phases present."""
    text = _BAMBU_HEAD.format(sim="--simulate --simulator=VERILATOR " if simulate else "")
    text += "                         High-Level Synthesis Tool\n"
    if hls_done:
        text += _BAMBU_HLS_DONE
    if simulate and cosim:
        text += _BAMBU_COSIM_OK
    return text


def _v(tmp_path: Path, content: str = "module coal_shape(); endmodule\n") -> Path:
    """Write a stand-in generated Verilog file."""
    path = tmp_path / "coal_shape.v"
    path.write_text(content, encoding="utf-8")
    return path


def test_bambu_cosim_run_is_pass(tmp_path: Path) -> None:
    """A --simulate run with a cosim block and a non-empty .v is PASS."""
    status, summary = summarize.parse_bambu(_bambu_log(simulate=True), 0, _v(tmp_path))
    assert status == PASS
    assert summary["simulated"] is True
    assert summary["top"] == "coal_shape"
    assert summary["device"] == "asap7-TC"
    assert summary["cycles"] == 58
    assert summary["executions"] == 2
    assert summary["flip_flops"] == 820
    assert summary["estimated_area"] == 352744
    assert len(summary["verilog_sha256"]) == 64


def test_bambu_generation_only_is_pass(tmp_path: Path) -> None:
    """A run without --simulate is PASS despite having no cosim block.

    Generation-only runs legitimately print no cycle counts. The parser learns
    the mode from the echoed command line rather than demanding cycles always.
    """
    status, summary = summarize.parse_bambu(_bambu_log(simulate=False), 0, _v(tmp_path))
    assert status == PASS
    assert summary["simulated"] is False
    assert "cycles" not in summary


def test_bambu_cosim_abort_is_fail(tmp_path: Path) -> None:
    """Bambu's own `error ->` line is a FAIL even when the HLS phase completed."""
    text = _bambu_log(simulate=True, cosim=False)
    text += "Warning: Returned error code!\nerror -> Co-simulation main aborted\n"
    status, summary = summarize.parse_bambu(text, 1, _v(tmp_path))
    assert status == FAIL
    assert any("Co-simulation main aborted" in e for e in summary["errors"])


def test_bambu_truncated_log_is_error_not_pass(tmp_path: Path) -> None:
    """A log that never reached the end of the HLS phase is ERROR, not PASS.

    The banner alone proves nothing: Bambu prints it before doing any work.
    """
    status, summary = summarize.parse_bambu(
        _bambu_log(simulate=False, hls_done=False), 0, _v(tmp_path)
    )
    assert status == ERROR
    assert "dwp" in summary["note"]


def test_bambu_simulate_without_cycles_is_error_not_pass(tmp_path: Path) -> None:
    """--simulate that produced no cosim block verified nothing, so it is ERROR."""
    status, summary = summarize.parse_bambu(_bambu_log(simulate=True, cosim=False), 0, _v(tmp_path))
    assert status == ERROR
    assert "dwp" in summary["note"]


def test_bambu_missing_verilog_is_error_not_pass(tmp_path: Path) -> None:
    """A clean exit that produced no .v is ERROR — the artefact is the deliverable."""
    status, summary = summarize.parse_bambu(_bambu_log(simulate=True), 0, tmp_path / "absent.v")
    assert status == ERROR
    assert "not found" in summary["note"]


def test_bambu_normalized_hash_ignores_the_generation_timestamp(tmp_path: Path) -> None:
    """Two runs of identical input differ only in Bambu's embedded date stamp.

    Verified against the real tool: three back-to-back runs of the same source
    produced three different raw digests and were byte-identical everywhere
    except the `- Date ...` header line. The normalized digest is what a
    committed "expected sha256" must pin, or it would fail on every
    regeneration.
    """
    head = "// Code created using PandA - Version: PandA 2024.10 - Date "
    body = "module coal_shape(); endmodule\n"
    first = tmp_path / "a.v"
    first.write_text(head + "2026-09-06T01:13:19\n" + body, encoding="utf-8")
    second = tmp_path / "b.v"
    second.write_text(head + "2026-09-06T01:13:52\n" + body, encoding="utf-8")

    _, sum_a = summarize.parse_bambu(_bambu_log(simulate=True), 0, first)
    _, sum_b = summarize.parse_bambu(_bambu_log(simulate=True), 0, second)

    assert sum_a["verilog_sha256"] != sum_b["verilog_sha256"]
    assert sum_a["verilog_sha256_normalized"] == sum_b["verilog_sha256_normalized"]


def test_bambu_empty_verilog_is_error_not_pass(tmp_path: Path) -> None:
    """A zero-byte .v is the exit-0-empty-report shape and must not be PASS."""
    status, summary = summarize.parse_bambu(_bambu_log(simulate=True), 0, _v(tmp_path, ""))
    assert status == ERROR
    assert "empty" in summary["note"]


def test_missing_log_file_exits_error_not_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An unreadable --log yields the ERROR verdict as JSON, not a traceback.

    A traceback exits 1, which a gate reads as FAIL — the distinction this
    script exists to preserve.
    """
    monkeypatch.setattr(
        "sys.argv",
        ["summarize.py", "--tool", "opensta", "--log", str(tmp_path / "nope.log")],
    )
    assert summarize.main() == ERROR
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "ERROR"
    assert "could not read log" in payload["summary"]["errors"][0]
