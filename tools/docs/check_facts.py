#!/usr/bin/env python3
"""Check that the hard facts of a document did not change when its prose was rewritten.

Facts are collected from each side as a multiset and must be equal:
  num    numbers with unit (25.0 ns, 571 MHz, -727.37 ps, 0x2000_8000, 8'hFF, 99.95 %)
  id     inline code, \\texttt/\\src/\\path/\\bead/\\lstinline, URLs, and bare tokens with an
         underscore, a dotted name or a file-path shape
  lbl    arguments of \\label, \\ref, \\cref, \\Cref, \\autoref, \\pageref
  ref    "GH #n", "PR #n" and RUN_YYYY-MM-DD_HH-MM-SS
  modal  must, must not, do not, never, always, only, cannot
  code   one sha256 per code block (verbatim, listings, Markdown fences)
Markdown list and heading numbers and LaTeX layout arguments are ignored.

Usage:
  python tools/docs/check_facts.py --before FILE_OR_REV:PATH --after FILE [--by-section]

Input is .tex or .md; REV:PATH reads the old version with git show. With
--by-section the comparison is per section (key: \\label for LaTeX, heading text for
Markdown) and added or removed sections are reported.

Exit codes: 0 facts equal, 1 differences (token, count before, count after, section),
2 usage or read error.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import re
import sys
from collections import Counter
from pathlib import Path

from prose_preserve import (
    _ESC,
    _FENCE,
    _HTMLTAG,
    _LINK,
    _MD_ESCCODE,
    _STASH,
    _UNESC,
    _VERB_ENV,
    _VERB_INLINE,
    _group,
    _latex_commands,
    _strip_html_comments,
    fold_symbols,
    git_show,
    inline_verb_body,
    read_text,
    strip_emphasis,
)

Facts = Counter  # Counter[tuple[str, str]]
Stash = list[tuple[str, str]]

_UNITS = (
    "ns|ps|us|ms|kHz|MHz|GHz|Hz|mW|uW|mV|uA|mA|um2|um|mm|nm|KiB|MiB|GiB|KB|MB|GB|kB|bits|bit|"
    "bytes|byte|dBm|dB|pF|fF|ppm|degC|deg|cycles|cycle|cyc|lanes|warps|ohm"
)
_NUM = re.compile(
    r"(?<![\w.])(?P<num>\d+'[sS]?[bBdDhHoO][0-9A-Fa-f_xXzZ?]+|0[xX][0-9A-Fa-f_]+"
    r"|[-+]?\d{1,3}(?:,\d{3})+(?:\.\d+)?|[-+]?\d[\d_]*(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    r"(?:\s*(?P<u1>%|(?:" + _UNITS + r")(?![A-Za-z]))|(?P<u2>[sWVABx])(?![A-Za-z]))?"
)
_REFPAT = re.compile(r"\b(GH|PR)\s*#(\d+)|(RUN_\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2})")
_MODAL = re.compile(r"\b(must\s+not|do\s+not|must|never|always|only|cannot)\b")
_ABBR = {"e.g", "i.e", "etc", "vs", "a.k.a", "w.r.t", "cf"}
_SECT = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?"
    r"\s*(?:\[[^\]]*\])?\s*(?=\{)"
)
_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_EDGE = ".,;:!?()[]{}\"'<>*"
_HEAD_NUM = r"(?:\d+(?:\.\d+)+\.?\s+|\d+\.\s+)?"


def _digest(content: str) -> str:
    return hashlib.sha256(" ".join(content.split()).encode("utf-8")).hexdigest()[:16]


def _resolve(text: str, stash: Stash, facts: Facts) -> str:
    def rep(m: re.Match[str]) -> str:
        kind, content = stash[int(m.group(1))]
        if kind == "code":
            facts[("code", _digest(content))] += 1
        else:
            facts[("id", " ".join(content.split()))] += 1
        return " "

    return _STASH.sub(rep, text)


def _is_ident(tok: str) -> bool:
    if not re.search(r"[A-Za-z]", tok):
        return False
    if "_" in tok:
        return True
    if tok.lower() in _ABBR:
        return False
    if re.fullmatch(r"[\w+-]+(?:\.[\w+-]+)+", tok):
        return True
    slashes = tok.count("/")
    if slashes and re.fullmatch(r"[~.]?[\w+.:-]+(?:/[\w+.:-]+)+/?", tok):
        return slashes >= 2 or "." in tok
    return False


def text_facts(text: str, facts: Facts) -> None:
    """Collect numbers, references, modal words and bare identifiers from plain text."""
    text = fold_symbols(text)

    def ref(m: re.Match[str]) -> str:
        facts[("ref", f"{m.group(1)} #{m.group(2)}" if m.group(1) else m.group(3))] += 1
        return " "

    text = _REFPAT.sub(ref, text)
    for m in _MODAL.finditer(text.lower()):
        facts[("modal", " ".join(m.group(1).split()))] += 1

    def num(m: re.Match[str]) -> str:
        value = m.group("num").replace(",", "") if "," in m.group("num") else m.group("num")
        unit = m.group("u1") or m.group("u2")
        facts[("num", f"{value} {unit}" if unit else value)] += 1
        return " "

    text = _NUM.sub(num, text)
    for raw in text.split():
        tok = raw.strip(_EDGE)
        if tok and _is_ident(tok):
            facts[("id", tok)] += 1


# ---------------------------------------------------------------- Markdown


def _md_stash_fences(text: str) -> tuple[list[str], Stash]:
    stash: Stash = []
    lines: list[str] = []
    fence, buf = "", []
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        m = _FENCE.match(line)
        if fence:
            if (
                m
                and m.group(1)[0] == fence[0]
                and len(m.group(1)) >= len(fence)
                and not m.group(2).strip()
            ):
                stash.append(("code", "\n".join(buf)))
                lines.append(f"\x00{len(stash) - 1}\x00")
                fence, buf = "", []
            else:
                buf.append(line)
        elif m and not (m.group(1)[0] == "`" and "`" in m.group(2)):
            fence, buf = m.group(1), []
        else:
            lines.append(line)
    if fence:
        stash.append(("code", "\n".join(buf)))
        lines.append(f"\x00{len(stash) - 1}\x00")
    return lines, stash


def _md_chunk_facts(lines: list[str], stash: Stash, facts: Facts) -> None:
    out: list[str] = []
    in_comment = False
    for line in lines:
        line, in_comment = _strip_html_comments(line, in_comment)
        line = re.sub(r"^\s*(?:>\s?)+", "", line)
        line = re.sub(r"^\s{0,3}#{1,6}\s+" + _HEAD_NUM, "", line)
        line = re.sub(r"^\s*(?:[-*+]|\d+[.)])\s+", "", line)
        if line.lstrip().startswith("|") or line.count("|") >= 2:
            line = line.replace("\\|", _ESC["|"]).replace("|", " ")
        out.append(line)
    text = "\n".join(out)

    def esc_or_code(m: re.Match[str]) -> str:
        if m.group(1):
            return _ESC[m.group(1)]
        facts[("id", " ".join(m.group(3).split()))] += 1
        return " "

    text = _MD_ESCCODE.sub(esc_or_code, text)

    def link(m: re.Match[str]) -> str:
        if m.group(3) and not m.group(3).startswith("#"):
            facts[("id", m.group(3))] += 1
        return f"{m.group(2)} "

    for _ in range(3):
        text = _LINK.sub(link, text)

    def auto(m: re.Match[str]) -> str:
        facts[("id", m.group(1))] += 1
        return " "

    text = re.sub(r"<((?:https?://|mailto:)[^>\s]+)>", auto, text)
    text = _HTMLTAG.sub(" ", text)
    text = strip_emphasis(html.unescape(text)).translate(_UNESC)
    text_facts(_resolve(text, stash, facts), facts)


def md_sections(text: str) -> list[tuple[str, Facts]]:
    lines, stash = _md_stash_fences(text)
    chunks: list[tuple[str, list[str]]] = [("(start)", [])]
    for line in lines:
        m = _HEADING.match(line)
        if m:
            key = strip_emphasis(re.sub(r"[`]", "", m.group(2))).strip()
            chunks.append((key, [line]))
        else:
            chunks[-1][1].append(line)
    return _finish(chunks, lambda ls, f: _md_chunk_facts(ls, stash, f))


# ------------------------------------------------------------------- LaTeX


def _tex_prepare(text: str) -> tuple[str, Stash]:
    stash: Stash = []

    def keep(m: re.Match[str]) -> str:
        if m.re is _VERB_ENV:
            stash.append(("code", m.group(2)))
            return f"\n\x00{len(stash) - 1}\x00\n"
        stash.append(("id", inline_verb_body(m)))
        return f"\x00{len(stash) - 1}\x00"

    text = _VERB_ENV.sub(keep, text.replace("\r\n", "\n"))
    text = _VERB_INLINE.sub(keep, text)

    def escapes(m: re.Match[str]) -> str:
        return _ESC[m.group(1)] if m.group(1) else " "

    text = re.sub(r"\\\\(?:\[[^\]\n]*\])?|\\([%&_#${}])", escapes, text)
    return re.sub(r"%[^\n]*", "", text), stash


def _tex_chunk_facts(text: str, stash: Stash, facts: Facts) -> None:
    text = re.sub(r"\A(" + _SECT.pattern + r"\{)\s*" + _HEAD_NUM, r"\1", text)
    text = _latex_commands(text, facts).replace("~", " ")
    text = re.sub(r"[&{}$]", " ", text).translate(_UNESC)
    text_facts(_resolve(text, stash, facts), facts)


def tex_sections(text: str) -> list[tuple[str, Facts]]:
    text, stash = _tex_prepare(text)
    chunks: list[tuple[str, list[str]]] = []
    starts = [m.end() for m in _SECT.finditer(text)]
    bounds = [m.start() for m in _SECT.finditer(text)]
    chunks.append(("(start)", [text[: bounds[0]] if bounds else text]))
    for k, (b, brace) in enumerate(zip(bounds, starts)):
        end = bounds[k + 1] if k + 1 < len(bounds) else len(text)
        g = _group(text, brace)
        title = (
            " ".join(_latex_commands(g[0]).replace("{", "").replace("}", "").split()) if g else ""
        )
        lab = None
        if g:
            lab = re.match(r"\s*\\label\{([^}]*)\}", text[g[1] : g[1] + 300])
        key = lab.group(1) if lab else title
        chunks.append((key or "(untitled)", [text[b:end]]))
    return _finish(chunks, lambda ls, f: _tex_chunk_facts("\n".join(ls), stash, f))


def _finish(chunks, fn):  # type: ignore[no-untyped-def]
    out: list[tuple[str, Facts]] = []
    seen: Counter[str] = Counter()
    for key, lines in chunks:
        seen[key] += 1
        facts: Facts = Counter()
        fn(lines, facts)
        out.append((key if seen[key] == 1 else f"{key}#{seen[key]}", facts))
    return out


# ---------------------------------------------------------------------- CLI


def load_side(spec: str) -> tuple[str, str]:
    """Return (format, text) for a file path or a REV:PATH git reference."""
    path, text = spec, ""
    if Path(spec).is_file():
        text = read_text(spec)
    elif ":" in spec:
        rev, path = spec.split(":", 1)
        text = git_show(rev, path)
    else:
        raise FileNotFoundError(spec)
    ext = Path(path).suffix.lower()
    if ext == ".tex":
        return "tex", text
    if ext in (".md", ".markdown"):
        return "md", text
    raise ValueError(f"unsupported input type (want .tex or .md): {path}")


def sections_of(fmt: str, text: str, by_section: bool) -> dict[str, Facts]:
    secs = tex_sections(text) if fmt == "tex" else md_sections(text)
    if by_section:
        return dict(secs)
    total: Facts = Counter()
    for _, f in secs:
        total.update(f)
    return {"(file)": total}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check that facts are unchanged after a rewrite.")
    ap.add_argument("--before", required=True, metavar="FILE_OR_REV:PATH")
    ap.add_argument("--after", required=True, metavar="FILE")
    ap.add_argument("--by-section", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="backslashreplace")
    try:
        bfmt, btext = load_side(args.before)
        afmt, atext = load_side(args.after)
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    before = sections_of(bfmt, btext, args.by_section)
    after = sections_of(afmt, atext, args.by_section)
    diffs = 0
    for key in before:
        if key not in after:
            print(f"SECTION-REMOVED\t{key}")
            diffs += 1
    for key in after:
        if key not in before:
            print(f"SECTION-ADDED\t{key}")
            diffs += 1
    for key in before:
        if key not in after:
            continue
        b, a = before[key], after[key]
        for fact in sorted(set(b) | set(a)):
            if b[fact] != a[fact]:
                kind, tok = fact
                print(f"DIFF\t{kind}\t{tok}\tbefore={b[fact]}\tafter={a[fact]}\tsection={key}")
                diffs += 1
    print("FACTS: equal" if not diffs else f"FACTS: {diffs} difference(s)")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
