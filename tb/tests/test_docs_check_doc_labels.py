"""Unit tests for tools/docs/check_doc_labels.py."""

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import check_doc_labels as cdl  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error

MAP_HEADER = "old_path\tnew_file\tlabel\n"


def tree(root: Path, files: dict[str, str]) -> Path:
    """Create a synthetic repository tree."""
    files = {"docs/manual/common/path_map.tsv": MAP_HEADER, **files}
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root


def run(root: Path, capsys, write: bool = True):  # type: ignore[no-untyped-def]
    """Run the checker and return (exit code, output lines)."""
    capsys.readouterr()
    args = ["--root", str(root)] + (["--write-labels"] if write else [])
    rc = cdl.main(args)
    return rc, capsys.readouterr().out.splitlines()


GOOD_DS = (
    "\\part{A}\\label{ds:part:alpha}\n"
    "\\chapter{First}\\label{ds:ch:first}\n"
    "\\section{Mod}\\label{ds:mod:apb-cdc-bridge}\n"
    "See \\cref{tm:ch:second} and \\cref{ds:ch:first,tm:ch:second}.\n"
)
GOOD_TM = "\\chapter{Second}\\label{tm:ch:second}\n"


def good(root: Path) -> Path:
    """Create a clean tree."""
    return tree(root, {"docs/manual/ds/ds.tex": GOOD_DS, "docs/manual/tm/tm.tex": GOOD_TM})


def test_good_tree_passes(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A clean tree has no findings."""
    rc, out = run(good(tmp_path), capsys)
    assert rc == 0 and out == []


def test_bad_label_format(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A label outside the scheme is a finding."""
    bad = GOOD_TM + "\\section{X}\\label{tm:chapter:Second_One}\n\\label{sec:intro}\n"
    rc, out = run(tree(tmp_path, {"docs/manual/tm/tm.tex": bad}), capsys)
    assert rc == 1
    assert any("tm:chapter:Second_One" in ln and "scheme" in ln for ln in out)
    assert any("sec:intro" in ln for ln in out)


def test_prefixed_labels_need_a_book_prefix(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """fig:, tab:, lst: and eq: labels continue with a valid label."""
    text = "\\label{tab:tm:pd:corners}\n\\label{tab:corners}\n"
    rc, out = run(tree(tmp_path, {"docs/manual/tm/tm.tex": text}), capsys)
    assert rc == 1
    assert len(out) == 1 and "tab:corners" in out[0]


def test_duplicate_label_across_books(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The same label in two books is a finding."""
    files = {
        "docs/manual/ds/ds.tex": "\\label{ds:ch:same}\n",
        "docs/manual/tm/tm.tex": "\\label{tm:ch:other}\n",
        "docs/manual/um/um.tex": "\\label{ds:ch:same}\n",
    }
    rc, out = run(tree(tmp_path, files), capsys)
    assert rc == 1
    assert any("duplicate label 'ds:ch:same'" in ln for ln in out)


def test_undefined_cref_target(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A reference to an unknown label is a finding."""
    text = GOOD_DS + "\\cref{ds:ch:missing}\n"
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 1
    assert any("undefined label 'ds:ch:missing'" in ln for ln in out)


def test_one_undefined_item_in_a_comma_list(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """One bad item of a cref list is found, the good ones are not."""
    text = GOOD_DS + "\\Cref{ds:ch:first,ds:ch:nope}\n"
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 1 and len(out) == 1 and "ds:ch:nope" in out[0]


def test_other_reference_commands(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """ref, autoref, pageref and nameref are checked."""
    text = "".join(
        f"\\{c}{{ds:ch:gone{i}}}\n" for i, c in enumerate(["ref", "autoref", "pageref", "nameref"])
    )
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 1 and len(out) == 4


def test_label_in_comment_is_ignored(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A commented label or reference does not count, an escaped percent does."""
    text = (
        GOOD_DS
        + "% \\label{bad label}\n"
        + "% \\cref{ds:ch:missing}\n"
        + "50\\% done \\label{ds:ch:after-percent}\n"
    )
    rc, out = run(
        tree(tmp_path, {"docs/manual/ds/ds.tex": text, "docs/manual/tm/tm.tex": GOOD_TM}), capsys
    )
    assert rc == 0 and out == []
    labels = (tmp_path / "docs/manual/common/labels.tsv").read_text(encoding="utf-8")
    assert "ds:ch:after-percent" in labels


def test_verbatim_material_is_ignored(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Labels and references inside a listing are examples, not real."""
    text = GOOD_DS + "\\begin{lstlisting}\n\\cref{ds:ch:nowhere}\n\\end{lstlisting}\n"
    rc, out = run(
        tree(tmp_path, {"docs/manual/ds/ds.tex": text, "docs/manual/tm/tm.tex": GOOD_TM}), capsys
    )
    assert rc == 0, out


def test_doc_citation_defined_and_undefined(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Doc comments in .sv, .py and .sdc files are checked."""
    files = {
        "docs/manual/ds/ds.tex": GOOD_DS,
        "docs/manual/tm/tm.tex": GOOD_TM,
        "rtl/ok.sv": "// Doc: ds:mod:apb-cdc-bridge\nmodule m; endmodule\n",
        "rtl/bad.sv": "module m; endmodule\n// Doc: ds:mod:no-such\n",
        "tools/ok.py": "# Doc: ds:ch:first, tm:ch:second\n",
        "tools/bad.py": "x = 1\n# Doc: tm:ch:missing, ds:ch:first\n",
        "pnr/bad.sdc": "# Doc: um:guide:gone\n",
        "tools/doc.py": 'def f():\n    """Text.\n\n    Doc: ds:ch:docstring-gone\n    """\n',
    }
    rc, out = run(tree(tmp_path, files), capsys)
    assert rc == 1
    joined = "\n".join(out)
    assert "rtl/bad.sv:2:" in joined and "ds:mod:no-such" in joined
    assert "tools/bad.py:2:" in joined and "tm:ch:missing" in joined
    assert "pnr/bad.sdc:1:" in joined and "um:guide:gone" in joined
    assert "tools/doc.py:4:" in joined and "ds:ch:docstring-gone" in joined
    assert "rtl/ok.sv" not in joined and "tools/ok.py" not in joined


def test_prose_with_doc_colon_is_ignored(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Ordinary prose that contains Doc: without a label is not a citation."""
    files = {
        "rtl/prose.sv": "// Doc: see the manual for details\n// Doc: ds is a book\n",
        "tools/p.py": "# Doc: https://example.org/x\nprint('Doc: ds:ch:inline')\n",
    }
    rc, out = run(tree(good(tmp_path), files), capsys)
    assert rc == 0, out


def test_excluded_directories_are_not_scanned(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Citations under memory/ and pnr/commercial/ are skipped."""
    files = {
        "memory/note.md": "# Doc: ds:ch:gone\n",
        "pnr/commercial/a.tcl": "# Doc: ds:ch:gone\n",
    }
    rc, out = run(tree(good(tmp_path), files), capsys)
    assert rc == 0, out


def test_path_map_unknown_label_and_missing_file(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A path_map row needs a defined label and an existing file."""
    rows = (
        MAP_HEADER
        + "docs/a.md\tdocs/manual/ds/ds.tex\tds:ch:first\n"
        + "docs/b.md\tdocs/manual/ds/ds.tex\tds:ch:unknown\n"
        + "docs/c.md\tdocs/manual/ds/none.tex\tds:ch:first\n"
    )
    files = {"docs/manual/common/path_map.tsv": rows}
    rc, out = run(tree(good(tmp_path), files), capsys)
    assert rc == 1 and len(out) == 2
    assert any("path_map.tsv:3:" in ln and "ds:ch:unknown" in ln for ln in out)
    assert any("path_map.tsv:4:" in ln and "none.tex" in ln for ln in out)


def test_path_map_bad_header(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The header row is checked."""
    files = {"docs/manual/common/path_map.tsv": "a\tb\tc\n"}
    rc, out = run(tree(good(tmp_path), files), capsys)
    assert rc == 1 and "header" in out[0]


def test_src_to_missing_path(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A \\src path must exist; directories and globs are allowed."""
    text = (
        GOOD_DS
        + "\\src{rtl/soc/apb_cdc_bridge.sv} \\src{rtl/soc/} \\src{rtl/soc/*.sv}\n"
        + "\\src{rtl/soc/gone.sv} \\src{nodir/} \\src{rtl/nomatch*.sv}\n"
    )
    files = {"docs/manual/ds/ds.tex": text, "rtl/soc/apb_cdc_bridge.sv": "module m; endmodule\n"}
    rc, out = run(tree(good(tmp_path), files), capsys)
    assert rc == 1 and len(out) == 3
    joined = "\n".join(out)
    assert "gone.sv" in joined and "nodir/" in joined and "nomatch" in joined


def test_src_path_with_line_suffix(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A \\src path may carry a :line or :first-last suffix; the file must still exist."""
    text = (
        GOOD_DS
        + "\\src{rtl/soc/apb_cdc_bridge.sv:12} \\src{rtl/soc/apb_cdc_bridge.sv:3-9}\n"
        + "\\src{rtl/soc/gone.sv:5}\n"
    )
    files = {"docs/manual/ds/ds.tex": text, "rtl/soc/apb_cdc_bridge.sv": "module m; endmodule\n"}
    rc, out = run(tree(good(tmp_path), files), capsys)
    assert rc == 1 and len(out) == 1 and "gone.sv" in out[0]


def test_labels_tsv_drift(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A stale labels.tsv fails, --write-labels repairs it."""
    root = good(tmp_path)
    assert run(root, capsys, write=False)[0] == 1  # file does not exist yet
    assert run(root, capsys, write=True)[0] == 0
    assert run(root, capsys, write=False)[0] == 0
    tsv = root / "docs/manual/common/labels.tsv"
    tsv.write_text(tsv.read_text(encoding="utf-8") + "x\ty\t1\tz\n", encoding="utf-8", newline="\n")
    rc, out = run(root, capsys, write=False)
    assert rc == 1 and "out of date" in out[0]
    assert run(root, capsys, write=True)[0] == 0


def test_labels_tsv_content_and_title(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """labels.tsv is sorted and carries the nearest section title."""
    root = good(tmp_path)
    run(root, capsys)
    rows = (root / "docs/manual/common/labels.tsv").read_text(encoding="utf-8").splitlines()
    assert rows[0] == "label\tfile\tline\ttitle"
    labels = [r.split("\t")[0] for r in rows[1:]]
    assert labels == sorted(labels)
    assert "ds:mod:apb-cdc-bridge\tdocs/manual/ds/ds.tex\t3\tMod" in rows
    assert "ds:part:alpha\tdocs/manual/ds/ds.tex\t1\tA" in rows


def test_missing_manual_directory_is_setup_error(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A root without docs/manual gives exit code 2."""
    rc, _ = run(tmp_path, capsys, write=False)
    assert rc == 2


def test_real_repository_is_clean(capsys) -> None:  # type: ignore[no-untyped-def]
    """The checker passes on this repository."""
    capsys.readouterr()
    rc = cdl.main([])
    out = capsys.readouterr().out
    assert rc == 0, out


def test_src_to_moved_document_is_allowed(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A \\src path that is an old path in path_map.tsv names a moved document."""
    rows = MAP_HEADER + "docs/a.md\tdocs/manual/ds/ds.tex\tds:ch:first\n"
    text = GOOD_DS + "\\src{docs/a.md} \\src{docs/other.md}\n"
    files = {"docs/manual/common/path_map.tsv": rows, "docs/manual/ds/ds.tex": text}
    rc, out = run(tree(good(tmp_path), files), capsys)
    assert rc == 1 and len(out) == 1
    assert "docs/other.md" in out[0]


def test_req_and_arc_kinds_pass(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The kinds req and arc are part of the scheme."""
    text = GOOD_DS + "\\label{ds:req:cdc-020}\n\\label{cr:arc:ds-cdc-sync}\n"
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 0, out


def test_caveat_kind_passes_and_unknown_kind_fails(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The kind caveat is in the scheme. A kind outside the scheme is still a finding."""
    text = GOOD_TM + "\\section{C}\\label{tm:caveat:some-limit}\n\\cref{tm:caveat:some-limit}\n"
    rc, out = run(tree(tmp_path, {"docs/manual/tm/tm.tex": text}), capsys)
    assert rc == 0, out
    bad = GOOD_TM + "\\section{C}\\label{tm:limitation:some-limit}\n"
    rc, out = run(tree(tmp_path, {"docs/manual/tm/tm.tex": bad}), capsys)
    assert rc == 1
    assert any("tm:limitation:some-limit" in ln and "scheme" in ln for ln in out)


def test_requirement_defines_derived_label(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A requirement environment defines the label that its ID derives."""
    text = (
        GOOD_DS
        + "\\begin{requirement}{DS-ABC-001}{Short title}[verify={review}]\nBody.\n"
        + "\\end{requirement}\n\\reqref{DS-ABC-001} and \\ref{ds:req:abc-001}\n"
    )
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 0, out
    labels = (tmp_path / "docs/manual/common/labels.tsv").read_text(encoding="utf-8")
    assert "ds:req:abc-001\tdocs/manual/ds/ds.tex\t" in labels
    assert "\tDS-ABC-001 Short title\n" in labels


def test_reqref_without_definition_is_a_finding(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A reqref to an ID that no requirement defines is a finding."""
    text = GOOD_DS + "\\reqref{DS-ABC-002}\n"
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 1
    assert any("undefined label 'ds:req:abc-002'" in ln for ln in out)


def test_requirement_label_is_unique(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """Two requirements with one ID define one label twice."""
    one = "\\begin{requirement}{DS-ABC-001}{T}[verify={review}]\nB.\n\\end{requirement}\n"
    text = GOOD_DS + one + one
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 1
    assert any("duplicate label 'ds:req:abc-001'" in ln for ln in out)


def test_requirement_start_accepts_spaces_between_arguments(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """LaTeX allows spaces between the arguments, so the label is defined all the same."""
    one = "\\begin{requirement} {DS-ABC-001} {T} [verify={review}]\nB.\n\\end{requirement}\n"
    text = GOOD_DS + one + "\\reqref{DS-ABC-001}\n"
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 0, out


def test_cref_on_a_requirement_is_a_finding(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The rule is reqref only. cref, Cref and autoref on a requirement label are findings."""
    one = "\\begin{requirement}{DS-ABC-001}{T}[verify={review}]\nB.\n\\end{requirement}\n"
    refs = "\\cref{ds:req:abc-001} \\Cref{ds:req:abc-001} \\autoref{ds:req:abc-001}\n"
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": GOOD_DS + one + refs}), capsys)
    assert rc == 1
    assert sum("use reqref, not" in ln for ln in out) == 3


def test_cref_on_a_requirement_table_is_allowed(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A table label of a requirement map is an ordinary label."""
    text = GOOD_DS + "\\label{tab:ds:req:abc-map}\n\\cref{tab:ds:req:abc-map}\n"
    rc, out = run(tree(good(tmp_path), {"docs/manual/ds/ds.tex": text}), capsys)
    assert rc == 0, out
