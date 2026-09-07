# C++ → SystemVerilog (HLS) Flow Evaluation & RTL-Generation Approach Decision

**Date:** 2026-07-14
**Status:** Decision recorded · **pilot RUN and COMPLETE — Stage 1 + Stage 2, 2026-09-07** (see "Stage 1 results" and "Stage 2 results — the PPA table" at the end)
**Scope:** Should RTL be generated via `NL → C++ (AI) → RTL (HLS tool)` instead of the
current `NL → SystemVerilog (RTL-orchestrator agents)` flow?

---

## Recommended Approach (decision)

> **Use `NL → SystemVerilog` (RTL-orchestrator agents, current flow) for the
> CPU, caches, AXI interconnect, and GPU control logic.**
>
> **Use `NL → C++ → HLS → SystemVerilog` only for *future, datapath-dominant*
> accelerators** (e.g. the Phase 6 INT8 NPU, DSP/FFT, or crypto cores) where there
> is no tuned hand-RTL to beat and dataflow HLS is strongest.

Rationale summary (see Part 2 for the per-axis discussion and per-claim citations):
control-heavy, timing-critical, cycle-accurate microarchitecture (hazard/forward unit,
cache refill FSMs, crossbar arbitration/handshake, SIMT divergence stack, warp scheduler)
is the regime where the surveyed literature and this project's own sign-off experience
indicate hand-RTL beats HLS on quality, PPA, and timing — treat this as a well-supported
working hypothesis, not a measured result for *this* RTL (that is what the pilot below
would settle). The two-stage flow also stacks two error sources (LLM spec-drift in NL→C++
*plus* HLS QoR/subset limits) and forfeits the cycle/timing control this project relied on
for sign-off (EX-stage retiming, forwarding-mux placement, per-path SDC false/multicycle
exemptions). Our current NL→SV path is strictly shorter and keeps full control. HLS's
documented wins are datapath results — e.g. a memcached dataflow pipeline reported ~70%
register reduction at comparable performance ([arXiv:1408.5387], Xilinx Vivado HLS, FPGA
target) — which is why HLS is reserved here for datapath accelerators.

---

## Part 1 — Available open-source C++/HLS → (System)Verilog tools

Survey as of **2026-07**; releases are **not pinned** below (the pilot in the backlog
section must pin exact commits/tags before any measurement). "Front-end coverage" = which
input language/subset the tool accepts; "output target" = HDL(s) it emits. Qualitative
notes ("active", "broadest front-end") are relative editorial judgments from the linked
project pages, not benchmarked scores — verify against each project at pilot time.

| Tool | Front-end | Output target | License / activity (as of 2026-07) | Notes |
|------|-----------|--------------|-------------------------------------|-------|
| **Bambu (PandA)** | C / C++ (GCC-based subset) | Verilog | GPL; repo actively maintained | General C/C++ HLS with the widest C/C++ input coverage of this set; PPA competitive *within the HLS class* per its own literature. |
| **Google XLS** | DSLX (Rust-like); C++ via `xlscc` subset | **Verilog + SystemVerilog** | Apache-2; actively developed | "Mid-level" synthesis; explicit pipeline-stage / throughput control; one source → SW model + RTL. Strongest for fixed-latency dataflow. |
| **SCCL** | SystemC (C++11 subset) | **SystemVerilog** / VHDL / FIRRTL | Open source | Clang front-end; SystemC synthesis subset; emits SystemVerilog directly. |
| **CIRCT + ScaleHLS / Calyx** | C/C++ → MLIR | **SystemVerilog** (via ExportVerilog) | Apache-2; actively developed | Infrastructure/frameworks, not a turnkey C++→RTL button; strong future direction. |
| **LegUp** | C | Verilog | Open version dated; maintained path proprietary (Microchip SmartHLS) | Historically better fuzz-reliability than early Bambu (per the reliability study cited below). |

**Takeaway:** viable open-source C++→RTL tools exist. **Multiple** emit SystemVerilog —
**SCCL** (from SystemC), **XLS** (from DSLX / `xlscc`), and **CIRCT** (via ExportVerilog);
**Bambu** and **LegUp** emit Verilog. So SystemVerilog output is *not* a differentiator; the
real axes are front-end (which C/C++ subset) and QoR. **Bambu** accepts the widest plain
C/C++ input; every tool imposes a *synthesizable subset* — none ingests arbitrary modern C++.

## Part 2 — Why not for this project's core (quality / PPA / timing)

The claims below are drawn from the cited literature and this project's own sign-off data.
Where a statement is a general finding from the literature rather than a measurement of
*this* RTL, it is framed as such — the backlog pilot is what would convert these from
supported expectations into project-specific numbers.

- **Quality:** The surveyed literature reports HLS excels at dataflow/statically-scheduled
  algorithms and is weaker than hand-RTL on control-intensive logic — the regime that
  dominates this SoC (semiengineering.com "HLS for RISC-V"; BittWare RTL-vs-HLS study).
  Independent of QoR, the two-stage flow compounds LLM spec-drift with HLS subset/QoR
  limits, and the LLM must target each tool's narrow subset (a less-trained target than
  "write SystemVerilog"). *Hypothesis for this RTL, pending the pilot.*
- **PPA:** Reliability/QoR studies place open HLS ~on par with commercial HLS on datapath
  but behind hand-RTL for control blocks (johnwickerson fuzzing-HLS study; BittWare). Our
  *measured* sign-off numbers (CPU 1418 MHz / 27.27 mW ASAP7; SoC 571 MHz / 62.9 mW) come
  from hand micro-architecture and are the concrete anchor; the expectation that HLS
  control FSMs add registers/area and miss these fmax targets is a literature-based
  hypothesis the pilot would test.
- **Timing:** HLS gives limited timing controllability (pragmas/target-period, not
  hand-placed critical paths). Full HLS RISC-V cores exist and work (HL5, arXiv/CICC'20)
  but are reported below tuned hand-RTL fmax. A regression on the paths that gate this
  design is expected but unproven for this RTL — again, the pilot's purpose.
- **Process cost:** New toolchain + subset + pragma tuning + mandatory C↔RTL equivalence
  checking (HLS tools have documented reliability bugs — johnwickerson study) — a large new
  verification surface on top of the existing cocotb/pyuvm flow.

### References
- PandA-Bambu — https://github.com/ferrandi/PandA-bambu
- Google XLS — https://github.com/google/xls
- SCCL: An open-source SystemC to RTL translator (IEEE) — https://ieeexplore.ieee.org/document/10171476/
- An Empirical Study of the Reliability of HLS Tools — https://johnwickerson.github.io/papers/fuzzingHLS.pdf
- High-Level Synthesis for RISC-V (Semiconductor Engineering) — https://semiengineering.com/high-level-synthesis-for-risc-v/
- HL5: A 32-bit RISC-V Processor Designed with HLS — https://sld.cs.columbia.edu/pubs/mantovani_cicc20.pdf
- Comparing FPGA RTL to HLS C/C++ (BittWare) — https://www.bittware.com/resources/comparing-rtl-to-hls/
- HLS Case Study: Memcached Server (~70% register reduction claim) — https://arxiv.org/abs/1408.5387
- CIRCT Verilog/SystemVerilog generation (ExportVerilog) — https://circt.llvm.org/docs/VerilogGeneration/

---

## Backlog item — Empirical confirmation pilot

> **Tracked as GitHub issue [#119](https://github.com/chuanseng-ng/claude_verilog_test/issues/119).**
> Filed on GitHub rather than beads (`bd`) because the remote beads DB is at schema v32 while
> the available `bd` is v53; writing a native `bd` issue would require migrating the shared
> schema (forces every clone to re-bootstrap), a team-wide coordination decision left to the
> maintainer. Convert to a `bd` issue later if desired.

**Title:** Empirically confirm HLS-vs-hand-RTL PPA gap on one datapath + one control block
**Type:** task · **Priority:** low (validation, not blocking) · **Phase:** 6+ exploration

**Goal:** Quantify (not just argue) the QoR gap between the two flows on an
already-signed-off block, to confirm the recommendation above.

**Method (apples-to-apples on ASAP7):**
1. Pick two poles from existing signed-off RTL:
   - **Memory coalescer** (`rtl/gpu/`, datapath-ish → HLS-favorable).
   - A **cache refill FSM** (`rtl/mem/`, control-heavy → HLS-unfavorable).
2. **Flow A (baseline):** existing hand-RTL through the current ASAP7 sign-off.
3. **Flow B:** `NL → C++ (LLM) → Bambu` (widest C/C++ FE) and/or **XLS** (SV output) →
   same `make librelane-asap7` sign-off.
4. **Verification — two independent checks, both required:**
   - **Source→RTL equivalence:** C++ ↔ generated-RTL equivalence via the HLS tool's own
     C/RTL co-simulation *or* formal equivalence (e.g. the tool's cosim harness). This is
     the check that actually validates the HLS step, and is the known gap flagged in the
     project's existing source-to-RTL-equivalence backlog item.
   - **Reference agreement:** generated RTL vs the Python reference model (`tb/models/`) as
     an independent oracle. Neither check substitutes for the other.
5. Then compare **fmax / area / power / DRC** against Flow A.

**Reproducibility — pin before measuring (else the comparison isn't apples-to-apples):**
Bambu/XLS release commit or tag; LibreLane + ASAP7 PDK revision; the exact SDC constraints
(clock period, IO delays, false/multicycle paths) used for *both* flows; PVT/process corner
(match the current ASAP7 sign-off corner); clock/reset/IO wrapper the generated block is
placed in; power-activity assumptions (VCD-driven vs default switching); and
latency/throughput normalization (HLS may pick a different cycle count — normalize on
throughput at matched fmax, and report the II/latency of each version).

**Acceptance thresholds (measurable; tune before the run if desired):**
- "Regresses noticeably" = Flow B is worse than Flow A by **>10 % fmax** *or* **>20 % area**
  *or* **>20 % power** at matched function. ~~*or* introduces any DRC/antenna violation Flow A
  did not have.~~ — **DRC clause struck, see below.**
- "Competitive" = Flow B within **±5 % fmax** and **±10 % area/power** of Flow A. ~~with 0 DRC.~~
- Any result between these bands is "inconclusive → widen the block set or re-tune pragmas."

> **⚠ The DRC/antenna axis is withdrawn for ASAP7 — struck 2026-09-07 (Stage 1, bead `cge`).**
> Bead `xy6` (closed, root-caused) established that **no ASAP7 run in this project's history has
> ever completed detailed routing**: `pnr/scripts/openroad/drt.tcl` wraps the whole
> `detailed_route` call in a bare `catch{}`, so DRT-0073/0074 pin-access failures abort routing
> and `write_views` commits the pre-route placed netlist. 100 % of recoverable runs show zero
> ROUTED nets. Bead `ocm` (open) owns the unsolved pin-access cause.
> Both arms of this pilot would hit the identical wall, so a DRC column yields **no
> discriminating signal** — it would compare two vacuous zeros. Timing/power/area survive as
> GRT-estimate-based figures that are self-consistent between arms.
> **Stage 2 must not promise a DRC column.** Revisit only if `ocm` is solved.

**Expected result (hypothesis):** HLS regresses per the thresholds above on the FSM, is
competitive on the coalescer — which would confirm "keep hand-RTL for the control core,
reserve HLS for datapath accelerators." A surprising result (HLS competitive on the FSM)
would itself be a useful signal to revisit the recommendation.

**Deliverable:** a short PPA comparison table appended to this doc.

**Note:** this pilot was optional. **It was run anyway — Stage 1 completed 2026-09-07;
see "Stage 1 results" at the end of this document.** Two of the three blocks returned
categorical results rather than PPA numbers, and one correction landed on this section's own
framing (the "datapath-ish" pole is not a datapath block). Stage 2 (P&R + the PPA table) has
not been run.

---

# Stage 1 results — the pilot was run (2026-09-07)

**Status:** Stage 1 complete. **No PPA table yet** — that is Stage 2, which measures. Stage 1
installed the tool, authored the C, generated the RTL, and proved functional equivalence.

The pilot was expected to return a PPA delta. It returned something more decisive: on the three
blocks attempted, **two of the three results are categorical rather than numeric.** Details in
`hls/*/NOTES.md`; the reproducibility pin is `hls/PROVENANCE.json`.

## What was pinned

Bambu (PandA) **2024.10**, revision `c2ba6936ca2ed63137095fea0b630a1c66e20e63-main`. Upstream ships
only a prebuilt AppImage, so it is packaged as a nix devshell (`flake.nix`, `devShells.hls`) via
`appimageTools.wrapType2` + `fetchurl` with the AppImage sha256 enforced by nix. **The flake is the
pin** — no per-machine install step, and nix refuses to build if the upstream artefact ever changes.

Target `--device-name=asap7-TC`, `--clock-period=0.705` ns (matching
`pnr/asap7/template/config.json`). Bambu bundles `asap7sc7p5t_SIMPLE_RVT_TT_nldm_201020.lib` — the
same cell library and TT corner `pnr/asap7/cpu/config.json` already uses, so Stage 2 can match the
corner exactly. Co-simulation against the flake's Verilator 5.048.

Generated Verilog is **not committed**. Bambu stamps a timestamp into a header comment of every
`.v`, so the raw digest changes every run (verified: three back-to-back runs of identical input gave
three digests, byte-identical except the `- Date …` line). `tools/eda/wrap-bambu.sh` therefore emits
a **normalized** digest, which is stable and is what `PROVENANCE.json` pins.

## Method: the reference RTL body was withheld

Each C source was authored by a fresh agent given **only** the block's natural-language spec (the
reference `.sv` header comment) and its port list, explicitly barred from reading anything under
`rtl/`. Transliterating the SystemVerilog would have measured transliteration and answered nothing.
Each block's `ASSUMPTIONS.md` records every point where the spec was silent and what was chosen —
those files are a measured output of the experiment, not paperwork.

## Results

| Block | Pole | Outcome |
|---|---|---|
| `memory_coalescer` | AXI / serialiser | Equivalent on both legs. One measured latency penalty. |
| `rv32i_hazard_unit` | control | **Form inexpressible** (combinational → 6-9 cycle FSM) **and** functional divergence, 254/2000 vectors |
| `rv32i_cache_arbiter` | control / bus arbitration | **Inexpressible — no C authored** |

Every block was checked on **two independent legs**: Bambu's own C/RTL co-simulation (which
validates the C→RTL step), and the *same, unmodified* cocotb suite run against both the hand-RTL and
the HLS arm behind a wire-only shim (which validates the C against the spec). Neither leg
substitutes for the other.

### 1. `memory_coalescer` — equivalent, with a 6× control-path latency penalty

Both legs green: cosim 5/5 vectors; the existing 5-test cocotb suite passes on both arms.

One test initially failed. Measured cause: on an empty lane mask the hand-RTL asserts `done_o` after
**1** rising edge (`IDLE → DONE` directly), the HLS version after **6** — Bambu walks all eight lane
predicates sequentially even when none fire. The test's 5-cycle bound was a testbench assumption
calibrated against the reference, not a specified requirement (the spec sets no cycle budget), so it
was rebased for **both** arms with the AXI-silence assertions untouched.

**Correction to this document's own framing:** `memory_coalescer` was named here as the
"datapath-ish → HLS-favorable" pole. It is not a datapath block. It is 214 lines of lane-walking FSM
plus AXI handshakes with zero arithmetic, and `GPU_ENABLE_COALESCE = 1'b0` means nothing is actually
coalesced — it serialises one single-beat transaction per active lane. It was kept because it is the
block that exercises Bambu's `m_axi` path and carries the real interface risk, but it never tested
the datapath hypothesis.

### 2. `rv32i_hazard_unit` — the control pole, substituted and doubly negative

Substituted for "a cache refill FSM", which turned out not to exist as a standalone module — the
refill logic is smeared across `rv32i_icache.sv` (619 lines, 5 SRAM macros) and `rv32i_dcache.sv`
(990 lines). Carving it out would have created a *new* baseline that was never signed off. The
hazard unit is 427 lines, purely combinational, and is named in this document's own control-heavy
list, so it tests the same hypothesis against real signed-off RTL.

**Result 2a — HLS cannot express the block's form.** The reference has no clock, no reset and
**zero flip-flops**. Bambu wraps every design in a start/done handshake: **9 FSM states, 50
flip-flops, 6-9 cycles per evaluation, data-dependent latency.** For a block whose job is resolving
hazards within one cycle, that is not a drop-in replacement at any clock period. This is not an
authoring artefact — rebuilding the stall/flush logic branch-free, with no priority chain at all,
produced an *identical* schedule (area within 0.3 %).

**Result 2b — spec drift, precisely localised.** Hand-RTL 28/28 spec-derived directed tests;
HLS 26/28; the 2000-vector cross-arm differential reports **254 mismatches (12.7 %)**. Root cause:
the failing vectors make the EX1b/EX1c producers *loads*, whose data is not ready, so those
forwarding tiers must be excluded; the HLS version gates only the EX2 tier on `mem_rd`.

The sharp part: **all 254 mismatches land on forwarding outputs. Not one stall, flush or load-use
output ever mismatched.** The 9-item priority ladder — which this document's source spec states
explicitly and completely — transferred perfectly. The drift is confined entirely to what the spec
left to inference. **Spec-stated behaviour transferred; spec-implied behaviour did not.**

The divergence was deliberately not fixed. It is the measurement. It was also *predicted in advance*
by the C author in `ASSUMPTIONS.md`, including the observation that it would "only ever fail under
random-vector equivalence, never under a trace" — which is exactly what happened.

### 3. `rv32i_cache_arbiter` — outside the expressible domain

No C was authored, and none should be. Bambu emits AXI **masters** only, and only as a side-effect
of pointer dereference; asking for a slave is rejected (`error: Invalid HLS interface mode` for
`mode = s_axilite`), the shipped clang plugin contains no AXI-slave mode string at all, and
`--generate-interface` accepts only `MINIMAL` / `INFER` / `WB4`. Under the first two every top
module carries `start_port`/`done_port` — the C execution model made structural. The arbiter is
permanently reactive, with three incoming AXI channel sets and grant-hold-until-`RLAST`; there is no
invocation to map onto. Full evidence, including a probe of the one slave-shaped option (`WB4`, a
memory-mapped *control* interface in Wishbone), is in
`hls/mem/rv32i_cache_arbiter/INEXPRESSIBLE.md`.

Forcing it would have required a hand-written shim containing the grant register, priority encoder,
burst-hold logic and response routing — the entire design — around an HLS core contributing nothing.
That comparison would be hand-RTL versus hand-RTL, reported as hand-RTL versus HLS.

## What this does to the recommendation

The recommendation at the top of this document **stands, and is strengthened on its control-logic
half.** For that half the claim can now be stated more strongly than the literature supported:

> Not "HLS produces worse control logic" but, for the two control blocks attempted, **"HLS cannot
> express these blocks at all"** — one because a combinational block becomes a multi-cycle FSM, the
> other because the interface has no representation. Neither is a scheduling or pragma-tuning
> problem; both follow from the C execution model, so neither is fixed by re-tuning.

**The datapath half of the recommendation remains untested.** Neither measured block is a datapath
block, and the one named as such is not. Nothing here supports or undermines reserving HLS for
datapath accelerators — that hypothesis is exactly as evidenced as it was before this pilot ran.
If it matters, a genuine datapath pole (`rtl/gpu/vector_alu.sv`, 8 × 32-bit multiply plus
shift/logic) would test it.

Two secondary findings worth carrying into any future HLS work:
- **Ordinary C factoring is not available.** Bambu refuses to inline `static` helpers — it made a
  shared helper a 1-resource submodule with internal DISTRAM and *failed the build*
  (`clock constraint too tight: BRAMs for this device cannot run so fast`).
  `__attribute__((always_inline))` did not change the decision; only preprocessor macros worked.
- **The output is structurally explosive.** Bambu instantiates ~550 modules for one small block.
  Verilator then emits a 1.2 MB symbol-table constructor on which g++ spun at 99.9 % CPU for
  32 minutes at `-O0`. `sim/Makefile` carries `--output-split 500` and `NO_TRACE=1` on the HLS arms
  for this reason.

## Stage 2 — what it may and may not claim

- **No DRC column.** See the struck threshold above (beads `xy6` / `ocm`).
- Bambu's own estimates (coalescer 820 FF / area 352 744; hazard unit 50 FF / area 1 791 535) are
  **not comparable to hand-RTL** — they cover the whole generated hierarchy including Bambu's AXI
  master adapter, which the hand-RTL has no equivalent of. Stage 2 must synthesise both arms for
  real and state the counting boundary before quoting anything.
- Both shims are wire-only (zero registers), so Flow B's area needs no separate shim line.
- Normalize on throughput per the pinning list above: the hand-RTL cycle counts are 1 (coalescer,
  empty mask) and **0** (hazard unit, combinational) against 6 and 6-9 respectively.

---

# Stage 2 results — the PPA table (2026-09-07)

**Status:** Stage 2 complete (bead `r8r`). This is the comparison table this document names as the
pilot's deliverable. Reproducibility pin: `hls/PROVENANCE.json`; configs under
`pnr/asap7/{coalescer,hazard}_{rtl,hls}/`; collector `tools/verif/collect_r8r_ppa.py`.

## Method

Four ASAP7 runs — two hand-RTL, two Bambu-HLS — **to `OpenROAD.STAPrePNR` only**. That step is
where area, timing *and* power all first appear, so placement, CTS and routing are needed for none
of them. All four use the same clock period (705 ps), the same corner (`nom_tt_025C_0p7V`), the same
synthesis strategy and the same skip list; a diff of the four `config.json` differs **only** in
`DESIGN_NAME`, `VERILOG_FILES` and the clock port. Both HLS arms are synthesised *with* their
wire-only shim, so all four have identical port lists.

## The table

| Block | Flow | Area µm² | Cells | Critical path ps | fmax MHz | Power mW | Undriven wires |
|---|---|---|---|---|---|---|---|
| `memory_coalescer` | hand-RTL | 569.74 | 4219 | 1620.15 | 617.2 | 4.469 | **0** |
| `memory_coalescer` | **HLS** | 605.22 | 4814 | **1059.09** | **944.2** | 4.845 | **9** |
| `rv32i_hazard_unit` | hand-RTL | 23.17 | 233 | **149.3** (combinational) | n/a | **0.018** | **0** |
| `rv32i_hazard_unit` | **HLS** | 26.55 | 233 | 302.53 (per cycle) | 3305.5 | **0.182** | **28** |

`rv32i_hazard_unit`'s hand-RTL arm is purely combinational — no clock, no registers, zero
register-to-register paths — so "fmax" is undefined for it. It is timed against a **virtual clock**
with a zero I/O budget, and its number is the input-to-output path delay (705 − 555.7 slack).

## Result 1 — the coalescer: HLS *won* on speed, and that was not the hypothesis

Against this document's own thresholds (>10 % fmax or >20 % area/power = "regresses"; ±5 % fmax and
±10 % area/power = "competitive"):

- **Critical path −34.6 %** (1620 → 1059 ps), i.e. **fmax +53 %**, in the HLS arm's favour.
- **Area +6.2 %**, **power +8.4 %** — both inside the ±10 % "competitive" band.

So on raw PPA the HLS coalescer is **better than competitive**. The reason is visible in the
structure: Bambu split the lane walk across more, shorter cycles, while the hand-RTL keeps a longer
combinational path through the 8-lane mux and its AXI FSM.

**This does not overturn the recommendation, and the reason is throughput.** A shorter clock period
bought with more cycles per transaction is only a win if the cycle count holds, and it does not:
on the empty-mask case the hand-RTL completes in **1** rising edge and the HLS arm in **6**.
Per-transaction latency, not fmax, is what this block's consumer sees.

*Honest gap:* a full 8-lane-transaction cycle count for the hand-RTL arm was **not measured**, so
the throughput comparison is anchored only on the empty-mask case plus Bambu's own cosim average of
23 cycles/vector. A rigorous throughput ratio needs that measurement; it is not claimed here.

## Result 2 — the hazard unit: regression on every axis that matters

- **Power ×10.1** (0.018 → 0.182 mW, +911 %) — far outside the >20 % "regresses" threshold, and the
  single starkest number in this pilot.
- **Area +14.6 %** — past the ±10 % competitive band.
- **Latency ×12.2 – ×18.2**: 149.3 ps of combinational delay versus 302.53 ps × 6–9 cycles =
  1815–2723 ps for the same evaluation.

**Verdict: regresses**, decisively. This is the block Stage 1 already showed to be *inexpressible in
form* — a zero-flip-flop combinational cloud becoming a 9-state, 33-flop FSM — and the PPA numbers
now put a cost on that: an order of magnitude more power and over an order of magnitude more
latency, for logic the pipeline needs resolved within a single cycle.

## Result 3 — netlist quality: undriven wires, only in the HLS arms

Yosys' own `CHECK` pass reports wires that are used but never driven:

| | hand-RTL | HLS |
|---|---|---|
| `memory_coalescer` | 0 | **9** |
| `rv32i_hazard_unit` | 0 | **28** |

They are `OUT_UNBOUNDED_*` functional-unit outputs plus an undriven `s_start_port0`. Both hand-RTL
arms are clean. The flow's `Checker.YosysSynthChecks` had to be skipped **on all four** (to keep the
flow identical) for the HLS arms to synthesise at all; the skip is documented in `pnr/Makefile` and
this asymmetry is reported rather than hidden by it.

## What must not be read into this table

- **No DRC column, by construction.** Struck in Stage 1 (beads `xy6`/`ocm`): no ASAP7 run in this
  project has ever completed detailed routing, so both arms would compare two vacuous zeros. These
  are partial runs and never route.
- **Pre-placement, zero-parasitic STA.** Absolute fmax is optimistic for all four. The *comparison*
  holds because every arm is treated identically, but these are not sign-off numbers.
- The 233-cell count matching across the two hazard arms is a coincidence, not an error — the areas
  and flop counts differ (the HLS arm has 33 flip-flops; the hand-RTL arm has none).

## Effect on the recommendation

The recommendation at the top of this document **stands**, now with numbers behind its control-logic
half rather than only literature: on the control block, HLS costs **10× the power and 12–18× the
latency**, on top of Stage 1's finding that it cannot reproduce the block's combinational form at
all.

The coalescer result is the honest complication, and it is worth stating plainly: **on an
AXI-serialiser workload, HLS produced a shorter critical path at ~6 % area cost.** That is a point
in HLS's favour on a block that is *not* control-dominated in the hazard-unit sense, and it is
consistent with reserving HLS for throughput-oriented dataflow rather than for cycle-critical
control.

**The datapath half of the recommendation remains untested** — neither measured block is a datapath
block (see the Stage 1 correction above). Bead `gg8` tracks `rtl/gpu/vector_alu.sv` as the block
that would actually test it.
