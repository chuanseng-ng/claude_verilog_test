#!/usr/bin/env python3
"""Prove that a change altered comments only (code-equivalence of two file versions).

Each file is reduced to a comment-free canonical form (tokens, AST, commands or lines) and the
two forms are compared.  Pragma-style comments that tools act on (lint waivers, coverage
markers, noqa, upf-check, shellcheck ...) are kept as code, so removing one counts as a change.

Usage:
    code_equiv.py BASE HEAD [FILE ...]      # git revisions; HEAD may be WORKTREE
    code_equiv.py --files-pair OLD NEW --lang LANG     # two files on disk (LANG: auto, sv,
                                                       # python, tcl, cfg, make, yaml, shell)

With no FILE the files from `git diff --name-only` are compared; files of an unsupported type
are then listed as SKIPPED (counted in the summary) and do not affect the exit code.

Exit codes:
    0  every file is code-equivalent
    1  at least one file has a code change (added and deleted files count as changes)
    2  unsupported file type, parse error or usage error (takes precedence over 1)
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
from collections.abc import Callable
from pathlib import Path
from typing import Any, NamedTuple


class ParseError(Exception):
    """Raised when a file cannot be reduced to its canonical form."""


class Item(NamedTuple):
    """One comparable unit (token, statement, line) with its source line."""

    text: str
    line: int
    shown: str = ""


NEWLINE = "\n"
MAX_SHOWN = 160

# ---------------------------------------------------------------- SystemVerilog / Verilog

_VERILATOR_WORDS = (
    "lint_off lint_on lint_save lint_restore coverage_off coverage_on coverage_block_off public "
    "public_flat public_flat_rd public_flat_rw public_module no_inline_module no_inline_task "
    "inline_module split_var isolate_assignments clock_enable clocker no_clocker sc_bv sformat "
    "tracing_off tracing_on full_case parallel_case unroll_full unroll_disable hier_block "
    "forceable timing_off timing_on tag"
)
_SYNOPSYS_WORDS = (
    "translate_off translate_on synthesis_off synthesis_on full_case parallel_case "
    "async_set_reset sync_set_reset "
    "dc_script_begin dc_script_end dc_tcl_script_begin dc_tcl_script_end infer_mux "
    "infer_multibit attribute keep preserve noprune off on protect coverage template black_box "
    "syn_keep syn_preserve loop_limit ramstyle romstyle"
)


def _alt(words: str) -> str:
    return "|".join(words.split())


# Case-sensitive on purpose: tools only act on the lowercase forms, so prose such as
# "Synthesis ..." or "Coverage of ..." is an ordinary comment.
_SV_PRAGMA = re.compile(
    rf"(?:verilator\s+(?:{_alt(_VERILATOR_WORDS)})"
    rf"|(?:synopsys|synthesis|pragma|cadence|ambit|rtl_synthesis)\s+(?:synthesis\s+)?(?:{_alt(_SYNOPSYS_WORDS)})"
    r"|coverage\s+(?:off|on)"
    r"|(?:translate_off|translate_on|lint_off|lint_on|coverage_off|coverage_on)"
    r"|spyglass\s+(?:disable_block|enable_block|disable|enable)"
    r"|tessent\s+[a-z_]+"
    r"|(?:vcs|ncvlog|xcelium|cover)\s+(?:off|on|coverage|translate_off|translate_on))"
    r"(?![A-Za-z0-9_])"
)
# Directives whose argument list ends at end of line, so the newline is kept as a token.
_SV_LINE_DIRECTIVES = frozenset(
    "define undef include ifdef ifndef elsif timescale default_nettype pragma line "
    "begin_keywords".split()
)
_SV_OPS = sorted(
    (
        "<<<= >>>= === !== ==? !=? <<< >>> <<= >>= ->> <-> |-> |=> ## :: ** &&& ... +: -: == != "
        "<= >= && || << >> ~& ~| ~^ ^~ += -= *= /= %= &= |= ^= ++ -- -> => *> '{ ``"
    ).split(),
    key=len,
    reverse=True,
)
_SV_BASED = re.compile(r"(?:\d[\d_]*)?\s*'[sS]?[bBoOdDhH]\s*[0-9a-fA-FxXzZ?_]+")
_SV_UNBASED = re.compile(r"'[01xXzZ](?![A-Za-z0-9_])")
_SV_NUMBER = re.compile(r"\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d[\d_]*)?")
_SV_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_$]*")
_SV_SYSID = re.compile(r"\$[A-Za-z0-9_$]*")
_SV_ESCID = re.compile(r"\\\S+")
_SV_WS = " \t\r\f\v"


def _norm(text: str) -> str:
    return " ".join(text.split())


def lex_sv(src: str) -> list[Item]:
    """Tokenise SystemVerilog, dropping non-pragma comments."""
    toks: list[Item] = []
    i, n, line = 0, len(src), 1
    in_dir = False
    while i < n:
        c = src[i]
        if c == "\n":
            if in_dir:
                toks.append(Item(NEWLINE, line))
                in_dir = False
            line += 1
            i += 1
        elif c in _SV_WS or c == "\ufeff":
            i += 1
        elif c == "\\" and in_dir and src.startswith(("\\\n", "\\\r\n"), i):
            i = src.index("\n", i) + 1
            line += 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            text = src[i + 2 : j]
            if _SV_PRAGMA.match(text.lstrip()):
                toks.append(Item("PRAGMA " + _norm(text), line))
            i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                raise ParseError(f"unterminated block comment at line {line}")
            text = src[i + 2 : j]
            if _SV_PRAGMA.match(text.lstrip()):
                toks.append(Item("PRAGMA " + _norm(text), line))
            line += src.count("\n", i, j)
            i = j + 2
        elif c == '"':
            j = i + 1
            while j < n and src[j] != '"':
                if src[j] == "\\":
                    j += 1
                elif src[j] == "\n":
                    raise ParseError(f"unterminated string at line {line}")
                if j < n and src[j] == "\n":
                    line += 1
                j += 1
            if j >= n:
                raise ParseError(f"unterminated string at line {line}")
            toks.append(Item(src[i : j + 1], line))
            i = j + 1
        elif src.startswith("(*", i) and src[i + 2 : i + 3] != ")" and src.find("*)", i + 2) >= 0:
            j = src.find("*)", i + 2)
            toks.append(Item("(*" + _norm(src[i + 2 : j]) + "*)", line))
            line += src.count("\n", i, j)
            i = j + 2
        elif c == "`":
            if src.startswith('`\\`"', i):
                toks.append(Item('`\\`"', line))
                i += 4
            elif src.startswith('`"', i):
                toks.append(Item('`"', line))
                i += 2
            else:
                m = _SV_IDENT.match(src, i + 1)
                if m:
                    toks.append(Item("`" + m.group(), line))
                    if m.group() in _SV_LINE_DIRECTIVES:
                        in_dir = True
                    i = m.end()
                elif src.startswith("``", i):
                    toks.append(Item("``", line))
                    i += 2
                else:
                    toks.append(Item("`", line))
                    i += 1
        else:
            i = _lex_sv_atom(src, i, line, toks)
    return toks


def _lex_sv_atom(src: str, i: int, line: int, toks: list[Item]) -> int:
    """Lex one number, identifier, operator or punctuation char at i; return the new index."""
    c = src[i]
    for rx in (_SV_BASED, _SV_UNBASED):
        m = rx.match(src, i)
        if m and (c.isdigit() or c == "'" or c.isspace()):
            toks.append(Item(m.group(), line))
            return m.end()
    if c.isdigit():
        m = _SV_NUMBER.match(src, i)
        assert m
        toks.append(Item(m.group(), line))
        return m.end()
    for rx in (_SV_IDENT, _SV_SYSID, _SV_ESCID):
        m = rx.match(src, i)
        if m:
            toks.append(Item(m.group(), line))
            return m.end()
    for op in _SV_OPS:
        if src.startswith(op, i):
            toks.append(Item(op, line))
            return i + len(op)
    toks.append(Item(c, line))
    return i + 1


# ---------------------------------------------------------------------------------- Python

_PY_PRAGMA = re.compile(
    r"noqa|type:\s*ignore|pylint:|pragma:\s*no cover|fmt:|shellcheck|mypy:|ruff:|^#!"
    r"|^#.*coding[:=]",
    re.IGNORECASE,
)


def _strip_docstrings(tree: ast.Module) -> None:
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            first = body[0] if body else None
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                del body[0]


def py_items(src: str, keep_docstrings: bool = False) -> list[Item]:
    """One item per top-level statement (docstrings removed) plus the pragma comments."""
    try:
        tree = ast.parse(src)
    except (SyntaxError, ValueError) as exc:
        raise ParseError(f"python syntax error: {exc}") from exc
    if not keep_docstrings:
        _strip_docstrings(tree)
    lines = src.splitlines()
    items = [
        Item(ast.dump(s, include_attributes=False), s.lineno, lines[s.lineno - 1].strip())
        for s in tree.body
    ]
    try:
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and _PY_PRAGMA.search(tok.string):
                code = tok.line[: tok.start[1]].strip()
                comment = tok.string.strip()
                items.append(Item(f"{code}\0{comment}", tok.start[0], f"{code}  {comment}"))
    except (tokenize.TokenError, SyntaxError) as exc:
        raise ParseError(f"python tokenize error: {exc}") from exc
    return items


# ------------------------------------------------------------------------------------- Tcl


def lex_tcl(src: str) -> list[Item]:
    """Tokenise Tcl/SDC/UPF; commands are separated by SEP items (newline or semicolon)."""
    toks: list[Item] = []
    i, n, line = 0, len(src), 1
    cmd_start, after_open = True, False

    def sep() -> None:
        if toks and toks[-1].text != NEWLINE:
            toks.append(Item(NEWLINE, line))

    while i < n:
        c = src[i]
        if c in " \t\r":
            if after_open:
                cmd_start, after_open = True, False
            i += 1
        elif c == "\n":
            sep()
            line += 1
            cmd_start, after_open = True, False
            i += 1
        elif c == ";":
            sep()
            cmd_start, after_open = True, False
            i += 1
        elif c == "\\" and src.startswith(("\\\n", "\\\r\n"), i):
            i = src.index("\n", i) + 1
            line += 1
        elif c == "#" and cmd_start:
            j = i
            while True:
                e = src.find("\n", j)
                e = n if e < 0 else e
                seg = src[j:e].rstrip("\r")
                if e < n and seg.endswith("\\") and (len(seg) - len(seg.rstrip("\\"))) % 2 == 1:
                    j = e + 1
                    continue
                break
            text = _norm(src[i + 1 : e].replace("\\\n", " ").replace("\\\r\n", " "))
            if text.startswith("upf-check"):
                toks.append(Item("#" + text, line))
            line += src.count("\n", i, e)
            i = e
        elif c == '"' and (i == 0 or src[i - 1] in " \t\r\n;{["):
            j = i + 1
            while j < n and src[j] != '"':
                if src[j] == "\\":
                    j += 1
                j += 1
            if j >= n:
                raise ParseError(f"unterminated string at line {line}")
            toks.append(Item(src[i : j + 1], line))
            line += src.count("\n", i, j)
            i = j + 1
            cmd_start, after_open = False, False
        elif c in "{}[]":
            toks.append(Item(c, line))
            cmd_start, after_open = False, c == "{"
            i += 1
        else:
            j = i
            while j < n:
                ch = src[j]
                if ch in " \t\r\n;{}[]":
                    break
                if ch == "\\":
                    if src.startswith(("\\\n", "\\\r\n"), j):
                        break
                    j += 2
                else:
                    j += 1
            j = min(max(j, i + 1), n)
            toks.append(Item(src[i:j], line))
            cmd_start, after_open = False, False
            i = j
    while toks and toks[-1].text == NEWLINE:
        toks.pop()
    return toks


# ---------------------------------------------------------------- cfg, Makefile, shell, YAML


def _split_lines(src: str) -> list[str]:
    return src.replace("\r\n", "\n").split("\n")


def cfg_items(src: str) -> list[Item]:
    """Non-blank, non-comment lines split on whitespace."""
    out = []
    for no, ln in enumerate(_split_lines(src), 1):
        s = ln.strip()
        if s and not s.startswith("#"):
            out.append(Item(" ".join(s.split()), no, s))
    return out


_MK_DEFINE = re.compile(r"\s*(?:(?:override|export)\s+)*define\s")
_MK_ENDEF = re.compile(r"\s*endef\b")


def make_items(src: str) -> list[Item]:
    """Makefile lines minus comment lines; recipe lines and trailing comments are code."""
    lines = _split_lines(src)
    out: list[Item] = []
    last_blank = True
    depth = 0
    i = 0
    while i < len(lines):
        ln = lines[i]
        if depth == 0 and not ln.startswith("\t") and ln.lstrip().startswith("#"):
            while ln.endswith("\\") and i + 1 < len(lines):
                i += 1
                ln = lines[i]
            i += 1
            continue
        if _MK_DEFINE.match(ln) and not ln.startswith("\t"):
            depth += 1
        elif _MK_ENDEF.match(ln) and depth:
            depth -= 1
        if ln.strip() == "":
            if not last_blank:
                out.append(Item("", i + 1))
                last_blank = True
        else:
            out.append(Item(ln, i + 1))
            last_blank = False
        i += 1
    while out and out[-1].text == "":
        out.pop()
    return out


def shell_items(src: str) -> list[Item]:
    """Shell lines minus full-line comments (shebang and shellcheck directives are kept)."""
    out: list[Item] = []
    last_blank = True
    for no, ln in enumerate(_split_lines(src), 1):
        s = ln.strip()
        if s.startswith("#") and not (no == 1 and s.startswith("#!")) and "shellcheck" not in s:
            continue
        if s == "":
            if not last_blank:
                out.append(Item("", no))
                last_blank = True
        else:
            out.append(Item(ln.rstrip(), no))
            last_blank = False
    while out and out[-1].text == "":
        out.pop()
    return out


def _flatten(obj: Any, path: str, out: list[Item]) -> None:
    if isinstance(obj, dict):
        if not obj:
            out.append(Item(f"{path}={{}}", 0))
        for k in sorted(obj, key=repr):
            _flatten(obj[k], f"{path}.{k!r}", out)
    elif isinstance(obj, list):
        if not obj:
            out.append(Item(f"{path}=[]", 0))
        for idx, v in enumerate(obj):
            _flatten(v, f"{path}[{idx}]", out)
    else:
        out.append(Item(f"{path}={type(obj).__name__}:{obj!r}", 0))


def yaml_items(src: str) -> list[Item]:
    """Flattened (path, value) leaves of the parsed YAML documents."""
    import yaml

    try:
        docs = list(yaml.safe_load_all(src))
    except yaml.YAMLError as exc:
        raise ParseError(f"yaml error: {exc}") from exc
    out: list[Item] = []
    for d, doc in enumerate(docs):
        _flatten(doc, f"doc{d}", out)
    return out


# ------------------------------------------------------------------------- dispatch/compare

LANGS: dict[str, Callable[[str], list[Item]]] = {
    "sv": lex_sv,
    "python": py_items,
    "tcl": lex_tcl,
    "cfg": cfg_items,
    "make": make_items,
    "yaml": yaml_items,
    "shell": shell_items,
}
_EXT = {
    ".sv": "sv", ".svh": "sv", ".v": "sv", ".vh": "sv",
    ".py": "python",
    ".tcl": "tcl", ".sdc": "tcl", ".upf": "tcl",
    ".cfg": "cfg",
    ".mk": "make",
    ".yml": "yaml", ".yaml": "yaml",
    ".sh": "shell", ".csh": "shell", ".bash": "shell",
}  # fmt: skip
_MAKE_NAMES = frozenset({"makefile", "gnumakefile"})


def detect_lang(path: str) -> str | None:
    """Language name for a path, or None when unsupported."""
    p = Path(path)
    if p.name.lower() in _MAKE_NAMES:
        return "make"
    return _EXT.get(p.suffix.lower())


class Diff(NamedTuple):
    left: Item | None
    right: Item | None


def compare_texts(lang: str, old: str, new: str) -> Diff | None:
    """Return None when the code is equivalent, else the first differing items."""
    if lang == "python":
        keep = "__doc__" in old or "__doc__" in new
        a, b = py_items(old, keep), py_items(new, keep)
    elif lang in LANGS:
        a, b = LANGS[lang](old), LANGS[lang](new)
    else:
        raise ParseError(f"unsupported language {lang!r}")
    for k in range(max(len(a), len(b))):
        x = a[k] if k < len(a) else None
        y = b[k] if k < len(b) else None
        if x is None or y is None or x.text != y.text:
            return Diff(x, y)
    return None


def _fmt(side: str, item: Item | None) -> str:
    if item is None:
        return f"  {side}: <end of file>"
    shown = (item.shown or item.text).replace("\n", "\\n").replace("\0", " ")
    if len(shown) > MAX_SHOWN:
        shown = shown[:MAX_SHOWN] + "..."
    where = f"line {item.line}" if item.line else "value"
    return f"  {side} ({where}): {shown}"


# ----------------------------------------------------------------------------------- git/CLI


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, stdin=subprocess.DEVNULL, check=False
    )


def _repo_root() -> Path:
    res = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        stdin=subprocess.DEVNULL,
        check=False,
    )
    if res.returncode != 0:
        raise ParseError("not inside a git repository")
    return Path(res.stdout.decode().strip())


def _decode(data: bytes) -> str:
    return data.decode("utf-8-sig", errors="replace")


def read_rev(root: Path, rev: str, path: str) -> str | None:
    """File text at a revision (or the worktree), None when the file does not exist there."""
    if rev == "WORKTREE":
        f = root / path
        return _decode(f.read_bytes()) if f.is_file() else None
    if _git(root, "cat-file", "-e", f"{rev}:{path}").returncode != 0:
        return None
    res = _git(root, "show", f"{rev}:{path}")
    if res.returncode != 0:
        raise ParseError(f"git show {rev}:{path} failed: {res.stderr.decode().strip()}")
    return _decode(res.stdout)


def changed_files(root: Path, base: str, head: str) -> list[str]:
    args = ["diff", "--name-only", "--no-renames", "-z", base]
    if head != "WORKTREE":
        args.append(head)
    res = _git(root, *args)
    if res.returncode != 0:
        raise ParseError(f"git diff failed: {res.stderr.decode().strip()}")
    return [p for p in res.stdout.decode("utf-8", errors="replace").split("\0") if p]


def _report(label: str, lang: str | None, old: str | None, new: str | None) -> int:
    """Print the verdict for one file and return its exit code."""
    if lang is None:
        print(f"UNSUPPORTED {label}: unsupported file type")
        return 2
    if old is None or new is None:
        print(f"CHANGED {label} ({lang}): file {'added' if old is None else 'deleted'}")
        return 1
    try:
        diff = compare_texts(lang, old, new)
    except ParseError as exc:
        print(f"UNSUPPORTED {label} ({lang}): parse error: {exc}")
        return 2
    if diff is None:
        print(f"EQUIV {label} ({lang})")
        return 0
    print(f"CHANGED {label} ({lang})")
    print(_fmt("base", diff.left))
    print(_fmt("head", diff.right))
    return 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Prove a change altered comments only.")
    ap.add_argument("revs", nargs="*", metavar="BASE HEAD [FILE ...]")
    ap.add_argument("--files-pair", nargs=2, metavar=("OLD", "NEW"))
    ap.add_argument("--lang", default="auto", help="auto, " + ", ".join(LANGS))
    ns = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(errors="backslashreplace")

    if ns.files_pair:
        if ns.revs:
            ap.error("--files-pair cannot be combined with BASE HEAD")
        old_p, new_p = (Path(p) for p in ns.files_pair)
        lang = detect_lang(str(old_p)) if ns.lang == "auto" else ns.lang
        if lang is not None and lang not in LANGS:
            print(f"UNSUPPORTED {old_p}: unknown language {lang!r}")
            return 2
        try:
            old_t, new_t = _decode(old_p.read_bytes()), _decode(new_p.read_bytes())
        except OSError as exc:
            print(f"UNSUPPORTED {old_p}: cannot read: {exc}")
            return 2
        return _report(f"{old_p} {new_p}", lang, old_t, new_t)

    if len(ns.revs) < 2:
        ap.error("BASE and HEAD are required (or use --files-pair)")
    base, head, *files = ns.revs
    try:
        root = _repo_root()
        explicit = bool(files)
        if explicit:
            files = [_rel(root, f) for f in files]
        else:
            files = changed_files(root, base, head)
        worst = 0
        counts = {"EQUIV": 0, "CHANGED": 0, "UNSUPPORTED": 0, "SKIPPED": 0}
        for f in files:
            lang = detect_lang(f)
            if lang is None and not explicit:
                print(f"SKIPPED {f}: unsupported file type")
                counts["SKIPPED"] += 1
                continue
            old: str | None = None
            new: str | None = None
            try:
                if lang is not None:
                    old, new = read_rev(root, base, f), read_rev(root, head, f)
                    if old is None and new is None:
                        print(f"UNSUPPORTED {f}: not present in either revision")
                        worst = 2
                        counts["UNSUPPORTED"] += 1
                        continue
            except ParseError as exc:
                print(f"UNSUPPORTED {f}: {exc}")
                worst = 2
                counts["UNSUPPORTED"] += 1
                continue
            code = _report(f, lang, old, new)
            counts[("EQUIV", "CHANGED", "UNSUPPORTED")[code]] += 1
            worst = max(worst, code)
        print(
            f"summary: {counts['EQUIV']} equiv, {counts['CHANGED']} changed, "
            f"{counts['UNSUPPORTED']} unsupported, {counts['SKIPPED']} skipped"
        )
    except ParseError as exc:
        print(f"UNSUPPORTED: {exc}")
        return 2
    return worst


def _rel(root: Path, f: str) -> str:
    p = Path(f)
    if p.exists():
        try:
            return p.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            pass
    return p.as_posix()


if __name__ == "__main__":
    sys.exit(main())
