#!/usr/bin/env python3
"""Assert every peripheral / NPU RTL module appears in all five build file lists.

Why this exists
---------------
Adding an APB4 peripheral means touching five separate Make source lists. Missing
one has wildly asymmetric consequences:

  * Missing from a *cocotb* list -> Verilator errors out immediately. Loud, cheap.
  * Missing from a *PD* list     -> **sv2v silently blackboxes the module.** The
    flow completes, the netlist is wrong, and no cocotb suite can ever detect it,
    because cocotb does not run the PD flow.

That second case is what this script exists to prevent. It is read-only and
dependency-free, intended to run in CI beside lint.

Relationship to check_source_closure.py
---------------------------------------
`check_source_closure.py` answers a *different* question: does a given list
contain the packages that the files already in it `import`? A peripheral that is
entirely absent from a list closes perfectly well under that check, because
nothing in the list imports it. That blind spot is exactly the sv2v-blackbox
hazard, so this script complements it rather than duplicating it.

Make-variable resolution is **reused** from `check_source_closure.py`
(`extract_makefile_lists`), so there is exactly one Make parser in this repo.

What it checks
--------------
Every `.sv` file under `rtl/periph/` and `rtl/npu/` that declares a `module` must
be referenced by all five lists in `LISTS`. Anything legitimately absent must be
named in `EXEMPT` with a written reason, so an omission is always a recorded
decision rather than an oversight.

Usage
-----
    python3 tools/verif/check_periph_filelists.py            # check; exit 1 on failure
    python3 tools/verif/check_periph_filelists.py --list     # show each list's entries

Exit codes: 0 = all present, 1 = at least one missing, 2 = a list could not be parsed.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_source_closure import extract_makefile_lists  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[2]

# (makefile, variable, human label). A peripheral must appear in every one.
LISTS: list[tuple[str, str, str]] = [
    ("tb/cocotb/soc/Makefile", "PLL_SOURCES", "cocotb PLL/SoC suites"),
    ("tb/cocotb/soc/Makefile", "SOC_BOOT_SOURCES", "cocotb soc_top suites"),
    ("sim/Makefile", "SOC_TOP_SOURCES", "sim/ lint + regression"),
    ("pnr/Makefile", "SKY130_SOC_SV_FILES", "Sky130 SoC PD (sv2v)"),
    ("pnr/Makefile", "SOC_SV_FILES", "ASAP7 SoC PD (sv2v)"),
]

# Directories whose modules must appear in every list above.
SCAN_DIRS = ["rtl/periph", "rtl/npu"]

# basename -> reason. Keep reasons specific; a vague entry defeats the purpose.
EXEMPT: dict[str, str] = {
    # Sky130-only entropy source for the TRNG, selected by `ifdef TRNG_RO_SKY130`
    # and never compiled in the portable default build, so it is deliberately
    # absent from every list. See docs/PHASE6_IP_EXPANSION_PLAN.md section 7.
    "trng_ro_sky130.sv": "ifdef-gated Sky130-only entropy source; not in the default build",
}

MODULE_RE = re.compile(r"^\s*module\s+(\w+)", re.MULTILINE)


def load_lists() -> dict[str, list[str]] | None:
    """Resolve every configured list. Returns None after reporting a hard error.

    A variable that cannot be found is fatal rather than treated as empty — an
    empty list would silently pass every membership test.
    """
    resolved: dict[str, list[str]] = {}
    by_makefile: dict[str, dict[str, list[str]]] = {}

    for rel, var, _label in LISTS:
        if rel not in by_makefile:
            try:
                by_makefile[rel] = extract_makefile_lists(REPO_ROOT / rel)
            except Exception as exc:  # noqa: BLE001 - surface the parser's own message
                print(f"ERROR: could not parse {rel}: {exc}", file=sys.stderr)
                return None

        lists = by_makefile[rel]
        if var not in lists:
            print(f"ERROR: variable '{var}' not found in {rel}.", file=sys.stderr)
            print("       It was renamed, or its definition form changed.", file=sys.stderr)
            print("       Update LISTS in this script — do not delete the check.",
                  file=sys.stderr)
            return None
        resolved[f"{rel}::{var}"] = lists[var]

    return resolved


def declares_module(path: Path) -> bool:
    try:
        return bool(MODULE_RE.search(path.read_text()))
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true",
                    help="print each list's peripheral/NPU entries and exit")
    args = ap.parse_args()

    resolved = load_lists()
    if resolved is None:
        return 2

    if args.list:
        for rel, var, label in LISTS:
            entries = resolved[f"{rel}::{var}"]
            hits = sorted({Path(e).name for e in entries
                           if "/periph/" in e or "/npu/" in e})
            print(f"\n{label}  ({rel} :: {var})  — {len(hits)} peripheral/NPU entries")
            for h in hits:
                print(f"    {h}")
        return 0

    sources: list[Path] = []
    for d in SCAN_DIRS:
        sources.extend(sorted((REPO_ROOT / d).glob("*.sv")))

    if not sources:
        print(f"ERROR: no .sv files found under {SCAN_DIRS}.", file=sys.stderr)
        return 2

    # Pre-compute the basename set per list; membership is by filename, because
    # the lists use different path prefixes ($(RTL), $(RTL_DIR), $(PROJECT_ROOT)/rtl).
    names_per_list = {key: {Path(e).name for e in entries}
                      for key, entries in resolved.items()}

    failures: list[str] = []
    skipped: list[str] = []
    checked = 0

    for src in sources:
        name = src.name
        if name in EXEMPT:
            skipped.append(f"{name} — {EXEMPT[name]}")
            continue
        if not declares_module(src):
            skipped.append(f"{name} — declares no module (package or header?)")
            continue

        checked += 1
        rel_src = src.relative_to(REPO_ROOT)
        for rel, var, label in LISTS:
            if name not in names_per_list[f"{rel}::{var}"]:
                failures.append(f"{rel_src}\n      missing from  {rel} :: {var}   ({label})")

    for note in skipped:
        print(f"skip: {note}")

    if failures:
        plural = "y" if len(failures) == 1 else "ies"
        print(f"\nFAIL: {len(failures)} missing file-list entr{plural} "
              f"across {checked} module file(s):\n", file=sys.stderr)
        for f in failures:
            print(f"  {f}", file=sys.stderr)
        print("\nA module missing from a PD list is silently BLACKBOXED by sv2v: the flow",
              file=sys.stderr)
        print("completes, the netlist is wrong, and no cocotb suite can detect it.",
              file=sys.stderr)
        print("Add the file to each list above, or add it to EXEMPT with a reason.",
              file=sys.stderr)
        return 1

    print(f"\nOK: all {checked} peripheral/NPU module file(s) present in all "
          f"{len(LISTS)} build file lists.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
