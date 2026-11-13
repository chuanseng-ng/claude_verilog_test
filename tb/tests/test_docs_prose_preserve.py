"""Unit tests for tools/docs/prose_preserve.py."""

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import prose_preserve as pp  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error


def _w(root: Path, name: str, text: str) -> str:
    """Helper: w."""
    p = root / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return str(p)


def _run(capsys, *argv: str) -> tuple[int, str]:  # type: ignore[no-untyped-def]
    """Helper: run."""
    code = pp.main(list(argv))
    return code, capsys.readouterr().out


def _words(text: str) -> list[str]:
    """Helper: words."""
    return [t for t, _ in pp.tokenize_text(text)]


MD = """# Bus evaluation

The **arbiter** is _round-robin_ and `grant_o` is registered.

* First item with a [link](https://example.com/a_b) here
* Second item

1. Step one
2. Step two

| Name | Value |
|------|:-----:|
| clk  | 571 MHz |
| rst_n | active low |
"""

TEX = r"""\chapter{Bus evaluation}\label{bus-evaluation}
The \textbf{arbiter} is \emph{round-robin} and \texttt{grant\_o} is registered.
\begin{itemize}
\item First item with a \href{https://example.com/a_b}{link} here
\item Second item
\end{itemize}
\begin{enumerate}
\item Step one
\item Step two
\end{enumerate}
\begin{longtable}[]{@{}ll@{}}
\toprule\noalign{}
Name & Value \\
\midrule\noalign{}
clk & 571 MHz \\
rst\_n & active low \\
\bottomrule\noalign{}
\end{longtable}
"""


def test_markdown_to_latex_equivalent_is_preserved(tmp_path, capsys):
    """Check markdown to latex equivalent is preserved."""
    src = _w(tmp_path, "a.md", MD)
    dst = _w(tmp_path, "a.tex", TEX)
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 0, out
    assert "0 missing in 0 runs" in out


def test_final_line_format(tmp_path, capsys):
    """Check final line format."""
    src = _w(tmp_path, "a.md", "alpha beta gamma\n")
    dst = _w(tmp_path, "a.tex", "alpha beta gamma\n")
    _, out = _run(capsys, "--from", src, "--to", dst)
    assert out.strip().splitlines()[-1] == "PRESERVED: 3 source tokens, 0 missing in 0 runs"


def test_dropped_sentence_reported_with_line(tmp_path, capsys):
    """Check dropped sentence reported with line."""
    src = _w(
        tmp_path,
        "a.md",
        "First line stays here.\n\nThe quick brown fox jumps over the lazy dog.\n\nLast line.\n",
    )
    dst = _w(tmp_path, "a.tex", "First line stays here.\n\nLast line.\n")
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 1
    assert "a.md:3:" in out
    assert "quick brown fox" in out
    assert "missing in" in out.splitlines()[-1]


def test_dropped_single_rare_word_reported(tmp_path, capsys):
    """Check dropped single rare word reported."""
    src = _w(tmp_path, "a.md", "The arbiter grants requests in strict rotation.\n")
    dst = _w(tmp_path, "a.tex", "The arbiter grants requests in rotation.\n")
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 1
    assert ">>> strict <<<" in out
    assert "1 missing in 1 runs" in out


def test_dropped_common_word_is_not_hidden_by_same_word_elsewhere(tmp_path, capsys):
    """Check dropped common word is not hidden by same word elsewhere."""
    src = _w(tmp_path, "a.md", "alpha beta gamma delta the epsilon zeta eta theta iota\n")
    dst = _w(
        tmp_path,
        "a.tex",
        "alpha beta gamma delta epsilon zeta eta theta iota\n\nthe end of the file\n",
    )
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 1
    assert ">>> the <<<" in out


def test_reordered_units_ok_but_missing_text_is_not(tmp_path, capsys):
    """Check reordered units ok but missing text is not."""
    a = _w(tmp_path, "a.md", "Alpha unit has some distinct words about clocks.\n")
    b = _w(tmp_path, "b.md", "Bravo unit speaks about resets and fabrics.\n")
    both = _w(
        tmp_path,
        "d.tex",
        "Bravo unit speaks about resets and fabrics.\n\n"
        "Alpha unit has some distinct words about clocks.\n",
    )
    code, _ = _run(capsys, "--from", a, b, "--to", both)
    assert code == 0
    only_b = _w(tmp_path, "e.tex", "Bravo unit speaks about resets and fabrics.\n")
    code, out = _run(capsys, "--from", a, b, "--to", only_b)
    assert code == 1
    assert "a.md:1:" in out
    assert "b.md" not in out.replace("PRESERVED", "")


def test_latex_escapes_match_markdown(tmp_path, capsys):
    """Check latex escapes match markdown."""
    src = _w(tmp_path, "a.md", "Use foo\\_bar at 100% load, R&D and issue #5 cost $3.\n")
    dst = _w(tmp_path, "a.tex", r"Use foo\_bar at 100\% load, R\&D and issue \#5 cost \$3." + "\n")
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 0, out


def test_emoji_against_project_macros(tmp_path, capsys):
    """Check emoji against project macros."""
    src = _w(
        tmp_path, "a.md", "\u26a0\ufe0f caveat \u2705 done \u274c failed \u23f8\ufe0f paused\n"
    )
    dst = _w(tmp_path, "a.tex", "\\warn caveat \\ok done \\bad failed \\hold paused\n")
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 0, out


def test_section_sign_em_dash_and_symbols(tmp_path, capsys):
    """Check section sign em dash and symbols."""
    src = _w(
        tmp_path, "a.md", "See \u00a77 \u2014 timing \u2265 5 \u00b5s, 3 \u00d7 faster \u2192 ok\n"
    )
    dst = _w(tmp_path, "a.tex", "See section 7 --- timing >= 5 us, 3 x faster -> ok\n")
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 0, out


def test_fenced_code_contents_must_appear(tmp_path, capsys):
    """Check fenced code contents must appear."""
    md = "Intro text.\n\n```sv\nassign y = a & b;\n```\n"
    src = _w(tmp_path, "a.md", md)
    ok = _w(
        tmp_path,
        "ok.tex",
        "Intro text.\n\\begin{lstlisting}[language=Verilog]\n"
        "assign y = a & b;\n\\end{lstlisting}\n",
    )
    assert _run(capsys, "--from", src, "--to", ok)[0] == 0
    bad = _w(tmp_path, "bad.tex", "Intro text.\n")
    code, out = _run(capsys, "--from", src, "--to", bad)
    assert code == 1
    assert "assign" in out


def test_fence_markers_themselves_are_not_prose():
    """Check fence markers themselves are not prose."""
    toks = _words(pp.norm_markdown("```systemverilog\nx\n```\n"))
    assert toks == ["x"]


def test_allow_drop_exempts_listed_phrase(tmp_path, capsys):
    """Check allow drop exempts listed phrase."""
    src = _w(tmp_path, "a.md", "Keep this. Remove the obsolete banner text. Keep that.\n")
    dst = _w(tmp_path, "a.tex", "Keep this. Keep that.\n")
    assert _run(capsys, "--from", src, "--to", dst)[0] == 1
    allow = _w(tmp_path, "allow.txt", "Remove the obsolete banner text.\n")
    code, out = _run(capsys, "--from", src, "--to", dst, "--allow-drop", allow)
    assert code == 0, out


def test_min_run_suppresses_short_runs(tmp_path, capsys):
    """Check min run suppresses short runs."""
    src = _w(tmp_path, "a.md", "aaa bbb ccc ddd eee fff ggg zzz hhh iii jjj kkk lll mmm\n")
    dst = _w(tmp_path, "a.tex", "aaa bbb ccc ddd eee fff ggg hhh iii jjj kkk lll mmm\n")
    assert _run(capsys, "--from", src, "--to", dst)[0] == 1
    assert _run(capsys, "--from", src, "--to", dst, "--min-run", "2")[0] == 0


def test_link_text_and_url_both_required(tmp_path, capsys):
    """Check link text and url both required."""
    src = _w(tmp_path, "a.md", "See [the guide](https://example.org/guide) now.\n")
    dst = _w(tmp_path, "a.tex", "See the guide now.\n")
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 1
    assert "https://example.org/guide" in out
    ok = _w(tmp_path, "b.tex", "See \\href{https://example.org/guide}{the guide} now.\n")
    assert _run(capsys, "--from", src, "--to", ok)[0] == 0


def test_html_comment_and_tags_are_not_prose():
    """Check html comment and tags are not prose."""
    toks = _words(pp.norm_markdown("a<br>b <!-- hidden\nmore --> c <div class='x'>d</div>\n"))
    assert toks == ["a", "b", "c", "d"]


def test_latex_structure_commands_vanish():
    """Check latex structure commands vanish."""
    tex = (
        "\\section{Intro}\\label{sec:intro}\\index{x}"
        "See \\cref{sec:intro} and \\phantomsection end.\n"
    )
    assert _words(pp.norm_latex(tex)) == ["intro", "see", "and", "end"]


def test_latex_comments_dropped_but_escaped_percent_kept():
    """Check latex comments dropped but escaped percent kept."""
    toks = _words(pp.norm_latex("kept 50\\% value % trailing comment words\nnext\n"))
    assert toks == ["kept", "50", "value", "next"]


def test_latex_symbol_commands():
    """Check latex symbol commands."""
    tex = r"a\textbackslash{}b \textasciitilde{} \ldots \textless{}x\textgreater{} A~B"
    folded = pp.norm_latex(tex)
    for piece in ("a\\b", "~", "...", "<x>", "A B"):
        assert piece in folded


def test_latex_verbatim_body_is_raw():
    """Check latex verbatim body is raw."""
    tex = r"\begin{lstlisting}" + "\n" + r"x_y = 100% a\b" + "\n" + r"\end{lstlisting}"
    assert _words(pp.norm_latex(tex)) == ["x_y", "100", "a\\b"]


def test_signed_number_keeps_sign_and_internal_punctuation():
    """Check signed number keeps sign and internal punctuation."""
    assert _words("WNS -727.37 ps at 0x2000_8000, a.b (x).") == [
        "wns",
        "-727.37",
        "ps",
        "at",
        "0x2000_8000",
        "a.b",
        "x",
    ]


def test_decorative_rules_yield_no_words():
    """Check decorative rules yield no words."""
    assert _words("==== ---- #### **** ~~~~ ----") == []
    assert _words("// ======== Section ========"[2:]) == ["section"]


def test_directory_destination_is_searched_recursively(tmp_path, capsys):
    """Check directory destination is searched recursively."""
    src = _w(tmp_path, "a.md", "Alpha words here. Beta words there.\n")
    _w(tmp_path, "book/ch1/one.tex", "Alpha words here.\n")
    _w(tmp_path, "book/ch2/two.tex", "Beta words there.\n")
    _w(tmp_path, "book/notes.txt", "ignored file\n")
    code, out = _run(capsys, "--from", src, "--to", str(tmp_path / "book"))
    assert code == 0, out


def test_exit_2_on_missing_files_and_bad_specs(tmp_path, capsys):
    """Check exit 2 on missing files and bad specs."""
    ok = _w(tmp_path, "ok.tex", "x\n")
    assert pp.main(["--from", str(tmp_path / "nope.md"), "--to", ok]) == 2
    src = _w(tmp_path, "a.md", "x\n")
    assert pp.main(["--from", src, "--to", str(tmp_path / "nope.tex")]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert pp.main(["--from", src, "--to", str(empty)]) == 2
    assert pp.main(["--from", "diff:HEAD", "--to", ok]) == 2
    capsys.readouterr()
    with pytest.raises(SystemExit) as exc:
        pp.main(["--from", src])
    assert exc.value.code == 2


def test_latex_footnote_does_not_glue_words():
    """Check latex footnote does not glue words."""
    assert _words(pp.norm_latex("run)\\footnote{This note} end\n")) == [
        "run",
        "this",
        "note",
        "end",
    ]


def test_markdown_literal_underscores_survive_but_pairs_are_stripped():
    """Check markdown literal underscores survive but pairs are stripped."""
    toks = _words(pp.norm_markdown("grid_dim_{x} and _emph_ and snake_case_name\n"))
    assert toks == ["grid_dim_{x", "and", "emph", "and", "snake_case_name"]


def test_multiline_code_span_and_nested_image_link():
    """Check multiline code span and nested image link."""
    md = "see `a b\nc_d*e` and [![alt](img.svg)](https://x.org/y)\n"
    toks = _words(pp.norm_markdown(md))
    assert toks == ["see", "a", "b", "c_d*e", "and", "alt", "img.svg", "https://x.org/y"]


def test_pandoc_style_inline_code_escapes_are_undone():
    """Check pandoc style inline code escapes are undone."""
    tex = r"\passthrough{\lstinline!a\_b\\c \~f \{x\}!}"
    assert _words(pp.norm_latex(tex)) == ["a_b\\c", "f", "x"]


def test_same_document_anchor_links_keep_text_only():
    """Check same document anchor links keep text only."""
    assert _words(pp.norm_markdown("see [below](#sec-x) now\n")) == ["see", "below", "now"]


# ------------------------------------------------------------ diff: source


def _repo(tmp_path: Path, monkeypatch) -> "callable":  # type: ignore[valid-type]
    """Helper: repo."""
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
    return git


def _commit(git, tmp_path: Path, name: str, text: str) -> None:  # type: ignore[no-untyped-def]
    """Helper: commit."""
    _w(tmp_path, name, text)
    git("add", name)
    git("commit", "-q", "-m", "x")


def test_diff_source_systemverilog(tmp_path, monkeypatch, capsys):
    """Check diff source systemverilog."""
    git = _repo(tmp_path, monkeypatch)
    old = (
        "// Arbiter grants the oldest request first.\n"
        "module m;\n"
        "  /* Multi line\n   * block explains reset behaviour. */\n"
        "  wire a; // keep this note\n"
        "endmodule\n"
    )
    _commit(git, tmp_path, "m.sv", old)
    _w(tmp_path, "m.sv", "module m;\n  wire a; // keep this note\nendmodule\n")
    spec = "diff:HEAD:m.sv"
    dst = _w(tmp_path, "d.tex", "Arbiter grants the oldest request first.\n")
    code, out = _run(capsys, "--from", spec, "--to", dst)
    assert code == 1
    assert "multi line block explains reset behaviour" in out
    assert "keep this note" not in out
    both = _w(
        tmp_path,
        "e.tex",
        "Arbiter grants the oldest request first. Multi line block explains reset behaviour.\n",
    )
    code, out = _run(capsys, "--from", spec, "--to", both)
    assert code == 0, out


def test_diff_source_python_comment_and_docstring(tmp_path, monkeypatch, capsys):
    """Check diff source python comment and docstring."""
    git = _repo(tmp_path, monkeypatch)
    old = (
        '"""Module docstring about quantum flux."""\n'
        "def f():\n"
        '    """Function docstring about gizmo."""\n'
        "    # comment about widgets\n"
        "    return 1\n"
    )
    _commit(git, tmp_path, "p.py", old)
    _w(tmp_path, "p.py", "def f():\n    return 1\n")
    dst = _w(tmp_path, "d.tex", "Nothing relevant.\n")
    code, out = _run(capsys, "--from", "diff:HEAD:p.py", "--to", dst)
    assert code == 1
    for word in ("quantum flux", "gizmo", "widgets"):
        assert word in out
    ok = _w(
        tmp_path,
        "ok.tex",
        "Module docstring about quantum flux. Function docstring about gizmo. "
        "comment about widgets\n",
    )
    assert _run(capsys, "--from", "diff:HEAD:p.py", "--to", ok)[0] == 0


def test_diff_source_sdc_and_makefile_rules(tmp_path, monkeypatch, capsys):
    """Check diff source sdc and makefile rules."""
    git = _repo(tmp_path, monkeypatch)
    old = "# Clock period is tight\nset_false_path -from a\n#### \n# ====\n"
    _commit(git, tmp_path, "c.sdc", old)
    _w(tmp_path, "c.sdc", "set_false_path -from a\n")
    dst = _w(tmp_path, "d.tex", "unrelated\n")
    code, out = _run(capsys, "--from", "diff:HEAD:c.sdc", "--to", dst)
    assert code == 1
    assert "3 missing in 1 runs" not in out
    assert ">>> clock period is tight <<<" in out
    # Makefile: TAB-led recipe lines are not comment text.
    mk = "# build rule note\n\t# shell comment\ntarget:\n\techo hi\n"
    assert [t for t, _ in pp._tokens_of(pp.comments_hash(mk, makefile=True))] == [
        "build",
        "rule",
        "note",
    ]


def test_diff_source_absolute_path_and_new_file_missing(tmp_path, monkeypatch, capsys):
    """Check diff source absolute path and new file missing."""
    git = _repo(tmp_path, monkeypatch)
    _commit(git, tmp_path, "gone.sv", "// vanished comment words\nmodule x; endmodule\n")
    (tmp_path / "gone.sv").unlink()
    dst = _w(tmp_path, "d.tex", "vanished comment words\n")
    assert _run(capsys, "--from", f"diff:HEAD:{tmp_path / 'gone.sv'}", "--to", dst)[0] == 0


def test_diff_source_unknown_revision_or_type_is_error(tmp_path, monkeypatch):
    """Check diff source unknown revision or type is error."""
    git = _repo(tmp_path, monkeypatch)
    _commit(git, tmp_path, "m.sv", "// c\n")
    dst = _w(tmp_path, "d.tex", "x\n")
    assert pp.main(["--from", "diff:no-such-rev:m.sv", "--to", dst]) == 2
    _commit(git, tmp_path, "data.bin", "x\n")
    assert pp.main(["--from", "diff:HEAD:data.bin", "--to", dst]) == 2


def test_sv_comment_markers_inside_strings_are_not_comments():
    """Check sv comment markers inside strings are not comments."""
    src = 'string s = "http://x /* not a comment */ y"; // real note\n'
    assert [t for t, _ in pp._tokens_of(pp.comments_sv(src))] == ["real", "note"]
    src2 = 'a = "esc \\" // still string"; /* block */\n'
    assert [t for t, _ in pp._tokens_of(pp.comments_sv(src2))] == ["block"]


def test_sv_block_comment_continuation_stars_and_lines():
    """Check sv block comment continuation stars and lines."""
    src = "/*\n * first line\n * second line\n */\nwire a; // third\n"
    pieces = [(t.strip(), ln) for t, ln in pp.comments_sv(src) if t.strip()]
    assert pieces == [("first line", 2), ("second line", 3), ("third", 5)]


def test_python_comments_use_tokenizer_not_strings():
    """Check python comments use tokenizer not strings."""
    src = 's = "# not a comment"\n# real comment\n'
    assert [t for t, _ in pp._tokens_of(pp.comments_py(src))] == ["real", "comment"]


def test_moderate_size_runs_quickly(tmp_path, capsys):
    """Check moderate size runs quickly."""
    words = [f"w{i % 977}x{i % 13}" for i in range(20000)]
    text = " ".join(words) + "\n"
    src = _w(tmp_path, "big.md", text)
    dst = _w(tmp_path, "big.tex", text)
    t0 = time.time()
    code, out = _run(capsys, "--from", src, "--to", dst)
    assert code == 0, out
    assert time.time() - t0 < 30


def _tex_tokens(text: str) -> list[str]:
    """Helper: tokens of LaTeX text."""
    return [t for t, _ in pp.tokenize_text(pp.norm_latex(text))]


def _md_tokens(text: str) -> list[str]:
    """Helper: tokens of Markdown text."""
    return [t for t, _ in pp.tokenize_text(pp.norm_markdown(text))]


def test_pictograph_table_agrees_on_both_sides():
    """Check each row of marks.tsv gives the same token on the Markdown and LaTeX side."""
    rows = pp.load_marks()
    assert len(rows) >= 30
    for cp, tex, token in rows:
        md_side = _md_tokens(f"x {chr(cp)} y")
        assert md_side == ["x", token.lower(), "y"], (hex(cp), md_side)
        assert _tex_tokens(f"x {tex} y") == ["x", token.lower(), "y"], tex
        assert _tex_tokens(f"x {chr(cp)} y") == ["x", token.lower(), "y"]


def test_pictograph_table_matches_the_class():
    """Check cvtmacros.sty prints every pictograph of marks.tsv as the same macro."""
    sty = (REPO / "docs" / "manual" / "common" / "cvtmacros.sty").read_text(encoding="utf-8")
    declared = {
        m.group(1): m.group(2) for m in re.finditer(r"^\\newunicodechar\{(.)\}\{(.*)\}$", sty, re.M)
    }
    for cp, tex, _token in pp.load_marks():
        assert declared.get(chr(cp)) == tex, hex(cp)
    for _cp, tex, _token in pp.load_marks():
        name = re.match(r"\\([A-Za-z]+)", tex)
        assert name is not None
        if name.group(1) != "textbf":
            assert f"\\newcommand{{\\{name.group(1)}}}" in sty


def test_new_marks_and_variation_selector():
    """Check the new marks fold to their tokens and U+FE0F vanishes."""
    assert _md_tokens("a \U0001f7e1 b ℹ️ c ❓ d") == ["a", "partial", "b", "note", "c", "open", "d"]
    assert _tex_tokens(r"a \partialmark{} b \notemark{} c \openmark{} d \wip{}") == [
        "a",
        "partial",
        "b",
        "note",
        "c",
        "open",
        "d",
        "wip",
    ]


def test_github_and_pr_references_print_their_words():
    """Check GH and PR macros give the same tokens as the Markdown reference text."""
    assert _tex_tokens(r"see \ghref{12} and \prref{259}'s fix, post-\prref{113})") == _md_tokens(
        "see GH #12 and PR #259's fix, post-PR #113)"
    )
    assert _tex_tokens(r"\ghref{105}/\#106") == _md_tokens("GH #105/#106")


def test_bead_and_run_identifiers_round_trip():
    """Check bead and run macros keep their visible words."""
    assert _tex_tokens(r"bead \bead{ma7} in \runid{RUN_2026-09-17_20-41-11}.") == _md_tokens(
        "bead `ma7` in `RUN_2026-09-17_20-41-11`."
    )


def test_code_spans_joined_by_punctuation_split_the_same_way():
    """Check a/b between code spans gives the same tokens in Markdown and LaTeX."""
    assert _md_tokens("`u99`/`ma7`, `a`s and (`x`)") == _tex_tokens(
        r"\code{u99}/\code{ma7}, \code{a}s and (\code{x})"
    )


def test_caret_and_break_hints_do_not_change_words():
    """Check 2\\^{} and \\allowbreak{} are invisible to the word stream."""
    assert _md_tokens("2^k and GPU_BLOCK_DIM_Y a/b/c") == _tex_tokens(
        r"2\^{}k and GPU\_\allowbreak{}BLOCK\_\allowbreak{}DIM\_Y a/\allowbreak{}b/c"
    )


def test_link_to_a_markdown_file_keeps_only_its_text():
    """Check a local Markdown link and a link with its own file name give no extra words."""
    assert _md_tokens("see [the plan](../PLAN.md#goals) now") == ["see", "the", "plan", "now"]
    assert _md_tokens("[`a.md`](a.md) x") == ["a.md", "x"]
    assert _md_tokens("[`rtl-checks.yml`](../../.github/workflows/rtl-checks.yml)") == [
        "github",
        "workflows",
        "rtl-checks.yml",
    ]
    # a link to a source file keeps both its text and its target
    assert _md_tokens("[the core](rtl/cpu/core.sv)") == ["the", "core", "rtl", "cpu", "core.sv"]


def test_deleting_a_word_or_a_sentence_is_still_reported(tmp_path, capsys):
    """Check the changed tokenisation still reports a deleted word and a deleted sentence."""
    md = _w(tmp_path, "a.md", "The arbiter grants one `req_i` per cycle. Spare words stay here.\n")
    head = "The arbiter grants one \\code{req\\_i} per"
    full = _w(tmp_path, "full.tex", head + " cycle. Spare words stay here.\n")
    code, out = _run(capsys, "--from", md, "--to", full)
    assert code == 0, out
    no_word = _w(tmp_path, "w.tex", head + ". Spare words stay here.\n")
    code, out = _run(capsys, "--from", md, "--to", no_word)
    assert code == 1 and ">>> cycle <<<" in out
    no_sentence = _w(tmp_path, "s.tex", "The arbiter grants one \\code{req\\_i} per cycle.\n")
    code, out = _run(capsys, "--from", md, "--to", no_sentence)
    assert code == 1 and "spare words stay here" in out


def test_origsec_counts_as_the_heading_number(tmp_path, capsys):
    """Check a heading that moved its number to origsec loses no token."""
    md = _w(tmp_path, "a.md", "## 7.3 Citation line\n\nBody words here.\n")
    good = _w(
        tmp_path,
        "good.tex",
        "\\section{Citation line}\\label{x:y}\\origsec{7.3}\nBody words here.\n",
    )
    code, out = _run(capsys, "--from", md, "--to", good)
    assert code == 0, out
    wrapped = _w(
        tmp_path,
        "wrapped.tex",
        "\\section{\\texorpdfstring{Citation\nline}{Citation line}}\\label{x:y}\\origsec{7.3}\n"
        "Body words here.\n",
    )
    code, out = _run(capsys, "--from", md, "--to", wrapped)
    assert code == 0, out
    stripped = _w(tmp_path, "bad.tex", "\\section{Citation line}\\label{x:y}\nBody words here.\n")
    code, out = _run(capsys, "--from", md, "--to", stripped)
    assert code == 1 and "7.3" in out
