#!/usr/bin/env python3
"""Rewrite references to old Markdown documents as label citations.

Usage:
    python tools/docs/repoint.py --map docs/manual/common/path_map.tsv
        [--sections-dir DIR] [--apply] [--report FILE] [--root DIR] [PATH ...]

Reads the path map (old_path, new_file, label) and scans git-tracked text files
for references to the old paths: root-relative, file-relative, or a bare .md
basename that is unique in the map. A section reference after the path (section
sign and number, "section N", or a quoted title) is resolved with the
*.sections.tsv sidecars written by md2tex. Replacement: "Doc: <label>" in
comments and Markdown, \\cref{<label>} in .tex under docs/manual/. In .tex a path
inside \\code, \\src, \\texttt, \\path, \\url or \\runid stays and " (\\cref{<label>})" is
appended after the macro once; the argument of \\begin{relocated} and \\begin{record}
and the "% Converted from" comment lines are never touched. A "path.md:123" suffix
becomes "<label> (line 123 of the original file)". A section label that holds an ISO
date is never used; the file-level label is used and the case is reported. Only comment
text and docstrings are rewritten in source files; other lines are reported as
code references. Line counts and newline styles are preserved. Default is a dry
run that prints a preview; --apply writes the files.

Exit codes: 0 nothing left to do (or dry run without problems), 1 unresolved
sections, code references or unmapped docs paths remain, 2 usage error.
"""

from __future__ import annotations

import argparse
import io
import json
import posixpath
import re
import subprocess
import sys
import tokenize
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# sw/bootloader/ and sw/bench/bin2hex.py are hashed by the boot image drift gate
# (tools/fpga/boot_image.py), so a comment edit there fails CI. The manifests listed in
# BOOT_MANIFESTS add every source they record, read at run time.
EXCLUDE_PREFIXES = (".beads/", "memory/", "micro_p/", "pnr/commercial/", "sw/bootloader/")
EXCLUDE_FILES = {"sw/bench/bin2hex.py"}
BOOT_MANIFESTS = ("fpga/nexys_video/boot_uart.manifest.json",)
EXCLUDE_NAMES = {"design_state.json", "path_map.tsv", "package-lock.json", "uv.lock", "flake.lock"}
EXCLUDE_SUFFIXES = (".lock",)
MAP_REL = "docs/manual/common/path_map.tsv"

SLASH_EXT = {
    ".sv", ".v", ".svh", ".vh", ".c", ".h", ".cc", ".cpp", ".hpp", ".java", ".js", ".ts",
}  # fmt: skip
HASH_EXT = {
    ".sdc", ".tcl", ".upf", ".cfg", ".sh", ".bash", ".yml", ".yaml", ".toml", ".nix", ".mk",
    ".gitignore", ".xdc",
}  # fmt: skip
PROSE_EXT = {".md", ".markdown", ".txt", ".rst"}
HASH_NAMES = {"makefile", "gnumakefile"}

TOKEN = re.compile(r"(?<![\w./~$@%-])((?:[\w.-]+/)*[\w.-]+\.md)(?![\w-]|\.\w)")
TOKEN_TEX = re.compile(r"(?<![\w./~$@%-])((?:(?:[\w.-]|\\_)+/)*(?:[\w.-]|\\_)+\.md)(?![\w-]|\.\w)")
MD_LINK = re.compile(r"\[([^\]\n]*)\]\(\s*<?([^)\s>]+)>?(?:\s+\"[^\"]*\")?\s*\)")
ANCHOR = re.compile(r"#([\w-]+)")
SEC_NUM = re.compile(r"[ \t]*(?:§[ \t]*|[Ss]ections?[ \t]+)(\d+(?:\.\d+)*)(?![\w])")
SEC_QUOTED = re.compile(r"[ \t]*§[ \t]*([\"“'`])([^\n]+?)([\"”'`])")
SEC_BARE = re.compile(
    r"[ \t]*§[ \t]*([A-Z][^\n\"“”'`)\];,:]{2,80}?)(?=$|[)\"”'`\];,:]|\.[ \t]|\.$)"
)
TEX_OPEN = re.compile(r"\\(?:src|code|path|texttt|url|runid)\{[^{}]*$")
TEX_PROVENANCE = re.compile(r"\\begin\{(?:relocated|record)\}\{[^{}]*\}")
TEX_PROVENANCE_COMMENT = re.compile(r"^\s*%\s*(?:Converted|Moved|Rewritten)\b.*\bfrom\b")
LINE_SUFFIX = re.compile(r":(\d+)(?:-(\d+))?(?![\w])")
ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
FENCE = re.compile(r"^\s*(```|~~~)")
TEX_VERB_BEGIN = re.compile(r"\\begin\{(lstlisting|logblock|textblock|verbatim|Verbatim)\}")
TEX_VERB_END = re.compile(r"\\end\{(lstlisting|logblock|textblock|verbatim|Verbatim)\}")


@dataclass
class Report:
    changed: dict[str, int] = field(default_factory=Counter)
    unresolved: list[str] = field(default_factory=list)
    code_refs: list[str] = field(default_factory=list)
    unmapped: list[str] = field(default_factory=list)
    by_top: Counter = field(default_factory=Counter)
    sec_total: int = 0
    sec_resolved: int = 0
    previews: list[str] = field(default_factory=list)


@dataclass
class Sections:
    by_num: dict[str, dict[str, list[str]]] = field(default_factory=dict)
    titles: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    labels: set[str] = field(default_factory=set)

    def file_known(self, label: str) -> bool:
        return label in self.titles or label in self.by_num


def norm_title(s: str) -> str:
    return " ".join(re.sub(r"[^0-9a-z]+", " ", s.casefold()).split())


def load_map(path: Path) -> dict[str, str]:
    rows: dict[str, str] = {}
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        parts = line.split("\t")
        if n == 0 and parts[0] == "old_path":
            continue
        if len(parts) >= 3 and parts[0].strip() and parts[2].strip():
            rows[parts[0].strip()] = parts[2].strip()
    return rows


def load_sections(directory: Path | None) -> Sections:
    sec = Sections()
    if directory is None:
        return sec
    for f in sorted(directory.rglob("*.sections.tsv")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines()):
            parts = line.split("\t")
            if len(parts) < 3 or (n == 0 and parts[0] == "number"):
                continue
            num, label, title = parts[0], parts[1], parts[2]
            file_label = ":".join(label.split(":")[:3])
            sec.by_num.setdefault(file_label, {}).setdefault(num, []).append(label)
            body = re.sub(r"^(?:§\s*)?[A-Z0-9][\d.]*\.?\s+", "", title)
            sec.titles.setdefault(file_label, []).append((norm_title(body), label))
            sec.titles[file_label].append((norm_title(title), label))
            sec.labels.add(label)
    return sec


def resolve_section(sec: Sections, file_label: str, number: str | None, title: str | None):
    """Return (sub_label or None, reason)."""
    if number is not None:
        cands = sec.by_num.get(file_label, {}).get(number)
        if not cands:
            return None, "no such section number in sidecar"
        if len(set(cands)) > 1:
            return None, "ambiguous section number"
        return cands[0], ""
    assert title is not None
    q = norm_title(title)
    rows = sec.titles.get(file_label, [])
    exact = {lab for t, lab in rows if t == q}
    if len(exact) == 1:
        return exact.pop(), ""
    part = {lab for t, lab in rows if len(q) >= 6 and (t.startswith(q) or q in t)}
    if len(part) == 1:
        return part.pop(), ""
    return None, "title not found" if not part else "ambiguous title"


def git_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
    ).stdout
    return [p for p in out.decode("utf-8", "replace").split("\0") if p]


def manifest_sources(root: Path) -> set[str]:
    """Return the sources that the boot-image manifests record (none if absent or unreadable)."""
    found: set[str] = set()
    for rel in BOOT_MANIFESTS:
        try:
            data = json.loads((root / rel).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        srcs = data.get("sources") if isinstance(data, dict) else None
        if isinstance(srcs, dict):
            found.update(str(k).replace("\\", "/") for k in srcs)
    return found


def is_excluded(rel: str, old_paths: set[str], pinned: frozenset[str] = frozenset()) -> bool:
    if rel.startswith(EXCLUDE_PREFIXES) or rel in EXCLUDE_FILES or rel in pinned:
        return True
    name = rel.rsplit("/", 1)[-1]
    if name in EXCLUDE_NAMES or name.endswith(EXCLUDE_SUFFIXES):
        return True
    return rel == MAP_REL or rel in old_paths


def file_kind(rel: str, first_line: str) -> str:
    low = rel.lower()
    name = low.rsplit("/", 1)[-1]
    ext = posixpath.splitext(name)[1]
    if ext == ".tex":
        return "tex" if rel.startswith("docs/manual/") else "code"
    if ext in PROSE_EXT:
        return "prose"
    if ext == ".py":
        return "python"
    if ext in SLASH_EXT:
        return "slash"
    if ext in HASH_EXT or name in HASH_NAMES or name == ".gitignore":
        return "hash"
    if not ext and first_line.startswith("#!"):
        return "hash"
    return "code"


def decode(raw: bytes) -> tuple[str, str] | None:
    if b"\0" in raw[:8192]:
        return None
    if raw.startswith(b"\xef\xbb\xbf"):
        return raw[3:].decode("utf-8", "strict"), "utf-8-sig"
    try:
        return raw.decode("utf-8"), "utf-8"
    except UnicodeDecodeError:
        return raw.decode("latin-1"), "latin-1"


def encode(text: str, enc: str) -> bytes:
    if enc == "utf-8-sig":
        return b"\xef\xbb\xbf" + text.encode("utf-8")
    return text.encode(enc)


# ---------------------------------------------------------------- regions
def _scan_slash(lines: list[str]) -> list[list[tuple[int, int]]]:
    res: list[list[tuple[int, int]]] = []
    in_block = False
    for line in lines:
        iv: list[tuple[int, int]] = []
        i, n = 0, len(line)
        start = 0 if in_block else -1
        in_str = False
        while i < n:
            c = line[i]
            if in_block:
                if line.startswith("*/", i):
                    iv.append((start, i))
                    in_block = False
                    i += 2
                    continue
                i += 1
                continue
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == '"':
                    in_str = False
            elif c == '"':
                in_str = True
            elif line.startswith("//", i):
                iv.append((i + 2, n))
                break
            elif line.startswith("/*", i):
                in_block = True
                start = i + 2
                i += 2
                continue
            i += 1
        if in_block:
            iv.append((start, n))
        res.append(iv)
    return res


def _scan_hash(lines: list[str]) -> list[list[tuple[int, int]]]:
    res: list[list[tuple[int, int]]] = []
    for line in lines:
        quote = ""
        iv: list[tuple[int, int]] = []
        for i, c in enumerate(line):
            if quote:
                if c == quote and (i == 0 or line[i - 1] != "\\"):
                    quote = ""
            elif c in "\"'":
                quote = c
            elif c == "#" and (i == 0 or line[i - 1] in " \t;"):
                iv.append((i + 1, len(line)))
                break
        res.append(iv)
    return res


def _scan_python(text: str, lines: list[str]) -> list[list[tuple[int, int]]] | None:
    res: list[list[tuple[int, int]]] = [[] for _ in lines]
    try:
        toks = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return None
    skip = {tokenize.NL, tokenize.COMMENT, tokenize.INDENT, tokenize.DEDENT}
    sig = [t for t in toks if t.type not in {tokenize.NL, tokenize.COMMENT}]
    for t in toks:
        if t.type == tokenize.COMMENT:
            r = t.start[0] - 1
            res[r].append((t.start[1] + 1, len(lines[r])))
    for k, t in enumerate(sig):
        if t.type != tokenize.STRING:
            continue
        prev = sig[k - 1].type if k else tokenize.NEWLINE
        nxt = sig[k + 1].type if k + 1 < len(sig) else tokenize.NEWLINE
        if prev in {
            tokenize.NEWLINE,
            tokenize.INDENT,
            tokenize.DEDENT,
            tokenize.ENCODING,
        } and nxt in {
            tokenize.NEWLINE,
            tokenize.ENDMARKER,
        }:
            (sr, sc), (er, ec) = t.start, t.end
            for r in range(sr, er + 1):
                a = sc if r == sr else 0
                b = ec if r == er else len(lines[r - 1])
                res[r - 1].append((a, b))
    del skip
    return res


def regions(kind: str, text: str, lines: list[str]) -> list[list[tuple[int, int]]]:
    n = len(lines)
    whole = [[(0, len(ln))] for ln in lines]
    if kind == "prose":
        out: list[list[tuple[int, int]]] = []
        fenced = False
        for i, ln in enumerate(lines):
            if FENCE.match(ln):
                fenced = not fenced
                out.append([])
            else:
                out.append([] if fenced else whole[i])
        return out
    if kind == "tex":
        out = []
        verb = False
        for ln in lines:
            if TEX_VERB_BEGIN.search(ln):
                verb = True
            if verb or TEX_PROVENANCE_COMMENT.match(ln):
                out.append([])
            else:
                ivs = [(0, len(ln))]
                for pm in TEX_PROVENANCE.finditer(ln):
                    ivs = [
                        piece
                        for s, e in ivs
                        for piece in ((s, min(e, pm.start())), (max(s, pm.end()), e))
                        if piece[0] < piece[1]
                    ]
                out.append(ivs)
            if TEX_VERB_END.search(ln):
                verb = False
        return out
    if kind == "slash":
        return _scan_slash(lines)
    if kind == "hash":
        return _scan_hash(lines)
    if kind == "python":
        py = _scan_python(text, lines)
        return py if py is not None else _scan_hash(lines)
    return [[] for _ in range(n)]


# ------------------------------------------------------------- resolution
class Resolver:
    def __init__(self, mapping: dict[str, str]):
        self.map = mapping
        base = Counter(p.rsplit("/", 1)[-1] for p in mapping)
        self.unique = {p.rsplit("/", 1)[-1]: p for p in mapping if base[p.rsplit("/", 1)[-1]] == 1}

    def resolve(self, tok: str, citing_dir: str) -> tuple[str | None, str | None]:
        """Return (mapped old path, normalised candidate for unmapped check)."""
        t = tok.replace("\\_", "_")
        rel = (
            posixpath.normpath(posixpath.join(citing_dir, t))
            if citing_dir
            else posixpath.normpath(t)
        )
        root = posixpath.normpath(t)
        for cand in (rel, root):
            if cand in self.map:
                return cand, None
        if "/" not in t and t in self.unique:
            return self.unique[t], None
        for cand in (root, rel):
            if cand.startswith(("docs/", "fixes/")) and not cand.startswith("docs/manual/"):
                return None, cand
        return None, None


def _in_regions(ivs: list[tuple[int, int]], a: int, b: int) -> bool:
    return any(s <= a and b <= e for s, e in ivs)


def repl_text(kind: str, label: str) -> str:
    return f"\\cref{{{label}}}" if kind == "tex" else f"Doc: {label}"


def process(
    rel: str,
    text: str,
    kind: str,
    res: Resolver,
    sec: Sections,
    rep: Report,
) -> str:
    lines = text.split("\n")
    cr = [ln.endswith("\r") for ln in lines]
    body = [ln[:-1] if c else ln for ln, c in zip(lines, cr, strict=True)]
    regs = regions(kind, text.replace("\r\n", "\n"), body)
    citing_dir = posixpath.dirname(rel)
    tok_re = TOKEN_TEX if kind == "tex" else TOKEN
    out_lines: list[str] = []
    top = rel.split("/", 1)[0] if "/" in rel else "(root)"
    for ln_no, line in enumerate(body, start=1):
        ivs = regs[ln_no - 1]
        edits: list[tuple[int, int, str]] = []
        claimed: list[tuple[int, int]] = []

        def free(a: int, b: int) -> bool:
            return not any(a < e and s < b for s, e in claimed)

        if kind == "prose":
            for m in MD_LINK.finditer(line):
                target = m.group(2)
                path_part, _, anchor = target.partition("#")
                if not path_part.endswith(".md"):
                    continue
                old, unm = res.resolve(path_part, citing_dir)
                if old is None:
                    if unm:
                        rep.unmapped.append(f"{rel}:{ln_no}: {path_part}")
                    continue
                label = res.map[old]
                rep.by_top[top] += 1
                if not _in_regions(ivs, m.start(), m.end()):
                    rep.code_refs.append(f"{rel}:{ln_no}: {line.strip()[:100]}")
                    claimed.append(m.span())
                    continue
                if anchor:
                    sub = f"{label}:{anchor.lower()}"
                    if sub in sec.labels:
                        label = sub
                    elif sec.file_known(label):
                        rep.unresolved.append(
                            f"{rel}:{ln_no}: {path_part}#{anchor} -> {label} (anchor not in sidecar)"  # noqa: E501
                        )
                text_norm = m.group(1).strip("` ")
                same = text_norm in {path_part, posixpath.basename(path_part), old}
                new = f"Doc: {label}" if same or not text_norm else f"{m.group(1)} (Doc: {label})"
                edits.append((m.start(), m.end(), new))
                claimed.append(m.span())
        skip: list[tuple[int, int]] = []
        if kind == "tex":
            skip = [pm.span() for pm in TEX_PROVENANCE.finditer(line)]
            if TEX_PROVENANCE_COMMENT.match(line):
                skip = [(0, len(line))]
        for m in tok_re.finditer(line):
            a, b = m.span(1)
            if not free(a, b):
                continue
            if any(s <= a and b <= e for s, e in skip):
                continue
            old, unm = res.resolve(m.group(1), citing_dir)
            if old is None:
                if unm:
                    rep.unmapped.append(f"{rel}:{ln_no}: {m.group(1)}")
                continue
            label = res.map[old]
            rep.by_top[top] += 1
            start, end = a, b
            tail = line[end:]
            bt_open = start > 0 and line[start - 1] == "`"
            close_tick = tail.startswith("`")
            if kind == "tex":
                mac = TEX_OPEN.search(line[:start])
                if mac:
                    close = line.find("}", end)
                    if close < 0 or "{" in line[end:close]:
                        rep.code_refs.append(f"{rel}:{ln_no}: {line.strip()[:100]}")
                        claimed.append((start, end))
                        continue
                    ins = close + 1
                    claimed.append((start, end))
                    if not re.match(rf"[ \t]*\(?\\cref\{{{re.escape(label)}\}}", line[ins:]) and (
                        ins not in {e[0] for e in edits}
                    ):
                        edits.append((ins, ins, f" (\\cref{{{label}}})"))
                    continue
            elif bt_open and close_tick:
                pass
            elif m.group(1).endswith(".md") and tail.startswith("#") and ANCHOR.match(tail):
                am = ANCHOR.match(tail)
                assert am is not None
                sub = f"{label}:{am.group(1).lower()}"
                if sub in sec.labels and not ISO_DATE.search(sub):
                    label = sub
                    end += am.end()
                    tail = line[end:]
            # line suffix: the original file line, not a section
            suffix = LINE_SUFFIX.match(tail)
            sm_end = None
            sub_label = None
            if suffix is None:
                probe = tail[1:] if (close_tick and kind != "tex") else tail
                probe_off = 1 if (close_tick and kind != "tex") else 0
                sm = SEC_NUM.match(probe)
                q = SEC_QUOTED.match(probe) if not sm else None
                bare = SEC_BARE.match(probe) if not sm and not q else None
                if sm or q or bare:
                    rep.sec_total += 1
                    if sm:
                        sub_label, why = resolve_section(sec, label, sm.group(1), None)
                        span_end = end + probe_off + sm.end()
                        desc = f"section {sm.group(1)}"
                    elif q:
                        sub_label, why = resolve_section(sec, label, None, q.group(2))
                        span_end = end + probe_off + q.end()
                        desc = f'section "{q.group(2)}"'
                    else:
                        assert bare is not None
                        sub_label, why = resolve_section(sec, label, None, bare.group(1).strip())
                        span_end = end + probe_off + bare.end()
                        desc = f"section {bare.group(1).strip()!r}"
                    if sub_label and kind != "tex" and ISO_DATE.search(sub_label):
                        sub_label, why = None, "section label contains a date"
                    if sub_label:
                        rep.sec_resolved += 1
                        sm_end = span_end
                    else:
                        rep.unresolved.append(
                            f"{rel}:{ln_no}: {m.group(1)} {desc} -> {label} ({why})"
                        )
            if not _in_regions(ivs, start, end):
                rep.code_refs.append(f"{rel}:{ln_no}: {line.strip()[:100]}")
                claimed.append((start, end))
                continue
            final_label = sub_label or label
            note = ""
            if suffix is not None:
                end += suffix.end()
                lo, hi = suffix.group(1), suffix.group(2)
                note = (
                    f" (lines {lo}-{hi} of the original file)"
                    if hi
                    else f" (line {lo} of the original file)"
                )
            elif sm_end is not None:
                end = sm_end
                if bt_open and close_tick and kind != "tex":
                    start -= 1
            repl = repl_text(kind, final_label)
            if kind != "tex" and re.search(r"Doc:[ \t]*$", line[:start]):
                repl = final_label
            if kind == "tex" and re.match(
                rf"[ \t]*\(\\cref\{{{re.escape(final_label)}\}}\)", line[end:]
            ):
                claimed.append((start, end))
                continue
            edits.append((start, end, repl + note))
            claimed.append((start, end))
        new_line = line
        for s, e, t in sorted(edits, reverse=True):
            new_line = new_line[:s] + t + new_line[e:]
        if new_line != line:
            rep.changed[rel] += 1
            rep.previews.append(f"{rel}:{ln_no}\n- {line.strip()}\n+ {new_line.strip()}")
        out_lines.append(new_line + ("\r" if cr[ln_no - 1] else ""))
    return "\n".join(out_lines)


def summarise(rep: Report, apply: bool) -> str:
    out: list[str] = []
    total = sum(rep.changed.values())
    out.append(
        f"repoint: {len(rep.changed)} file(s), {total} line(s) "
        f"{'rewritten' if apply else 'would be rewritten'}"
    )
    out.append(f"references by top-level directory: {dict(rep.by_top)}")
    out.append(f"section references: {rep.sec_total}, resolved: {rep.sec_resolved}")
    out.append("counts per file:")
    out += [f"  {n:4d}  {f}" for f, n in sorted(rep.changed.items())]
    for title, items in (
        ("unresolved sections (file-level label used)", rep.unresolved),
        ("code references, manual", rep.code_refs),
        ("references to docs paths not in the map", rep.unmapped),
    ):
        out.append(f"{title}: {len(items)}")
        out += [f"  {i}" for i in items]
    return "\n".join(out)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Repoint old .md references to label citations.")
    ap.add_argument("--map", required=True, type=Path)
    ap.add_argument("--sections-dir", type=Path)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--report", type=Path)
    ap.add_argument("--root", type=Path, help="repository root (default: from git)")
    ap.add_argument("paths", nargs="*")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if not args.map.is_file():
        print(f"repoint: map not found: {args.map}", file=sys.stderr)
        return 2
    if args.sections_dir is not None and not args.sections_dir.is_dir():
        print(f"repoint: sections dir not found: {args.sections_dir}", file=sys.stderr)
        return 2
    try:
        root = args.root or Path(
            subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=True,
            ).stdout.strip()
        )
        files = git_files(root)
    except (OSError, subprocess.CalledProcessError):
        print("repoint: not inside a git repository", file=sys.stderr)
        return 2
    mapping = load_map(args.map)
    if not mapping:
        print("repoint: path map has no usable rows", file=sys.stderr)
        return 2
    sec = load_sections(args.sections_dir)
    res = Resolver(mapping)
    wanted = [p.replace("\\", "/").strip("/") for p in args.paths]
    rep = Report()
    old_paths = set(mapping)
    pinned = frozenset(manifest_sources(root))
    for rel in files:
        if wanted and not any(rel == w or rel.startswith(w + "/") for w in wanted):
            continue
        if is_excluded(rel, old_paths, pinned):
            continue
        fp = root / rel
        try:
            raw = fp.read_bytes()
        except OSError:
            continue
        dec = decode(raw)
        if dec is None:
            continue
        text, enc = dec
        first = text.split("\n", 1)[0]
        kind = file_kind(rel, first)
        if ".md" not in text:
            continue
        new = process(rel, text, kind, res, sec, rep)
        if new != text:
            assert new.count("\n") == text.count("\n")
            if args.apply:
                fp.write_bytes(encode(new, enc))
    if not args.apply:
        for p in rep.previews:
            print(p)
    summary = summarise(rep, args.apply)
    print(summary)
    if args.report:
        args.report.write_text(summary + "\n", encoding="utf-8", newline="\n")
    return 1 if (rep.unresolved or rep.code_refs or rep.unmapped) else 0


if __name__ == "__main__":
    sys.exit(main())
