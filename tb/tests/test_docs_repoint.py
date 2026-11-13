"""Unit tests for tools/docs/repoint.py (temporary git repositories)."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import repoint  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error

pytestmark = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")

MAP = (
    "old_path\tnew_file\tlabel\n"
    "docs/PLAN.md\tx.tex\ttm:dec:plan\n"
    "docs/design/SPEC.md\tx.tex\tds:ch:spec\n"
    "docs/a/DUP.md\tx.tex\ttm:dec:dup-a\n"
    "docs/b/DUP.md\tx.tex\ttm:dec:dup-b\n"
)
SECTIONS = (
    "number\tlabel\ttitle\n"
    "1\ttm:dec:plan\t1. Intro\n"
    "7\ttm:dec:plan:7-results\t7. Results\n"
    "14.10\ttm:dec:plan:1410-scrub\t14.10 Scrub\n"
    "\tx\tignored\n"
    "9\ttm:dec:plan:power-figure-caveat\t9. Power figure caveat\n"
)


def make_repo(tmp_path: Path, files: dict[str, str | bytes]) -> Path:
    """Helper: make repo."""
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(
        ["git", "init", "-q"], cwd=root, check=True, stdin=subprocess.DEVNULL, capture_output=True
    )
    for rel, content in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
    subprocess.run(
        ["git", "add", "-A"], cwd=root, check=True, stdin=subprocess.DEVNULL, capture_output=True
    )
    (root / "map.tsv").write_text(MAP, encoding="utf-8")
    sd = root / "_sections"
    sd.mkdir()
    (sd / "plan.tex.sections.tsv").write_text(SECTIONS, encoding="utf-8")
    return root


def run(root: Path, *extra: str, apply: bool = False, sections: bool = True) -> int:
    """Helper: run."""
    argv = ["--map", str(root / "map.tsv"), "--root", str(root)]
    if sections:
        argv += ["--sections-dir", str(root / "_sections")]
    if apply:
        argv.append("--apply")
    return int(repoint.main(argv + list(extra)))


def read(root: Path, rel: str) -> str:
    """Helper: read."""
    return (root / rel).read_bytes().decode("utf-8")


def test_root_relative_in_sv_comment(tmp_path):
    """Check root relative in sv comment."""
    root = make_repo(tmp_path, {"rtl/a.sv": "// see docs/PLAN.md for details\nassign x = 1;\n"})
    assert run(root, apply=True) == 0
    assert read(root, "rtl/a.sv") == "// see Doc: tm:dec:plan for details\nassign x = 1;\n"


def test_file_relative_reference(tmp_path):
    """Check file relative reference."""
    root = make_repo(tmp_path, {"rtl/cpu/a.sv": "// per ../../docs/PLAN.md\n"})
    run(root, apply=True)
    assert read(root, "rtl/cpu/a.sv") == "// per Doc: tm:dec:plan\n"


def test_dot_slash_sibling(tmp_path):
    """Check dot slash sibling."""
    root = make_repo(tmp_path, {"docs/notes.md": "See ./PLAN.md here.\n"})
    run(root, apply=True)
    assert read(root, "docs/notes.md") == "See Doc: tm:dec:plan here.\n"


def test_unique_basename(tmp_path):
    """Check unique basename."""
    root = make_repo(tmp_path, {"tools/x.py": "# uses SPEC.md as source\n"})
    run(root, apply=True)
    assert read(root, "tools/x.py") == "# uses Doc: ds:ch:spec as source\n"


def test_ambiguous_basename_left_and_not_reported_as_unmapped(tmp_path):
    """Check ambiguous basename left and not reported as unmapped."""
    root = make_repo(tmp_path, {"tools/x.py": "# see DUP.md\n"})
    run(root, apply=True)
    assert read(root, "tools/x.py") == "# see DUP.md\n"


def test_section_number_resolved(tmp_path):
    """Check section number resolved."""
    root = make_repo(tmp_path, {"rtl/a.sv": "// docs/PLAN.md §7 and more\n"})
    assert run(root, apply=True) == 0
    assert read(root, "rtl/a.sv") == "// Doc: tm:dec:plan:7-results and more\n"


def test_section_word_and_decimal(tmp_path):
    """Check section word and decimal."""
    root = make_repo(
        tmp_path,
        {
            "rtl/a.sv": "// docs/PLAN.md section 14.10\n// docs/PLAN.md Section 7\n// docs/PLAN.md § 7\n"  # noqa: E501
        },
    )
    run(root, apply=True)
    text = read(root, "rtl/a.sv")
    assert "Doc: tm:dec:plan:1410-scrub\n" in text
    assert text.count("tm:dec:plan:7-results") == 2


def test_quoted_title_resolved(tmp_path):
    """Check quoted title resolved."""
    root = make_repo(
        tmp_path,
        {
            "CLAUDE.md": 'See `docs/PLAN.md` §"Power figure caveat" for it.\nAlso docs/PLAN.md §"power FIGURE caveat".\n'  # noqa: E501
        },
    )
    assert run(root, apply=True) == 0
    text = read(root, "CLAUDE.md")
    assert text.splitlines()[0] == "See Doc: tm:dec:plan:power-figure-caveat for it."
    assert text.splitlines()[1] == "Also Doc: tm:dec:plan:power-figure-caveat."


def test_unquoted_title_resolved(tmp_path):
    """Check unquoted title resolved."""
    root = make_repo(tmp_path, {"docs/n.md": '("docs/PLAN.md §Power figure caveat")\n'})
    run(root, apply=True)
    assert read(root, "docs/n.md") == '("Doc: tm:dec:plan:power-figure-caveat")\n'


def test_unresolved_section_falls_back_and_is_reported(tmp_path, capsys):
    """Check unresolved section falls back and is reported."""
    root = make_repo(tmp_path, {"rtl/a.sv": "// docs/PLAN.md §99\n"})
    rc = run(root, apply=True)
    assert rc == 1
    assert read(root, "rtl/a.sv") == "// Doc: tm:dec:plan §99\n"
    assert "unresolved sections (file-level label used): 1" in capsys.readouterr().out


def test_sv_code_line_reported_not_rewritten(tmp_path, capsys):
    """Check sv code line reported not rewritten."""
    src = 'localparam string P = "docs/PLAN.md";\n'
    root = make_repo(tmp_path, {"rtl/a.sv": src})
    assert run(root, apply=True) == 1
    assert read(root, "rtl/a.sv") == src
    assert "code references, manual: 1" in capsys.readouterr().out


def test_sv_trailing_comment_rewritten_code_part_not(tmp_path):
    """Check sv trailing comment rewritten code part not."""
    root = make_repo(
        tmp_path,
        {"rtl/a.sv": "assign x = 1; // docs/PLAN.md\n/* docs/PLAN.md\n   docs/PLAN.md */\n"},
    )
    run(root, apply=True)
    assert (
        read(root, "rtl/a.sv")
        == "assign x = 1; // Doc: tm:dec:plan\n/* Doc: tm:dec:plan\n   Doc: tm:dec:plan */\n"
    )


def test_python_comment_docstring_rewritten_literal_reported(tmp_path, capsys):
    """Check python comment docstring rewritten literal reported."""
    src = (
        '"""Module doc, see docs/PLAN.md."""\n'
        "# note docs/PLAN.md\n"
        'PATH = "docs/PLAN.md"\n'
        "def f():\n"
        '    """Doc for f.\n\n    More in docs/PLAN.md §7.\n    """\n'
    )
    root = make_repo(tmp_path, {"tools/m.py": src})
    assert run(root, apply=True) == 1
    new = read(root, "tools/m.py")
    assert "see Doc: tm:dec:plan." in new
    assert "# note Doc: tm:dec:plan" in new
    assert 'PATH = "docs/PLAN.md"' in new
    assert "More in Doc: tm:dec:plan:7-results." in new
    assert "code references, manual: 1" in capsys.readouterr().out


def test_makefile_variable_is_code_reference(tmp_path):
    """Check makefile variable is code reference."""
    root = make_repo(tmp_path, {"pnr/Makefile": "DOC = docs/PLAN.md\n# docs/PLAN.md\n"})
    assert run(root, apply=True) == 1
    assert read(root, "pnr/Makefile") == "DOC = docs/PLAN.md\n# Doc: tm:dec:plan\n"


def test_markdown_link_form(tmp_path):
    """Check markdown link form."""
    root = make_repo(
        tmp_path,
        {
            "README.md": "See [the plan](docs/PLAN.md) and [docs/design/SPEC.md](docs/design/SPEC.md).\n"  # noqa: E501
        },
    )
    run(root, apply=True)
    assert read(root, "README.md") == "See the plan (Doc: tm:dec:plan) and Doc: ds:ch:spec.\n"


def test_markdown_fenced_block_is_code_reference(tmp_path):
    """Check markdown fenced block is code reference."""
    src = "```\ncat docs/PLAN.md\n```\n"
    root = make_repo(tmp_path, {"README.md": src})
    assert run(root, apply=True) == 1
    assert read(root, "README.md") == src


def test_tex_form(tmp_path):
    """Check tex form."""
    tex = "see docs/PLAN.md and \\src{docs/PLAN.md} and docs/design/SPEC.md\\_x.\n"
    root = make_repo(tmp_path, {"docs/manual/tm/a.tex": tex})
    run(root, apply=True)
    new = read(root, "docs/manual/tm/a.tex")
    assert new.startswith(
        "see \\cref{tm:dec:plan} and \\src{docs/PLAN.md} (\\cref{tm:dec:plan}) and"
    )


def test_tex_verbatim_untouched(tmp_path):
    """Check tex verbatim untouched."""
    src = (
        "\\begin{lstlisting}\ndocs/PLAN.md\n\\end{lstlisting}\n"
        "\\begin{textblock}\ndocs/PLAN.md\n\\end{textblock}\n"
    )
    root = make_repo(tmp_path, {"docs/manual/tm/a.tex": src})
    run(root, apply=True)
    assert read(root, "docs/manual/tm/a.tex") == src


def test_excluded_paths_untouched(tmp_path):
    """Check excluded paths untouched."""
    line = "see docs/PLAN.md\n"
    files = {
        ".beads/x.md": line,
        "memory/pd/k.md": line,
        "micro_p/n.md": line,
        "pnr/commercial/r.md": line,
        "design_state.json": '{"d": "docs/PLAN.md"}\n',
        "uv.lock": line,
        "docs/PLAN.md": line,
        "docs/manual/common/path_map.tsv": "docs/PLAN.md\n",
    }
    root = make_repo(tmp_path, files)
    assert run(root, apply=True) == 0
    for rel, content in files.items():
        assert read(root, rel) == content


def test_untracked_file_untouched(tmp_path):
    """Check untracked file untouched."""
    root = make_repo(tmp_path, {"a.md": "x\n"})
    (root / "new.md").write_bytes(b"see docs/PLAN.md\n")
    run(root, apply=True)
    assert read(root, "new.md") == "see docs/PLAN.md\n"


def test_line_count_preserved(tmp_path):
    """Check line count preserved."""
    src = "\n".join(f"// l{i} docs/PLAN.md §7" for i in range(20)) + "\n\n"
    root = make_repo(tmp_path, {"rtl/a.sv": src})
    run(root, apply=True)
    assert read(root, "rtl/a.sv").count("\n") == src.count("\n")


def test_crlf_preserved(tmp_path):
    """Check crlf preserved."""
    root = make_repo(tmp_path, {"rtl/a.sv": b"// docs/PLAN.md\r\nassign x = 1;\r\n"})
    run(root, apply=True)
    assert (root / "rtl/a.sv").read_bytes() == b"// Doc: tm:dec:plan\r\nassign x = 1;\r\n"


def test_binary_file_skipped(tmp_path):
    """Check binary file skipped."""
    data = b"\x00\x01docs/PLAN.md"
    root = make_repo(tmp_path, {"blob.bin": data})
    run(root, apply=True)
    assert (root / "blob.bin").read_bytes() == data


def test_dry_run_changes_nothing_and_previews(tmp_path, capsys):
    """Check dry run changes nothing and previews."""
    src = "// docs/PLAN.md\n"
    root = make_repo(tmp_path, {"rtl/a.sv": src})
    assert run(root) == 0
    assert read(root, "rtl/a.sv") == src
    out = capsys.readouterr().out
    assert "- // docs/PLAN.md" in out and "+ // Doc: tm:dec:plan" in out


def test_unmapped_docs_path_reported(tmp_path, capsys):
    """Check unmapped docs path reported."""
    root = make_repo(tmp_path, {"rtl/a.sv": "// docs/OTHER.md\n"})
    assert run(root) == 1
    assert "references to docs paths not in the map: 1" in capsys.readouterr().out


def test_existing_doc_prefix_not_doubled(tmp_path):
    """Check existing doc prefix not doubled."""
    root = make_repo(tmp_path, {"rtl/a.sv": "// Doc: docs/PLAN.md\n"})
    run(root, apply=True)
    assert read(root, "rtl/a.sv") == "// Doc: tm:dec:plan\n"


def test_path_filter_and_report_file(tmp_path):
    """Check path filter and report file."""
    root = make_repo(tmp_path, {"a/x.sv": "// docs/PLAN.md\n", "b/y.sv": "// docs/PLAN.md\n"})
    rep = tmp_path / "rep.txt"
    run(root, "a", "--report", str(rep), apply=True)
    assert "Doc:" in read(root, "a/x.sv") and "docs/PLAN.md" in read(root, "b/y.sv")
    assert "counts per file" in rep.read_text(encoding="utf-8")


def test_usage_errors(tmp_path):
    """Check usage errors."""
    root = make_repo(tmp_path, {"a.md": "x\n"})
    assert repoint.main(["--map", str(root / "nope.tsv"), "--root", str(root)]) == 2
    with pytest.raises(SystemExit) as e:
        repoint.main([])
    assert e.value.code == 2
    assert (
        repoint.main(
            [
                "--map",
                str(root / "map.tsv"),
                "--root",
                str(root),
                "--sections-dir",
                str(root / "zz"),
            ]
        )
        == 2
    )


def test_provenance_argument_and_comment_untouched(tmp_path):
    """Check the relocated and record arguments and the Converted-from comment stay."""
    src = (
        "% Converted from docs/PLAN.md by tools/docs/md2tex.py; edit this file.\n"
        "\\begin{relocated}{docs/PLAN.md}\n"
        "text\n"
        "\\end{relocated}\n"
        "\\begin{record}{docs/PLAN.md}\n"
        "\\end{record}\n"
    )
    root = make_repo(tmp_path, {"docs/manual/tm/a.tex": src})
    assert run(root, apply=True) == 0
    assert read(root, "docs/manual/tm/a.tex") == src


def test_provenance_line_still_repoints_other_paths(tmp_path):
    """Check only the provenance argument is protected, not the rest of the line."""
    src = "\\begin{relocated}{docs/PLAN.md} see docs/design/SPEC.md\n"
    root = make_repo(tmp_path, {"docs/manual/tm/a.tex": src})
    run(root, apply=True)
    assert read(root, "docs/manual/tm/a.tex") == (
        "\\begin{relocated}{docs/PLAN.md} see \\cref{ds:ch:spec}\n"
    )


@pytest.mark.parametrize("macro", ["code", "src", "texttt", "runid"])
def test_tex_macro_argument_kept_and_cref_appended_once(tmp_path, macro):
    """Check a path in a text macro stays and a cref follows the macro, once."""
    src = f"see \\{macro}{{docs/PLAN.md}} now\n"
    root = make_repo(tmp_path, {"docs/manual/tm/a.tex": src})
    run(root, apply=True)
    once = f"see \\{macro}{{docs/PLAN.md}} (\\cref{{tm:dec:plan}}) now\n"
    assert read(root, "docs/manual/tm/a.tex") == once
    run(root, apply=True)
    assert read(root, "docs/manual/tm/a.tex") == once


def test_tex_macro_with_line_suffix_and_existing_cref(tmp_path):
    """Check a macro with a line suffix gets a cref; an existing cref is not doubled."""
    src = (
        "a \\code{docs/PLAN.md:431} b\n"
        "c \\src{docs/PLAN.md} (\\cref{tm:dec:plan}) d\n"
        "e \\src{docs/PLAN.md}\\cref{tm:dec:plan} f\n"
    )
    root = make_repo(tmp_path, {"docs/manual/tm/a.tex": src})
    run(root, apply=True)
    lines = read(root, "docs/manual/tm/a.tex").splitlines()
    assert lines[0] == "a \\code{docs/PLAN.md:431} (\\cref{tm:dec:plan}) b"
    assert lines[1] == "c \\src{docs/PLAN.md} (\\cref{tm:dec:plan}) d"
    assert lines[2] == "e \\src{docs/PLAN.md}\\cref{tm:dec:plan} f"
    assert "\\code{\\cref" not in "".join(lines)


def test_tex_bare_path_before_existing_cref_not_doubled(tmp_path):
    """Check a bare path that a cref already follows does not give a doubled cref."""
    src = "see docs/PLAN.md (\\cref{tm:dec:plan}) here\n"
    root = make_repo(tmp_path, {"docs/manual/tm/a.tex": src})
    run(root, apply=True)
    assert read(root, "docs/manual/tm/a.tex") == src


def test_line_suffix_in_comment_never_joins_label(tmp_path):
    """Check path.md:123 becomes a label plus a line note, never label:123."""
    root = make_repo(
        tmp_path,
        {
            "rtl/a.sv": "// see docs/PLAN.md:123 and docs/PLAN.md:10-20 end\n",
            "docs/manual/tm/a.tex": "x docs/PLAN.md:123 y\n",
        },
    )
    run(root, apply=True)
    assert read(root, "rtl/a.sv") == (
        "// see Doc: tm:dec:plan (line 123 of the original file) and "
        "Doc: tm:dec:plan (lines 10-20 of the original file) end\n"
    )
    assert read(root, "docs/manual/tm/a.tex") == (
        "x \\cref{tm:dec:plan} (line 123 of the original file) y\n"
    )


def test_section_label_with_date_falls_back_to_file_label(tmp_path):
    """Check a section label that holds an ISO date is never emitted in a comment."""
    root = make_repo(tmp_path, {"rtl/a.sv": "// docs/PLAN.md section 5 and more\n"})
    (root / "_sections" / "plan.tex.sections.tsv").write_text(
        "number\tlabel\ttitle\n5\ttm:dec:plan:2026-09-18-update\t5 Update\n", encoding="utf-8"
    )
    assert run(root, apply=True) == 1
    text = read(root, "rtl/a.sv")
    assert "2026-09-18" not in text
    assert text == "// Doc: tm:dec:plan section 5 and more\n"


def test_boot_image_sources_never_rewritten(tmp_path):
    """Check files hashed by the boot image manifest, and the static boot paths, stay untouched."""
    src = "// see docs/PLAN.md here\n"
    py_src = "# see docs/PLAN.md here\n"
    manifest = '{"sources": {"tools/pinned_gen.py": "00", "sw/other/x.c": "11"}}\n'
    root = make_repo(
        tmp_path,
        {
            "fpga/nexys_video/boot_uart.manifest.json": manifest,
            "tools/pinned_gen.py": py_src,
            "sw/other/x.c": src,
            "sw/bootloader/uart_boot.c": src,
            "sw/bench/bin2hex.py": py_src,
            "rtl/a.sv": src,
        },
    )
    run(root, apply=True)
    assert read(root, "tools/pinned_gen.py") == py_src
    assert read(root, "sw/other/x.c") == src
    assert read(root, "sw/bootloader/uart_boot.c") == src
    assert read(root, "sw/bench/bin2hex.py") == py_src
    assert read(root, "rtl/a.sv") == "// see Doc: tm:dec:plan here\n"
