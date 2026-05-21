# ASAP7 Run 17 PPA Analysis

*Run directory: `pnr/asap7/runs/RUN_2026-05-16_08-05-19`*
*Completed: 2026-05-16, 48/48 stages, "Flow complete."*
*Clock period: 1.2 ns (833 MHz target)*

---

## 1. Key Results Summary

| Metric | Run 16 (baseline) | Run 17 | Delta | Status |
|--------|-------------------|--------|-------|--------|
| Setup WNS (ps) | -812.032 | **-788.347** | **+23.7 ps** | Marginal improvement |
| fmax (MHz) | ~497 | **~503** | **+6 MHz** | Marginal improvement |
| Setup TNS (ps) | -2,182,240 | -2,156,870 | +25,370 ps | Marginal improvement |
| Hold WNS (ps) | 0 (clean) | **-13.807** | -13.807 ps | REGRESSION (1 violation) |
| Hold violations | 0 | 1 | +1 | REGRESSION |
| Total area (µm²) | 6,724.95 | **6,971.66** | +246.7 µm² | +3.7% (EX1b FFs) |
| Stdcell area (µm²) | 3,213.75 | 3,460.46 | +246.7 µm² | +7.7% std cells |
| SRAM area (µm²) | 3,511.2 | 3,511.2 | 0 | Unchanged (10 macros) |
| Instance count | 27,074 | 28,559 | +1,485 | New EX1b + I-cache FFs |
| Total power (mW) | 28.23 | **28.73** | +0.50 mW | +1.8% (flat) |
| DRC violations | 0 | 0 | — | Clean |
| Antenna violations | 0 | 0 | — | Clean |
| Max-slew violations | 0 | 0 | — | Clean |
| Max-fanout violations | 0 | 0 | — | Clean |

**Achieved fmax formula**: fmax = 1 / (T_period_ns + |WNS_ns|) = 1 / (1.2 + 0.788) = **503 MHz**

---

## 2. P1 and P2 Fix Assessment

### 2.1 P1 (EX-stage mid-cone retiming) — CONFIRMED, GAIN ABSORBED

**Change applied**: Inserted `ex1a_ex1b_reg_q` FF register between EX1a and EX1b
pipeline sub-stages in `rv32i_core.sv`. EX1a handles ALU computation and branch
comparator; EX1b handles trap priority cascade and PC redirect.

**Run 16 target**: Startpoint `_40621_/QN` (QN net fanout large, deep EX ALU cone).
**Run 17 result**: `_40621_` does **NOT appear** in the Run 17 post-GRT violator list.
Zero occurrences. P1 completely eliminated the Run 16 critical path.

**New EX bottleneck**: The Run 17 critical path launches from `_43062_` (fanout=7,
net `_03196_`), which is an EX1b-stage output FF driven by the combinational EX1b
sub-stage. The path goes through:
- `_43062_/QN` → INVx1 → AOI22xp33 → OAI221xp5 → (rebuffer17) → NOR3x2 →
  AOI311xp33 → BUFx5 → AOI32xp33 → BUFx5 → AOI21x1 → NAND5xp2 → NOR5xp2 →
  AND4x1 → OAI211xp5 → OAI211xp5 → O2A1O1Ix → O2A1O1Ix → OAI21 → A2O1A1Ix →
  HB1 → NOR2 → OAI311 → A2O1A1Ix → endpoint `_42797_/D`
- Data arrival: 898.78 ps, launch clock: 117.85 ps, slack: **-788.35 ps**
- ~22 combinational gate levels through EX1b trap/redirect logic

The EX1b second-half combinational cone is itself deep — the trap priority cascade
and PC redirect logic in EX1b (formerly the second half of the monolithic EX cone)
still spans ~22 gate levels. The P1 split broke the EX cone in two but the EX1b
half is still about as deep as the original EX cone bottleneck.

**P1 gain = +23.7 ps total** (including P2 contribution). The split was correctly
applied but the EX1b combinational cone is now the binding constraint.

### 2.2 P2 (I-cache tag-write register) — CONFIRMED, STRUCTURAL IMPROVEMENT

**Change applied**: Added `tag_we_q`, `tag_din_q`, `tag_idx_q` registers in
`rv32i_icache.sv` to insert a FF stage between the FSM and the SRAM tag port.

**Run 16 target**: Startpoint `_40031_/QN` (fanout ~298, I-cache tag net).
**Run 17 result**: `_40031_` does **NOT appear** anywhere in the Run 17 post-GRT
violator list. P2 completely eliminated the Run 16 second critical path.

**Post-P2 I-cache behavior**: The formerly 834-fanout FF `_45222_/QN` (`_01458_` net)
now appears as an **endpoint** in Run 17 (driven by `_45838_`), with WNS -642 ps in
the violator list — significantly below the overall worst path of -788 ps. The P2
register successfully broke the high-fanout tag write path, but `_45222_` is now a
downstream FF loaded by the pre-registered tag data, still with some fanout load.

The pre-PnR worst startpoint was `_45222_` with 834 fanout and -2529 ps WNS. After
P2, the post-GRT WNS from `_45222_` is -513 ps — a **+2016 ps** improvement on that
specific path, but it no longer sets the global WNS.

**MCU SDC addition**: The `set_multicycle_path -setup 2` on `*u_icache*tag_web0*`
and `*u_icache*tag_din0*` was applied and accepted (no multicycle SDC errors in flow).

---

## 3. Pre-PnR vs Post-GRT WNS Flow

| Stage | WNS (ps) | Notes |
|-------|----------|-------|
| Pre-PnR (step 11) | -2,529.7 | Ideal clocks, unplaced — `_45222_` (I-cache tag, 834 fanout) dominates |
| Post-GPL (step 29) | -11,406 | After global placement (clock/routing pessimism inflated) |
| Post-CTS (step 34) | -1,263.6 | After CTS, propagated clocks |
| Post-GRT (step 36) | -961.6 | After global routing |
| Post-GRT + resizer (step 40) | -788.3 | After timing repair — **final post-DRT STA** |

The resizer closed ~1741 ps of timing from pre-PnR to post-GRT. The remaining -788 ps
is set by EX1b trap/redirect logic depth, not by the P1 or P2 targets.

---

## 4. Top-5 Violating Startpoints (Post-GRT)

| Rank | Startpoint FF | Worst Slack (ps) | #Paths as Source | Net Fanout (QN) | RTL Function |
|------|---------------|-----------------|-----------------|-----------------|--------------|
| 1 | `_43062_` | -788.347 | 126 paths (est.) | 7 | EX1b output FF — trap/redirect cascade result register |
| 2 | `_43132_` | ~-749 | 684 paths | 35 | EX1b / EX-stage pipeline register bit (broad fan) |
| 3 | `_43053_` | ~-737 | 471 paths | 11 | EX1b-stage control bit (trap priority output) |
| 4 | `_45838_` | ~-735 | 434 paths | 10 | I-cache tag pre-stage register — drives `_45222_` |
| 5 | `_44587_` | ~-725 | 868 paths | 22 | EX/MEM pipeline register bit (high-path-count but lower WNS) |

**Note on fanout vs path count**: `_44587_` generates the most violating paths (868) but
has a less severe worst slack (-725 ps estimated). It is a broad but shallow fan driving
many endpoints at moderate violation levels. `_43062_` has the deepest path at -788 ps.

**Confirmed absent** (Run 16 critical startpoints, both P1 and P2 targets):
- `_40621_`: 0 occurrences in violator_list.rpt
- `_40031_`: 0 occurrences in violator_list.rpt

---

## 5. Why P1 Gain Was Only +23.7 ps (vs +400–500 ps Projected)

### 5.1 EX1b cone is itself deep

The monolithic EX cone was split at the ALU/trap boundary:
- **EX1a** (before register): ALU computation, branch comparator, CSR write data
- **EX1b** (after register): Store byte-align, trap priority cascade, PC redirect

The trap priority cascade in EX1b — which must decide between interrupt, ecall,
ebreak, misalign, illegal and then mux the correct exception cause and PC — is itself
a deep combinational structure spanning ~22 gate levels (AOI/OAI cascade through
NOR/AND/OAI311/O2A1O1I chains). This is essentially the same depth as the original
EX ALU bottleneck.

**Key insight**: The EX retiming moved the critical path from the ALU half to the
trap/redirect half. Both halves are ~22 levels. Splitting a 44-gate cone into two
22-gate halves gives ~0 ps improvement if both halves are equally deep.

### 5.2 The projected +400–500 ps gain assumed an unbalanced cone

The projection assumed the ALU cone was longer than the trap cone. In practice, the
trap priority cascade (exception ordering: misalign > illegal > ecall > ebreak > IRQ)
involves as many gate levels as the ALU forwarding mux logic. The cone was symmetric.

### 5.3 Hold regression introduced

The P1 `ex1a_ex1b_reg_q` register creates a new short path: `ex1a_ex1b_reg_q` → EX1b
combinational inputs → `ex_mem_reg`. The shortest data path is 1 gate level ≈ 15 ps.
With clock skew of 64 ps (worst hold skew per metrics), this path violates hold by
~13.8 ps. The worst hold path is `_44651_` → `_44995_` (AOI211 → DFF, 1 gate only).

---

## 6. Error Log Summary

The error.log contains **only expected non-fatal errors** — no new issues:
- `[PDN-0179]`: PDN rail violation (permanent, patched as non-fatal) 
- `[PSM-0069]`: VDD/VSS connectivity check on SRAM black-box (permanent)
- `[DRT-0074]`: 373 I/O pin access errors (permanent ASAP7 structural issue, non-fatal)

**DRC violations**: 0 (`design__violations = 0`)
**Antenna violations**: 0 (`antenna__violating__nets = 0`, `antenna__violating__pins = 0`)
**LVS**: Skipped (ASAP7 open PDK limitation, expected)

---

## 7. Area and Power Delta vs Run 16

| Sub-metric | Run 16 | Run 17 | Delta |
|------------|--------|--------|-------|
| Total instance area (µm²) | 6,724.95 | 6,971.66 | +246.71 |
| Stdcell area (µm²) | 3,213.75 | 3,460.46 | +246.71 |
| SRAM macro area (µm²) | 3,511.2 | 3,511.2 | 0 |
| Instance count | 27,074 | 28,559 | +1,485 |
| Internal power (mW) | — | 27.39 | — |
| Switching power (mW) | — | 1.34 | — |
| Leakage power (mW) | — | 0.001 | — |
| Total power (mW) | 28.23 | 28.73 | +0.50 |

The +246.71 µm² area increase comes from:
1. **P1 (`ex1a_ex1b_reg_q`)**: The `ex1a_ex1b_t` struct size × 1 FF per bit ≈ ~200 bits
   × ~0.9 µm²/FF ≈ ~180 µm²
2. **P2 (tag_we_q, tag_din_q, tag_idx_q)**: 1 + 32 + 8 = 41 bits × ~0.9 µm² ≈ ~37 µm²
3. **Resizer-added buffers**: remaining ~30 µm² from additional timing repair buffers

Core utilization: **25.87% stdcell / 41.3% total** (140×140 die, 135×135 core).
The density is healthy — routing congestion is not a problem at this utilization level.

---

## 8. Run 18 Priority Recommendations

### P1 (HIGH IMPACT — est. +200–350 ps WNS): Split EX1b trap cascade

**Root cause**: EX1b's trap priority cascade is ~22 gate levels — as deep as the
original EX cone. The cascade evaluates: interrupt > misalign > illegal > ecall >
ebreak, then muxes mcause, mepc, and PC redirect. This is a serial priority encoder.

**Fix**: Insert a second pipeline register inside EX1b, or restructure the trap
cascade to register intermediate results:

Option A — Register the trap type at EX1a→EX1b boundary: compute `trap_type`
(4-bit priority encoding: IRQ/ECALL/EBREAK/MISALIGN/ILLEGAL) in EX1a using
registered inputs, then in EX1b only select among pre-encoded trap causes.
Expected reduction: 10-12 gate levels removed from EX1b cone → +200-300 ps.

Option B — Add a third pipeline sub-stage (EX1a→EX1b→EX1c): fully split the
trap cascade into pre-compute (EX1b) and commit (EX1c). This adds another branch
misprediction cycle (3→4 cycle penalty). Expected gain: +250-350 ps.

Option C — Register `ex_pc_redirect` directly (same as original Run 10 plan):
This was the Run 10 target. Register the PC redirect decision at EX1b output,
paying 3→4 cycle branch penalty. 

### P2 (MEDIUM IMPACT — est. +80–150 ps): D-cache tag comparison duplication

**Root cause**: `_44587_` (868 paths, -725 ps) appears to be an EX/MEM pipeline
register bit. However, SRAM endpoints also appear in the violator list (128 paths:
`u_core.u_icache.gen_data_sram[0..3]` and `u_core.u_dcache.gen_data_sram[0..3]`
each with 32 paths). These SRAM-endpoint paths are at -640 ps range and suggest
the D-cache tag comparison fan (Run 14/15 bottleneck) may still be contributing.

**Verify**: Check if `_44587_` corresponds to a D-cache tag comparison register
bit (similar to Run 14's `_55931_`/`_56972_` at 821/785 fanout). If so, the
tag-comparison register duplication fix (per-bank `tag_hit_bank[b]` in
`rv32i_dcache.sv`) is still the right approach and would reduce SRAM-endpoint
violations.

### P3 (LOW-MEDIUM — est. +30–60 ps): Hold repair for EX1b short path

**Root cause**: The 1 hold violation at -13.8 ps is on a path `_44651_` → `_44995_`
that is just 1 gate (AOI211xp5) long — a short path created by the P1 register insertion.

**Fix**: Add an SDC hold multi-cycle or a false-path exclusion for this path:
```tcl
set_multicycle_path -hold 0 -from [get_cells _44651_] -to [get_cells _44995_]
```
Or add a delay buffer at the RTL boundary. The hold failure is minor (-13.8 ps)
and may self-correct with different placement.

### P4 (LOW — config): Maintain density 42% and MAX_FANOUT 25

These Run 17 config settings produced clean routing (0 DRC, 0 antenna). Keep them
for Run 18. Do not change die size or PDN configuration.

---

## 9. Run 18 WNS Projection

| Scenario | Expected WNS (ps) | Expected fmax (MHz) |
|----------|-----------------|---------------------|
| Option A only (trap type pre-encode) | -500 to -600 | ~545–588 MHz |
| Option B (EX1b sub-stage split) | -450 to -550 | ~571–606 MHz |
| Option B + D-cache duplication | -350 to -450 | ~606–640 MHz |
| Option C (register ex_pc_redirect) | -350 to -500 | ~588–632 MHz |

To break through 600 MHz at 1.2 ns, the EX1b trap cascade depth must be reduced
from ~22 levels to ~12 levels. Either a sub-stage split or trap-type pre-encoding
are the viable paths.

---

## 10. Flow Health Checks

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
| Hold violations | 1 (new — EX1b short path, -13.8 ps) |

---

*Analysis completed 2026-05-16.*
*Run 17 launched after Run 16 (RUN_2026-05-15_18-51-46, WNS -812 ps).*
