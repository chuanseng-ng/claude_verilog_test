# `rv32i_hazard_unit` HLS arm — authoring record and results

GH #119 bead `gvr`, the **control pole** of the pilot. Companion to
`hls/gpu/memory_coalescer/NOTES.md` (the datapath pole). Part of the reproducibility pin required
by `docs/CPP_TO_RTL_HLS_EVALUATION.md` L127-133.

## Method: the RTL body was withheld

Same protocol as the coalescer. The C was authored by an agent whose entire input was the block's
natural-language spec (the header comment of `rtl/cpu/core/rv32i_hazard_unit.sv`, lines 1-26), the
port list (lines 28-120), and Bambu's shape constraints. It was **barred from reading anything
under `rtl/`** and confirmed it did not. The verbatim prompt is in the bead record.

`ASSUMPTIONS.md` (405 lines) records the assumptions and ranks the residual risks. That ranking
turned out to be predictive — see below.

## Headline result 1: HLS cannot express this block's form at all

The reference is **purely combinational** — no clock, no reset, no `always_ff`, zero flip-flops.
Bambu cannot emit combinational logic: it wraps every design in a `start_port`/`done_port`
handshake. The generated core has **9 FSM states, 50 flip-flops, and takes 6-9 cycles per
evaluation — and the latency is data-dependent.**

This is not an artefact of how the C was written. The author tested that directly: they rebuilt the
stall/flush section branch-free, with no `if`/`else if` priority chain at all, and got an
**identical schedule** (9 states, 6-9 cycles, 11 control steps; area within 0.3 %). It is Bambu
scheduling a wide 32-bit comparison network against a 0.705 ns clock, not an authoring choice.

For a block whose entire purpose is to resolve hazards **within one cycle**, a 6-9 cycle
data-dependent replacement is not a drop-in substitute at any clock period. This is the
"HLS is weaker on control logic" claim of `CPP_TO_RTL_HLS_EVALUATION.md`, measured on this
project's own RTL — and it is a stronger statement than a PPA delta, because no amount of
tuning converts a multi-cycle FSM back into a combinational cloud.

## Headline result 2: NL→C spec drift, and this time it bit

On the coalescer the spec gap did **not** materialise. Here it did, and it is precisely
quantified.

| | hand-RTL | HLS + shim |
|---|---|---|
| directed spec-derived tests | **28 / 28** | **26 / 28** |
| cross-arm differential (2000 random vectors) | — | **254 mismatched (12.7 %)** |

The two failing directed tests are `test_fwd_a_priority_ex1c_over_ex1b2_ex2_wb` and
`test_fwd_a_priority_ex1b2_over_ex2_wb`; both fail as `fwd_a_sel: expected 0, got 3`.

**Root cause.** Those vectors set `ex1b_mem_rd = 1` and `ex1c_mem_rd = 1` — the EX1b/EX1c producers
are *loads*, whose results are not yet available, so those forwarding tiers must be excluded and a
lower tier wins. The HLS implementation gates only the **EX2** tier on `mem_rd`, not the EX1b or
EX1c tiers, so it over-forwards from in-flight loads.

**The failure was predicted by the author, in advance, in `ASSUMPTIONS.md`.** Residual risk #3 is
`ex_mem_mem_rd` gating the EX2 tier, with the note that "the load-use interlock makes the gate
unreachable in any legal pipeline state… it will only ever fail under random-vector equivalence,
never under a trace." That is exactly what happened: the divergence is invisible to a legal
pipeline trace and only appears under synthetic vectors. It is a real bug in a real pipeline only
if a consumer can sit in EX1a while a load sits in EX1b/EX1c without the interlock having fired.

**Every mismatch is confined to forwarding outputs.** All 254 land on `fwd_*` fields and their
`*_pre` counterparts (`fwd_b_sel` 40, `fwd_store_sel` 40, `fwd_b_ex1c` 32, `fwd_store_ex1c` 32,
`fwd_a_sel` 29, …). **No stall, flush, or load-use output ever mismatched** — the 9-item priority
ladder, which is the part the spec states explicitly and completely, was reproduced exactly. The
drift is entirely in the part the spec left to inference.

That is the sharpest form of this pilot's result: **the spec-stated behaviour transferred
perfectly; the spec-implied behaviour did not.**

## The equivalence harness

The two arms have genuinely different interfaces — combinational versus handshake — so a single
uniform wrapper would have meant injecting RTL into the reference arm. Instead
`tb/cocotb/cpu/test_hazard_unit.py` detects the arm at runtime (`hasattr(dut, "clk")`) and branches
in exactly one place; vectors, expected values and assertions are identical for both.

Two independent layers, because neither alone suffices:
- **Directed tests, oracle = the spec.** Expected values derived by hand from the documented
  9-item priority ladder and forwarding encoding — not from the reference implementation, which
  would have made the test a tautology that can only ever confirm whatever the RTL does.
- **Randomised cross-arm differential.** 2000 seeded vectors (seed 12345), register addresses
  drawn from a small pool so producer/consumer collisions are frequent, dumped per-arm and diffed
  by `tools/verif/compare_hazard_traces.py`. That comparator refuses to pass vacuously (bead
  `dwp`): missing, empty, or mismatched-length traces are ERROR(2), not PASS.

This suite is new standalone coverage for a block that previously had none — worth having
independently of #119.

## The shim is wire-only

`shim/rv32i_hazard_unit_hls.sv`, module `rv32i_hazard_unit_hls`. Zero registers — only
zero-extension of the 26 inputs (5-bit and 1-bit → 32-bit), truncation of the 28 outputs (32-bit →
2-bit or 1-bit), and the four handshake ports the reference does not have (`clk`, `rst_n`,
`start_i`, `done_o`). No tie-offs were needed; unlike the coalescer core this one exposes no
`cache_reset`. It contributes 0 Verilator warnings.

## Two toolchain findings

1. **Bambu refuses to inline ordinary `static` C helpers.** With the forwarding cascade factored
   into a `static` function called five times, Bambu emitted `Required never inline for function`,
   turned it into a shared 1-resource submodule with 80 bytes of internal DISTRAM, and **failed
   the build**: `clock constraint too tight: BRAMs for this device cannot run so fast
   (0.8129 > 0.7050)`. `__attribute__((always_inline))` did not change the decision. The only fix
   was demoting the helpers to preprocessor macros. Ordinary C factoring is not available here.
2. **The generated hierarchy is pathological for Verilator.** Bambu instantiates ~550 modules for
   this one block; Verilator then emits a symbol-table constructor of ~4000 giant statements in a
   single 1.2 MB translation unit, and g++ spun on that one file at 99.9 % CPU for **32 minutes**
   at `-O0` before being killed. Fixed with `--output-split 500` on the HLS arms (`sim/Makefile`),
   which also carry `NO_TRACE=1` — waveform tracing does not scale to this module count either.
   Both are harness-only and change no functional result.

## Reproducibility

- Bambu PandA 2024.10, rev `c2ba6936ca2ed63137095fea0b630a1c66e20e63-main`, pinned by sha256 in
  `flake.nix`; flags in `hls/bambu.mk`.
- Leg 1 (Bambu C/RTL cosim, 30 vectors covering all 9 priority cases, each forwarding tier, an
  x0 case and 13 randomised): **PASS**, 203 cycles / 6 average.
- Generated Verilog is not committed. Pin the **normalized** digest (Bambu stamps a timestamp into
  a header comment, so the raw digest changes every run):
  `verilog_sha256_normalized = 397eb1ce38e3619a3f0072daa90035b88283fb87216eaf4444512faae593aeda`

### Numbers for Stage 2 (do not treat as PPA)

Bambu's own pre-synthesis estimates: **50 flip-flops** (reference: **0**), estimated area
1 791 535, 0 DSPs, 11 control steps, estimated fmax 1857 MHz. As with the coalescer these are not
comparable to the hand-RTL as-is — Stage 2 must synthesise both for real and state the counting
boundary. The flip-flop count is the one figure that needs no normalisation: 0 versus 50, for a
block the spec describes as combinational.
