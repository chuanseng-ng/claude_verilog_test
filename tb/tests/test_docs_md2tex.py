"""Unit tests for tools/docs/md2tex.py (needs pandoc; skipped when it is absent)."""

import re
import shutil
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import md2tex  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error

needs_pandoc = pytest.mark.skipif(shutil.which("pandoc") is None, reason="pandoc not installed")

TRACKED = ("rtl/soc/soc_top.sv", "pnr/Makefile", "docs/b.md")


@pytest.fixture(autouse=True)
def _tracked(monkeypatch):
    """Helper:  tracked."""
    monkeypatch.setattr(md2tex, "tracked_files", lambda root: TRACKED)


def conv(tmp_path: Path, text: str, *, path_map: str | None = None, **kw):
    """Helper: conv."""
    md = tmp_path / "docs" / "a.md"
    md.parent.mkdir(exist_ok=True)
    md.write_text(text, encoding="utf-8")
    pm = None
    if path_map is not None:
        pm = tmp_path / "map.tsv"
        pm.write_text("old_path\tnew_file\tlabel\n" + path_map, encoding="utf-8")
    out = tmp_path / "out" / "a.tex"
    args = {"book": "cr", "kind": "inv", "slug": "a", "out": out, "root": tmp_path, "path_map": pm}
    args.update(kw)
    code, warns = md2tex.convert(md, **args)
    assert code == 0, warns
    return out.read_text(encoding="utf-8"), out, warns


@needs_pandoc
def test_first_heading_is_chapter_with_label(tmp_path):
    """Check first heading is chapter with label."""
    tex, _, _ = conv(tmp_path, "# Title\n\ntext\n\n## Part One\n")
    assert "\\chapter{Title}\\label{cr:inv:a}" in tex
    assert "\\section{Part One}\\label{cr:inv:a:part-one}" in tex


@needs_pandoc
def test_section_level_option(tmp_path):
    """Check section level option."""
    tex, _, _ = conv(tmp_path, "# Title\n\n## Sub\n", level="section")
    assert "\\section{Title}\\label{cr:inv:a}" in tex
    assert "\\subsection{Sub}" in tex


@needs_pandoc
def test_duplicate_headings_get_unique_labels(tmp_path):
    """Check duplicate headings get unique labels."""
    tex, _, _ = conv(tmp_path, "# T\n\n## Same\n\n## Same\n\n## Same\n")
    labels = re.findall(r"\\label\{([^}]*)\}", tex)
    assert len(labels) == len(set(labels)) == 4


@needs_pandoc
def test_no_hypertarget_and_label_follows_command(tmp_path):
    """Check no hypertarget and label follows command."""
    tex, _, _ = conv(tmp_path, "# T\n\n## Sec\n\ntext\n")
    assert "hypertarget" not in tex
    assert re.search(r"\\section\{Sec\}\\label\{", tex)


@needs_pandoc
def test_deep_headings_become_paragraph(tmp_path):
    """Check deep headings become paragraph."""
    tex, _, _ = conv(tmp_path, "# T\n\n## A\n\n### B\n\n#### C\n\n##### D\n\n###### E\n")
    assert "\\subsubsection{C}" in tex
    assert "\\paragraph{D}" in tex
    assert "\\paragraph{E}" in tex
    assert "\\subparagraph" not in tex


@needs_pandoc
def test_section_numbers_kept_and_sidecar(tmp_path):
    """Check section numbers kept and sidecar."""
    md = "# 1. Top\n\n## 7. Results\n\n## §5 Confirmation\n\n## 14.10 Scrub\n\n## Plain\n"
    tex, out, _ = conv(tmp_path, md)
    assert "\\section{7. Results}" in tex and "\\section{§5 Confirmation}" in tex
    rows = [r.split("\t") for r in Path(str(out) + ".sections.tsv").read_text("utf-8").splitlines()]
    assert rows[0] == ["number", "label", "title"]
    got = {r[0]: r[1] for r in rows[1:]}
    assert got["7"] == "cr:inv:a:7-results"
    assert got["5"] == "cr:inv:a:5-confirmation"
    assert got["14.10"] == "cr:inv:a:1410-scrub"
    assert "1" in got and len(got) == 4


@needs_pandoc
def test_link_to_mapped_md_becomes_cref(tmp_path):
    """Check link to mapped md becomes cref."""
    tex, _, _ = conv(
        tmp_path, "# T\n\nSee [the plan](b.md) now.\n", path_map="docs/b.md\tx\tds:ch:b\n"
    )
    assert "the plan (\\cref{ds:ch:b})" in tex


@needs_pandoc
def test_link_anchor_resolves_to_sublabel(tmp_path):
    """Check link anchor resolves to sublabel."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "b.md").write_text("# B\n\n## Some Heading\n", encoding="utf-8")
    tex, _, _ = conv(
        tmp_path,
        "# T\n\n[x](b.md#some-heading) and [y](b.md#nope)\n",
        path_map="docs/b.md\tx\tds:ch:b\n",
    )
    assert "\\cref{ds:ch:b:some-heading}" in tex
    assert "\\cref{ds:ch:b}" in tex


@needs_pandoc
def test_unmapped_md_link_becomes_src_and_warns(tmp_path):
    """Check unmapped md link becomes src and warns."""
    tex, out, warns = conv(tmp_path, "# T\n\n[other](c.md)\n", path_map="docs/b.md\tx\tds:ch:b\n")
    assert "\\code{docs/c.md}" in tex or "\\src{docs/c.md}" in tex
    assert ("unmapped-md-link", "docs/c.md") in warns
    assert "unmapped-md-link\tdocs/c.md" in Path(str(out) + ".warnings.txt").read_text("utf-8")


@needs_pandoc
def test_non_md_repo_link_becomes_src(tmp_path):
    """Check non md repo link becomes src."""
    tex, _, _ = conv(tmp_path, "# T\n\n[make](../pnr/Makefile) and [file](../rtl/soc/soc_top.sv)\n")
    assert "\\src{pnr/Makefile}" in tex
    assert "\\src{rtl/soc/soc_top.sv}" in tex


@needs_pandoc
def test_external_link_stays_href(tmp_path):
    """Check external link stays href."""
    tex, _, _ = conv(tmp_path, "# T\n\n[site](https://example.org/x)\n")
    assert "\\href{https://example.org/x}{site}" in tex


@needs_pandoc
def test_inline_code_path_and_identifier(tmp_path):
    """Check inline code path and identifier."""
    tex, _, _ = conv(tmp_path, "# T\n\nUse `rtl/soc/soc_top.sv` and `my_signal` and `a b`.\n")
    assert "\\src{rtl/soc/soc_top.sv}" in tex
    assert "\\code{my_signal}" in tex
    assert "\\code{a b}" not in tex and "a" in tex


@needs_pandoc
def test_path_like_but_untracked_is_code(tmp_path):
    """Check path like but untracked is code."""
    tex, _, _ = conv(tmp_path, "# T\n\n`rtl/nothing/here.sv`\n")
    assert "\\code{rtl/nothing/here.sv}" in tex


@needs_pandoc
def test_emoji_mapping_in_text(tmp_path):
    """Check emoji mapping in text."""
    tex, _, _ = conv(tmp_path, "# T\n\n⚠️ a ⚠ b ✅ c ✔ d ❌ e 🔴 f ⏸️ g 🟢 h 🚧 i ⭐ j\n")
    for macro in ("\\warn{}", "\\ok{}", "\\bad{}", "\\hold{}", "\\wip{}", "\\textbf{*}"):
        assert macro in tex
    assert tex.count("\\warn{}") == 2 and tex.count("\\ok{}") == 3 and tex.count("\\bad{}") == 2
    assert "⚠" not in tex and "✅" not in tex


@needs_pandoc
def test_emoji_not_mapped_in_code(tmp_path):
    """Check emoji not mapped in code."""
    tex, _, _ = conv(tmp_path, "# T\n\n```\n✅ ok ⚠️\n```\n\nand `✅x`\n")
    assert "✅ ok ⚠️" in tex
    assert "\\texttt{✅x}" in tex


@needs_pandoc
def test_code_block_languages(tmp_path):
    """Check code block languages."""
    md = "# T\n\n```systemverilog\nx\n```\n\n```py\ny\n```\n\n```sdc\nz\n```\n\n```\nplain\n```\n"
    tex, _, _ = conv(tmp_path, md)
    assert "[language=Verilog]" in tex and "[language=Python]" in tex and "[language=tcl]" in tex
    assert "\\begin{lstlisting}[language={}]\nplain" in tex


@needs_pandoc
def test_mermaid_caption_and_logblock(tmp_path):
    """Check mermaid caption and logblock."""
    long_text = "\n".join(f"line {i}" for i in range(45))
    md = f"# T\n\n```mermaid\nA-->B\n```\n\n```log\nx\n```\n\n```text\n{long_text}\n```\n\n```text\nshort\n```\n"  # noqa: E501
    tex, _, _ = conv(tmp_path, md)
    assert "caption={Diagram source (Mermaid)}" in tex
    assert tex.count("\\begin{logblock}") == 2
    assert "\\begin{lstlisting}[language={}]\nshort" in tex


@needs_pandoc
def test_wide_table_gets_landscape_and_narrow_does_not(tmp_path):
    """Check wide table gets landscape and narrow does not."""
    wide = "| a | b | c | d | e | f | g |\n|---|---|---|---|---|---|---|\n| 1 | 2 | 3 | 4 | 5 | 6 | 7 |\n"  # noqa: E501
    narrow = "| a | b | c |\n|---|---|---|\n| 1 | 2 | 3 |\n"
    tex, _, _ = conv(tmp_path, f"# T\n\n{wide}\n{narrow}")
    assert tex.count("\\begin{landscape}") == 1 and tex.count("\\end{landscape}") == 1
    assert tex.count("\\begin{longtable}") == 2


@needs_pandoc
def test_long_cells_get_proportional_widths(tmp_path):
    """Check long cells get proportional widths."""
    cell = "word " * 30
    tex, _, _ = conv(tmp_path, f"# T\n\n| a | b |\n|---|---|\n| x | {cell} |\n")
    assert "\\dimexpr" in tex and "\\real" not in tex


@needs_pandoc
def test_reference_wrapping(tmp_path):
    """Check reference wrapping."""
    md = (
        "# T\n\nSee GH #123, PR #44, RUN_2026-08-09_14-36-16 and bead `ew3`, bead 8f3x, "
        "bead `a.1`. Not bead and not bead `toolong99`.\n"
    )
    tex, _, _ = conv(tmp_path, md)
    assert "\\ghref{123}" in tex and "\\prref{44}" in tex
    assert "\\runid{RUN_2026-08-09_14-36-16}" in tex
    assert "bead \\bead{ew3}" in tex and "bead \\bead{8f3x}" in tex
    assert "bead and" in tex and "\\bead{toolong99}" not in tex


@needs_pandoc
def test_reference_wrapping_leaves_code_alone(tmp_path):
    """Check reference wrapping leaves code alone."""
    md = "# T\n\n`GH #5` and `PR #6`\n\n```\nGH #7 RUN_2026-08-09_14-36-16 bead abc1\n```\n"
    tex, _, _ = conv(tmp_path, md)
    assert "\\ghref{5}" not in tex and "\\prref{6}" not in tex
    assert "GH #7 RUN_2026-08-09_14-36-16 bead abc1" in tex
    assert "\\runid" not in tex


@needs_pandoc
def test_html_handling(tmp_path):
    """Check html handling."""
    md = "# T\n\nline<br>next <!-- hidden --> <b>bold</b> and <name> stays.\n"
    tex, _, warns = conv(tmp_path, md)
    kinds = [k for k, _ in warns]
    assert "html-comment" in kinds and "html-tag" in kinds
    assert "hidden" not in tex and "bold" in tex and "name" in tex and "\\\\" in tex


@needs_pandoc
def test_record_wraps_section_bodies(tmp_path):
    """Check record wraps section bodies."""
    tex, _, _ = conv(tmp_path, "# T\n\nintro\n\n## A\n\nbody a\n\n## B\n\nbody b\n", record=True)
    assert tex.count("\\begin{record}") == tex.count("\\end{record}") == 3
    assert tex.index("\\begin{record}") > tex.index("\\label{cr:inv:a}")


@needs_pandoc
def test_output_hygiene(tmp_path):
    """Check output hygiene."""
    tex, _, _ = conv(tmp_path, "# T\n\ntext with trailing   \n\n```\ncode  \n```\n")
    first = tex.split("\n", 1)[0]
    assert first == (
        "% Converted from docs/a.md by tools/docs/md2tex.py; edit this file, not the original."
    )
    assert tex.endswith("\n") and not tex.endswith("\n\n")
    assert all(ln == ln.rstrip() for ln in tex.split("\n"))


@needs_pandoc
def test_strikeout_uses_sout(tmp_path):
    """Check strikeout uses sout."""
    tex, _, _ = conv(tmp_path, "# T\n\n~~gone `x_y`~~\n")
    assert "\\sout{gone" in tex


def test_table_overflow_detection():
    """Check table overflow detection."""
    ok = "| a | b |\n|---|---|\n| 1 | 2 |\n"
    bad = "intro\n\n| a | b |\n|---|---|\n| 1 | 2 |\n| 1 | 2 | 3 |\n"
    escaped = "| a | b |\n|---|---|\n| x \\| y | 2 |\n"
    fenced = "```\n| a |\n|---|\n| 1 | 2 |\n```\n"
    assert md2tex.table_overflow(ok) == []
    assert md2tex.table_overflow(bad) == [(6, 3, 2)]
    assert md2tex.table_overflow(escaped) == []
    assert md2tex.table_overflow(fenced) == []


@needs_pandoc
def test_convert_stops_on_table_overflow(tmp_path, capsys):
    """Check convert stops on table overflow."""
    md = tmp_path / "a.md"
    md.write_text("# T\n\n| a | b |\n|---|---|\n| 1 | 2 | 3 |\n", encoding="utf-8")
    code, _ = md2tex.convert(
        md, book="cr", kind="inv", slug="a", out=tmp_path / "o.tex", root=tmp_path
    )
    assert code == 2
    assert "a.md:5" in capsys.readouterr().err
    assert not (tmp_path / "o.tex").exists()


def test_main_usage_errors(tmp_path):
    """Check main usage errors."""
    with pytest.raises(SystemExit) as e:
        md2tex.main(["x.md"])
    assert e.value.code == 2
    assert (
        md2tex.main(["nofile.md", "--book", "cr", "--kind", "inv", "--slug", "a", "-o", "o.tex"])
        == 2
    )
    f = tmp_path / "a.md"
    f.write_text("# T\n", encoding="utf-8")
    assert (
        md2tex.main([str(f), "--book", "cr", "--kind", "inv", "--slug", "Bad Slug", "-o", "o.tex"])
        == 2
    )


def test_missing_pandoc_exit_code(tmp_path, monkeypatch):
    """Check missing pandoc exit code."""
    monkeypatch.setattr(md2tex.shutil, "which", lambda name: None)
    f = tmp_path / "a.md"
    f.write_text("# T\n", encoding="utf-8")
    rc = md2tex.main(
        [str(f), "--book", "cr", "--kind", "inv", "--slug", "a", "-o", str(tmp_path / "o.tex")]
    )
    assert rc == 3


@needs_pandoc
def test_status_marks_follow_the_pictograph_table(tmp_path):
    """Check every pictograph maps to its mark and the variation selector is removed."""
    md = (
        "# T\n\n🟡 a 🟠 b ✋ c 🛑 d 🚫 e ❗ f 🚨 g 🚩 h 🎉 i 🎯 j 🔄 k ⏭ l "
        "ℹ️ m 📝 n 👉 o 🔥 p ⚡ q ❓ r 🤔 s 📉 t 📈 u 📊 v 🔧 w 🚀 x\n"
    )
    tex, _, warns = conv(tmp_path, md)
    assert tex.count("\\partialmark{}") == 2
    assert tex.count("\\hold{}") == 3
    assert tex.count("\\warn{}") == 5
    assert tex.count("\\ok{}") == 2
    assert tex.count("\\wip{}") == 2
    assert tex.count("\\notemark{}") == 8
    assert tex.count("\\openmark{}") == 2
    assert "\ufe0f" not in tex
    assert not [w for w in warns if w[0] == "pictograph"]


@needs_pandoc
def test_unknown_pictograph_warns_and_maps_to_notemark(tmp_path):
    """Check an unknown pictograph is reported with its file and mapped to a note mark."""
    tex, _, warns = conv(tmp_path, "# T\n\nunicorn \U0001f984 here\n")
    assert "\\notemark{}" in tex and "\U0001f984" not in tex
    hits = [d for k, d in warns if k == "pictograph"]
    assert len(hits) == 1 and "U+1F984" in hits[0] and "docs/a.md" in hits[0]


@needs_pandoc
def test_text_symbols_are_not_pictographs(tmp_path):
    """Check check marks, ballot boxes and arrows stay text and give no warning."""
    tex, _, warns = conv(tmp_path, "# T\n\n✓ ☐ ☒ ☑ ✗ → ↔ ⇒ ≥ ∈ ⁷\n")
    for ch in "✓☐☒☑✗→↔⇒≥∈⁷":
        assert ch in tex
    assert "\\notemark{}" not in tex and not warns


@needs_pandoc
def test_code_block_with_non_ascii_uses_textblock(tmp_path):
    """Check box-drawing code avoids listings and keeps its text."""
    md = "# T\n\n```\n┌──┐\n│ab│\n└──┘\n```\n\n```py\nx = 1\n```\n"
    tex, _, _ = conv(tmp_path, md)
    assert "\\begin{textblock}\n┌──┐\n│ab│\n└──┘\n\\end{textblock}" in tex
    assert "\\begin{lstlisting}[language=Python]\nx = 1" in tex


@needs_pandoc
def test_inline_code_fallback_can_break_but_strikeout_cannot(tmp_path):
    """Check monospace text breaks after path marks and strike-through text does not."""
    tex, _, _ = conv(tmp_path, "# T\n\n`a/b,c d` and ~~`x/y z`~~\n")
    assert "\\texttt{a/\\allowbreak{}b,\\allowbreak{}c\\ d}" in tex
    assert "\\sout{\\texttt{x/y\\ z}}" in tex


@needs_pandoc
def test_long_words_break_after_slash_and_underscore(tmp_path):
    """Check long plain words get break points, short words do not."""
    tex, _, _ = conv(tmp_path, "# T\n\n(VADD/VSUB/VMUL) GPU_BLOCK_DIM_Y a_b\n")
    assert "VADD/\\allowbreak{}VSUB/\\allowbreak{}VMUL" in tex
    assert "GPU\\_\\allowbreak{}BLOCK" in tex
    assert "a\\_b" in tex and "a\\_\\allowbreak" not in tex


@needs_pandoc
def test_wide_table_uses_smaller_font(tmp_path):
    """Check a dense table gets a smaller font and less column padding."""
    cell = "word " * 12
    row = "| " + " | ".join([cell] * 4) + " |\n"
    md = "# T\n\n| a | b | c | d |\n|---|---|---|---|\n" + row
    tex, _, _ = conv(tmp_path, md)
    assert "\\footnotesize\\setlength{\\tabcolsep}{3pt}" in tex
    tex2, _, _ = conv(tmp_path, "# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n")
    assert "\\footnotesize" not in tex2 and "\\small" not in tex2
