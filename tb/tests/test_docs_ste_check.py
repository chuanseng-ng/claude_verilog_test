"""Unit tests for tools/docs/ste_check.py (heuristic STE checker)."""

import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import ste_check as ste  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error

VOCAB = ste.load_vocab()


def run(tmp_path: Path, text: str, name: str = "t.md", header: bool = False):
    """Helper: run."""
    p = tmp_path / name
    p.write_text(text, encoding="utf-8", newline="\n")
    return ste.check_file(p, VOCAB, header, False)


def rules(tmp_path: Path, text: str, name: str = "t.md") -> list[str]:
    """Helper: rules."""
    return [f.rule for f in run(tmp_path, text, name)[0]]


def words(n: int) -> str:
    """Helper: words."""
    return " ".join(["cat"] * n)


def test_vocab_loads_lists():
    """Check vocab loads lists."""
    assert "utilize" in VOCAB.not_approved and "timing" in VOCAB.allowed_ing
    assert "on" in VOCAB.function_words and "the" in VOCAB.function_words


def test_s2_positive_negative(tmp_path):
    """Check s2 positive negative."""
    assert "S2" in rules(tmp_path, f"The {words(26)}.\n")
    assert "S2" not in rules(tmp_path, f"The {words(22)}.\n")


def test_s1_procedural_limit_markdown(tmp_path):
    """Check s1 procedural limit markdown."""
    long_step = f"1. Open the {words(21)}.\n"
    assert "S1" in rules(tmp_path, long_step)
    assert "S1" not in rules(tmp_path, "1. Open the door.\n")


def test_descriptive_22_words_passes_but_fails_in_enumerate(tmp_path):
    """Check descriptive 22 words passes but fails in enumerate."""
    sentence = f"Open the door {words(19)}."
    desc = f"{sentence}\n"
    assert "S1" not in rules(tmp_path, desc, "t.tex") and "S2" not in rules(tmp_path, desc, "t.tex")
    proc = f"\\begin{{enumerate}}\n\\item {sentence}\n\\end{{enumerate}}\n"
    assert "S1" in rules(tmp_path, proc, "t.tex")
    proc2 = f"\\begin{{procedure}}\n\\item {sentence}\n\\end{{procedure}}\n"
    assert "S1" in rules(tmp_path, proc2, "t.tex")
    bullets = f"\\begin{{itemize}}\n\\item {sentence}\n\\end{{itemize}}\n"
    assert "S1" not in rules(tmp_path, bullets, "t.tex")


def test_p1_paragraph_length(tmp_path):
    """Check p1 paragraph length."""
    seven = " ".join(f"Item {i} is here." for i in range(7))
    six = " ".join(f"Item {i} is here." for i in range(6))
    assert "P1" in rules(tmp_path, seven + "\n")
    assert "P1" not in rules(tmp_path, six + "\n")


def test_v1_passive(tmp_path):
    """Check v1 passive."""
    assert "V1" in rules(tmp_path, "The file is written by the tool.\n")
    assert "V1" in rules(tmp_path, "The value was quickly shown.\n")
    assert "V1" not in rules(tmp_path, "The tool writes the file.\n")
    assert "V1" not in rules(tmp_path, "The port is required.\n")
    assert "V1" not in rules(tmp_path, "The clock is unused.\n")


def test_v2_compound_tenses(tmp_path):
    """Check v2 compound tenses."""
    assert "V2" in rules(tmp_path, "The tool has written the file.\n")
    assert "V2" in rules(tmp_path, "The tool will be starting.\n")
    assert "V2" in rules(tmp_path, "The tool is starting.\n")
    assert "V2" not in rules(tmp_path, "The tool writes the file.\n")
    assert "V2" not in rules(tmp_path, "We have a file.\n")


def test_g1_ing_words(tmp_path):
    """Check g1 ing words."""
    assert "G1" in rules(tmp_path, "The testing step is long.\n")
    assert "G1" not in rules(tmp_path, "The timing step is long.\n")
    assert "G1" not in rules(tmp_path, "Use a string during the run.\n")
    assert "G1" not in rules(tmp_path, "The routing step is long.\n")


def test_n1_noun_cluster(tmp_path):
    """Check n1 noun cluster."""
    assert "N1" in rules(tmp_path, "Check the clock domain crossing reset pulse width.\n")
    assert "N1" not in rules(tmp_path, "Check the width of the reset pulse.\n")
    assert "N1" not in rules(tmp_path, "Check the reset pulse width.\n")


def test_n1_multiword_dictionary_terms_removed():
    """Check n1 multiword dictionary terms removed."""
    v = ste.Vocab({}, set(), set(), ["clock domain crossing"], set())
    assert ste.noun_clusters("check clock domain crossing reset now", v) == []
    assert ste.noun_clusters("check alpha beta gamma delta now", v)


def test_w1_not_approved(tmp_path):
    """Check w1 not approved."""
    f = run(tmp_path, "Utilize the tool in order to start.\n")[0]
    msgs = " ".join(x.msg for x in f if x.rule == "W1")
    assert "utilize" in msgs and "use" in msgs and "in order to" in msgs
    assert "W1" not in rules(tmp_path, "Use the tool to start.\n")
    assert "W1" in rules(tmp_path, "The tool performs a check.\n")


def test_w1_abbreviations_listed(tmp_path):
    """Check w1 abbreviations listed."""
    assert "W1" in rules(tmp_path, "Use a tool, e.g. a script.\n")
    assert "W1" in rules(tmp_path, "Use a tool, that is a script, etc. Then stop.\n")


def test_c1_contractions(tmp_path):
    """Check c1 contractions."""
    assert "C1" in rules(tmp_path, "The tool doesn't start.\n")
    assert "C1" in rules(tmp_path, "It's a tool.\n")
    assert "C1" not in rules(tmp_path, "The tool's output is long.\n")


def test_m1_two_instructions(tmp_path):
    """Check m1 two instructions."""
    assert "M1" in rules(tmp_path, "1. Open the door and close the window.\n")
    assert "M1" not in rules(tmp_path, "1. Open the door.\n2. Close the window.\n")
    assert "M1" not in rules(tmp_path, "Open the door and close the window.\n")


def test_x1_only_with_pedantic(tmp_path):
    """Check x1 only with pedantic."""
    p = tmp_path / "t.md"
    p.write_text("1. The door opens.\n", encoding="utf-8")
    assert "X1" not in [f.rule for f in ste.check_file(p, VOCAB, False, False)[0]]
    assert "X1" in [f.rule for f in ste.check_file(p, VOCAB, False, True)[0]]


def test_z1_waiver_without_reason(tmp_path):
    """Check z1 waiver without reason."""
    f = rules(tmp_path, "<!-- ste-ok: -->\nUtilize it.\n")
    assert "Z1" in f and "W1" in f


def test_waiver_with_reason_suppresses_next_sentence(tmp_path):
    """Check waiver with reason suppresses next sentence."""
    f = rules(tmp_path, "<!-- ste-ok: quoted standard -->\nUtilize it.\n\nUtilize it again.\n")
    assert f.count("W1") == 1
    tex = "% ste-ok: legacy\nUtilize it.\n"
    assert rules(tmp_path, tex, "t.tex") == []


def test_latex_skips_listings_record_code_and_macros(tmp_path):
    """Check latex skips listings record code and macros."""
    tex = (
        "\\begin{lstlisting}\nUtilize it in order to run.\n\\end{lstlisting}\n"
        "\\begin{record}\nUtilize it in order to run.\n\\end{record}\n"
        "\\begin{relocated}{x.sv}\nUtilize it.\n\\end{relocated}\n"
        "Run \\code{utilize_the_testing_step} and \\src{rtl/utilize.sv}.\n"
        "% Utilize in a comment.\n"
        "The value is $a + b$.\n"
    )
    assert rules(tmp_path, tex, "t.tex") == []


def test_latex_reference_token_does_not_split_sentence(tmp_path):
    """Check latex reference token does not split sentence."""
    tex = "See \\cref{tm:ch:x}. Then stop.\n"
    ex = ste.extract_tex(tex.split("\n"))
    assert ste.split_sentences(ex.paras[0].text) == ["See REF.", "Then stop."]


def test_latex_table_cells_threshold(tmp_path):
    """Check latex table cells threshold."""
    short = "\\begin{tabular}{ll}\nUtilize & it \\\\\n\\end{tabular}\n"
    long_cell = (
        "\\begin{tabular}{ll}\nUtilize the tool in order to start now & x \\\\\n\\end{tabular}\n"
    )
    assert rules(tmp_path, short, "t.tex") == []
    assert "W1" in rules(tmp_path, long_cell, "t.tex")


def test_latex_title_length_only(tmp_path):
    """Check latex title length only."""
    assert rules(tmp_path, "\\section{Utilize the testing step}\n", "t.tex") == []
    assert "S2" in rules(tmp_path, f"\\section{{{words(30)}}}\n", "t.tex")


def test_markdown_skips_code_tables_comments(tmp_path):
    """Check markdown skips code tables comments."""
    md = (
        "```\nUtilize it in order to run.\n```\n\n"
        "| Utilize the tool in order to start | x |\n|---|---|\n| a | b |\n\n"
        "<!-- Utilize in a comment -->\n\n"
        "Use `utilize` here.\n"
    )
    assert rules(tmp_path, md) == []


def test_markdown_managed_blocks_skipped(tmp_path):
    """Check markdown managed blocks skipped."""
    md = (
        "<!-- BEGIN generated -->\nUtilize it.\n<!-- END generated -->\n\n"
        "<!-- rtk-instructions v2 -->\nUtilize it.\n<!-- /rtk-instructions -->\n\n"
        "Utilize it.\n"
    )
    f = run(tmp_path, md)[0]
    assert [x.line for x in f if x.rule == "W1"] == [9]


def test_sentence_splitter_abbreviations_decimals_files():
    """Check sentence splitter abbreviations decimals files."""
    s = ste.split_sentences("Use e.g. a tool. The value is 3.5 ns. Open file.name.txt now. Done.")
    assert s == ["Use e.g. a tool.", "The value is 3.5 ns.", "Open file.name.txt now.", "Done."]
    assert ste.split_sentences("Version v1.2.3 is out. Next one.") == [
        "Version v1.2.3 is out.",
        "Next one.",
    ]
    assert len(ste.split_sentences("See etc. and more. Then stop.")) == 2


def test_done_marker_makes_findings_exit_1(tmp_path, capsys):
    """Check done marker makes findings exit 1."""
    p = tmp_path / "a.tex"
    p.write_text("% ste: done\n\\chapter{A}\nUtilize it.\n", encoding="utf-8")
    assert ste.main([str(p)]) == 1
    assert "[marked]" in capsys.readouterr().out


def test_done_marker_after_chapter_limits_region(tmp_path):
    """Check done marker after chapter limits region."""
    lines = ["\n"] * 12
    text = "".join(lines) + "\\chapter{A}\n% ste: done\nUtilize it.\n\\chapter{B}\nUtilize it.\n"
    p = tmp_path / "a.tex"
    p.write_text(text, encoding="utf-8")
    findings, marked = ste.check_file(p, VOCAB, False, False)
    hits = [ste.in_marked(f, marked) for f in findings if f.rule == "W1"]
    assert hits == [True, False]


def test_unmarked_findings_exit_0_unless_all(tmp_path, capsys):
    """Check unmarked findings exit 0 unless all."""
    p = tmp_path / "a.md"
    p.write_text("Utilize it.\n", encoding="utf-8")
    assert ste.main([str(p)]) == 0
    assert ste.main(["--all", str(p)]) == 1
    assert ste.main(["--all", "--strict-marked", str(p)]) == 0
    assert "summary: W1=1" in capsys.readouterr().out


def test_markdown_done_marker(tmp_path):
    """Check markdown done marker."""
    p = tmp_path / "a.md"
    p.write_text("<!-- ste: done -->\n\nUtilize it.\n", encoding="utf-8")
    assert ste.main([str(p)]) == 1


def test_tsv_format(tmp_path, capsys):
    """Check tsv format."""
    p = tmp_path / "a.md"
    p.write_text("Utilize it.\n", encoding="utf-8")
    ste.main(["--format", "tsv", str(p)])
    row = capsys.readouterr().out.splitlines()[0].split("\t")
    assert row[1] == "1" and row[2] == "W1" and row[4] == "Utilize it."


def test_header_mode_sv_and_python(tmp_path):
    """Check header mode sv and python."""
    sv = "// Utilize the bus.\n// It starts now.\n\nmodule m; // Utilize here\nendmodule\n"
    f, _ = run(tmp_path, sv, "m.sv", header=True)
    assert [x.rule for x in f] == ["W1"] and f[0].line == 1
    py = '"""Utilize the bus.\n\nUsage text.\n"""\nx = 1  # Utilize later\n'
    f, _ = run(tmp_path, py, "m.py", header=True)
    assert [x.rule for x in f] == ["W1"]
    clean = "# Start the bus.\nimport os\n# Utilize later\n"
    assert run(tmp_path, clean, "n.py", header=True)[0] == []


def test_header_mode_ignores_shebang_and_decoration(tmp_path):
    """Check header mode ignores shebang and decoration."""
    sh = "#!/bin/sh\n# ====\n# Utilize it.\n# ====\necho hi\n"
    f, _ = run(tmp_path, sh, "s.sh", header=True)
    assert [x.rule for x in f] == ["W1"]


def test_directory_input_and_exit_2(tmp_path, capsys):
    """Check directory input and exit 2."""
    d = tmp_path / "docs"
    d.mkdir()
    (d / "a.md").write_text("Fine text.\n", encoding="utf-8")
    (d / "b.tex").write_text("Fine text.\n", encoding="utf-8")
    (d / "c.txt").write_text("Utilize it.\n", encoding="utf-8")
    assert ste.main([str(d)]) == 0
    assert "no findings" in capsys.readouterr().out
    assert ste.main([str(tmp_path / "missing.md")]) == 2
    empty = tmp_path / "empty"
    empty.mkdir()
    assert ste.main([str(empty)]) == 2
    with pytest.raises(SystemExit) as e:
        ste.main([])
    assert e.value.code == 2


def test_finding_text_is_shortened(tmp_path, capsys):
    """Check finding text is shortened."""
    p = tmp_path / "a.md"
    p.write_text("Utilize " + "word " * 60 + ".\n", encoding="utf-8")
    ste.main([str(p)])
    out = capsys.readouterr().out.splitlines()
    sent = [ln for ln in out if ln.startswith("    ")][0].strip()
    assert len(sent) <= 120 and sent.endswith("...")
