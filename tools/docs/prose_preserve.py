#!/usr/bin/env python3
"""Prove that no prose was lost when text moves from one place to another.

Sources (--from), any mix of:
  FILE.md / FILE.txt   the whole file is source text
  diff:BASE:PATH       comment words removed from PATH between git revision BASE
                       and the working tree (comment extraction by file type)
Destinations (--to): .tex or .md files, or directories searched for .tex files.

Both sides are normalised to lower-case word tokens (Markdown and LaTeX markup
removed, symbols and emoji folded). Every source token must be covered by a run
of destination tokens. Runs of fewer than 3 tokens must also sit next to a
neighbouring run in the destination, so a dropped common word is not hidden by
the same word elsewhere.

Rules that keep both sides equal: a pictograph and its status macro fold to one token
(table tools/docs/pandoc/marks.tsv, shared with cvt.lua); a slash separates tokens
(URLs excepted); a code span is separated from the text next to it; GH and PR
references print "gh N" and "pr N"; a local link to a Markdown file keeps its text only.

Usage:
  python tools/docs/prose_preserve.py --from SRC [SRC ...] --to DEST [DEST ...]
         [--allow-drop FILE] [--min-run N]

Exit codes: 0 all prose found, 1 text lost (each run printed with its source
line and context), 2 usage or read error.
The last line is: PRESERVED: <n> source tokens, <m> missing in <k> runs
"""

from __future__ import annotations

import argparse
import ast
import difflib
import html
import io
import re
import string
import subprocess
import sys
import tokenize
import unicodedata
from bisect import bisect_left
from collections import Counter
from pathlib import Path

STRONG = 3  # runs at least this long are always accepted
SLACK = 4  # allowed destination gap for a short run next to its neighbour
CAP = 200  # candidate destination positions examined per step
CONTEXT = 12  # words of context printed on each side of a missing run

_SYMBOLS = {
    "\u2014": "--",
    "\u2013": "--",
    "\u2265": ">=",
    "\u2264": "<=",
    "\u2192": "->",
    "\u2190": "<-",
    "\u00d7": "x",
    "\u00b5": "u",
    "\u03bc": "u",
    "\u00b1": "+/-",
    "\u2248": "~",
    "\u2260": "!=",
    "\u00b0": "deg",
    "\u00a7": " section ",
    "\u2018": "'",
    "\u2019": "'",
    "\u201c": '"',
    "\u201d": '"',
    "\u2026": "...",
    "\u2212": "-",
    "\u2010": "-",
    "\u2011": "-",
    "\ufe0f": "",
}
MARKS_FILE = Path(__file__).resolve().parent / "pandoc" / "marks.tsv"


def load_marks(path: Path = MARKS_FILE) -> list[tuple[int, str, str]]:
    """Rows (code point, LaTeX replacement, token) of the pictograph table."""
    rows: list[tuple[int, str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cp, tex, token = line.split("\t")
        rows.append((int(cp, 16), tex, token))
    return rows


_MARK_ROWS = load_marks()
# A pictograph folds to its token on both sides, so the two sides agree.
_SYMBOLS.update({chr(cp): f" {token} " for cp, _tex, token in _MARK_ROWS})
_SYM_TABLE = {ord(k): v for k, v in _SYMBOLS.items()}
_PUNCT = string.punctuation + "\u2022\u00b7\u2023"
_PUNCT_NOSIGN = _PUNCT.replace("-", "").replace("+", "")

# Characters that must survive later markup passes; mapped to private-use code points.
_ESC_CHARS = "\\`*_{}[]()#+-.!|<>~$%&\"'^"
_ESC = {c: chr(0xE000 + i) for i, c in enumerate(_ESC_CHARS)}
_UNESC = {ord(v): k for k, v in _ESC.items()}


def _esc(s: str) -> str:
    return "".join(_ESC.get(c, c) for c in s)


def fold_symbols(text: str) -> str:
    """Unicode NFKC plus the fixed symbol and emoji table."""
    text = text.translate(_SYM_TABLE)
    text = unicodedata.normalize("NFKC", text).translate(_SYM_TABLE)
    return re.sub(r"-{2,}", "--", text)


def _clean_token(tok: str) -> str:
    t = tok.lstrip(_PUNCT_NOSIGN)
    if not (len(t) > 1 and t[0] in "+-" and t[1].isdigit()):
        t = t.lstrip(_PUNCT)
    return t.rstrip(_PUNCT)


def tokenize_text(text: str, first_line: int = 1) -> list[tuple[str, int]]:
    """Common normalisation step: word tokens with their line numbers."""
    out: list[tuple[str, int]] = []
    folded = fold_symbols(text).lower().replace("$", "")
    for ln, chunk in enumerate(folded.split("\n"), first_line):
        for raw in chunk.split():
            # A slash separates tokens, so a path and its parts count the same on both
            # sides (`a`/`b`, a link text that is the file name inside a printed path).
            for piece in [raw] if "://" in raw else raw.split("/"):
                tok = _clean_token(piece)
                if tok:
                    out.append((tok, ln))
    return out


def strip_emphasis(s: str) -> str:
    """Remove paired Markdown emphasis marks; keep literal `_` and `*`."""
    s = s.replace("~~", "")
    pending = {"_": 0, "*": 0}

    def repl(m: re.Match[str]) -> str:
        a, b = m.start(), m.end()
        left = s[a - 1] if a else " "
        right = s[b] if b < len(s) else " "
        run = m.group()
        mark = run[0]
        intraword = left.isalnum() and right.isalnum()
        if intraword and (mark == "_" or len(run) == 1):
            return run
        can_open = not right.isspace() and (mark == "*" or not left.isalnum())
        can_close = not left.isspace() and (mark == "*" or not right.isalnum())
        if can_close and pending[mark]:
            pending[mark] -= 1
            return ""
        if can_open:
            pending[mark] += 1
            return ""
        return run

    return re.sub(r"_+|\*+", repl, s)


# ---------------------------------------------------------------- Markdown

_FENCE = re.compile(r"^\s*(`{3,}|~{3,})(.*)$")
_LINKDEF = re.compile(
    r"^\s{0,3}\[([^\]\n]+)\]:\s*(\S+)(?:\s+(?:\"([^\"]*)\"|'([^']*)'|\(([^)]*)\)))?\s*$"
)
_FOOTDEF = re.compile(r"^\s{0,3}\[\^[^\]]+\]:\s*")
_MD_ESCCODE = re.compile(
    r"\\([\\`*_{}\[\]()#+\-.!|<>~$%&\"'^])"
    r"|(?<!`)(`+)(?!`)((?:[^\n]|\n(?!\s*\n))+?)(?<!`)\2(?!`)"
)
_LINK = re.compile(
    r"(!?)\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(\s*<?((?:[^()\s<>]|\([^()\s]*\))*)>?"
    r"(?:\s+(?:\"([^\"]*)\"|'([^']*)'))?\s*\)"
)
_REFLINK = re.compile(r"(!?)\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\[([^\]]*)\]")
_SHORTREF = re.compile(r"\[([^\[\]]+)\](?![\[(:])")
_HTMLTAG = re.compile(
    r"</?(?:br|hr|p|div|span|details|summary|sub|sup|b|i|em|strong|code|pre|a|img|table|"
    r"thead|tbody|tr|td|th|ul|ol|li|h[1-6]|center|kbd|u|s|small|font|blockquote)"
    r"(?:\s[^<>]*)?/?>",
    re.I,
)
_AUTOLINK = re.compile(r"<((?:https?://|mailto:)[^>\s]+)>")
_STASH = re.compile(r"\x00(\d+)\x00")


def _strip_html_comments(line: str, in_comment: bool) -> tuple[str, bool]:
    while True:
        if in_comment:
            end = line.find("-->")
            if end < 0:
                return "", True
            line, in_comment = line[end + 3 :], False
        start = line.find("<!--")
        if start < 0:
            return line, False
        end = line.find("-->", start + 4)
        if end < 0:
            return line[:start], True
        line = line[:start] + " " + line[end + 3 :]


def _md_prefix(line: str, table: bool) -> str:
    """Per-line Markdown markers: quote, heading, list bullet, task box, table pipes."""
    if _LINKDEF.match(line):
        return ""
    line = _FOOTDEF.sub("", line)
    line = re.sub(r"^\s*(?:>\s?)+", "", line)
    line = re.sub(r"^\s{0,3}#{1,6}(?:\s+|$)", "", line)
    line = re.sub(r"\s#+\s*$", "", line)
    line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
    line = re.sub(r"^\[[ xX]\]\s+", "", line)
    if table:
        line = line.replace("\\|", _ESC["|"]).replace("|", " ")
    return line


def _md_inline(text: str, defs: dict[str, str]) -> str:
    """Inline Markdown on a block of consecutive text lines (spans may cross lines)."""
    stash: list[str] = []

    def st(x: str) -> str:
        stash.append(x)
        return f"\x00{len(stash) - 1}\x00"

    def esc_or_code(m: re.Match[str]) -> str:
        return _ESC[m.group(1)] if m.group(1) else st(f" {m.group(3)} ")

    text = _MD_ESCCODE.sub(esc_or_code, text)
    text = re.sub(r"\[\^[^\]]+\]", "", text)

    def link(m: re.Match[str]) -> str:
        title = m.group(4) or m.group(5) or ""
        target = m.group(3)
        if target.startswith("#"):
            return f"{m.group(2)}  {title}"
        local = not re.match(r"[A-Za-z][A-Za-z0-9+.-]*:|//", target)
        path = re.sub(r"#.*$", "", target)
        text = _STASH.sub(lambda c: stash[int(c.group(1))], m.group(2)).strip()
        if local and not m.group(1) and path.endswith(".md"):
            return f"{m.group(2)}  {title}"
        if local and not m.group(1) and text in (path, path.rsplit("/", 1)[-1]):
            return f" {st(target)}  {title}"
        return f"{m.group(2)} {st(target)} {title}"

    for _ in range(3):  # nested links such as [![alt](img)](url)
        text = _LINK.sub(link, text)

    def reflink(m: re.Match[str]) -> str:
        label = (m.group(3) or m.group(2)).lower()
        if label in defs:
            return f"{m.group(2)} {st(defs[label])}"
        return m.group(0)

    text = _REFLINK.sub(reflink, text)
    text = _SHORTREF.sub(
        lambda m: (
            f"{m.group(1)} {st(defs[m.group(1).lower()])}"
            if m.group(1).lower() in defs
            else m.group(0)
        ),
        text,
    )
    text = _AUTOLINK.sub(lambda m: st(m.group(1)), text)
    text = _HTMLTAG.sub(" ", text)
    text = html.unescape(text)
    text = strip_emphasis(text)
    text = _STASH.sub(lambda m: stash[int(m.group(1))], text)
    return text.translate(_UNESC)


def norm_markdown(text: str) -> str:
    """Strip Markdown markup, keep fence contents; one output line per input line."""
    raw = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kinds: list[str] = []
    fence = ""
    for line in raw:
        m = _FENCE.match(line)
        if fence:
            closing = (
                m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence)
            ) and not m.group(2).strip()
            kinds.append("f" if closing else "c")
            if closing:
                fence = ""
        elif m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            kinds.append("f")
            fence = m.group(1)
        else:
            kinds.append("t")
    defs: dict[str, str] = {}
    for i, line in enumerate(raw):
        d = _LINKDEF.match(line) if kinds[i] == "t" else None
        if d:
            defs[d.group(1).lower()] = d.group(2)
    table = [False] * len(raw)
    for i, line in enumerate(raw):
        is_align = (
            kinds[i] == "t"
            and "|" in line
            and "-" in line
            and re.fullmatch(r"[\s|:\-]+", line)
            and i > 0
            and kinds[i - 1] == "t"
            and "|" in raw[i - 1]
        )
        if is_align:
            table[i - 1] = table[i] = True
            j = i + 1
            while j < len(raw) and kinds[j] == "t" and raw[j].strip() and "|" in raw[j]:
                table[j] = True
                j += 1
    out: list[str] = []
    block: list[str] = []

    def flush() -> None:
        if block:
            out.append(_md_inline("\n".join(block), defs))
            block.clear()

    in_comment = False
    for i, line in enumerate(raw):
        if kinds[i] == "t":
            line, in_comment = _strip_html_comments(line, in_comment)
            block.append(_md_prefix(line, table[i]))
            continue
        flush()
        out.append("" if kinds[i] == "f" else line)
    flush()
    return "\n".join(out)


# ------------------------------------------------------------------- LaTeX

_VERB_ENV = re.compile(
    r"\\begin\{(lstlisting|logblock|textblock|verbatim\*?|Verbatim|minted)\}(?:\[[^\]]*\])?(?:\{[^}\n]*\})?"
    r"(.*?)\\end\{\1\}",
    re.S,
)
_VERB_INLINE = re.compile(
    r"\\(?:verb\*?|lstinline(?:\[[^\]]*\])?)(?P<d>[^A-Za-z\s{\[*])(?P<b>.*?)(?P=d)"
)
WS = " \t\n"
_CMD = re.compile(r"\\([A-Za-z]+)(\*?)")
_DROP1 = {
    "label", "index", "cref", "Cref", "ref", "autoref", "pageref", "eqref", "nameref",
    "hypertarget", "hyperlink", "hspace", "vspace", "setcounter", "phantom", "hphantom",
    "vphantom",
}  # fmt: skip
_REFS = {"cref", "Cref", "ref", "autoref", "pageref", "eqref", "nameref"}
# Inline formatting commands whose argument may sit inside a word; others add a space.
_GLUE = {
    "textbf", "textit", "emph", "texttt", "textsc", "textsl", "textrm", "textsf", "textmd",
    "textup", "textnormal", "underline", "mbox", "hbox", "passthrough", "text",
    "textsuperscript", "textsubscript", "sout", "st",
}  # fmt: skip
_CODE_CMDS = {"texttt", "src", "path", "bead", "lstinline"}
_ARG_ENVS = {
    "tabular": 1, "tabular*": 2, "longtable": 1, "tabularx": 2, "array": 1,
    "minipage": 1, "multicols": 1,
}  # fmt: skip
_SYM_CMD = {
    "textbackslash": "\\", "textasciitilde": "~", "textasciicircum": "^",
    "textless": "<", "textgreater": ">", "textbar": "|", "textquotesingle": "'",
    "textquotedbl": '"', "textquoteleft": "'", "textquoteright": "'",
    "textquotedblleft": '"', "textquotedblright": '"', "textendash": "--",
    "textemdash": "--", "ldots": "...", "dots": "...", "textellipsis": "...",
    "textunderscore": "_", "textbraceleft": "{", "textbraceright": "}",
    "textdollar": "$", "textpercent": "%", "textampersand": "&", "textnumbersign": "#",
    "textsection": " section ", "texttimes": "x", "textmu": "u", "textpm": "+/-",
    "textdegree": "deg", "allowbreak": "",
}  # fmt: skip
# The status macros come from the pictograph table: \name{} prints its token word.
_MARK_LITERALS: dict[str, str] = {}
for _cp, _tex, _tok in _MARK_ROWS:
    _m = re.fullmatch(r"\\([A-Za-z]+)\{\}", _tex)
    if _m:
        _SYM_CMD[_m.group(1)] = f" {_tok} "
    else:
        _MARK_LITERALS[_tex] = f" {_tok} "
# Macros whose argument prints as written; code spans are separated from their neighbours.
_SPACED_CMDS = {"code", "src", "runid", "bead", "texttt"}
_REF_WORDS = {"ghref": "gh", "prref": "pr"}


def _group(s: str, i: int) -> tuple[str, int] | None:
    if i >= len(s) or s[i] != "{":
        return None
    depth = 0
    for j in range(i, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
            if depth == 0:
                return s[i + 1 : j], j + 1
    return None


def _opt(s: str, i: int) -> tuple[str, int] | None:
    if i >= len(s) or s[i] != "[":
        return None
    depth = 0
    for j in range(i + 1, len(s)):
        if s[j] == "{":
            depth += 1
        elif s[j] == "}":
            depth -= 1
        elif s[j] == "]" and depth <= 0:
            return s[i + 1 : j], j + 1
    return None


def _plain(arg: str) -> str:
    text = _latex_commands(arg).replace("{", "").replace("}", "").replace("~", " ")
    return " ".join(text.translate(_UNESC).split())


def _latex_commands(s: str, facts: Counter[tuple[str, str]] | None = None) -> str:
    out: list[str] = []
    i, n = 0, len(s)
    while i < n:
        j = s.find("\\", i)
        if j < 0:
            out.append(s[i:])
            break
        out.append(s[i:j])
        i = j
        m = _CMD.match(s, i)
        if not m:
            nxt = s[i + 1 : i + 2]
            if nxt == "^":
                out.append(_esc("^"))
                i += 2
                if s.startswith("{}", i):
                    i += 2
                continue
            out.append("" if nxt in ("-", "(", ")") else " ")
            i += 2
            continue
        name, i = m.group(1), m.end()
        if name in _SYM_CMD:
            out.append(_esc(_SYM_CMD[name]))
            if s.startswith("{}", i):
                i += 2
            else:
                while i < n and s[i] in WS:
                    i += 1
        elif name in ("begin", "end"):
            g = _group(s, i)
            env = g[0] if g else ""
            i = g[1] if g else i
            if name == "begin":
                o = _opt(s, i)
                i = o[1] if o else i
                for _ in range(_ARG_ENVS.get(env, 0)):
                    g = _group(s, i)
                    i = g[1] if g else i
            out.append(" ")
        elif facts is not None and name in _CODE_CMDS:
            o = _opt(s, i)
            i = o[1] if o else i
            g = _group(s, i)
            if g:
                facts[("id", _plain(g[0]))] += 1
                i = g[1]
            out.append(" ")
        elif name in _REF_WORDS and _group(s, i):
            g = _group(s, i)
            assert g is not None
            out.append(f"{_REF_WORDS[name]} {_plain(g[0])}")
            i = g[1]
        elif name in _SPACED_CMDS and _group(s, i):
            g = _group(s, i)
            assert g is not None
            out.append(f" {_latex_commands(g[0])} ")
            i = g[1]
        elif name in _DROP1:
            o = _opt(s, i)
            i = o[1] if o else i
            g = _group(s, i)
            if facts is not None and g and (name == "label" or name in _REFS):
                for part in g[0].split(","):
                    if part.strip():
                        facts[("lbl", part.strip().translate(_UNESC))] += 1
            i = g[1] if g else i
            out.append(" ")
        elif name == "href":
            g1 = _group(s, i)
            g2 = _group(s, g1[1]) if g1 else None
            if g1 and g2 and facts is not None:
                facts[("id", g1[0].translate(_UNESC))] += 1
                out.append(_latex_commands(g2[0], facts) + " ")
                i = g2[1]
            elif g1 and g2:
                out.append(f"{_latex_commands(g2[0])} {g1[0]} ")
                i = g2[1]
        elif name == "url":
            g = _group(s, i)
            if g and facts is not None:
                facts[("id", g[0].translate(_UNESC))] += 1
                out.append(" ")
                i = g[1]
            elif g:
                out.append(f" {g[0]} ")
                i = g[1]
        elif name == "texorpdfstring":
            g1 = _group(s, i)
            g2 = _group(s, g1[1]) if g1 else None
            if g1 and g2:
                out.append(_latex_commands(g1[0], facts))
                i = g2[1]
        elif name in ("includegraphics", "includesvg"):
            o = _opt(s, i)
            i = o[1] if o else i
            g = _group(s, i)
            alt = re.search(r"alt=\{([^{}]*)\}", o[0]) if o else None
            if g:
                path = "" if facts is not None else g[0]
                out.append(f" {alt.group(1) if alt else ''} {path} ")
                i = g[1]
        else:
            o = _opt(s, i)
            if o and o[1] < n and s[o[1]] == "{":
                i = o[1]
            out.append("" if s.startswith("{", i) and name in _GLUE else " ")
    return "".join(out)


def inline_verb_body(m: re.Match[str]) -> str:
    """Body of a \\verb or \\lstinline match; pandoc backslash-escapes the latter."""
    body = m.group("b")
    if m.group(0).startswith("\\lstinline"):
        body = re.sub(r"\\([%&_#${}~^\\])", r"\1", body)
    return body


def norm_latex(text: str) -> str:
    """Strip LaTeX markup following the project's normalisation rules."""
    stash: list[str] = []

    def keep(m: re.Match[str]) -> str:
        stash.append(m.group(2) if m.re is _VERB_ENV else inline_verb_body(m))
        pad = "\n" if m.re is _VERB_ENV else ""
        return f"{pad}\x00{len(stash) - 1}\x00{pad}"

    text = text.replace("\r\n", "\n")
    for lit, tok in _MARK_LITERALS.items():
        text = text.replace(lit, tok)
    text = _VERB_ENV.sub(keep, text)
    text = _VERB_INLINE.sub(keep, text)

    def escapes(m: re.Match[str]) -> str:
        return _ESC[m.group(1)] if m.group(1) else " "

    text = re.sub(r"\\\\(?:\[[^\]\n]*\])?|\\([%&_#${}])", escapes, text)
    text = re.sub(r"%[^\n]*", "", text)
    text = _latex_commands(text)
    text = text.replace("~", " ")
    text = re.sub(r"&", " ", text)
    text = text.replace("``", '"').replace("''", '"')
    text = re.sub(r"[{}$]", "", text)
    text = text.translate(_UNESC)
    return _STASH.sub(lambda m: stash[int(m.group(1))], text)


# ----------------------------------------------------- comment extraction

Piece = tuple[str, int]


def comments_sv(text: str) -> list[Piece]:
    out: list[Piece] = []
    i, n, line = 0, len(text), 1
    while i < n:
        c = text[i]
        if c == "\n":
            line += 1
            i += 1
        elif c == '"':
            i += 1
            while i < n and text[i] not in '"\n':
                if text[i] == "\\" and i + 1 < n:
                    line += text[i + 1] == "\n"
                    i += 2
                else:
                    i += 1
            if i < n and text[i] == '"':
                i += 1
        elif text.startswith("//", i):
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append((text[i + 2 : j], line))
            i = j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            end = n if j < 0 else j
            body = text[i + 2 : end]
            for k, part in enumerate(body.split("\n")):
                out.append((re.sub(r"^\s*\*+", "", part), line + k))
            line += body.count("\n")
            i = n if j < 0 else j + 2
        else:
            i += 1
    return out


def comments_hash(text: str, makefile: bool = False) -> list[Piece]:
    out: list[Piece] = []
    for ln, line in enumerate(text.split("\n"), 1):
        if makefile and line.startswith("\t"):
            continue
        s = line.lstrip()
        if s.startswith("#"):
            out.append((s.lstrip("#"), ln))
    return out


def comments_py(text: str) -> list[Piece]:
    out: list[Piece] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                out.append((tok.string.lstrip("#"), tok.start[0]))
        tree = ast.parse(text)
    except (tokenize.TokenError, SyntaxError, ValueError) as exc:
        print(f"warning: python parse failed ({exc}); using '#' lines only", file=sys.stderr)
        return comments_hash(text)
    kinds = (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
    for node in ast.walk(tree):
        if not isinstance(node, kinds) or not node.body:
            continue
        first = node.body[0]
        val = getattr(first, "value", None)
        if isinstance(first, ast.Expr) and isinstance(val, ast.Constant):
            if isinstance(val.value, str):
                for k, part in enumerate(val.value.split("\n")):
                    out.append((part, first.lineno + k))
    return out


_SV_EXT = {".sv", ".svh", ".v", ".vh"}
_HASH_EXT = {".tcl", ".sdc", ".upf", ".cfg", ".sh", ".yml", ".yaml", ".mk"}
_MAKEFILES = {"makefile", "gnumakefile"}


def extract_comments(path: str, text: str) -> list[Piece]:
    p = Path(path)
    ext = p.suffix.lower()
    if ext in _SV_EXT:
        return comments_sv(text)
    if ext == ".py":
        return comments_py(text)
    is_make = ext == ".mk" or p.name.lower() in _MAKEFILES
    if ext in _HASH_EXT or is_make:
        return comments_hash(text, is_make)
    raise ValueError(f"unsupported file type for comment extraction: {path}")


def _tokens_of(pieces: list[Piece]) -> list[tuple[str, int]]:
    toks: list[tuple[str, int]] = []
    for text, ln in pieces:
        toks.extend(tokenize_text(text, ln))
    return toks


# ----------------------------------------------------------- source loading


def git_show(rev: str, path: str) -> str:
    """Return the content of PATH at git revision REV."""
    p = Path(path).resolve()
    attempts = [(f"{rev}:./{p.name}", p.parent), (f"{rev}:{path}", None)]
    err = ""
    for spec, cwd in attempts:
        if cwd is not None and not cwd.is_dir():
            continue
        try:
            res = subprocess.run(
                ["git", "show", spec],
                cwd=cwd,
                capture_output=True,
                stdin=subprocess.DEVNULL,
                check=False,
            )
        except OSError as exc:
            raise OSError(f"cannot run git: {exc}") from exc
        if res.returncode == 0:
            return res.stdout.decode("utf-8", errors="replace")
        err = res.stderr.decode("utf-8", errors="replace").strip()
    raise OSError(f"git show {rev}:{path} failed: {err}")


def read_text(path: str | Path) -> str:
    return Path(path).read_bytes().decode("utf-8-sig", errors="replace")


def normalise_file(path: str, text: str) -> list[tuple[str, int]]:
    ext = Path(path).suffix.lower()
    if ext in (".md", ".markdown"):
        text = norm_markdown(text)
    elif ext == ".tex":
        text = norm_latex(text)
    return tokenize_text(text)


def load_source(spec: str) -> tuple[str, list[tuple[str, int]]]:
    if spec.startswith("diff:"):
        parts = spec.split(":", 2)
        if len(parts) != 3 or not parts[1] or not parts[2]:
            raise ValueError(f"bad diff source (want diff:BASE:PATH): {spec}")
        _, base, path = parts
        old = _tokens_of(extract_comments(path, git_show(base, path)))
        try:
            new_text = read_text(path)
        except FileNotFoundError:
            new_text = ""
        new = [t for t, _ in _tokens_of(extract_comments(path, new_text))]
        sm = difflib.SequenceMatcher(None, [t for t, _ in old], new, autojunk=False)
        gone: list[tuple[str, int]] = []
        for tag, i1, i2, _j1, _j2 in sm.get_opcodes():
            if tag in ("delete", "replace"):
                gone.extend(old[i1:i2])
        return f"{path} (vs {base})", gone
    return spec, normalise_file(spec, read_text(spec))


def load_dest(paths: list[str]) -> list[str]:
    toks: list[str] = []
    for d in paths:
        p = Path(d)
        if p.is_dir():
            files = sorted(p.rglob("*.tex"))
            if not files:
                raise ValueError(f"no .tex files under {d}")
        elif p.is_file():
            files = [p]
        else:
            raise FileNotFoundError(d)
        for f in files:
            toks.extend(t for t, _ in normalise_file(str(f), read_text(f)))
    return toks


# ------------------------------------------------------------------ matching


def find_missing(src: list[str], dest: list[str]) -> list[bool]:
    """Flag the source tokens that are not covered by a destination run."""
    index: dict[str, list[int]] = {}
    for pos, tok in enumerate(dest):
        index.setdefault(tok, []).append(pos)
    bigram: dict[tuple[str, str], list[int]] = {}
    for pos in range(len(dest) - 1):
        bigram.setdefault((dest[pos], dest[pos + 1]), []).append(pos)
    n, m = len(src), len(dest)
    runs: list[list[int]] = []  # [source start, length, destination start or -1]
    pos = prev_end = 0
    while pos < n:
        cands = bigram.get((src[pos], src[pos + 1])) if pos + 1 < n else None
        cands = cands or index.get(src[pos])
        if not cands:
            runs.append([pos, 1, -1])
            pos += 1
            continue
        k = bisect_left(cands, prev_end)
        window = cands[k : k + CAP]
        if len(window) < CAP:
            window = window + cands[: CAP - len(window)]
        best, bpos, rem = 0, -1, n - pos
        for c in window:
            if best and (c + best >= m or dest[c + best] != src[pos + best]):
                continue
            lim = min(rem, m - c)
            length = 0
            while length < lim and dest[c + length] == src[pos + length]:
                length += 1
            if length > best:
                best, bpos = length, c
                if length == rem or length >= 64:
                    break
        runs.append([pos, best, bpos])
        pos += best
        if best >= STRONG or prev_end <= bpos <= prev_end + SLACK:
            prev_end = bpos + best
    missing = [False] * n
    anchor: int | None = None
    for idx, (s0, length, c) in enumerate(runs):
        accepted = c >= 0
        if accepted and length < STRONG and n >= STRONG:
            nxt = runs[idx + 1][2] if idx + 1 < len(runs) else -1
            mono = nxt < 0 or nxt >= c + length
            near_prev = anchor is not None and anchor <= c <= anchor + SLACK
            near_next = (
                nxt >= 0
                and c + length <= nxt <= c + length + SLACK
                and (anchor is None or c >= anchor)
            )
            accepted = mono and (near_prev or near_next)
        if accepted:
            anchor = c + length
        else:
            for t in range(s0, s0 + length):
                missing[t] = True
    return missing


def allowed_mask(src: list[str], phrases: list[list[str]]) -> list[bool]:
    mask = [False] * len(src)
    for ph in phrases:
        k = len(ph)
        for i in range(len(src) - k + 1):
            if src[i : i + k] == ph:
                for t in range(i, i + k):
                    mask[t] = True
    return mask


def check_unit(
    label: str,
    toks: list[tuple[str, int]],
    dest: list[str],
    phrases: list[list[str]],
    min_run: int,
    report: list[str],
) -> tuple[int, int, int]:
    words = [t for t, _ in toks]
    allowed = allowed_mask(words, phrases)
    # Allowed phrases are removed before matching so they cannot break up a run.
    kept = [i for i, a in enumerate(allowed) if not a]
    miss_kept = find_missing([words[i] for i in kept], dest)
    bad = [False] * len(words)
    for i, m in zip(kept, miss_kept):
        bad[i] = m
    n_missing = n_runs = 0
    i = 0
    while i < len(words):
        if not bad[i]:
            i += 1
            continue
        j = i
        while j < len(words) and bad[j]:
            j += 1
        if j - i >= min_run:
            n_missing += j - i
            n_runs += 1
            before = " ".join(words[max(0, i - CONTEXT) : i])
            after = " ".join(words[j : j + CONTEXT])
            report.append(
                f"MISSING {label}:{toks[i][1]}: {j - i} token(s)\n"
                f"    ... {before} >>> {' '.join(words[i:j])} <<< {after} ..."
            )
        i = j
    return len(words), n_missing, n_runs


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check that source prose survives in the destination.")
    ap.add_argument("--from", dest="srcs", nargs="+", required=True, metavar="SRC")
    ap.add_argument("--to", dest="dests", nargs="+", required=True, metavar="DEST")
    ap.add_argument("--allow-drop", metavar="FILE")
    ap.add_argument("--min-run", type=int, default=1, metavar="N")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    try:
        dest = load_dest(args.dests)
        phrases: list[list[str]] = []
        if args.allow_drop:
            for line in read_text(args.allow_drop).splitlines():
                ph = [t for t, _ in tokenize_text(line)]
                if ph:
                    phrases.append(ph)
        units = [load_source(s) for s in args.srcs]
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    report: list[str] = []
    total = n_missing = n_runs = 0
    for label, toks in units:
        t, mi, ru = check_unit(label, toks, dest, phrases, max(1, args.min_run), report)
        total, n_missing, n_runs = total + t, n_missing + mi, n_runs + ru
    for block in report:
        print(block)
    print(f"PRESERVED: {total} source tokens, {n_missing} missing in {n_runs} runs")
    return 1 if n_missing else 0


if __name__ == "__main__":
    sys.exit(main())
