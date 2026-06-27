# 3-PLL Multi-Clock + CDC Evaluation (pre-Phase-6 #4)

**Status:** DECIDED 2026-06-27 — **GO, 2-domain MVP** (Option A): one CPU domain @ ~1282 MHz + one shared GPU+bus+peripheral domain @ 571 MHz, with a single async-AXI CDC bridge on CPU↔crossbar. The full 3-domain split (separate GPU PLL) is rejected as over-scoped (GPU already == bus speed). Folds in the `ste` PLL-enable fix. Implementation = per-module PRs under the epic below.
**Date:** 2026-06-27 · Bead `claude_verilog_test-d8v`.
**Proposal:** instantiate the `pll_subsystem` 3× — separate PLLs for CPU / GPU / SoC-bus+peripherals — to create genuine clock domains, and evaluate whether that's meaningful for exercising CDC.

## 1. Where we are today

- **Single clock.** Every instance runs on `core_clk` from one `pll_subsystem` (`clk_i` ref); only `pll_subsystem` itself is on `clk_i` (bootstrap rule). The AXI4 crossbar / AXI-Lite ring / APB subtree are **purely synchronous** — `soc_top.sv`, `soc_bus.sv`.
- **Zero genuine CDC.** The only synchronizers are 2-FF on async *pads* (IRQ `irq_src_i`, UART RX). No async-AXI FIFO, no gray-code pointers, no CDC-aware fabric. `design_state.json: cdc_clean=false`; `cdc_snitch` reports 0 real internal crossings (BAD count is ~95% reset-domain false positives).
- **Signed off single-clock** at M11: **571 MHz, GPU-governed** (`pnr/constraints/.../phase5_soc.sdc` = one `create_clock`, no `set_clock_groups -asynchronous`). The plan already flags multi-clock as a **High/Med risk** (CDC review; pre-harden macros [done]; per-domain SDC).

## 2. The upside (why 3-PLL was proposed)

| Block | Standalone ASAP7 fmax | In single-clock SoC |
| ----- | --------------------- | ------------------- |
| CPU | **1282 MHz** (780 ps, +24 ps; M7) | throttled to **571** |
| GPU | **571 MHz** (its native fmax) | 571 (governs) |
| Bus/periph | fast (small logic) | 571 |

So independent domains could run **CPU ~1282 MHz (2.25×)** while GPU stays 571. Plus: it's the **only way to exercise real CDC** in this design (currently none).

## 3. The cost (this is the hard part)

A domain split puts a **clock-domain crossing on every fabric boundary where the master and the crossbar differ**. From the topology map:

| Crossing | Signals | Needs |
| -------- | ------: | ----- |
| CPU ↔ crossbar (M0) | ~70 | async-AXI bridge (FIFO, gray-code ptrs) |
| GPU-data ↔ crossbar (M2) | ~70 | async-AXI bridge |
| GPU-ifetch ↔ crossbar (M1) | ~40 | async-AXI bridge (read-only) |
| GPU-ctrl AXI-Lite | ~20 | CDC on the AXI-Lite slave |
| (DMA, if its own domain) | ~70 | async-AXI bridge |

Plus: **reset synchronizers** per domain (reset is single-domain today), **multi-clock SDC** (3× `create_clock` + `set_clock_groups -asynchronous` + `max_delay` on every CDC path), **CDC verification** (the `cdc_snitch` POC needs a wrapper — reset-domain neutralization, port allowlist, `magic_cdc` attributes — before `BAD=0` is a real gate; Verilator CDC is weak; metastability isn't fully simulatable), and a **full M11-scale PD re-closure** (3 CTS trees, per-domain PDN/IR, multi-clock STA).

Async-AXI FIFOs / gray-code CDC are the **classic silicon-killer RTL** — hardest to get right, hardest to verify. This is a large, high-risk feature, not a refactor.

## 4. Key scoping insight — the full 3-domain split is over-scoped

The proposal was CPU / GPU / bus as **three** domains. But **GPU's fmax (571) == the bus target (571)** — so GPU and bus can share one domain. That collapses the design to **two** domains:

- **Domain A — CPU @ ~1282 MHz** (its own PLL).
- **Domain B — GPU + bus + peripherals @ 571 MHz** (one PLL).

Result: **ONE CDC boundary (CPU ↔ crossbar)** instead of four, while still (a) exercising real CDC end-to-end and (b) delivering the entire CPU 2.25× speedup. A separate 3rd PLL for GPU buys a *second* CDC boundary for ~no benefit (GPU is already at bus speed). **3 PLLs ≠ 3 useful domains here.**

## 5. Recommendation

**3-PLL as literally proposed (3 domains): NO.** **A 2-domain MVP (CPU-fast + everything-else): the right scope IF we pursue CDC** — and it's worth doing for the CDC-methodology value (this SoC has never exercised real CDC) plus a free CPU 2.25×, at a fraction of the 3-domain cost/risk.

But note the honest counter: **Phase 5 is signed off at 571 MHz single-clock, and this is a GPU-governed SoC** — the CPU is the control core, and CoreMark-class firmware (M10) runs fine. So multi-clock is **not required to ship**; its value is (a) CDC methodology/portfolio demonstration and (b) CPU-bound headroom that this design doesn't centrally need.

### Decision options (this PR)
- **A — 2-domain MVP (recommended if pursuing CDC):** one async-AXI bridge on CPU↔crossbar; CPU PLL @1282, shared GPU+bus PLL @571; multi-clock SDC; wrap `cdc_snitch` to a real gate; folds in the `ste` PLL-enable fix (PLL control redesigned anyway). Own feature epic + re-verify + a PD re-closure.
- **B — Full 3-domain:** as proposed; adds the GPU↔fabric CDC boundary. More cost/risk for marginal benefit.
- **C — NO-GO (defer):** stay single-clock (signed off). Multi-clock/CDC isn't needed for this GPU-centric SoC; revisit only if a CPU-bound workload justifies it. Keep `ste` as a standalone PLL-safety fix.

### Folds in
The 3-PLL/2-domain work redesigns PLL control (multiple `pll_subsystem`), so **fix the `pll_enable` self-brick (`ste` / issue #89) here** — make CONTROL[0] safe per domain.

## 6. If GO (A) — implementation sketch (own PRs, each re-verified)
1. **`async_axi_fifo.sv`** — parameterized dual-clock AXI4 CDC bridge (gray-code FIFO per channel). The crux; unit-test exhaustively (full-throttle, backpressure, near-empty/full, reset-while-busy).
2. **3×/2× `pll_subsystem`** in soc_top (params ready) + `ste` PLL-enable safety fix.
3. Insert the async bridge on CPU↔crossbar; reset synchronizers; GPU+bus on the shared PLL (no CDC there).
4. **`phase5_soc_multiclock.sdc`** — per-domain clocks, `set_clock_groups -asynchronous`, `max_delay` CDC budgets.
5. **CDC verification**: wrap `cdc_snitch` (reset neutralize + port allowlist + `magic_cdc` on synchronizer FFs) → `BAD=0` CI gate; directed CPU↔fabric CDC tests; `soc_all` regression.
6. **PD re-closure**: multi-clock M11 run (2 CTS trees, per-domain STA/PDN).

## 7. Verdict line
Pending human GO/NO-GO. Recommendation: **A (2-domain MVP)** if the goal includes real-CDC methodology; **C (defer)** if the goal is shipping the GPU-centric SoC, since single-clock 571 MHz is already signed off.
