# Sky130 (+FreePDK45) Harden + Real DRC/LVS — Evaluation (pre-Phase-6 #6)

**Status:** DECIDED 2026-06-27 — **GO, staged + host-gated.** Do the tractable, high-value part now: harden the CPU on Sky130 and run a **CPU + peripherals SoC with REAL Magic DRC + Netgen LVS** (the genuine physical sign-off the indicative ASAP7 run skipped). The **GPU-on-Sky130** stage is gated on a bigger host (≥32 GB RAM + ~500 GB scratch) — attempt only when available, else GPU stays ASAP7-indicative. **FreePDK45 ruled out** (Magic/Netgen blocked). Bead `claude_verilog_test-n0i`.

## 1. Findings

- **ASAP7 sign-off has no real DRC/LVS.** `pnr/asap7/soc/config.json:112` (+ cpu/gpu) set `RUN_MAGIC_DRC/RUN_KLAYOUT_DRC/RUN_LVS = false` — predictive PDK, indicative only (`PHASE5_RUN_HISTORY.md:34`). All three ASAP7 sign-offs (CPU/GPU/SoC) skip physical verification.
- **Sky130 gives REAL DRC/LVS.** Proven on the Phase 7 charge-pump PLL: real Magic DRC = 0 + Netgen LVS = MATCH on `sky130A.tech` (`PHASE_STATUS.md`, `PHASE7_MIXED_SIGNAL_PLL_PLAN.md:4`). Magic + Netgen are in the LibreLane nix-shell (currently `--skip`-ped, not absent). Sky130 is the **fabricatable** node (CLAUDE.md).
- **FreePDK45 ruled out.** `memory/pd/knowledge.md:136`: Magic DRC + Netgen LVS **permanently blocked** for NanGate45 (only KLayout DRC, post-DRT). → Sky130 is the only real-sign-off PDK.
- **CPU on Sky130 = easy.** Phase 2 already closed 75 MHz / 0 violations on Sky130 (`pnr/librelane/`). Just enable `RUN_MAGIC_DRC/LVS=true`. Hours.
- **GPU on Sky130 = the gating risk.** GPU = 485k cells / 60.5k µm² on ASAP7 7nm → **~1.2-1.8M µm²** on Sky130 130nm (20-30×). Synthesis already hit OOM on ASAP7 (`GPU_ASAP7_RUN_HISTORY.md:54`); Sky130 flat ≈ 18-25 h GRT, needs **≥32 GB RAM + ~500 GB scratch** — the **~15 GB host cannot**. Sky130 GPU fmax ~100-150 MHz.
- **No `pnr/sky130/soc/` exists** (only ASAP7). ASAP7 macro LEFs are ASAP7-layer-specific → **native Sky130 macro regen required** (can't port abstracts across PDKs).

## 2. Why GO (and why staged)

Value: this is the **only path to genuine fabrication readiness** — real DRC/LVS catches actual physical errors (shorts, spacing, antenna, netlist mismatch) that predictive ASAP7 never checks (Phase 7 lesson: hand-drawn primitives gave a misleading "clean" DRC with zero FETs extracted — real decks catch this). But GPU-on-Sky130 is resource-bound on the current host, so stage it:

- **Stage 1 (now, tractable):** CPU standalone Sky130 real DRC/LVS → native Sky130 CPU LEF/LIB.
- **Stage 2 (now):** CPU(macro) + peripherals (UART/SPI/timer/IRQ/DMA/crossbar, all small) SoC on Sky130 with real DRC/LVS — **no GPU**. Delivers a real-sign-off of most of the SoC.
- **Stage 3 (host-gated):** GPU standalone Sky130 harden — only on a ≥32 GB / 500 GB host. Intermediate gate: DRC=0 + LVS MATCH before proceeding.
- **Stage 4 (host-gated):** full SoC incl. GPU macro on Sky130, real DRC/LVS.

If the bigger host never materializes: Stages 1-2 still give a real-DRC/LVS CPU+periph SoC; GPU documented as ASAP7-indicative-only. That's a meaningful, honest sign-off improvement.

## 3. Risks
- Macro LEF/GDS regen per PDK (ASAP7 layers ≠ Sky130 M1-M5/V1-V4).
- SoC PDN: connect macro VDD/VSS pins to global rails (floating-domain risk).
- Antenna: don't re-insert diodes on macro-internal nets.
- Sky130 100-120 MHz is tight — pessimistic macro-interface LEF delays + clock uncertainty.
- Magic tech-file device generators must be used (Phase 7 lesson) — never hand-drawn.
- `g0o` (CPU macro LEF missing AXI4 burst ports) should be fixed during Stage 1 macro regen.

## 4. Decision options (this PR)
- **A — Staged + host-gated (CHOSEN):** Stages 1-2 now (CPU+periph real DRC/LVS); Stages 3-4 host-gated.
- **B — Full incl. GPU now:** attempt GPU-on-Sky130 on the 15 GB host — high OOM/runtime risk (likely fails). Rejected.
- **C — NO-GO:** keep ASAP7 indicative only. Rejected — leaves zero real physical sign-off.

## 5. If GO (A) — implementation sketch (own PRs)
1. **`pnr/sky130/cpu/`** — config from `pnr/librelane/`, `RUN_MAGIC_DRC/LVS=true`; harden CPU (+fix `g0o` burst-port LEF); output `sky130_rv32i_cpu_top.{lef,lib,nl.v}`, DRC=0/LVS MATCH.
2. **`pnr/sky130/soc/`** — CPU macro + flat peripherals (no GPU), `RUN_MAGIC_DRC/LVS=true`; real DRC/LVS sign-off; record fmax/power/area + DRC/LVS logs.
3. **[host-gated] `pnr/sky130/gpu/`** — GPU standalone Sky130 harden (≥32 GB/500 GB host); DRC=0/LVS MATCH gate.
4. **[host-gated] full Sky130 SoC** — CPU+GPU macros + periph, real DRC/LVS.
All PD via physical-design-orchestrator; read PD memories first. PD-only artifacts (config/SDC/LEF) don't need functional re-verification.

## 6. Verdict line
**GO, staged.** CPU+periph Sky130 real DRC/LVS now (Stages 1-2); GPU host-gated (Stages 3-4). FreePDK45 out. Tracking: GitHub epic + children below.
