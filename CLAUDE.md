# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-phase RV32I RISC-V microprocessor + GPU-lite SoC project.

**Current Phase**: Phase 5 (SoC Integration) — ✅ COMPLETE (2026-06-24). M1–M12 done; M11 ASAP7 SoC P&R signed off at **571 MHz / 62.9 mW / 520×520 µm / 65.6 % util / 0 DRC / 0 antenna** (run 14, sv2v frontend; PDN = benign tap-cell artifact). See `docs/PHASE5_RUN_HISTORY.md`.

**Status**: Phase 4 complete (2026-05-27, all GPU tests green; ASAP7 GPU sign-off 571 MHz / 262 mW); Phase 3 complete (2026-05-21, 139/139 total, ASAP7 1418 MHz sign-off); Phase 2 complete (2026-03-08, 75 MHz on Sky130).

**Target**: Build a complete SoC with CPU, GPU, caches, and peripherals through incremental phases.

Per-phase completion records → [`docs/readme/PHASE_HISTORY.md`](docs/readme/PHASE_HISTORY.md) and [`docs/PHASE_STATUS.md`](docs/PHASE_STATUS.md).

## Project Phases

See `docs/ROADMAP.md` for the complete phase plan and `docs/PHASE_STATUS.md` for current status.

| Phase | Scope | Status |
| :---- | :---- | :----- |
| 0 — Foundations | Specs + Python reference models (no RTL) | ✅ 2026-01-18 |
| 1 — Minimal RV32I core | Single-cycle; AXI4-Lite master; APB3 debug | ✅ 2026-02-13 |
| 2 — Pipelined CPU | 5-stage in-order; RV32I+Zicsr; M-mode interrupts; hazard/forwarding | ✅ 2026-03-08 (75 MHz Sky130) |
| 3 — Memory system | L1 I$ + D$ (4 KB each, direct-mapped, write-back); FENCE.I | ✅ 2026-05-21 (ASAP7 1418 MHz) |
| 4 — GPU-Lite SIMT | 8-lane warps, single CU, round-robin, 1-level divergence, 16 KB shared mem | ✅ 2026-05-27 (ASAP7 571 MHz) |
| 5 — SoC integration | CPU + GPU + DMA + AXI4 crossbar + UART/SPI/timer/IRQ + behavioral SRAM | ✅ 2026-06-24 (ASAP7 SoC 571 MHz / 62.9 mW sign-off) |
| 6+ — IP expansion | GPIO/I2C/PWM/WDT/TRNG/AES-SHA peripherals; INT8 NPU; tech-node exploration | ⏸️ Future |
| 7 — Mixed-Signal PLL | Dual-PDK charge-pump PLL (ASAP7 indicative + Sky130 real DRC/LVS) via analog-design agents; AMS RNM integrated as SoC clock source | done (M-a..M-c) |

### Phase 4: GPU-Lite SIMT Engine (frozen)

- **ISA**: Custom 32-bit vector encoding — VADD, VSUB, VMUL, VAND, VOR, VSLL, VLD, VST, VBEQ, VBNE, VJMP, VRET, VSYNC
- **Execution**: Single compute unit; 8 SIMD lanes; 8 warps max; 64 total threads
- **Register file**: 32 registers × 8 threads per warp (1 KB)
- **Divergence**: Single-level SIMT stack with per-lane active mask; round-robin scheduler
- **Shared memory**: 16 KB scratchpad, 32 banks
- **Memory**: AXI4 master (burst) + memory coalescer (8-lane → fewer AXI4 bursts)
- **Coherency**: Software-managed — CPU flushes D-cache before launch, invalidates after completion. No HW coherence.
- **Spec**: `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md`

### Phase 5: SoC Integration (in progress)

- **Interconnect**: AXI4 crossbar (data fabric) + AXI-Lite bus (control/config)
  - AXI4 masters: CPU D-cache (upgraded to burst), GPU, DMA engine
  - AXI4 slave: behavioral SRAM controller (no DRAM refresh)
  - AXI-Lite slaves: GPU/DMA config registers, UART, SPI, timer, IRQ controller
- **Cache upgrade**: Phase 3 refill FSMs upgraded from 4 sequential AXI4-Lite beats to AXI4 burst transactions
- **DMA engine**: Descriptor queue, AXI4 master, interrupt output to CPU
- **Memory model**: Behavioral AXI4-slave SRAM (no DRAM refresh logic)
- **Power domains**: PD_CPU, PD_GPU, PD_SRAM, PD_PERIPH (clock + power gating per `UPF_POWER_SPEC.md`)
- **Performance counters**: CSR-mapped — cycle count, instructions retired, branch mispredictions, I$/D$ miss counts, active warps, warp stall cycles, divergence events
- **Roadmap**: `docs/PHASE5_SOC_INTEGRATION_PLAN.md` (12 milestones M1–M12, golden spec)

## Key Documentation

**Always refer to these specifications** (do not rely on non-existent RTL):

### Architecture & Design

| Document | Purpose |
| :------- | :------ |
| `docs/ROADMAP.md` | High-level project plan and phases |
| `docs/PHASE_STATUS.md` | Current project status and next steps |
| `docs/design/PHASE0_ARCHITECTURE_SPEC.md` | CPU architectural requirements (Phase 0) |
| `docs/design/PHASE1_ARCHITECTURE_SPEC.md` | CPU implementation spec (Phase 1) - ✅ Complete |
| `docs/design/PHASE2_ARCHITECTURE_SPEC.md` | Pipelined CPU spec (Phase 2) - ✅ Complete |
| `docs/design/PHASE3_ARCHITECTURE_SPEC.md` | Cache architecture spec (Phase 3) - ✅ Approved |
| `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md` | GPU architecture spec (Phase 4) — frozen ISA/execution model |
| `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` | Phase 3 closure + Phase 4 implementation plan (golden spec) |
| `docs/PHASE5_SOC_INTEGRATION_PLAN.md` | Phase 5 SoC integration roadmap — 12 milestones M1–M12 (golden spec) |
| `docs/design/RTL_DEFINITION.md` | Interface signal definitions |
| `docs/design/MEMORY_MAP.md` | Address space and register map |
| `docs/design/REFERENCE_MODEL_SPEC.md` | Python reference model API |

### Physical Design

| Document | Purpose |
| :------- | :------ |
| `docs/design/OPENROAD_FLOW_SPEC.md` | Complete OpenROAD flow documentation |
| `docs/design/UPF_POWER_SPEC.md` | Power intent and UPF specification |
| `docs/design/SDC_TIMING_SPEC.md` | Timing constraints and STA guidelines |
| `pnr/README.md` | Physical design directory structure |

### Verification & Fixes

| Document | Purpose |
| :------- | :------ |
| `docs/verification/VERIFICATION_PLAN.md` | Verification strategy (RTL + physical design) |
| `docs/RANDOM_TESTS_STATUS.md` | Random instruction test results and guide |
| `fixes/FIXES_INDEX.md` | ⭐ Central reference for all RTL bug fixes |

### README detail set

`docs/readme/` holds the deep content split out of the root README: `PHASE_HISTORY.md`, `QUICK_START.md` (build/run commands per phase), `SUPPORTED_INSTRUCTIONS.md`, `DEBUG_INTERFACE.md` (APB3 register map), `PROJECT_STRUCTURE.md` (full directory tree).

### HDL Property Graph (`hdl-kgraph`)

`.hdl-kgraph/graph.db` is a Kùzu property graph of the HDL design (SystemVerilog/Verilog/VHDL), extracted by `hdl-kgraph`. As of 2026-06-04 (commit `1c08229`): **2150 nodes, 22473 edges, 275 files** (verilog, python, bash). Edges carry a confidence score: 1.0 = syntactically resolved, 0.8 = unique cross-file name match, 0.6 = ambiguous match, 0.4 = naming heuristic. Unresolved references appear as stub nodes flagged `unresolved`.

Query it via the **`hdl-kgraph` MCP server** (read-only) — prefer this over Grep/Glob for HDL structure questions:

| Tool | Use when |
| ---- | -------- |
| `get_hierarchy` / `find_module` | Orient: module tree, find a module by name |
| `who_instantiates` / `port_map` | Find parents of a module; inspect port connections |
| `find_signal_drivers` | Trace what drives a signal |
| `impact_of_change` | Blast radius of editing a module/signal |
| `clock_domains` / `uvm_topology` | CDC analysis; UVM testbench structure |
| `search_nodes` | Find nodes by name/keyword |

Rebuild after RTL changes: `hdl-kgraph build` / `hdl-kgraph update`.

## Technology Node Strategy

Three nodes are supported by the existing `pnr/Makefile`. Use the right node for the right goal:

| Node | Makefile target | Config status | Realistic CPU freq | Fabricatable | Best use |
|------|----------------|---------------|-------------------|--------------|----------|
| **Sky130 130nm** | `librelane-sky130`, `docker-run` | ✅ Complete | 75–100 MHz | ✅ Yes (SkyWater MPW) | Functional sign-off; tape-out candidate |
| **FreePDK45 / NanGate45 45nm** | `librelane-nangate45` | ✅ Complete (`pnr/freepdk45/`) | 150–250 MHz | No (predictive) | First non-Sky130 exploration; SRAM macros available |
| **ASAP7 7nm FinFET** | `librelane-asap7` | ✅ Complete (`pnr/asap7/`); Run 43 signoff 2026-05-20 | **1418 MHz achieved (Run 43)** | No (predictive) | Phase 2+3 RTL PPA sign-off completed at 1418 MHz / 27.27 mW / 3 844 µm² |

### Sky130 real DRC/LVS sign-off (GH epic #102, Stages 1–2 complete 2026-07-31)
Sky130 is the **only** node in this project with genuine physical verification — ASAP7 skips Magic/KLayout/Netgen entirely (predictive PDK) and FreePDK45 has them permanently blocked.

- **Stage 1** — CPU standalone (`pnr/sky130/cpu/`): KLayout DRC 0, Netgen LVS MATCH, +0.366 ns setup @ 75 MHz. Magic DRC 27.7 M is a waived PDK artifact — 100 % of violations sit inside SRAM macro footprints (bead `45a`).
- **Stage 2** — CPU macro + peripherals SoC, no GPU (`pnr/sky130/soc/`): LVS PASSED, routing DRC 0, PDN 0, hold clean, 40 MHz, nom_tt 37.63 mW, die 6700 × 3100 µm. Residual gates, neither open work: ss setup fail (`ujv`, deferred host-blocked), antenna 140/120 (`58q`, closed as an accepted trade-off against hold).
- ⚠️ **Stage-2 timing is typical-corner (nom_tt) only.** The SRAM macro is characterized at TT alone, so "clean at 9 corners" means 9 corner *labels* backed by one macro model. Physical gates (LVS/DRC/PDN) are unaffected. Per-corner SRAM characterization is host-blocked (~80–95 h SPICE; bead `o1i`).
- **Stages 3–4** (GPU, GH #105/#106): host-gated on ≥32 GB RAM + ~500 GB scratch. GPU stays ASAP7-indicative.
- Detail → `docs/SKY130_REAL_DRC_LVS_EVALUATION.md` §7.

### Sky130 PPA ceiling (assessed 2026-03-28)
Sky130 130nm is frequency-limited by cell drive strength and clock tree skew. The realistic ceiling for this pipeline topology is **~100–120 MHz** with all optimisations applied — not the 200–500 MHz originally targeted.

| Technique | Gain | Effort |
|-----------|------|--------|
| Switch to `sky130_fd_sc_hs` (high-speed cell library) | +10–30 MHz | Low — Makefile config change |
| EX-stage retiming (split ALU + branch-compare) | +15–25 MHz | Medium — re-verify forwarding paths |
| SDC multi-cycle exemptions for CSR/debug paths | +5–10 MHz | Low — SDC annotation only |
| Floorplan: place forwarding mux adjacent to ALU | +5–10 MHz | Medium — P&R iteration |
| **Combined ceiling** | **~100–120 MHz** | |

### FreePDK45/NanGate45 (ready to run)
`pnr/freepdk45/` is fully configured: `config.json` (2.5 ns / 400 MHz target), SRAM macros (`sram_1rw_256x32_freepdk45` with LEF/LIB/GDS), `macro_placement.cfg`, `pdn.tcl`, `freepdk45.sdc`, `freepdk45.upf`. Run with `make librelane-nangate45`. Expected Phase 2 result: 150–250 MHz, ~8–10× logic density vs Sky130.

### ASAP7 (Phase 2+3 sign-off achieved at Run 43, 2026-05-20)
`pnr/asap7/` is fully configured and signed off: `config.json` (705 ps / 1418 MHz, CTS clustering 8/10, density 50 %), `constraints/asap7.sdc` (single-period clock, hold/setup uncertainty 10/15 ps, SRAM ICG `gclk_sram` generated clock + false-paths), `macro_placement.cfg`, `pdn.tcl`, `sram_1rw_256x32_asap7_TT_0p7V_25C.lib` (RVT TT 0.7 V / 25 °C). Run with `make librelane-asap7`. Phase 2+3 PPA (no perf counters): **1418 MHz fmax, 27.27 mW power, 3 844 µm² stdcell, 0 DRC, 0 antenna, +5.97 ps setup slack, +22.54 ps hold slack** at run `pnr/asap7/runs/RUN_2026-05-20_06-27-10/`. **Phase 5 M7 update (2026-06-02):** adding the perf-monitoring CSRs lowers the standalone CPU sign-off to **1282 MHz (780 ps, +24 ps setup, +28 ps hold, 24.38 mW, 4 058 µm²; achievable ~1323 MHz)** at run `pnr/asap7/cpu/runs/RUN_2026-06-02_20-37-12/` — the 1418 MHz number does not hold with M7 (limiter = 836-fanout counter-write-enable cone). Moot for the SoC (GPU-governed ~571 MHz). `pnr/asap7/cpu/config.json` + `constraints/asap7.sdc` are now at 780 ps. See `docs/ASAP7_RUN_HISTORY.md` for the full campaign history.

## Frequently Used Commands

Build/run commands for every phase live in [`docs/readme/QUICK_START.md`](docs/readme/QUICK_START.md). Quick entry points:

```bash
# Phase 0 reference-model tests
cd tb/tests && pytest -v

# Cache sims (Phase 3)
cd sim && make phase3_all

# OpenROAD back-end flow
cd pnr && make all          # synth → floorplan → place → cts → route → sta → power
cd pnr && make report_summary
```

Commit with the `[Category]` convention (see below). Use `rtk`-prefixed commands for token-efficient output (see RTK section).

**Analog/mixed-signal flow (Phase 7+)**: the `analog` nix devshell provides the open analog toolchain (ngspice / xschem / magic / klayout / netgen) — enter it with `nix develop ~/Downloads/Github/librelane#analog` (OpenVAF is not in nixpkgs → ngspice-behavioral fallback). The analog flow state lives in `analog/pll_clkgen/{,sky130}/design_state.json` — **separate from the digital `design_state.json`** at repo root. Full-SoC AMS cosim (RNM PLL through `Vtop`) needs `MAKEFLAGS=-j2` (OOM on a 15 GiB host otherwise) with `SIM_BUILD` routed to `/nobackup`. See `docs/PHASE7_MIXED_SIGNAL_PLL_PLAN.md`.

## Project Structure

Top level: `rtl/` (`cpu/`, `gpu/`, `mem/` caches, `periph/`, `soc/`), `tb/` (`models/` Python + `cocotb/`), `docs/` (specs + `readme/` detail set), `pnr/` (physical design), `sim/`, `micro_p/` (archived Phase 1).

Full annotated directory tree → [`docs/readme/PROJECT_STRUCTURE.md`](docs/readme/PROJECT_STRUCTURE.md).

## Key Design Decisions (From Specifications)

**Phase 1 CPU**:

- Single-cycle execution with AXI stalls for memory operations
- Unified AXI4-Lite bus for instruction fetch and data access
- x0 register hardwired to zero (per RV32I spec)
- EBREAK instruction triggers CPU halt; debug writes only allowed when halted
- Only illegal instruction traps supported (no interrupts in Phase 1)
- Naturally aligned memory accesses only (misaligned = trap)

**Phase 4 GPU**:

- SIMT execution model (8 lanes per warp); single compute unit
- Round-robin warp scheduling; one-level divergence handling
- No cache coherence with CPU; memory coalescing when possible

**Sky130 frequency ceiling**: ~100–120 MHz maximum for this CPU pipeline topology (see Technology Node Strategy). PDK limitation — not an RTL issue. For higher frequencies, target FreePDK45/NanGate45 (150–250 MHz) or ASAP7 (**1418 MHz demonstrated** at Run 43, 2026-05-20).

**Phase 5 SoC — Locked Architecture Decisions** (confirmed 2026-03-28):

1. **Cache line size**: 16 bytes locked for Phase 3. Revisit 32-byte lines only if/when an L2 cache is added.
2. **Cache associativity**: Direct-mapped locked. **M10 RESOLVED (2026-06-21): stays direct-mapped.** A 2-way D$ was prototyped + benchmarked (`experiment/dcache-2way`): it eliminates synthetic K=2 conflict misses (153/kI→0) but representative firmware (CoreMark, 232 B working set) fits L1 with 18× margin and shows no conflict pressure — so 2-way is not adopted (adds ~100–200 ps hit-path mux for no real benefit). See `docs/M10_L2_DECISION_ANALYSIS.md`.
3. **AXI4 burst upgrade**: Phase 3 refill FSMs use 4 sequential AXI4-Lite transactions. These are upgraded to AXI4 burst mode during Phase 5 SoC integration — do not change Phase 3 FSMs before then.
4. **L2 cache**: Not in Phase 5 scope. **M10 RESOLVED (2026-06-21): NO-GO.** Benchmarking (`sw/bench/` sweep/conflict/CoreMark on `soc_top`) found the L1 capacity wall (>4 KB) is synthetic-only; representative firmware fits the 4 KB L1; the GPU carries bulk data. No real L1 bottleneck → no L2. Revisit only if a future on-core workload sustains >4 KB working sets. See `docs/M10_L2_DECISION_ANALYSIS.md`.
5. **DRAM controller**: Use behavioral AXI4-slave SRAM model for Phase 5. Real DRAM controller (with refresh) is a Phase 6+ stretch goal only if tape-out is targeted.

## Reference Model (Python)

Python reference models for CPU and GPU live in `tb/models/`: `rv32i_model.py` (CPU instruction-accurate), `gpu_kernel_model.py` (GPU SIMT), `memory_model.py`, `cache_model.py` (DirectMappedCache). See `docs/design/REFERENCE_MODEL_SPEC.md` for the complete API.

```python
from tb.models.rv32i_model import RV32IModel
cpu = RV32IModel()
result = cpu.step(0x00000093)  # addi x1, x0, 0
assert result['rd'] == 1
```

## Verification Strategy

- **Phase 0**: Python reference models, pytest unit tests, cross-validate vs RISC-V spike, cocotb infra.
- **Phase 1+**: cocotb interface drivers, pyuvm sequences/scoreboards, RTL-vs-model comparison, 10k+ random instructions.

See `docs/verification/VERIFICATION_PLAN.md` for the phase-by-phase plan. Per-phase completion history → [`docs/readme/PHASE_HISTORY.md`](docs/readme/PHASE_HISTORY.md).

### Agent delegation policy (user-mandated)

- RTL design → `chip-design-rtl:rtl-design-orchestrator`
- Verification (cocotb suites, coverage, regression) → `chip-design-verification:verification-orchestrator`
- LibreLane / physical design → `chip-design-pd:physical-design-orchestrator` (sub-delegated to specialists)

Do NOT hand-write RTL or run PD/verif inline when a matching orchestrator exists.

## Current Workflow (Phase 5 — SoC Integration)

Legend: ✅ done · 🚧 in progress · ⏸️ not started. Milestone status (M1–M12) tracked in `docs/PHASE5_SOC_INTEGRATION_PLAN.md`.

1. ✅ **AXI4 interconnect** (M1/M3): `axi4_crossbar.sv`, `axi_lite_interconnect.sv`, `axi_lite_register_bank.sv`; Phase 3 refill FSMs upgraded to AXI4 burst (M2)
2. ✅ **Peripherals + DMA** (M4/M5): UART, SPI, timer, interrupt controller, DMA engine in `rtl/periph/`
3. ✅ **SRAM controller** (M6): behavioral AXI4-slave in `rtl/soc/sram_controller.sv`
4. ✅ **SoC top integration** (M8): CPU + GPU + DMA + peripherals wired in `rtl/soc/soc_top.sv` (+ `boot_rom.sv`)
5. ✅ **Performance counters** (M7): CSR-mapped + AXI-Lite GPU stats (CPU re-sign-off 1282 MHz)
6. ✅ **SoC verification** (M9): boot 100/100; DMA+UART+SPI loopback; SW coherency (D$ flush→GPU→D$ inval); CPU-GPU IRQ-driven integration; DUT-side boot SRAM check. Found+fixed 2 RTL bugs (D-cache MMIO caching `go9`; axi4_crossbar AR/AW handshake+arbitration `7fs`). `soc_all` 73/73 at M9 (142/142 as of 2026-08-01, after the PMU epic + GH #91 async_axi_fifo).
7. ✅ **Full regression**: CPU rollup + GPU + cache green; **1M+ cycle SoC stress (1,079,867 cyc, 0 fail)** + CPU/GPU benchmarks (M9 `pgf`)
8. ✅ **L2 cache evaluation** (M10): benchmarked → **NO-GO** (no L2, keep direct-mapped L1; 2-way also evaluated + rejected). `docs/M10_L2_DECISION_ANALYSIS.md`
9. ✅ **Backend flow** (M11): full SoC synth + P&R + STA via `make librelane-asap7-soc` (sv2v frontend — Synlig can't synth this SoC; `pnr/asap7/soc/`, `phase5_soc.sdc` single-clock, `phase5_soc.upf` 4-domain). Signed off **571 MHz / 62.9 mW / 520×520 µm / 65.6 % util / 0 DRC / 0 antenna** (run 14). PDN = benign tap-cell artifact (CPU/GPU precedent). `docs/PHASE5_RUN_HISTORY.md`
10. ✅ **Sign-off** (M12): M11 PPA recorded; docs updated (CLAUDE/ROADMAP/PHASE_STATUS → Phase 5 complete). Indicative ASAP7 (predictive PDK). Follow-ups: sv2v↔RTL EQY + CPU-macro burst-port LEF (`g0o`)

11. ✅ **Behavioral PMU** (Pre-Phase-6 #5, GH epic #98 → #99/#100/#101, 2026-08-01): `rtl/soc/pmu.sv` — APB4 slave + per-domain sequencer FSM encoding the 4 PST states from `phase5_soc.upf`. Sequencing order is **fixed by the UPF** (down: `ret_save → iso_en → gate clk → reset`; up: the reverse), walked one action per cycle through an explicit 9-state chain. PMU sits at `0x2000_8000–8FFF` — no free APB slot existed, so `PERIPH_LIMIT` + `AXIL_APB_LIMIT` were extended to `0x2000_8FFF`. Two `rv32i_clock_gate` cells gate `core_clk` into `u_cpu`/`u_gpu` (first SoC-level clock gates); isolation clamps live in `soc_top` per `-location parent`. **Sequencing only** — retention save/restore are emitted in order but are a functional no-op (`phase5_soc.upf:23`: no retention registers in Phase 5), and no power switches or `pg_ctrl`. `soc_all` **120/120**, `test_pmu` 10/10 with per-cycle ordering assertions.

12. ✅ **2-domain multi-clock SoC + CDC** — COMPLETE 2026-08-09, both domains close (Pre-Phase-6 #4, GH epic #90 → #91–#96, bead `d8v` decision in `docs/3PLL_CDC_EVALUATION.md`): split the SoC into CPU @ ~1282 MHz and GPU+bus+periph @ 571 MHz, giving exactly **one** CDC boundary (CPU ↔ crossbar M0). **#91 done (2026-08-01)**: `rtl/soc/async_axi_fifo.sv` — dual-clock AXI4 bridge, 5 gray-code FIFOs (AW/W/B/AR/R, id-less to match the crossbar's master face), built on new reusable primitives in `rtl/soc/cdc/` (`cdc_2ff_sync`, `cdc_reset_sync`, `cdc_gray_fifo`). Cummings style-1 pointers: only the *registered* gray pointer crosses, through one 2-FF sync each way; `full_q`/`empty_q` registered in their own domains, so **no combinational path crosses the boundary**. Reset is cross-coupled (`rst_both_n = s_rst_n_i & m_rst_n_i` into both `cdc_reset_sync`) — a one-sided reset would otherwise inject fabricated AXI beats. Reset is a **hard flush, not a graceful abort** (a burst can be left half-transferred; both resets must share a common root). `DEPTH` must be a power of two ≥ 4 (elaboration guard). `test_async_axi_fifo` **22/22**, `soc_all` **142/142**. ⚠️ The `mem_q` → read-domain combinational read is a real async path — **#94 must add `set_max_delay -datapath_only`** on it and on the two gray-pointer crossings.
    **#92 done (2026-08-01)**: second `pll_subsystem` instance (`u_cpu_pll_sub`) + second top-level reference port `cpu_clk_i`/`cpu_rst_n_i` + `APB_PLL2` slot at `0x2000_9000–9FFF` (`PERIPH_LIMIT`/`AXIL_APB_LIMIT` extended). `pll_clkgen_stub` is a pure ref passthrough with no divide, so two PLLs off **one** reference would be bit-identical — hence a second *port*, not a divided clock (also avoids the Run-13 CTS split-tree lesson in `phase5_soc.sdc`). GH #89 `pll_enable` self-brick was already fixed in `110d7ac`; #92 only replicates it to instance 2.
    **#93 done (2026-08-02)**: CPU domain made real. `u_cpu_cg` re-sourced `core_clk`→`cpu_core_clk`; `async_axi_fifo u_cpu_axi_cdc` inserted on CPU↔crossbar M0; `pmu_cpu_clk_en`/`iso_en` via `cdc_2ff_sync` and `pmu_cpu_rst_n` via `cdc_reset_sync` into the CPU domain; `ext_irq`/`timer_irq` synchronised (both level-held, so 2-FF is safe); ISO_CPU clamps moved to the bridge's CPU-domain face. New **`rtl/soc/apb_cdc_bridge.sv`** (2-phase toggle handshake) closes the APB_PLL2 crossing that went live once `cpu_clk_i != clk_i` (`axil_to_apb` confirmed tolerant of arbitrary `pready` wait states). TB wrappers now expose `cpu_clk_i`/`cpu_rst_n_i` as real ports with a shared `soc_clocks.py` helper; existing suites stay at 1:1. `soc_all` **159/159** (21 suites), `test_apb_cdc_bridge` 15/15, `soc_multiclock` 4/4 + `soc_pll_multiclock` 1/1 at a **7 ns / 3 ns coprime ratio** — the first real CDC coverage in this repo.
    ⚠️ **Two RTL bugs found only at a divergent ratio**, both invisible to every 1:1 suite *and* to `async_axi_fifo`'s own 22 unit tests, because both reset their domains together: (1) `4398c2e` — the CPU clock-enable synchroniser reset to "disabled", so `cpu_gated_clk` was stopped for the whole reset window and the CPU's *synchronous* reset never loaded `RESET_PC` (fix: synchronise the inverted enable so reset-to-0 means "not disabled"); (2) `7a9f9d4` — `cdc_gray_fifo`'s `wr_ready_o = !full_q` was not gated by `wr_rst_n_i`, so the FIFO advertised ready while held in reset and silently swallowed beats (fix: `wr_ready_o = wr_rst_n_i && !full_q`). Shared signature: **a reset value that advertises availability**. #95 should gate on that class explicitly rather than trusting unit-suite green.
    **#94 done (2026-08-02)**: `pnr/constraints/phase5_soc_multiclock.sdc` — evolved from the run-14 signed-off `phase5_soc.sdc`, not rewritten. Two `create_clock` on the **ports** (`sys_clk` 1750 ps on `clk_i`, `cpu_clk` 780 ps on `cpu_clk_i`) — the Run-13 CTS split-tree lesson is preserved and extended to the second PLL stub, so still **no `create_generated_clock`** for `core_clk`/`cpu_core_clk`. Adds `set_clock_groups -asynchronous` between the two, then `set_max_delay -datapath_only` (bounded to one *destination*-domain period) on: all 5 `async_axi_fifo` channel FIFOs (`mem_q` combinational read + both gray-pointer crossings each), `apb_cdc_bridge`'s 2 toggle crossings + 4 `cmd_*`/2 `resp_*` payload buses, and the PMU/IRQ single-bit crossings into `cpu_core_clk`. `u_cpu_pmu_rst_sync` gets `set_false_path` instead — it is an async-clear reset path, not a setup-checked datapath. Also fixed the sv2v build lists (`SKY130_SOC_SV_FILES`/`SOC_SV_FILES` were missing all 5 CDC modules **and** `rv32i_clock_gate.sv`); both `make <pdk>-soc-sv2v` runs now regenerate clean. ⚠️ **sv2v has no Verilator-style `-I` auto-discovery**, so a missing module there is silently blackboxed — the cocotb regression can never catch it. SDC is Tcl-syntax-validated only, not yet run through OpenSTA and not yet wired into any `config.json` (#96).
    Residual, non-blocking: metastability injection is not modelable in Verilator; PMU-driven live power-cycling across domains is untested (bead `2k8`) — the underlying ordering hazard (`pmu.sv` releases `rst_n_w` one cycle *before* ungating `clk_en_w` on power-up) was **closed in `soc_top.sv`**, not `pmu.sv`, by gating `u_cpu_cg` with the CPU-domain-native `pmu_cpu_rst_n_cpu_sync` (`cpu_gated_clk_en = ~pmu_cpu_clk_dis_sync & pmu_cpu_rst_n_cpu_sync`, commit `30beab3`): `pmu.sv`'s sequence order is UPF-mandated and the behavioural model depends on it for retention-by-construction (`docs/POWER_DOMAIN_EVALUATION.md:22,25`), so it stays unchanged. `timer_irq` is never exercised by any reused firmware. Also unfixed by design: the PMU power-down path has **no drain/quiesce step**, so a mid-burst CPU reset can wedge a crossbar slave engine (`soc_top.sv:84-93`) — pre-existing, widened by the bridge's hard-flush reset.
    **#96 done (2026-08-09)**: multi-clock PD re-closure, 8 runs (16–23). Driven by a new `pnr/asap7/soc/config_multiclock.json` + `librelane-asap7-soc-multiclock` target, leaving `config.json` and the run-14 sign-off byte-reproducible. **Best and accepted: run 23** (`RUN_2026-08-09_14-36-16`) — **BOTH domains close**: `sys_clk` **+74.8 ps / TNS 0 / 0 violators → 571 MHz MET**, `cpu_clk` **+9.8 ps / TNS 0 / 0 violators → 1282 MHz MET**, the first time the CPU domain has ever met its 780 ps target. 0 routing DRC, 0 antenna, 0 slew/cap, 51.9 mW, 66.9 % util, and the **post-route CDC budget check PASS**. The CPU domain runs **2.24× the fabric** instead of being de-rated onto it. Getting there needed two independent fixes: (a) the macro exported ~600–800 ps combinational in→out arcs on its APB outputs — `apb_prdata_o`/`apb_pslverr_o`/`apb_pready_o` are now PURE registered outputs (two earlier attempts failed and are documented in `rv32i_cpu_top.sv`: registering `prdata` alone merely RELOCATED the delay into an 876.85 ps input setup requirement, and a SETUP-phase decode for `pslverr` still left a 617.9 ps arc re-sourced from `apb_psel_i`); and (b) the CPU macro had **no `FP_PIN_ORDER_CFG`**, so every regeneration reshuffled **393 of 401** boundary pins — that, not the RTL, caused run 22's −596 ps collapse (post-CTS `cpu_clk` skew −485.6 → −922.1 ps, hold violations 805 → 4702, 4814 hold buffers inserted). `pnr/asap7/cpu/pin_order.cfg` now pins it: two runs produce a byte-identical LEF, which made tuning measurable for the first time (block setup −25.87 → −10.48 → **−0.87 ps** across three revisions). Full table + caveats → `docs/PHASE5_RUN_HISTORY.md`.
    ⚠️ **Three findings that outlive #96, all measured:** (1) bead `s9f` — librelane declares the resizer slack margins `units="ns"` but passes them raw to OpenROAD, which reads the Liberty unit; ASAP7 is `1ps`, so `0.075`/`0.1` meant 0.075 ps / 0.1 ps. **Every ASAP7 sign-off in this repo (CPU 1282 MHz, GPU, SoC run 14) had ~0 optimisation guard band, not 75/100 ps.** Reported slacks remain valid; the guard band does not. (2) bead `7l5` (fixed + closed) — `check_cdc_timing.tcl`'s exceptions never bound on a flattened netlist: hierarchy survives only as dot-joined escaped **net** names while cells become anonymous, OpenSTA's `-filter "name =~"` mis-parses a literal `.`, and the old exceptions targeted the synchroniser **output** (`q_o`), a destination-domain-only path rather than the crossing. Now re-pointed at the launch→first-capture segment and proven non-vacuous by negative control (all budgets forced to 1 ps → 7 violated groups). (3) beads `cyb`/`g0o` — **both now FIXED in run 23**: the 800.71 ps combinational APB-debug arc is gone (all three APB outputs registered; no output pin of the macro carries a combinational arc), and the burst-era ports (`axi_rlast_i`, `awlen`, `wlast`, `arlen`, …) are now constrained in the block SDC and present in both the LEF and the Liberty. A new finding replaces them: the macro boundary was never pinned, so any regeneration could silently wreck the integrating top's timing — fixed by `pin_order.cfg`, and the GPU macro has the same untreated exposure. IR drop is unobtainable on this design: `analyze_power_grid` fails `PSM-0069` from the same tap-cell connectivity artifact.

**Phase 6+** (after Phase 5 sign-off): additional AXI4-Lite peripherals (GPIO/I2C/PWM/WDT/TRNG/AES-SHA), minimal INT8 NPU (`rtl/npu/`), and FreePDK45 tech-node exploration. See `docs/ROADMAP.md`.

## AI/Human Boundaries

### AI MAY assist with

- Python boilerplate (class structure, imports)
- Simple instruction implementations (after human verification)
- cocotb driver scaffolding; test case generation; documentation formatting

### Human MUST

- Write and approve all specifications
- Implement complex instructions (branches, loads, stores); design control FSMs
- Define verification strategy; review all AI-generated code; make architectural decisions

See each phase in `docs/verification/VERIFICATION_PLAN.md` for detailed AI/Human responsibilities.

## Commit Message Convention

Use the format: `[Category] Brief description`

Categories: `[Fix]`, `[Feature]`, `[Code]` (refactoring), `[Env]` (build), `[Doc]`, `[Test]`, `[Spec]`, `[RTL]` (RTL design), `[PD]` (physical design), `[Analog]` (mixed-signal), `[Chore]` (maintenance).

## Coding Guidelines

All new/modified code follows [`docs/development/CODING_GUIDELINES.md`](docs/development/CODING_GUIDELINES.md) (SystemVerilog per lowRISC-adapted house style, Python per ruff/PEP 8). Compliance backlog: [`docs/development/CODING_COMPLIANCE_AUDIT.md`](docs/development/CODING_COMPLIANCE_AUDIT.md). Existing verified RTL is grandfathered — no style-only mass edits.

## Questions?

Refer to specifications in `docs/` — they are the source of truth.

<!-- rtk-instructions v2 -->
## RTK (Rust Token Killer)

**Golden rule**: prefix dev commands with `rtk` (e.g. `rtk git status`, `rtk pytest`, `rtk cargo build`). RTK uses a dedicated filter when one exists and passes through unchanged otherwise — always safe. Use it even inside `&&` chains. Typical savings 60–90% (tests 90–99%, build 70–87%, git 59–80%). Full command reference is in the user's global `~/.claude/RTK.md`; `rtk gain` shows analytics, `rtk proxy <cmd>` runs raw.
<!-- /rtk-instructions -->

### Project filters (`.rtk/filters.toml`)

The sim/lint flows are driven through `nix develop --command make ...`; without setup, none of that output is filtered. One command per clone / per machine:

```bash
make setup            # rtk trust + rtk transparent_prefixes + .mcp.json paths for this clone
make verify-tooling   # proves all three took effect; exits non-zero if not
```

Both setup steps fail **silently** when skipped — the suites still run, they are just no longer compressed, so there is no error to notice. `make verify-tooling` is the check. `make setup` is idempotent; re-run it after editing `.rtk/filters.toml`.

With both in place, `nix develop --command make -C tb/cocotb/soc soc_all` is auto-rewritten to `... --command rtk make ...` and a 26-test suite drops from 244 lines / 35 KB to 2 lines. Failures are never hidden: every non-PASS row, ERROR line, traceback and `make: *** Error` is kept, the exit code propagates, and rtk tees the complete log to `~/.local/share/rtk/tee/`. Edit the filters with `rtk verify` as the gate (inline tests live beside each filter).

### EDA tool output: wrappers + MCP session servers (`tools/eda/`)

`tools/eda/wrap-{verilator,yosys,opensta,cocotb}.sh` turn a raw one-shot tool
log into a compact JSON verdict (`tools/eda/summarize.py`) with a real exit
code (0 PASS / 1 FAIL / 2 ERROR / 3 tool missing) — a tool that exits 0 with an
empty or unparsable report is never read as PASS (bead `dwp`). For repeated
queries against one loaded design (timing closure), `tools/eda/mcp/` instead
exposes a persistent OpenSTA/OpenROAD session as an MCP server (`eda-opensta`,
`eda-openroad` in `.mcp.json`) so the multi-minute liberty+netlist+SDC load
happens once, not per query; raw reports are never returned inline, only a
JSON summary plus the on-disk path. See `tools/eda/README.md` for the full tool
surface and the session-vs-wrapper guidance.

<!-- BEGIN BEADS INTEGRATION v:1 profile:minimal hash:7510c1e2 -->
## Beads Issue Tracker

This project uses **bd (beads)** for issue tracking. Run `bd prime` to see full workflow context and commands.

### Quick Reference

```bash
bd ready              # Find available work
bd show <id>          # View issue details
bd update <id> --claim  # Claim work
bd close <id>         # Complete work
```

### Rules

- Use `bd` for ALL task tracking — do NOT use TodoWrite, TaskCreate, or markdown TODO lists
- Run `bd prime` for detailed command reference and session close protocol
- Use `bd remember` for persistent knowledge — do NOT use MEMORY.md files

**Architecture in one line:** issues live in a local Dolt DB; sync uses `refs/dolt/data` on your git remote; `.beads/issues.jsonl` is a passive export. See https://github.com/gastownhall/beads/blob/main/docs/SYNC_CONCEPTS.md for details and anti-patterns.

## Session Completion

**When ending a work session**, you MUST complete ALL steps below. Work is NOT complete until `git push` succeeds.

**MANDATORY WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update issue status** - Close finished work, update in-progress items
4. **PUSH TO REMOTE** - This is MANDATORY:
   ```bash
   git pull --rebase
   git push
   git status  # MUST show "up to date with origin"
   ```
5. **Clean up** - Clear stashes, prune remote branches
6. **Verify** - All changes committed AND pushed
7. **Hand off** - Provide context for next session

**CRITICAL RULES:**
- Work is NOT complete until `git push` succeeds
- NEVER stop before pushing - that leaves work stranded locally
- NEVER say "ready to push when you are" - YOU must push
- If push fails, resolve and retry until it succeeds
<!-- END BEADS INTEGRATION -->
