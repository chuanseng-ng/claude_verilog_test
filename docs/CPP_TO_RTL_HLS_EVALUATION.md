# C++ → SystemVerilog (HLS) Flow Evaluation & RTL-Generation Approach Decision

**Date:** 2026-07-14
**Status:** Decision recorded · empirical-confirmation pilot logged as backlog (below)
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
  *or* **>20 % power** at matched function, *or* introduces any DRC/antenna violation Flow A
  did not have.
- "Competitive" = Flow B within **±5 % fmax** and **±10 % area/power** of Flow A, with 0 DRC.
- Any result between these bands is "inconclusive → widen the block set or re-tune pragmas."

**Expected result (hypothesis):** HLS regresses per the thresholds above on the FSM, is
competitive on the coalescer — which would confirm "keep hand-RTL for the control core,
reserve HLS for datapath accelerators." A surprising result (HLS competitive on the FSM)
would itself be a useful signal to revisit the recommendation.

**Deliverable:** a short PPA comparison table appended to this doc.

**Note:** this pilot is optional — the literature + this project's existing PPA profile
already support the decision above. Run only if empirical proof is wanted before committing
HLS to any future datapath accelerator.
