"""Unit tests for tools/docs/check_requirements.py."""

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "tools" / "docs"))

import check_requirements as cr  # type: ignore[import-not-found]  # noqa: E402  # pylint: disable=import-error

TEST_PY = (
    "def test_alpha():\n    pass\n\n"
    "async def test_beta():\n    pass\n\n"
    "def run_gamma():\n    pass\n\n"
    "class K:\n    def test_nested(self):\n        pass\n"
)
MUTANT_PY = 'MUTANTS = ["m_one", "m_two"]\n'


def req(rid: str, verify: str = "review", title: str = "Title", body: str = "Body.") -> str:
    """Return the text of one requirement environment."""
    opt = f"[verify={{{verify}}}]" if verify is not None else ""
    return f"\\begin{{requirement}}{{{rid}}}{{{title}}}{opt}\n{body}\n\\end{{requirement}}\n"


def tree(
    root: Path, ds: str, extra: dict[str, str] | None = None, ledger: str | None = None
) -> Path:
    """Create a synthetic repository."""
    files = {
        "docs/manual/ds/ds.tex": ds,
        "tb/cocotb/soc/test_a.py": TEST_PY,
        "tools/verif/mut.py": MUTANT_PY,
        "pnr/constraints/a.sdc": "# sdc\n",
        "tools/formal/p.sby": "[options]\n",
        **(extra or {}),
    }
    if ledger is not None:
        files["docs/manual/common/requirement_ids.tsv"] = ledger
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
    return root


def run(root: Path, capsys, *args: str):  # type: ignore[no-untyped-def]
    """Run the checker and return the exit code and the output lines."""
    capsys.readouterr()
    rc = cr.main(["--root", str(root), *args])
    return rc, capsys.readouterr().out.splitlines()


def run_err(root: Path, capsys, *args: str):  # type: ignore[no-untyped-def]
    """Run the checker and return the exit code and the error output."""
    capsys.readouterr()
    rc = cr.main(["--root", str(root), *args])
    return rc, capsys.readouterr().err


def written(root: Path, capsys):  # type: ignore[no-untyped-def]
    """Write the ledger and the tables, then return the result of --write."""
    return run(root, capsys, "--write")


def test_good_tree_after_write_is_clean(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """--write and then --check give no finding."""
    ds = req("DS-CDC-020", "test:tb/cocotb/soc/test_a.py::test_alpha; review")
    root = tree(tmp_path, ds)
    rc, out = written(root, capsys)
    assert rc == 0, out
    rc, out = run(root, capsys, "--check", "-v")
    assert rc == 0
    assert out == ["check_requirements: 1 requirements, 1 refs, 0 review-only, 0 finding(s)"]


def test_bad_id(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """An ID outside the form is a finding."""
    root = tree(tmp_path, req("DS-cdc-20") + req("XX-CDC-001") + req("DS-CDC-0001"))
    rc, out = run(root, capsys)
    assert rc == 1
    assert sum("bad requirement ID" in ln for ln in out) == 3


def test_duplicate_id(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The same ID twice is a finding."""
    root = tree(tmp_path, req("DS-CDC-001") + req("DS-CDC-001"))
    rc, out = run(root, capsys)
    assert rc == 1 and any("duplicate requirement ID DS-CDC-001" in ln for ln in out)


def test_missing_verify(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A requirement without a verify argument is a finding."""
    root = tree(tmp_path, req("DS-CDC-001", verify=None))  # type: ignore[arg-type]
    rc, out = run(root, capsys)
    assert rc == 1 and any("missing verify argument" in ln for ln in out)


def test_body_starting_with_bracket(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A body that starts with a bracket is read as the option, so it is a finding."""
    root = tree(tmp_path, req("DS-CDC-001", verify=None, body="[x] is a thing."))  # type: ignore[arg-type]
    rc, out = run(root, capsys)
    assert rc == 1 and any("body that starts with '['" in ln for ln in out)


def test_test_file_missing(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A test file that does not exist is a finding."""
    root = tree(tmp_path, req("DS-CDC-001", "test:tb/cocotb/soc/test_none.py::test_alpha"))
    rc, out = run(root, capsys)
    assert rc == 1 and any("test_none.py' does not exist" in ln for ln in out)


def test_function_missing(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A function that the file does not define at top level is a finding."""
    ds = req("DS-CDC-001", "test:tb/cocotb/soc/test_a.py::test_gone")
    ds += req("DS-CDC-002", "test:tb/cocotb/soc/test_a.py::test_nested")
    rc, out = run(tree(tmp_path, ds), capsys)
    assert rc == 1 and sum("has no function" in ln for ln in out) == 2


def test_run_function_and_async_def_are_accepted(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A run_ function and an async def count as test functions."""
    ds = req(
        "DS-CDC-001",
        "test:tb/cocotb/soc/test_a.py::run_gamma; test:tb/cocotb/soc/test_a.py::test_beta",
    )
    rc, out = written(tree(tmp_path, ds), capsys)
    assert rc == 0, out


def test_test_path_must_be_under_tb(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A test reference outside tb/ is a finding."""
    extra = {"tools/t.py": "def test_x():\n    pass\n"}
    root = tree(tmp_path, req("DS-CDC-001", "test:tools/t.py::test_x"), extra)
    rc, out = run(root, capsys)
    assert rc == 1 and any("under tb/" in ln for ln in out)


def test_mutation_reference(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A mutant must be named as a quoted string in its file."""
    good = req("DS-CDC-001", "mutation:tools/verif/mut.py::m_one")
    bad = req("DS-CDC-002", "mutation:tools/verif/mut.py::m_three")
    rc, out = run(tree(tmp_path, good + bad), capsys)
    assert rc == 1
    assert any("m_three" in ln for ln in out) and not any("m_one" in ln for ln in out)


def test_check_and_formal_paths(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """check: and formal: need an existing file."""
    ds = req("DS-CDC-001", "check:pnr/constraints/a.sdc; formal:tools/formal/p.sby")
    ds += req("DS-CDC-002", "check:pnr/constraints/none.sdc")
    rc, out = run(tree(tmp_path, ds), capsys)
    assert rc == 1 and sum("does not exist" in ln for ln in out) == 1


def test_unknown_form_and_bad_characters(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """An unknown method and a forbidden character are findings."""
    ds = req("DS-CDC-001", "run:tb/x.py") + req("DS-CDC-002", "check:a#b")
    rc, out = run(tree(tmp_path, ds), capsys)
    assert rc == 1
    assert any("unknown reference form" in ln for ln in out)
    assert any("character that is not allowed" in ln for ln in out)


def test_unknown_reqref(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A reqref to an ID that no requirement defines is a finding."""
    ds = req("DS-CDC-001") + "See \\reqref{DS-CDC-001} and \\reqref{DS-CDC-009}.\n"
    rc, out = run(tree(tmp_path, ds), capsys)
    assert rc == 1
    assert any("DS-CDC-009" in ln for ln in out) and not any("'DS-CDC-001'" in ln for ln in out)


def test_ledger_new_id_needs_write(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A new ID that the ledger lacks is a finding until --write."""
    root = tree(tmp_path, req("DS-CDC-001"), ledger=cr.LEDGER_HEADER + "\n")
    rc, out = run(root, capsys)
    assert rc == 1 and any("not in the ledger" in ln for ln in out)
    assert written(root, capsys)[0] == 0
    ledger = (root / cr.LEDGER).read_text(encoding="utf-8")
    assert ledger == "id\tstatus\tfirst_file\nDS-CDC-001\tactive\tdocs/manual/ds/ds.tex\n"


def test_active_ledger_id_missing_from_tex(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """An active ledger ID with no requirement is a finding. --write does not delete it."""
    ledger = cr.LEDGER_HEADER + "\nDS-CDC-001\tactive\tdocs/manual/ds/ds.tex\n"
    root = tree(tmp_path, "No requirement here.\n", ledger=ledger)
    rc, out = run(root, capsys)
    assert rc == 1 and any("active ID DS-CDC-001" in ln for ln in out)
    assert written(root, capsys)[0] == 1
    assert "DS-CDC-001" in (root / cr.LEDGER).read_text(encoding="utf-8")


def test_retired_id_reuse(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A retired ID that appears in a .tex file is a finding."""
    ledger = cr.LEDGER_HEADER + "\nDS-CDC-001\tretired\tdocs/manual/ds/ds.tex\n"
    rc, out = run(tree(tmp_path, req("DS-CDC-001"), ledger=ledger), capsys)
    assert rc == 1 and any("retired ID DS-CDC-001 is used again" in ln for ln in out)


def test_retired_id_without_use_is_clean(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A retired ID that no file uses is not a finding."""
    ledger = cr.LEDGER_HEADER + "\nDS-CDC-001\tretired\tdocs/manual/ds/ds.tex\n"
    rc, out = run(tree(tmp_path, "Nothing.\n", ledger=ledger), capsys)
    assert rc == 0, out


def test_table_content(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The table lists ID, title and the verification with the method in bold."""
    ds = req("DS-CDC-020", "test:tb/cocotb/soc/test_a.py::test_alpha; review", title="Latency")
    root = tree(tmp_path, ds)
    assert written(root, capsys)[0] == 0
    text = (root / "docs/manual/ds/generated/requirements-cdc.tex").read_text(encoding="utf-8")
    assert "\\label{tab:ds:req:cdc-map}" in text
    assert "Requirements of area CDC and their verification" in text
    assert "ID & Requirement & Verified by" in text
    assert (
        "\\reqref{DS-CDC-020} & Latency & "
        "\\textbf{test} \\code{tb/cocotb/soc/test_a.py::test_alpha}"
        " \\newline \\textbf{review}\\\\"
    ) in text
    assert text.startswith("% Generated by tools/docs/check_requirements.py")


def test_table_drift_is_a_finding(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A changed table is a finding for --check."""
    root = tree(tmp_path, req("DS-CDC-020"))
    assert written(root, capsys)[0] == 0
    path = root / "docs/manual/ds/generated/requirements-cdc.tex"
    path.write_text(path.read_text(encoding="utf-8") + "x\n", encoding="utf-8", newline="\n")
    rc, out = run(root, capsys)
    assert rc == 1 and any("requirements-cdc.tex:1: is out of date" in ln for ln in out)


def test_example_area_is_user_manual_only_and_left_out(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """EXAMPLE counts in the total but is in no ledger and no table."""
    um = req("DS-EXAMPLE-001", "test:tb/cocotb/soc/test_a.py::test_alpha")
    root = tree(tmp_path, req("DS-CDC-020"), {"docs/manual/um/um.tex": um})
    assert written(root, capsys)[0] == 0
    ledger = (root / cr.LEDGER).read_text(encoding="utf-8")
    assert "EXAMPLE" not in ledger
    assert not (root / "docs/manual/ds/generated/requirements-example.tex").exists()
    rc, out = run(root, capsys, "-v")
    assert rc == 0 and out[-1].startswith("check_requirements: 2 requirements")


def test_example_in_design_specification_is_a_finding(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The EXAMPLE area belongs in the User Manual, and other areas in the Design Specification."""
    root = tree(tmp_path, req("DS-EXAMPLE-002"), {"docs/manual/um/um.tex": req("DS-CDC-050")})
    rc, out = run(root, capsys)
    assert rc == 1
    assert any("DS-EXAMPLE-002" in ln and "docs/manual/um/" in ln for ln in out)
    assert any("DS-CDC-050" in ln and "docs/manual/ds/" in ln for ln in out)


def test_requirement_in_listing_or_comment_is_ignored(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """An example in a listing or a comment is not a requirement."""
    ds = "\\begin{lstlisting}\n" + req("DS-BAD-1") + "\\end{lstlisting}\n"
    ds += "% " + req("DS-BAD-2").replace("\n", "\n% ")
    rc, out = written(tree(tmp_path, ds), capsys)
    assert rc == 0, out


def test_bad_ledger_is_setup_error(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A ledger with a wrong header gives exit code 2."""
    root = tree(tmp_path, req("DS-CDC-001"), ledger="a\tb\tc\n")
    rc, _ = run(root, capsys)
    assert rc == 2


def test_missing_manual_is_setup_error(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A root without docs/manual gives exit code 2."""
    rc, _ = run(tmp_path, capsys)
    assert rc == 2


def test_real_repository_is_clean(capsys) -> None:  # type: ignore[no-untyped-def]
    """The checker passes on this repository."""
    capsys.readouterr()
    rc = cr.main(["-v"])
    out = capsys.readouterr().out
    assert rc == 0, out


def test_mutation_name_in_a_comment_is_not_a_mutant(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A name that appears only in a comment is a finding, and a name in a list is not."""
    extra = {"tools/verif/mut2.py": '# the mutant "m_comment" was removed\nMUTANTS = ["m_one"]\n'}
    ds = req("DS-CDC-001", "mutation:tools/verif/mut2.py::m_comment")
    ds += req("DS-CDC-002", "mutation:tools/verif/mut2.py::m_one")
    rc, out = run(tree(tmp_path, ds, extra), capsys)
    assert rc == 1
    assert any("DS-CDC-001" in ln and "no string literal 'm_comment'" in ln for ln in out)
    assert not any("DS-CDC-002" in ln and "string literal" in ln for ln in out)


def test_mutation_file_must_be_python(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A mutation reference needs a Python file that parses."""
    extra = {"tools/verif/mut.txt": "m_one\n"}
    rc, out = run(
        tree(tmp_path, req("DS-CDC-001", "mutation:tools/verif/mut.txt::m_one"), extra), capsys
    )
    assert rc == 1 and any("must be a Python file" in ln for ln in out)


def test_paths_must_be_relative_posix(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A backslash, an absolute path and a parent directory are findings on every host."""
    ds = req("DS-CDC-001", "check:pnr\\\\constraints\\\\a.sdc")
    ds += req("DS-CDC-002", "check:/etc/hosts")
    ds += req("DS-CDC-003", "check:../x.sdc")
    ds += req("DS-CDC-004", "check:C:/x.sdc")
    rc, out = run(tree(tmp_path, ds), capsys)
    assert rc == 1
    assert any("DS-CDC-001" in ln and "not allowed" in ln for ln in out)
    for rid in ("DS-CDC-002", "DS-CDC-003", "DS-CDC-004"):
        assert any(rid in ln and "relative path" in ln for ln in out), rid


def test_option_after_a_blank_line_is_missing(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """LaTeX does not read an option after a blank line, so the verify argument is missing."""
    ds = "\\begin{requirement}{DS-CDC-001}{T}\n\n[verify={review}]\nBody.\n\\end{requirement}\n"
    rc, out = run(tree(tmp_path, ds), capsys)
    assert rc == 1 and any("missing verify argument" in ln for ln in out)


def test_option_on_the_next_line_and_spaces_are_accepted(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """One newline or spaces between the arguments are fine, as for LaTeX."""
    ds = "\\begin{requirement} {DS-CDC-001} {T}\n  [verify={review}]\nBody.\n\\end{requirement}\n"
    rc, out = written(tree(tmp_path, ds), capsys)
    assert rc == 0, out


def test_duplicate_ledger_row_is_a_setup_error(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A second row for one ID could hide a retired row, so it is an error."""
    row = "DS-CDC-001\tretired\tdocs/manual/ds/ds.tex\n"
    ledger = cr.LEDGER_HEADER + "\n" + row + row.replace("retired", "active")
    root = tree(tmp_path, "Nothing.\n", ledger=ledger)
    rc, err = run_err(root, capsys)
    assert rc == 2
    assert "duplicate ledger row for DS-CDC-001" in err


def test_misplaced_id_is_not_written_to_the_ledger(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A DS ID in another book is a finding and does not use up the number."""
    root = tree(tmp_path, "Nothing.\n", {"docs/manual/tm/a.tex": req("DS-CDC-001")})
    rc, out = written(root, capsys)
    assert rc == 1 and any("belongs in docs/manual/ds/" in ln for ln in out)
    assert "DS-CDC-001" not in (root / cr.LEDGER).read_text(encoding="utf-8")


def git(root: Path, *args: str) -> None:
    """Run git in a synthetic repository."""
    done = subprocess.run(
        [
            "git",
            "-c",
            "user.name=t",
            "-c",
            "user.email=t@example.org",
            "-c",
            "commit.gpgsign=false",
            *args,
        ],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
    )
    assert done.returncode == 0, done.stderr.decode()


def committed(root: Path, ledger_rows: str, only_first: bool = False) -> Path:
    """Write a ledger, commit the tree and return the root."""
    ds = req("DS-CDC-001") + ("" if only_first else req("DS-CDC-002"))
    tree(root, ds, ledger=cr.LEDGER_HEADER + "\n" + ledger_rows)
    assert cr.main(["--root", str(root), "--write"]) == 0
    git(root, "init", "-q")
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "base")
    return root


ROWS = "DS-CDC-001\tactive\tdocs/manual/ds/ds.tex\nDS-CDC-002\tactive\tdocs/manual/ds/ds.tex\n"


def test_base_ref_accepts_an_unchanged_or_longer_ledger(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """The base comparison passes when rows are only added or retired."""
    root = committed(tmp_path, ROWS)
    assert run(root, capsys, "--base-ref", "HEAD")[0] == 0, "an unchanged tree"
    retired = ROWS.replace("DS-CDC-002\tactive", "DS-CDC-002\tretired")
    (root / cr.LEDGER).write_text(cr.LEDGER_HEADER + "\n" + retired, encoding="utf-8", newline="\n")
    (root / "docs/manual/ds/ds.tex").write_text(req("DS-CDC-001"), encoding="utf-8", newline="\n")
    rc, out = run(root, capsys, "--write", "--base-ref", "HEAD")
    assert rc == 0, out


def test_base_ref_finds_a_deleted_row(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A row of the base that is gone is a finding, although the file alone is clean."""
    root = committed(tmp_path, ROWS)
    (root / cr.LEDGER).write_text(
        cr.LEDGER_HEADER + "\n" + ROWS.splitlines()[0] + "\n", newline="\n"
    )
    (root / "docs/manual/ds/ds.tex").write_text(req("DS-CDC-001"), encoding="utf-8", newline="\n")
    assert run(root, capsys, "--write")[0] == 0, "the file alone is clean"
    rc, out = run(root, capsys, "--base-ref", "HEAD")
    assert rc == 1 and any("ledger row DS-CDC-002 of HEAD is missing" in ln for ln in out)


def test_base_ref_finds_a_retired_row_that_is_active_again(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """A retired row of the base cannot become active."""
    rows = ROWS.replace("DS-CDC-002\tactive", "DS-CDC-002\tretired")
    root = committed(tmp_path, rows, only_first=True)
    (root / "docs/manual/ds/ds.tex").write_text(req("DS-CDC-001"), encoding="utf-8", newline="\n")
    (root / cr.LEDGER).write_text(cr.LEDGER_HEADER + "\n" + ROWS, encoding="utf-8", newline="\n")
    rc, out = run(root, capsys, "--base-ref", "HEAD")
    assert rc == 1
    assert any("DS-CDC-002 was retired at HEAD and is active again" in ln for ln in out)


def test_base_ref_errors_are_setup_errors(tmp_path, capsys) -> None:  # type: ignore[no-untyped-def]
    """An unknown ref, or a ref without the ledger, exits with code 2 and says why."""
    root = committed(tmp_path, ROWS)
    rc, err = run_err(root, capsys, "--base-ref", "no-such-ref")
    assert rc == 2
    assert "cannot read docs/manual/common/requirement_ids.tsv at --base-ref no-such-ref" in err
    (root / cr.LEDGER).unlink()
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", "no ledger")
    rc, err = run_err(root, capsys, "--base-ref", "HEAD")
    assert rc == 2
    assert "at --base-ref HEAD" in err
