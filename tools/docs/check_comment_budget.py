#!/usr/bin/env python3
"""Measure source-comment size budgets and banned comment content against a shrink-only baseline.

Scope: git-tracked files under rtl/, tb/, sim/, pnr/ and .github/workflows/ (a tree walk when the
root is not a git top level), except pnr/commercial/, micro_p/, *.json, *.md, generated files and
Python files that use __doc__.

Budget rules: hdr (RTL header 40 lines, pnr constraint header 25), blk (RTL comment block 8),
doc (Python module docstring 25), mk (Makefile comment run 6), wf (workflow comment run 5).
Content rules: bead, ghpr, run, date, meas, fline. Tool pragma lines neither count nor break.

Usage: python tools/docs/check_comment_budget.py [--root DIR] [--baseline FILE]
           [--update-baseline [--allow-growth]] [--report] [FILE ...]

Exit codes:
  0  findings equal the baseline exactly (also always for --report, and a successful update)
  1  regression, or the baseline can be tightened, or an update would grow it
  2  usage or setup error
"""

from __future__ import annotations

import argparse
import ast
import io
import re
import subprocess
import sys
import tokenize
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

SCOPE_PREFIXES = ("rtl/", "tb/", "sim/", "pnr/", ".github/workflows/")
EXCLUDED_PREFIXES = ("pnr/commercial/", "micro_p/")
LIMITS = {"hdr_rtl": 40, "blk": 8, "doc": 25, "hdr_pnr": 25, "mk": 6, "wf": 5}
BLOCK_RULES = ("hdr", "blk", "doc", "mk", "wf")
CONTENT_RULES = ("bead", "ghpr", "run", "date", "meas", "fline")
SV_EXT = (".sv", ".svh", ".v", ".vh")
HASH_EXT = (".tcl", ".sdc", ".upf", ".cfg", ".sh", ".bash")
PNR_HDR_EXT = (".sdc", ".upf", ".tcl", ".cfg")
DEFAULT_BASELINE = "tools/docs/comment_budget_baseline.txt"

# A pragma comment is a tool directive: it neither counts toward a block nor breaks one.
_PRAGMA_START = re.compile(r"^\s*\**\s*(verilator|synopsys|synthesis|pragma|spyglass)\b", re.I)
_PRAGMA_ANY = re.compile(r"noqa|type: ignore|pylint:|shellcheck|upf-check")

_BEAD_ID = re.compile(r"\b(?i:beads?)\s+[`'\"(#]*(?P<id>[a-z0-9]{2,6}(?:\.\d+)?)\b(?!-)")
_CONTENT = {
    "ghpr": re.compile(
        r"\b(?:GH|PR)\s?#\d+|\b(?i:issue|epic)\s*#\d{2,4}\b|\b(?:post|pre)-#\d{2,4}\b"
    ),
    "run": re.compile(r"RUN_\d{4}-\d{2}-\d{2}"),
    "date": re.compile(r"\b20\d\d-\d\d-\d\d\b"),
    "meas": re.compile(r"-?\d+(\.\d+)?\s?(ps|ns|MHz|GHz|mW|uW|µW|µm|um|µm²|um²|pF|fF)\b"),
    "fline": re.compile(r"[\w./-]+\.(sv|svh|v|py|sdc|tcl|upf|mk|yml|sh):\d+"),
}
_BEAD_LONG = re.compile(r"claude_verilog_test-[a-z0-9.]+")
# English words that follow "bead" in prose. Only the bare three-letter case consults this list;
# a token with a digit, or three letters plus a .N suffix, is always an ID.
_BEAD_STOP = frozenset(
    """
    the was and for has had are not but its can may did see all any one two new old now yet per via
    who how why out off own set got nan ids id is in on of to as at by or if it be we so no this
    that with from then when were been will also only note notes list epic work text tags rows
    state issue issues track tracker export import hooks tool tools file files data base body
    bug bugs fix fixes use used uses are our you your his her him she they them their there
    here what which while where whose than too very just more most much such some each both
    few many other same own like into onto over under upon about after again below above
    mark marks line lines name names type types kind kinds form forms code open done need needs
    run runs ran add adds map maps key keys log logs row col end top get let put way ago
    day days ten six nine zero ref refs due non nor
    """.split()
)


@dataclass(frozen=True)
class Finding:
    path: str
    rule: str
    line: int
    size: int | None = None
    text: str = ""


@dataclass
class Line:
    code: bool = False  # real code outside comments
    segs: tuple[str, ...] = ()  # comment text pieces
    comment_only: bool = False  # counts toward comment runs
    blank: bool = False

    @property
    def pragma(self) -> bool:
        return any(_PRAGMA_START.match(s) or _PRAGMA_ANY.search(s) for s in self.segs)


def is_bead_ref(text: str) -> bool:
    if _BEAD_LONG.search(text):
        return True
    for m in _BEAD_ID.finditer(text):
        base = m.group("id").split(".")[0]
        if len(base) < 2:
            continue
        if any(ch.isdigit() for ch in base):
            return True
        if len(base) == 3 and base.isalpha() and (m.group("id") != base or base not in _BEAD_STOP):
            return True
    return False


def content_rules(text: str) -> list[str]:
    hits = []
    if is_bead_ref(text):
        hits.append("bead")
    for rule, rx in _CONTENT.items():
        if rule == "meas" and "measured-ok" in text:
            continue
        if rx.search(text):
            hits.append(rule)
    return hits


# ------------------------------------------------------------------------------ line classifiers
def scan_c_like(text: str) -> list[Line]:
    out: list[Line] = []
    in_block = False
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        segs: list[str] = []
        code = False
        i, n = 0, len(line)
        in_block_at_start = in_block
        while i < n:
            if in_block:
                j = line.find("*/", i)
                if j < 0:
                    segs.append(line[i:].lstrip("*"))
                    i = n
                else:
                    segs.append(line[i:j].lstrip("*"))
                    in_block = False
                    i = j + 2
                continue
            c = line[i]
            if c == '"':
                code = True
                i += 1
                while i < n and line[i] != '"':
                    i += 2 if line[i] == "\\" else 1
                i += 1
            elif line.startswith("//", i):
                segs.append(line[i + 2 :])
                i = n
            elif line.startswith("/*", i):
                in_block = True
                i += 2
                if i >= n:
                    segs.append("")
            else:
                if not c.isspace():
                    code = True
                i += 1
        if in_block_at_start and not segs:
            segs.append("")
        out.append(
            Line(
                code=code,
                segs=tuple(segs),
                comment_only=bool(segs) and not code,
                blank=not line.strip(),
            )
        )
    return out


def split_hash(line: str) -> tuple[bool, str | None]:
    """Return (has_code, comment_text) for a #-comment language line (simple quote tracking)."""
    quote = ""
    code = False
    i, n = 0, len(line)
    while i < n:
        c = line[i]
        if c == "\\":
            code = True
            i += 2
            continue
        if quote:
            if c == quote:
                quote = ""
            i += 1
            continue
        if c in "\"'":
            quote = c
            code = True
        elif c == "#" and (i == 0 or line[i - 1].isspace() or line[i - 1] == ";"):
            return code, line[i + 1 :]
        elif not c.isspace():
            code = True
        i += 1
    return code, None


def scan_hash(text: str, make: bool = False) -> list[Line]:
    out: list[Line] = []
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        blank = not line.strip()
        if make and line.startswith("\t"):  # recipe: shell comments do not form make comment runs
            body = line.lstrip("\t").lstrip()
            segs = (body[1:],) if body.startswith("#") else ()
            out.append(Line(code=True, segs=segs, comment_only=False, blank=blank))
            continue
        code, com = split_hash(line)
        segs = (com,) if com is not None else ()
        out.append(Line(code=code, segs=segs, comment_only=bool(segs) and not code, blank=blank))
    return out


# ------------------------------------------------------------------------------ rule evaluation
def leading_block(lines: list[Line]) -> tuple[int, int, int]:
    """(count, first_line_no, end_index): comment lines before the first code line."""
    count, first, idx = 0, 0, 0
    for idx, ln in enumerate(lines):
        if ln.comment_only:
            if ln.pragma:
                continue
            if not first:
                first = idx + 1
            count += 1
        elif ln.blank:
            continue
        else:
            return count, first, idx
    return count, first, len(lines)


def runs(lines: list[Line], start: int = 0):
    """Yield (size, first_line_no) for each run of consecutive comment-only lines."""
    size, first = 0, 0
    for idx in range(start, len(lines)):
        ln = lines[idx]
        if ln.comment_only:
            if ln.pragma:
                continue
            if not size:
                first = idx + 1
            size += 1
        else:
            if size:
                yield size, first
            size = 0
    if size:
        yield size, first


def content_findings(path: str, lines: list[Line], skip: set[int] | None = None) -> list[Finding]:
    out = []
    for idx, ln in enumerate(lines):
        if not ln.segs or (skip and idx in skip):
            continue
        segs = [s for s in ln.segs if not (_PRAGMA_START.match(s) or _PRAGMA_ANY.search(s))]
        if not segs:
            continue
        joined = " ".join(segs)
        for rule in content_rules(joined):
            out.append(Finding(path, rule, idx + 1, None, joined.strip()[:100]))
    return out


def analyse_python(path: str, text: str) -> list[Finding]:
    if "__doc__" in text:
        return []
    out: list[Finding] = []
    src_lines = text.split("\n")
    comments: dict[int, str] = {}
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT:
                comments[tok.start[0]] = tok.string[1:]
    except (tokenize.TokenError, IndentationError, SyntaxError):
        for i, ln in enumerate(src_lines, 1):
            if ln.lstrip().startswith("#"):
                comments[i] = ln.lstrip()[1:]
    try:
        tree = ast.parse(text)
    except SyntaxError:
        tree = None
    doc_lines: set[int] = set()
    mod_doc = None
    if tree is not None:
        for node in ast.walk(tree):
            if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                body = node.body
                if (
                    body
                    and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)
                ):
                    e = body[0]
                    doc_lines.update(range(e.lineno, (e.end_lineno or e.lineno) + 1))
                    if isinstance(node, ast.Module):
                        mod_doc = e
    # comment-only line numbers (for the leading block and content rules)
    for ln_no, com in sorted(comments.items()):
        if (
            _PRAGMA_START.match(com)
            or _PRAGMA_ANY.search(com)
            or src_lines[ln_no - 1].startswith("#!")
        ):
            continue
        for rule in content_rules(com):
            out.append(Finding(path, rule, ln_no, None, com.strip()[:100]))
    for ln_no in sorted(doc_lines):
        seg = src_lines[ln_no - 1]
        if _PRAGMA_ANY.search(seg):
            continue
        for rule in content_rules(seg):
            out.append(Finding(path, rule, ln_no, None, seg.strip()[:100]))
    if path.startswith(("tb/", "sim/")):
        first_code = mod_doc.lineno if mod_doc else None
        if first_code is None and tree is not None and tree.body:
            first_code = tree.body[0].lineno
        lead = [
            n
            for n, c in comments.items()
            if (first_code is None or n < first_code)
            and src_lines[n - 1].lstrip().startswith("#")
            and not src_lines[n - 1].startswith("#!")
            and not _PRAGMA_START.match(c)
            and not _PRAGMA_ANY.search(c)
        ]
        dl = (mod_doc.end_lineno - mod_doc.lineno + 1) if mod_doc else 0
        total = len(lead) + dl
        if total > LIMITS["doc"]:
            out.append(Finding(path, "doc", mod_doc.lineno if mod_doc else 1, total))
    return out


def analyse(path: str, text: str) -> list[Finding]:
    name = path.rsplit("/", 1)[-1]
    ext = "." + name.rsplit(".", 1)[-1] if "." in name else ""
    head = "\n".join(text.split("\n", 5)[:5])
    if "GENERATED" in head or "DO NOT EDIT" in head:
        return []
    if ext == ".py":
        return analyse_python(path, text)
    out: list[Finding] = []
    if ext in SV_EXT:
        lines = scan_c_like(text)
        if path.startswith("rtl/"):
            count, first, end = leading_block(lines)
            if count > LIMITS["hdr_rtl"]:
                out.append(Finding(path, "hdr", first, count))
            for size, start in runs(lines, end):
                if size > LIMITS["blk"]:
                    out.append(Finding(path, "blk", start, size))
        out += content_findings(path, lines)
    elif name == "Makefile" or name.startswith("Makefile.") or ext == ".mk":
        lines = scan_hash(text, make=True)
        for size, start in runs(lines):
            if size > LIMITS["mk"]:
                out.append(Finding(path, "mk", start, size))
        out += content_findings(path, lines)
    elif ext in (".yml", ".yaml"):
        lines = scan_hash(text)
        if path.startswith(".github/workflows/"):
            for size, start in runs(lines):
                if size > LIMITS["wf"]:
                    out.append(Finding(path, "wf", start, size))
        out += content_findings(path, lines)
    elif ext in HASH_EXT:
        lines = scan_hash(text)
        if ext in PNR_HDR_EXT and path.startswith("pnr/"):
            count, first, _ = leading_block(lines)
            if count > LIMITS["hdr_pnr"]:
                out.append(Finding(path, "hdr", first, count))
        out += content_findings(path, lines)
    return out


# ------------------------------------------------------------------------------ files and baseline
def list_scope(root: Path) -> list[str]:
    files: list[str] = []
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve():
            res = subprocess.run(
                ["git", "-C", str(root), "ls-files"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=True,
            )
            files = [f for f in res.stdout.split("\n") if f]
    except OSError:
        files = []
    if not files:
        files = sorted(
            p.relative_to(root).as_posix()
            for p in root.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(root).parts
        )
    out = []
    for f in files:
        if not f.startswith(SCOPE_PREFIXES) or f.startswith(EXCLUDED_PREFIXES):
            continue
        if f.endswith((".json", ".md", ".gz", ".zip", ".tar", ".f")):
            continue
        out.append(f)
    return out


def _decode(raw: bytes) -> str:
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def collect(root: Path, only: set[str] | None = None) -> list[Finding]:
    findings: list[Finding] = []
    for rel in list_scope(root):
        if only is not None and rel not in only:
            continue
        p = root / rel
        if not p.is_file():
            continue
        try:
            raw = p.read_bytes()
        except OSError:
            continue
        if b"\0" in raw[:8192]:
            continue
        findings += analyse(rel, _decode(raw).replace("\r\n", "\n"))
    return findings


Entry = tuple[int, int | None]  # (count, worst)


def summarise(findings: list[Finding]) -> dict[tuple[str, str], Entry]:
    acc: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for f in findings:
        acc[(f.path, f.rule)].append(f)
    out: dict[tuple[str, str], Entry] = {}
    for key, fs in acc.items():
        sizes = [f.size for f in fs if f.size is not None]
        out[key] = (len(fs), max(sizes) if sizes else None)
    return out


def parse_baseline(text: str) -> dict[tuple[str, str], Entry]:
    out: dict[tuple[str, str], Entry] = {}
    for n, raw in enumerate(text.split("\n"), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        if len(parts) != 4 or not parts[2].isdigit() or (parts[3] and not parts[3].isdigit()):
            raise ValueError(f"baseline line {n} is malformed: {raw!r}")
        out[(parts[0], parts[1])] = (int(parts[2]), int(parts[3]) if parts[3] else None)
    return out


def fmt_entry(key: tuple[str, str], e: Entry) -> str:
    return f"{key[0]} | {key[1]} | {e[0]} | {'' if e[1] is None else e[1]}".rstrip()


BASELINE_HEADER = """\
# Comment-budget baseline (tools/docs/check_comment_budget.py). It may only shrink.
# Format: <path> | <rule> | <count> | <worst>
#   count = findings of that rule in that file; worst = largest size (blank for content rules).
# Rules: hdr blk doc mk wf (size budgets); bead ghpr run date meas fline (banned content).
# Update after a cleanup: python tools/docs/check_comment_budget.py --update-baseline
# Growth is refused; the check fails if an entry is higher or lower than the measured value.
"""


def render_baseline(entries: dict[tuple[str, str], Entry]) -> str:
    return BASELINE_HEADER + "".join(fmt_entry(k, entries[k]) + "\n" for k in sorted(entries))


def grows(cur: dict, base: dict) -> list[str]:
    msgs = []
    for key, (cnt, worst) in sorted(cur.items()):
        b = base.get(key)
        if b is None:
            msgs.append(f"new entry {fmt_entry(key, (cnt, worst))}")
        elif cnt > b[0] or (worst is not None and b[1] is not None and worst > b[1]):
            msgs.append(f"raised {fmt_entry(key, b)}  ->  {fmt_entry(key, (cnt, worst))}")
    return msgs


def report(findings: list[Finding]) -> str:
    out = ["Totals per rule:"]
    by_rule = Counter(f.rule for f in findings)
    for rule in BLOCK_RULES + CONTENT_RULES:
        out.append(f"  {rule:6s} {by_rule.get(rule, 0):6d}")
    out.append(f"  total  {len(findings):6d}")
    out.append("Totals per top-level directory:")
    by_dir: dict[str, Counter] = defaultdict(Counter)
    for f in findings:
        d = f.path.split("/", 2)[0:2] if f.path.startswith(".github") else f.path.split("/", 1)[:1]
        by_dir["/".join(d)][f.rule] += 1
    for d in sorted(by_dir):
        c = by_dir[d]
        out.append(
            f"  {d:20s} total {sum(c.values()):5d}  " + " ".join(f"{r}={c[r]}" for r in sorted(c))
        )
    per_file: dict[str, list[Finding]] = defaultdict(list)
    for f in findings:
        per_file[f.path].append(f)
    out.append("20 worst files (by finding count; block sizes in brackets):")
    ranked = sorted(per_file.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:20]
    for path, fs in ranked:
        blocks = ",".join(
            f"{r}={max(x.size for x in fs if x.rule == r)}"
            for r in BLOCK_RULES
            if any(x.rule == r for x in fs)
        )
        out.append(f"  {len(fs):5d}  {path}  [{blocks}]")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Comment size budgets against a shrink-only baseline.")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--update-baseline", action="store_true")
    ap.add_argument("--allow-growth", action="store_true")
    ap.add_argument("--report", action="store_true")
    ap.add_argument("files", nargs="*")
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"setup error: --root {root} is not a directory")
        return 2
    bpath = Path(args.baseline) if args.baseline else root / DEFAULT_BASELINE
    only: set[str] | None = None
    if args.files:
        only = set()
        for f in args.files:
            p = Path(f)
            p = p if p.is_absolute() else (Path.cwd() / p)
            try:
                only.add(p.resolve().relative_to(root).as_posix())
            except ValueError:
                only.add(Path(f).as_posix())
    findings = collect(root, only)
    cur = summarise(findings)
    if args.report:
        print(report(findings))
        return 0
    try:
        base_all = parse_baseline(bpath.read_text(encoding="utf-8")) if bpath.is_file() else {}
    except ValueError as e:
        print(f"setup error: {e}")
        return 2
    if not bpath.is_file() and not args.update_baseline:
        print(f"setup error: baseline {bpath} does not exist")
        return 2
    base = {k: v for k, v in base_all.items() if only is None or k[0] in only}
    if args.update_baseline:
        growth = grows(cur, base)
        if growth and not args.allow_growth:
            print("refusing to update: the baseline may only shrink (use --allow-growth once)")
            for g in growth:
                print("  " + g)
            return 1
        merged = {k: v for k, v in base_all.items() if only is not None and k[0] not in only}
        merged.update(cur)
        bpath.parent.mkdir(parents=True, exist_ok=True)
        bpath.write_text(render_baseline(merged), encoding="utf-8", newline="\n")
        print(f"baseline written: {len(merged)} entries -> {bpath}")
        return 0
    by_key: dict[tuple[str, str], list[Finding]] = defaultdict(list)
    for f in findings:
        by_key[(f.path, f.rule)].append(f)
    regress, tighten = [], []
    for key in sorted(set(cur) | set(base)):
        c, b = cur.get(key), base.get(key)
        if c == b:
            continue
        if c is None:
            tighten.append((key, None))
        elif b is None or c[0] > b[0] or (c[1] is not None and b[1] is not None and c[1] > b[1]):
            regress.append((key, c, b))
        else:
            tighten.append((key, c))
    for key, c, b in regress:
        print(
            f"REGRESSION {key[0]} [{key[1]}]: now {fmt_entry(key, c)}"
            + (f", baseline {fmt_entry(key, b)}" if b else ", no baseline entry")
        )
        for f in by_key[key][:12]:
            size = f" size {f.size}" if f.size is not None else ""
            print(f"    {f.path}:{f.line}: {f.rule}{size} {f.text}")
    if tighten:
        print("baseline can be tightened; replace/remove these lines:")
        for key, c in tighten:
            old = fmt_entry(key, base[key])
            print(f"  - {old}")
            if c is not None:
                print(f"  + {fmt_entry(key, c)}")
    if regress:
        print(f"FAIL: {len(regress)} regression(s)")
        return 1
    if tighten:
        print(f"FAIL: baseline is not exact ({len(tighten)} entries to tighten)")
        return 1
    print(f"OK: {len(cur)} baseline entries match exactly")
    return 0


if __name__ == "__main__":
    sys.exit(main())
