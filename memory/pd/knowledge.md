# Physical Design Knowledge Base

## ASAP7 PDK — LibreLane Issues and Fixes

### RSZ-0089: Zero Wire RC Values (CRITICAL - will block global placement)

**Root cause**: The ASAP7 tech LEF (`asap7_tech_1x_201209.lef`) has NO `RESISTANCE` or
`CAPACITANCE` attributes in any LAYER definition (M1-M9). LibreLane's `set_rc.tcl` calls
`set_wire_rc -signal -layers` after calling `set_layer_rc` for layers from `LAYERS_RC`.
When `LAYERS_RC` is not set and LEF has no RC data, all layers have R=0, C=0 and
OpenROAD throws RSZ-0089.

**Fix applied**: Modified
`/home/neuromorphic/Downloads/Github/librelane/librelane/scripts/openroad/common/set_rc.tcl`
to detect ASAP7 by checking `STD_CELL_LIBRARY` contains "asap7" and inject ORFS-calibrated
values when `LAYERS_RC` is not set.

**RC values** (from OpenROAD Flow Scripts `platforms/asap7/setRC.tcl`, calibrated against
aes/cva6/ibex/riscv32i):

```tcl
M1: R=7.04175e-02, C=1e-10   (M1 C is near-zero; M1 often blocked from routing)
M2: R=4.62311e-02, C=1.84542e-01
M3: R=3.63251e-02, C=1.53955e-01
M4: R=2.03083e-02, C=1.89434e-01
M5: R=1.93005e-02, C=1.71593e-01
M6: R=1.18619e-02, C=1.76146e-01
M7: R=1.25311e-02, C=1.47030e-01
Via resistances: V1-V3=1.72e-02, V4-V5=1.18e-02, V6-V7=8.20e-03
```

**Why LAYERS_RC in config.json does NOT work**: LibreLane's Python Variable schema does not
register `LAYERS_RC` as a known variable. Unknown variables are silently dropped during
config resolution and do NOT appear in `_env.tcl`. The TCL script's `[info exist ::env(LAYERS_RC)]`
check fails. Must modify the set_rc.tcl directly or register the variable in LibreLane Python.

### PDN-0179: PDN Rail Width Violation (non-fatal after fix)

**Root cause**: Default `FP_PDN_RAIL_WIDTH` (0.072) exceeds ASAP7 M1 WIDTHTABLE constraints.

**Fix applied**:
- `/home/neuromorphic/pdk/asap7/libs.tech/openlane/asap7sc7p5t_SIMPLE/config.tcl`:
  set `FP_PDN_RAIL_WIDTH` = 0.054
- `config.json`: `ERROR_ON_PDN_VIOLATIONS: false`
- `pdn.tcl` patched: `exit 1` changed to warning message so PDN errors are non-fatal

### Process Lifecycle: LibreLane Killed When Agent Shell Exits

**Fix**: Run via tmux detached session so the process survives agent bash session exit.

```bash
tmux new-session -d -s asap7 "cd /home/neuromorphic/Downloads/Github/librelane && nix-shell --run 'python -m librelane ...'"
```

Or use `nohup ... &` with output redirected to a persistent log file.

### LibreLane Resume from Step

Use `-F <StepID>` combined with `--last-run` to resume from a specific step:

```bash
python -m librelane --manual-pdk --pdk-root /home/neuromorphic/pdk \
  -F OpenROAD.GlobalPlacement --last-run config.json
```

Step IDs follow the format: `OpenROAD.GlobalPlacement`, `OpenROAD.CTS`,
`OpenROAD.GlobalRouting`, `OpenROAD.DetailedRouting`, etc.

### RSZ-0090: SDC set_max_transition Misinterpreted as Picoseconds

**Root cause**: ASAP7 liberty files use `time_unit: "1ps"`. SDC `set_max_transition 0.040` is
therefore 0.040 ps (impossibly tight), not 40 ps. OpenROAD warns "Max transition time from SDC
is 0.040ps" and aborts resizing.

**Fix applied**: Removed `set_max_transition` from `pnr/asap7/constraints/asap7.sdc` entirely.
Also changed `set_clock_transition 0.010` → `set_clock_transition 10` (= 10 ps).
Use `MAX_TRANSITION_CONSTRAINT: 40.0` in `config.json` for the 40 ps budget (LibreLane
handles the unit correctly through its own path, unlike raw SDC).

**Rule**: For ASAP7 SDC, all `set_max_transition` / `set_clock_transition` values must be in
picoseconds (1ps time unit). `create_clock -period 1.000` is correct (LibreLane handles ns→ps
internally for clock period; raw SDC timing constraints go through OpenROAD directly).

### OpenROAD.CheckAntennas: C++ Segfault / Assertion Failure

**Root cause**: OpenROAD `ant::AntennaChecker::saveGates` hits `std::vector::operator[]`
bounds assertion failure during parallel processing of ASAP7 routing topology. This is a
tool bug, not a design issue.

**Fix applied**: `--skip OpenROAD.CheckAntennas` in Makefile `librelane-asap7` target.

### Odb.DiodesOnPorts: AttributeError NoneType.connect

**Root cause**: `Odb.PortDiodePlacement` (a sub-step of `Odb.DiodesOnPorts`) crashes with
`AttributeError: 'NoneType' object has no attribute 'connect'` when `GPL_CELL_PADDING: 0`.
The diode placement Python step tries to connect a net object that is None.

**Fix applied**: `--skip Odb.DiodesOnPorts` in Makefile `librelane-asap7` target.

### Full Set of Skip Flags for ASAP7 (as of 2026-04-24)

```makefile
--skip Checker.LintTimingConstructs \
--skip Odb.HeuristicDiodeInsertion \
--skip OpenROAD.RepairAntennas \
--skip Odb.ReportDisconnectedPins \
--skip Checker.DisconnectedPins \
--skip Magic.SpiceExtraction \
--skip Checker.IllegalOverlap \
--skip Odb.CheckDesignAntennaProperties \
--skip Checker.LVS \
--skip OpenROAD.CheckAntennas \
--skip Odb.DiodesOnPorts \
```

### chip-design-pd Agent Usage

The `chip-design-pd:physical-design-orchestrator` agent can autonomously manage the full
LibreLane flow, diagnose step failures, apply fixes, and relaunch. Invoke with full context:
PDK, run directory, log path, all known prior fixes, and the Makefile invocation pattern.
The agent writes to `/tmp/asap7_run2.log` (second run) when it relaunches. Monitor via
`tail -5 /tmp/asap7_run2.log` and `ls runs/<RUN>/` step count.

### PSM-0069 Power Connectivity Warnings (Expected, Non-Blocking)

After PDN generation, expect these warnings — they are non-fatal:
```
[PSM-0069] Check connectivity failed on VDD.
[PSM-0069] Check connectivity failed on VSS.
```
These occur because SRAM black-box macros have no physical VDD/VSS pin geometry in the ASAP7
stub LEF. Set `ERROR_ON_PDN_VIOLATIONS: false` in config.json.

## NanGate45 PDK Notes

- Magic DRC and LVS are permanently blocked (no Magic support for NanGate45)
- KLayout DRC is feasible once detailed routing (DRT) passes
- Gate-level VCD power sim blocked: no NanGate45 Verilog models

## DRT-0074: No Access Point for PIN (I/O pins)

**Symptom**: OpenROAD.DetailedRouting fails during "Start pin access" (BEFORE detailed_route
even starts) with `[ERROR DRT-0074] No access point for PIN/<pinname>` for ALL 373 top-level
I/O pins. OpenROAD exits with non-zero returncode.

**Complete root cause** (determined over 4 runs — read carefully):

### Layer config (correct, not the problem)
ASAP7 PDK defaults `FP_IO_HLAYER=M4` and `FP_IO_VLAYER=M5`. These are confirmed correct —
M4 is HORIZONTAL, M5 is VERTICAL. Setting `FP_IO_HLENGTH/VLENGTH=4.0` makes stub lengths 4µm.

### The ACTUAL root cause: pin width is invalid per WIDTHTABLE
`FP_IO_HTHICKNESS_MULT` default is 2, giving pin width = `2 × 0.024 = 0.048µm = 48 DBU`.
M4/M5 pitch is also 48 DBU. But the M4/M5 **WIDTHTABLE is: 0.024, 0.12, 0.216, 0.312...**
(i.e., 24, 120, 216... DBU). The value 48 DBU is NOT a valid M4/M5 width!

Additionally, with exactly 1 pitch of width, there is a ~50% probability that zero on-grid
tracks fall within the pin rectangle (depends on pin Y/X position relative to track grid
offset). The DRT access point algorithm cannot form any valid via landing, causing DRT-0074.

**Confirmed** by checking the IOPlacement DEF: M4 pins have rect `(-2000,-24)...(2000,24)` =
48 DBU thick. All 373 pins fail, consistent with systematic grid-alignment failure.

### Fix
Set pin thickness multiplier to 5 → valid WIDTHTABLE entry, 2.5 pitches, guaranteed coverage:

```json
"FP_IO_HLENGTH":          4.0,
"FP_IO_VLENGTH":          4.0,
"FP_IO_MIN_DISTANCE":     1.0,
"FP_IO_HTHICKNESS_MULT":  5,
"FP_IO_VTHICKNESS_MULT":  5
```

Result: pin width = `5 × 0.024 = 0.12µm` = 120 DBU = valid M4/M5 WIDTHTABLE entry.
120 DBU / 48 DBU pitch = 2.5 pitches → guaranteed 2+ on-grid tracks inside every pin rect.

### Backup: patch drt.tcl to non-fatal
If DRT-0074 still occurs (e.g. different pin placement scenario), patch
`~/Downloads/Github/librelane/librelane/scripts/openroad/drt.tcl` to wrap `detailed_route`
in a `catch {}` block (same approach as pdn.tcl). This allows write_views to complete even
if some pins remain disconnected. This is now done permanently in the patched drt.tcl.

**Note**: DRT-0074 errors during "Start pin access" cause OpenROAD to abort BEFORE
`detailed_route` runs — so a drt.tcl catch on `detailed_route` does NOT help when the errors
come from pin access init. The catch helps only for errors during routing itself.

**Important for re-runs**: Any change to `FP_IO_HTHICKNESS_MULT` or `FP_IO_HLENGTH/VLENGTH`
affects step 23 (IOPlacement). LibreLane cannot resume from step 39 — a full fresh run from
step 1 is required. The run takes several hours.

**ASAP7 M4/M5 layer geometry**:
- M4: HORIZONTAL, PITCH=0.048µm, WIDTH=0.024µm, WIDTHTABLE=0.024,0.12,0.216...
- M5: VERTICAL,   PITCH=0.048µm, WIDTH=0.024µm, WIDTHTABLE=0.024,0.12,0.216...
- Both: `RIGHTWAYONGRIDONLY`, `RECTONLY` — via access requires on-grid pin overlap
- Pin width MUST be from WIDTHTABLE; 0.048µm is NOT valid; minimum useful value is 0.12µm

**LibreLane variable name reference** (IOPlacement step, `io_layer_variables` in common_variables.py):
- `FP_IO_HLAYER`: metal layer for horizontal pins (E/W edges), string, pdk=True — default M4
- `FP_IO_VLAYER`: metal layer for vertical pins (N/S edges), string, pdk=True — default M5
- `FP_IO_HLENGTH`: total horizontal pin length (µm), Optional[Decimal], pdk=True — NOT set by PDK
- `FP_IO_VLENGTH`: total vertical pin length (µm), Optional[Decimal], pdk=True — NOT set by PDK
- `FP_IO_MIN_DISTANCE`: min distance between adjacent pins (µm) — NOT set by PDK
- `FP_IO_HTHICKNESS_MULT`: horizontal pin width multiplier, Decimal, default=2 — OVERRIDE TO 5
- `FP_IO_VTHICKNESS_MULT`: vertical pin width multiplier, Decimal, default=2 — OVERRIDE TO 5
- `FP_IO_HEXTEND`/`FP_IO_VEXTEND`: extend pins OUTSIDE the die (µm) — different from LENGTH

## ASAP7 Post-DRT Step Failures (GDS export / signoff checkers)

After DRT passes on ASAP7, the following steps all fail and must be skipped. These are not
fixable without a full ASAP7 tech file for Magic and a real SRAM GDS — neither of which exists
for the open ASAP7 PDK. For PPA characterisation (the goal), skipping all of them is correct.

### Magic.StreamOut (e.g. step 89)
**Error**: "No CIF/GDS output style set!" — Magic has no ASAP7 technology file.
**Fix**: `--skip Magic.StreamOut` in Makefile librelane-asap7 target.

### KLayout.StreamOut (e.g. step 90)
**Error**: "LEF Cell 'sram_1rw_256x32_asap7' has no matching GDS cell" — the SRAM is a
black-box stub with no GDS geometry.
**Fix**: `--skip KLayout.StreamOut` in Makefile librelane-asap7 target.

### Magic.WriteLEF (e.g. step 91)
**Error**: Same Magic ASAP7 tech file missing.
**Fix**: `--skip Magic.WriteLEF` in Makefile librelane-asap7 target.

### Checker.SetupViolations / HoldViolations / MaxSlewViolations / MaxCapViolations
**Error**: Flow exits non-zero when violations exist. ASAP7 at 1 GHz with SRAM black-box
stubs will have WNS ≈ -1167 ps (achievable ≈ 462 MHz). These violations are expected —
the goal is PPA characterisation, not tape-out signoff.
**Fix**: `--skip Checker.SetupViolations --skip Checker.HoldViolations --skip Checker.MaxSlewViolations --skip Checker.MaxCapViolations`

### OpenROAD.CheckAntennas-1 (second antenna check, post-routing)
**Error**: Same `ant::AntennaChecker::saveGates` C++ assertion failure as CheckAntennas.
**Fix**: `--skip OpenROAD.CheckAntennas-1` in Makefile librelane-asap7 target.

### Complete ASAP7 skip list (as of 2026-04-25, run 4)

```makefile
--skip Checker.LintTimingConstructs \
--skip Odb.HeuristicDiodeInsertion \
--skip Odb.DiodesOnPorts \
--skip OpenROAD.RepairAntennas \
--skip Odb.ReportDisconnectedPins \
--skip Checker.DisconnectedPins \
--skip Magic.SpiceExtraction \
--skip Checker.IllegalOverlap \
--skip Odb.CheckDesignAntennaProperties \
--skip Checker.LVS \
--skip OpenROAD.CheckAntennas \
--skip OpenROAD.CheckAntennas-1 \
--skip Magic.StreamOut \
--skip KLayout.StreamOut \
--skip Magic.WriteLEF \
--skip Checker.SetupViolations \
--skip Checker.HoldViolations \
--skip Checker.MaxSlewViolations \
--skip Checker.MaxCapViolations \
```

## ASAP7 SRAM Stub — Timing Visibility

The SRAM liberty stub (`sram_1rw_256x32_asap7_TT_0p7V_25C.lib`) is a **hand-crafted black-box**
— it was NOT generated by OpenRAM. It has `time_unit: "1ns"` (different from ASAP7 std cells
at "1ps") and **zero `timing()` groups**. This means:

- OpenSTA sees NO timing arcs through the SRAM — paths entering/exiting the SRAM are not
  analyzed. The SRAM is a timing black hole.
- WNS / TNS numbers from the run reflect only **standard cell logic paths** — SRAM access time
  (estimated 0.30 ns at 7nm) is NOT included.
- If SRAM timing were included, WNS would be worse (longer critical paths through cache FSM).
- This is intentional for PPA estimation but means the STA result is optimistic on any
  path involving SRAM read/write.
- To get real SRAM timing: generate a lib from OpenRAM ASAP7 port (experimental) or use
  hand-annotated timing arcs (setup/hold/access) in the stub lib file.

## ASAP7 Phase 3 PPA Results — Run History

### Run 4 (RUN_2026-04-25_08-07-21) — SRAM timing zero (black-box stub, no arcs)

**Design**: rv32i_cpu_top (Phase 3: CPU + I-cache + D-cache)
**PDK**: asap7sc7p5t_SIMPLE, TT 0.7V 25°C
**Clock target**: 1.0 ns (1 GHz)

| Metric | Value |
|--------|-------|
| Setup WNS | **-1167 ps** @ 1 GHz → achievable ≈ **462 MHz** |
| Setup TNS | -2,593,720 ps |
| Hold WNS | -112 ps (hold not closed) |
| Cell instance area | **7,207 µm²** |
| Total power | **5.76 mW** (SRAM power NOT counted — zero-timing stub) |

**Notes**: SRAM had no timing arcs — power/timing optimistic.

### Run 5 (RUN_2026-04-25_20-40-58) — SRAM with real timing arcs (setup/hold=0.050 ns)

**Clock target**: 1.0 ns (1 GHz)

| Metric | Value |
|--------|-------|
| Setup WNS | **-1140 ps** @ 1 GHz → achievable ≈ **467 MHz** |
| Setup TNS | -2,738,520 ps |
| Hold WNS | **-185 ps** (PROBLEM — 924 hold violations on SRAM input paths) |
| Cell instance area | **7,208 µm²** (10 macros × 351 µm² = 3511 µm² macro area) |
| Total power | **32.3 mW** (internal 30.8 mW dominates — 10 SRAM × high internal energy) |

**Root cause of hold violations**: SRAM hold constraint is 0.050 ns (50 ps). Hold repair
inserted 0 buffers because `PL_RESIZER_ALLOW_SETUP_VIOS=false` (default). With massive
setup violations at 1 GHz, the resizer refuses to add delay (hold fix) that would make
setup worse. The `repair_timing -hold` ran but printed 0 buffers at iteration 0/final.

**Root cause of high power**: 10 SRAM macros × large internal energy values in Liberty.
The `internal_power` of ~30.8 mW is from SRAM activity. Std cell power is ~1.5 mW switching.

### Run 6 (RUN_2026-04-25_21-30-27) — COMPLETE — 2.0 ns / 500 MHz target (REGRESSION)

**Changes from run 5**:
1. `CLOCK_PERIOD`: 1.0 → 2.0 ns (500 MHz target)
2. `PL_RESIZER_ALLOW_SETUP_VIOS`: true
3. Hold margins: 0.100 ns
4. `FP_IO_HTHICKNESS_MULT/VTHICKNESS_MULT`: 5 → 8 (pin width = 8×24 = 192 DBU = 0.192 µm)
5. SDC: `create_clock -period 2.000`, IO delays 0.300 ns

**Actual results** (WORSE than expected — frequency regression):

| Metric | Value |
|--------|-------|
| Setup WNS | **-1148 ps** @ 2.0 ns → data path = 3.148 ns → achievable ≈ **318 MHz** |
| Hold WNS | -12.5 ps (7 violations — minor, but not fully closed) |
| Instance area | 7266 µm² |
| Total power | **16.15 mW** (real SRAM power) |
| DRT-0074 count | **374 errors** (same pins as before — MULT=8 did NOT fix it) |

**Root cause of frequency regression**: Looser 2.0 ns target caused placement/routing to
insert MORE buffering fanout cells. The data path grew from ~2.14 ns (run 5) to ~3.15 ns
(run 6). The tool "gave up" optimizing early since paths only miss by 1.1 ns.

**DRT-0074 root cause update**: MULT=8 gives pin width = 192 DBU. The pin at (148000, 4122)
has rect X=146000..150000, Y=4026..4218. Track analysis confirms 3 M4 Y-tracks pass through
(Y=4068, 4122, 4176). Yet DRT-0074 persists — suggesting the issue is not track coverage but
routing CONGESTION or OBSTRUCTION near the die edge. The drt.tcl catch patch allows the run
to complete despite these errors.

**Critical path analysis**: The critical path (FF → NAND5 → BUF → AND4 → AOI31 → ... → FF)
does NOT pass through any SRAM instance — pure std-cell logic is the bottleneck.

### Run 7 (RUN_2026-04-26_07-23-37) — COMPLETE — 1.0 ns target, real SRAM timing lib

**Changes from run 6**:
1. `CLOCK_PERIOD`: 2.0 → **1.0 ns** (restored — 1.0 ns drives more aggressive optimization)
2. `RUN_POST_GRT_DESIGN_REPAIR`: false → **true** (post-routing repair pass)
3. `PL_RESIZER_SETUP_SLACK_MARGIN`: **0.050 ns** added
4. `GRT_RESIZER_SETUP_SLACK_MARGIN`: **0.050 ns** added
5. Hold margins: 0.100 → **0.050 ns** (right-sized for SRAM hold=50 ps)
6. SDC: `create_clock -period 1.000`, IO delays **0.150 ns** (15%), APB = **0.120 ns**
7. `PL_RESIZER_ALLOW_SETUP_VIOS: true` retained from run 6

**Actual results**:

| Metric | Value |
|--------|-------|
| Setup WNS | **-1147 ps** @ 1 GHz → achievable **466 MHz** |
| Setup TNS | -2,750,980 ps |
| Hold WNS | **-12.5 ps** (8 violations — NOT improved vs run 6) |
| Std-cell area | **3,745 um2** (total incl. macros: 7,257 um2) |
| Total power | **32.29 mW** (internal 30.8 mW from 10 SRAM macros) |
| DRT-0074 errors | **374** (same as run 6 — structural, non-fatal) |
| Max-fanout violations | **145** (up from 0 in run 4 — caused by 50 ps slack margins) |

**Critical path analysis (run 7 — definitive)**:

The critical path does NOT pass through any SRAM. It is pure std-cell combinatorial logic:
- Start: `_55344_` (DFFASRHQNx1 QN output), clock arrival 119 ps
- Chain: NOR3 -> NAND5 -> NOR5 -> NAND5 -> NOR5 -> BUF2 -> NAND5 -> AOI21 -> A2O1A1O1I ->
  BUF3 -> BUF6f -> AO21 -> BUF6f -> OA22 -> NAND3 -> BUF3 -> OA31 -> AOI31 -> A2O1A1I ->
  AOI21 -> OR4 -> AOI21 -> BUF3 -> O2A1O1I -> BUF5 -> NOR2 -> AOI221 -> A2O1A1I -> ... -> OAI32
- End: `_53574_` (DFFASRHQNx1 D input), data arrival 1025 ps
- Logic depth: approximately **20 combinational stages** — pipeline control/hazard/flush logic
- Setup slack post-GRT: -930 ps

**Worst hold path endpoint**: `u_core.u_icache.u_tag_sram` — SRAM IS on the hold critical path.
The 8 hold violations at -12.5 ps are on paths ending at SRAM data/address inputs. These are
structurally unfixable at 1 GHz: `repair_timing -hold` refuses to insert delay buffers when
setup violations are large (known behavior from run 5, confirmed again here).

**Key findings from run 7**:

1. **SRAM is NOT on the setup critical path** — the 0.218 ns fakeram7 read delay applies only
   to read-data paths THROUGH the SRAM (read-to-output arcs). The setup critical path is
   purely register-to-register std-cell control logic. WNS is determined by pipeline hazard
   detection depth, not by SRAM access time.

2. **SRAM IS on the hold critical path** — fakeram7 Liberty hold time = 50 ps for SRAM inputs.
   Hold cannot be closed without first closing setup. Structural limitation at 1 GHz.

3. **Post-GRT repair pass (RUN_POST_GRT_DESIGN_REPAIR=true) had zero effect on hold** — 0 hold
   buffers inserted. Same 8 violations at -12.5 ps as run 6. Known blocked behavior.

4. **50 ps slack margins caused 145 fanout violations** — `PL_RESIZER_SETUP_SLACK_MARGIN=0.050`
   and `GRT_RESIZER_SETUP_SLACK_MARGIN=0.050` generated excessive conservative buffering.
   Remove these margins in any future run to restore fanout to 0 violations (as in run 4).

5. **Achievable frequency ceiling confirmed: ~466 MHz** for this 5-stage RV32I + L1 cache
   design on ASAP7 7nm (asap7sc7p5t_SIMPLE). Ceiling is set by ~20-stage control logic depth.

**No further reruns recommended** for PPA characterization of this design configuration.
The 466 MHz result is consistent across runs 4, 5, and 7 (all at 1 GHz target). To close
timing, would need RTL-level pipeline retiming (e.g., split EX stage, reduce hazard fanout).

**Log**: `/tmp/asap7_run7.log`
**tmux session**: `asap7_run7` (completed)

## Hold Repair Root Cause (CRITICAL — learned in run 5)

`repair_timing -hold` inserts ZERO buffers when `PL_RESIZER_ALLOW_SETUP_VIOS=false` (the
default) AND setup violations are already large. The resizer refuses to add delay for hold
fixing if it would worsen setup beyond the existing setup margin. Fix: either:
1. Set `PL_RESIZER_ALLOW_SETUP_VIOS: true` in config.json, OR
2. Relax the clock period so setup has positive slack before hold repair runs
BOTH approaches are used in run 6 for belt-and-suspenders.

## General LibreLane Tips

- Runs directory: `pnr/<pdk>/runs/RUN_<timestamp>/`
- Per-step logs: `<step_num>-<tool>-<stepname>/<tool>-<stepname>.log`
- Step state input: `state_in.json` — contains ODB/DEF file paths for resume
- Flow log: `flow.log` in the run directory
- `--manual-pdk` flag required when not using Ciel/Volare for PDK management
- `--pdk-root` must point to the directory containing the `asap7/` or `sky130*/` folder

## ASAP7 Run 8 Post-Retiming Results (2026-04-29)

**Run**: `RUN_2026-04-29_17-58-24` | 48 steps completed | Flow complete

### PPA vs Baseline (Run 7 `RUN_2026-04-26_07-23-37`)

| Metric | Run 7 (baseline) | Run 8 (post-retiming) | Delta |
|--------|-----------------|----------------------|-------|
| WNS (setup) | -1147 ps | **-1026 ps** | **+121 ps (+10.5%)** |
| fmax | ~466 MHz | **~494 MHz** | **+28 MHz (+6%)** |
| TNS | -2,751,000 ps | -2,475,200 ps | +276k ps |
| Hold WNS | -12.51 ps | **+1.76 ps** | **CLEARED** |
| Hold violations | 8 | **0** | **-8** |
| Power | 32.29 mW | 32.41 mW | +0.12 mW (flat) |
| Area | 7256.79 µm² | 7232.63 µm² | -24 µm² |

### RTL Changes Applied
Three retiming strategies reduced the CPU control-logic critical path:
1. **Strategy 3**: `irq_valid_i` registered in EX stage — removed 6-7 interrupt AND/OR levels
2. **Strategy 2**: `csr_illegal` pre-decoded in ID stage (`id_ex_reg_t.csr_illegal`) — removed 3-4 CSR decode levels
3. **Strategy 1**: Misaligned detection moved EX→MEM — broke `alu_result[1:0]` data dependency

### New Critical Path
After CPU logic retiming, the critical path shifted to **SRAM address inputs**:
`u_core.u_icache.gen_data_sram[3].u_data_sram/addr0[7]`

The fakeram7 Liberty setup time on addr/data pins now limits fmax. Further improvement
requires either SRAM timing optimization or a pipeline register on the I-cache address path.

### Why Improvement Was Lower Than Predicted
Predicted: 270–410 ps WNS improvement. Actual: 121 ps.
The SRAM address input path was hidden behind the longer CPU logic path in Run 7.
Once CPU logic was retimed, SRAM became the binding constraint at ~494 MHz.
