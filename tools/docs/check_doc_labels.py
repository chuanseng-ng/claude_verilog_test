#!/usr/bin/env python3
"""Check the label scheme and the citations of the LaTeX books.

Needs no TeX. It reads docs/manual/**/*.tex and checks these rules:
  - every label is <book>:<kind>:<slug> (book ds, tm, um, cr);
  - no label is defined twice;
  - every cross-reference points to a defined label;
  - a requirement defines the label derived from its ID (DS-CDC-020 gives
    ds:req:cdc-020) and a \\reqref points to such a label;
  - every source-file comment that cites labels (the word Doc, a colon and
    labels) names defined labels;
  - every row of common/path_map.tsv has a defined label and an existing file;
  - every path in a \\src{...} macro is a repository file or directory;
  - common/labels.tsv equals the generated label list.

Usage:
    python tools/docs/check_doc_labels.py [--root DIR] [--write-labels] [-v]

Exit codes: 0 clean, 1 findings (printed as path:line: message), 2 setup error.
"""

from __future__ import annotations

import argparse
import fnmatch
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BOOKS = ("ds", "tm", "um", "cr")
KINDS = (
    "part ch mod pd suite dec defect run fix status caveat guide flow mm inv app req arc".split()
)
SLUG = r"[a-z0-9][a-z0-9-]*"
LABEL_RE = re.compile(
    rf"^(?:(?:fig|tab|lst|eq):)?(?:{'|'.join(BOOKS)}):(?:{'|'.join(KINDS)}):{SLUG}(?::{SLUG})*$"
)
# A token that looks like a label of this scheme (book prefix and parts).
LOOKS_RE = rf"(?:{'|'.join(BOOKS)}):{SLUG}(?::{SLUG})+"
CITE_RE = re.compile(
    rf"^\s*(?:/\*+|//+|#+|--|;|\*)?\s*Doc:\s*({LOOKS_RE}(?:\s*,\s*{LOOKS_RE})*)\s*(?:\*/)?\s*$"
)
CITE_SKIP = ("docs/manual/", "memory/", ".beads/", "micro_p/", "pnr/commercial/")
MAP_HEADER = "old_path\tnew_file\tlabel"
LABELS_HEADER = "label\tfile\tline\ttitle"

_LABEL = re.compile(r"\\label\{([^{}]*)\}")
_REF = re.compile(r"\\(cref|Cref|ref|autoref|pageref|nameref|vref)\*?\{([^{}]*)\}")
_REQ_LABEL = re.compile(r"^[a-z]+:req:")
_REQ_CMDS = ("cref", "Cref", "autoref", "vref")
_REQREF = re.compile(r"\\reqref\{([^{}]*)\}")
# The start of a requirement as LaTeX reads it: spaces may separate the arguments.
# The group is the ID. The match ends after the opening brace of the title.
REQ_BEGIN = re.compile(r"\\begin\{requirement\}\s*\{([^{}]*)\}\s*\{")
REQ_ID_RE = re.compile(r"^[A-Z]+-[A-Z0-9]+-\d{3}$")
_SRC = re.compile(r"\\src\{([^{}]*)\}")
_SECT = re.compile(r"\\(?:part|chapter|section|subsection|subsubsection)\*?(?:\[[^\]]*\])?\{")
_VERB_ENV = re.compile(
    r"\\begin\{(lstlisting|verbatim|Verbatim|logblock|minted)\*?\}.*?\\end\{\1\*?\}", re.S
)
_VERB_INLINE = re.compile(r"\\(?:verb\*?|lstinline)(?:\[[^\]]*\])?(.)(.*?)\1")
_TEXT_SKIP = {".pdf", ".png", ".jpg", ".gz", ".zip", ".gds", ".oas", ".bin", ".so", ".a", ".o"}


def strip_comments(text: str) -> str:
    """Remove TeX comments. A percent sign after an odd run of backslashes stays."""
    out = []
    for line in text.split("\n"):
        i = 0
        while i < len(line):
            if line[i] == "%":
                n = 0
                j = i - 1
                while j >= 0 and line[j] == "\\":
                    n += 1
                    j -= 1
                if n % 2 == 0:
                    line = line[:i]
                    break
            i += 1
        out.append(line)
    return "\n".join(out)


def blank_verbatim(text: str) -> str:
    """Replace verbatim material by blank lines so line numbers stay correct."""

    def blank(m: re.Match) -> str:
        return "\n" * m.group(0).count("\n")

    return _VERB_INLINE.sub(blank, _VERB_ENV.sub(blank, text))


def brace_arg(text: str, start: int) -> str:
    """Return the text of the braced group whose '{' ends just before start."""
    depth = 1
    i = start
    while i < len(text) and depth:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
        i += 1
    return text[start : i - 1] if depth == 0 else text[start:i]


def req_label(req_id: str) -> str:
    """Return the label derived from a requirement ID: DS-CDC-020 gives ds:req:cdc-020."""
    book, _, slug = req_id.lower().partition("-")
    return f"{book}:req:{slug}"


def line_of(text: str, pos: int) -> int:
    """Return the 1-based line number of an offset."""
    return text.count("\n", 0, pos) + 1


class Checker:
    """Collect the findings for one repository root."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.manual = root / "docs" / "manual"
        self.findings: list[str] = []
        self.labels: dict[str, list[tuple[str, int, str]]] = {}
        self._files: list[str] | None = None

    def err(self, path: str, line: int, msg: str) -> None:
        """Record a finding."""
        self.findings.append(f"{path}:{line}: {msg}")

    def repo_files(self) -> list[str]:
        """Return tracked and untracked-but-not-ignored files (posix paths)."""
        if self._files is not None:
            return self._files
        files: list[str] | None = None
        try:
            top = subprocess.run(
                ["git", "-C", str(self.root), "rev-parse", "--show-toplevel"],
                capture_output=True,
                text=True,
                timeout=60,
                stdin=subprocess.DEVNULL,
            )
            if top.returncode == 0 and Path(top.stdout.strip()).resolve() == self.root.resolve():
                ls = subprocess.run(
                    [
                        "git",
                        "-C",
                        str(self.root),
                        "ls-files",
                        "-z",
                        "--cached",
                        "--others",
                        "--exclude-standard",
                    ],
                    capture_output=True,
                    timeout=120,
                    stdin=subprocess.DEVNULL,
                )
                if ls.returncode == 0:
                    names = ls.stdout.decode("utf-8", "replace").split("\0")
                    files = sorted({n for n in names if n and (self.root / n).exists()})
        except (OSError, subprocess.SubprocessError):
            files = None
        if files is None:
            files = sorted(
                p.relative_to(self.root).as_posix()
                for p in self.root.rglob("*")
                if p.is_file() and ".git" not in p.relative_to(self.root).parts
            )
        self._files = files
        return files

    def tex_files(self) -> list[Path]:
        """Return the .tex files of the books, without the build directory."""
        return sorted(
            p
            for p in self.manual.rglob("*.tex")
            if "_build" not in p.relative_to(self.manual).parts
        )

    def rel(self, path: Path) -> str:
        """Return a path relative to the root in posix form."""
        return path.relative_to(self.root).as_posix()

    def scan_tex(self) -> None:
        """Collect labels, references and \\src paths."""
        self.refs: list[tuple[str, int, str]] = []
        self.srcs: list[tuple[str, int, str]] = []
        for path in self.tex_files():
            rel = self.rel(path)
            text = blank_verbatim(
                strip_comments(path.read_text(encoding="utf-8", errors="replace"))
            )
            titles = [
                (m.start(), re.sub(r"\s+", " ", brace_arg(text, m.end())).strip())
                for m in _SECT.finditer(text)
            ]
            for m in _LABEL.finditer(text):
                title = ""
                for pos, name in titles:
                    if pos < m.start():
                        title = name
                    else:
                        break
                if not title:
                    # A file with no heading (a generated table): use the caption on the same line.
                    start = text.rfind("\n", 0, m.start()) + 1
                    cap = re.search(r"\\caption\{", text[start : m.start()])
                    if cap:
                        title = " ".join(brace_arg(text, start + cap.end()).split())
                self.labels.setdefault(m.group(1), []).append(
                    (rel, line_of(text, m.start()), title)
                )
            for m in REQ_BEGIN.finditer(text):
                rid = m.group(1).strip()
                if not REQ_ID_RE.match(rid):
                    continue  # check_requirements.py reports a bad ID
                title = " ".join(brace_arg(text, m.end()).split())
                self.labels.setdefault(req_label(rid), []).append(
                    (rel, line_of(text, m.start()), f"{rid} {title}".strip())
                )
            for m in _REF.finditer(text):
                for name in m.group(2).split(","):
                    name = name.strip()
                    if not name:
                        continue
                    line = line_of(text, m.start())
                    self.refs.append((rel, line, name))
                    if m.group(1) in _REQ_CMDS and _REQ_LABEL.match(name):
                        self.err(
                            rel, line, f"use reqref, not {m.group(1)}, for requirement '{name}'"
                        )
            for m in _REQREF.finditer(text):
                name = m.group(1).strip()
                self.refs.append((rel, line_of(text, m.start()), req_label(name)))
            for m in _SRC.finditer(text):
                self.srcs.append((rel, line_of(text, m.start()), m.group(1).strip()))

    def check_labels(self) -> None:
        """Apply the label scheme and the uniqueness rule."""
        for label, places in sorted(self.labels.items()):
            for rel, line, _ in places:
                if not LABEL_RE.match(label):
                    self.err(rel, line, f"label '{label}' does not follow the scheme")
            for rel, line, _ in places[1:]:
                first = places[0]
                self.err(rel, line, f"duplicate label '{label}' (first at {first[0]}:{first[1]})")
        for rel, line, name in self.refs:
            if name not in self.labels:
                self.err(rel, line, f"reference to undefined label '{name}'")

    def check_src(self) -> None:
        """Check the paths in \\src macros."""
        files = self.repo_files()
        moved = self.moved_paths()
        for rel, line, raw in self.srcs:
            path = raw.replace("\\_", "_").replace("\\", "")
            # Historical text may cite "file:line" or "file:first-last"; the file must exist.
            path = re.sub(r":\d+(?:-\d+)?$", "", path)
            if "*" in path or "?" in path:
                ok = any(fnmatch.fnmatch(f, path) for f in files)
            elif path.endswith("/"):
                ok = any(f.startswith(path) for f in files)
            else:
                ok = path in files or any(f.startswith(path + "/") for f in files)
            if not ok and path in moved:
                ok = True  # a moved document: path_map.tsv names its new label
            if not ok:
                self.err(rel, line, f"\\src path '{path}' is not a repository file or directory")

    def moved_paths(self) -> set[str]:
        """Old paths of the documents that moved into the books (first column of path_map.tsv)."""
        path = self.manual / "common" / "path_map.tsv"
        if not path.exists():
            return set()
        rows = path.read_text(encoding="utf-8").split("\n")[1:]
        return {r.split("\t")[0] for r in rows if r.strip() and not r.startswith("#")}

    def check_citations(self) -> None:
        """Check the Doc comment lines of the source files."""
        for name in self.repo_files():
            if name.startswith(CITE_SKIP) or Path(name).suffix.lower() in _TEXT_SKIP:
                continue
            path = self.root / name
            try:
                if path.stat().st_size > 2_000_000:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            if b"\0" in data or b"Doc:" not in data:
                continue
            for n, line in enumerate(data.decode("utf-8", "replace").split("\n"), 1):
                if "Doc:" not in line:
                    continue
                m = CITE_RE.match(line)
                if not m:
                    continue
                for lab in re.split(r"\s*,\s*", m.group(1)):
                    if lab not in self.labels:
                        self.err(name, n, f"Doc citation names undefined label '{lab}'")

    def check_path_map(self) -> None:
        """Check path_map.tsv."""
        path = self.manual / "common" / "path_map.tsv"
        rel = self.rel(path)
        if not path.exists():
            self.err(rel, 1, "file is missing")
            return
        lines = path.read_text(encoding="utf-8").split("\n")
        if lines[0] != MAP_HEADER:
            self.err(rel, 1, "header must be old_path, new_file, label separated by tabs")
        for n, line in enumerate(lines[1:], 2):
            if not line.strip() or line.startswith("#"):
                continue
            cols = line.split("\t")
            if len(cols) != 3:
                self.err(rel, n, "a row needs 3 tab-separated columns")
                continue
            _, new_file, label = cols
            if label not in self.labels:
                self.err(rel, n, f"label '{label}' is not defined")
            if not (self.root / new_file).exists():
                self.err(rel, n, f"new file '{new_file}' does not exist")

    def render_labels(self) -> str:
        """Return the text of labels.tsv."""
        rows = []
        for label in sorted(self.labels):
            for rel, line, title in sorted(self.labels[label]):
                rows.append(f"{label}\t{rel}\t{line}\t{title.replace(chr(9), ' ')}")
        return "\n".join([LABELS_HEADER, *rows]) + "\n"

    def check_labels_tsv(self, write: bool) -> None:
        """Compare or write labels.tsv."""
        path = self.manual / "common" / "labels.tsv"
        data = self.render_labels().encode("utf-8")
        if write:
            path.write_bytes(data)
        elif not path.exists() or path.read_bytes().replace(b"\r\n", b"\n") != data:
            self.err(
                self.rel(path),
                1,
                "labels.tsv is out of date; run check_doc_labels.py --write-labels",
            )


def main(argv: list[str] | None = None) -> int:
    """Run the command line tool."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--root", type=Path, default=REPO)
    ap.add_argument("--write-labels", action="store_true", help="regenerate labels.tsv")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args(argv)
    root = args.root.resolve()
    chk = Checker(root)
    if not chk.manual.is_dir():
        print(f"check_doc_labels: {chk.manual} not found", file=sys.stderr)
        return 2
    chk.scan_tex()
    chk.check_labels()
    chk.check_src()
    chk.check_path_map()
    chk.check_citations()
    chk.check_labels_tsv(args.write_labels)
    for finding in chk.findings:
        print(finding)
    if args.verbose:
        print(
            f"check_doc_labels: {sum(len(v) for v in chk.labels.values())} labels, "
            f"{len(chk.refs)} references, {len(chk.srcs)} src paths, "
            f"{len(chk.findings)} finding(s)"
        )
    return 1 if chk.findings else 0


if __name__ == "__main__":
    sys.exit(main())
