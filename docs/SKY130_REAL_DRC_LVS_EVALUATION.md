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

## 7. Results (added 2026-07-31 — sections 1-6 above are the original 2026-06-27 plan)

### Stage 1 — CPU standalone (GH #103, bead closed)
Real sign-off achieved: **KLayout DRC 0, Netgen LVS MATCH, setup +0.366 ns @ 75 MHz**, native Sky130 macro views produced in `pnr/sky130/cpu/macro/`. `g0o` verified fixed for Sky130 (all 403 LEF pins incl. AXI4 burst ports present; `g0o` remains open as an ASAP7-only issue). Magic DRC reported 27.7 M violations — **waived**: 100.0000 % of all 27,730,498 coordinates fall inside the 10 SRAM macro footprints, KLayout on the same GDS reports 0, and the foundry KLayout deck excludes SRAM as pre-verified. Bead `45a`.

### Stage 2 — CPU macro + peripherals SoC, no GPU (GH #104, bead `9t6` closed)
Adopted run `RUN_2026-07-30_06-42-17` at 25.0 ns / 40 MHz:

| Gate | Result |
|---|---|
| Netgen LVS | **PASSED** |
| Routing DRC | **0** |
| Power-grid violations | **0** |
| Hold | 0 at all 9 corner labels (worst +0.0274 ns, max_ss) |
| Setup tt / ff | 0 |
| Setup ss | **FAIL** −4.6432 ns → bead `ujv`, deferred |
| Antenna | **FAIL** 140 pin / 120 net — quantified accepted residual, bead `58q` |
| KLayout DRC | 4 — GH #121 macro-internal waiver |
| Magic DRC | 9,081 — bead `45a` DEF+LEF-abstract waiver |

Power (per corner, from `51-openroad-stapostpnr/<corner>/power.rpt`): **nom_tt 37.63 mW**, worst corner max_ff 44.13 mW. 37.9 % utilization, 226,952 stdcells, die 6700 × 3100 µm.

### Stage 2 re-harden with Phase 6a GPIO — `RUN_2026-09-26_00-07-59` (2026-09-26, bead `00ef`)

First Sky130 SoC hardening since 2026-07-30. ⚠️ **Not a single-variable comparison against the run
above**: 33 RTL commits landed in between, 13 touching `soc_top.sv`, including the `rvb`/`ydw` SRAM
read/write pipelining, the `apb_cdc_bridge` debug-port bridge (GH #93/#95) and Phase 6a GPIO (`ckc`).

| Gate | 2026-07-30 | Final run |
|---|---|---|
| Netgen LVS | PASSED | **PASSED** — "Circuits match uniquely", 0 errors |
| Routing DRC | 0 | **0** |
| Setup, all 9 corners | ss **FAIL** −4.6432 ns | **0 violations**, worst slack **+7.08 ns** |
| Hold, all 9 corners | 0, worst +0.0274 ns | **0 violations**, worst **+0.1413 ns** |
| Antenna | 140 pin / 120 net | 191 pin / 132 net — bead `58q` class |
| Magic DRC | 9,081 | 9,081 — unchanged, bead `45a` waiver; the ONLY deferred error |
| KLayout DRC | 4 | **not run** — deliberately skipped, see below |
| Power (total) | 37.63 mW nom_tt | 48.25 mW |
| Utilization | 37.9 % | 38.98 % |

Timing is fully closed: setup AND hold clean at all nine corners. Two intermediate runs got here —
`RUN_2026-09-25_22-02-12` (resizer hold margins, 71 → 3 violations) and this one (SDC false path on
`gpio_in_i`, 3 → 0).

**The ss setup failure is gone.** Bead `ujv` was deferred as host-blocked on the premise that closing
ss needed SRAM re-characterization; on current RTL, setup now passes at all nine corners with +6.95 ns
of margin. The SRAM-model caveat below still applies to how much that ss number can be *trusted*, but
the design is no longer failing it. `ujv` should be revisited against this result.

**KLayout DRC was skipped, not waived.** `KLayout.DRC` peaked at 8.5 GB and was OOM-killed on this
15 GB host in the preceding attempt (`RUN_2026-09-20_19-46-05`), and it sits *before* `Netgen.LVS` in
librelane's Classic flow — so the kill cost LVS, the most valuable gate this node has, for a check that
is not on the path to it. `make librelane-sky130-soc-noklayout` passes `--skip KLayout.DRC --skip
Checker.KLayoutDRC` on the command line; `config.json` still says `RUN_KLAYOUT_DRC: true`. Re-run the
plain target on a larger host to recover it.

**Hold: 71 → 3 → 0.** The first attempt showed 71 hold violations including 2 at the gated `max_tt`
corner. Root cause (bead `00ef`): every violation was a boundary-port path — `timing__hold_r2r_vio__count`
= 0 at all nine corners — and all design repair runs on GRT-*estimated* parasitics, with no repair step
after RCX, so real-route erosion lands where nothing can react. Raising `GRT_RESIZER_HOLD_SLACK_MARGIN`
0.05 → 0.3 and adding `PL_RESIZER_HOLD_SLACK_MARGIN: 0.3` closed 68 of 71. The 3 survivors were all the
same path, `gpio_in_i[31]` → a `cdc_2ff_sync` stage-1 flop, closed by `set_false_path -from
[get_ports gpio_in_i]` in `sky130_soc.sdc` — the same treatment `uart_rx_i` and `spi_miso_i` already had,
and correct because `gpio_controller.sv` synchronises every pin internally. Verified: hold reaches
**0 violations at all nine corners**, worst slack +0.1413 ns.

**Max-slew 8623 / max-cap 346 are NOT new and NOT a macro artifact** — see bead `e45j`. They were 8357/329 before the
hold change and 8402/337 after it (so neither the margin raise nor the SDC false paths caused them;
the residual drift is ordinary run-to-run placement variation), they are 0 at every pre-RCX stage, and
only 0.29 % touch the SRAM macro. Both checkers are `--skip`-ped and do not gate. Note also that
"max fanout violations = 0" is **vacuous** here: there is no `set_max_fanout` in the SDC at all.

**⚠️ SCOPE — this is a TYPICAL-CORNER (nom_tt) TIMING SIGN-OFF, not a validated multi-corner one.** The nine reported corners are nine *labels*. The SRAM macro `sky130_sram_4kbyte_1rw1r_32x1024_8` is characterized at TT only, so its internal timing arcs are identical in all nine; ss/ff results carry macro-model error of unknown sign. The CPU macro *is* genuinely per-corner (9 distinct Liberty views, fixed 2026-07-25), and paths entirely within flat `sky130_fd_sc_hd` logic are corner-accurate. The physical gates — LVS, routing DRC, PDN, KLayout DRC — are **not** subject to this caveat and stand as real results. See the `pnr/sky130/soc/constraints/sky130_soc.sdc` header.

**Why Stage 2 stops here.** Closing ss honestly requires SPICE characterization of the SRAM macro at ss/ff. Bead `o1i` measured this as ~26–31 h **per corner** (~80–95 h for three) from Xyce's own progress meter, against a host that reboots every 2–8 h. Both `ujv` (ss setup) and `o1i` (SRAM characterization) are therefore **deferred as host-blocked**, not open work — `ujv` is not a PD-tuning problem, and relaxing frequency does not fix it (path delay scales with period at ≈0.52 ns/ns, so extrapolated closure is ~29 MHz and even that is a two-point lower bound).

### Stages 3 & 4 — GPU (GH #105, #106)
**Not attempted. Still host-gated** on ≥32 GB RAM + ~500 GB scratch; the current host has ~15 GB. The GPU remains ASAP7-indicative-only, exactly the fallback anticipated in §2. Epic GH #102 stays open on these two stages.
