# `hls/` — Bambu HLS flow (GH #119 PPA pilot)

C++ → Verilog via **Bambu (PandA) 2024.10**, for the empirical arm of
[`docs/CPP_TO_RTL_HLS_EVALUATION.md`](../docs/CPP_TO_RTL_HLS_EVALUATION.md): measure the QoR gap
between `NL → C++ → HLS` and the project's hand-written RTL on already-signed-off blocks.

This directory holds **inputs only** — C++ sources, testbenches, port-adapting shims, and the flag
set. Generated Verilog is not committed (see "Reproducibility" below).

## Running

Bambu lives in its own devshell, because it needs an FHS sandbox and its own 32-bit/ncurses
runtime (see the extensive comment block in [`flake.nix`](../flake.nix)):

```bash
nix develop .#hls --command make -C hls gate_b     # the Gate B port-shape regression
nix develop .#hls --command bambu --version        # PandA 2024.10, rev c2ba6936…
```

Every target runs through [`tools/eda/wrap-bambu.sh`](../tools/eda/wrap-bambu.sh), so the exit
status is a real verdict, not Bambu's own. Bambu exits 0 on a generation run that produced nothing
useful, and its co-simulation can die without the HLS phase noticing — bead `dwp`.

## The pinned flags

All in [`bambu.mk`](bambu.mk), with a per-flag rationale. Two are worth repeating because they fail
*silently*:

- **`--generate-interface=INFER`** — the `#pragma HLS interface` lines are inert under the default
  `MINIMAL`. Omit it and you get BRAM-style ports instead of an AXI master, with no error.
- **`--compiler=I386_CLANG16`** — those pragmas are parsed by Bambu's clang plugin; a GCC front-end
  never sees them.

## Two testbench rules (learned the hard way, GH #119 Gate B)

1. **Use the XML testbench form for anything with an `m_axi` bundle.** A C-driver testbench
   (`--generate-tb=x.c`) cannot size a memory space from a decayed pointer: `unsigned* mem` gets a
   4-byte space and every access past offset 0 dies with
   `Interface N: Read to non-mapped address`. Passing several pointers into one array collapses
   them into a single 4-byte space (`Unknown data required: 4`). The XML form
   (`mem="{v0,…,vN}"`, one `r_i="{0}"` per pointer output) sizes each space explicitly.
2. **Never pass `--tb-param-size`.** It would fix the sizing above, but its own help says it
   "will disable automated top-level function verification" — it makes the equivalence leg
   vacuous, which is the one thing this pilot cannot afford.

## Reproducibility

Generated `.v` goes to `$(HLS_OUT)` (default `/nobackup/hls/out/<block>/`) and is **not committed**:
it is large, machine-written, and regenerable.

Bambu stamps the generation time into a header comment of every `.v`, so the raw sha256 differs on
every run. Verified: three back-to-back runs of identical input produced three different digests
and were byte-identical everywhere except the `- Date …` line. The wrapper therefore reports two
digests — `verilog_sha256` (identity of the exact file on disk) and
**`verilog_sha256_normalized`** (the same file with the date blanked). The normalized one is stable
across runs and is the digest to pin.
