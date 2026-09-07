# `vector_alu` — HLS arm notes (GH #119, bead `gg8`)

Bead `gg8` exists because Stage 2 (`r8r`) closed with an admitted hole: the pilot's
recommendation had a *datapath* half that no measured block supported.
`memory_coalescer` — the block Stage 2 called the datapath pole — is an AXI
transaction FSM, not a datapath. `rtl/gpu/vector_alu.sv` is the real thing: 8 lanes ×
32 bits of pure combinational arithmetic, zero registers.

Same protocol as Stage 1: the C was authored from the natural-language spec with the
hand-RTL withheld (see `ASSUMPTIONS.md`), then Bambu-synthesised, then both arms taken
through identical ASAP7 runs.

## Result: the datapath half of the recommendation does not hold

| Metric | hand-RTL `vector_alu` | HLS `vector_alu_hls` | Δ |
| :-- | --: | --: | :-- |
| Area (µm²) | 4 655.15 | 7 234.00 | **+55.4 %** |
| Cells | 54 634 | 70 895 | +29.8 % |
| Sequential cells | **0** | 9 412 | — |
| Power (mW) | 14.147 | 37.281 | **+163.5 %** |
| Critical path | 759.29 ps (comb, in→out) | 4 142.52 ps (FF→FF) | ×5.5 |
| Cycles / operation | 1 (combinational) | mean 14.35, range 8–38 | ×14–38 |
| Undriven wires (`synthesis__check_error__count`) | **0** | 16 | — |

Against the thresholds in `docs/CPP_TO_RTL_HLS_EVALUATION.md` (>10 % fmax or >20 %
area/power = "regresses"), the HLS arm **regresses on every axis**, by margins several
times the threshold.

Throughput, which is the number that matters for a datapath: 759.29 ps for one
operation against 4 142.52 ps × 14.35 = **59.4 ns** average, 157.4 ns worst case —
**≈78× average, ≈207× worst**. Even crediting the HLS arm the fanout correction below,
it is ≈33× average.

## Two caveats that cut in the HLS arm's favour, both stated

1. **The 4 142.52 ps is inflated by a flow choice, not only by the design.** 2 550.65 ps
   of it — **62.3 %** — is a *single* arc: a minimum-drive `DFFASRHQNx1` driving
   **fanout 1188 / 630.7 fF** unbuffered. `--to OpenROAD.STAPrePNR` stops before the
   resizer, so no buffer tree is ever built. The other 12 arcs total 1 546.4 ps. A
   buffered version of that net would plausibly land the path near 1.7–1.8 ns.
   The hand-RTL arm has no comparable net (its worst arc is 60.6 ps, 8.0 % of its path,
   over 24 well-balanced arcs) so **skipping the resizer penalises the HLS arm
   asymmetrically**, even though both arms ran the identical flow.
   This does not change the verdict — area and power are resizer-independent, and both
   regress on their own — but the timing ratio should be read as ×2.2–5.5, not ×5.5 flat.

2. **Bambu's own `CYCLES value="7"` is not the latency.** Parsed per-vector from
   `results.txt`, the real distribution is 8 cycles ×22, 22 ×9, 38 ×3 — mean 14.35 over
   488 cycles / 34 vectors. The `7` figure is roughly half the true mean and must not be
   quoted.

## Two ablations: the FSM is structural, not an authoring or clock artifact

Neither was requested; both were run because "the C was written badly" and "the clock
was too tight" are the first two objections to any result like this.

- **Relaxed clock (1.75 ns instead of 0.705 ns):** 62 control steps, 6 012 FF,
  **identical area**. A slower target does not buy a flatter datapath.
- **"HLS-friendly" rewrite** (the lane loop restructured into a ternary-select chain,
  the shape usually recommended to make HLS produce parallel hardware): **3.3× area**,
  still sequential.

Bambu schedules this into a multi-cycle FSM over a shared functional unit because that
is what its scheduler does with a loop over lanes; it does not have a mode in which the
8 lanes become 8 parallel combinational slices. Whether it can be made to emit a
single-control-step datapath at all is a genuinely open question and is left as a
follow-up.

## Verification

Both arms pass `tb/cocotb/gpu/test_vector_alu.py` **14/14**. The suite originally had
no handshake handling at all, so the HLS arm scored 1/14 until a runtime protocol branch
(the `test_hazard_unit.py` pattern) was added; expected values and assertions are
unchanged, only the sampling point moved into `ReadOnly()`. Note that this directed
suite does not exercise `ASSUMPTIONS.md` items 8 (`result_o` for branch opcodes) or 10
(`VMOV_*`), so those two spec-drift candidates remain unprobed rather than cleared.

The shim (`shim/vector_alu_hls.sv`) is wire-only — zero registers — so the 9 412
sequential cells are all Bambu's.
