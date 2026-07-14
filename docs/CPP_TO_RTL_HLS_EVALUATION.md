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

Rationale summary: control-heavy, timing-critical, cycle-accurate microarchitecture
(hazard/forward unit, cache refill FSMs, crossbar arbitration/handshake, SIMT
divergence stack, warp scheduler) is where hand-RTL consistently beats HLS on quality,
PPA, and timing. The two-stage flow also stacks two error sources (LLM spec-drift in
NL→C++ *plus* HLS QoR/subset limits) and forfeits the cycle/timing control this project
relied on for sign-off (EX-stage retiming, forwarding-mux placement, per-path SDC
false/multicycle exemptions). Our current NL→SV path is strictly shorter and keeps full
control. HLS's documented wins are datapath results (e.g. ~70% register reduction on a
memcached dataflow pipeline), which is why it is reserved for datapath accelerators.

---

## Part 1 — Available open-source C++/HLS → (System)Verilog tools

| Tool | Front-end | Output | License | Notes |
|------|-----------|--------|---------|-------|
| **Bambu (PandA)** | C / C++ (subset) | Verilog | GPL, active | Best-maintained general C/C++ HLS; PPA competitive *within the HLS class*; broadest C++ front-end. |
| **Google XLS** | DSLX (Rust-like); C++ via `xlscc` subset | **Verilog + SystemVerilog** | Apache-2, active | "Mid-level" synthesis; explicit pipeline-stage / throughput control; one source → SW model + RTL. Best for fixed-latency dataflow. |
| **SCCL** | SystemC (C++11 subset) | **SystemVerilog** / VHDL / FIRRTL | Open source | Only tool emitting idiomatic SystemVerilog; Clang front-end; SystemC synthesis subset. |
| **CIRCT + ScaleHLS / Calyx** | C/C++ → MLIR | SystemVerilog (ExportVerilog) | Apache-2, active | Infra, not turnkey; strong future direction. |
| **LegUp** | C | Verilog | Open version dated; maintained path is proprietary (Microchip SmartHLS). | Historically better fuzz-reliability than early Bambu. |

**Takeaway:** viable open-source C++→RTL tools exist. Only **SCCL** natively targets
idiomatic SystemVerilog; **XLS** emits SV but from DSLX (C++ via `xlscc` subset);
**Bambu** has the broadest C++ front-end but emits Verilog. Each imposes a *synthesizable
subset* — none ingests arbitrary modern C++.

## Part 2 — Why not for this project's core (quality / PPA / timing)

- **Quality:** HLS excels at dataflow/statically-scheduled algorithms; it is consistently
  weaker than hand-RTL on control-intensive logic, which dominates this SoC. The two-stage
  flow compounds LLM spec-drift with HLS subset/QoR limits, and the LLM must target each
  tool's narrow subset (a less-trained target than "write SystemVerilog").
- **PPA:** Studies place open HLS ~on par with commercial HLS on datapath but behind
  hand-RTL for control blocks. Our sign-off numbers (CPU 1418 MHz / 27.27 mW ASAP7; SoC
  571 MHz / 62.9 mW) come from hand micro-architecture; HLS control FSMs typically add
  registers/area and rarely hit these fmax targets.
- **Timing:** HLS gives limited timing controllability (pragmas/target-period, not
  hand-placed critical paths). Full HLS RISC-V cores exist (e.g. HL5) and work, but land
  well below tuned hand-RTL fmax. Expect a regression on the paths that gate this design.
- **Process cost:** New toolchain + subset + pragma tuning + mandatory C↔RTL equivalence
  checking (HLS tools have documented reliability bugs) — a large new verification surface
  on top of the existing cocotb/pyuvm flow.

### References
- PandA-Bambu — https://github.com/ferrandi/PandA-bambu
- Google XLS — https://github.com/google/xls
- SCCL: An open-source SystemC to RTL translator (IEEE) — https://ieeexplore.ieee.org/document/10171476/
- An Empirical Study of the Reliability of HLS Tools — https://johnwickerson.github.io/papers/fuzzingHLS.pdf
- High-Level Synthesis for RISC-V (Semiconductor Engineering) — https://semiengineering.com/high-level-synthesis-for-risc-v/
- HL5: A 32-bit RISC-V Processor Designed with HLS — https://sld.cs.columbia.edu/pubs/mantovani_cicc20.pdf
- Comparing FPGA RTL to HLS C/C++ (BittWare) — https://www.bittware.com/resources/comparing-rtl-to-hls/

---

## Backlog item — Empirical confirmation pilot

> **Intended tracker:** beads (`bd`). Logged here as a doc because the remote beads DB is
> at schema v32 while the available `bd` is v53; writing a native issue would require
> migrating the shared schema (forces every clone to re-bootstrap), which is a team-wide
> coordination decision left to the maintainer. **Action for maintainer:** create a `bd`
> issue mirroring the block below, then this section can be trimmed.

**Title:** Empirically confirm HLS-vs-hand-RTL PPA gap on one datapath + one control block
**Type:** task · **Priority:** low (validation, not blocking) · **Phase:** 6+ exploration

**Goal:** Quantify (not just argue) the QoR gap between the two flows on an
already-signed-off block, to confirm the recommendation above.

**Method (apples-to-apples on ASAP7):**
1. Pick two poles from existing signed-off RTL:
   - **Memory coalescer** (`rtl/gpu/`, datapath-ish → HLS-favorable).
   - A **cache refill FSM** (`rtl/mem/`, control-heavy → HLS-unfavorable).
2. **Flow A (baseline):** existing hand-RTL through the current ASAP7 sign-off.
3. **Flow B:** `NL → C++ (LLM) → Bambu` (broadest C++ FE) and/or **XLS** (SV output) →
   same `make librelane-asap7` sign-off.
4. Verify functional equivalence of Flow B output vs the Python reference model
   (`tb/models/`), then compare **fmax / area / power / DRC** against Flow A.

**Expected result:** HLS regresses noticeably on the FSM, is competitive on the coalescer
— confirming "keep hand-RTL for the control core, reserve HLS for datapath accelerators."

**Deliverable:** a short PPA comparison table appended to this doc.

**Note:** this pilot is optional — the literature + this project's existing PPA profile
already support the decision above. Run only if empirical proof is wanted before committing
HLS to any future datapath accelerator.
