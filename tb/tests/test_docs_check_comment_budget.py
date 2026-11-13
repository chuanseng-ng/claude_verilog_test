"""Unit tests for tools/docs/check_comment_budget.py (synthetic trees only)."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import check_comment_budget as cb  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error


def rules(path: str, text: str) -> dict[str, int]:
    """Helper: rules."""
    out: dict[str, int] = {}
    for f in cb.analyse(path, text):
        out[f.rule] = out.get(f.rule, 0) + 1
    return out


def sizes(path: str, text: str, rule: str) -> list[int]:
    """Helper: sizes."""
    return [f.size for f in cb.analyse(path, text) if f.rule == rule]


def sv_header(n: int) -> str:
    """Helper: sv header."""
    return "".join(f"// line {i}\n" for i in range(n)) + "module m; endmodule\n"


def write(root: Path, rel: str, text: str) -> None:
    """Helper: write."""
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


# ----------------------------------------------------------------------------- size budgets
def test_rtl_header_at_limit_ok_and_one_over_flagged() -> None:
    """Check rtl header at limit ok and one over flagged."""
    assert "hdr" not in rules("rtl/a.sv", sv_header(40))
    assert sizes("rtl/a.sv", sv_header(41), "hdr") == [41]


def test_header_ignores_blank_lines_and_ends_at_first_code() -> None:
    """Check header ignores blank lines and ends at first code."""
    text = "// a\n\n// b\n\nmodule m;\n// late\nendmodule\n"
    assert not rules("rtl/a.sv", text)
    lines = cb.scan_c_like(text)
    assert cb.leading_block(lines)[0] == 2


def test_block_comment_header_counts_each_line() -> None:
    """Check block comment header counts each line."""
    text = "/*\n * a\n * b\n */\nmodule m; endmodule\n"
    assert cb.leading_block(cb.scan_c_like(text))[0] == 4


def test_rtl_inline_block_at_limit_ok_one_over_flagged() -> None:
    """Check rtl inline block at limit ok one over flagged."""

    def body(n: int) -> str:
        """Helper: body."""
        return "module m;\n" + "".join(f"  // c{i}\n" for i in range(n)) + "  wire w;\nendmodule\n"

    assert "blk" not in rules("rtl/a.sv", body(8))
    assert sizes("rtl/a.sv", body(9), "blk") == [9]


def test_pragma_lines_neither_count_nor_break_a_block() -> None:
    """Check pragma lines neither count nor break a block."""
    mid = "  // verilator lint_off WIDTH\n"
    ok = "module m;\n" + "  // a\n" * 4 + mid + "  // b\n" * 4 + "  wire w;\nendmodule\n"
    assert "blk" not in rules("rtl/a.sv", ok)  # 8 counted lines, pragma ignored
    over = "module m;\n" + "  // a\n" * 5 + mid + "  // b\n" * 4 + "  wire w;\nendmodule\n"
    assert sizes("rtl/a.sv", over, "blk") == [9]  # pragma does not split the run


def test_pragma_header_line_not_counted() -> None:
    """Check pragma header line not counted."""
    text = "// synopsys translate_off\n" + sv_header(40)
    assert "hdr" not in rules("rtl/a.sv", text)


def test_blk_and_hdr_apply_only_to_rtl() -> None:
    """Check blk and hdr apply only to rtl."""
    assert not rules("tb/a.sv", sv_header(60))


def test_python_docstring_with_leading_comment_counts() -> None:
    """Check python docstring with leading comment counts."""

    def py(comment_lines: int, doc_lines: int) -> str:
        """Helper: py."""
        doc = '"""' + "x\n" * (doc_lines - 1) + '"""\n'
        return "#!/usr/bin/env python3\n" + "# c\n" * comment_lines + doc + "x = 1\n"

    assert "doc" not in rules("tb/t.py", py(5, 20))  # 25 total
    assert sizes("tb/t.py", py(6, 20), "doc") == [26]
    assert "doc" not in rules("tools/t.py", py(6, 40))  # only tb/ and sim/


def test_pnr_constraint_header_limit() -> None:
    """Check pnr constraint header limit."""
    assert "hdr" not in rules("pnr/a.sdc", "# c\n" * 25 + "create_clock\n")
    assert sizes("pnr/a.sdc", "# c\n" * 26 + "create_clock\n", "hdr") == [26]
    assert not rules("tb/a.sdc", "# c\n" * 30 + "x\n")


def test_makefile_run_limit_and_recipe_comments() -> None:
    """Check makefile run limit and recipe comments."""
    assert "mk" not in rules("tb/Makefile", "# c\n" * 6 + "all:\n\techo hi\n")
    assert sizes("tb/Makefile", "# c\n" * 7 + "all:\n\techo hi\n", "mk") == [7]
    recipe = "all:\n" + "\t# shell comment\n" * 10
    assert "mk" not in rules("tb/Makefile", recipe)


def test_workflow_run_limit() -> None:
    """Check workflow run limit."""
    assert "wf" not in rules(".github/workflows/a.yml", "# c\n" * 5 + "on: push\n")
    assert sizes(".github/workflows/a.yml", "# c\n" * 6 + "on: push\n", "wf") == [6]


# ----------------------------------------------------------------------------- content rules
@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("bead ckc", "bead"),
        ("see (bead j41m.6)", "bead"),
        ("Bead 3ogd closed", "bead"),
        ("claude_verilog_test-abc.1", "bead"),
        ("bead gcd", "bead"),
        ("bead a1", "bead"),
        ("bead abc.2", "bead"),
        ("bead was.1", "bead"),
        ("bead `ewz`", "bead"),
        ("fixed in PR #132", "ghpr"),
        ("GH#12 tracks it", "ghpr"),
        ("per epic #99", "ghpr"),
        ("RUN_2026-09-17_20-41-11", "run"),
        ("updated 2026-10-10", "date"),
        ("period 25.0 ns", "meas"),
        ("a 1.5 GHz clock", "meas"),
        ("see rtl/soc/pmu.sv:123", "fline"),
    ],
)
def test_content_rule_positive(text: str, rule: str) -> None:
    """Check content rule positive."""
    assert rule in cb.content_rules(text)


@pytest.mark.parametrize(
    ("text", "rule"),
    [
        ("a bead of solder", "bead"),
        ("bead sequence", "bead"),
        ("the bead was cracked", "bead"),
        ("bead the", "bead"),
        ("each bead nan", "bead"),
        ("bead and bead for", "bead"),
        ("beads are small", "bead"),
        ("bead has", "bead"),
        ("the pull request", "ghpr"),
        ("issue #1", "ghpr"),
        ("RUN_ID is set", "run"),
        ("version 2.0.0", "date"),
        ("25.0 ns  measured-ok", "meas"),
        ("100 nsec", "meas"),
        ("see rtl/soc/pmu.sv", "fline"),
    ],
)
def test_content_rule_negative(text: str, rule: str) -> None:
    """Check content rule negative."""
    assert rule not in cb.content_rules(text)


def test_content_rules_only_look_at_comments() -> None:
    """Check content rules only look at comments."""
    sv = 'module m; string s = "PR #132 25 ns"; // fine\nendmodule\n'
    assert not rules("tb/a.sv", sv)
    assert rules("tb/a.sv", "// PR #132\n") == {"ghpr": 1}
    assert rules("tb/a.py", 'x = "PR #132"\n# PR #132\n') == {"ghpr": 1}
    assert rules("tb/a.py", '"""See bead ckc."""\n') == {"bead": 1}


# ----------------------------------------------------------------------------- exclusions
def test_exclusions_honoured(tmp_path: Path) -> None:
    """Check exclusions honoured."""
    noisy = "// PR #132\n"
    write(tmp_path, "rtl/a.sv", noisy)
    write(tmp_path, "pnr/commercial/x.sdc", "# PR #132\n")
    write(tmp_path, "micro_p/rtl/b.sv", noisy)
    write(tmp_path, "rtl/c.json", '{"a": "PR #132"}')
    write(tmp_path, "tb/d.md", "PR #132\n")
    write(tmp_path, "rtl/gen.sv", "// GENERATED by tool\n" + noisy)
    write(tmp_path, "rtl/gen2.sv", "// x\n// DO NOT EDIT\n" + noisy)
    write(tmp_path, "tb/e.py", "import x\nprint(__doc__)\n# PR #132\n")
    write(tmp_path, "tools/f.py", "# PR #132\n")
    found = {f.path for f in cb.collect(tmp_path)}
    assert found == {"rtl/a.sv"}


# ----------------------------------------------------------------------------- baseline logic
def _tree(tmp_path: Path, n_hdr: int = 41) -> tuple[Path, Path]:
    """Helper: tree."""
    write(tmp_path, "rtl/a.sv", sv_header(n_hdr))
    return tmp_path, tmp_path / "base.txt"


def _run(root: Path, base: Path, *extra: str) -> int:
    """Helper: run."""
    return int(cb.main(["--root", str(root), "--baseline", str(base), *extra]))


def test_update_baseline_then_exact_run_passes(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Check update baseline then exact run passes."""
    root, base = _tree(tmp_path)
    assert _run(root, base, "--update-baseline", "--allow-growth") == 0
    assert "rtl/a.sv | hdr | 1 | 41" in base.read_text(encoding="utf-8")
    assert _run(root, base) == 0
    assert "OK" in capsys.readouterr().out


def test_regression_exits_1_and_lists_lines(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Check regression exits 1 and lists lines."""
    root, base = _tree(tmp_path)
    _run(root, base, "--update-baseline", "--allow-growth")
    write(root, "rtl/a.sv", sv_header(45))
    capsys.readouterr()
    assert _run(root, base) == 1
    out = capsys.readouterr().out
    assert "REGRESSION" in out and "rtl/a.sv:1: hdr size 45" in out


def test_new_finding_without_entry_is_regression(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Check new finding without entry is regression."""
    root, base = _tree(tmp_path)
    _run(root, base, "--update-baseline", "--allow-growth")
    write(root, "rtl/b.sv", "// PR #5\nmodule b; endmodule\n")
    capsys.readouterr()
    assert _run(root, base) == 1
    assert "no baseline entry" in capsys.readouterr().out


def test_generous_baseline_fails_with_tighten_message(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Check generous baseline fails with tighten message."""
    root, base = _tree(tmp_path, 45)
    _run(root, base, "--update-baseline", "--allow-growth")
    write(root, "rtl/a.sv", sv_header(41))
    capsys.readouterr()
    assert _run(root, base) == 1
    out = capsys.readouterr().out
    assert "baseline can be tightened" in out
    assert "- rtl/a.sv | hdr | 1 | 45" in out and "+ rtl/a.sv | hdr | 1 | 41" in out


def test_fixed_file_leaves_stale_entry(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Check fixed file leaves stale entry."""
    root, base = _tree(tmp_path)
    _run(root, base, "--update-baseline", "--allow-growth")
    write(root, "rtl/a.sv", sv_header(10))
    capsys.readouterr()
    assert _run(root, base) == 1
    assert "baseline can be tightened" in capsys.readouterr().out
    assert _run(root, base, "--update-baseline") == 0  # shrinking is allowed
    assert "rtl/a.sv" not in base.read_text(encoding="utf-8")
    assert _run(root, base) == 0


def test_update_refuses_growth_without_flag(tmp_path: Path) -> None:
    """Check update refuses growth without flag."""
    root, base = _tree(tmp_path)
    _run(root, base, "--update-baseline", "--allow-growth")
    before = base.read_text(encoding="utf-8")
    write(root, "rtl/a.sv", sv_header(50))
    assert _run(root, base, "--update-baseline") == 1
    assert base.read_text(encoding="utf-8") == before
    assert _run(root, base, "--update-baseline", "--allow-growth") == 0


def test_file_arguments_restrict_the_check(tmp_path: Path) -> None:
    """Check file arguments restrict the check."""
    root, base = _tree(tmp_path)
    write(root, "rtl/b.sv", sv_header(41))
    _run(root, base, "--update-baseline", "--allow-growth")
    write(root, "rtl/b.sv", sv_header(60))  # regression in b only
    assert _run(root, base, "rtl/a.sv") == 0
    assert _run(root, base, "rtl/b.sv") == 1
    assert _run(root, base) == 1


def test_report_always_exits_0(tmp_path: Path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Check report always exits 0."""
    root, base = _tree(tmp_path)
    assert _run(root, base, "--report") == 0  # no baseline needed
    out = capsys.readouterr().out
    assert "Totals per rule" in out and "rtl/a.sv" in out


def test_missing_baseline_is_a_setup_error(tmp_path: Path) -> None:
    """Check missing baseline is a setup error."""
    root, base = _tree(tmp_path)
    assert _run(root, base) == 2


def test_malformed_baseline_is_a_setup_error(tmp_path: Path) -> None:
    """Check malformed baseline is a setup error."""
    root, base = _tree(tmp_path)
    base.write_text("rtl/a.sv | hdr | many |\n", encoding="utf-8")
    assert _run(root, base) == 2
