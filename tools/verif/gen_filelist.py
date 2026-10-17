#!/usr/bin/env python3
"""Generate the committed, tool-agnostic RTL filelists under ``rtl/filelist/`` (bead 1as3).

Why this exists
---------------
RTL file lists are duplicated per flow (``tb/cocotb/soc/Makefile``, ``sim/Makefile``,
``pnr/Makefile``). An external tool (a simulator, linter, formatter, an sv2v wrapper)
needs ONE plain ``.f`` file. Hand-writing it would just add a fourth copy that drifts, so
the ``.f`` files are *generated* from the existing authoritative Make variables and a CI
step (``--check``) fails on any difference.

Authoritative sources (parsed with the one Make parser in this repo,
``check_source_closure.extract_makefile_lists``)::

    soc_top  <- tb/cocotb/soc/Makefile :: PLL_SOURCES  (the list the cocotb regression elaborates)
                + rtl/mem/rv32i_clock_gate.sv          (see EXTRA_RTL below)
    cpu_top  <- pnr/Makefile            :: CPU_SV_FILES (rv32i_cpu_top, the ASAP7 CPU macro cone)
    gpu_top  <- pnr/Makefile            :: GPU_SV_FILES (gpu_top, the ASAP7 GPU macro cone)

What the generator does to a source list
----------------------------------------
* drops testbench files (anything under ``tb/``);
* moves simulation-only behavioural SRAM models (anything under ``sim/``) into a companion
  ``<name>_sim_models.f``, so the synthesisable list never contains a model that a hard
  macro replaces;
* puts packages first (stable: relative order inside each group is the Make order);
* adds ``EXTRA_RTL``: ``rv32i_clock_gate.sv`` is never named in ``PLL_SOURCES`` because
  Verilator finds it through ``-I rtl/mem``; sv2v has no such auto-discovery and silently
  BLACKBOXES a missing module, so the committed list names it;
* emits repo-root-relative paths and ``+incdir+`` for every directory that holds a listed
  RTL file.

Usage
-----
    python3 tools/verif/gen_filelist.py                 # (re)write rtl/filelist/*.f
    python3 tools/verif/gen_filelist.py --check         # CI: fail on any drift
    python3 tools/verif/gen_filelist.py --print soc_top --prefix /abs/repo   # absolute paths

Exit codes: 0 = ok / up to date, 1 = drift, 2 = a source list could not be resolved.
"""

from __future__ import annotations

import argparse
import difflib
import re
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_source_closure import extract_makefile_lists, resolve_makefile_vars  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]
FILELIST_DIR = "rtl/filelist"
GENERATOR = "tools/verif/gen_filelist.py"

PACKAGE_RE = re.compile(r"^\s*package\s+\w+", re.MULTILINE)

# Files every consumer needs but that the authoritative list does not name. Reason is
# mandatory so an addition is a recorded decision rather than an accident.
EXTRA_RTL: dict[str, str] = {
    "rtl/mem/rv32i_clock_gate.sv": (
        "instantiated by soc_top / the caches but absent from PLL_SOURCES: Verilator finds it "
        "via -I rtl/mem, sv2v has no -I discovery and would silently blackbox it"
    ),
}


class FilelistError(Exception):
    """A source list or path could not be resolved (exit code 2)."""


@dataclass(frozen=True)
class ListSpec:
    """One generated ``<name>.f`` (+ ``<name>_sim_models.f``)."""

    name: str  # file stem, e.g. "soc_top"
    top: str  # top module the list elaborates
    makefile: str  # repo-relative Makefile holding the authoritative variable
    variable: str  # Make variable listing the sources
    summary: str  # one-line description for the header
    extra_rtl: tuple[str, ...] = ()  # keys of EXTRA_RTL to append (after packages)
    # Make variables (in tb/cocotb/soc/Makefile) naming sim models this block needs even when
    # the authoritative list does not carry them (the pnr lists are synthesis-only).
    model_vars: tuple[str, ...] = ()


MODEL_VAR_MAKEFILE = "tb/cocotb/soc/Makefile"

SPECS: tuple[ListSpec, ...] = (
    ListSpec(
        name="soc_top",
        top="soc_top",
        makefile="tb/cocotb/soc/Makefile",
        variable="PLL_SOURCES",
        summary="full SoC (CPU + GPU + caches + peripherals + NPU/crypto), default arm",
        extra_rtl=("rtl/mem/rv32i_clock_gate.sv",),
    ),
    ListSpec(
        name="cpu_top",
        top="rv32i_cpu_top",
        makefile="pnr/Makefile",
        variable="CPU_SV_FILES",
        summary="RV32I CPU hard-macro cone (rv32i_cpu_top: core + I$/D$ + arbiter)",
        model_vars=("SRAM_SIM_MODEL",),
    ),
    ListSpec(
        name="gpu_top",
        top="gpu_top",
        makefile="pnr/Makefile",
        variable="GPU_SV_FILES",
        summary="GPU-lite SIMT engine hard-macro cone (gpu_top)",
        model_vars=("GPU_SRAM_SIM",),
    ),
)


# ── source resolution ────────────────────────────────────────────────────────


def _rel(token: str, root: Path) -> str:
    """Repo-root-relative POSIX path for a resolved Make token."""
    p = Path(token)
    try:
        return p.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise FilelistError(f"{token}: resolves outside the repository ({root})") from exc


def _classify(rel: str) -> str:
    """'rtl' | 'model' | 'tb'. Anything else is a new category that needs a decision."""
    top = rel.split("/", 1)[0]
    if top == "rtl":
        return "rtl"
    if top == "sim":
        return "model"
    if top == "tb":
        return "tb"
    raise FilelistError(
        f"{rel}: not under rtl/, sim/ or tb/ - teach {GENERATOR} how to classify it "
        "(refusing to guess which list it belongs to)"
    )


def _is_package(root: Path, rel: str) -> bool:
    return bool(PACKAGE_RE.search((root / rel).read_text(encoding="utf-8", errors="replace")))


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def collect(spec: ListSpec, root: Path) -> tuple[list[str], list[str]]:
    """Return ``(rtl_files, sim_models)`` for *spec*, both repo-relative, ordered."""
    makefile = root / spec.makefile
    if not makefile.is_file():
        raise FilelistError(f"{spec.makefile}: not found under {root}")
    lists = extract_makefile_lists(makefile)
    if spec.variable not in lists:
        raise FilelistError(
            f"{spec.makefile}: variable {spec.variable} not found / not a file list"
        )
    tokens = lists[spec.variable]
    unresolved = [t for t in tokens if "$" in t]
    if unresolved:
        raise FilelistError(f"{spec.makefile}::{spec.variable}: unresolved entries {unresolved}")

    rtl: list[str] = []
    models: list[str] = []
    for token in tokens:
        rel = _rel(token, root)
        kind = _classify(rel)
        if kind == "rtl":
            rtl.append(rel)
        elif kind == "model":
            models.append(rel)
        # kind == "tb": testbench, dropped by design

    if spec.model_vars:
        resolved, _ = resolve_makefile_vars(root / MODEL_VAR_MAKEFILE)
        for var in spec.model_vars:
            if var not in resolved or "$" in resolved[var]:
                raise FilelistError(f"{MODEL_VAR_MAKEFILE}: model variable {var} not resolvable")
            models.append(_rel(resolved[var], root))

    rtl = _dedupe(rtl)
    for key in spec.extra_rtl:
        if key not in EXTRA_RTL:
            raise FilelistError(f"{key}: extra_rtl entry has no recorded reason in EXTRA_RTL")
        rtl.append(key)
    rtl = _dedupe(rtl)

    for rel in rtl + models:
        if not (root / rel).is_file():
            raise FilelistError(f"{rel}: listed by {spec.makefile}::{spec.variable} but missing")

    # Packages first, then the extras are not packages so they simply follow them; the stable
    # partition keeps the authoritative Make order inside each group.
    pkgs = [r for r in rtl if _is_package(root, r)]
    rest = [r for r in rtl if r not in pkgs]
    return pkgs + rest, _dedupe(models)


def incdirs(rtl_files: Sequence[str]) -> list[str]:
    """Every directory that holds a listed RTL file, in first-appearance order."""
    return _dedupe([Path(f).parent.as_posix() for f in rtl_files])


# ── rendering ────────────────────────────────────────────────────────────────

DEFINES_BLOCK = """\
// DEFINES (arm selectors) - deliberately NOT baked in; pass them on the command line
// (Verilator/VCS/Xcelium/Questa: +define+NAME ; sv2v: --define=NAME):
//   (none)           default arm: behavioural SRAM models from <name>_sim_models.f. This is the
//                    arm the cocotb regression elaborates.
//   SIMULATION       enables the cdc_sync assertions / sim-only checks (the regression sets it).
//   SRAM_SKY130      Sky130 arm: caches, sram_controller and npu_weight_mem instantiate Sky130 SRAM
//                    macros (model: sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv, not in this list).
//   SRAM_ASAP7       ASAP7 arm: caches / npu_weight_mem instantiate sram_1rw_256x32_asap7 behind
//                    rv32i_clock_gate (hard macro; no sim model in this list).
//   FPGA             FPGA arm: block-RAM-inferable memories; also add rtl/fpga/*.sv (or
//                    -y rtl/fpga) to the compile. Mutually exclusive with SRAM_SKY130/SRAM_ASAP7.
//   __pnr__          physical-design arm (set by the sv2v/Yosys flows): drops sim-only code.
//   USE_ICG_CELL     rv32i_clock_gate instantiates the ASAP7 ICG library cell.
//   SRAM_CTRL_2P     sram_controller dual-port variant (sim only).
//   TRNG_RO_SKY130   Sky130 ring-oscillator entropy source; needs rtl/periph/trng_ro_sky130.sv,
//                    which is deliberately in no default list.
"""

USAGE_BLOCK = """\
// USAGE - paths are REPO-ROOT-RELATIVE, so run from the repository root and use -f:
//     verilator --lint-only -Wall -Wno-fatal --top-module {top} \\
//         -f {dir}/{name}.f -f {dir}/{name}_sim_models.f
//     vcs   -sverilog -f {dir}/{name}.f -f {dir}/{name}_sim_models.f -top {top}
//     xrun  -sv       -f {dir}/{name}.f -f {dir}/{name}_sim_models.f -top {top}
//     vlog  -sv       -f {dir}/{name}.f -f {dir}/{name}_sim_models.f          (Questa)
//   Only Verilator 5.048 and sv2v/yosys were run against these lists; the VCS/Xcelium/Questa
//   lines follow those tools' documented -f semantics and are UNVERIFIED here (no licence).
// Do NOT use -F: it resolves paths relative to this file's own directory ({dir}/), which
// would look for {dir}/rtl/... and find nothing.
// From another working directory, either cd to the repo root first or print an absolute copy:
//     python3 tools/verif/gen_filelist.py --print {name} --prefix /abs/path/to/repo > /tmp/{name}.f
// sv2v / tools without -f: strip comments and options, then pass the paths as arguments:
//     grep -hvE '^(//|\\+|-|$)' {dir}/{name}.f {dir}/{name}_sim_models.f \\
//         | xargs sv2v <--define=...>
// Order: packages first, then the remaining RTL in the authoritative Make order. No `include
// is used anywhere in rtl/ today; the +incdir+ lines list every directory that holds a listed
// file so a future `include next to a source still resolves. NB Verilator treats +incdir+ like
// -I, i.e. it also auto-discovers modules by file name in those directories - to prove a list
// complete, run it with the +incdir+ lines removed (see {dir}/README.md).
"""


def _prefixed(path: str, prefix: str | None) -> str:
    return f"{prefix.rstrip('/')}/{path}" if prefix else path


def render_main(spec: ListSpec, rtl: Sequence[str], prefix: str | None = None) -> str:
    makefile_ref = f"{spec.makefile}::{spec.variable}"
    lines = [
        f"// {spec.name}.f - synthesisable RTL for {spec.top}: {spec.summary}",
        f"// GENERATED by {GENERATOR} from {makefile_ref} - DO NOT EDIT.",
        f"// Regenerate: python3 {GENERATOR} ; CI runs it with --check and fails on any diff.",
        f"// Companion: {spec.name}_sim_models.f (simulation-only SRAM models; not synthesisable).",
        "// No testbench files. Top module: " + spec.top,
        "//",
    ]
    lines += USAGE_BLOCK.format(top=spec.top, name=spec.name, dir=FILELIST_DIR).splitlines()
    lines += DEFINES_BLOCK.replace("<name>", spec.name).splitlines()
    for key in spec.extra_rtl:
        lines.append(f"// Added to the Make list (not in {spec.variable}): {key}")
        lines.append(f"//   because: {EXTRA_RTL[key]}")
    lines.append("//")
    lines.append("// ---- include directories ----")
    lines += [f"+incdir+{_prefixed(d, prefix)}" for d in incdirs(rtl)]
    lines.append("")
    lines.append(f"// ---- RTL ({len(rtl)} files, packages first) ----")
    lines += [_prefixed(f, prefix) for f in rtl]
    return "\n".join(lines) + "\n"


def render_models(spec: ListSpec, models: Sequence[str], prefix: str | None = None) -> str:
    lines = [
        f"// {spec.name}_sim_models.f - SIMULATION-ONLY behavioural SRAM models for {spec.name}.f",
        f"// GENERATED by {GENERATOR} from {spec.makefile}::{spec.variable} - DO NOT EDIT.",
        f"// Pair with the main list:  -f {FILELIST_DIR}/{spec.name}.f -f "
        f"{FILELIST_DIR}/{spec.name}_sim_models.f",
        "// These are the default-arm (no SRAM_* define) replacements for hard macros: they are",
        "// NOT synthesisable and must not go to synthesis / sv2v for PD. With SRAM_SKY130,",
        "// SRAM_ASAP7 or FPGA defined the macro / FPGA memory is used instead and the matching",
        "// model must come from the vendor view or rtl/fpga/*.sv (see the main list).",
        "// Paths are repo-root-relative: run from the repository root and use -f (not -F).",
        "//",
        f"// ---- simulation models ({len(models)} files) ----",
    ]
    lines += [_prefixed(m, prefix) for m in models]
    return "\n".join(lines) + "\n"


def build(
    root: Path | None = None, specs: Sequence[ListSpec] | None = None, prefix: str | None = None
) -> dict[str, str]:
    """Filename -> content for every generated list."""
    root = root or REPO_ROOT
    out: dict[str, str] = {}
    for spec in specs or SPECS:
        rtl, models = collect(spec, root)
        out[f"{spec.name}.f"] = render_main(spec, rtl, prefix)
        out[f"{spec.name}_sim_models.f"] = render_models(spec, models, prefix)
    return out


# ── write / check ────────────────────────────────────────────────────────────


def write(root: Path | None = None, specs: Sequence[ListSpec] | None = None) -> list[str]:
    root = root or REPO_ROOT
    outdir = root / FILELIST_DIR
    outdir.mkdir(parents=True, exist_ok=True)
    generated = build(root, specs)
    for name, text in generated.items():
        (outdir / name).write_text(text, encoding="utf-8")
    return sorted(generated)


def check(root: Path | None = None, specs: Sequence[ListSpec] | None = None) -> list[str]:
    """Return human-readable drift messages (empty list = up to date)."""
    root = root or REPO_ROOT
    outdir = root / FILELIST_DIR
    generated = build(root, specs)
    problems: list[str] = []
    for name, want in sorted(generated.items()):
        path = outdir / name
        rel = f"{FILELIST_DIR}/{name}"
        if not path.is_file():
            problems.append(f"{rel}: missing (run python3 {GENERATOR})")
            continue
        have = path.read_text(encoding="utf-8")
        if have != want:
            diff = "".join(
                difflib.unified_diff(
                    have.splitlines(keepends=True),
                    want.splitlines(keepends=True),
                    fromfile=f"{rel} (committed)",
                    tofile=f"{rel} (regenerated)",
                    n=1,
                )
            )
            problems.append(f"{rel}: out of date\n{diff}")
    if outdir.is_dir():
        for extra in sorted(p.name for p in outdir.glob("*.f") if p.name not in generated):
            problems.append(
                f"{FILELIST_DIR}/{extra}: not produced by {GENERATOR} (stale / hand-written)"
            )
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="fail if the committed lists drifted")
    mode.add_argument("--print", dest="print_name", metavar="NAME", help="print NAME[.f] to stdout")
    ap.add_argument("--prefix", help="with --print: prepend this directory to every path")
    ap.add_argument("--models", action="store_true", help="with --print: the sim-models companion")
    args = ap.parse_args(argv)

    try:
        if args.check:
            problems = check()
            if problems:
                print("RTL filelist drift (bead 1as3):", file=sys.stderr)
                for p in problems:
                    print(f"  {p}", file=sys.stderr)
                print(f"\nFix: python3 {GENERATOR}  (then commit rtl/filelist/)", file=sys.stderr)
                return 1
            print(f"OK: {FILELIST_DIR}/*.f match their Makefile sources")
            return 0
        if args.print_name:
            stem = args.print_name.removesuffix(".f").removesuffix("_sim_models")
            key = f"{stem}_sim_models.f" if args.models else f"{stem}.f"
            built = build(prefix=args.prefix)
            if key not in built:
                print(f"unknown list {key}; have {sorted(built)}", file=sys.stderr)
                return 2
            sys.stdout.write(built[key])
            return 0
        for name in write():
            print(f"wrote {FILELIST_DIR}/{name}")
        return 0
    except FilelistError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
