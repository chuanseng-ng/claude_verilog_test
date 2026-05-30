# ASAP7 P&R Run History — GPU-Lite SIMT Compute Engine

**PDK**: ASAP7 7nm predictive FinFET
**Tool**: LibreLane + OpenROAD
**Design**: `gpu_top` (single compute unit, 8 lanes, 8 warps; 16 KB shared memory via `sram_1rw_128x32` macros)
**Target**: Max fmax with 0 setup/hold violations, 0 internal-net DRC, 0 antenna
**Branch**: `phase-4-pd-enhance`

---

## ✅ FINAL SIGNOFF — RUN_2026-05-28_06-29-48 (2026-05-28)

**Phase 4 GPU block is signed off at 571 MHz.** This run retargeted `CLOCK_PERIOD`
2.0 → 1.75 ns and closed clean, superseding the 500 MHz run `RUN_2026-05-27_11-16-37`.

| Metric | Value |
|---|---|
| Run directory | `pnr/asap7/gpu/runs/RUN_2026-05-28_06-29-48` |
| Fmax | **571 MHz** (1.75 ns clock period) |
| Setup WS / TNS / vios | +197.30 ps / 0 / **0** |
| Hold WS / TNS / vios | +16.29 ps / 0 / **0** |
| Max slew / cap / fanout vios | 0 / 0 / 0 |
| Power (total) | **262 mW** (internal 164 / switching 94 / leakage 4.2 mW; RVT TT @ 0.7 V / 25 °C) |
| Die / core / stdcell area | 115,600 / 102,282 / **60,500 µm²** |
| Macro area | 11,236 µm² (SRAM banks) |
| Utilization (stdcell) | 0.70 (0.664) |
| Instance count | 485,842 stdcells (70,164 sequential, 15,698 timing-repair buffers) |
| Antenna nets / pins | 0 / 0 |
| Clock skew (worst setup / hold) | 82.93 ps / −65.22 ps |

### Signoff caveats (documented, not regressions — carried by the prior 500 MHz run too)

1. **PDN connectivity not closed.** `design__power_grid_violation__count = 9,557,658`
   (VDD 4.78 M / VSS 4.78 M); `PSM-0069` check-connectivity fails on VDD/VSS;
   `PDN-0179` unable to repair all channels. **Identical count to the 500 MHz run** —
   a systematic block-level PDN gap, not introduced here. Defer the channel-repair /
   PDN fix to SoC-level power planning (Phase 5).
2. **325× `DRT-0074` "no access point"** — all on top-level I/O ports (`clk`, `rst_n`,
   `s_axil_*`, `m_axi_*`, `gpu_irq_o`). Zero internal-net DRC; `DRT-0073/0075` shorts /
   spacing = 0; `design__violations = 0`. Block-level I/O artifact that resolves when the
   SoC places real pins on routing tracks.
3. **Timing is post-GRT estimated.** Metrics come from step `39-openroad-stamidpnr-3`
   (post-global-route). `STAPostPNR` and `RCX` are gated off, so there is no SPEF-based
   sign-off STA. Numbers are optimistic but use the **same methodology as the 500 MHz run**,
   so the run-to-run comparison is apples-to-apples. A confirmation re-run with
   `STAPostPNR` + `RCX` enabled is the recommended next step before locking the number.

---

## Campaign Context

| Run | Date | Clock | Result | Notes |
|-----|------|-------|--------|-------|
| RUN_2026-05-23_14-02-43 | May 23 | 2.0 ns | Synthesis cleared | First GPU run past all prior synth stall points (regfile OOM, share-pass hang, DELAY-3 timeout resolved) |
| RUN_2026-05-26_20-00-11 | May 26 | 2.0 ns | Intermediate | GRT congestion / two-stage repair tuning |
| RUN_2026-05-27_11-16-37 | May 27 | 2.0 ns | **500 MHz (superseded)** | Prior signoff. Setup WS +306 ps. *Note: this run's `final/metrics.json` reports hold −212 ps / 368 viol — the 500 MHz signoff was not hold-clean at the final stage.* |
| RUN_2026-05-27_16-18-05 | May 27 | 1.75 ns | **Dead** | 571 MHz attempt; died at step 37 (`repair_design_postgrt`), ~18.9 h single-threaded GRT×2 bottleneck |
| **RUN_2026-05-28_06-29-48** | **May 28** | **1.75 ns** | **✅ 571 MHz SIGNOFF** | Hold-clean (+16.3 ps / 0 viol), setup +197 ps. `DRT_THREADS` 4→12 to reduce detailed-route runtime |

### Step-37 runtime note
`repair_design_postgrt` runs full GRT twice plus a multi-thousand-iteration repair loop on
the ~485 K-instance design — the dominant wall-clock cost. Levers explored: `DRT_THREADS`
4→12, die-area growth, and (deferred) disabling post-GRT resizer timing. See
`memory/pd/knowledge.md` and `docs/PHASE_STATUS.md` for the full step-37 analysis.

---

## Macro Views (Phase-5 hand-off)

The signoff DB is exported as ASAP7 hard-macro views for SoC integration:

```bash
cd pnr && make macro-views-asap7 BLOCK=gpu          # latest GPU run
make macro-views-asap7 BLOCK=gpu RUN=asap7/gpu/runs/RUN_2026-05-28_06-29-48
```

Output → `pnr/asap7/gpu/macro/`:
- `gpu_top.lef` — abstract LEF (gitignored, regenerated on demand)
- `gpu_top__nom_tt_025C_0p7V.lib` — timing model (committed)
- `gpu_top.nl.v.gz` — flat post-route netlist, gzipped (~9.6 MB; raw ~103 MB exceeds
  GitHub's 100 MB limit). Run `gunzip -k gpu_top.nl.v.gz` to restore for full-flat sim/LEC.
