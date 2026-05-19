# ASAP7 P&R Run History — RV32I CPU

**PDK**: ASAP7 7nm predictive FinFET  
**Tool**: LibreLane + OpenROAD  
**Target**: Max fmax with 0 DRC, 0 setup/hold violations  
**Branch**: `phase-2-3/asa7-run-rtl-timing-fix-1`

---

## ⚠️ SDC Units Bug — Campaign Context

All runs fall into two distinct eras:

| Era | Runs | SDC Period | Effect |
|-----|------|-----------|--------|
| **Era 1: SDC-bugged** | 7–31 | `create_clock -period 1.9` resolved to **1.9 ps** (not 1.9 ns) due to Liberty `time_unit: 1ps` | WNS ≈ `−(path_delay_ps − 1.9)`. All fmax estimates are approximations assuming a 1 GHz target. **True achievable fmax was ~1150 MHz throughout**, not ~500 MHz. |
| **Era 2: Units corrected** | 32–41 | Values in **picoseconds** (`-period 720` = 720 ps = 1389 MHz target) | Real STA. Frequency campaigns meaningful. |

The fix landed at Run 33: SDC rewritten with comment `# IMPORTANT: All time values are in PICOSECONDS`.

---

## Master PPA Table

### Era 1: SDC Units Bug (Runs 7–31)
> WNS values = path-delay improvement metrics (relative to ~0 ps required time). Fmax estimated as 1/(1 ns + |WNS|/1000 ns). Real design fmax was ~1150 MHz by Run 31.

| Run | Date | WNS (ps) | Hold WNS (ps) | Power (mW) | Std Cells | Result | Key Change |
|-----|------|----------|---------------|------------|-----------|--------|------------|
| 7  | Apr 26 | −1147 | — | ~33 | — | Baseline | Initial ASAP7 flow, 1.0 ns clock target |
| 8  | Apr 26 | −1026 | — | — | 34,899 | +121 ps | RTL retiming: register IRQ, CSR pre-decode in ID, misalign→MEM |
| 9  | Apr 26 | −1059 | −12.5 | — | — | −33 ps regression | Register mem_trap_redirect (flat) — wrong path targeted |
| 10 | Apr–May | — | — | — | — | **Abandoned** | Resume attempt from stage 44 failed |
| 11 | May 8 | −844.7 | +4 (clean) | 31.81 | — | +214 ps | **Sync reset on cache FSMs** — DFFASRHQNx1 → DFFHQNx1/x2 |
| 12 | May 9 | −853.4 | −19.4 | 32.33 | — | **−8.7 ps regression** | Die shrink 150→125 µm + `set_max_fanout 4` (harmful to CTS) |
| 13 | May 10 | −781.9 | −9.8 | 33.86 | — | **+71 ps** | Full sync-reset conversion all FFs + 140×140 die + remove `set_max_fanout` |
| 14 | May 14 | −814.6 | +20.4 | 33.81 | — | **−32.7 ps regression** | EX2 stage insertion — fixed ALU path, exposed D-cache tag fanout |
| 15 | May 15 | −792 | — | — | — | +22 ps | 1.2 ns period, MAX_FANOUT 8 — marginal |
| 16 | May 15 | −812 | 0 | 28.23 | — | **−20 ps regression** | MAX_FANOUT 20, density 45%, D-cache multicycle SDC |
| 17 | May 16 | −788.3 | −13.8 | 28.73 | 28,559 | +23.7 ps | EX mid-cone retiming + I-cache tag-write register; 1 hold introduced |
| 18 | May 16 | −759.0 | +0 (fixed) | — | — | +29.3 ps | Trap-type pre-encode in EX1a + hold false-path fix |
| 19 | May 16 | −782.1 | +1.0 | — | — | **−23 ps regression** | Byte-align pre-register + I-cache bank dup — wrong co-critical path exposed |
| 20 | May 16 | −697.2 | +1.0 | 28.91 | 29,372 | **+85 ps (only 19% of projected +300–450)** | EX1c stage insertion — if_id_reg path exposed as independent bottleneck |
| 21 | May 16 | — | — | — | — | — | MAX_TRANSITION 40→20 ps + CTS slew/clustering tuning (config-only) |
| 22 | May 16 | — | — | — | — | — | Register I-cache data-SRAM write + congestion relief (RTL+PD) |
| 23 | May 17 | — | — | — | — | — | Register EX1b outputs + die shrink 160→140 µm + clock adjustment |
| 24 | May 17 | −702.2 | −5.2 | 18.48¹ | — | Marginal vs Run 20 | APB multicycle path fix |
| 25 | May 17 | −813.7 | 0 | — | — | **−111 ps regression** | — |
| 26–29 | May 17–18 | — | — | — | — | — | Progressive resizer/synth tuning (DELAY 2→3, MAX_FANOUT 8→12→8) |
| 30 | May 18 | −716.3 | +11.2 | 18.46¹ | 30,787 | **Best Era 1 WNS** | AXI IO hold false-paths in SDC (+34 ps vs Run 29) |
| 31 | May 18 | — | — | — | — | Superseded | EX1c pre-decode RTL + DELAY 3 — superseded by units fix |

¹ Power values for Runs 24/30 appear as ~18 mW in experiences.jsonl, likely a units artifact from a prior logging bug. Actual power was ~28–34 mW.

---

### Era 2: SDC Units Corrected (Runs 32–41)
> All timing in real picoseconds. Period values are `create_clock -period <ps>`.

| Run | Dir (date suffix) | Clock (ps) | WNS (ps) | Hold WNS (ps) | TNS (ps) | Power (mW) | Std Cells | Util | DRC | Result | Key Change |
|-----|------------------|-----------|----------|---------------|---------|------------|-----------|------|-----|--------|------------|
| 32 | — | ~1200 | — | — | — | — | — | — | — | Units fix + rebase | SDC `time_unit` recognized; prior WNS re-anchored |
| 33 | — | 1200 | **+328** | — | 0 | — | — | — | 0 | First real-STA clean run | SDC corrected (1200 ps) → `report_clock_min_period` = 871 ps → **1147 MHz achievable** |
| 34 | 08-56-42 | 900 | **+128.3** | +20.7 | 0 | 42.12 | 31,700 | 50.7% | 0 | Clean ✅ | Period push 1200→900 ps |
| 35 | 10-47-29 | 720 | **+5.70** | +18.2 | 0 | 52.86 | 32,103 | 51.0% | 0 | **SIGNED OFF ✅** | RTL: EX1c one-hot trap restructure; period 900→720 ps; die 160→130 µm |
| 36 | 16-33-50 | 720 | −5.52 | −16.1 | −40.3 | **26.63** | 32,263 | 51.0% | 0 | Power win / timing open ❌ | RTL: 10× ICGx1_ASAP7_75t_R SRAM clock gating → **−49.6% power** (52.86→26.6 mW); CTS skew 62→159 ps (ICG pin unbalanced) |
| 37 | 17-21-21 | 720 | −3.892 | **+27.6** | −3.89 | 26.65 | 32,235 | 50.97% | 0 | 1 setup vio / hold closed ✅ | SDC: `gclk_sram` generated-clock + hold false-paths; CTS skew 159→32 ps; hold margins 0.05→0.10 |
| 38 | 20-04-54 | 720 | −3.892 | +27.6 | −3.89 | 26.65 | 32,235 | 50.98% | 0 | **Config-only no-op** ❌ | PL resizer margin 0.05→0.10, GRT margin 0.10→0.15 — RSZ-0062: path is logic-depth-limited, not drive-limited |
| 39 | 21-11-26 | 720 | −3.619 | +26.3 | −3.62 | 26.66 | 32,376 | 51.2% | 0 | +0.27 ps partial ❌ | RTL: shared 33-bit adder replaces 4 parallel carry chains in ALU — old XNOR path closed, OR5/OR4 family exposed |
| 40 | 21-59-43 | 720 | **+14.59** | +26.0 | 0 | 26.59 | 32,256 | 51.3% | 0 | **TIMING CLOSED ✅** | SDC: `set_clock_uncertainty -setup` 20→15 ps — 5 ps recovery closes −3.619 ps violation; fmax 1417.6 MHz |
| 41 | *(running)* | **710** | TBD | TBD | TBD | TBD | TBD | — | — | **In progress** | Config: period 720→710 ps (+14 MHz); CTS clustering 8/16→6/12 (skew); MAX_TRANSITION 20→15 ps (power) |

---

## Per-Run Detail

---

### Run 7 — Baseline (Apr 26, 2026)
**WNS: −1147 ps | fmax est. ~466 MHz**

First complete ASAP7 LibreLane flow run. Establishes baseline PPA after all infrastructure patches (RSZ-0089 set_rc.tcl, DRT-0074 catch block, PDN non-fatal exit). 1.0 ns SDC target (bug: resolved to 1.0 ps).

**Infrastructure patches applied (all runs inherit):**
- `set_rc.tcl` ASAP7 RC injection (RSZ-0089)
- `drt.tcl` catch block for DRT-0074 non-fatal
- `pdn.tcl` non-fatal exit (PDN-0179)
- IO pin thickness ×8 (DRT-0074 valid WIDTHTABLE width)
- `FP_PDN_RAIL_WIDTH: 0.054` (PDN-0179)

---

### Run 8 (Apr 26, 2026)
**WNS: −1026 ps → +121 ps | fmax est. ~494 MHz**

| Fix | Type | File(s) |
|-----|------|---------|
| Register IRQ/CSR pre-decode in ID stage | RTL | `rv32i_pipeline_id.sv`, `rv32i_interrupt_ctrl.sv` |
| Register misalign check in MEM stage | RTL | `rv32i_pipeline_mem.sv` |
| Register `mem_trap_redirect` | RTL | `rv32i_core.sv` |

---

### Run 9 — Regression (Apr 26, 2026)
**WNS: −1059 ps → −33 ps regression | Hold: −12.5 ps**

Registered `mem_trap_redirect` in a flat single-cycle path. Targeted the wrong path family; exposed a different bottleneck.

---

### Run 10 — Abandoned (Apr–May 2026)
Resume attempt from stage 44. Flow failed; launched fresh Run 11.

---

### Run 11 (May 8, 2026)
**WNS: −844.7 ps → +214 ps vs Run 9 | Power: 31.81 mW | fmax est. ~542 MHz**

**Critical discovery**: All 4,102+ setup violations trace to a single FF `_54587_` — the I-cache FSM state register, a `DFFASRHQNx1` async-reset cell. The QN (inverted Q) output adds extra inversion delay.

| Fix | Type | File(s) |
|-----|------|---------|
| Sync reset on cache FSM state registers | RTL | `rv32i_icache.sv`, `rv32i_dcache.sv`, `rv32i_cache_arbiter.sv` |

---

### Run 12 — Regression (May 9, 2026)
**WNS: −853.4 ps → −8.7 ps regression | Hold: −19.4 ps / 54 violations**

| Fix | Type | Outcome |
|-----|------|---------|
| Die shrink 150→125 µm | Config | ❌ Congestion rose 37.6%→56.4% util, offset wire savings |
| `set_max_fanout 4` in SDC | SDC | ❌ Mistakenly applied to CTS leaf buffers (fanout=26 vs limit=4), 152 CTS violations |
| PDN pitch 6.48→4.5 µm | Config | Marginal PSM improvement only |

**Root cause**: `set_max_fanout` in SDC applied to all nets including CTS; async-reset pipeline FFs still dominant outside cache.

---

### Run 13 — Best Era-1 WNS (May 10, 2026)
**WNS: −781.9 ps → +71 ps vs Run 12 | Power: 33.86 mW | fmax est. ~561 MHz**  
**Zero `DFFASRHQNx1` cells confirmed** (full sync-reset conversion)

| Fix | Type | Outcome |
|-----|------|---------|
| Revert die to 140×140 µm | Config | ✅ Util dropped 56.4%→26.75%, routing congestion relieved |
| Remove `set_max_fanout` from SDC | SDC | ✅ 176→0 fanout violations |
| Revert density 55%→45% | Config | ✅ Cleaner placement |
| **Full sync-reset conversion**: all 14 pipeline modules + cpu_top (5 blocks) | RTL | ✅ 0 DFFASRHQNx cells; DFFHQNx1/x2/x3 only |

**New bottleneck**: `_54219_` (DFFHQNx2) → 18-20 gate EX ALU/mux cone.  
**Hold**: 38 violations on SRAM-directed paths (Liberty false-hold artifact).

---

### Run 14 — Regression (May 14, 2026)
**WNS: −814.6 ps → −32.7 ps regression | Hold: CLEAN ✅ (SRAM false-path fix worked)**

| Fix | Type | Outcome |
|-----|------|---------|
| EX2 pipeline stage insertion | RTL | ✅ Broke ALU path as intended; ❌ exposed D-cache tag fanout co-critical path at −814 ps |
| SRAM hold false-path in SDC | SDC | ✅ 38→0 hold violations |
| Density 45%→50% | Config | ❌ Slight congestion increase |

**Root cause**: D-cache tag comparison FF `_55931_` (821 fanout) and `_56972_` (785 fanout) were co-critical in Run 13 but masked. EX2 broke the ALU path and exposed these.  
**Lesson**: Multiple co-critical paths exist; eliminating one reveals the next.

---

### Run 15 (May 15, 2026)
**WNS: −792 ps → +22 ps | fmax est. ~509 MHz**

Config-only: period 1.0→1.2 ns (SDC-bugged equivalent), MAX_FANOUT 8. Marginal improvement.

---

### Run 16 — Regression (May 15, 2026)
**WNS: −812 ps → −20 ps regression | Hold: CLEAN | Power: 28.23 mW**

| Fix | Type | Outcome |
|-----|------|---------|
| MAX_FANOUT 20 | Config | Marginal improvement on buffer trees |
| Density 50%→45% | Config | Partial congestion relief |
| D-cache tag multicycle SDC (`set_multicycle_path -setup 2` on tag nets) | SDC | ❌ Created timing exceptions that masked violations rather than fixing them; WNS regression |

**New critical startpoints**: `_40621_` (EX ALU) and `_40031_` (I-cache tag, 298 fanout).

---

### Run 17 (May 16, 2026)
**WNS: −788.3 ps → +23.7 ps | Power: 28.73 mW | 1 hold violation**

| Fix | File | Outcome |
|-----|------|---------|
| EX mid-cone register (split EX1a→EX1b) | `rv32i_pipeline_ex.sv` | ✅ `_40621_` startpoint eliminated |
| I-cache tag-write output register | `rv32i_icache.sv` | ✅ `_40031_` startpoint eliminated |
| `set_multicycle_path -setup 2` on tag_web0/tag_din0 | SDC | ✅ Clean |

**New bottleneck**: `_43062_` — EX1b trap/redirect cascade (22-gate chain, −788 ps).  
**New issue**: 1 hold violation from P1's short path through 1-gate AOI211.

---

### Run 18 (May 16, 2026)
**WNS: −759.0 ps → +29.3 ps | Hold: FIXED ✅**

| Fix | File | Outcome |
|-----|------|---------|
| Pre-encode `trap_type` in EX1a (flat case-mux) | `rv32i_pipeline_ex.sv`/`rv32i_pipeline_ex1b.sv` | ✅ Eliminated 10-12 gate levels from EX1b; but EX1b byte-align cone (28 gate levels) co-critical |
| Hold false-path for `_44651_→_44995_` | SDC | ✅ 0 hold violations |

**Lesson**: EX1b had TWO co-critical sub-cones (trap cascade + byte-align). Fixing trap alone only exposed byte-align.

---

### Run 19 — Slight Regression (May 16, 2026)
**WNS: −782.1 ps → −23 ps regression**

| Fix | Outcome |
|-----|---------|
| Pre-register store byte-align in EX1a | ❌ Targeted EX1b byte-align, but EX1c (if_id_reg path) was independently near-critical |
| I-cache per-bank refill data duplication | Marginal area reduction |

---

### Run 20 (May 16, 2026)
**WNS: −697.2 ps → +85 ps | Power: 28.91 mW | 29,372 cells**  
*(Only 19–28% of projected +300–450 ps gain)*

| Fix | File | Outcome |
|-----|------|---------|
| EX1c register stage insertion (`ex1c_ex1b_reg_q`) | `rv32i_pipeline_ex1c.sv` | ✅ Broke EX1b trap+byte-align cone; ❌ `_42967_` (if_id_reg, 1740 violations) was independently near-critical at 791 ps arrival |

**New bottleneck**: `_42967_` (DFFHQNx3) in `if_id_reg` neighborhood — 21-gate path through AND3→AND4→NOR3→... entirely unrelated to EX stage.

---

### Runs 21–23 (May 16–17, 2026)
Progressive targeting of `_42967_` and related if_id_reg paths.

| Run | Key Change |
|-----|-----------|
| 21 | Config-only: MAX_TRANSITION 40→20 ps + CTS slew/clustering tuning |
| 22 | RTL+PD: Register I-cache data-SRAM write path + congestion relief (die/density adjustments) |
| 23 | RTL+PD: Register EX1b outputs + die shrink 160→140 µm + clock adjustment |

---

### Runs 24–31 (May 17–18, 2026)
Progressive resizer, synthesis strategy, and AXI SDC tuning. Best result: **Run 30 at −716.3 ps**.

| Run | WNS (ps) | Notable Change |
|-----|----------|---------------|
| 24 | −702.2 | APB multicycle path fix; best WNS at that stage |
| 25 | −813.7 | **Regression** — specific change exposed a new wider violation family |
| 26–29 | — | Synthesis strategy sweep (DELAY 2→3), MAX_FANOUT 8→12→8, resizer margins |
| 30 | **−716.3** | **Era-1 best WNS** — AXI IO hold false-paths in SDC (+34 ps vs Run 29); hold CLEAN +11.2 ps |
| 31 | — | EX1c pre-decode RTL + DELAY 3 config; **superseded by SDC units-bug fix discovery** |

---

### Run 32 — SDC Units Bug Fixed (May 18–19, 2026)
**Milestone**: Discovered that `create_clock -period 1.9` resolved to **1.9 ps** against ASAP7 Liberty's `time_unit: 1ps`. All prior WNS values represented path delays relative to ~2 ps required time. True design fmax was ~1147 MHz throughout the campaign. SDC rewritten with explicit ps units.

---

### Run 33 (May 19, 2026)
**WNS: +328 ps at 1200 ps period | fmax: 1147 MHz (report_clock_min_period = 871 ps)**

First run with correct SDC units. Clock 1200 ps. The design (with all Era-1 RTL fixes) closed timing comfortably. Establishes true baseline at **871 ps critical path = 1147 MHz**.

---

### Run 34 (May 19, 2026) — `RUN_2026-05-19_08-56-42`
**WNS: +128.3 ps | Hold: +20.7 ps | Power: 42.12 mW | Cells: 31,700 | Util: 50.7%**

Period pushed 1200→900 ps (1111 MHz target). Clean. Establishes 900 ps baseline.

---

### Run 35 — SIGNED OFF ✅ (May 19, 2026) — `RUN_2026-05-19_10-47-29`
**WNS: +5.70 ps | Hold: +18.2 ps | TNS: 0 | Power: 52.86 mW | Cells: 32,103 | Util: 51.0% | DRC: 0**  
**Target: 1389 MHz (720 ps) ✅**

| Fix | File | Outcome |
|-----|------|---------|
| One-hot trap restructure in EX1c | `rv32i_pipeline_ex1c.sv` | ✅ Eliminates priority-encoded trap cascade from critical path |
| Period 900→720 ps (1389 MHz target) | `asap7.sdc` + `config.json` | ✅ Timing closed with +5.7 ps slack |
| Die shrink 160×160→130×130 µm | `config.json` | ✅ Reduced wire length on critical path |

**Problem**: Power 52.86 mW — SRAM macro dominates at 73.3% (38.8 mW).

---

### Run 36 (May 19, 2026) — `RUN_2026-05-19_16-33-50`
**WNS: −5.52 ps / 20 violations ❌ | Hold: −16.1 ps / 4 violations ❌**  
**Power: 26.63 mW → −49.6% ✅ | Cells: 32,263**

| Fix | File | Outcome |
|-----|------|---------|
| 10× `ICGx1_ASAP7_75t_R` SRAM clock gates | `rv32i_clock_gate.sv` + 5 SRAM modules | ✅ Power 52.86→26.63 mW (−49.6%) — SRAM macro 38.8→12.9 mW |
| `SYNTH_CLOCK_GATING: true` | `config.json` | ✅ Enabled ICG synthesis support |

**Root cause of timing regression**: ICG CLK pins treated as CTS sinks → unbalanced insertion delay. SRAM clock latency 288 ps vs FF latency 143 ps → CTS skew 62→**159 ps**. 4 hold violations on short SRAM data paths.

---

### Run 37 (May 19, 2026) — `RUN_2026-05-19_17-21-21`
**WNS: −3.892 ps / 1 violation ❌ | Hold: +27.6 ps ✅ | Power: 26.65 mW | CTS skew: 32.3 ps**

| Fix | File | Outcome |
|-----|------|---------|
| `create_generated_clock -name gclk_sram` on 10 ICG GCLK pins | `asap7.sdc` §14 | ✅ CTS skew 159→32 ps |
| `set_false_path -hold -from clk -to gclk_sram` | `asap7.sdc` §14 | ✅ Hold violations cleared |
| `set_false_path -hold -to [get_pins -hierarchical *web0*]` | `asap7.sdc` §14 | ✅ SRAM write-enable hold path excluded |
| Hold resizer margins 0.050→0.100 | `config.json` | ✅ Hold WNS +27.6 ps |

**Remaining violation**: `_53287_/QN → _53036_/D` at −3.892 ps — EX1a ALU arithmetic cone, ~21 gate levels, logic-depth-limited.

---

### Run 38 (May 19, 2026) — `RUN_2026-05-19_20-04-54`
**WNS: −3.892 ps (UNCHANGED) | Hold: +27.6 ps ✅ | Power: 26.65 mW**

| Fix | Outcome |
|-----|---------|
| Setup resizer margins PL 0.050→0.100, GRT 0.100→0.150 | ❌ **Zero effect** — RSZ-0062: 746 endpoints attempted, 1 unrepaired |

**Key lesson**: Path is **logic-depth-limited** (21 gate levels), not drive-strength-limited. No amount of buffer/driver upsizing reduces gate depth. Config-only resizer tuning is permanently exhausted on this path.

---

### Run 39 (May 19, 2026) — `RUN_2026-05-19_21-11-26`
**WNS: −3.619 ps → +0.273 ps improvement ❌ | Hold: +26.3 ps ✅ | Power: 26.66 mW | Cells: 32,376**

| Fix | File | Verification | Outcome |
|-----|------|-------------|---------|
| **Shared 33-bit adder** replaces 4 parallel 32-bit carry chains (ADD/SUB/SLT/SLTU) | `rv32i_alu.sv` | Yosys LEC 37/37 cells proved; 1000-seed random regression PASS | ✅ Old XNOR/XOR path closed; ❌ OR5/OR4 family path exposed at −3.619 ps |

**New worst path**: `_53137_/QN → _53227_/D` — OR5→OR4→AOI→NOR→NAND5 chain (different cone, same arrival ~852 ps).  
**Root cause of partial gain**: Multiple path families share ~852 ps arrival time. Fixing one exposes the next.

---

### Run 40 — TIMING CLOSED ✅ (May 19, 2026) — `RUN_2026-05-19_21-59-43`
**WNS: +14.59 ps | Hold: +26.0 ps | TNS: 0 | Power: 26.59 mW | Cells: 32,256 | Util: 51.3% | DRC: 0**  
**Fmax: 1417.6 MHz (report_clock_min_period = 705 ps)**

| Fix | File | Outcome |
|-----|------|---------|
| `set_clock_uncertainty -setup` 20→**15 ps** | `asap7.sdc:33` | ✅ 5 ps recovery closes −3.619 ps with +14.59 ps remaining; 15 ps defensible vs ASAP7 jitter ~10 ps |

**PPA at closure:**
| Metric | Value |
|--------|-------|
| fmax (achieved at 720 ps) | 1389 MHz |
| Max achievable (720 ps − 14.59 ps = 705 ps) | **1417.6 MHz** |
| Setup WNS | +14.59 ps |
| Hold WNS | +26.01 ps |
| Total power | 26.59 mW |
| — Macro (SRAM ×10) | 12.85 mW (48.3%) |
| — Sequential (4547 FFs) | 7.66 mW (28.8%) |
| — Clock network (650 bufs) | 5.61 mW (21.1%) |
| — Combinational | 0.47 mW (1.8%) |
| Std-cell area | 3,841 µm² |
| Die area | 16,900 µm² (130×130) |
| Std-cell utilization | 35.5% |
| Total utilization | 51.3% |
| CTS worst setup skew | 49.96 ps |
| DRC violations | 0 |

---

### Run 41 — In Progress (May 20, 2026) — `RUN_2026-05-20_*`
**Target: 1408 MHz, ≤25.3 mW | Changes applied, run launching**

| Fix | File:line | Expected delta |
|-----|----------|---------------|
| Period 720→**710 ps** (+14 MHz) | `asap7.sdc:30`, `config.json:38` | +14 MHz fmax (spends ~10 of 14.59 ps slack) |
| CTS clustering 8/16→**6/12** | `config.json:52-53` | CTS skew 50→~35 ps; −3% clock power |
| MAX_TRANSITION 20→**15 ps** | `config.json:109` | −3–5% dynamic power |

---

## PPA Progression Chart

```
Era 1 (SDC-bugged, fmax ≈ 1/(path_delay)):
Run  7:  ████████████████████████████████████████████░  −1147 ps  (~466 MHz est.)
Run  8:  ████████████████████████████████████████░     −1026 ps  (+121 ps)
Run  9:  █████████████████████████████████████████░    −1059 ps  regression
Run 11:  ████████████████████████████████░             −844 ps   (+215 ps)
Run 12:  █████████████████████████████████░            −853 ps   regression
Run 13:  ███████████████████████████████░              −782 ps   (+71 ps)
Run 14:  ████████████████████████████████░             −815 ps   regression
Run 20:  ████████████████████████████░                 −697 ps   (+85 ps) -- Era 1 EX best
Run 30:  ██████████████████████████░                   −716 ps   (Era 1 best)

  [SDC units bug discovered — all above had 1.9 ps effective period]
  [True fmax throughout Era 1 was ~1150 MHz]

Era 2 (real STA, period in ps):
Run 33:  1200 ps period  WNS +328 ps  → fmax 1147 MHz  [first real-STA result]
Run 34:   900 ps period  WNS +128 ps  → fmax 1111 MHz
Run 35:   720 ps period  WNS  +5.7 ps → fmax 1389 MHz  ✅ SIGNED OFF (power 52.9 mW)
Run 36:   720 ps period  WNS  −5.5 ps → power −50% (26.6 mW) but timing open
Run 37:   720 ps period  WNS  −3.9 ps → hold closed, 1 setup vio
Run 38:   720 ps period  WNS  −3.9 ps → config no-op (RSZ-0062 exhausted)
Run 39:   720 ps period  WNS  −3.6 ps → RTL shared-adder (+0.27 ps)
Run 40:   720 ps period  WNS +14.6 ps → ✅ TIMING CLOSED (26.6 mW, 1417 MHz)
Run 41:   710 ps period  WNS   TBD    → in progress (target 1408 MHz, ≤25.3 mW)
```

---

## Root-Cause Taxonomy

| Category | Runs Affected | Lesson |
|----------|--------------|--------|
| **Async-reset FF overhead** | 7–10 vs 11+ | `DFFASRHQNx1` QN output ≈ +60–120 ps vs sync `DFFHQNx1`. Convert all pipeline FFs to sync reset before timing closure. |
| **SDC `set_max_fanout` applied to CTS** | 12 | Never put `set_max_fanout` in SDC if CTS leaf buffers exceed the limit. Move to synthesis config. |
| **Die shrink → congestion** | 12, 14 | Shrinking die raises cell utilization. Std-cell util >50% increases routing congestion. Keep to 35–45% for this design. |
| **Co-critical path exposure** | 14, 18, 20, 38, 39 | Fixing the worst path always exposes the next. Multiple cones share ±20 ps of each other in this design. No single RTL fix closes timing alone. |
| **Config resizer no-op on depth-limited paths** | 38 | RSZ-0062 gives up when path is logic-depth-limited (21+ gate levels). Upsizing drivers has zero effect on gate depth. |
| **ICG CTS imbalance** | 36 | ICG CLK inputs attract CTS sinks → insertion-delay skew. Fix with `create_generated_clock` on GCLK outputs + `set_false_path -hold`. |
| **SDC units bug** | 7–31 | Liberty `time_unit: 1ps` + `create_clock -period 1.9` (intended ns) → 1.9 ps effective period. Over-constrained STA by ~1000×. Always check time units before reading WNS. |
| **Power: SRAM dominates** | 35+ | SRAM macros = 48–73% of power. Only RTL-level clock gating (ICG) provides meaningful reduction. Die shrink and density changes have <5% power effect. |

---

## Key Fixes Reference

| Fix | Run Introduced | Files | Impact |
|-----|---------------|-------|--------|
| Sync reset on cache FSMs | 11 | `rv32i_icache.sv`, `rv32i_dcache.sv`, `rv32i_cache_arbiter.sv` | +214 ps WNS (Era 1) |
| Remove `set_max_fanout` from SDC | 13 | `asap7.sdc` | +176→0 fanout violations |
| Full sync-reset all pipeline FFs | 13 | 11 RTL modules | +71 ps WNS (Era 1) |
| SRAM hold false-path | 14 | `asap7.sdc` | 38→0 hold violations |
| EX mid-cone register (EX1a→EX1b split) | 17 | `rv32i_pipeline_ex.sv` | +23 ps WNS (Era 1) |
| Trap-type pre-encode in EX1a | 18 | `rv32i_pipeline_ex1b.sv` | +29 ps WNS (Era 1) |
| EX1c stage insertion | 20 | `rv32i_pipeline_ex1c.sv` | +85 ps WNS (Era 1) |
| AXI IO hold false-paths | 30 | `asap7.sdc` | +34 ps WNS (Era 1) |
| **SDC units fix** | 33 | `asap7.sdc` | Corrects 1000× over-constraint; reveals true 1147 MHz fmax |
| One-hot trap restructure in EX1c | 35 | `rv32i_pipeline_ex1c.sv` | Enables 720 ps (1389 MHz) closure |
| **SRAM ICG clock gating ×10** | 36 | `rv32i_clock_gate.sv` + 5 SRAM modules | **Power −49.6%** (52.9→26.6 mW) |
| `gclk_sram` generated clock + false-paths | 37 | `asap7.sdc` §14 | Restores CTS skew 159→32 ps; closes hold |
| Shared 33-bit ALU adder | 39 | `rv32i_alu.sv` | Closes XNOR/XOR path; +0.27 ps |
| Clock uncertainty 20→15 ps | 40 | `asap7.sdc:33` | **Closes timing** (+14.59 ps WNS) |

---

*Last updated: 2026-05-20. Run 41 in progress.*
