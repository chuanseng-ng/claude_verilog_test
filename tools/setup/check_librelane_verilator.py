#!/usr/bin/env python3
"""Lint the CPU block's RTL with LibreLane's OWN Verilator, not the project's.

Why this exists (bead claude_verilog_test-2wo). Three different Verilators are
reachable on a typical dev host here:

    librelane nix-shell   5.018 (2023-10-30)   <- every `make librelane-*` run
    project flake         5.048 (2026-04-26)   <- every `make -C sim lint*` run
    nix-shell -p verilator 5.050 (2026-07-01)  <- `pnr/Makefile`'s `lint` target

LibreLane's flow starts with step `01-verilator-lint`, gated by
`02-checker-linterrors`, and it runs inside the FIRST one. So RTL can be lint
clean under 5.048 all day and still kill a P&R run at step 1.

That is not hypothetical. Commit f814b21 flipped the i/d-cache valid/dirty
bulk-clear loops from blocking to non-blocking assignment to satisfy Spyglass
SM_BNP/W336, which 5.018 rejects outright:

    %Error-BLKLOOPINIT: Unsupported: Delayed assignment to array inside for
                        loops (non-delayed is ok - see docs)

Nothing caught it, because no sim or lint target in the repo uses 5.018 and no
P&R run had been started since. This check closes that gap.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# Mirrors librelane/steps/verilator.py's Lint step. Kept deliberately close to
# what the flow actually emits (see any run's 01-verilator-lint/COMMANDS) so a
# pass here means a pass there.
LINT_FLAGS = [
    "--lint-only",
    "--Wall",
    "--Wno-DECLFILENAME",
    "--Wno-EOFNEWLINE",
    "--Wno-fatal",
    "--relative-includes",
]

DEFAULT_CONFIG = "pnr/asap7/cpu/config.json"
DEFAULT_LIBRELANE = Path.home() / "Downloads" / "Github" / "librelane"


def resolve_verilog_files(config_path: Path) -> tuple[list[Path], list[str]]:
    """Return (source files, +define+ args) from a librelane config.json.

    librelane's `dir::` prefix is relative to the config file's own directory.
    """
    cfg = json.loads(config_path.read_text())
    base = config_path.parent

    files: list[Path] = []
    for entry in cfg.get("VERILOG_FILES", []):
        raw = entry[len("dir::"):] if entry.startswith("dir::") else entry
        resolved = (base / raw).resolve()
        if not resolved.is_file():
            raise FileNotFoundError(f"{config_path}: VERILOG_FILES entry not found: {entry}")
        files.append(resolved)

    if not files:
        raise ValueError(f"{config_path}: no VERILOG_FILES")

    # The flow lints with the power define on and the PDK/SCL defines set; a
    # missing define can hide or invent errors, so carry the ones that matter.
    defines = ["+define+USE_POWER_PINS", "+define+__librelane__", "+define+__pnr__"]
    for key, prefix in (("PDK", "PDK_"), ("STD_CELL_LIBRARY", "SCL_")):
        value = cfg.get(key)
        if isinstance(value, str):
            defines.append(f"+define+{prefix}{value}")
    # librelane's Lint step takes its extra defines from LINTER_DEFINES, NOT
    # VERILOG_DEFINES -- the two differ in practice (the ASAP7 CPU config sets
    # VERILOG_DEFINES=[SRAM_ASAP7, USE_ICG_CELL] but LINTER_DEFINES=[SRAM_ASAP7],
    # and any run's 01-verilator-lint/COMMANDS confirms only the latter reaches
    # the linter). Getting this wrong makes the SRAM macro unresolvable and the
    # check fails for a reason that has nothing to do with the RTL.
    extra = cfg.get("LINTER_DEFINES")
    if extra is None:
        extra = cfg.get("VERILOG_DEFINES", [])
    for name in extra:
        defines.append(f"+define+{name}")

    return files, defines


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=DEFAULT_CONFIG,
                    help=f"librelane config.json to take VERILOG_FILES from (default: {DEFAULT_CONFIG})")
    ap.add_argument("--top", default="rv32i_cpu_top", help="top module (default: rv32i_cpu_top)")
    ap.add_argument("--librelane-dir", default=os.environ.get("LIBRELANE_DIR", str(DEFAULT_LIBRELANE)),
                    help="LibreLane checkout whose nix-shell provides the Verilator to test with")
    ap.add_argument("--repo-root", default=None, help="repo root (default: this script's ../..)")
    ap.add_argument("--timeout", type=int, default=900, help="seconds to allow for the lint (default: 900)")
    args = ap.parse_args()

    repo_root = Path(args.repo_root).resolve() if args.repo_root \
        else Path(__file__).resolve().parents[2]
    config_path = (repo_root / args.config).resolve()
    librelane_dir = Path(args.librelane_dir).expanduser()

    # A machine without LibreLane installed is a legitimate skip. Say so
    # loudly: a silent no-op is the exact failure mode this file guards.
    if not librelane_dir.is_dir():
        print(f"  SKIP: no LibreLane checkout at {librelane_dir}")
        print("        (set LIBRELANE_DIR to check, or ignore on a sim-only clone)")
        return 0
    if shutil.which("nix-shell") is None:
        print("  SKIP: nix-shell not on PATH — cannot enter LibreLane's shell")
        return 0
    if not config_path.is_file():
        print(f"  FAIL: config not found: {config_path}", file=sys.stderr)
        return 1

    try:
        files, defines = resolve_verilog_files(config_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"  FAIL: {exc}", file=sys.stderr)
        return 1

    inner = " ".join([
        "verilator --version;",
        "verilator", *LINT_FLAGS, "--top-module", args.top,
        *(str(f) for f in files), *defines,
    ])

    try:
        proc = subprocess.run(
            ["nix-shell", "--run", inner],
            cwd=str(librelane_dir), capture_output=True, text=True, timeout=args.timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"  FAIL: lint did not finish within {args.timeout}s", file=sys.stderr)
        return 1

    out = (proc.stdout or "") + (proc.stderr or "")
    version = next((ln.strip() for ln in out.splitlines() if ln.startswith("Verilator ")),
                   "Verilator <version not reported>")

    errors = [ln for ln in out.splitlines() if ln.startswith("%Error")]
    if proc.returncode != 0 or errors:
        print(f"  FAIL: {config_path.relative_to(repo_root)} does not lint under LibreLane's {version}",
              file=sys.stderr)
        print(f"         (it may still be clean under the project flake's Verilator —"
              f" that is the whole point of this check)", file=sys.stderr)
        for line in errors[:20]:
            print(f"         {line}", file=sys.stderr)
        if not errors:
            print("         no %Error lines; raw tail follows", file=sys.stderr)
            for line in out.splitlines()[-20:]:
                print(f"         {line}", file=sys.stderr)
        return 1

    print(f"  ok: {config_path.relative_to(repo_root)} lints clean under LibreLane's {version}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
