#!/usr/bin/env python3
"""Build the project books (ds, tm, um, cr) to PDF with LuaLaTeX.

The books reference each other through xr-hyper. The driver compiles every
book in rounds until all .aux files stop changing (at most 5 rounds), so
cross-book references settle. Aux files go to <outdir>/aux/<book>/ and the
PDFs go to <outdir>/<book>.pdf. The default outdir is docs/manual/_build.

Usage:
    python tools/docs/build_books.py [ds tm um cr] [--outdir DIR]
        [--engine lualatex] [--strict] [--keep-aux] [--timeout SECONDS]

Exit codes:
    0  clean build
    1  an error, an undefined reference, a duplicate label or a missing
       glossary entry remains (with --strict: also an overfull box > 10pt)
    2  setup error (no book source)
    3  the engine is not installed
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BOOKS = ("ds", "tm", "um", "cr")
MAX_ROUNDS = 5
OVERFULL_LIMIT = 10.0

_UNDEF = re.compile(r"(?:Reference|Citation|Hyper reference) [`'\"]([^`'\"]+)['\"] on page")
_MULTI = re.compile(r"Label [`'\"]([^`'\"]+)['\"] multiply defined")
_GLOSS = re.compile(r"[Gg]lossary entry [`'\"]+([^`'\"\s]+)['\"]* (?:has not been|is not) defined")
_ERR_BANG = re.compile(r"^! (.+)$")
_ERR_FLE = re.compile(r"^(?:[A-Za-z]:)?[^\s:][^:\n]*\.\w+:\d+: (.+)$")
_OVERFULL = re.compile(r"Overfull \\hbox \(([0-9.]+)pt too wide\)")


def parse_log(text: str) -> dict[str, list]:
    """Extract the problems from the text of a LaTeX log."""
    res: dict[str, list] = {"undefined": [], "multiply": [], "glossary": [], "errors": []}
    res["overfull"] = []
    for raw in text.splitlines():
        line = raw.strip("\r")
        for rx, key in ((_UNDEF, "undefined"), (_MULTI, "multiply"), (_GLOSS, "glossary")):
            m = rx.search(line)
            if m and m.group(1) not in res[key]:
                res[key].append(m.group(1))
        m = _ERR_BANG.match(line) or _ERR_FLE.match(line)
        if m and "Overfull" not in line and "Underfull" not in line:
            res["errors"].append(m.group(1))
        m = _OVERFULL.search(line)
        if m and float(m.group(1)) > OVERFULL_LIMIT:
            res["overfull"].append(float(m.group(1)))
    return res


def git_revision() -> str:
    """Return the output of git describe, or 'unversioned'."""
    try:
        out = subprocess.run(
            ["git", "describe", "--always", "--dirty"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=30,
            stdin=subprocess.DEVNULL,
        )
        rev = out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        rev = ""
    return re.sub(r"[^A-Za-z0-9.+-]", "-", rev) or "unversioned"


def is_miktex(engine: str) -> bool:
    """Tell whether the engine comes from MiKTeX."""
    try:
        out = subprocess.run(
            [engine, "--version"],
            capture_output=True,
            text=True,
            timeout=60,
            stdin=subprocess.DEVNULL,
        )
        return "miktex" in (out.stdout + out.stderr).lower()
    except (OSError, subprocess.SubprocessError):
        return False


class Builder:
    """Compile the books and collect the problems."""

    def __init__(self, args: argparse.Namespace, manual: Path, outdir: Path) -> None:
        self.args = args
        self.manual = manual
        self.outdir = outdir
        self.rev = git_revision()
        self.miktex = is_miktex(args.engine)
        self.failed: dict[str, str] = {}
        self.ran: set[str] = set()

    def aux_dir(self, book: str) -> Path:
        """Return the working directory of a book."""
        return self.outdir / "aux" / book

    def run_once(self, book: str) -> bool:
        """Run the engine once for a book. Return True on success."""
        wd = self.aux_dir(book)
        wd.mkdir(parents=True, exist_ok=True)
        self.ran.add(book)
        dirs = [(self.manual / "common").as_posix(), (self.manual / book).as_posix()]
        cmd = [
            self.args.engine,
            "-interaction=nonstopmode",
            "-halt-on-error",
            "-file-line-error",
            f"-jobname={book}",
        ]
        env = dict(os.environ)
        if self.miktex:
            cmd += [f"-include-directory={d}" for d in dirs]
        else:
            env["TEXINPUTS"] = os.pathsep.join(dirs) + os.pathsep
        cmd.append(f"\\def\\cvtrevision{{{self.rev}}}\\def\\cvtauxroot{{..}}\\input{{{book}.tex}}")
        try:
            proc = subprocess.run(
                cmd,
                cwd=wd,
                env=env,
                stdin=subprocess.DEVNULL,
                capture_output=True,
                timeout=self.args.timeout,
            )
        except subprocess.TimeoutExpired:
            self.failed[book] = f"timeout after {self.args.timeout} s"
            self.print_tail(book)
            return False
        self.run_makeindex(book)
        if proc.returncode != 0:
            self.failed[book] = f"engine exit code {proc.returncode}"
            self.print_tail(book)
            return False
        return True

    def run_makeindex(self, book: str) -> None:
        """Run makeindex for an index that imakeidx could not run itself."""
        wd = self.aux_dir(book)
        for idx in wd.glob("*.idx"):
            ind = idx.with_suffix(".ind")
            if idx.stat().st_size > 0 and (
                not ind.exists() or ind.stat().st_mtime < idx.stat().st_mtime
            ):
                subprocess.run(
                    ["makeindex", "-q", "-o", ind.name, idx.name],
                    cwd=wd,
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    timeout=self.args.timeout,
                    check=False,
                )

    def log_text(self, book: str) -> str:
        """Return the text of the log of a book."""
        log = self.aux_dir(book) / f"{book}.log"
        return log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""

    def print_tail(self, book: str) -> None:
        """Print the last 30 lines of the log."""
        print(f"--- {book}: {self.failed[book]}; last 30 log lines ---")
        print("\n".join(self.log_text(book).splitlines()[-30:]))

    def aux_hash(self, book: str) -> str:
        """Return a hash of the aux file."""
        aux = self.aux_dir(book) / f"{book}.aux"
        return hashlib.sha256(aux.read_bytes()).hexdigest() if aux.exists() else ""

    def build(self, books: list[str]) -> int:
        """Build all books in rounds. Return the number of rounds."""
        prev: dict[str, str] = {}
        for rnd in range(1, MAX_ROUNDS + 1):
            for book in books:
                if not self.run_once(book):
                    return rnd
            cur = {b: self.aux_hash(b) for b in books}
            print(f"round {rnd}: {len(books)} book(s) compiled")
            if cur == prev:
                return rnd
            prev = cur
        print(f"warning: aux files still change after {MAX_ROUNDS} rounds")
        return MAX_ROUNDS


def main(argv: list[str] | None = None) -> int:
    """Run the command line tool."""
    ap = argparse.ArgumentParser(description="Build the project books.")
    ap.add_argument("books", nargs="*", help="books to build (default: all)")
    ap.add_argument("--outdir", type=Path, default=None)
    ap.add_argument("--manual", type=Path, default=REPO / "docs" / "manual")
    ap.add_argument("--engine", default="lualatex")
    ap.add_argument("--strict", action="store_true")
    ap.add_argument("--keep-aux", action="store_true")
    ap.add_argument("--timeout", type=int, default=600)
    args = ap.parse_args(argv)

    unknown = [b for b in args.books if b not in BOOKS]
    if unknown:
        ap.error(f"unknown book(s): {', '.join(unknown)}")
    manual = args.manual.resolve()
    outdir = (args.outdir or manual / "_build").resolve()
    wanted = [b for b in BOOKS if b in (args.books or BOOKS)]
    if not all((manual / b / f"{b}.tex").exists() for b in wanted):
        print(f"build_books: book sources not found under {manual}", file=sys.stderr)
        return 2
    if shutil.which(args.engine) is None:
        print(f"build_books: engine '{args.engine}' is not installed", file=sys.stderr)
        return 3

    bld = Builder(args, manual, outdir)
    # A book that is not requested but has no aux file yet is built too,
    # so the cross-book references can resolve.
    books = [b for b in BOOKS if b in wanted or not (bld.aux_dir(b) / f"{b}.aux").exists()]
    start = time.monotonic()
    rounds = bld.build(books)
    elapsed = time.monotonic() - start

    bad = bool(bld.failed)
    for book in books:
        if book in bld.failed:
            print(f"{book}: FAILED ({bld.failed[book]})")
            continue
        if book not in bld.ran:
            print(f"{book}: not built")
            continue
        found = parse_log(bld.log_text(book))
        pdf = bld.aux_dir(book) / f"{book}.pdf"
        if pdf.exists():
            outdir.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(pdf, outdir / f"{book}.pdf")
        print(
            f"{book}: undefined={len(found['undefined'])} "
            f"multiply-defined={len(found['multiply'])} "
            f"glossary={len(found['glossary'])} errors={len(found['errors'])} "
            f"overfull>{OVERFULL_LIMIT:g}pt={len(found['overfull'])}"
        )
        for key, label in (
            ("undefined", "undefined reference"),
            ("multiply", "multiply defined label"),
            ("glossary", "missing glossary entry"),
            ("errors", "error"),
        ):
            for item in found[key]:
                print(f"  {label}: {item}")
        if any(found[k] for k in ("undefined", "multiply", "glossary", "errors")):
            bad = True
        if args.strict and found["overfull"]:
            bad = True

    print(f"build_books: {rounds} round(s), {elapsed:.1f} s, revision {bld.rev}")
    if not args.keep_aux and not bad:
        for book in wanted:
            shutil.rmtree(bld.aux_dir(book), ignore_errors=True)
        try:
            (outdir / "aux").rmdir()
        except OSError:
            pass
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
