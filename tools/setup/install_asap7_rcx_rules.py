#!/usr/bin/env python3
"""Install the real ASAP7 OpenRCX extraction-rules deck into the manually
structured PDK tree, replacing the 0-byte stub.

Why this script exists: `~/pdk/asap7/libs.tech/openlane/rcx_rules.pex` ships
as an empty placeholder (its own header comment admits it: "stub --
RUN_SPEF_EXTRACTION=false, but variable must be set"). `~/pdk/asap7` is NOT a
git repo and is NOT vendored into this repo, so a one-off `cp` from an
engineer's machine is a silent single-clone fix that the next clone loses --
exactly the failure class `make setup` / `make verify-tooling` exist to
prevent for the rest of this project's tooling (see repo-root Makefile).
This script makes that install reproducible and self-verifying instead.

Source of the real ruleset: OpenROAD-flow-scripts (ORFS)
`flow/platforms/asap7/rcx_patterns.rules` -- a genuine OpenRCX rules deck
(`DIAGMODEL ON`, `LayerCount 10`, per-metal DIST tables), used upstream as
`RCX_RULES` in `flow/platforms/asap7/config.mk`. Geometry-equivalence with
this repo's tech LEF (`asap7_tech_1x_201209.lef`) was hand-verified before
this script was written: every WIDTH/PITCH/SPACING/THICKNESS/DIRECTION line
across all 10 ROUTING layers matches byte-for-byte (76/76 lines, 0 diffs)
between ORFS's and this repo's tech LEF; only non-routing layers (implant vs.
masterslice declarations, which do not feed RC extraction) differ. See bead
claude_verilog_test-e69 and the PR that introduced this script for the full
diff. Do not regenerate this ruleset from `bench_wires`/`bench_read` --
vendoring the validated upstream file is sufficient and was the explicit
resolution of that bead.

Stdlib only -- this runs from a Makefile target, outside any Python venv.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

DEFAULT_ORFS_ROOT = Path.home() / "Downloads" / "Github" / "OpenROAD-flow-scripts"
DEFAULT_PDK_ROOT = Path.home() / "pdk"

RULES_SRC_RELPATH = Path("flow") / "platforms" / "asap7" / "rcx_patterns.rules"
RULES_DST_RELPATH = Path("asap7") / "libs.tech" / "openlane" / "rcx_rules.pex"

# The real deck starts with this header and is well over 100 KB; the stub it
# replaces is exactly 0 bytes. Both are cheap, meaningful sanity checks that
# a `cp` of the wrong file (or a truncated one) will not silently pass.
EXPECTED_HEADER = "Extraction Rules for OpenRCX"
MIN_EXPECTED_BYTES = 50_000


def _orfs_commit(orfs_root: Path) -> str | None:
    """Best-effort ORFS commit hash for the provenance message. None if the
    tree isn't a git checkout (e.g. a tarball extract) -- not fatal."""
    try:
        out = subprocess.run(
            ["git", "-C", str(orfs_root), "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None


def _verify(path: Path) -> tuple[bool, str]:
    """Return (ok, message) for whether `path` looks like the real ruleset."""
    if not path.is_file():
        return False, f"{path}: does not exist"
    size = path.stat().st_size
    if size == 0:
        return False, f"{path}: is the 0-byte stub (RUN_SPEF_EXTRACTION cannot work)"
    if size < MIN_EXPECTED_BYTES:
        return False, f"{path}: only {size} bytes (expected > {MIN_EXPECTED_BYTES}); looks truncated"
    with path.open("r", encoding="utf-8", errors="replace") as f:
        head = f.read(4096)
    if EXPECTED_HEADER not in head:
        return False, f"{path}: {size} bytes but missing expected header '{EXPECTED_HEADER}'"
    return True, f"{path}: OK ({size} bytes, header present)"


def check(pdk_root: Path) -> int:
    """--check-only: verify the installed rules without touching anything."""
    dst = pdk_root / RULES_DST_RELPATH
    ok, message = _verify(dst)
    print(("OK: " if ok else "FAIL: ") + message)
    if not ok:
        print(
            "Run tools/setup/install_asap7_rcx_rules.py (or `make -C pnr "
            "install-asap7-rcx-rules`) to install the real ruleset from ORFS."
        )
    return 0 if ok else 1


def install(orfs_root: Path, pdk_root: Path) -> int:
    src = orfs_root / RULES_SRC_RELPATH
    dst = pdk_root / RULES_DST_RELPATH

    if not src.is_file():
        print(
            f"ERROR: source ruleset not found at {src}\n"
            "       Expected an OpenROAD-flow-scripts checkout at "
            f"{orfs_root} (override with --orfs-root or $ORFS_ROOT).\n"
            "       Clone: git clone https://github.com/The-OpenROAD-Project/"
            "OpenROAD-flow-scripts"
        )
        return 1

    src_ok, src_message = _verify(src)
    if not src_ok:
        print(f"ERROR: source file failed verification: {src_message}")
        return 1

    if not dst.parent.is_dir():
        print(f"ERROR: destination directory does not exist: {dst.parent}")
        print("       Is $MANUAL_PDK_ROOT / --pdk-root pointing at a real ASAP7 PDK tree?")
        return 1

    commit = _orfs_commit(orfs_root)
    print(f"Source : {src} ({src.stat().st_size} bytes)")
    print(f"  ORFS commit: {commit or 'unknown (not a git checkout)'}")
    print(f"Dest   : {dst}")

    if dst.is_file() and dst.stat().st_size > 0:
        print(f"  NOTE: destination already exists ({dst.stat().st_size} bytes) -- overwriting")

    shutil.copyfile(src, dst)

    ok, message = _verify(dst)
    if not ok:
        print(f"ERROR: post-copy verification failed: {message}")
        return 1

    print(f"OK: {message}")
    print(
        "Provenance recorded here and in the config.tcl comment this replaces: "
        "vendored from OpenROAD-flow-scripts "
        f"{RULES_SRC_RELPATH} (commit {commit or 'unknown'}). See bead "
        "claude_verilog_test-e69 for the geometry-equivalence evidence."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--orfs-root", type=Path, default=DEFAULT_ORFS_ROOT,
        help=f"OpenROAD-flow-scripts checkout (default: {DEFAULT_ORFS_ROOT})",
    )
    parser.add_argument(
        "--pdk-root", type=Path, default=DEFAULT_PDK_ROOT,
        help=f"manual PDK root, i.e. the dir containing asap7/ (default: {DEFAULT_PDK_ROOT})",
    )
    parser.add_argument(
        "--check-only", action="store_true",
        help="verify the installed rules without copying anything; exit 1 if still the stub",
    )
    args = parser.parse_args()

    if args.check_only:
        return check(args.pdk_root)
    return install(args.orfs_root, args.pdk_root)


if __name__ == "__main__":
    sys.exit(main())
