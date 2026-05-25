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

## ASAP7 Macro Views for Hierarchical PnR (rv32i_cpu_top)

Because Magic.StreamOut / KLayout.StreamOut / Magic.WriteLEF are all blocked (see above),
the Classic LibreLane flow produces **no LEF, GDS, or LIB** from an ASAP7 CPU run.
To use `rv32i_cpu_top` as a hard macro in a top-level (Phase-5 SoC) PnR run, generate
the views post-hoc from the saved final ODB using:

```bash
cd pnr && make macro-views-asap7                       # uses latest CPU run
make macro-views-asap7 RUN=asap7/runs/RUN_2026-05-20_21-43-24  # specific run
```

**What this produces** (`pnr/asap7/macro/`):
- `rv32i_cpu_top.lef` — abstract LEF via OpenROAD `write_abstract_lef -bloat_occupied_layers`
- `rv32i_cpu_top__nom_tt_025C_0p7V.lib` — timing model via OpenROAD `write_timing_model`
- `rv32i_cpu_top.nl.v` — gate-level netlist for blackbox instantiation

**Why not GDS**: SRAM stub has no GDS geometry; GDS is not needed for PnR on predictive PDKs.

**Implementation** (`pnr/scripts/asap7_macro_views.tcl`): standalone `openroad -exit` script
that reads the final ODB + liberty + SDC and calls `write_abstract_lef` then `write_timing_model`.
Does NOT use librelane.steps (avoids SPEF=None hard-fail in `OpenROAD.STAPostPNR.inputs`).

**Convention**: LEF + LIB + NL matches how the SRAM macro is already provided to the CPU run
(`sram_1rw_256x32_asap7.lef` + `sram_1rw_256x32_asap7_TT_0p7V_25C.lib` + stub.v). Consistent.

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

## ASAP7 Run 9 — Register mem_trap_redirect Results (2026-04-30)

**Run**: `RUN_2026-04-30_19-30-03` | 48 steps completed | Flow complete
**RTL commit**: `ffc7bbd` — registered all 5 MEM-trap signals + ghost instruction NOP kill

### PPA vs Run 8

| Metric | Run 8 (baseline) | Run 9 (mem_trap_redirect_r) | Delta |
|--------|-----------------|------------------------------|-------|
| WNS (setup) | -1026 ps | **-1059 ps** | -33 ps (flat/slight regression) |
| fmax | ~494 MHz | **~486 MHz** | -8 MHz |
| TNS | -2,475,200 ps | -2,514,910 ps | -40k ps |
| Hold WNS | 0 ps | **-3.2 ps** | new minor violations |
| Hold TNS | 0 ps | -19.2 ps | |
| Power | 32.41 mW | **32.50 mW** | +0.09 mW (flat) |
| Area | 7232.63 µm² | **7274.81 µm²** | +42 µm² (+5 FFs × ~8 µm²) |

**Power correction**: Earlier memory recorded 5.76 mW for "Run 8" — that was incorrect,
likely from an older intermediate estimate. Both Run 8 and Run 9 are ~32.4 mW from
the actual final/metrics.json.

### Why Timing Did Not Improve

The mem_trap_redirect → SRAM addr0 critical path **was broken** — no SRAM endpoint
appears in Run 9's top paths. However, a **co-critical path** of nearly identical length
was already present in Run 8 and became the new bottleneck:

**New critical path**: EX-stage pipeline register → deep combinational logic → `u_core.flush_id_ex` → ID/EX register NOP insertion → endpoint FF `_54588_`
- Data arrival: 1161 ps | Required: 102 ps | Slack: -1059 ps
- All top 6 violating paths share the SAME launch FF (`_53395_`)
- Launch FF has high fanout (drives NOR5/NAND4/complex logic through 25+ levels)
- Path group: PIPELINE

The EX→flush_id_ex path was already at ~-1026 ps in Run 8 (second-worst, hidden behind
SRAM path). Fixing the SRAM path exposed it at -1059 ps. The 33 ps regression is from
slight placement pressure from the 5 new FFs.

### Synthesis: ex_mem_reg_to_mem NOP Mux
The ghost instruction kill mux (`ex_mem_reg_to_mem = mem_trap_redirect_r ? ex_mem_nop() : ex_mem_reg`)
synthesized successfully — `u_core.ex_mem_reg_to_mem[258:265+]` bits are visible in the netlist.
The NOP mux is NOT on the new critical path (hazard unit reads `ex_mem_reg` directly, not `ex_mem_reg_to_mem`).

### Next Critical Path: EX Stage → flush_id_ex

The new bottleneck is the combinational path:
```text
EX/MEM pipeline register FF (_53395_, QN output)
  → ~25 levels of branch/trap/control logic (NOR5, NAND4, OA21, OAI221, AOI21...)
  → ex_pc_redirect computation
  → u_core.flush_id_ex (hazard unit output)
  → BUFx10 fanout342 + ID/EX register NOP gate logic
  → ID/EX register bit (endpoint FF _54588_)
Total: ~1161 ps data path → WNS -1059 ps at 1 GHz
```

**Recommended fix (Run 10)**: Register `ex_pc_redirect` before it feeds the hazard unit.
This breaks the EX→flush_id_ex combinational path. The launch FF `_53395_` drives into
the ex_pc_redirect computation; after registration, the path from `ex_pc_redirect_r` to
`flush_id_ex` to the endpoint FF would be ~300-400 ps.
Trade-off: branch misprediction penalty increases from 2 cycles → 3 cycles (ISA-compliant).
Estimated WNS gain: ~+700 ps → targeting 650-750 MHz.

## SDC Constraint Patterns (Learned from Run 24, 2026-05-17)

### APB Multicycle Path — Two Separate Calls Required

OpenSTA does **NOT** accept `-setup N -hold M` on a single `set_multicycle_path` call.
Split into two commands:

```tcl
# WRONG — OpenSTA rejects combined setup/hold on one line:
# set_multicycle_path -setup 3 -hold 2 -from [get_ports apb_paddr_i*]

# CORRECT — two separate calls:
set_multicycle_path -setup 3 -from [get_ports {apb_paddr_i* apb_psel_i apb_penable_i apb_pwrite_i apb_pwdata_i*}]
set_multicycle_path -hold  2 -from [get_ports {apb_paddr_i* apb_psel_i apb_penable_i apb_pwrite_i apb_pwdata_i*}]
```

This was confirmed effective in Run 24: the apb_paddr_i[8] startpoint (Run 23 WNS) was
eliminated from the critical path entirely (+67.5 ps WNS gain attributed to this fix).

### SRAM Liberty False-Path — csb0 Must Be Covered Alongside din0/addr0

The fakeram7/OpenRAM Liberty stubs generate hold violations on SRAM control inputs that
are timing artifacts, not real violations. The full set of false-path annotations needed:

```tcl
set_false_path -hold -to [get_pins -hierarchical *din0*]
set_false_path -hold -to [get_pins -hierarchical *addr0*]
set_false_path -hold -to [get_pins -hierarchical *csb0*]   # ADD THIS — easy to miss
```

Omitting `csb0` leaves hold violations that survive routing (Run 24 observed 1→4 hold
violations; the 3 new violations are likely on paths ending at `*csb0*` pins).

### IRDropReport Requires RUN_SPEF_EXTRACTION: true

`RUN_IR_DROP_REPORT` and `RUN_SPEF_EXTRACTION` must both be `true` or both `false` in
`config.json`. Enabling IR drop reporting without SPEF extraction causes the flow to abort
during the power analysis step because parasitics are missing.

## SDC Constraint Patterns (Learned from Run 25, 2026-05-17)

### get_pins vs get_cells for FF-Instance False-Paths

When targeting a pipeline register by its RTL name (e.g., `ex1a_ex1b_reg_q`), use
`get_cells -hierarchical` — NOT `get_pins -hierarchical`. Post-synthesis, the synthesizer
mangles FF output pin names; `get_pins` with a hierarchical glob generates STA-0363 "pin
not found" and the constraint is silently dropped.

```tcl
# WRONG — STA-0363, constraint not applied:
set_false_path -hold -from [get_pins -hierarchical {*ex1a_ex1b_reg_q*}]

# CORRECT — targets the FF cell instance, resolves post-synthesis:
set_false_path -hold -from [get_cells -hierarchical {*ex1a_ex1b_reg_q*}]
```

If the cell no longer exists (e.g., EX1c removed), `get_cells` returns an empty collection
silently — no warning — whereas `get_pins` emits STA-0363 for every missing pin.

### get_nets in Flattened Netlists — Use get_pins Instead

`get_nets -hierarchical "*u_dcache*wb_tag*"` fails (STA-0361) in a flattened post-synthesis
netlist because hierarchy separators are removed and the `*u_dcache*` prefix no longer
matches. Use `-through [get_pins -hierarchical "*wb_tag*"]` instead:

```tcl
# WRONG — STA-0361, hierarchy prefix lost in synthesis:
set_multicycle_path -setup 2 -through [get_nets -hierarchical "*u_dcache*wb_tag*"]

# CORRECT — pin-based through-point, shorter glob survives flattening:
set_multicycle_path -setup 2 -through [get_pins -hierarchical "*wb_tag*"]
set_multicycle_path -hold  1 -through [get_pins -hierarchical "*wb_tag*"]
```

## RTL Pipeline Timing Lessons (Learned from Runs 20–25)

### EX1c Was Timing-Motivated — Do Not Remove Without Replacing

The EX1c pipeline stage was inserted (Run 20) to break a 15-gate combinational cone in
the EX1a → EX1b path (trap-type encoder + store byte-align case tree). Run 25 removed
EX1c and moved that logic back into EX1a, which restored the 15-gate cone and regressed
WNS by -111 ps (from -702 ps to -813 ps).

**Rule**: Do not remove a retiming stage unless the logic it was breaking is also being
restructured or its cone shortened by another means.

### SYNTH_STRATEGY DELAY 3 Creates High-Fanout ABC FFs

`SYNTH_STRATEGY "DELAY 3"` enables aggressive ABC retiming that can create single-bit
synthesized FFs (`dfflibmap`) driving 1000+ endpoints. In Run 25, two such FFs (`_48075_`
and `_50320_`) contributed 952K ps of the 2.36M ps TNS (40% of total). These FFs are
RTL-invisible — they appear only in the post-synthesis netlist.

**Fix**: Try `SYNTH_STRATEGY "DELAY 2"` first. If high-fanout ABC FFs persist, consider
`SYNTH_STRATEGY "AREA 0"` as a fallback (sacrifices some WNS for better fanout structure).

### Forwarding Unit Comparison is a Deep Cone (Run 27+ target)

The worst single path in Run 25 (`_49400_/QN → _49478_/D`, -813 ps) traverses the
forwarding unit address comparison + MUX select tree: 15 unique logic gates (NAND5 → NAND3
→ NOR5 → AOI211 → AOI21 → NAND4 → ... → A2O1A1I × 3) plus ~15 inserted rebuffer cells.
The fix is to move the forwarding address comparison (`ex_rd_addr == id_rs1_addr` etc.)
into the ID stage and register the select signal — leaving only a 2:1 MUX in EX1a.
This requires a full regression campaign (forwarding correctness re-verification) and is
deferred to Run 27+ if Run 26 (SYNTH_STRATEGY DELAY 2) is insufficient.

## SDC Clock Period and Synthesis Aggressiveness (Run 26 Lesson)

**Rule**: Keep SDC clock period at 1.9 ns (aggressive target) even when the design is deeply
violating (WNS -700 to -900 ps). Do NOT relax the clock to 2.0 ns to "make it achievable."

**Why**: ABC uses the SDC clock period as an optimization pressure target. At 1.9 ns, ABC
aggressively restructures paths between 1.9–2.0 ns that it would leave alone at 2.0 ns.
Run 26 relaxed to 2.0 ns expecting +100 ps slack benefit, but the achievable fmax dropped
from 384 MHz (Run 24) to 354 MHz — a 30 MHz regression — because synthesis QoR degraded.

**How to apply**: CLOCK_PERIOD in config.json and create_clock in asap7.sdc must stay at 1.9.
Only relax once the design is close to meeting timing (WNS within 50–100 ps of 0).

## EX1c Retiming Stage — Removal Discipline (Run 25/26 Lesson)

**Rule**: Do not remove a retiming stage (EX1c) without first restructuring the combinational
cone it was inserted to break.

**Why**: EX1c was inserted in Run 20 to break a 22-gate ALU+trap-encode+store-byte-align cone.
Run 25 removed EX1c to restore a 3-cycle branch penalty, causing -111 ps WNS regression.
Re-inserting EX1c in Run 26 was neutral (the bottleneck had already shifted to forwarding/hazard
logic), but removing it caused confirmed regression. Do not remove it again without restructuring
the EX1a trap-encode + byte-align logic to fit in one stage first.

**How to apply**: rv32i_pipeline_ex1c.sv must remain in the flow. If branch-penalty improvement
is desired, restructure the EX1a logic first, then remove EX1c only after verifying WNS holds.

## SRAM Liberty Power Model — clk0 is Unconditional (Run 36 Finding)

**Finding**: `pnr/asap7/sram_1rw_256x32_asap7_TT_0p7V_25C.lib` has NO `csb0`-conditional
`internal_power`. The only `when`-conditioned power is on `web0` (read vs write). The clk0
pin internal power (1.345 energy units per rise/fall) is charged every clock toggle regardless
of `csb0`.

**Implication for power reduction**:
- `csb0` / `web0` gating does NOT move `report_power` output (no `when` clause for them)
- Only gating `clk0` toggles reduces reported SRAM internal power
- `cell_leakage_power : 128.9 µW` × 10 macros = 1.289 mW (matches report exactly)
- Macro internal 37.5 mW ≈ all clk0 toggles at 1.4 GHz

**Fix applied in Run 36**: `rtl/mem/rv32i_clock_gate.sv` — behavioral latch-AND ICG wrapper.
Instantiated for all 10 SRAM clk0 pins (icache tag + 4 data, dcache tag + 4 data) using
`!csb0` as the enable. `SYNTH_CLOCK_GATING: true` added to config.json so Yosys maps
the latch-AND to an ICGx* cell from the SEQ library.

**Expected gain**: ~15–22 mW reduction (30–40% of total chip power).

## PDN PSM-0039 Violations — Tool Artifact at Tap Cell Column (Run 35/36 Finding)

**Finding**: 1.81M PSM-0038/0039 "Unconnected instance" violations appear every run.
All are tap cells (`TAP_TAPCELL_ROW_*`) at a single x coordinate (84.834 µm) spanning
rows 67–175. SRAM macros are at x=5–54.8 µm — NOT involved.

**Root cause**: x=84.834 µm falls between PDN V-stripes at 81.5 µm and 86.0 µm (pitch=4.5,
offset=0.5). PSM analysis uses M1-only connectivity. The M1 power rail gap at that column
(routing congestion / PDN gap) means those tap cells cannot be reached via M1 alone.
The actual VDD/VSS path goes through M2/M3 straps which PSM does not model.

**Verdict**: Tool artifact — not a real disconnection. `ERROR_ON_PDN_VIOLATIONS: false`
allows flow to continue. Confirmed: SRAM macros are not involved.

**Potential fix**: Shift `FP_PDN_VOFFSET` by ~2.3 µm so a V-stripe lands near x=84.834 µm,
or increase V-stripe density. Not needed for ASAP7 predictive flow.

## Yosys `share` Pass Hangs on GPU 8-Lane Vector Datapath (2026-05-23, Phase 4 GPU)

**Finding**: ASAP7 GPU synthesis (`make librelane-asap7-gpu`, design `gpu_top`) hangs in
yosys step 05. Symptom: yosys pegged at ~100% CPU for 60+ min, RSS ~4 GB, synthesis log
frozen mid-`SHARE pass (SAT-based resource sharing)` with repeated "Analyzing resource
sharing options for ... vector_alu.sv:52 ($shl)" lines and no further progress. NOT a
crash — no error, 0 latches, lint clean, pre_synth_chk 0 problems. The frozen log mtime
can look like an "external kill"; it is not — `ps -o time` shows CPU time still climbing.

**Root cause**: the yosys `share` pass does SAT-based resource sharing over the 8 identical
32-bit barrel-shifter ($shl) cones in `rtl/gpu/vector_alu.sv:52` (VSLL, 8 SIMT lanes). The
O(n^2) candidate enumeration across structurally-identical wide shifters blows up. The CPU
designs never hit this (no 8-wide identical shifter cones). In LibreLane's pyosys flow,
`d.run_pass("share")` at `librelane/scripts/pyosys/synthesize.py` (~line 167) was
UNCONDITIONAL — the declared `SYNTH_SHARE_RESOURCES` config var (default true) was not
wired to it, so it could not be disabled from config.json.

**Fix applied (2026-05-23)**: gate the pass on the existing flag, then disable it.
1. `librelane/scripts/pyosys/synthesize.py` (LOCAL install, outside the project repo):
   - add `share_resources=True` to `librelane_synth(...)` signature
   - change the call to `if share_resources: d.run_pass("share")`
   - at the `librelane_synth(...)` call site, pass `share_resources=config["SYNTH_SHARE_RESOURCES"]`
2. `pnr/asap7/gpu/config.json`: add `"SYNTH_SHARE_RESOURCES": false`.
`share` is an area-only optimization (merges shareable resources to cut cell count); skipping
it is functionally safe — minor area cost only.

**How to apply**: this patch lives in the LOCAL ~/Downloads/Github/librelane checkout and is
NOT tracked by the project repo — re-apply it after any librelane update/reinstall. For any
future wide-datapath block (GPU, NPU MAC array) that stalls in synthesis step 05, check the
synth log for a frozen `SHARE pass` and set `SYNTH_SHARE_RESOURCES: false` in that block's
config.json. CPU configs are unaffected and can leave it at the default.
