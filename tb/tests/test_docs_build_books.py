"""Unit tests for the log parsing of tools/docs/build_books.py."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import build_books  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error

TALL = r"Overfull \vbox (51.24896pt too high) has occurred while \output is active []"


def test_tall_rows_are_counted():
    """Check each overfull vbox in the output routine counts as a tall row."""
    other = r"Overfull \vbox (3.0pt too high) has occurred while \output is active"
    log = f"[44]\n{TALL}\n\n{TALL}\n[46]\n{other}\n"
    found = build_books.parse_log(log)
    assert len(found["tallrows"]) == 3
    assert found["tallrows"][0] == 51.24896


def test_other_overfull_boxes_are_not_tall_rows():
    """Check an ordinary overfull vbox, hbox or underfull vbox does not count."""
    log = (
        r"Overfull \vbox (12.0pt too high) detected at line 5"
        "\n"
        r"Overfull \hbox (40.0pt too wide) in paragraph at lines 1--2"
        "\n"
        r"Underfull \vbox (badness 10000) has occurred while \output is active"
        "\n"
    )
    found = build_books.parse_log(log)
    assert found["tallrows"] == []
    assert found["overfull"] == [40.0]
    assert found["errors"] == []


def test_the_line_inside_an_index_file_is_not_a_tall_row():
    """Check the multicol index line is skipped, and counting resumes after the index."""
    log = f"[379\n\n\n] (./crbeads.ind\n{TALL}\n\n\n[380\n\n\n]) [381] (./cr.aux)\n{TALL}\n"
    assert len(build_books.parse_log(log)["tallrows"]) == 1
    log2 = f"(./cr.aux)\n{TALL}\n"
    assert len(build_books.parse_log(log2)["tallrows"]) == 1


def test_a_tall_row_alone_is_not_an_error_line():
    """Check the tall row line is not read as a LaTeX error."""
    assert build_books.parse_log(TALL)["errors"] == []
