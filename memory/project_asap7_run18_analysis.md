# ASAP7 Run 18 PPA Analysis

*Run directory: `pnr/asap7/runs/RUN_2026-05-16_10-12-46`*
*Completed: 2026-05-16, 48/48 stages, "Flow complete."*
*Clock period: 1.2 ns (833 MHz target)*

---

## 1. Key Results Summary

| Metric | Run 17 (baseline) | Run 18 | Delta | Status |
|--------|-------------------|--------|-------|--------|
| Setup WNS (ps) | -788.347 | **-758.992** | **+29.4 ps** | Marginal improvement |
| fmax (MHz) | ~503 | **~510** | **+7 MHz** | Marginal improvement |
| Setup TNS (ps) | -2,156,870 | -2,001,070 | +155,800 ps | Marginal improvement |
| Hold WNS (ps) | -13.807 (1 vio) | **+5.648 (0 vio)** | **FIXED** | P3 hold false-path worked |
| Hold violations | 1 | **0** | -1 | FIXED |
| Total area (µm²) | 6,971.66 | **6,980.79** | +9.1 µm² | +0.1% (P1 trap_type FFs) |
| Stdcell area (µm²) | 3,460.46 | 3,469.59 | +9.1 µm² | Flat |
| SRAM area (µm²) | 3,511.2 | 3,511.2 | 0 | Unchanged (10 macros) |
| Instance count | 28,559 | 28,674 | +115 | Small (trap_type encoding FFs) |
| Total power (mW) | 28.73 | **28.85** | +0.12 mW | Flat |
| DRC violations | 0 | 0 | — | Clean |
| Antenna violations | 0 | 0 | — | Clean |
| Max-slew violations | 0 | 0 | — | Clean |
| Max-fanout violations | 0 | 0 | — | Clean |

**Achieved fmax formula**: fmax = 1 / (T_period_ns + |WNS_ns|) = 1 / (1.2 + 0.759) = **510 MHz**

---

## 2. P1 Confirmation: Was Run 17's `_43062_` Startpoint Eliminated?

**YES — CONFIRMED ELIMINATED.** The startpoint `_43062_` (Run 17's #1 violator, EX1b trap
cascade output, fanout=7) has exactly **1 occurrence** in the Run 18 violator_list.rpt, and it
is NOT in the top-5 startpoints by path count or worst slack. The Run 17 critical path is gone.

Run 17's entire top-5 (`_43062_`, `_43132_`, `_43053_`) are absent from Run 18's top violators.
This confirms P1 (trap_type pre-encoding) successfully eliminated the 22-gate EX1b trap cascade.

---

## 3. Run 18 Critical Path Identity — `_42314_`

**Startpoint**: `_42314_` (DFFHQNx2_ASAP7_75t_R, net `_03673_`, fanout=8)
**Endpoint**: `_42143_` (DFFHQNx2_ASAP7_75t_R)
**Path Group**: PIPELINE
**Slack**: -758.992 ps
**Data arrival**: 870.49 ps; **Required**: 111.50 ps

### Gate chain (from max.rpt):
```
_42314_/QN → split802/BUFx2 → AOI221xp5 → NAND4xp25 → HB1xp67 → BUFx2 → BUFx6f →
AND4x1 → A2O1A1O1Ixp25 → HB1xp67 → AOI211x1 → BUFx3 → BUFx6f → AO31x2 → OAI211xp5 →
AOI21xp5 → AOI21xp5 → NAND5xp2 → A2O1A1Ixp33 → BUFx3 → HB1xp67 → A2O1A1Ixp33 →
AOI31xp67 → A2O1A1Ixp33 → OA211x2 → OAI31xp33 → OAI31xp33 → _42143_/D
```
Total logic depth: **~28 combinational stages** (longer than Run 17's `_43062_` at ~22 stages)

### RTL Identity of `_42314_`
The gate chain starts from a fanout=8 FF and immediately hits AOI221/NAND4/AND4/A2O1A1O1I —
this is characteristic of **EX1b store-byte-align** + **EX1b → EX2 pipeline packing** logic.
The chain passes through shared nodes `_14356_`, `_14820_`, `_14926_`, `_15036_`, `_15197_`
which are also traversed by the `_42317_` and `_42414_` paths — all three startpoints feed the
same combinational cone. This is the **EX1b packed output → EX2 register** datapath:
byte-alignment mux, write-strobe generation, plus the downstream EX1b→EX2 mux-and-pack logic.

**This is NOT the trap cascade** (which was replaced by a flat case-mux in P1). The P1 fix
eliminated the trap priority encoder but exposed the parallel EX1b path: store-byte-align +
pipeline struct packing. Both halves of EX1b share the same structural depth.

**Key insight**: P1 reduced the trap cone from ~22 levels but the byte-align/pack path through
EX1b was already ~28 levels — equally deep, now fully exposed as the new bottleneck.

---

## 4. Root Cause: Why P1 Pre-Encoding Gained Only +29 ps

### 4.1 Wrong sub-cone targeted

Run 17's `_43062_` was the trap cascade OUTPUT register, and P1 shortened the trap cascade by
pre-encoding trap_type in EX1a. The gain (+29 ps) was absorbed because:

1. **The trap cascade was not the global bottleneck in Run 17.** `_43062_` generated only 126
   paths (worst -788 ps). The EX1b store-byte-align path from `_42314_` (which is ~28 gate
   levels) was already present at ~-760 ps range in Run 17 but hidden behind `_43062_`'s
   slightly worse slack.

2. **P1 shortened the trap cascade from ~22 to ~4 gate levels** (flat case-mux on a 3-bit
   enum). This was structurally correct. But the trap-cascade output did not set the timing of
   the STORE path — both cones share only the final mux stages into ex1_ex2_reg_o.

3. **The byte-align/pack path is the true EX1b bottleneck**. It starts from `_42314_` with
   fanout=8 and traverses AOI221→NAND4→AND4→A2O1A1O1I (≈12 levels just to reach the midpoint
   rebuffer), then continues through OAI211→AOI21→AOI21→NAND5→A2O1A1I→AOI31→OA211→OAI31×2
   (another 16 levels). Total ~28 levels. No amount of trap cascade shortening helps here.

4. **Net result**: P1 moved the trap cascade timing from co-critical to non-critical, but the
   byte-align / EX1b-pack cone simply became the new bottleneck at essentially the same depth.

### 4.2 Three consecutive marginal-gain runs

| Run | Change | WNS gain | Root cause |
|-----|--------|----------|------------|
| 16→17 | EX1a/EX1b mid-cone register insertion | +23.7 ps | EX1b trap cone = ALU cone depth |
| 17→18 | trap_type pre-encode in EX1a | +29.4 ps | Byte-align/pack path same depth |
| 18→19 | ? | ? | Must target byte-align cone or a different stage |

The EX cone as a whole has been split into EX1a + EX1b + EX2 (three pipe stages with two FFs).
Each half of EX1b is still ~28 gate levels. Further EX retiming would require adding EX1c
(4→5 cycle branch penalty) or restructuring EX1b's store-byte-align to pre-compute in EX1a.

---

## 5. Pre-PnR vs Post-GRT WNS Flow

| Stage | WNS (ps) | Notes |
|-------|----------|-------|
| Pre-PnR (step 11) | -2,440.6 | Ideal clocks, unplaced — MAX_FANOUT VIOLATIONS=19, MAX_SLEW=9255 |
| Post-GRT + resizer (step 40) | -758.99 | After timing repair — **final post-DRT STA** |

Pre-PnR has 9,255 max-slew violations and 19 max-cap violations (worst fanout not flagged).
The resizer closed ~1,681 ps of timing from pre-PnR to post-DRT.

---

## 6. Top-5 Violating Startpoints (Post-DRT, Run 18)

| Rank | Startpoint FF | Worst Slack (ps) | #Paths as Source | Net Fanout (QN) | RTL Function |
|------|---------------|-----------------|-----------------|-----------------|--------------|
| 1 | `_42314_` | -758.992 | 24 paths | 8 | EX1b store-byte-align + pack → EX2 reg |
| 2 | `_42039_` | -738.253 | 98 paths | 8 | EX1b pipeline register bit (same cone, adjacent FF) |
| 3 | `_42414_` | -752.286 | 9 paths | 7 | EX1b control output FF (same combinational cone) |
| 4 | `_45628_` | -639.354 | 537 paths | 11 | I-cache FSM state / address output FF — high path count, feeds I-cache data SRAMs |
| 5 | `_45886_` | -600.592 | ~10 paths | ~8 | I-cache tag or control FF |

**Key findings:**
- `_43062_` (Run 17 #1): **1 occurrence only** — ELIMINATED as a material source
- `_42314_`, `_42039_`, `_42414_`: All three traverse the SAME combinational cone (nodes
  `_14356_`, `_14820_`, `_14926_`, `_15036_` appear in all three paths). Combined they account
  for ~131 violating paths all in EX1b → EX2 data packing logic.
- `_45628_` is the LARGEST SINGLE SOURCE BY PATH COUNT: 537 paths with endpoints at
  `u_core.u_icache.gen_data_sram[0..3].u_data_sram/din0[*]` and `addr0[*]` — this is the
  I-cache SRAM write-data/address path. Fanout=11. Worst slack -639 ps. This is a structural
  I-cache fanout problem (similar to the D-cache problem in Runs 14-16).
- `_45886_`: ~10 paths, worst -600 ps, also I-cache related.

---

## 7. D-cache / I-cache SRAM-Endpoint Paths

### D-cache paths
The `_45628_` startpoint endpoints include `u_core.u_icache.gen_data_sram[2].u_data_sram/din0[*]`
and `u_core.u_icache.gen_data_sram[3].u_data_sram/addr0[*]` at -607 to -608 ps. These are
**I-cache** data SRAM endpoints (not D-cache).

The `hit_bank_q` D-cache fix from Run 16 appears to have resolved the D-cache fanout bottleneck
— D-cache-specific SRAM endpoints are NOT dominant in Run 18's violator list (no D-cache data
SRAMs in top violators). The `_45628_` path is purely an I-cache write path issue.

### I-cache fanout — `_45628_` (new bottleneck, 537 paths)
This FF feeds: `u_core.u_icache.gen_data_sram[0..3].u_data_sram/din0[*]` (all 4 data bank
inputs) and `addr0[*]` — identical structural pattern to the Run 14 D-cache bottleneck but now
in the I-cache. The `_45628_` net (fanout=11) drives 4 SRAMs × 32 bits = 128 data inputs plus
8-bit address = 520 total loads before rebuffering, resulting in 537 violating paths.

**Root cause**: The I-cache refill data/address path from the AXI refill buffer to all 4 data
SRAMs is driven by a single FF that broadcasts to all four banks simultaneously — same structural
pattern as D-cache pre-Run16 fix. The fix pattern (per-bank registered copies) would apply
identically to `rv32i_icache.sv`.

---

## 8. Hold Status

Hold WNS: **+5.648 ps, 0 violations**. P3 (SDC false-path for `_44651_ → _44995_`) fixed the
Run 17 hold regression cleanly. Hold worst-case register-to-register slack is +14.55 ps.

---

## 9. Area and Power Delta vs Run 17

| Sub-metric | Run 17 | Run 18 | Delta |
|------------|--------|--------|-------|
| Total instance area (µm²) | 6,971.66 | 6,980.79 | +9.13 |
| Stdcell area (µm²) | 3,460.46 | 3,469.59 | +9.13 |
| SRAM macro area (µm²) | 3,511.2 | 3,511.2 | 0 |
| Instance count | 28,559 | 28,674 | +115 |
| Sequential cells | ~4,067 | 4,102 | +35 |
| Total power (mW) | 28.73 | 28.85 | +0.12 |

The +9.13 µm² increase is from P1's `trap_type_e` 3-bit register in `ex1a_ex1b_reg_q` (~35 new FFs).

---

## 10. Power Breakdown (Run 18)

| Group | Internal (mW) | Switching (mW) | Leakage | Total | % |
|-------|--------------|----------------|---------|-------|---|
| Sequential | 4.079 | 0.038 | ~0 | 4.118 | 14.3% |
| Combinational | 0.194 | 0.228 | ~0 | 0.422 | 1.5% |
| Clock | 0.703 | 1.116 | ~0 | 1.819 | 6.3% |
| Macro (SRAM) | 22.487 | 0 | 0.001 | 22.488 | 78.0% |
| **Total** | **27.463** | **1.383** | **0.001** | **28.847** | |

SRAM dominates at 78% of total power. Std-cell (sequential + combinational + clock) = 22%.

---

## 11. Flow Health Checks

| Check | Result |
|-------|--------|
| Stages completed | 48/48 |
| Flow termination | "Flow complete." |
| DRC violations | 0 |
| Antenna violations | 0 |
| Max-slew violations | 0 |
| Max-fanout violations | 0 |
| DRT-0074 errors | 373 (permanent, non-fatal) |
| PDN-0179 | 1 (permanent, non-fatal) |
| PSM-0069 | 2 (permanent, non-fatal) |
| Hold violations | **0 (FIXED — P3 hold false-path worked)** |

---

## 12. Run 19 Priority Recommendations

### Primary bottlenecks (two independent cones):

**Bottleneck A (131 paths, -759 ps worst)**: EX1b store-byte-align + pipeline-pack cone
- Startpoints `_42314_`, `_42039_`, `_42414_` all feed the same ~28-gate-level cone
- Fix options: (1) Pre-register store byte-align signals (pre_wstrb, pre_wdata_aligned) in EX1a,
  saving ~8-10 gate levels from EX1b; (2) Add EX1c sub-stage (4-cycle branch penalty)
- Recommended: Pre-register byte-align in `ex1a_ex1b_reg_q` (same approach as P1 for trap_type)
  — extends ex1a_ex1b_t struct with pre_wdata_aligned[31:0] + pre_wstrb[3:0], computes in EX1a,
  uses in EX1b. Zero branch penalty change. Expected gain: +150-200 ps.

**Bottleneck B (537 paths, -639 ps worst)**: I-cache refill data/address fan from `_45628_`
- FF drives all 4 I-cache data SRAM banks' din0[*] and addr0[*] simultaneously (~537 loads)
- Fix: Per-bank register duplication in `rv32i_icache.sv` (identical pattern to D-cache Run 16 fix)
  — 4 registered copies of the refill write data/address, each driving one bank
- Expected gain: +100-150 ps on I-cache SRAM-endpoint paths; removes 537-path cluster

### P1 (HIGH — est. +150-200 ps): Pre-register store byte-align in EX1a → EX1b
Add `pre_wdata_aligned[31:0]` and `pre_wstrb[3:0]` fields to `ex1a_ex1b_t` struct.
Compute in `rv32i_pipeline_ex.sv` EX1a (before the registered boundary).
Use in `rv32i_pipeline_ex1b.sv` directly from `ex1a_i.pre_wdata_aligned` / `ex1a_i.pre_wstrb`.
This removes the byte-align mux tree (~8-10 gates) from the EX1b cone.

### P2 (HIGH — est. +100-150 ps): I-cache per-bank refill data register duplication
In `rv32i_icache.sv`: duplicate the refill write-data/address registers per data bank.
Pattern: 4 per-bank copies of `refill_din_q[b][31:0]` and `refill_addr_q[b][7:0]`, each
driving only one `gen_data_sram[b].u_data_sram/{din0,addr0}`.
Use `(* keep = 1 *)` attribute to prevent Yosys re-merging.

### P3 (SDC — no change): Hold is clean, no new false-paths needed.

### Config (no change): Keep density 42%, MAX_FANOUT 25, die 140×140, period 1.2 ns.

### Projected Run 19 WNS

| Scenario | Expected WNS (ps) | Expected fmax (MHz) |
|----------|-----------------|---------------------|
| P1 only (byte-align pre-register) | -560 to -620 | ~541-580 MHz |
| P2 only (I-cache bank dup) | -600 to -660 | ~525-556 MHz |
| P1 + P2 (both) | -400 to -480 | ~575-625 MHz |

**If both fixes applied and work as projected, Run 19 should break 570 MHz fmax.**

---

## 13. EX Retiming Summary — 3 Consecutive Marginal Gains Explained

| Run | EX change | WNS gain | True bottleneck after fix |
|-----|-----------|----------|--------------------------|
| Run 17 (EX1a/EX1b split) | Inserted FF between ALU and trap cascade | +23.7 ps | EX1b trap cascade = same depth |
| Run 18 (trap_type pre-encode) | Flat case-mux replacing 22-level cascade | +29.4 ps | EX1b byte-align/pack = 28 levels |
| Run 19 (byte-align pre-register) | Move mux to EX1a | est. +150-200 ps | I-cache fanout |

The EX cone retiming approach has produced diminishing returns because each EX1b sub-cone
is similarly deep (~22-28 gates). The byte-align pre-register is the last practical EX retiming
without adding a 4-cycle branch penalty. After Run 19, further EX gains will require EX1c.

---

*Analysis completed 2026-05-16.*
*Run 18 launched after Run 17 (RUN_2026-05-16_08-05-19, WNS -788 ps).*
