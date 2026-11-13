"""Unit tests for tools/docs/check_facts.py."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import check_facts as cf  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error


def _w(root: Path, name: str, text: str) -> str:
    """Helper: w."""
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return str(p)


def _run(capsys, before: str, after: str, *flags: str) -> tuple[int, str]:  # type: ignore[no-untyped-def]
    """Helper: run."""
    code = cf.main(["--before", before, "--after", after, *flags])
    return code, capsys.readouterr().out


def _facts(fmt: str, text: str):  # type: ignore[no-untyped-def]
    """Helper: facts."""
    return cf.sections_of(fmt, text, False)["(file)"]


def test_pure_rewording_with_same_facts_passes(tmp_path, capsys):
    """Check pure rewording with same facts passes."""
    a = _w(tmp_path, "a.md", "The clock runs at 571 MHz with `grant_o` registered.\n")
    b = _w(tmp_path, "b.md", "`grant_o` is registered, and the clock rate is 571 MHz.\n")
    code, out = _run(capsys, a, b)
    assert code == 0, out
    assert out.strip() == "FACTS: equal"


def test_changed_number_fails_and_is_reported(tmp_path, capsys):
    """Check changed number fails and is reported."""
    a = _w(tmp_path, "a.md", "Period is 25.0 ns here.\n")
    b = _w(tmp_path, "b.md", "Period is 26.0 ns here.\n")
    code, out = _run(capsys, a, b)
    assert code == 1
    assert "DIFF\tnum\t25.0 ns\tbefore=1\tafter=0\tsection=(file)" in out
    assert "DIFF\tnum\t26.0 ns\tbefore=0\tafter=1" in out


def test_dropped_unit_fails(tmp_path, capsys):
    """Check dropped unit fails."""
    a = _w(tmp_path, "a.md", "Slack is 571 MHz.\n")
    b = _w(tmp_path, "b.md", "Slack is 571.\n")
    code, out = _run(capsys, a, b)
    assert code == 1
    assert "571 MHz" in out


def test_number_spacing_and_thousands_separators_are_normalised():
    """Check number spacing and thousands separators are normalised."""
    assert _facts("md", "571MHz and 1,079,867 cycles") == _facts("md", "571 MHz and 1079867 cycles")
    assert _facts("md", "99.95%") == _facts("md", "99.95 %")


def test_number_forms_recognised():
    """Check number forms recognised."""
    f = _facts("md", "WNS -727.37 ps, addr 0x2000_8000, literal 8'hFF, 99.95 %, count 42.")
    keys = {tok for (kind, tok) in f if kind == "num"}
    assert keys == {"-727.37 ps", "0x2000_8000", "8'hFF", "99.95 %", "42"}


def test_number_inside_identifier_is_not_a_number():
    """Check number inside identifier is not a number."""
    f = _facts("md", "Core rv32i and signal x86 only.")
    assert not [t for (k, t) in f if k == "num"]


def test_modal_change_fails(tmp_path, capsys):
    """Check modal change fails."""
    a = _w(tmp_path, "a.md", "You must reset the block.\n")
    b = _w(tmp_path, "b.md", "You should reset the block.\n")
    code, out = _run(capsys, a, b)
    assert code == 1
    assert "DIFF\tmodal\tmust\tbefore=1\tafter=0" in out


def test_must_not_is_distinct_from_must(tmp_path, capsys):
    """Check must not is distinct from must."""
    a = _w(tmp_path, "a.md", "It must not stall. Always check; never skip; do not ignore.\n")
    f = _facts("md", Path(a).read_text(encoding="utf-8"))
    assert {t for (k, t) in f if k == "modal"} == {"must not", "always", "never", "do not"}
    assert ("modal", "must") not in f


def test_changed_cref_target_fails(tmp_path, capsys):
    """Check changed cref target fails."""
    a = _w(tmp_path, "a.tex", "See \\cref{sec:alpha} for details.\n")
    b = _w(tmp_path, "b.tex", "See \\cref{sec:beta} for details.\n")
    code, out = _run(capsys, a, b)
    assert code == 1
    assert "lbl\tsec:alpha" in out and "lbl\tsec:beta" in out


def test_label_lists_are_split_and_reordering_is_equal():
    """Check label lists are split and reordering is equal."""
    a = _facts("tex", "\\cref{a,b} and \\label{x}")
    b = _facts("tex", "\\cref{b, a} and \\label{x}")
    assert a == b
    assert ("lbl", "a") in a and ("lbl", "x") in a


def test_edit_inside_listing_fails(tmp_path, capsys):
    """Check edit inside listing fails."""
    base = "Text.\n\\begin{lstlisting}\nassign y = a & b;\n\\end{lstlisting}\n"
    a = _w(tmp_path, "a.tex", base)
    b = _w(tmp_path, "b.tex", base.replace("a & b", "a | b"))
    code, out = _run(capsys, a, b)
    assert code == 1
    assert "DIFF\tcode\t" in out
    same = _w(tmp_path, "c.tex", base.replace("assign y", "assign   y"))
    assert _run(capsys, a, same)[0] == 0  # whitespace-insensitive


def test_edit_inside_markdown_fence_fails(tmp_path, capsys):
    """Check edit inside markdown fence fails."""
    a = _w(tmp_path, "a.md", "Text.\n\n```sv\nx = 1;\n```\n")
    b = _w(tmp_path, "b.md", "Text.\n\n```sv\nx = 2;\n```\n")
    assert _run(capsys, a, b)[0] == 1


def test_markdown_before_against_latex_after_same_facts(tmp_path, capsys):
    """Check markdown before against latex after same facts."""
    md = (
        "# Timing\n\nThe period is 25.0 ns and `grant_o` must stay registered, "
        "see [guide](https://example.org/g).\n\n1. First 3 steps\n\n"
        "```sv\nx = 1;\n```\n"
    )
    tex = (
        "\\section{Timing}\nThe period is 25.0 ns and \\texttt{grant\\_o} must stay "
        "registered, see \\href{https://example.org/g}{guide}.\n"
        "\\begin{enumerate}\n\\item First 3 steps\n\\end{enumerate}\n"
        "\\begin{lstlisting}\nx = 1;\n\\end{lstlisting}\n"
    )
    code, out = _run(capsys, _w(tmp_path, "a.md", md), _w(tmp_path, "b.tex", tex))
    assert code == 0, out


def test_list_and_heading_numbers_are_ignored():
    """Check list and heading numbers are ignored."""
    assert _facts("md", "## 3.2 Heading\n\n1. item\n2. item\n") == _facts(
        "md", "## Heading\n\n- item\n- item\n"
    )


def test_layout_arguments_are_not_facts():
    """Check layout arguments are not facts."""
    a = _facts("tex", "\\vspace{12pt}\\begin{tabular}{ll} x \\end{tabular}")
    b = _facts("tex", "\\vspace{3pt}\\begin{tabular}{lr} x \\end{tabular}")
    assert a == b


def test_identifiers_and_reference_ids():
    """Check identifiers and reference ids."""
    f = _facts(
        "md",
        "See rtl/soc/pmu.sv and snake_case, Mr. Smith e.g. here, GH #244, PR #280, "
        "RUN_2026-09-17_20-41-11 and `inline_code`.",
    )
    ids = {t for (k, t) in f if k == "id"}
    assert {"rtl/soc/pmu.sv", "snake_case", "inline_code"} <= ids
    assert "e.g" not in ids
    refs = {t for (k, t) in f if k == "ref"}
    assert refs == {"GH #244", "PR #280", "RUN_2026-09-17_20-41-11"}


def test_changed_inline_code_fails(tmp_path, capsys):
    """Check changed inline code fails."""
    a = _w(tmp_path, "a.md", "Use `foo_bar` here.\n")
    b = _w(tmp_path, "b.md", "Use `foo_baz` here.\n")
    assert _run(capsys, a, b)[0] == 1


def test_bead_macro_equals_inline_code():
    """Check bead macro equals inline code."""
    assert _facts("tex", "bead \\bead{ew3} done") == _facts("md", "bead `ew3` done")


def test_by_section_reports_the_right_section(tmp_path, capsys):
    """Check by section reports the right section."""
    a = _w(
        tmp_path,
        "a.tex",
        "\\section{One}\\label{sec:one}\nValue 5 ns.\n"
        "\\section{Two}\\label{sec:two}\nValue 7 ns.\n",
    )
    b = _w(
        tmp_path,
        "b.tex",
        "\\section{One}\\label{sec:one}\nValue 5 ns.\n"
        "\\section{Two}\\label{sec:two}\nValue 8 ns.\n",
    )
    code, out = _run(capsys, a, b, "--by-section")
    assert code == 1
    assert "num\t7 ns\tbefore=1\tafter=0\tsection=sec:two" in out
    assert "section=sec:one" not in out


def test_by_section_reports_added_and_removed_sections(tmp_path, capsys):
    """Check by section reports added and removed sections."""
    a = _w(tmp_path, "a.md", "# Alpha\n\nx 1\n\n# Beta\n\ny 2\n")
    b = _w(tmp_path, "b.md", "# Alpha\n\nx 1\n\n# Gamma\n\ny 2\n")
    code, out = _run(capsys, a, b, "--by-section")
    assert code == 1
    assert "SECTION-REMOVED\tBeta" in out
    assert "SECTION-ADDED\tGamma" in out


def test_whole_file_mode_ignores_section_moves_but_by_section_does_not(tmp_path, capsys):
    """Check whole file mode ignores section moves but by section does not."""
    a = _w(tmp_path, "a.md", "# A\n\nv 1 ns\n\n# B\n\nv 2 ns\n")
    b = _w(tmp_path, "b.md", "# A\n\nv 2 ns\n\n# B\n\nv 1 ns\n")
    assert _run(capsys, a, b)[0] == 0
    assert _run(capsys, a, b, "--by-section")[0] == 1


def test_fenced_heading_is_not_a_section():
    """Check fenced heading is not a section."""
    secs = cf.sections_of("md", "# Real\n\n```\n# not a heading\n```\n", True)
    assert list(secs) == ["(start)", "Real"]


def test_before_can_be_a_git_revision(tmp_path, monkeypatch, capsys):
    """Check before can be a git revision."""
    if shutil.which("git") is None:
        pytest.skip("git is not available")

    def git(*args: str) -> None:
        """Helper: git."""
        subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, stdin=subprocess.DEVNULL
        )

    git("init", "-q")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    git("config", "commit.gpgsign", "false")
    git("config", "core.autocrlf", "false")
    monkeypatch.chdir(tmp_path)
    _w(tmp_path, "d.md", "Period 25 ns.\n")
    git("add", "d.md")
    git("commit", "-q", "-m", "x")
    _w(tmp_path, "d.md", "The period is 25 ns.\n")
    code, out = _run(capsys, "HEAD:d.md", "d.md")
    assert code == 0, out
    _w(tmp_path, "d.md", "The period is 30 ns.\n")
    assert _run(capsys, "HEAD:d.md", "d.md")[0] == 1


def test_exit_2_on_bad_input(tmp_path, capsys):
    """Check exit 2 on bad input."""
    ok = _w(tmp_path, "a.md", "x\n")
    assert cf.main(["--before", str(tmp_path / "nope.md"), "--after", ok]) == 2
    txt = _w(tmp_path, "a.txt", "x\n")
    assert cf.main(["--before", txt, "--after", ok]) == 2
    assert cf.main(["--before", "no-such-rev:a.md", "--after", ok]) == 2
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        cf.main(["--before", ok])
    assert exc.value.code == 2
