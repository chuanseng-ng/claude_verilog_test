#!/usr/bin/env python3
"""Strip `// synthesis translate_off` regions from Bambu output for synthesis.

Bambu correctly guards its simulation-only code (an AXI-response checker calling
$display/$finish) with the standard pragma pair

    // synthesis translate_off
    ...
    // synthesis translate_on

Yosys' native Verilog frontend honours that pragma; **Synlig (the UHDM/Surelog
frontend this project needs for its SystemVerilog) does not**, and fails with

    ERROR: System task `$finish' outside initial block is unsupported.

Switching the comparison to the Yosys-native frontend is not an option: it cannot
parse the repo's SystemVerilog (packages, typedefs) or the shims, and both arms
fail. Keeping Synlig and removing the guarded regions here is a semantic no-op --
`translate_off` means "synthesis must not see this" -- and keeps every arm on the
identical frontend, which is what makes the PPA numbers comparable at all.

The generated `.v` is left untouched, so the digest pinned in hls/PROVENANCE.json
still describes the real artefact. This writes a separate `*_synth.v` differing
only by the removal of simulation-only regions.

GH #119 bead r8r.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# Non-greedy so each pragma pair matches individually; DOTALL so a region spans lines.
_REGION = re.compile(
    rb"[ \t]*//[ \t]*synthesis[ \t]+translate_off\b.*?//[ \t]*synthesis[ \t]+translate_on\b[ \t]*\n?",
    re.S | re.I,
)


def strip(data: bytes) -> tuple[bytes, int]:
    """Return the source with translate_off regions removed, and how many were removed."""
    return _REGION.subn(b"", data)


def main() -> int:
    """Strip simulation-only regions from one Verilog file."""
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("src", type=Path)
    ap.add_argument("dst", type=Path)
    args = ap.parse_args()

    data = args.src.read_bytes()
    out, n = strip(data)

    # A tool that silently produces nothing useful must not look like success
    # (bead dwp): if any simulation-only construct survives, fail loudly.
    leftover = [t for t in (b"$finish", b"$display", b"$stop") if t in out]
    if leftover:
        names = ", ".join(t.decode() for t in leftover)
        print(
            f"ERROR: {names} still present after stripping {n} region(s) - "
            f"Synlig will reject {args.dst}",
            file=sys.stderr,
        )
        return 2

    args.dst.write_bytes(out)
    removed = len(data.splitlines()) - len(out.splitlines())
    print(f"{args.src.name}: removed {n} region(s), {removed} lines -> {args.dst.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
