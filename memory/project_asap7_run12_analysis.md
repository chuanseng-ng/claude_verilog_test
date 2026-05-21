# ASAP7 Run 12 Full PPA Analysis

**Run Directory**: `pnr/asap7/runs/RUN_2026-05-09_18-28-12`
**Date**: 2026-05-09
**Result**: REGRESSION vs Run 11 — die shrink strategy failed

---

## Metrics Summary

| Metric | Run 11 | Run 12 | Delta | Status |
|--------|--------|--------|-------|--------|
| Setup WNS (ps) | -844.7 | -853.41 | -8.7 | WORSE |
| Setup TNS (ps) | -2,347,619 | -2,569,480 | -221,861 | WORSE |
| Setup violations | 4,230 | 4,251 | +21 | WORSE |
| Hold WNS (ps) | -2.43 | -19.42 | -16.99 | WORSE |
| Hold violations | 4 | 54 | +50 | WORSE |
| Achievable fmax (MHz) | ~542 | ~539 | -3 | WORSE |
| Max-fanout violations | 150 | 176 | +26 | WORSE |
| PSM violations | 2,175,434 | 1,736,573 | -438,861 | Better |
| Power total (mW) | ~32 | 32.33 | +0.33 | Flat |
| Total area (µm²) | 7,352 | 7,447.52 | +95.52 | Slightly worse |
| Stdcell area (µm²) | 3,841 | 3,936.32 | +95.32 | Slightly worse |
| SRAM macro area (µm²) | 3,511 | 3,511.2 | 0 | Same |
| Core utilization (%) | 37.6 | 56.4 | +18.8 | Much higher |
| Die area (µm²) | 22,500 | 15,625 | -6,875 | Smaller |
| Routing DRC | 0 | 0 | 0 | Same (clean) |
| Antenna violations | 0 | 0 | 0 | Same (clean) |
| DRT-0074 errors | 374 | 373 | -1 | Same |

### vs Pre-Run Projection

| Metric | Projected | Actual | Assessment |
|--------|-----------|--------|------------|
| Setup WNS | -500 to -600 ps | -853 ps | MISSED by 250-350 ps |
| fmax | 600–640 MHz | ~539 MHz | MISSED — regression |
| Core utilization | ~55% | 56.4% | Matched |
| PSM violations | ~0–50k | 1,736,573 | MISSED by 1.7M |

---

## Completion Status

- **Stages completed**: 48/48 (full flow)
- **Flow**: Completed without abort
- **DRC/LVS**: DRC skipped (known limitation — Magic/KLayout DRC disabled for ASAP7), LVS skipped
- **GDS**: Not generated (GDS steps skipped per configuration)
- **Errors**: DRT-0074 (373 port access point failures — known ASAP7 issue, non-fatal), PSM-0069 (grid connectivity)

---

## Timing Analysis

### Setup (Max) Timing

- **WNS**: -853.41 ps
- **TNS**: -2,569,480 ps
- **Violations**: 4,251
- **Worst clock skew**: 50.9 ps
- **Achievable fmax**: 1000 / (1000 + 853.41 / 1000) = ~539 MHz

#### Worst Setup Critical Path

```
Startpoint: _54861_ (DFFASRHQNx1_ASAP7_75t_R, clknet_leaf_90_clk_i)
Endpoint:   _54985_ (DFFASRHQNx1_ASAP7_75t_R, clknet_leaf_84_clk_i)
Path Group: PIPELINE
Path Type:  max (setup)

Data arrival:  952.05 ps
Data required:  98.65 ps
Slack:        -853.41 ps  (VIOLATED)
```

**Path description**: The worst path is a pure std-cell logic chain, ~16 combinational stages:
`FF (DFFASRHQNx1 QN) → HB4xp67 (hold buf) → HB1xp67 → HB4xp67 → NAND5xp2 → HB1xp67 → OAI21xp33 → NOR5xp2 → OAI21xp5 → A2O1A1O1Ixp25 → AOI21xp5 → OAI21x1 → A2O1A1Ixp33 → A2O1A1Ixp33 → A2O1A1Ixp33 → AOI21xp5 → OA31x2 → OAI21xp33 → OAI22xp5 → FF D`

The critical path data arrival is 952 ps. With a 1000 ps clock period and ~98 ps clock delivery overhead (clock tree + library setup), there is only ~100 ps of slack remaining budget. The full combinational logic must complete in ~850 ps — currently failing by 853 ps.

**Observation**: FF `_54478_` (the DFFASRHQNx1 that was the bottleneck in Run 11 driving all 4,230 violations) is now the 2nd worst path startpoint. The sync reset RTL change successfully moved `_54478_` off the absolute worst path, but `_54861_` (another DFFASRHQNx1) became the new worst — indicating the async-reset FF topology (slow QN output) is a systemic problem across all pipeline register FFs, not just cache FSMs.

### Hold (Min) Timing

- **Hold WNS**: -19.42 ps (worsened from -2.43 ps in Run 11)
- **Hold TNS**: -337.79 ps
- **Hold violations**: 54 (up from 4 in Run 11)
- **R2R hold WNS**: -1.32 ps

**Root cause**: The PDN pitch change (6.48 → 4.5 µm) altered insertion delay balance across the clock tree. With tighter PDN straps, some clock paths now arrive earlier at endpoints creating hold violations. The post-GRT resizer could NOT close hold checks: `RSZ-0064: Unable to repair all hold checks within margin`.

---

## Power Analysis

| Component | Power (mW) |
|-----------|-----------|
| Internal (dynamic) | 31.06 |
| Switching | 1.27 |
| Leakage | 0.0013 |
| **Total** | **32.33** |

Power is essentially unchanged from Run 11 (~32 mW). SRAM macros dominate at ~26–27 mW internal (SRAM Liberty power models are switching-activity independent).

---

## Area Analysis

| Category | Count | Area (µm²) |
|----------|-------|-----------|
| SRAM Macros | 10 | 3,511.20 |
| Tap cells | 2,100 | 61.24 |
| Tie cells | 2,220 | 97.10 |
| Buffers (data) | 7,591 | 488.59 |
| Clock buffers | 184 | 35.37 |
| Timing repair buffers | 5,647 | 433.68 |
| Inverters | 493 | 22.92 |
| Clock inverters | 79 | 13.87 |
| Sequential cells | 3,759 | 1,285.02 |
| Multi-input combo | 15,580 | 1,498.53 |
| **Total** | **37,663** | **7,447.52** |

FF breakdown: 2,116 DFFASRHQNx1 (async reset), 1,406 DFFHQNx1, 214 DFFHQNx2, 23 DFFHQNx3.
The 2,116 async-reset FFs represent the pipeline register banks — these are the primary timing bottleneck due to slow QN output.

---

## Physical Quality

- **Routing DRC**: 0 (DRT clean)
- **Antenna violations**: 0
- **DRT-0074 errors**: 373 (known port access point issue — non-fatal, routing complete)
- **PSM power grid violations**: 1,736,573 (VDD: 868,390, VSS: 868,183)
  - Reduced 20% from Run 11 (2,175,434) but still catastrophic
  - Root cause: PSM-0039 warnings show unconnected tapcells near macro boundary at x≈84.8 µm — physical gap in VDD/VSS rails near SRAM macro edges
- **Max-fanout violations**: 176 (all are clock buffers)
  - 152 clock leaf buffers: fanout=26, limit=4, slack=-22
  - 14 clock level-4 buffers: fanout=10–14, slack=-5 to -10
  - Only 10 are data path FFs: `_54322_`, `_54319_`, `_53863_`, etc. with fanout=5–8

---

## Fanout Violation Root Cause

The `set_max_fanout 4` in `asap7.sdc` is being applied to ALL nets including CTS clock buffers. CTS inserts buffers to drive large fanouts by design (leaf buffers drive 26 FFs each — normal for ASAP7 CTS). The SDC `set_max_fanout` constraint applies to the STA reporting, causing 152 false violations on clock leaf buffers.

**Fix**: Remove `set_max_fanout` from the SDC file entirely. `MAX_FANOUT_CONSTRAINT: 4` in `config.json` controls resizer behavior for DATA paths correctly without affecting CTS.

---

## Timing Progression Through Flow

| Stage | Setup WNS (ps) | Hold WNS (ps) |
|-------|---------------|---------------|
| Post-placement (stamidpnr) | -9,437 | -9,249 |
| Post-CTS (stamidpnr-1) | -1,478 | -212 |
| Post-GRT (stamidpnr-2) | -1,102 | 0 (clean) |
| Post-DRT (stamidpnr-3) | **-853** | **-19.4** |

Post-GRT to post-DRT: setup IMPROVED from -1,102 to -853 ps (post-DRT resizer helped 249 ps). Hold DEGRADED from clean to -19.4 ps after DRT — insertion delay changes from actual routing caused hold violations.

---

## Root Cause Summary — Why Die Shrink Failed

1. **Congestion increase dominated wire-length reduction**: The 125×125 µm die raised core utilization from 37.6% to 56.4%. At >50% utilization with large SRAM macros occupying ~27% of core, routing congestion significantly increased. The routing tool was forced to use longer detour paths, canceling the benefit of shorter average wire distances.

2. **set_max_fanout 4 misapplied to CTS**: SDC constraint applied to clock network as well as data, creating 152 false violations. Does NOT affect actual timing — these are reporting artifacts — but inflates violation counts and may have caused unnecessary resizer buffering.

3. **PDN pitch change broke hold timing**: Tighter PDN straps (4.5 µm) changed the insertion delay profile across the clock tree, creating 54 hold violations (was 4).

4. **DFFASRHQNx1 systemic issue**: Sync reset fix only moved `_54478_` off worst path — `_54861_` (another async-reset FF) immediately became worst. The entire pipeline register bank uses DFFASRHQNx1 with inherently slow QN transition.

---

## Recommended Run 13 Changes

### Priority 1 — Immediate (Critical)
1. **Revert die to 140×140 µm**: `DIE_AREA: [0, 0, 140, 140]`, `CORE_AREA: [5, 5, 135, 135]`
   - Core area: 130×130 = 16,900 µm², utilization ~44% — matches Run 11 spacing but shorter wires than 150×150
2. **Adjust PL_TARGET_DENSITY_PCT to 46**: Matches ~44% utilization target
3. **Remove `set_max_fanout` from SDC**: Delete the `set_max_fanout` line from `asap7.sdc` entirely

### Priority 2 — High Value
4. **Keep PDN pitch at 4.5 µm**: Keep the Run 12 improvement (even if modest)
5. **Keep PDN_CONNECT_MACROS_TO_GRID: true**
6. **Investigate tapcell gap at x≈84.8 µm**: Add `MACRO_PLACEMENT_HALO` or adjust macro placement to close PSM-0039 tapcell gap

### Priority 3 — RTL (Longer-term)
7. **Convert pipeline register FFs to sync reset**: Replace DFFASRHQNx1 (async) with DFFHQNx2/x3 (sync, higher drive) in `rv32i_pipeline_*.sv`. This removes the slow QN output (~60 ps saved per critical FF) and reduces reset sensitivity. Estimated impact: 80–150 ps WNS improvement.

### Expected Run 13 Outcome
- WNS: -750 to -800 ps (from -853 ps)
- fmax: ~555–570 MHz
- Hold: Should close (smaller die + same PDN pitch)
- Fanout violations: Should drop to 0 or near-0 (SDC fix)
- PSM: Should remain ~1.7M (structural issue requires tapcell fix)
