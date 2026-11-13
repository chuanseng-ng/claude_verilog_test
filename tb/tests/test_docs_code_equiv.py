"""Tests for tools/docs/code_equiv.py: the comment-only change proof."""

# pylint: disable=missing-function-docstring

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import code_equiv as ce  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error


def equiv(lang: str, a: str, b: str) -> bool:
    return ce.compare_texts(lang, a, b) is None


# ------------------------------------------------------------------ SystemVerilog


def test_sv_comment_only_change_is_equivalent() -> None:
    a = "module m; // top\n  assign a = b; /* x */\nendmodule\n"
    b = "module m;\n  assign a = b;\nendmodule\n"
    assert equiv("sv", a, b)


def test_sv_whitespace_reflow_is_equivalent() -> None:
    assert equiv("sv", "assign a=b+1;", "assign   a = b +\n  1 ;")


def test_sv_code_change_detected() -> None:
    diff = ce.compare_texts("sv", "assign a = b;", "assign a = c;")
    assert diff is not None and diff.left is not None and diff.right is not None
    assert diff.left.text == "b" and diff.right.text == "c"


def test_sv_comment_marker_in_string_is_not_a_comment() -> None:
    a = 'initial $display("a // b /* c");\n'
    b = 'initial $display("a // B /* c");\n'
    assert not equiv("sv", a, b)
    assert equiv("sv", a, a.replace("initial", "initial // note\n"))


def test_sv_string_escaped_quote() -> None:
    src = 'x = "a\\" // still string";\n'
    assert not equiv("sv", src, src.replace("still", "other"))


@pytest.mark.parametrize(
    "pragma",
    ["// verilator lint_off WIDTH", "/* verilator coverage_off */", "// synopsys translate_off"],
)
def test_sv_pragma_removal_is_change(pragma: str) -> None:
    with_p = f"{pragma}\nassign a = b;\n"
    assert not equiv("sv", with_p, "assign a = b;\n")


def test_sv_pragma_edit_is_change() -> None:
    a = "// verilator lint_off WIDTH\nassign a = b;\n"
    b = "// verilator lint_off UNUSED\nassign a = b;\n"
    assert not equiv("sv", a, b)


def test_sv_pragma_whitespace_and_case_normalised() -> None:
    a = "//   verilator   lint_off  WIDTH\nx;\n"
    b = "/*verilator lint_off WIDTH*/ x;\n"
    assert equiv("sv", a, b)


def test_sv_multiline_block_comment() -> None:
    a = "a; /* one\n two\n three */ b;\n"
    assert equiv("sv", a, "a; b;\n")


def test_sv_unterminated_block_comment_is_parse_error() -> None:
    with pytest.raises(ce.ParseError):
        ce.compare_texts("sv", "a; /* oops", "a;")


def test_sv_define_body_change_detected() -> None:
    a = "`define W 8 // width\nwire [`W-1:0] x;\n"
    b = "`define W 16 // width\nwire [`W-1:0] x;\n"
    assert not equiv("sv", a, b)


def test_sv_define_continuation_and_newline_boundary() -> None:
    a = "`define M(x) \\\n  (x + 1)\nfoo;\n"
    assert equiv("sv", a, a.replace("foo;", "foo; // c"))
    # the define body ends at the newline, so moving a token across it is a change
    assert not equiv("sv", "`define A 1\nB\n", "`define A 1 B\n")


def test_sv_attribute_removal_is_change() -> None:
    assert not equiv("sv", "(* keep *) wire w;\n", "wire w;\n")
    assert equiv("sv", "(* keep *) wire w;\n", "(*  keep  *) wire w;\n")


def test_sv_event_star_is_not_an_attribute() -> None:
    assert equiv("sv", "always @(*) a = b; // c\n", "always @(*) a = b;\n")


@pytest.mark.parametrize("lit", ["8'hFF", "'0", "4'sb1010_x", "32'd10", "'1", "8 'h0F"])
def test_sv_literals_lex_as_one_unit(lit: str) -> None:
    assert [t.text for t in ce.lex_sv(f"x = {lit};")] == ["x", "=", lit, ";"]


def test_sv_assignment_pattern_apostrophe() -> None:
    assert [t.text for t in ce.lex_sv("x = '{default: 0};")][2:4] == ["'{", "default"]


# ------------------------------------------------------------------------ Python


def test_py_docstring_only_change_is_equivalent() -> None:
    a = 'def f():\n    """Old doc."""\n    return 1\n'
    b = 'def f():\n    """New, longer doc."""\n    return 1\n'
    assert equiv("python", a, b)


def test_py_module_and_class_docstring_removal() -> None:
    a = '"""mod"""\nclass C:\n    """cls"""\n    x = 1\n'
    assert equiv("python", a, "class C:\n    x = 1\n")


def test_py_docstring_change_with_dunder_doc_is_change() -> None:
    a = '"""Old."""\nprint(__doc__)\n'
    b = '"""New."""\nprint(__doc__)\n'
    assert not equiv("python", a, b)


def test_py_non_docstring_string_is_code() -> None:
    assert not equiv("python", "x = 'a'\n", "x = 'b'\n")


def test_py_ordinary_comment_change_is_equivalent() -> None:
    assert equiv("python", "x = 1  # old\n# lone\ny = 2\n", "x = 1\ny = 2  # new\n")


def test_py_noqa_removal_is_change() -> None:
    assert not equiv("python", "import os  # noqa: F401\n", "import os\n")


@pytest.mark.parametrize(
    "pragma", ["type: ignore[x]", "pragma: no cover", "fmt: skip", "ruff: noqa"]
)
def test_py_other_pragmas_are_kept(pragma: str) -> None:
    assert not equiv("python", f"x = 1  # {pragma}\n", "x = 1\n")


def test_py_noqa_inside_string_is_not_a_pragma() -> None:
    assert equiv("python", "x = '# noqa'\n", "x = '# noqa'  # extra\n")


def test_py_syntax_error_is_parse_error() -> None:
    with pytest.raises(ce.ParseError):
        ce.compare_texts("python", "def (:\n", "x = 1\n")


# --------------------------------------------------------------------------- Tcl


def test_tcl_comment_line_removal_is_equivalent() -> None:
    a = "# header\nset a 1\n  # mid\nset b 2\n"
    assert equiv("tcl", a, "set a 1\nset b 2\n")


def test_tcl_semicolon_hash_is_comment_but_bare_hash_is_arg() -> None:
    assert equiv("tcl", "set a 1 ;# note\n", "set a 1\n")
    assert not equiv("tcl", "set a 1 # note\n", "set a 1\n")


def test_tcl_backslash_continued_comment() -> None:
    a = "# first \\\n  second \\\n  third\nset a 1\n"
    assert equiv("tcl", a, "set a 1\n")
    # without the backslash the next line is code
    assert not equiv("tcl", "# first\nsecond\nset a 1\n", "set a 1\n")


def test_tcl_upf_check_comment_is_code() -> None:
    a = "# upf-check aon\ncreate_power_domain PD\n"
    assert not equiv("tcl", a, "create_power_domain PD\n")
    assert equiv("tcl", a, "#   upf-check   aon\ncreate_power_domain PD\n")


def test_tcl_hash_in_quoted_string_is_not_comment() -> None:
    a = 'puts "a # b"\n'
    assert not equiv("tcl", a, 'puts "a # c"\n')


def test_tcl_comment_after_open_brace() -> None:
    a = "foreach x {a b} { # per item\n  puts $x\n}\n"
    b = "foreach x {a b} {\n  puts $x\n}\n"
    assert equiv("tcl", a, b)


def test_tcl_code_change_detected() -> None:
    assert not equiv("tcl", "set a [get_ports {clk}]\n", "set a [get_ports {clk2}]\n")


def test_tcl_unterminated_string_is_parse_error() -> None:
    with pytest.raises(ce.ParseError):
        ce.compare_texts("tcl", 'puts "abc\n', "puts abc\n")


# ---------------------------------------------------------------- cfg / Makefile


def test_cfg_comments_and_blank_lines_ignored() -> None:
    assert equiv("cfg", "# c\nA  1 2\n\nB 3\n", "A 1 2\nB 3\n")
    assert not equiv("cfg", "A 1 2\n", "A 1 3\n")


def test_make_recipe_line_starting_with_hash_is_code() -> None:
    a = "all:\n\t# echo hi\n\t@# quiet\n\tcc x\n"
    assert not equiv("make", a, "all:\n\tcc x\n")


def test_make_trailing_comment_on_assignment_is_code() -> None:
    assert not equiv("make", "CC = gcc # compiler\n", "CC = gcc\n")


def test_make_comment_line_removal_is_equivalent() -> None:
    a = "# top\n\nCC = gcc\n\n# rule\n\nall:\n\tcc x\n# end\n"
    b = "CC = gcc\n\nall:\n\tcc x\n"
    assert equiv("make", a, b)


def test_make_continued_comment_line() -> None:
    a = "# a \\\n  b \\\n  c\nCC = gcc\n"
    assert equiv("make", a, "CC = gcc\n")


def test_make_define_block_keeps_hash_lines() -> None:
    a = "define BODY\n# kept\nx\nendef\n"
    assert not equiv("make", a, "define BODY\nx\nendef\n")


# ---------------------------------------------------------------- YAML / shell


def test_yaml_comment_only_change_equivalent_value_change_detected() -> None:
    a = "# top\na: 1\nb:\n  - x  # note\n  - y\n"
    assert equiv("yaml", a, "a: 1\nb: [x, y]\n")
    assert not equiv("yaml", a, "a: 2\nb: [x, y]\n")
    assert not equiv("yaml", a, "a: 1\nb: [y, x]\n")


def test_shell_comment_removal_equivalent_shebang_kept() -> None:
    a = "#!/bin/sh\n# note\necho hi   \n\n\n# end\necho bye\n"
    assert equiv("shell", a, "#!/bin/sh\necho hi\n\necho bye\n")
    assert not equiv("shell", a, "echo hi\n\necho bye\n")


def test_shell_shellcheck_directive_kept() -> None:
    a = "# shellcheck disable=SC2086\necho $x\n"
    assert not equiv("shell", a, "echo $x\n")


# ------------------------------------------------------------------------- CLI


@pytest.mark.parametrize(
    ("name", "lang"),
    [
        ("a.sv", "sv"), ("a.vh", "sv"), ("a.py", "python"), ("a.sdc", "tcl"), ("a.upf", "tcl"),
        ("a.cfg", "cfg"), ("Makefile", "make"), ("x/GNUmakefile", "make"), ("r.mk", "make"),
        ("a.yml", "yaml"), ("a.sh", "shell"), ("a.json", None), ("README.md", None),
    ],
)  # fmt: skip
def test_detect_lang(name: str, lang: str | None) -> None:
    assert ce.detect_lang(name) == lang


def _pair(tmp_path: Path, name: str, a: str, b: str) -> list[str]:
    (tmp_path / "old").mkdir(exist_ok=True)
    (tmp_path / "new").mkdir(exist_ok=True)
    (tmp_path / "old" / name).write_text(a, encoding="utf-8")
    (tmp_path / "new" / name).write_text(b, encoding="utf-8")
    return ["--files-pair", str(tmp_path / "old" / name), str(tmp_path / "new" / name)]


def test_cli_exit_0_equivalent(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = _pair(tmp_path, "a.sv", "a; // x\n", "a;\n")
    assert ce.main([*args, "--lang", "auto"]) == 0
    assert "EQUIV" in capsys.readouterr().out


def test_cli_exit_1_changed_reports_lines(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    args = _pair(tmp_path, "a.sv", "a;\nb;\n", "a;\nc;\n")
    assert ce.main(args) == 1
    out = capsys.readouterr().out
    assert "CHANGED" in out and "(sv)" in out
    assert "base (line 2): b" in out and "head (line 2): c" in out


def test_cli_exit_2_json_unsupported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    args = _pair(tmp_path, "a.json", "{}", "{}")
    assert ce.main(args) == 2
    assert "UNSUPPORTED" in capsys.readouterr().out


def test_cli_exit_2_parse_error(tmp_path: Path) -> None:
    assert ce.main(_pair(tmp_path, "a.py", "def (:\n", "x = 1\n")) == 2


def test_cli_exit_2_unknown_lang(tmp_path: Path) -> None:
    assert ce.main([*_pair(tmp_path, "a.txt", "a", "a"), "--lang", "cobol"]) == 2


def test_cli_lang_override(tmp_path: Path) -> None:
    args = _pair(tmp_path, "a.txt", "x # c\n", "x\n")
    assert ce.main([*args, "--lang", "shell"]) == 1


def test_cli_usage_error_is_exit_2() -> None:
    with pytest.raises(SystemExit) as exc:
        ce.main(["only-one-rev"])
    assert exc.value.code == 2


def test_cli_script_exit_code_via_subprocess(tmp_path: Path) -> None:
    args = _pair(tmp_path, "a.tcl", "set a 1 ;# c\n", "set a 1\n")
    script = str(REPO / "tools" / "docs" / "code_equiv.py")
    res = subprocess.run(
        [sys.executable, script, *args], capture_output=True, stdin=subprocess.DEVNULL, check=False
    )
    assert res.returncode == 0
    args = _pair(tmp_path, "a.tcl", "set a 1\n", "set a 2\n")
    res = subprocess.run(
        [sys.executable, script, *args], capture_output=True, stdin=subprocess.DEVNULL, check=False
    )
    assert res.returncode == 1


# ------------------------------------------------------------- pragma strictness


@pytest.mark.parametrize(
    "prose",
    [
        "Synthesis (__pnr__ defined by LibreLane Yosys steps): directly instantiates",
        "Synthesis had mapped the mux",
        "SYNTHESIS NOTE: split into lanes",
        "Coverage of the deferred scope",
        "coverage is part of the scope",
        "Spyglass SignedUnsignedExpr-ML: waived",
        "verilator is a simulator",
        "Verilator lint_off WIDTH",
        "pragma is overloaded here",
        "tessent Scan flow",
    ],
)
def test_sv_prose_comment_is_not_a_pragma(prose: str) -> None:
    assert equiv("sv", f"// {prose}\nassign a = b;\n", "assign a = b;\n")
    assert equiv("sv", f"/* {prose} */ assign a = b;\n", "assign a = b;\n")


@pytest.mark.parametrize(
    "pragma",
    [
        "verilator lint_off WIDTH",
        "verilator public_flat_rw",
        "verilator tag foo",
        "verilator coverage_block_off",
        "synopsys translate_off",
        "synthesis full_case parallel_case",
        "pragma protect begin",
        "cadence keep",
        "synopsys synthesis_off",
        "rtl_synthesis off",
        "ambit synthesis off",
        "coverage off",
        "coverage on",
        "translate_off",
        "lint_on",
        "coverage_off",
        "spyglass disable_block SomeRule",
        "spyglass enable",
        "tessent mbist_clock",
        "vcs coverage",
        "cover off",
        "xcelium translate_on",
    ],
)
def test_sv_real_pragma_forms_are_kept(pragma: str) -> None:
    assert not equiv("sv", f"// {pragma}\nassign a = b;\n", "assign a = b;\n")
    assert not equiv("sv", f"/* {pragma} */ assign a = b;\n", "assign a = b;\n")
    assert not equiv("sv", f"//{pragma}\nx;\n", "x;\n")


def test_sv_pragma_word_boundary() -> None:
    assert equiv("sv", "// verilator lint_offish\nx;\n", "x;\n")
    assert equiv("sv", "// coverage onwards\nx;\n", "x;\n")


# ------------------------------------------------------------ git revision mode

GIT = pytest.mark.skipif(shutil.which("git") is None, reason="git not available")


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=True,
    )


def _commit(repo: Path, files: dict[str, str], msg: str) -> None:
    for name, text in files.items():
        f = repo / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(text.encode("utf-8"))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", msg)


@pytest.fixture(name="repo")
def _repo_fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    r = tmp_path / "repo"
    r.mkdir()
    _git(r, "init", "-q")
    _commit(r, {"rtl/m.sv": "assign a = b; // old\n", "notes/x.json": "{}\n"}, "base")
    monkeypatch.chdir(r)
    return r


@GIT
def test_git_comment_only_commit_is_exit_0(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _commit(repo, {"rtl/m.sv": "// header\nassign a = b;\n"}, "comments")
    assert ce.main(["HEAD~1", "HEAD", "rtl/m.sv"]) == 0
    assert "EQUIV rtl/m.sv" in capsys.readouterr().out


@GIT
def test_git_code_change_is_exit_1(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _commit(repo, {"rtl/m.sv": "assign a = c; // old\n"}, "code")
    assert ce.main(["HEAD~1", "HEAD", "rtl/m.sv"]) == 1
    assert "CHANGED rtl/m.sv" in capsys.readouterr().out


@GIT
def test_git_worktree_form(repo: Path) -> None:
    (repo / "rtl" / "m.sv").write_text("assign a = b;\n", encoding="utf-8")
    assert ce.main(["HEAD", "WORKTREE", "rtl/m.sv"]) == 0
    (repo / "rtl" / "m.sv").write_text("assign a = d;\n", encoding="utf-8")
    assert ce.main(["HEAD", "WORKTREE", "rtl/m.sv"]) == 1


@GIT
def test_git_added_and_deleted_file_is_exit_1(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(repo, {"rtl/n.sv": "assign x = y;\n"}, "add")
    assert ce.main(["HEAD~1", "HEAD", "rtl/n.sv"]) == 1
    assert "added" in capsys.readouterr().out
    assert ce.main(["HEAD", "HEAD~1", "rtl/n.sv"]) == 1
    assert "deleted" in capsys.readouterr().out


@GIT
def test_git_no_file_mode_picks_up_changed_files(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(
        repo,
        {"rtl/m.sv": "assign a = b;\n", "notes/x.json": "{ }\n", "Makefile": "all:\n\techo\n"},
        "mixed",
    )
    assert ce.main(["HEAD~1", "HEAD"]) == 1  # Makefile added
    out = capsys.readouterr().out
    assert "EQUIV rtl/m.sv" in out
    assert "CHANGED Makefile" in out
    assert "SKIPPED notes/x.json" in out
    assert "1 skipped" in out


@GIT
def test_git_no_file_mode_skipped_files_do_not_cause_exit_2(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _commit(repo, {"rtl/m.sv": "assign a = b; // new\n", "notes/x.json": "[]\n"}, "c")
    assert ce.main(["HEAD~1", "HEAD"]) == 0
    assert "1 skipped" in capsys.readouterr().out


@GIT
def test_git_explicit_unsupported_file_is_exit_2(repo: Path) -> None:
    _commit(repo, {"notes/x.json": "[]\n"}, "c")
    assert ce.main(["HEAD~1", "HEAD", "notes/x.json"]) == 2


@GIT
def test_git_parse_error_is_exit_2(repo: Path) -> None:
    _commit(repo, {"rtl/m.sv": "assign a = b; /* open\n"}, "bad")
    assert ce.main(["HEAD~1", "HEAD"]) == 2
