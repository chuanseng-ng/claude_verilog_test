#!/usr/bin/env python3
"""Convert one GFM Markdown file to a native LaTeX chapter or section.

Usage:
    python tools/docs/md2tex.py INPUT.md --book {ds,tm,um,cr} --kind KIND --slug SLUG \
        -o OUT.tex [--level chapter|section] [--path-map FILE] [--record]
        [--relocated OLDPATH] [--strip-heading-numbers] [--tables {auto,rows,long}]

Tables. A GFM table becomes a longtable. A longtable cannot break a row across pages,
and a row taller than the page makes it fail (an overfull box in the output routine,
and an endless loop in some TeX Live versions). So a table that can have such a row
becomes row blocks (environment rowtable: a bold row title, then one "Header: content"
entry per column; rowtitle and rowcell in docs/manual/common/cvtmacros.sty), which
break across pages freely. The rule (tools/docs/pandoc/cvt.lua, table_filter): the
converter estimates each row's height from the character count of its cells and the
column widths, and uses row blocks when the tallest row is more than 60 % of the usable
page height (A4, 25 mm margins; 703 pt portrait, 455 pt landscape, a table of 7 columns
or more being landscape). A table of at most 72 characters of natural width has no
wrapping column and stays a longtable. To force the form, put one comment line before
the table (<!-- cvt-table: rows -->, <!-- cvt-table: long -->, or auto), or pass
--tables for the whole document. --table-debug adds one "table-estimate" warning per
table with the estimate.

Runs pandoc with tools/docs/pandoc/cvt.lua, then post-processes the text
(label placement, bead / GH / PR / run-id macros, whitespace). Side files:
OUT.tex.sections.tsv (heading number, label, title) and OUT.tex.warnings.txt.

Pictographs map to status marks through tools/docs/pandoc/marks.tsv, the table that
prose_preserve.py reads too. A pictograph that is not in the table gives a warning.

Exit codes: 0 success (warnings allowed), 2 usage or pandoc failure,
3 pandoc not installed.
"""

from __future__ import annotations

import argparse
import functools
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILTER = HERE / "pandoc" / "cvt.lua"
MARKS = HERE / "pandoc" / "marks.tsv"
BOOKS = ("ds", "tm", "um", "cr")
TABLE_MODES = ("auto", "rows", "long")
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")

_SECT = r"(?:chapter|section|subsection|subsubsection|paragraph|subparagraph)"
_VERB_ENVS = ("lstlisting", "logblock", "textblock", "verbatim", "Verbatim")
_PROTECT_CMDS = (
    "texttt|src|code|url|label|cref|href|lstinline|runid|bead|ghref|prref|passthrough|"
    "chapter|section|subsection|subsubsection|paragraph|subparagraph|caption"
)


def repo_root(start: Path) -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=start,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            check=True,
        )
        return Path(out.stdout.strip())
    except (OSError, subprocess.CalledProcessError):
        return start


@functools.lru_cache(maxsize=4)
def tracked_files(root: str) -> tuple[str, ...]:
    """Repository file list from git, fetched once per process."""
    try:
        out = subprocess.run(
            ["git", "ls-files", "-z"],
            cwd=root,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            check=True,
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return ()
    return tuple(p for p in out.decode("utf-8", "replace").split("\0") if p)


def _match_brace(text: str, start: int) -> int:
    """Index just past the brace group opened at text[start] == '{', or -1."""
    depth = 0
    i = start
    n = len(text)
    while i < n:
        c = text[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def protected_spans(text: str) -> list[tuple[int, int]]:
    """Spans where inline macro wrapping must not happen."""
    spans: list[tuple[int, int]] = []
    env = "|".join(_VERB_ENVS)
    for m in re.finditer(rf"\\begin\{{({env})\}}.*?\\end\{{\1\}}", text, re.S):
        spans.append(m.span())
    for m in re.finditer(rf"\\(?:{_PROTECT_CMDS})\*?(?:\[[^\]]*\])?\{{", text):
        end = _match_brace(text, m.end() - 1)
        if end > 0:
            spans.append((m.start(), end))
    spans.sort()
    merged: list[tuple[int, int]] = []
    for s, e in spans:
        if merged and s <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(e, merged[-1][1]))
        else:
            merged.append((s, e))
    return merged


def _apply_outside(text: str, fn) -> str:
    out: list[str] = []
    pos = 0
    for s, e in protected_spans(text):
        out.append(fn(text[pos:s]))
        out.append(text[s:e])
        pos = e
    out.append(fn(text[pos:]))
    return "".join(out)


_WS = r"(?:[ \t]+|[ \t]*\n[ \t]*)"
_GH = re.compile(rf"(?<![\w\\])GH{_WS}\\#(\d+)")
_PR = re.compile(rf"(?<![\w\\])PR{_WS}\\#(\d+)")
_BRK = r"(?:\\allowbreak\{\})?"  # break hint that cvt.lua puts after an underscore
_RUN = re.compile(
    rf"(?<![\w\\])RUN\\_{_BRK}(\d{{4}}-\d{{2}}-\d{{2}})\\_{_BRK}(\d{{2}}-\d{{2}}-\d{{2}})(?![\w\\-])"
)
_BEAD_CODE = re.compile(rf"(?<![\w\\])(bead{_WS})\\code\{{([a-z0-9]{{3,6}}(?:\.\d+)?)\}}")
_BEAD_PLAIN = re.compile(rf"(?<![\w\\])(bead{_WS})([a-z0-9]{{3,6}}(?:\.\d+)?)(?![\w.])")


def _bead_plain(m: re.Match) -> str:
    bid = m.group(2)
    if re.search(r"[a-z]", bid) and re.search(r"\d", bid):
        return f"{m.group(1)}\\bead{{{bid}}}"
    return m.group(0)


def _bead_codes(text: str) -> str:
    spans = protected_spans(text)

    def fn(m: re.Match) -> str:
        if any(s <= m.start() < e for s, e in spans):
            return m.group(0)
        return f"{m.group(1)}\\bead{{{m.group(2)}}}"

    return _BEAD_CODE.sub(fn, text)


def wrap_references(text: str) -> str:
    text = _bead_codes(text)

    def fn(seg: str) -> str:
        seg = _GH.sub(lambda m: f"\\ghref{{{m.group(1)}}}", seg)
        seg = _PR.sub(lambda m: f"\\prref{{{m.group(1)}}}", seg)
        seg = _RUN.sub(lambda m: f"\\runid{{RUN_{m.group(1)}_{m.group(2)}}}", seg)
        seg = _BEAD_CODE.sub(lambda m: f"{m.group(1)}\\bead{{{m.group(2)}}}", seg)
        return _BEAD_PLAIN.sub(_bead_plain, seg)

    return _apply_outside(text, fn)


def join_labels(text: str) -> str:
    pat = re.compile(rf"(\\{_SECT}\{{(?:(?!\n\n).)*?\}})[ \t]*\n\n(\\label\{{[^}}\n]*\}})", re.S)
    return pat.sub(r"\1\2", text)


def strip_hypertargets(text: str) -> str:
    """Drop pandoc's hypertarget wrappers if any survive (keeps their content)."""
    out = []
    i = 0
    pat = re.compile(r"\\hypertarget\{[^}]*\}\{%?\n?")
    while True:
        m = pat.search(text, i)
        if not m:
            out.append(text[i:])
            break
        out.append(text[i : m.start()])
        end = _match_brace(text, m.end() - 1)
        if end < 0:
            out.append(text[m.start() :])
            break
        out.append(text[m.end() : end - 1])
        i = end
    return "".join(out)


def drop_captype(text: str) -> str:
    """Remove pandoc's LTcaptype counter switch (needs a counter the class lacks)."""
    return re.sub(r"\\def\\LTcaptype\{none\}[ \t]*(?:%[^\n]*)?", "", text)


_PCOL = re.compile(r"p\{\(\\linewidth - (\d+)\\tabcolsep\) \* \\real\{([0-9.]+)\}\}")


def plain_dimexpr(text: str) -> str:
    """Rewrite calc-style column widths as e-TeX dimexpr (no calc package needed)."""

    def fn(m: re.Match) -> str:
        frac = round(float(m.group(2)) * 1000)
        return f"p{{\\dimexpr(\\linewidth-{m.group(1)}\\tabcolsep)*{frac}/1000\\relax}}"

    return _PCOL.sub(fn, text)


def tidy(text: str) -> str:
    lines = [ln.rstrip() for ln in text.replace("\r\n", "\n").split("\n")]
    out = "\n".join(lines).strip("\n")
    return re.sub(r"\n{3,}", "\n\n", out) + "\n"


_HEAD_CMD = re.compile(r"\\(chapter|section|subsection|subsubsection|paragraph|subparagraph)\{")
_HEAD_NUM = re.compile(r"^(\d+(?:\.\d+)*)\.?\s+(?=\S)")
_PDFSTR = "\\texorpdfstring{"


def _strip_num(title: str) -> tuple[str, str | None]:
    m = _HEAD_NUM.match(title)
    if not m:
        return title, None
    return title[m.end() :], m.group(1)


def strip_heading_numbers(text: str) -> str:
    """Remove a leading number from heading titles and keep it as \\origsec{N}.

    The macro follows the heading, and the label when one follows at once, so the
    original section number stays in the text and prose_preserve.py counts it.
    """
    out: list[str] = []
    pos = 0
    for m in _HEAD_CMD.finditer(text):
        if m.start() < pos:
            continue
        end = _match_brace(text, m.end() - 1)
        if end < 0:
            continue
        title = text[m.end() : end - 1]
        num: str | None
        if title.startswith(_PDFSTR):
            first_end = _match_brace(title, len(_PDFSTR) - 1)
            if first_end < 0:
                continue
            first = title[len(_PDFSTR) : first_end - 1]
            rest = title[first_end:]
            new_first, num = _strip_num(first)
            if num is None:
                continue
            new_rest = rest
            if rest.startswith("{"):
                pdf_end = _match_brace(rest, 0)
                if pdf_end > 0:
                    new_pdf, _ = _strip_num(rest[1 : pdf_end - 1])
                    new_rest = "{" + new_pdf + "}" + rest[pdf_end:]
            new_title = _PDFSTR + new_first + "}" + new_rest
        else:
            new_title, num = _strip_num(title)
            if num is None:
                continue
        out.append(text[pos : m.end()])
        out.append(new_title + "}")
        pos = end
        lab = re.match(r"\\label\{[^}\n]*\}", text[pos:])
        if lab:
            out.append(lab.group(0))
            pos += lab.end()
        out.append("\\origsec{" + num + "}")
    out.append(text[pos:])
    return "".join(out)


def postprocess(
    tex: str,
    src_rel: str,
    relocated: str | None = None,
    strip_numbers: bool = False,
) -> str:
    tex = strip_hypertargets(tex)
    tex = join_labels(tex)
    tex = drop_captype(tex)
    tex = plain_dimexpr(tex)
    tex = wrap_references(tex)
    if strip_numbers:
        tex = strip_heading_numbers(tex)
    header = (
        f"% Converted from {src_rel} by tools/docs/md2tex.py; edit this file, not the original."
    )
    tex = tidy(header + "\n" + tex)
    if relocated:
        tex = "\\begin{relocated}{" + relocated + "}\n" + tex + "\\end{relocated}\n"
    return tex


def read_tsv_lines(path: Path) -> list[list[str]]:
    if not path.exists():
        return []
    rows = []
    for ln in path.read_text(encoding="utf-8").splitlines():
        if ln.strip():
            rows.append(ln.split("\t"))
    return rows


def _cells(row: str) -> int:
    parts = re.split(r"(?<!\\)\|", row.strip())
    if parts and not parts[0].strip():
        parts = parts[1:]
    if parts and not parts[-1].strip():
        parts = parts[:-1]
    return len(parts)


def table_overflow(text: str) -> list[tuple[int, int, int]]:
    """Rows with more cells than their header (GFM would drop the extra cells).

    Returns (line number, cells in row, cells in header).
    """
    bad: list[tuple[int, int, int]] = []
    lines = text.split("\n")
    fenced = False
    i = 0
    delim = re.compile(r"^\s*\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")
    while i < len(lines):
        ln = lines[i]
        if re.match(r"\s*(```|~~~)", ln):
            fenced = not fenced
        if (
            not fenced
            and "|" in ln
            and i + 1 < len(lines)
            and "-" in lines[i + 1]
            and delim.match(lines[i + 1])
        ):
            width = _cells(ln)
            j = i + 2
            while j < len(lines) and lines[j].strip() and "|" in lines[j]:
                n = _cells(lines[j])
                if n > width:
                    bad.append((j + 1, n, width))
                j += 1
            i = j
            continue
        i += 1
    return bad


def convert(
    md: Path,
    *,
    book: str,
    kind: str,
    slug: str,
    out: Path,
    level: str = "chapter",
    path_map: Path | None = None,
    record: bool = False,
    relocated: str | None = None,
    strip_numbers: bool = False,
    root: Path | None = None,
    tables: str = "auto",
    table_debug: bool = False,
) -> tuple[int, list[tuple[str, str]]]:
    """Convert one file. Returns (exit code, warnings). Writes out and side files."""
    pandoc = shutil.which("pandoc")
    if not pandoc:
        print("md2tex: pandoc not found on PATH", file=sys.stderr)
        return 3, []
    md = md.resolve()
    if root is None:
        root = repo_root(md.parent)
        if not (root / ".git").exists() and not (md.parent / ".git").exists():
            root = repo_root(Path.cwd())
    try:
        src_rel = md.relative_to(root.resolve()).as_posix()
    except ValueError:
        src_rel = md.name
    bad = table_overflow(md.read_text(encoding="utf-8", errors="replace"))
    if bad:
        for ln, n, w in bad:
            print(
                f"md2tex: {md}:{ln}: table row has {n} cells, header has {w}; "
                "fix the Markdown (extra cells would be lost)",
                file=sys.stderr,
            )
        return 2, []
    out = out.resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    sec_out = Path(str(out) + ".sections.tsv")
    warn_out = Path(str(out) + ".warnings.txt")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        tracked = tdp / "tracked.txt"
        tracked.write_text("\n".join(tracked_files(str(root))) + "\n", encoding="utf-8")
        lua_warn = tdp / "warn.tsv"
        lua_sec = tdp / "sec.tsv"
        meta = {
            "cvt-book": book,
            "cvt-kind": kind,
            "cvt-slug": slug,
            "cvt-level": level,
            "cvt-src": src_rel,
            "cvt-tracked": tracked.as_posix(),
            "cvt-sections-out": lua_sec.as_posix(),
            "cvt-warn-out": lua_warn.as_posix(),
            "cvt-record": "1" if record else "0",
            "cvt-marks": MARKS.as_posix(),
            "cvt-tables": tables,
            "cvt-table-debug": "1" if table_debug else "0",
        }
        if path_map is not None:
            meta["cvt-pathmap"] = Path(path_map).resolve().as_posix()
        cmd = [
            pandoc,
            "-f",
            "gfm",
            "-t",
            "latex",
            "--listings",
            f"--top-level-division={level}",
            f"--lua-filter={FILTER.as_posix()}",
        ]
        for k, v in meta.items():
            cmd += ["-M", f"{k}={v}"]
        cmd.append(md.as_posix())
        proc = subprocess.run(
            cmd,
            cwd=root,
            capture_output=True,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
        )
        if proc.returncode != 0:
            print(f"md2tex: pandoc failed for {md}:\n{proc.stderr}", file=sys.stderr)
            return 2, []
        tex = postprocess(proc.stdout, src_rel, relocated, strip_numbers)
        out.write_text(tex, encoding="utf-8", newline="\n")
        sec_rows = read_tsv_lines(lua_sec) or [["number", "label", "title"]]
        sec_out.write_text(
            "\n".join("\t".join(r) for r in sec_rows) + "\n", encoding="utf-8", newline="\n"
        )
        warns = [(r[0], r[1] if len(r) > 1 else "") for r in read_tsv_lines(lua_warn)]
    warn_out.write_text("".join(f"{k}\t{d}\n" for k, d in warns), encoding="utf-8", newline="\n")
    return 0, warns


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Convert a GFM Markdown file to LaTeX.")
    ap.add_argument("input", type=Path)
    ap.add_argument("--book", required=True, choices=BOOKS)
    ap.add_argument("--kind", required=True)
    ap.add_argument("--slug", required=True)
    ap.add_argument("-o", "--output", required=True, type=Path)
    ap.add_argument("--level", choices=("chapter", "section"), default="chapter")
    ap.add_argument("--path-map", type=Path)
    ap.add_argument("--record", action="store_true")
    ap.add_argument(
        "--relocated", metavar="OLDPATH", help="wrap the output in a relocated environment"
    )
    ap.add_argument(
        "--strip-heading-numbers",
        action="store_true",
        help="drop a leading number from heading titles, keep it as origsec",
    )
    ap.add_argument("--root", type=Path, help="repository root (default: from git)")
    ap.add_argument(
        "--tables",
        choices=TABLE_MODES,
        default="auto",
        help="table form: auto (by row height), rows (row blocks), long (longtable)",
    )
    ap.add_argument(
        "--table-debug", action="store_true", help="warn with the row height estimate of each table"
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not SLUG_RE.match(args.slug) or not re.match(r"^[a-z]+$", args.kind):
        print(
            "md2tex: kind must be lowercase letters, slug lowercase/digits/hyphens", file=sys.stderr
        )
        return 2
    if not args.input.is_file():
        print(f"md2tex: input not found: {args.input}", file=sys.stderr)
        return 2
    code, warns = convert(
        args.input,
        book=args.book,
        kind=args.kind,
        slug=args.slug,
        out=args.output,
        level=args.level,
        path_map=args.path_map,
        record=args.record,
        relocated=args.relocated,
        strip_numbers=args.strip_heading_numbers,
        root=args.root,
        tables=args.tables,
        table_debug=args.table_debug,
    )
    if code:
        return code
    if warns:
        counts = Counter(k for k, _ in warns)
        print(
            f"md2tex: {len(warns)} warning(s): " + ", ".join(f"{k}={v}" for k, v in counts.items())
        )
        for k, d in warns:
            print(f"  {k}: {d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
