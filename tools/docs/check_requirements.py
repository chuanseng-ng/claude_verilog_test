#!/usr/bin/env python3
"""Check the requirements of the Design Specification and write their tables.

Needs no TeX. It reads docs/manual/**/*.tex and finds each requirement environment:
    \\begin{requirement}{DS-CDC-020}{Short title}[verify={test:tb/x.py::name; review}]
It checks the ID form, the unique IDs, the \\reqref targets and each verify reference.
The ledger docs/manual/common/requirement_ids.tsv keeps every ID that was ever used.
The area EXAMPLE is only for the User Manual and is not in the ledger or the tables.
With --base-ref the ledger is also compared with its version at a git ref: a row of the
base must still exist, and a retired row must stay retired.

Usage:
    python tools/docs/check_requirements.py [--check | --write] [--root DIR] [-v]
        [--base-ref REF]

Exit codes: 0 clean, 1 findings or drift, 2 setup error (including an unreadable base ref).
"""

from __future__ import annotations

import argparse
import ast
import os
import re
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_doc_labels import (  # noqa: E402
    REQ_BEGIN,
    Checker,
    blank_verbatim,
    brace_arg,
    line_of,
    strip_comments,
)
from doc_tables import longtable  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
LEDGER = Path("docs/manual/common/requirement_ids.tsv")
LEDGER_HEADER = "id\tstatus\tfirst_file"
TABLE_DIR = Path("docs/manual/ds/generated")
ID_RE = re.compile(r"^DS-([A-Z][A-Z0-9]{1,7})-(\d{3})$")
EXAMPLE_AREA = "EXAMPLE"
METHODS = ("test", "mutation", "check", "formal")
TABLE_COLS = ("p{23mm}", "p{52mm}", "p{68mm}")
GIT_LOCATION_VARS = ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")
_REQREF = re.compile(r"\\reqref\{([^{}]*)\}")

Row = tuple[str, str, str]


@dataclass
class Requirement:
    """One requirement environment found in a .tex file."""

    id: str
    title: str
    refs: list[str]
    path: str
    line: int


@dataclass
class State:
    """The facts and findings of one run."""

    root: Path
    findings: list[str] = field(default_factory=list)
    reqs: list[Requirement] = field(default_factory=list)
    reqrefs: list[tuple[str, int, str]] = field(default_factory=list)
    _ast: dict[Path, ast.Module | None] = field(default_factory=dict)

    def err(self, path: str, line: int, msg: str) -> None:
        """Record a finding."""
        self.findings.append(f"{path}:{line}: {msg}")


def parse_optional(text: str, pos: int) -> tuple[str | None, int]:
    """Read the optional [..] argument at pos, as LaTeX does.

    Spaces, tabs and one newline may come first. A blank line is a paragraph break.
    """
    i = pos
    newlines = 0
    while i < len(text) and text[i] in " \t\n":
        newlines += text[i] == "\n"
        i += 1
    if newlines > 1 or i >= len(text) or text[i] != "[":
        return None, pos
    depth = 0
    j = i + 1
    while j < len(text):
        c = text[j]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "]" and depth == 0:
            return text[i + 1 : j], j + 1
        j += 1
    return text[i + 1 :], len(text)


def scan(state: State) -> None:
    """Collect the requirements and the \\reqref uses of all .tex files."""
    for path in Checker(state.root).tex_files():
        rel = path.relative_to(state.root).as_posix()
        if rel.startswith(TABLE_DIR.as_posix() + "/requirements-"):
            continue  # a generated table is output, not source
        text = blank_verbatim(strip_comments(path.read_text(encoding="utf-8", errors="replace")))
        for m in REQ_BEGIN.finditer(text):
            rid = m.group(1).strip()
            line = line_of(text, m.start())
            raw_title = brace_arg(text, m.end())
            title = " ".join(raw_title.split())
            arg, _ = parse_optional(text, m.end() + len(raw_title) + 1)
            refs: list[str] = []
            if arg is None:
                state.err(rel, line, f"{rid}: missing verify argument")
            else:
                vm = re.match(r"^\s*verify\s*=\s*\{(.*)\}\s*$", arg, re.S)
                if not vm:
                    state.err(
                        rel,
                        line,
                        f"{rid}: the option must be verify={{...}}; "
                        "a body that starts with '[' is read as the option",
                    )
                else:
                    refs = [
                        r.strip() for r in re.sub(r"\s+", " ", vm.group(1)).split(";") if r.strip()
                    ]
                    if not refs:
                        state.err(rel, line, f"{rid}: the verify argument is empty")
            state.reqs.append(Requirement(rid, title, refs, rel, line))
        for m in _REQREF.finditer(text):
            state.reqrefs.append((rel, line_of(text, m.start()), m.group(1).strip()))


def parsed(state: State, path: Path) -> ast.Module | None:
    """Return the syntax tree of a Python file, or None if it cannot be read."""
    if path not in state._ast:
        try:
            state._ast[path] = ast.parse(path.read_text(encoding="utf-8"))
        except (OSError, SyntaxError, UnicodeDecodeError):
            state._ast[path] = None
    return state._ast[path]


def top_level_defs(tree: ast.Module) -> set[str]:
    """Return the names of the top-level functions of a module."""
    return {n.name for n in tree.body if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)}


def string_literals(tree: ast.Module) -> set[str]:
    """Return the string constants of a module. A comment is not a constant."""
    return {
        n.value for n in ast.walk(tree) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    }


def bad_path(rel: str) -> bool:
    """Return True for a path that is not a relative POSIX path without '..'."""
    return (
        not rel
        or "\\" in rel
        or rel.startswith("/")
        or re.match(r"^[A-Za-z]:", rel) is not None
        or ".." in rel.split("/")
    )


def check_ref(state: State, req: Requirement, ref: str) -> None:
    """Check one verify reference."""
    where = (req.path, req.line)
    if re.search(r"[#%{}\\]", ref):
        state.err(*where, f"{req.id}: reference '{ref}' has a character that is not allowed")
        return
    if ref == "review":
        return
    method, sep, rest = ref.partition(":")
    if not sep or method not in METHODS or not rest:
        state.err(*where, f"{req.id}: unknown reference form '{ref}'")
        return
    if method in ("test", "mutation"):
        rel, sep2, name = rest.partition("::")
        if not sep2 or not name or not rel:
            state.err(*where, f"{req.id}: '{ref}' needs <path>::<name>")
            return
    else:
        rel, name = rest, ""
    if bad_path(rel):
        state.err(*where, f"{req.id}: '{rel}' is not a relative path with / separators")
        return
    path = state.root / rel
    if not path.is_file():
        state.err(*where, f"{req.id}: file '{rel}' does not exist")
        return
    if method == "test":
        if not rel.startswith("tb/") or not rel.endswith(".py"):
            state.err(*where, f"{req.id}: a test file must be a Python file under tb/")
            return
        tree = parsed(state, path)
        if tree is None:
            state.err(*where, f"{req.id}: cannot parse '{rel}'")
        elif name not in top_level_defs(tree):
            state.err(*where, f"{req.id}: '{rel}' has no function '{name}'")
    elif method == "mutation":
        tree = parsed(state, path) if rel.endswith(".py") else None
        if tree is None:
            state.err(*where, f"{req.id}: a mutation file must be a Python file that parses")
        elif name not in string_literals(tree):
            state.err(*where, f"{req.id}: '{rel}' has no string literal '{name}'")


def check_requirements(state: State) -> dict[str, Requirement]:
    """Check ID form, placement, uniqueness, \\reqref targets and verify references."""
    seen: dict[str, Requirement] = {}
    for req in state.reqs:
        m = ID_RE.match(req.id)
        if not m:
            state.err(req.path, req.line, f"bad requirement ID '{req.id}'")
        else:
            book_dir = "docs/manual/um/" if m.group(1) == EXAMPLE_AREA else "docs/manual/ds/"
            if not req.path.startswith(book_dir):
                state.err(req.path, req.line, f"{req.id}: this ID belongs in {book_dir}")
        if req.id in seen:
            first = seen[req.id]
            where = f"first at {first.path}:{first.line}"
            state.err(req.path, req.line, f"duplicate requirement ID {req.id} ({where})")
        else:
            seen[req.id] = req
        for ref in req.refs:
            check_ref(state, req, ref)
    for rel, line, rid in state.reqrefs:
        if rid not in seen:
            state.err(rel, line, f"reqref to undefined requirement '{rid}'")
    return seen


def parse_ledger(text: str, name: str) -> list[Row]:
    """Return the rows of a ledger text. Raise ValueError when the form is bad."""
    lines = text.replace("\r\n", "\n").split("\n")
    if lines[0] != LEDGER_HEADER:
        raise ValueError(f"{name}: the header must be id, status, first_file separated by tabs")
    rows: list[Row] = []
    seen: set[str] = set()
    for n, line in enumerate(lines[1:], 2):
        if not line.strip() or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) != 3 or cols[1] not in ("active", "retired") or not ID_RE.match(cols[0]):
            raise ValueError(f"{name}:{n}: a row is 'ID<TAB>active|retired<TAB>file'")
        if cols[0] in seen:
            raise ValueError(f"{name}:{n}: duplicate ledger row for {cols[0]}")
        seen.add(cols[0])
        rows.append((cols[0], cols[1], cols[2]))
    return rows


def read_ledger(state: State) -> list[Row]:
    """Return the rows of the ledger file, or no row when the file does not exist."""
    path = state.root / LEDGER
    if not path.exists():
        return []
    return parse_ledger(path.read_bytes().decode("utf-8"), LEDGER.as_posix())


def read_base_ledger(root: Path, ref: str) -> list[Row]:
    """Return the rows of the ledger at a git ref. Raise ValueError when it cannot be read."""
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_VARS}
    try:
        res = subprocess.run(
            ["git", "-C", str(root), "show", f"{ref}:{LEDGER.as_posix()}"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            env=env,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ValueError(f"cannot run git for --base-ref {ref}: {exc}") from exc
    if res.returncode != 0:
        why = res.stderr.decode("utf-8", "replace").strip()
        raise ValueError(f"cannot read {LEDGER.as_posix()} at --base-ref {ref}: {why}")
    return parse_ledger(res.stdout.decode("utf-8"), f"{ref}:{LEDGER.as_posix()}")


def ledger_text(rows: list[Row]) -> str:
    """Return the text of the ledger."""
    return "\n".join([LEDGER_HEADER, *("\t".join(r) for r in rows)]) + "\n"


def tracked(seen: dict[str, Requirement]) -> dict[str, Requirement]:
    """Return the requirements of the ledger scope.

    These have a valid ID in the Design Specification. A misplaced ID is a finding and stays out.
    """
    out = {}
    for rid, req in seen.items():
        m = ID_RE.match(rid)
        if m and m.group(1) != EXAMPLE_AREA and req.path.startswith("docs/manual/ds/"):
            out[rid] = req
    return out


def check_ledger(state: State, seen: dict[str, Requirement], write: bool) -> list[Row]:
    """Compare TeX and ledger. Return the ledger rows to keep (new IDs appended)."""
    rows = read_ledger(state)
    status = {i: s for i, s, _ in rows}
    scope = tracked(seen)
    new = sorted(i for i in scope if i not in status)
    for rid in sorted(scope):
        req = scope[rid]
        if status.get(rid) == "retired":
            state.err(req.path, req.line, f"retired ID {rid} is used again")
    if write:
        rows = rows + [(i, "active", scope[i].path) for i in new]
    else:
        for rid in new:
            state.err(scope[rid].path, scope[rid].line, f"{rid} is not in the ledger; run --write")
    for rid, st, first in rows:
        if st == "active" and rid not in scope:
            state.err(
                LEDGER.as_posix(),
                1,
                f"active ID {rid} is not in a .tex file; mark it retired ({first})",
            )
    return rows


def check_base(state: State, rows: list[Row], ref: str) -> None:
    """Compare the ledger with its version at a git ref. The ledger only grows."""
    now = {i: s for i, s, _ in rows}
    for rid, st, _ in read_base_ledger(state.root, ref):
        if rid not in now:
            state.err(LEDGER.as_posix(), 1, f"ledger row {rid} of {ref} is missing")
        elif st == "retired" and now[rid] == "active":
            state.err(
                LEDGER.as_posix(), 1, f"ledger row {rid} was retired at {ref} and is active again"
            )


def ref_cell(ref: str) -> str:
    """Return a verify reference for the table: the method in bold, then the target."""
    method, sep, rest = ref.partition(":")
    if ref == "review" or not sep:
        return "\\textbf{review}"
    return f"\\textbf{{{method}}} \\code{{{rest}}}"


def render_table(area: str, reqs: list[Requirement]) -> str:
    """Return the text of requirements-<area>.tex."""
    rows = []
    for r in sorted(reqs, key=lambda x: x.id):
        verified = " \\newline ".join(ref_cell(x) for x in r.refs)
        rows.append([f"\\reqref{{{r.id}}}", r.title, verified])
    table = longtable(
        TABLE_COLS,
        f"Requirements of area {area} and their verification",
        f"tab:ds:req:{area.lower()}-map",
        ["ID", "Requirement", "Verified by"],
        rows,
    )
    head = "% Generated by tools/docs/check_requirements.py from the requirement environments. "
    return head + "Do not edit.\n" + table + "\n"


def tables(seen: dict[str, Requirement]) -> dict[str, str]:
    """Return the text of each generated table, by file name."""
    areas: dict[str, list[Requirement]] = defaultdict(list)
    for rid, req in tracked(seen).items():
        areas[ID_RE.match(rid).group(1)].append(req)  # type: ignore[union-attr]
    return {f"requirements-{a.lower()}.tex": render_table(a, rs) for a, rs in sorted(areas.items())}


def sync_file(state: State, path: Path, text: str, write: bool) -> None:
    """Write a generated file, or report that it is stale."""
    rel = path.relative_to(state.root).as_posix()
    if write:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return
    current = path.read_bytes().replace(b"\r\n", b"\n") if path.exists() else None
    if current != text.encode("utf-8"):
        state.err(rel, 1, "is out of date; run check_requirements.py --write")


def main(argv: list[str] | None = None) -> int:
    """Run the command line tool."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="check only (the default)")
    mode.add_argument("--write", action="store_true", help="append new IDs, write the tables")
    ap.add_argument("--base-ref", help="a git ref; compare the ledger with its version there")
    ap.add_argument("--root", type=Path, default=REPO)
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    if not (root / "docs" / "manual").is_dir():
        print(f"check_requirements: {root / 'docs' / 'manual'} not found", file=sys.stderr)
        return 2
    state = State(root)
    scan(state)
    seen = check_requirements(state)
    try:
        rows = check_ledger(state, seen, args.write)
        if args.base_ref:
            check_base(state, rows, args.base_ref)
    except (ValueError, UnicodeDecodeError) as exc:
        print(f"check_requirements: {exc}", file=sys.stderr)
        return 2
    outputs = tables(seen)
    if args.write:
        sync_file(state, root / LEDGER, ledger_text(rows), True)
    for name, text in outputs.items():
        sync_file(state, root / TABLE_DIR / name, text, args.write)
    table_dir = root / TABLE_DIR
    if table_dir.is_dir():
        for path in sorted(table_dir.glob("requirements-*.tex")):
            if path.name not in outputs:
                if args.write:
                    path.unlink()
                else:
                    state.err(path.relative_to(root).as_posix(), 1, "no requirement uses this area")
    for finding in state.findings:
        print(finding)
    if args.verbose:
        refs = sum(1 for r in state.reqs for x in r.refs if x != "review")
        review_only = sum(1 for r in state.reqs if r.refs and all(x == "review" for x in r.refs))
        print(
            f"check_requirements: {len(state.reqs)} requirements, {refs} refs, "
            f"{review_only} review-only, {len(state.findings)} finding(s)"
        )
    return 1 if state.findings else 0


if __name__ == "__main__":
    sys.exit(main())
