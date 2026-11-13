#!/usr/bin/env python3
"""Check that source text pinned by tests and scripts is still there.

Several scripts and tests match exact source text (including comment text or line numbers) and
most are not run by CI. This checker re-evaluates those anchors so that a comment edit, a line
shift or a removed marker is caught before it silently breaks a consumer.

Anchors are derived from the consumer files at run time where practical (mutation tables, sed
expressions, literals and regexes asserted by tests). The rest are hard-coded in CONSUMERS below.

Usage: python tools/docs/check_pinned_text.py [--root DIR] [-v] [--skip-waivers]

Exit codes:
  0  all anchors hold
  1  one or more anchors are broken (each one is printed)
  2  setup error: a consumer or target is missing or unreadable (never a silent pass)
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

# Hard-coded anchors: group -> (consumer path, what it pins). Derived anchors are not listed.
CONSUMERS = {
    "a": "tools/verif/mutate_*.py (mutant tables, derived)",
    "b": "pnr/commercial/signoff/lec/formality/Makefile + any Makefile/shell sed (derived)",
    "c": "tb/tests/test_cache_stall_encoding.py -> rtl/mem/rv32i_{i,d}cache.sv",
    "d": "tb/tests/test_cvt_scan_step.py -> pnr/sky130/soc/constraints/sky130_soc_cdc_check.sdc",
    "e": "tools/dft/make_scan_analysis_sdc.py -> pnr/sky130/soc/constraints/sky130_soc.sdc",
    "f": "tools/verif/check_upf.py -> pnr/constraints/phase5_soc.upf, rtl/soc/pmu.sv",
    "g": "tools/verif/soc_shards.py, tools/fpga/stage0_filelist.sh -> tb/cocotb/soc/Makefile",
    "h": "tb/tests/test_soc_shards.py -> .github/workflows/cocotb.yml, tb/cocotb/soc/test_*.py",
    "i": "tb/tests/test_pmu_registered_outputs.py -> rtl/soc/pmu.sv",
    "k": "tb/tests/test_{cvt_scan_step,soc_shards}.py literal asserts (derived)",
    "l": "tools/formal/run_eqy.py + modules.json -> rtl files",
    "m": "tools/verif/synth_gate/elab_gate.sh -> rtl/periph/timer.sv",
    "n": "tools/verif/struct_select/mkcone*.py -> rtl/gpu/gpu_compute_unit.sv",
    "o": "tb/tests/test_check_elab_strict.py -> last endmodule of three rtl files",
    "j": "tools/verif/coverage_report.py --check-waivers (subprocess)",
}
CACHE_FILES = ("rtl/mem/rv32i_icache.sv", "rtl/mem/rv32i_dcache.sv")
CDC_SDC = "pnr/sky130/soc/constraints/sky130_soc_cdc_check.sdc"
CDC_SEC_START = "# 2b. Functional-view case analysis"
CDC_SEC_END = "# Coverage guard + helper procs"
UPF = "pnr/constraints/phase5_soc.upf"
PMU = "rtl/soc/pmu.sv"
SOC_MAKEFILE = "tb/cocotb/soc/Makefile"
GPU_CU = "rtl/gpu/gpu_compute_unit.sv"
ELAB_STRICT_RTL = (
    "rtl/soc/soc_top.sv",
    "rtl/periph/gpio_controller.sv",
    "rtl/cpu/core/rv32i_regfile.sv",
)
KNOWN_ENGINE_TESTS = (
    "tb/tests/test_cvt_scan_step.py",
    "tb/tests/test_soc_shards.py",
)
WAIVER_CMD = [
    "tools/verif/coverage_report.py",
    "--check-waivers",
    "--waivers",
    "tools/verif/coverage_waivers.txt",
]


class SetupError(Exception):
    """A consumer or target is missing or its structure could not be read."""


@dataclass
class Ctx:
    root: Path
    verbose: bool = False
    failures: list[str] = field(default_factory=list)
    setup: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    _cache: dict[str, str] = field(default_factory=dict)

    def read(self, rel: str, who: str = "") -> str:
        if rel not in self._cache:
            p = self.root / rel
            if not p.is_file():
                raise SetupError(f"missing file {rel}" + (f" (needed by {who})" if who else ""))
            try:
                self._cache[rel] = p.read_text(encoding="utf-8", errors="replace")
            except OSError as e:
                raise SetupError(f"cannot read {rel}: {e}") from e
        return self._cache[rel]

    def ok(self, group: str, n: int = 1) -> None:
        self.counts[group] = self.counts.get(group, 0) + n

    def fail(self, group: str, pinned: str, consumer: str, expected: str, found: str) -> None:
        self.failures.append(
            f"[{group}] BROKEN: {pinned}\n    consumer: {consumer}\n"
            f"    expected: {expected}\n    found:    {found}"
        )


def list_files(root: Path) -> list[str]:
    """Tracked files (git) or a plain walk when root is not a git top level."""
    try:
        top = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            check=False,
        )
        if top.returncode == 0 and Path(top.stdout.strip()).resolve() == root.resolve():
            out = subprocess.run(
                ["git", "-C", str(root), "ls-files"],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                check=True,
            )
            return [f for f in out.stdout.split("\n") if f]
    except OSError:
        pass
    return sorted(
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if p.is_file() and ".git" not in p.relative_to(root).parts
    )


def line_of(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def in_line_comment(text: str, pos: int, marker: str = "//") -> bool:
    """True if a line comment opens earlier on the line that holds text[pos]."""
    start = text.rfind("\n", 0, pos) + 1
    return marker in text[start:pos]


def _load_module(path: Path, name: str):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise SetupError(f"cannot import {path}")
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:  # noqa: BLE001 - any import failure is a setup problem
        raise SetupError(f"importing {path.name} failed: {type(e).__name__}: {e}") from e
    return mod


def _parse(ctx: Ctx, rel: str, who: str = "") -> ast.Module:
    try:
        return ast.parse(ctx.read(rel, who))
    except SyntaxError as e:
        raise SetupError(f"cannot parse {rel}: {e}") from e


def _tuple_strings(tree: ast.AST, name: str) -> list[str]:
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in n.targets
        ):
            try:
                v = ast.literal_eval(n.value)
            except (ValueError, SyntaxError):
                break
            if isinstance(v, tuple | list) and v and all(isinstance(x, str) for x in v):
                return list(v)
    raise SetupError(f"no string tuple {name}")


def _str_const(tree: ast.AST, name: str) -> str | None:
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in n.targets
        ):
            try:
                v = ast.literal_eval(n.value)
            except (ValueError, SyntaxError):
                continue
            return v
    return None


# ---------------------------------------------------------------------------- a: mutation tables
def _apply_edits(ctx, group, script, mutant, label, text, edits):
    for old, _new in edits:
        n = text.count(old)
        if n != 1:
            ctx.fail(
                group,
                f"mutant {mutant}: `old` text ({old[:50]!r}) in {label}",
                script,
                "exactly 1 occurrence",
                f"{n} occurrence(s)",
            )
        else:
            ctx.ok(group)
        text = text.replace(old, _new)
    return text


def check_mutants(ctx: Ctx) -> None:
    vdir = ctx.root / "tools" / "verif"
    scripts = sorted(vdir.glob("mutate_*.py")) if vdir.is_dir() else []
    if not scripts:
        raise SetupError("no tools/verif/mutate_*.py found")
    for sp in scripts:
        rel = f"tools/verif/{sp.name}"
        mod = _load_module(sp, f"_pinned_{sp.stem}")
        before = ctx.counts.get("a", 0)
        mutants = getattr(mod, "MUTANTS", None)
        if not mutants:
            raise SetupError(f"{rel}: no MUTANTS table")

        def rtl_rel(p, mod=mod):
            p = Path(p)
            return p.relative_to(Path(mod.ROOT)).as_posix() if p.is_absolute() else p.as_posix()

        try:
            if sp.name == "mutate_cdc_gray_fifo.py":
                target = rtl_rel(mod.SRC)
                for name, _why, edits in mutants:
                    _apply_edits(ctx, "a", rel, name, target, ctx.read(target, rel), edits)
            elif sp.name == "mutate_crypto_scan_wipe.py":
                files = {k: ctx.read(v, rel) for k, v in mod.FILES.items()}
                for name, _why, edits in mutants:
                    texts = dict(files)
                    for key, old, new in edits:
                        texts[key] = _apply_edits(
                            ctx, "a", rel, name, mod.FILES[key], texts[key], [(old, new)]
                        )
            elif sp.name == "mutate_pmu_iso_ack.py":
                for name, _suite, fkey, _why, edits, _reason in mutants:
                    _apply_edits(ctx, "a", rel, name, fkey, ctx.read(fkey, rel), edits)
            else:
                raise SetupError(f"{rel}: new mutation script has no adapter in check_pinned_text")
        except (AttributeError, ValueError, TypeError) as e:
            raise SetupError(f"{rel}: unexpected table shape ({type(e).__name__}: {e})") from e
        ctx.notes.append(
            f"a: {sp.name}: {ctx.counts.get('a', 0) - before} mutant edits checked "
            f"({len(mutants)} mutants)"
        )


# ---------------------------------------------------------------------------- b: sed anchors
def bre_to_py(pat: str) -> str:
    """Convert a POSIX basic regular expression (GNU flavour) to Python re syntax."""
    out: list[str] = []
    i = 0
    while i < len(pat):
        c = pat[i]
        if c == "\\":
            if i + 1 >= len(pat):
                raise SetupError(f"sed pattern ends with a backslash: {pat!r}")
            n = pat[i + 1]
            i += 2
            if n in "(){}|+?":
                out.append(n)
            elif n in "wWsSb":
                out.append("\\" + n)
            elif n.isdigit():
                out.append("\\" + n)
            elif n.isalpha() or n in "<>'`":
                raise SetupError(f"unsupported sed escape \\{n} in {pat!r}")
            else:
                out.append(re.escape(n))
        elif c == "[":
            j = i + 1
            if j < len(pat) and pat[j] == "^":
                j += 1
            if j < len(pat) and pat[j] == "]":
                j += 1
            while j < len(pat) and pat[j] != "]":
                if pat[j] == "[" and j + 1 < len(pat) and pat[j + 1] in ":.=":
                    raise SetupError(f"unsupported POSIX class in {pat!r}")
                j += 1
            if j >= len(pat):
                raise SetupError(f"unterminated bracket expression in {pat!r}")
            body = pat[i + 1 : j].replace("\\", "\\\\")
            if body.startswith("^]") or body.startswith("]"):
                body = body.replace("]", "\\]", 1)
            out.append("[" + body + "]")
            i = j + 1
        elif c in "(){}|+?":
            out.append("\\" + c)
            i += 1
        elif c == "*" and not out:
            out.append("\\*")
            i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


_SED_S = re.compile(
    r"""\bsed\s+(?:-[A-Za-z-]+\s+)*(['"])(?:(?P<addr>\d+))?s/(?P<pat>(?:[^/\\]|\\.)*)/"""
    r"""(?:[^/\\]|\\.)*/[a-z]*\1\s+(?P<file>"[^"]+"|'[^']+'|[^\s>|;&]+)"""
)
_SED_HELP = re.compile(
    r"""\bsed\s+-n\s+'(\d+),(\d+)p'\s+("\$0"|\$\(lastword \$\(MAKEFILE_LIST\)\)|\$0)"""
)
_VARPREFIX = re.compile(
    r"^\$(?:\((?:REPO|ROOT|REPO_ROOT|PROJ_ROOT)\)|\{(?:REPO|ROOT)\}|REPO|ROOT)/"
)


def _is_script(name: str) -> bool:
    return (
        name == "Makefile" or name.startswith("Makefile.") or name.endswith((".mk", ".sh", ".bash"))
    )


def check_seds(ctx: Ctx) -> None:
    fm = "pnr/commercial/signoff/lec/formality/Makefile"
    ctx.read(fm)  # the audited consumer must exist
    found_in_fm = 0
    for rel in list_files(ctx.root):
        if rel.startswith("micro_p/") or not _is_script(rel.rsplit("/", 1)[-1]):
            continue
        p = ctx.root / rel
        if not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.split("\n")
        if "sed" not in text:
            continue
        for ln, raw in enumerate(lines, 1):
            if raw.lstrip().startswith("#"):
                continue
            line = raw.replace("$$", "$")
            hm = _SED_HELP.search(line)
            if hm:
                a, b = int(hm.group(1)), int(hm.group(2))
                # Lines past the first non-comment line may be printed by accident (off by one
                # in the consumer); the pinned part is the leading run of comment lines.
                bad = [a] if a > len(lines) or not lines[a - 1].lstrip().startswith("#") else []
                if bad:
                    ctx.fail(
                        "b",
                        f"self-help sed -n '{a},{b}p' prints lines {a}-{b} as usage",
                        f"{rel}:{ln}",
                        "the first printed line is a # comment",
                        f"non-comment line(s) {bad[:5]}",
                    )
                else:
                    ctx.ok("b")
                continue
            m = _SED_S.search(line)
            if not m:
                continue
            fpath = m.group("file").strip("\"'")
            pm = _VARPREFIX.match(fpath)
            target = fpath[pm.end() :] if pm else fpath
            addr = m.group("addr")
            tfile = ctx.root / target
            if not tfile.is_file():
                if addr:
                    raise SetupError(f"{rel}:{ln}: line-addressed sed target {fpath!r} unresolved")
                ctx.notes.append(
                    f"b: {rel}:{ln}: unaddressed sed target {fpath!r} not resolvable, skipped"
                )
                continue
            py = re.compile(bre_to_py(m.group("pat")))
            ttext = tfile.read_text(encoding="utf-8", errors="replace")
            if rel == fm:
                found_in_fm += 1
            if addr:
                n = int(addr)
                tl = ttext.split("\n")
                if n > len(tl):
                    ctx.fail(
                        "b",
                        f"sed line {n} of {target}",
                        f"{rel}:{ln}",
                        f"file has >= {n} lines",
                        f"{len(tl)} lines",
                    )
                elif py.search(tl[n - 1]):
                    ctx.ok("b")
                else:
                    ctx.fail(
                        "b",
                        f"sed {n}s/{m.group('pat')}/ on {target}",
                        f"{rel}:{ln}",
                        f"line {n} matches the pattern",
                        f"line {n} is {tl[n - 1].strip()[:80]!r}",
                    )
            else:
                hits = [mm for mm in py.finditer(ttext) if not in_line_comment(ttext, mm.start())]
                if hits:
                    ctx.ok("b")
                else:
                    ctx.fail(
                        "b",
                        f"sed s/{m.group('pat')}/ on {target}",
                        f"{rel}:{ln}",
                        "pattern matches at least once outside a comment",
                        "no code match",
                    )
    if found_in_fm == 0:
        raise SetupError(f"{fm}: no line-addressed sed expressions could be parsed")


# ---------------------------------------------------------------------------- c: cache stall
def check_cache_stall(ctx: Ctx) -> None:
    test = "tb/tests/test_cache_stall_encoding.py"
    tree = _parse(ctx, test)
    markers = [
        n.value
        for n in ast.walk(tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and "SRAM combinational control" in n.value
    ]
    if not markers:
        raise SetupError(f"{test}: no 'SRAM combinational control' markers found")
    ic = ctx.read(CACHE_FILES[0], test)
    dc = ctx.read(CACHE_FILES[1], test)
    for mk in markers:
        n = ic.count(mk)
        if n != 1:
            ctx.fail(
                "c",
                f"marker {mk!r}",
                f"{test} (splits {CACHE_FILES[0]})",
                "exactly 1 occurrence",
                f"{n}",
            )
            continue
        body = ic.split(mk, 1)[1]
        e = body.find("endcase")
        if e < 0:
            ctx.fail("c", f"'endcase' after marker {mk!r}", test, "present", "absent")
            continue
        seg_end = ic.index(mk) + len(mk) + e
        if in_line_comment(ic, seg_end):
            ctx.fail(
                "c",
                f"first 'endcase' after {mk!r}",
                test,
                "a code token, not comment text",
                "inside a // comment",
            )
        seg = body[:e]
        i = seg.find("CS_IDLE:")
        if i < 0:
            ctx.fail(
                "c", f"'CS_IDLE:' between marker {mk!r} and endcase", test, "present", "absent"
            )
            continue
        if in_line_comment(seg, i):
            ctx.fail("c", f"first 'CS_IDLE:' after {mk!r}", test, "code", "inside a // comment")
        if "ic_valid_i" in seg[i:]:
            ctx.fail(
                "c",
                f"ic_valid_i inside CS_IDLE arm after {mk!r} (comment text counts)",
                test,
                "absent",
                "present",
            )
        else:
            ctx.ok("c")
    stall_names = _tuple_strings(tree, "UNCONDITIONAL_STALL")
    for sig, text, rel in (("dc_stall_o", dc, CACHE_FILES[1]), ("ic_stall_o", ic, CACHE_FILES[0])):
        m = re.search(rf"assign {sig} =(.*?);", text, re.S)
        if not m:
            ctx.fail("c", f"assign {sig} = ...;", f"{test} ({rel})", "present", "absent")
            continue
        body = m.group(1)
        named = [n for n in stall_names if n in body]
        if named:
            ctx.fail(
                "c",
                f"state names in `assign {sig} =...;` (comment text counts)",
                test,
                "none of the unconditional-stall CS_ names",
                f"found {named}",
            )
        elif "state_q[3]" not in body:
            ctx.fail("c", f"state_q[3] in assign {sig}", test, "present", "absent")
        else:
            ctx.ok("c")


# ---------------------------------------------------------------------------- d: cvt scan step
def check_cvt_sdc(ctx: Ctx) -> None:
    test = "tb/tests/test_cvt_scan_step.py"
    ctx.read(test)
    sdc = ctx.read(CDC_SDC, test)
    i = sdc.find(CDC_SEC_START)
    j = sdc.find(CDC_SEC_END, i) if i >= 0 else -1
    if i < 0 or j < 0:
        ctx.fail(
            "d",
            f"section markers {CDC_SEC_START!r} .. {CDC_SEC_END!r}",
            test,
            "both present, in order",
            f"start={'ok' if i >= 0 else 'missing'}, end={'ok' if j >= 0 else 'missing'}",
        )
        return
    sec = sdc[i:j]
    checks = [
        (
            "scan-view guard",
            re.search(
                r"if \{\[info exists ::env\(CVT_SDC_SCAN_VIEW\)\] && "
                r'\$::env\(CVT_SDC_SCAN_VIEW\) eq "1"\}',
                sec,
            )
            is not None,
        ),
        ("foreach _p {scan_mode_i scan_en_i}", "foreach _p {scan_mode_i scan_en_i}" in sec),
        (
            "cdc_net_driver_pins {u_dft_ctrl.tap_serial}",
            "cdc_net_driver_pins {u_dft_ctrl.tap_serial}" in sec,
        ),
        ("exactly 2 'set_case_analysis 0' (comments count)", sec.count("set_case_analysis 0") == 2),
        ("'proc cdc_net_driver_pins' inside the section", "proc cdc_net_driver_pins" in sec),
    ]
    for what, good in checks:
        if good:
            ctx.ok("d")
        else:
            ctx.fail("d", f"{what} in section of {CDC_SDC}", test, "holds", "does not hold")
    if "proc cdc_net_driver_pins" in sec:
        tail = sec.replace("SE pin", "").replace("SE tree", "").split("proc cdc_net_driver_pins")[1]
        if "SCE" in tail:
            ctx.fail(
                "d", f"'SCE' after proc cdc_net_driver_pins in {CDC_SDC}", test, "absent", "present"
            )
        else:
            ctx.ok("d")
    tcl = _scan_tcl_path(ctx, test)
    if tcl:
        t = ctx.read(tcl, test)
        keys = ["[$block findNet $gate_net_nm]", "scan_out gate net '$gate_net_nm' not found"]
        pos = [t.find(k) for k in keys]
        if min(pos) < 0:
            ctx.fail("d", f"error-path markers in {tcl}", test, "present", f"positions {pos}")
        else:
            ex = t.find("exit 2", pos[1])
            ed = t.find("odb::dbBTerm_destroy $sin")
            if -1 < pos[0] < pos[1] < ex < ed:
                ctx.ok("d")
            else:
                ctx.fail(
                    "d",
                    f"order find < error < exit 2 < port edit in {tcl}",
                    test,
                    "strictly increasing",
                    f"{pos[0]},{pos[1]},{ex},{ed}",
                )


def _scan_tcl_path(ctx: Ctx, test: str) -> str | None:
    return (
        "pnr/sky130/soc/plugin/librelane_plugin_cvt_sky130/tcl/scan_insert.tcl"
        if (
            ctx.root / "pnr/sky130/soc/plugin/librelane_plugin_cvt_sky130/tcl/scan_insert.tcl"
        ).is_file()
        else None
    )


# ---------------------------------------------------------------------------- e: scan analysis sdc
def check_scan_analysis(ctx: Ctx) -> None:
    rel = "tools/dft/make_scan_analysis_sdc.py"
    tree = _parse(ctx, rel)
    fp = _str_const(tree, "FALSE_PATH")
    sdc = next(
        (
            n.value
            for n in ast.walk(tree)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and n.value.endswith("sky130_soc.sdc")
        ),
        None,
    )
    if not fp or not sdc:
        raise SetupError(f"{rel}: FALSE_PATH or default SDC path not found")
    text = ctx.read(sdc, rel)
    n = text.count(fp)
    if n == 1:
        ctx.ok("e")
    else:
        ctx.fail(
            "e",
            f"scan_out_o false-path line ({fp[:60]}...)",
            f"{rel}:FALSE_PATH",
            f"exactly 1 occurrence in {sdc}",
            f"{n}",
        )


# ---------------------------------------------------------------------------- f: check_upf
def check_upf(ctx: Ctx) -> None:
    rel = "tools/verif/check_upf.py"
    tree = _parse(ctx, rel)
    pats = {}
    for n in ast.walk(tree):
        if (
            isinstance(n, ast.Assign)
            and isinstance(n.value, ast.Call)
            and getattr(n.value.func, "attr", "") == "compile"
            and n.value.args
            and isinstance(n.value.args[0], ast.Constant)
        ):
            for t in n.targets:
                if isinstance(t, ast.Name):
                    pats[t.id] = n.value.args[0].value
    if "_DIRECTIVE" not in pats:
        raise SetupError(f"{rel}: _DIRECTIVE regex not found")
    directive = re.compile(pats["_DIRECTIVE"])
    upf = ctx.read(UPF, rel)
    mention = [
        ln for ln, raw in enumerate(upf.split("\n"), 1) if re.match(r"^\s*#\s*upf-check\b", raw)
    ]
    good = [ln for ln in mention if directive.match(upf.split("\n")[ln - 1])]
    if not good:
        ctx.fail(
            "f", "`# upf-check` directive lines", f"{rel} _DIRECTIVE", ">= 1 parsing line", "0"
        )
    else:
        ctx.ok("f")
    for ln in sorted(set(mention) - set(good)):
        ctx.fail(
            "f",
            f"{UPF}:{ln} directive line",
            f"{rel} _DIRECTIVE",
            "matches the directive regex",
            upf.split("\n")[ln - 1].strip()[:80],
        )
    pmu = ctx.read(PMU, rel)
    n_ok = 0
    for m in re.finditer(r"MODE_(\w+):\s*begin(.*?)\bend\b", pmu, re.S):
        if in_line_comment(pmu, m.end() - 3) or "/*" in pmu[m.start(2) : m.end()]:
            ctx.fail(
                "f",
                f"MODE_{m.group(1)} body in {PMU}:{line_of(pmu, m.start())}",
                f"{rel} parse_pmu",
                "body ends at a real `end` token",
                "the first `end` word is inside comment text",
            )
        else:
            n_ok += 1
    if n_ok == 0:
        ctx.fail("f", f"MODE_x: begin ... end bodies in {PMU}", f"{rel} parse_pmu", ">= 1", "0")
    ctx.ok("f", n_ok)


# ---------------------------------------------------------------------------- g: makefile blocks
def _block(text: str, start_re: str, stop: Callable[[str], bool] | None):
    lines = text.split("\n")
    for i, ln in enumerate(lines):
        if re.match(start_re, ln):
            j = i
            while True:
                if stop is not None and stop(lines[j]):
                    break
                if stop is None and not lines[j].endswith("\\"):
                    break
                j += 1
                if j >= len(lines):
                    break
            return i + 1, lines[i : j + 1]
    return None, []


def check_makefile_blocks(ctx: Ctx) -> None:
    mk = ctx.read(SOC_MAKEFILE)
    for who, var in (
        ("tools/verif/soc_shards.py", "SOC_CI_SUITES"),
        ("tools/verif/soc_shards.py", "SOC_CI_SPLITS"),
    ):
        src = ctx.read(who)
        if var not in src:
            raise SetupError(f"{who}: no longer mentions {var}; update check_pinned_text")
        start, blk = _block(mk, rf"{var}\s*:?=", None)
        if start is None:
            if var == "SOC_CI_SUITES":
                raise SetupError(f"{SOC_MAKEFILE}: {var} is not defined")
            continue
        bad = [start + k for k, ln in enumerate(blk) if "#" in ln]
        if bad:
            ctx.fail(
                "g",
                f"{var} block must be comment-free",
                f"{who}",
                "no '#' in lines",
                f"'#' at {SOC_MAKEFILE}:{bad[:5]}",
            )
        else:
            ctx.ok("g")
    sh = "tools/fpga/stage0_filelist.sh"
    if "PLL_SOURCES" not in ctx.read(sh):
        raise SetupError(f"{sh}: no longer mentions PLL_SOURCES; update check_pinned_text")
    start, blk = _block(mk, r"PLL_SOURCES = ", lambda s: "tb_soc_pll.sv" in s)
    if start is None:
        raise SetupError(f"{SOC_MAKEFILE}: PLL_SOURCES block not found")
    bad = [start + k for k, ln in enumerate(blk) if "#" in ln]
    if bad or "tb_soc_pll.sv" not in blk[-1]:
        ctx.fail(
            "g",
            "PLL_SOURCES block (sed range PLL_SOURCES .. tb_soc_pll.sv)",
            sh,
            "terminates at tb_soc_pll.sv with no '#'",
            f"'#' at lines {bad[:5]}" if bad else "no end line",
        )
    else:
        ctx.ok("g")


# ---------------------------------------------------------------------------- h: soc shards
def check_shards(ctx: Ctx) -> None:
    test = "tb/tests/test_soc_shards.py"
    ctx.read(test)
    yml = ctx.read(".github/workflows/cocotb.yml", test)
    m = re.search(r"\n(\s+)matrix:\n(.*?\n)", yml)
    if not m:
        ctx.fail("h", "matrix: block in cocotb.yml", test, "present", "absent")
    else:
        nxt = m.group(2).strip()
        if nxt.startswith("shard:"):
            ctx.ok("h")
        else:
            ctx.fail(
                "h",
                "`shard:` directly after `matrix:`",
                f"{test} (regex matrix:\\n\\s+shard:)",
                "no comment or key between",
                f"next line is {nxt[:60]!r}",
            )
    mod = "tb/cocotb/soc/test_uart_boot.py"
    src = ctx.read(mod, test)
    n_dec = len(re.findall(r"@cocotb\.test\(", src))
    n_re = len(re.findall(r"@cocotb\.test\([^)]*\)\s*\nasync def (\w+)", src))
    if n_dec == 0 or n_dec != n_re:
        ctx.fail(
            "h",
            f"every @cocotb.test decorator in {mod} directly followed by async def",
            test,
            f"{n_dec} matched",
            f"{n_re} matched",
        )
    else:
        ctx.ok("h", n_dec)


# ---------------------------------------------------------------------------- i: pmu ports
def check_pmu_ports(ctx: Ctx) -> None:
    test = "tb/tests/test_pmu_registered_outputs.py"
    tree = _parse(ctx, test)
    try:
        signals = ast.literal_eval(
            ast.parse("x=" + ast.unparse(_node(tree, "SIGNALS"))).body[0].value
        )
        domains = ast.literal_eval(
            ast.parse("x=" + ast.unparse(_node(tree, "DOMAINS"))).body[0].value
        )
        dom_index = ast.literal_eval(
            ast.parse("x=" + ast.unparse(_node(tree, "DOM_INDEX"))).body[0].value
        )
    except (ValueError, SyntaxError, AttributeError) as e:
        raise SetupError(f"{test}: SIGNALS/DOMAINS/DOM_INDEX not literals ({e})") from e
    pmu = ctx.read(PMU, test)
    for d in domains:
        for s in signals:
            port = f"{d}_{s}_o"
            pat = re.compile(rf"(assign\s+{port}\s*=\s*){s}_q(\[{dom_index[d]}\];)")
            n = len(pat.findall(pmu))
            if n == 1:
                ctx.ok("i")
            else:
                ctx.fail(
                    "i",
                    f"`assign {port} = {s}_q[{dom_index[d]}];`",
                    test,
                    "exactly 1 match",
                    f"{n}",
                )


def _node(tree: ast.AST, name: str) -> ast.AST:
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == name for t in n.targets
        ):
            return n.value
    raise SetupError(f"no assignment to {name}")


# ------------------------------------------------------------------- k: test-literal engine
_FLAGS = {
    "M": re.M,
    "MULTILINE": re.M,
    "S": re.S,
    "DOTALL": re.S,
    "I": re.I,
    "IGNORECASE": re.I,
    "X": re.X,
    "VERBOSE": re.X,
}


def _flags(node: ast.AST | None) -> int | None:
    if node is None:
        return 0
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "re"
    ):
        return _FLAGS.get(node.attr)
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr):
        a, b = _flags(node.left), _flags(node.right)
        return None if a is None or b is None else a | b
    return None


def _path(node: ast.AST, env: dict[str, str]) -> str | None:
    if isinstance(node, ast.Name):
        return env.get(node.id)
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        a, b = _path(node.left, env), _path(node.right, env)
        if a is None or b is None:
            return None
        return f"{a}/{b}" if a else b
    return None


def _own_nodes(scope: ast.AST):
    """Nodes of a scope excluding nested function bodies, in source order."""
    out = []
    stack = list(reversed(getattr(scope, "body", [])))
    while stack:
        n = stack.pop()
        out.append(n)
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        stack.extend(reversed(list(ast.iter_child_nodes(n))))
    return out


def _text_source(value: ast.AST, env: dict[str, str]) -> str | None:
    if (
        isinstance(value, ast.Call)
        and isinstance(value.func, ast.Attribute)
        and value.func.attr == "read_text"
    ):
        return _path(value.func.value, env)
    return None


def derive_literal_checks(tree: ast.Module):
    """Yield (kind, rel, arg, expect, lineno) checks from a test module's asserts."""
    checks = []
    menv: dict[str, str] = {}
    mtext: dict[str, str] = {}

    def scan(scope, env, tvars, parent_matches):
        matches = dict(parent_matches)
        for n in _own_nodes(scope):
            if (
                isinstance(n, ast.Assign)
                and len(n.targets) == 1
                and isinstance(n.targets[0], ast.Name)
            ):
                name, val = n.targets[0].id, n.value
                if "__file__" in ast.dump(val) and "parents" in ast.dump(val):
                    env[name] = ""
                    continue
                src = _text_source(val, env)
                if src is not None:
                    tvars[name] = src
                    continue
                p = _path(val, env) if isinstance(val, ast.BinOp) else None
                if p is not None:
                    env[name] = p
                if (
                    isinstance(val, ast.Call)
                    and _is_re(val, "search")
                    and len(val.args) >= 2
                    and isinstance(val.args[1], ast.Name)
                    and val.args[1].id in tvars
                ):
                    matches[name] = val
            if (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Attribute)
                and n.func.attr == "index"
            ):
                v = n.func.value
                if (
                    isinstance(v, ast.Name)
                    and v.id in tvars
                    and n.args
                    and isinstance(n.args[0], ast.Constant)
                    and isinstance(n.args[0].value, str)
                ):
                    checks.append(("in", tvars[v.id], n.args[0].value, True, n.lineno))
            if isinstance(n, ast.Assert):
                for c in _conj(n.test):
                    neg = False
                    if isinstance(c, ast.UnaryOp) and isinstance(c.op, ast.Not):
                        neg, c = True, c.operand
                    _classify(c, neg, tvars, matches, checks, n.lineno)

    scan(tree, menv, mtext, {})
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
            scan(fn, dict(menv), dict(mtext), {})
    seen, uniq = set(), []
    for c in checks:
        if c not in seen:
            seen.add(c)
            uniq.append(c)
    return uniq


def _is_re(call: ast.Call, fn: str) -> bool:
    f = call.func
    return (
        isinstance(f, ast.Attribute)
        and f.attr == fn
        and isinstance(f.value, ast.Name)
        and f.value.id == "re"
    )


def _conj(test: ast.AST):
    if isinstance(test, ast.BoolOp) and isinstance(test.op, ast.And):
        for v in test.values:
            yield from _conj(v)
    else:
        yield test


def _classify(c, neg, tvars, matches, checks, lineno):
    if isinstance(c, ast.Compare) and len(c.ops) == 1:
        op, left, right = c.ops[0], c.left, c.comparators[0]
        if (
            isinstance(op, ast.In | ast.NotIn)
            and isinstance(left, ast.Constant)
            and isinstance(left.value, str)
            and isinstance(right, ast.Name)
            and right.id in tvars
        ):
            checks.append(
                ("in", tvars[right.id], left.value, isinstance(op, ast.In) != neg, lineno)
            )
        elif (
            isinstance(op, ast.Eq)
            and isinstance(left, ast.Call)
            and isinstance(left.func, ast.Attribute)
            and left.func.attr == "count"
            and isinstance(left.func.value, ast.Name)
            and left.func.value.id in tvars
            and left.args
            and isinstance(left.args[0], ast.Constant)
            and isinstance(right, ast.Constant)
            and isinstance(right.value, int)
            and not neg
        ):
            checks.append(
                (
                    "count",
                    tvars[left.func.value.id],
                    (left.args[0].value, right.value),
                    True,
                    lineno,
                )
            )
    elif isinstance(c, ast.Call) and _is_re(c, "search") and len(c.args) >= 2:
        pat, txt = c.args[0], c.args[1]
        fl = _flags(c.args[2] if len(c.args) > 2 else None)
        if (
            isinstance(pat, ast.Constant)
            and isinstance(pat.value, str)
            and isinstance(txt, ast.Name)
            and txt.id in tvars
            and fl is not None
        ):
            checks.append(("re", tvars[txt.id], (pat.value, fl), not neg, lineno))
    elif isinstance(c, ast.Name) and c.id in matches:
        call = matches[c.id]
        pat, txt = call.args[0], call.args[1]
        fl = _flags(call.args[2] if len(call.args) > 2 else None)
        if isinstance(pat, ast.Constant) and isinstance(pat.value, str) and fl is not None:
            checks.append(("re", tvars[txt.id], (pat.value, fl), not neg, lineno))


def check_test_literals(ctx: Ctx) -> None:
    for test in KNOWN_ENGINE_TESTS:
        tree = _parse(ctx, test)
        checks = derive_literal_checks(tree)
        if not checks:
            raise SetupError(f"{test}: no literal assertions could be derived")
        for kind, rel, arg, expect, ln in checks:
            text = ctx.read(rel, f"{test}:{ln}")
            who = f"{test}:{ln}"
            if kind == "in":
                has = arg in text
                what, got = f"literal {arg[:70]!r} in {rel}", has
            elif kind == "count":
                has = text.count(arg[0]) == arg[1]
                what, got = f"count({arg[0][:50]!r}) == {arg[1]} in {rel}", has
            else:
                has = re.search(arg[0], text, arg[1]) is not None
                what, got = f"regex {arg[0][:70]!r} in {rel}", has
            if got == expect:
                ctx.ok("k")
            else:
                ctx.fail(
                    "k",
                    what,
                    who,
                    "holds" if expect else "does not match",
                    "fails" if expect else "matches",
                )
        ctx.notes.append(f"k: {test}: {len(checks)} derived assertions")


# ---------------------------------------------------------------------------- l: formal modules
def check_formal_modules(ctx: Ctx) -> None:
    rel = "tools/formal/modules.json"
    try:
        data = json.loads(ctx.read(rel))
    except json.JSONDecodeError as e:
        raise SetupError(f"{rel}: invalid JSON: {e}") from e
    for mod in data.get("modules", []):
        name = mod.get("name", "?")
        specs = list(mod.get("gold_rewrites", []))
        if isinstance(mod.get("negative_control"), dict):
            specs.append(mod["negative_control"])
        for sp in specs:
            f, find = sp.get("file"), sp.get("find")
            if not f or find is None:
                raise SetupError(f"{rel}: {name}: rewrite/negative_control without file/find")
            n = ctx.read(f, rel).count(find)
            if n == 1:
                ctx.ok("l")
            else:
                ctx.fail(
                    "l",
                    f"{name}: find {find[:50]!r} in {f}",
                    f"{rel} (run_eqy apply_text_rewrite)",
                    "exactly 1 occurrence",
                    f"{n}",
                )
        po = mod.get("param_override")
        if po:
            g = po.get("file")
            text = ctx.read(g, rel)
            for pname in po.get("params", {}):
                m = re.search(
                    rf"(parameter\s+int\s+unsigned\s+{re.escape(pname)}\s*=\s*)(\d+)", text
                )
                if m and not in_line_comment(text, m.start()):
                    ctx.ok("l")
                else:
                    ctx.fail(
                        "l",
                        f"{name}: parameter int unsigned {pname} in {g}",
                        f"{rel} param_override",
                        "first match is code",
                        "no match" if not m else "first match is in a comment",
                    )


# ---------------------------------------------------------------------------- m: elab_gate needle
def check_elab_gate(ctx: Ctx) -> None:
    sh = "tools/verif/synth_gate/elab_gate.sh"
    text = ctx.read(sh).replace("\\\n", " ")
    m = re.search(r'inject_snippet\.py"\s+"\$REPO/([^"]+)"\s+"[^"]+"\s+"[^"]+"\s+"([^"]+)"', text)
    if not m:
        raise SetupError(f"{sh}: inject_snippet.py call not parsable")
    rtl, needle = m.groups()
    hits = [ln for ln in ctx.read(rtl, sh).split("\n") if ln.strip() == needle]
    if len(hits) == 1:
        ctx.ok("m")
    else:
        ctx.fail(
            "m",
            f"line equal to {needle!r} in {rtl}",
            f"{sh} (inject_snippet.py)",
            "exactly 1 line",
            f"{len(hits)}",
        )


# ---------------------------------------------------------------------------- n: struct_select
def check_struct_select(ctx: Ctx) -> None:
    cu = ctx.read(GPU_CU, "tools/verif/struct_select/mkcone*.py")
    for pat, flg, what in (
        (
            r"typedef struct packed \{[^{}]*\} id_ex_t;",
            0,
            "id_ex_t typedef without braces in comments",
        ),
        (
            r"always_comb begin\n\s*logic \[31:0\] shmem_byte_addr;.*?\n    end\n",
            re.S,
            "shmem_byte_addr always_comb block",
        ),
    ):
        if re.search(pat, cu, flg):
            ctx.ok("n")
        else:
            ctx.fail(
                "n",
                what,
                "tools/verif/struct_select/mkcone.py, mkcone_oldnew.py",
                "regex matches",
                "no match",
            )


# ---------------------------------------------------------------------------- o: elab strict
def check_elab_strict_tail(ctx: Ctx) -> None:
    test = "tb/tests/test_check_elab_strict.py"
    ctx.read(test)
    for rel in ELAB_STRICT_RTL:
        t = ctx.read(rel, test)
        k = t.rfind("endmodule")
        if k < 0 or in_line_comment(t, k):
            ctx.fail(
                "o",
                f"last 'endmodule' in {rel}",
                test,
                "a code token (the test inserts before it)",
                "missing or inside a // comment",
            )
        else:
            ctx.ok("o")


# ---------------------------------------------------------------------------- j: waivers
def check_waivers(ctx: Ctx) -> None:
    script = ctx.root / WAIVER_CMD[0]
    if not script.is_file():
        raise SetupError(f"missing {WAIVER_CMD[0]}")
    r = subprocess.run(
        [sys.executable, str(script), *WAIVER_CMD[1:]],
        cwd=ctx.root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode == 0:
        ctx.ok("j")
    else:
        tail = (r.stdout + r.stderr).strip().splitlines()[-3:]
        ctx.fail(
            "j",
            "coverage waiver anchors",
            "tools/verif/coverage_report.py --check-waivers",
            "exit 0",
            f"exit {r.returncode}: {' | '.join(tail)[:300]}",
        )


GROUPS: list[tuple[str, Callable[[Ctx], None]]] = [
    ("a", check_mutants),
    ("b", check_seds),
    ("c", check_cache_stall),
    ("d", check_cvt_sdc),
    ("e", check_scan_analysis),
    ("f", check_upf),
    ("g", check_makefile_blocks),
    ("h", check_shards),
    ("i", check_pmu_ports),
    ("k", check_test_literals),
    ("l", check_formal_modules),
    ("m", check_elab_gate),
    ("n", check_struct_select),
    ("o", check_elab_strict_tail),
    ("j", check_waivers),
]


def run_all(root: Path, verbose: bool = False, skip_waivers: bool = False) -> Ctx:
    ctx = Ctx(root=root, verbose=verbose)
    for g, fn in GROUPS:
        if g == "j" and skip_waivers:
            continue
        try:
            fn(ctx)
        except SetupError as e:
            ctx.setup.append(f"[{g}] SETUP ERROR: {e}")
    return ctx


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check text pinned by tests and scripts.")
    ap.add_argument("--root", default=str(Path(__file__).resolve().parents[2]))
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument(
        "--skip-waivers", action="store_true", help="skip coverage_report --check-waivers"
    )
    args = ap.parse_args(argv)
    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"setup error: --root {root} is not a directory")
        return 2
    ctx = run_all(root, args.verbose, args.skip_waivers)
    for msg in ctx.setup + ctx.failures:
        print(msg)
    if args.verbose:
        for g, _ in GROUPS:
            print(f"group {g}: {ctx.counts.get(g, 0)} anchors  ({CONSUMERS.get(g, '')})")
        for n in ctx.notes:
            print(f"  note: {n}")
    total = sum(ctx.counts.values())
    if ctx.setup:
        print(
            f"SETUP ERROR: {len(ctx.setup)} group(s) could not be evaluated; {total} anchors held"
        )
        return 2
    if ctx.failures:
        print(f"FAIL: {len(ctx.failures)} broken anchor(s), {total} held")
        return 1
    print(f"OK: {total} pinned-text anchors hold")
    return 0


if __name__ == "__main__":
    sys.exit(main())
