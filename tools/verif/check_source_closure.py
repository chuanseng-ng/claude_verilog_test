#!/usr/bin/env python3
"""Verify that a Verilog/SystemVerilog source list "closes" over its imports.

Motivation (bead claude_verilog_test-50t, follow-up to v2q): source lists in
this repo are hand-maintained in three different places (PD `config.json`
`VERILOG_FILES`, `tb/cocotb/*/Makefile` `VERILOG_SOURCES`, `sim/Makefile`'s
and `pnr/Makefile`'s
several `*_SOURCES` variables) and nothing ever cross-checked them against
each other or against the RTL's actual `import <pkg>::*` statements. When RTL
gained a new package dependency (e.g. the M2 AXI4 burst upgrade adding
`import axi_pkg::*` to the cache/CPU files), only the lists someone happened
to re-run picked it up. `tb/cocotb/cpu/Makefile` silently rotted for an
entire phase (missing `axi_pkg`, `soc_addr_map_pkg`, and the whole EX1b/
EX1c/EX2 retiming split) because CI never builds it and nothing else caught
the gap.

This script performs a purely static, dependency-free check: for a given
named source list, does every `import <pkg>::...` used by a file *in that
list* have a matching `package <pkg>;` declared by some *other* file *also
in that list*? It does not invoke a simulator or compiler and does not
require `nix develop` — path resolution is via a small built-in GNU-Make
variable resolver (handles `:=`, `+=`, `?=`, backslash continuations, and a
narrow allowlist of `$(shell ...)` idioms actually used in this repo), not a
general Make implementation.

Usage:
    python3 tools/verif/check_source_closure.py               # scan the whole repo
    python3 tools/verif/check_source_closure.py --json         # machine-readable
    python3 tools/verif/check_source_closure.py path/to/config.json
    python3 tools/verif/check_source_closure.py path/to/Makefile

Exit code: 0 if every discovered list closes cleanly, 1 if any list has an
unresolved import, a missing file, or an unresolved Make variable/shell call
in its source list.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

PKG_DECL_RE = re.compile(r"^\s*package\s+([A-Za-z_]\w*)\s*;", re.MULTILINE)
IMPORT_RE = re.compile(r"\bimport\s+([A-Za-z_]\w*)\s*::")
SOURCE_LIST_VAR_RE = re.compile(r"^[A-Z0-9_]*(?:SOURCES|FILES)$")
VAR_REF_RE = re.compile(r"\$[({]([A-Za-z_][A-Za-z0-9_]*)[)}]")
ASSIGN_RE = re.compile(r"^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*(:=|\?=|\+=|=)\s*(.*)$")
DESIGN_FILE_EXTS = (".sv", ".v")


# ── package-import scan (real file content on disk) ─────────────────────────


def packages_provided(path: Path) -> set[str]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return set()
    return set(PKG_DECL_RE.findall(text))


def packages_imported(path: Path) -> set[str]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return set()
    return set(IMPORT_RE.findall(text))


@dataclass
class ListReport:
    label: str
    files: list[str] = field(default_factory=list)
    missing_files: list[str] = field(default_factory=list)
    unresolved_tokens: list[str] = field(default_factory=list)
    provided: set[str] = field(default_factory=set)
    imported: set[str] = field(default_factory=set)
    missing_packages: set[str] = field(default_factory=set)

    @property
    def closes(self) -> bool:
        return not (self.missing_packages or self.missing_files or self.unresolved_tokens)


def evaluate_list(label: str, tokens: list[str], base_dir: Path | None = None) -> ListReport:
    """Check one source list. Relative tokens resolve against `base_dir`.

    A Makefile's relative paths are relative to that Makefile's own directory,
    not the repo root — `pnr/Makefile` uses `RTL_DIR := ../rtl`, which means
    `<repo>/rtl` only when resolved from `pnr/`. Defaulting `base_dir` to the
    repo root would silently report every such file as missing.
    """
    base = base_dir or REPO_ROOT
    report = ListReport(label=label)
    for tok in tokens:
        if "$(" in tok or "${" in tok:
            report.unresolved_tokens.append(tok)
            continue
        path = Path(tok)
        if not path.is_absolute():
            path = (base / tok).resolve()
        if path.suffix.lower() not in DESIGN_FILE_EXTS:
            continue
        report.files.append(str(path))
        if not path.exists():
            report.missing_files.append(str(path))
            continue
        report.provided |= packages_provided(path)
        report.imported |= packages_imported(path)
    report.missing_packages = report.imported - report.provided
    return report


# ── JSON backend (pnr/*/config*.json "VERILOG_FILES") ───────────────────────


def extract_json_lists(config_path: Path) -> dict[str, list[str]]:
    try:
        data = json.loads(config_path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    files = data.get("VERILOG_FILES")
    if not isinstance(files, list):
        return {}
    resolved = []
    for entry in files:
        if not isinstance(entry, str):
            continue
        if entry.startswith("dir::"):
            rel = entry[len("dir::") :]
            resolved.append(str((config_path.parent / rel).resolve()))
        else:
            # Non dir:: entries (e.g. $PDK_ROOT/... macro views) aren't
            # repo-relative design sources — not in scope for this check.
            continue
    return {"VERILOG_FILES": resolved}


# ── Makefile backend (small GNU-Make variable resolver) ─────────────────────


def _logical_lines(text: str) -> list[tuple[bool, str]]:
    """Join backslash-continued lines; flag whether the first physical line
    of each logical line is a recipe line (starts with a tab)."""
    raw = text.split("\n")
    out: list[tuple[bool, str]] = []
    i, n = 0, len(raw)
    while i < n:
        line = raw[i]
        is_recipe = line.startswith("\t")
        buf = line
        while buf.rstrip().endswith("\\") and i + 1 < n:
            buf = buf.rstrip()[:-1] + " "
            i += 1
            buf += raw[i]
        out.append((is_recipe, buf))
        i += 1
    return out


def _split_tokens(value: str) -> list[str]:
    tokens: list[str] = []
    buf = ""
    depth = 0
    for ch in value:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        if ch.isspace() and depth <= 0:
            if buf:
                tokens.append(buf)
                buf = ""
        else:
            buf += ch
    if buf:
        tokens.append(buf)
    return tokens


def _resolve_shell(cmd: str, makefile_dir: Path) -> str | None:
    """Narrow allowlist of the `$(shell ...)` idioms actually used in this
    repo's Makefiles. Returns a resolved (space-joined) string, or None if
    the command isn't recognized."""
    cmd = cmd.strip()
    if cmd == "cd .. && pwd":
        return str((makefile_dir / "..").resolve())
    if cmd == "pwd":
        return str(makefile_dir)
    m = re.match(r"find\s+(\S+)\s+-i?name\s+'([^']+)'\s*$", cmd)
    if m:
        base_tok, pattern = m.groups()
        base = Path(base_tok)
        if not base.is_absolute():
            base = (makefile_dir / base_tok).resolve()
        if base.is_dir():
            hits = sorted(str(p) for p in base.rglob(pattern))
            return " ".join(hits)
    return None


_ABSPATH_RE = re.compile(r"\$\(abspath\s+([^()]*)\)")


def _apply_abspath(value: str, makefile_dir: Path) -> str:
    """Resolve GNU-Make's `$(abspath ...)` function once its argument no
    longer contains nested `$(...)` references (i.e. after variable
    substitution has already run on it).

    Make resolves a relative argument against the directory of the Makefile
    being read, NOT the invoking process's CWD -- `pnr/Makefile` has
    `PROJECT_ROOT := $(abspath ..)`, which is the repo root only when
    resolved from `pnr/`. Using `Path(arg).resolve()` here would make the
    result depend on where the checker happened to be run from, and every
    file under that variable would be reported missing.
    """

    def _one(m: re.Match[str]) -> str:
        arg = Path(m.group(1).strip())
        if not arg.is_absolute():
            arg = makefile_dir / arg
        return str(arg.resolve())

    prev = None
    while prev != value:
        prev = value
        value = _ABSPATH_RE.sub(_one, value)
    return value


def resolve_makefile_vars(makefile_path: Path) -> tuple[dict[str, str], list[str]]:
    """Returns (resolved variable strings, names of variables that hold at
    least one unresolved $(...) reference or unrecognized $(shell ...))."""
    text = makefile_path.read_text(errors="replace")
    makefile_dir = makefile_path.parent.resolve()
    resolved: dict[str, str] = {
        "PWD": str(makefile_dir),
        "CURDIR": str(makefile_dir),
    }
    unresolved_names: list[str] = []

    for is_recipe, raw_line in _logical_lines(text):
        if is_recipe:
            continue
        line = raw_line.split("#", 1)[0].strip()
        if not line or line.startswith(
            ("ifeq", "ifneq", "ifdef", "ifndef", "else", "endif", "include")
        ):
            continue
        m = ASSIGN_RE.match(line)
        if not m:
            continue
        name, op, raw_value = m.groups()
        raw_value = raw_value.strip()

        whole_shell = re.match(r"^\$\(shell\s+(.*)\)$", raw_value)
        if whole_shell:
            value = _resolve_shell(whole_shell.group(1), makefile_dir)
            if value is None:
                unresolved_names.append(name)
                value = raw_value  # keep literal so it's visible in output
        else:

            def _sub(mm: re.Match) -> str:
                ref = mm.group(1)
                return resolved.get(ref, mm.group(0))

            value = VAR_REF_RE.sub(_sub, raw_value)
            value = _apply_abspath(value, makefile_path.parent)

        if op == "+=":
            resolved[name] = (resolved.get(name, "") + " " + value).strip()
        elif op == "?=":
            resolved.setdefault(name, value)
        else:  # ':=' or '='
            resolved[name] = value

    return resolved, unresolved_names


def extract_makefile_lists(makefile_path: Path) -> dict[str, list[str]]:
    resolved, _ = resolve_makefile_vars(makefile_path)
    out: dict[str, list[str]] = {}
    for name, value in resolved.items():
        if not SOURCE_LIST_VAR_RE.match(name):
            continue
        tokens = _split_tokens(value)
        if not any(
            Path(t.split("$")[0]).suffix.lower() in DESIGN_FILE_EXTS
            for t in tokens
            if "$" not in t or t.rsplit(".", 1)[-1] in ("sv", "v")
        ):
            # Cheap pre-filter: skip vars that plainly hold no design files
            # (e.g. TEST_MODULES-style lists wouldn't match the name pattern
            # anyway; this guards oddities like empty/def-only vars).
            if not any(t.lower().endswith((".sv", ".v")) for t in tokens):
                continue
        out[name] = tokens
    return out


# ── discovery + reporting ────────────────────────────────────────────────────


# Targets that intentionally do not close and are not defects (bead
# claude_verilog_test-135, 2026-08-14 comment). Keyed by path relative to
# REPO_ROOT; extend with a comment explaining why each entry is safe to skip.
SKIP_TARGETS: dict[str, str] = {
    # Copy-me template, not a real flow config: its `dir::` entries are
    # written relative to a not-yet-created run directory and resolve to
    # non-existent pnr/rtl/... paths from here. Reported [GAP] on every scan
    # even though nothing is actually missing once the template is copied
    # and adapted for a real run.
    "pnr/asap7/template/config.json": (
        "copy-me template; relative dir:: paths resolve to non-existent "
        "pnr/rtl/... until copied into a real run directory"
    ),
}


def discover_targets() -> list[Path]:
    targets = sorted(REPO_ROOT.glob("pnr/*/config*.json"))
    targets += sorted(REPO_ROOT.glob("pnr/*/*/config*.json"))
    targets += sorted(REPO_ROOT.glob("tb/cocotb/*/Makefile"))
    for extra in ("sim/Makefile", "pnr/Makefile"):
        mk = REPO_ROOT / extra
        if mk.exists():
            targets.append(mk)
    targets = [t for t in targets if str(t.relative_to(REPO_ROOT)) not in SKIP_TARGETS]
    return targets


def reports_for_target(path: Path) -> list[ListReport]:
    if path.suffix == ".json":
        lists = extract_json_lists(path)
    elif path.name == "Makefile":
        lists = extract_makefile_lists(path)
    else:
        return []
    rel = path.relative_to(REPO_ROOT)
    base = path.parent
    reports = [
        evaluate_list(f"{rel}:{name}", tokens, base_dir=base) for name, tokens in lists.items()
    ]
    # Dedupe lists that resolve to an identical file set (e.g. CDC_SOURCES :=
    # $(sort $(SOC_TOP_SOURCES))) — keep the first label, note the alias.
    seen: dict[tuple[str, ...], ListReport] = {}
    deduped: list[ListReport] = []
    for r in reports:
        key = tuple(sorted(r.files))
        if key in seen:
            seen[key].label += f" (alias: {r.label.split(':', 1)[1]})"
            continue
        seen[key] = r
        deduped.append(r)
    return deduped


def print_human(all_reports: list[ListReport]) -> bool:
    all_ok = True
    for r in all_reports:
        status = "CLOSED" if r.closes else "GAP"
        if not r.closes:
            all_ok = False
        print(f"[{status}] {r.label}  ({len(r.files)} design files)")
        for f in r.missing_files:
            print(f"    missing file:      {f}")
        for t in r.unresolved_tokens:
            print(f"    unresolved token:  {t}")
        for p in sorted(r.missing_packages):
            print(f"    missing package:   {p}")
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Specific config.json / Makefile path(s) to check. Default: scan the whole repo.",
    )
    parser.add_argument(
        "--json", action="store_true", help="Emit machine-readable JSON instead of text."
    )
    args = parser.parse_args()

    targets = [Path(p).resolve() for p in args.paths] if args.paths else discover_targets()

    all_reports: list[ListReport] = []
    for t in targets:
        all_reports.extend(reports_for_target(t))

    if args.json:
        payload = [
            {
                "label": r.label,
                "closes": r.closes,
                "file_count": len(r.files),
                "missing_files": r.missing_files,
                "unresolved_tokens": r.unresolved_tokens,
                "missing_packages": sorted(r.missing_packages),
            }
            for r in all_reports
        ]
        print(json.dumps(payload, indent=2))
        all_ok = all(r.closes for r in all_reports)
    else:
        all_ok = print_human(all_reports)

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
