#!/usr/bin/env python3
"""Heuristic checker for likely ASD-STE100 Simplified Technical English problems.

THIS TOOL CANNOT PROVE COMPLIANCE. It finds likely violations with simple
patterns and accepts false positives. The official STE dictionary is not
available; word rules use the project list docs/manual/common/ste_words.yaml.

Usage:
    python tools/docs/ste_check.py [--strict-marked] [--all] [--pedantic]
        [--format text|tsv] [--header] PATH [PATH ...]
PATH is a .tex or .md file, a directory, or (with --header) a source file whose
leading comment block or module docstring is checked.

Rules: S1 procedural sentence over 20 words; S2 descriptive sentence over 25
words; P1 paragraph over 6 sentences; V1 passive voice; V2 compound tense; G1
-ing word not allowed; N1 noun cluster over 3 words; W1 word not approved; C1
contraction; M1 two instructions in one sentence; X1 step without imperative
(--pedantic only); Z1 waiver without a reason.
Waiver: "% ste-ok: reason" (LaTeX) or "<!-- ste-ok: reason -->" (Markdown) on
the line before a sentence. Marker "% ste: done" / "<!-- ste: done -->" in the
first 10 lines (or right after a \\chapter line) makes that region strict.

Exit codes: 0 no findings in marked regions (all findings are printed), 1
findings in a marked region, or any finding with --all (unless --strict-marked),
2 usage or read error.
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

HERE = Path(__file__).resolve().parent
COMMON = HERE.parent.parent / "docs" / "manual" / "common"
WORDS_FILE = COMMON / "ste_words.yaml"
DICT_FILE = COMMON / "dictionary.yaml"

PROC_LIMIT = 20
DESC_LIMIT = 25
PARA_LIMIT = 6
CLUSTER_LIMIT = 3

BE = {"is", "are", "was", "were", "be", "been", "being", "am"}
HAVE_DO = {"has", "have", "had", "having", "do", "does", "did", "done", "doing"}
IRREGULAR = set(
    """done made given taken written shown known seen run built set held kept left lost sent
    spent found put read cut hit let bound drawn driven chosen broken spoken stolen frozen
    forgotten gotten begun grown thrown blown flown worn torn born sworn hidden ridden risen
    fallen eaten beaten bitten forbidden forgiven mistaken overtaken proven withdrawn woken
    laid paid said sold told taught thought brought bought caught fought sought led fed bred
    met shot slept swept wept dealt felt meant lent bent burnt learnt dug hung stuck struck
    stung swung won spun sunk shrunk sung rung swum drunk lit slid sat stood understood
    withheld upheld overridden undone redone rewritten reset preset offset reread rebuilt
    remade retaken rerun overwritten been gone come become shed split spread shut quit""".split()
)
ADJ_PARTICIPLES = {
    "based", "related", "required", "needed", "associated", "dedicated", "limited", "reserved",
    "unused", "supported", "connected", "disabled", "enabled", "tied", "closed", "open",
    "given", "known", "shared", "fixed", "mixed", "advanced", "complicated", "selected",
}  # fmt: skip
NOT_PART_ED = {"need", "speed", "feed", "seed", "bed", "red", "embed", "indeed", "proceed",
               "exceed", "succeed", "hundred", "shred", "bleed", "breed", "weed", "reed"}  # fmt: skip  # noqa: E501
IMPERATIVES = set(
    """add apply assemble attach build call change check choose clear click close compare compile
    configure connect copy create delete disable do download drain enable enter execute exit fill
    find flash follow get go identify include insert install keep load lock look make measure
    monitor move note open pass perform power press prepare print push put read record release
    remove repeat replace reset restart return run save scroll select send set show start stop
    submit take tighten turn type update use verify wait write apply review report ensure
    inspect launch leave mark open pull push re-run rerun see store switch test tick use
    view""".split()
)
CONTRACTION_S = {"it", "that", "there", "what", "here", "let", "he", "she", "who", "how", "where"}
CODE_CMDS = "texttt|code|src|path|bead|runid|lstinline|url|verb|cvtmono|ghref|prref|nolinkurl"
REF_CMDS = "cref|Cref|ref|autoref|pageref|eqref|nameref|hyperref|vref"
DROP_CMDS = "label|index|vspace|hspace|phantomsection|addcontentsline|glsadd|newpage|clearpage"
SKIP_ENVS = {
    "lstlisting", "verbatim", "Verbatim", "logblock", "record", "relocated", "equation",
    "equation*", "align", "align*", "displaymath", "math", "tikzpicture", "minted",
}  # fmt: skip
VERBATIM_ENVS = {"lstlisting", "verbatim", "Verbatim", "logblock", "minted"}
TABLE_ENVS = {"tabular", "tabular*", "longtable", "tabularx"}
PROC_ENVS = {"enumerate", "procedure"}
SECTION_RE = re.compile(
    r"\\(?:part|chapter|section|subsection|subsubsection|paragraph|subparagraph)\*?"
    r"(?:\[[^\]]*\])?\{"
)
MARK_TEX = re.compile(r"^\s*%\s*ste:\s*done\b")
MARK_MD = re.compile(r"<!--\s*ste:\s*done\s*-->")
WAIVE_TEX = re.compile(r"^\s*%\s*ste-ok:(.*)$")
WAIVE_MD = re.compile(r"<!--\s*ste-ok:(.*?)-->")
MD_BEGIN = re.compile(r"<!--\s*(?:BEGIN\b.*?|[\w.-]+-instructions\b[^>]*?)\s*-->")
MD_END = re.compile(r"<!--\s*(?:END\b.*?|/[\w.-]+-instructions\b[^>]*?)\s*-->")


@dataclass
class Para:
    text: str
    raw: list[tuple[int, str]]
    proc: bool = False
    title: bool = False

    @property
    def first_line(self) -> int:
        return self.raw[0][0] if self.raw else 1


@dataclass
class Finding:
    path: str
    line: int
    rule: str
    msg: str
    sentence: str = ""


@dataclass
class Extracted:
    paras: list[Para] = field(default_factory=list)
    waivers: dict[int, str] = field(default_factory=dict)
    marked: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class Vocab:
    not_approved: dict[str, str]
    allowed_ing: set[str]
    function_words: set[str]
    terms_multi: list[str]
    terms_single: set[str]


_VOCAB: Vocab | None = None


def load_vocab(words_file: Path | None = None, dict_file: Path | None = None) -> Vocab:
    global _VOCAB
    if _VOCAB is not None and words_file is None and dict_file is None:
        return _VOCAB
    wf = words_file or WORDS_FILE
    df = dict_file or DICT_FILE
    data: dict = {}
    if yaml is not None and wf.is_file():
        data = yaml.safe_load(wf.read_text(encoding="utf-8")) or {}
    allowed = {str(w).lower() for w in data.get("allowed_ing", []) if isinstance(w, str)}
    multi: list[str] = []
    single: set[str] = set()
    if yaml is not None and df.is_file():
        entries = yaml.safe_load(df.read_text(encoding="utf-8")) or []
        for e in entries if isinstance(entries, list) else []:
            if not isinstance(e, dict) or "term" not in e:
                continue
            term = str(e["term"]).strip()
            if " " in term:
                multi.append(term.lower())
            else:
                single.add(term.lower())
                if e.get("kind") == "technical-name" and term.lower().endswith("ing"):
                    allowed.add(term.lower())
    multi.sort(key=len, reverse=True)
    vocab = Vocab(
        not_approved={str(k).lower(): str(v) for k, v in (data.get("not_approved") or {}).items()},
        allowed_ing=allowed,
        function_words={
            str(w).lower() for w in data.get("function_words", []) if isinstance(w, str)
        },
        terms_multi=multi,
        terms_single=single,
    )
    if words_file is None and dict_file is None:
        _VOCAB = vocab
    return vocab


# ------------------------------------------------------------- LaTeX text
def _match_brace(s: str, i: int) -> int:
    depth = 0
    n = len(s)
    while i < n:
        c = s[i]
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


def _drop_cmd(s: str, names: str, repl: str) -> str:
    pat = re.compile(rf"\\(?:{names})\*?(?:\[[^\]]*\])?(?=\{{)")
    out: list[str] = []
    pos = 0
    while True:
        m = pat.search(s, pos)
        if not m:
            out.append(s[pos:])
            break
        end = _match_brace(s, m.end())
        if end < 0:
            out.append(s[pos : m.end()])
            pos = m.end()
            continue
        out.append(s[pos : m.start()])
        out.append(repl)
        pos = end
    return "".join(out)


def _tidy(s: str) -> str:
    s = " ".join(s.split())
    return re.sub(r"\s+([.,;:!?)])", r"\1", s)


def clean_tex(s: str) -> str:
    s = re.sub(r"(?<!\\)%[^\n]*", "", s)
    s = re.sub(
        r"\$\$.*?\$\$|(?<!\\)\$[^$\n]*(?<!\\)\$|\\\(.*?\\\)|\\\[.*?\\\]", " MATH ", s, flags=re.S
    )
    s = _drop_cmd(s, CODE_CMDS, " CODE ")
    s = _drop_cmd(s, REF_CMDS, " REF ")
    s = _drop_cmd(s, DROP_CMDS, "")
    s = re.sub(r"\\href\{[^{}]*\}", "", s)
    s = re.sub(r"\\item(?:\[[^\]]*\])?", " ", s)
    for a, b in (
        (r"\textquotesingle", "'"), (r"\textquoteright", "'"), (r"\textasciitilde", "~"),
        (r"\textquotedbl", '"'), (r"\ldots", "..."), (r"\dots", "..."),
        (r"\textless", "<"), (r"\textgreater", ">"), (r"\textbackslash", " "),
    ):  # fmt: skip
        s = s.replace(a, b)
    s = re.sub(r"\\([&%#_${}])", r"\1", s)
    s = s.replace("\\\\", " ").replace("\\ ", " ").replace("~", " ")
    s = re.sub(r"\\[a-zA-Z]+\*?", " ", s)
    s = s.replace("---", " - ").replace("--", "-")
    s = s.replace("{", "").replace("}", "")
    return _tidy(s)


def extract_tex(lines: list[str]) -> Extracted:
    ex = Extracted()
    envs: list[str] = []
    buf: list[tuple[int, str]] = []
    buf_proc = False
    skip_name: str | None = None
    skip_depth = 0
    table: list[tuple[int, str]] | None = None
    table_name = ""

    def proc_now() -> bool:
        return any(e in PROC_ENVS for e in envs)

    def flush() -> None:
        nonlocal buf
        if buf:
            raw = "\n".join(t for _, t in buf)
            text = clean_tex(raw)
            if text:
                ex.paras.append(Para(text, list(buf), proc=buf_proc))
        buf = []

    def flush_table() -> None:
        nonlocal table
        if table is None:
            return
        raw = "\n".join(t for _, t in table)
        start = raw.find("{")
        body = raw
        if start >= 0:
            if raw.lstrip().startswith("["):
                close = raw.find("]")
                start = raw.find("{", close)
            end = _match_brace(raw, start) if start >= 0 else -1
            body = raw[end:] if end > 0 else raw
        offset = len(raw) - len(body)
        pos = 0
        line_starts = [0]
        for ch_i, ch in enumerate(raw):
            if ch == "\n":
                line_starts.append(ch_i + 1)
        for cell in re.split(r"&|\\\\", body):
            cstart = offset + body.find(cell, pos)
            pos = body.find(cell, pos) + len(cell)
            text = clean_tex(cell)
            if len(text.split()) >= 6:
                li = max(i for i, st in enumerate(line_starts) if st <= max(cstart, 0))
                lineno = table[min(li, len(table) - 1)][0]
                ex.paras.append(Para(text, [(lineno, cell)], proc=False))
        table = None

    for idx, line in enumerate(lines, start=1):
        w = WAIVE_TEX.match(line)
        if w:
            ex.waivers[idx] = w.group(1).strip()
            continue
        if MARK_TEX.match(line):
            if idx <= 10:
                ex.marked.append((1, len(lines) + 1))
            else:
                ex.marked.append((idx, idx))  # extended below
            continue
        if skip_name is not None:
            if (
                re.search(rf"\\begin\{{{re.escape(skip_name)}\}}", line)
                and skip_name not in VERBATIM_ENVS
            ):
                skip_depth += 1
            if re.search(rf"\\end\{{{re.escape(skip_name)}\}}", line):
                skip_depth -= 1
                if skip_depth <= 0:
                    skip_name = None
            continue
        if table is not None:
            table.append((idx, line))
            if re.search(rf"\\end\{{{re.escape(table_name)}\}}", line):
                flush_table()
            continue
        stripped = re.sub(r"(?<!\\)%.*$", "", line)
        m = re.search(r"\\begin\{([A-Za-z*]+)\}", stripped)
        if m and m.group(1) in SKIP_ENVS:
            flush()
            skip_name, skip_depth = m.group(1), 1
            if re.search(rf"\\end\{{{re.escape(skip_name)}\}}", stripped[m.end() :]):
                skip_name = None
            continue
        if m and m.group(1) in TABLE_ENVS:
            flush()
            table_name = m.group(1)
            table = [(idx, stripped[m.end() :])]
            if re.search(rf"\\end\{{{re.escape(table_name)}\}}", stripped):
                flush_table()
            continue
        sec = SECTION_RE.search(stripped)
        if sec:
            flush()
            end = _match_brace(stripped, sec.end() - 1)
            title = clean_tex(stripped[sec.end() : end - 1]) if end > 0 else ""
            if title:
                ex.paras.append(Para(title, [(idx, stripped)], title=True))
            continue
        for e in re.finditer(r"\\(begin|end)\{([A-Za-z*]+)\}", stripped):
            if e.group(1) == "begin":
                envs.append(e.group(2))
            elif e.group(2) in envs:
                while envs and envs.pop() != e.group(2):
                    pass
        if (
            not stripped.strip()
            or re.match(r"\s*\\(begin|end)\{", stripped)
            or "\\item" in stripped
        ):
            flush()
            if "\\item" in stripped and stripped.strip():
                buf_proc = proc_now()
                buf.append((idx, stripped))
            continue
        if not buf:
            buf_proc = proc_now()
        buf.append((idx, stripped))
    flush()
    flush_table()
    _fix_marked_tex(ex, lines)
    return ex


def _fix_marked_tex(ex: Extracted, lines: list[str]) -> None:
    """Turn chapter-local markers into line ranges."""
    chapters = [i for i, ln in enumerate(lines, start=1) if re.match(r"\s*\\chapter\b", ln)]
    out: list[tuple[int, int]] = []
    for a, b in ex.marked:
        if a == 1 and b == len(lines) + 1:
            out.append((a, b))
            continue
        prev = [c for c in chapters if c < a]
        nxt = [c for c in chapters if c > a]
        if prev and a - prev[-1] <= 2:
            out.append((prev[-1], (nxt[0] - 1) if nxt else len(lines)))
        else:
            out.append((a, a))
    ex.marked = out


# --------------------------------------------------------------- Markdown
_MD_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_LIST_RE = re.compile(r"^(\s*)([-*+]|\d+[.)])\s+(.*)$")


def clean_md(s: str) -> str:
    s = re.sub(r"`[^`]*`", " CODE ", s)
    s = _MD_LINK.sub(lambda m: m.group(1), s)
    s = re.sub(r"<(https?://|mailto:)[^>]*>", " CODE ", s)
    s = re.sub(r"https?://\S+", " CODE ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"\[\^[^\]]*\]", " ", s)
    s = re.sub(r"(\*\*|__|\*|~~)", "", s)
    s = re.sub(r"(?<![A-Za-z0-9])_|_(?![A-Za-z0-9])", "", s)
    s = s.replace("\\", " ")
    return _tidy(s)


def extract_md(lines: list[tuple[int, str]]) -> Extracted:
    """lines: (line number, text) pairs; blank text is kept to end paragraphs."""
    ex = Extracted()
    buf: list[tuple[int, str]] = []
    buf_proc = False
    fenced = False
    managed = False
    in_comment = False

    def flush() -> None:
        nonlocal buf, buf_proc
        if buf:
            raw = " ".join(t for _, t in buf)
            text = clean_md(raw)
            if text:
                ex.paras.append(Para(text, list(buf), proc=buf_proc))
        buf = []
        buf_proc = False

    for idx, line in lines:
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        w = WAIVE_MD.search(line)
        if w:
            ex.waivers[idx] = w.group(1).strip()
            continue
        if MARK_MD.search(line):
            ex.marked.append((1, 10**9) if idx <= 10 else (idx, idx))
            continue
        if MD_BEGIN.search(line):
            flush()
            managed = True
            continue
        if MD_END.search(line):
            managed = False
            continue
        if managed:
            continue
        if re.match(r"\s*(```|~~~)", line):
            flush()
            fenced = not fenced
            continue
        if fenced:
            continue
        if "<!--" in line:
            if "-->" not in line:
                in_comment = True
            line = re.sub(r"<!--.*?-->", "", line)
            if "<!--" in line:
                line = line.split("<!--")[0]
        text = line.rstrip()
        if not text.strip():
            flush()
            continue
        if text.lstrip().startswith("|"):
            flush()
            continue
        hm = re.match(r"\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$", text)
        if hm:
            flush()
            title = clean_md(hm.group(2))
            if title:
                ex.paras.append(Para(title, [(idx, text)], title=True))
            continue
        if re.match(r"\s*([-*_])\s*\1\s*\1[\s\-*_]*$", text) or re.match(r"\s*[=-]{3,}\s*$", text):
            flush()
            continue
        text = re.sub(r"^\s*>\s?", "", text)
        lm = _LIST_RE.match(text)
        if lm:
            flush()
            buf_proc = lm.group(2)[0].isdigit()
            buf.append((idx, lm.group(3)))
            continue
        buf.append((idx, text.strip()))
    flush()
    return ex


# ---------------------------------------------------------------- sentences
_ABBREV = {"e.g", "i.e", "etc", "vs", "cf", "approx", "fig", "no", "eq", "sec", "ch", "al", "st"}
_END_RE = re.compile(r"[.!?]+(?=\s|$)")


def split_sentences(text: str) -> list[str]:
    out: list[str] = []
    start = 0
    for m in _END_RE.finditer(text):
        before = text[start : m.start()]
        after = text[m.end() :].lstrip()
        last = re.search(r"([A-Za-z][A-Za-z.]*)$", before)
        if m.group(0) == "." and last:
            word = last.group(1).lower().rstrip(".")
            if word in _ABBREV and not (word == "etc" and after[:1].isupper()):
                continue
            if len(word) == 1 and after[:1].islower():
                continue
        if after and after[0].islower() and m.group(0) == ".":
            continue
        out.append(text[start : m.end()].strip())
        start = m.end()
    tail = text[start:].strip()
    if tail:
        out.append(tail)
    return [s for s in out if s]


_TOKEN_RE = re.compile(r"[A-Za-z0-9]+(?:[-'’/._][A-Za-z0-9]+)*|[^\sA-Za-z0-9]")


def tokens(sentence: str) -> list[str]:
    return _TOKEN_RE.findall(sentence)


def words_of(sentence: str) -> list[str]:
    return [t for t in tokens(sentence) if t[0].isalnum()]


# -------------------------------------------------------------------- rules
def is_participle(w: str) -> bool:
    lw = w.lower()
    if lw in IRREGULAR:
        return True
    return lw.endswith("ed") and len(lw) > 4 and lw not in NOT_PART_ED


_ADV = r"(?:\w+ly\s+)?"


def rule_findings(sentence: str, proc: bool, vocab: Vocab, pedantic: bool) -> list[tuple[str, str]]:
    res: list[tuple[str, str]] = []
    n_words = len(words_of(sentence))
    if proc and n_words > PROC_LIMIT:
        res.append(("S1", f"procedural sentence has {n_words} words (limit {PROC_LIMIT})"))
    if not proc and n_words > DESC_LIMIT:
        res.append(("S2", f"sentence has {n_words} words (limit {DESC_LIMIT})"))
    low = sentence.lower()
    plain = re.sub(r"\b(?:REF|CODE|MATH)\b", " ", low)
    # passive and compound tense
    seen: set[str] = set()
    for m in re.finditer(rf"\b(is|are|was|were|be|been|being|am)\s+{_ADV}([a-z]+)\b", plain):
        w = m.group(2)
        if (
            is_participle(w)
            and w not in ADJ_PARTICIPLES
            and not w.startswith("un")
            and m.group(0) not in seen
        ):
            seen.add(m.group(0))
            res.append(("V1", f'passive voice: "{m.group(0)}"'))
    for m in re.finditer(rf"\b(has|have|had)\s+{_ADV}([a-z]+)\b", plain):
        if is_participle(m.group(2)):
            res.append(("V2", f'compound tense: "{m.group(0)}"'))
    for m in re.finditer(r"\bwill\s+(?:be\s+)?[a-z]+", plain):
        res.append(("V2", f'future tense: "{m.group(0)}"'))
    for m in re.finditer(rf"\b(is|are|was|were|am)\s+{_ADV}([a-z]+ing)\b", plain):
        if m.group(2) not in {"being"}:
            res.append(("V2", f'progressive tense: "{m.group(0)}"'))
    # -ing words
    for w in words_of(sentence):
        lw = w.lower()
        if (
            len(lw) >= 5
            and lw.endswith("ing")
            and lw.isalpha()
            and lw not in vocab.allowed_ing
            and lw not in vocab.terms_single
        ):
            res.append(("G1", f'"-ing" word: "{w}"'))
    # not approved
    for key, repl in vocab.not_approved.items():
        pat = _na_pattern(key)
        if pat.search(low):
            res.append(("W1", f'"{key}" -> {repl}'))
    # contractions
    for m in re.finditer(r"\b([A-Za-z]+)(n['’]t|['’](?:re|ve|ll|d|m|s))\b", sentence):
        suffix = m.group(2).lower().replace("’", "'")
        if suffix == "'s" and m.group(1).lower() not in CONTRACTION_S:
            continue
        res.append(("C1", f'contraction: "{m.group(0)}"'))
    # noun cluster
    nc = noun_clusters(sentence, vocab)
    for c in nc:
        res.append(("N1", f'noun cluster of {len(c)} words: "{" ".join(c)}"'))
    if proc:
        wl = [w.lower() for w in words_of(sentence)]
        if wl and wl[0] in IMPERATIVES:
            m = re.search(r"\b(?:and|then)\s+([a-z]+)\b", plain)
            if m and m.group(1) in IMPERATIVES:
                res.append(("M1", f'more than one instruction: "{m.group(0)}"'))
        elif (
            pedantic
            and wl
            and wl[0] not in {"if", "when", "after", "before", "do", "make", "ref", "code"}
        ):
            res.append(("X1", f'step may not start with an imperative verb: "{wl[0]}"'))
    return res


_NA_CACHE: dict[str, re.Pattern[str]] = {}


def _na_pattern(key: str) -> re.Pattern[str]:
    pat = _NA_CACHE.get(key)
    if pat is not None:
        return pat
    parts = [re.escape(p) for p in key.split()]
    body = r"\s+".join(parts)
    if re.fullmatch(r"[a-z]+", key):
        stem = (
            key[:-1] + r"(?:y|ies|ied|ying)" if key.endswith("y") else key + r"(?:s|es|d|ed|ing)?"
        )
        body = stem
    pat = re.compile(rf"(?<![\w.]){body}(?!\w)" if not key.endswith(".") else rf"(?<![\w.]){body}")
    _NA_CACHE[key] = pat
    return pat


def noun_clusters(sentence: str, vocab: Vocab) -> list[list[str]]:
    text = sentence
    for term in vocab.terms_multi:
        text = re.sub(re.escape(term), " TERM ", text, flags=re.I)
    clusters: list[list[str]] = []
    run: list[str] = []
    for tok in tokens(text):
        lw = tok.lower()
        breaker = (
            not tok[0].isalnum()
            or tok in {"REF", "CODE", "MATH", "TERM"}
            or lw in vocab.function_words
            or lw in BE
            or lw in HAVE_DO
            or tok[0].isdigit()
        )
        if breaker:
            if len(run) > CLUSTER_LIMIT:
                clusters.append(run)
            run = []
        else:
            run.append(tok)
    if len(run) > CLUSTER_LIMIT:
        clusters.append(run)
    return clusters


# --------------------------------------------------------------- checking
def locate(sentence: str, para: Para, cursor: int) -> tuple[int, int]:
    """Find the source line of a sentence; returns (line, new cursor index)."""
    for m in re.finditer(r"[A-Za-z]{3,}", sentence):
        w = m.group(0)
        if w in {"REF", "CODE", "MATH"}:
            continue
        for i in range(cursor, len(para.raw)):
            if w in para.raw[i][1]:
                return para.raw[i][0], i
        break
    return para.raw[min(cursor, len(para.raw) - 1)][0], cursor


def check_extracted(
    ex: Extracted, path: str, vocab: Vocab, pedantic: bool = False
) -> list[Finding]:
    out: list[Finding] = []
    for line, reason in sorted(ex.waivers.items()):
        if not reason:
            out.append(Finding(path, line, "Z1", "waiver has no reason"))
    for para in ex.paras:
        sents = split_sentences(para.text)
        cursor = 0
        first = para.first_line
        waived_para = bool(ex.waivers.get(first - 1))
        if len(sents) > PARA_LIMIT and not para.title and not waived_para:
            out.append(
                Finding(
                    path,
                    first,
                    "P1",
                    f"paragraph has {len(sents)} sentences (limit {PARA_LIMIT})",
                    sents[0],
                )
            )
        for s in sents:
            line, cursor = locate(s, para, cursor)
            if ex.waivers.get(line - 1):
                continue
            if para.title:
                n = len(words_of(s))
                if n > DESC_LIMIT:
                    out.append(
                        Finding(path, line, "S2", f"title has {n} words (limit {DESC_LIMIT})", s)
                    )
                continue
            for rule, msg in rule_findings(s, para.proc, vocab, pedantic):
                out.append(Finding(path, line, rule, msg, s))
    return out


def header_lines(path: Path, text: str) -> list[tuple[int, str]]:
    """Leading comment block or module docstring of a source file."""
    lines = text.split("\n")
    ext = path.suffix.lower()
    if ext == ".py":
        try:
            tree = ast.parse(text)
            node = tree.body[0] if tree.body else None
            if (
                isinstance(node, ast.Expr)
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                first = node.lineno
                body = lines[first - 1 : node.end_lineno]
                joined = "\n".join(body)
                joined = re.sub(r'^\s*[rRuUbB]*("""|\'\'\'|"|\')', "", joined)
                joined = re.sub(r'("""|\'\'\'|"|\')\s*$', "", joined)
                return [(first + i, ln) for i, ln in enumerate(joined.split("\n"))]
        except SyntaxError:
            pass
    out: list[tuple[int, str]] = []
    started = False
    in_block = False
    for i, ln in enumerate(lines, start=1):
        s = ln.strip()
        if not started and (not s or s.startswith("#!") or re.match(r"#.*coding[:=]", s)):
            continue
        if in_block:
            if "*/" in s:
                in_block = False
                s = s.split("*/")[0]
                out.append((i, re.sub(r"^\*+\s?", "", s)))
                break
            out.append((i, re.sub(r"^\*+\s?", "", s)))
            continue
        if s.startswith("/*"):
            started = True
            in_block = "*/" not in s
            out.append((i, re.sub(r"^/\*+\s?|\*+/\s*$", "", s)))
            if not in_block:
                break
            continue
        m = re.match(r"^(//+|#+|--+|;+)\s?(.*)$", s)
        if m:
            started = True
            body = m.group(2)
            if re.fullmatch(r"[=\-*_#~/\s]*", body):
                body = ""
            out.append((i, body))
            continue
        break
    return out


# --------------------------------------------------------------------- CLI
def check_file(
    path: Path, vocab: Vocab, header: bool, pedantic: bool
) -> tuple[list[Finding], list[tuple[int, int]]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    ext = path.suffix.lower()
    name = path.as_posix()
    if header:
        ex = extract_md(header_lines(path, text))
        ex.marked = []
        return check_extracted(ex, name, vocab, pedantic), ex.marked
    if ext == ".tex":
        ex = extract_tex(text.split("\n"))
    else:
        ex = extract_md(list(enumerate(text.split("\n"), start=1)))
    return check_extracted(ex, name, vocab, pedantic), ex.marked


def collect(paths: list[str], header: bool) -> list[Path]:
    exts = (
        {".py", ".sv", ".v", ".svh", ".sh", ".tcl", ".sdc", ".upf", ".yml", ".yaml", ".cfg"}
        if header
        else {".tex", ".md"}
    )
    out: list[Path] = []
    for p in paths:
        pp = Path(p)
        if pp.is_dir():
            out += sorted(
                f
                for f in pp.rglob("*")
                if f.is_file()
                and f.suffix.lower() in exts
                and not any(part.startswith(".") for part in f.parts)
            )
        else:
            out.append(pp)
    return out


def in_marked(f: Finding, marked: list[tuple[int, int]]) -> bool:
    return any(a <= f.line <= b for a, b in marked)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Heuristic ASD-STE100 style checker (not a proof).")
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--strict-marked", action="store_true")
    ap.add_argument("--all", action="store_true", dest="all_fail")
    ap.add_argument("--pedantic", action="store_true")
    ap.add_argument("--header", action="store_true")
    ap.add_argument("--format", choices=("text", "tsv"), default="text")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    vocab = load_vocab()
    files = collect(args.paths, args.header)
    if not files:
        print("ste_check: no input files", file=sys.stderr)
        return 2
    total: list[Finding] = []
    marked_hits = 0
    for f in files:
        try:
            findings, marked = check_file(f, vocab, args.header, args.pedantic)
        except OSError as exc:
            print(f"ste_check: cannot read {f}: {exc}", file=sys.stderr)
            return 2
        for fd in findings:
            hit = in_marked(fd, marked)
            marked_hits += hit
            total.append(fd)
            sent = " ".join(fd.sentence.split())
            sent = sent if len(sent) <= 120 else sent[:117] + "..."
            if args.format == "tsv":
                print(
                    f"{fd.path}\t{fd.line}\t{fd.rule}\t{fd.msg}\t{sent}\t{'marked' if hit else ''}"
                )
            else:
                print(f"{fd.path}:{fd.line}: {fd.rule}: {fd.msg}" + (" [marked]" if hit else ""))
                if sent:
                    print(f"    {sent}")
    counts = Counter(fd.rule for fd in total)
    print(
        "summary: "
        + (", ".join(f"{r}={n}" for r, n in sorted(counts.items())) or "no findings")
        + f" ({len(total)} total, {marked_hits} in marked regions)",
        file=sys.stderr if args.format == "tsv" else sys.stdout,
    )
    print("note: heuristic report, not a proof of ASD-STE100 compliance", file=sys.stderr)
    if marked_hits:
        return 1
    if args.all_fail and not args.strict_marked and total:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
