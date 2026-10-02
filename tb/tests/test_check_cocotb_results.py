"""Unit tests for tools/verif/check_cocotb_results.py (bead p6t8).

cocotb 1.9.2's makefile cannot set an exit code from a test failure, so the SoC
Makefile redefines ``check_for_results_file`` to run this checker on every
build point's results.xml.  The checker reuses the tested ``summarize.parse_cocotb``
verdict; these tests pin the contract the Makefile depends on: exit 0 only for a
clean, non-empty run, exit 1 for everything else.
"""

from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "verif" / "check_cocotb_results.py"
_SPEC = importlib.util.spec_from_file_location("check_cocotb_results", SCRIPT)
assert _SPEC and _SPEC.loader
checker = importlib.util.module_from_spec(_SPEC)
sys.modules["check_cocotb_results"] = checker
_SPEC.loader.exec_module(checker)

_HEAD = '<?xml version="1.0" encoding="UTF-8"?>\n<testsuites>\n  <testsuite name="soc">\n'
_TAIL = "  </testsuite>\n</testsuites>\n"
_PASS_CASE = '    <testcase classname="test_x" name="test_ok"/>\n'

_XML_CLEAN = _HEAD + _PASS_CASE + '    <testcase classname="test_x" name="test_ok2"/>\n' + _TAIL
_XML_CLEAN_WITH_SKIP = (
    _HEAD
    + _PASS_CASE
    + '    <testcase classname="test_x" name="test_skip"><skipped/></testcase>\n'
    + _TAIL
)
_XML_FAILURE = (
    _HEAD
    + _PASS_CASE
    + '    <testcase classname="test_x" name="test_bad">\n'
    + '      <failure message="AssertionError: stale SIM_BUILD">trace</failure>\n'
    + "    </testcase>\n"
    + _TAIL
)
_XML_ERROR = (
    _HEAD
    + _PASS_CASE
    + '    <testcase classname="test_x" name="test_boom">\n'
    + '      <error message="RuntimeError: boom">trace</error>\n'
    + "    </testcase>\n"
    + _TAIL
)
_XML_NO_PASS = (
    _HEAD + '    <testcase classname="test_x" name="test_skip"><skipped/></testcase>\n' + _TAIL
)
_XML_EMPTY = _HEAD + _TAIL


def _write(tmp_path: Path, text: str) -> Path:
    xml = tmp_path / "results.xml"
    xml.write_text(text, encoding="utf-8")
    return xml


def _run(xml: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(xml)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_clean_results_exit_zero_and_silent(tmp_path: Path) -> None:
    """A clean run exits 0 and prints nothing (it runs once per build point)."""
    proc = _run(_write(tmp_path, _XML_CLEAN))
    assert proc.returncode == 0
    assert proc.stdout == ""
    assert proc.stderr == ""


def test_skipped_cases_do_not_make_a_clean_run_dirty(tmp_path: Path) -> None:
    """A skip next to a pass is clean: register_bank deliberately skips per build point."""
    assert _run(_write(tmp_path, _XML_CLEAN_WITH_SKIP)).returncode == 0


def test_failure_exits_nonzero_and_names_the_test(tmp_path: Path) -> None:
    """A <failure> testcase fails the check and the message names it."""
    xml = _write(tmp_path, _XML_FAILURE)
    proc = _run(xml)
    assert proc.returncode == 1
    assert str(xml) in proc.stderr
    assert "test_x.test_bad" in proc.stderr
    assert "stale SIM_BUILD" in proc.stderr


def test_error_testcase_exits_nonzero(tmp_path: Path) -> None:
    """An <error> testcase is treated exactly like a failure."""
    proc = _run(_write(tmp_path, _XML_ERROR))
    assert proc.returncode == 1
    assert "test_x.test_boom" in proc.stderr


@pytest.mark.parametrize("text", [_XML_NO_PASS, _XML_EMPTY], ids=["only-skipped", "no-testcases"])
def test_no_passing_test_exits_nonzero(tmp_path: Path, text: str) -> None:
    """A clean exit with nothing run is not a pass (bead dwp)."""
    proc = _run(_write(tmp_path, text))
    assert proc.returncode == 1
    assert "no passing test" in proc.stderr


def test_corrupt_xml_exits_nonzero(tmp_path: Path) -> None:
    """A results.xml that does not parse is an error, never clean."""
    xml = _write(tmp_path, "<testsuites><testsuite")
    proc = _run(xml)
    assert proc.returncode == 1
    assert "unparsable" in proc.stderr


def test_missing_file_exits_nonzero(tmp_path: Path) -> None:
    """A results file that was never written is not clean."""
    proc = _run(tmp_path / "does_not_exist.xml")
    assert proc.returncode == 1
    assert "missing" in proc.stderr


def test_wrong_argument_count_exits_nonzero() -> None:
    """Calling it with no path is a usage error, not a silent pass."""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)], capture_output=True, text=True, check=False
    )
    assert proc.returncode == 1
    assert "usage" in proc.stderr


def test_check_returns_clean_flag_and_message(tmp_path: Path) -> None:
    """The in-process API mirrors the CLI: (True, '') clean, (False, msg) otherwise."""
    assert checker.check(_write(tmp_path, _XML_CLEAN)) == (True, "")
    clean, message = checker.check(_write(tmp_path, _XML_FAILURE))
    assert clean is False
    assert "test_bad" in message
