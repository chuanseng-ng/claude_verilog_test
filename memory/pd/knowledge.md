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

### Checker.YosysSynthChecks: 4063 "no driver" errors on Synlig UHDM designs (ASAP7 SoC)

**Root cause**: Synlig UHDM marks child-module instances as `module_not_derived=1`.
After `hierarchy` (without `-check`), Yosys still sees FSM state registers (`bid_q`,
`rid_q`, `wstate`, `rstate`, etc.) in always_ff blocks as having no driver because
UHDM's partial elaboration leaves those regs as unresolved wires in the CHECK pass.
These are NOT real combinational loops or truly undriven nets — all 82 functional tests
pass on the identical synthesized netlist.

**Fix**: `--skip Checker.YosysSynthChecks` in the `librelane-asap7-soc` Makefile target.
Added 2026-06-22 (M11 P&R run 1 stumble, RUN_2026-06-22_18-16-11, step 07).

### PDN_MACRO_CONNECTIONS — Only Include True Hard Macros (SoC M11 Lesson)

**Symptom**: `[ERROR] No match found for regular expression '.*u_sram.*' defined in PDN_MACRO_CONNECTIONS.`
followed by `exit 1` from `set_global_connections.tcl` (line 59-61). Flow dies at
`OpenROAD.RepairDesignPostGPL` (stage 29 in the SoC run).

**Root cause**: `sram_controller` is a behavioral SystemVerilog module — it synthesizes flat
into Yosys-mangled std-cell instances. The SRAM black-box stubs inside `sram_controller`
appear in the placed netlist as `u_sram/_00_` through `u_sram/_23_` (Yosys `$paramod`
flattening produces `<parent_name>/<sequential_index>` naming). These are NOT hard macros
with a physical VDD/VSS pin in a LEF — they are std-cell instances whose power comes from
the global `.*` connection in `set_global_connections`. The `.*u_sram.*` regex correctly
matches nothing because no `sram_1rw_256x32_asap7` LEF macro instance appears at the top
level — `sram_controller` swallowed it during flat synthesis.

**Fix**: Remove any `.*u_sram.*` (or similar behavioral-module) entry from
`PDN_MACRO_CONNECTIONS` in config.json. Only include true hard macros that appear as
top-level LEF cells (e.g. rv32i_cpu_top, gpu_top).

**Rule for future runs**: Before adding a regex to `PDN_MACRO_CONNECTIONS`, confirm the
module produces a hard LEF cell at the top level (i.e., it is a black-box stub in the
verilog files list, not a real RTL module). Behavioral RTL modules synthesized flat will
NEVER appear as macro instances.

**Confirmed in**: M11 SoC Run 1 (`RUN_2026-06-22_18-23-26`, 2026-06-22). The floorplan
log for Run 1 shows `.*u_sram.* matched with u_sram/_00_` through `u_sram/_23_` during
stage 11 (floorplan-level matching), but by stage 29 the placed DB has these as std-cell
instances and the regex matches 0 MACRO-type cells — causing the fatal exit.

### Complete ASAP7 skip list (as of 2026-06-22, SoC M11 run)

```makefile
--skip Checker.LintTimingConstructs \
--skip Checker.YosysSynthChecks \
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

### PSM-0069 Macro PG Pin Connectivity — Abstract LEF Must Have PORT/RECT Geometry (SoC M11 Run 14)

**Symptom**: 8,281,711 PSM-0069 power-grid violations on VDD/VSS after a completed route.
All other metrics clean (WNS=0, DRC=0). Log shows `[PSM-0069] Check connectivity failed on VDD`
and `[PSM-0069] Check connectivity failed on VSS` at step 26 (CheckerPowerGridViolations).

**Root cause**: `write_abstract_lef -bloat_occupied_layers` generates `PIN VDD / USE POWER /
DIRECTION INOUT / END VDD` but **NO PORT/RECT block** when the block-level PDN has no macro
boundary ring. OpenROAD PSM does M1/M7-based connectivity analysis — without physical pin
geometry in the abstract LEF, PSM cannot find a macro VDD/VSS node to begin the walk.
`PDN_MACRO_CONNECTIONS` (logical net assignment via `set_global_connections`) is orthogonal
to this physical geometry requirement and does not substitute for PORT/RECT.

**Fix**: Add PORT/RECT perimeter geometry on M7 to both VDD and VSS pins in the abstract LEF.
Match the SoC pdn.tcl macro ring geometry:
```
pdn.tcl: add_pdn_ring -layers {M6 M7} -widths {0.160 0.160} -spacings {0.160 0.160}
         -core_offsets {0.5 0.5}   -> VDD ring: 0.50-0.66 um inset; VSS ring: 0.82-0.98 um inset
```

LEF PORT/RECT pattern for a W×H macro (e.g. CPU 130×130, GPU 340×340):
```lef
  PIN VDD
    USE POWER ;
    DIRECTION INOUT ;
    PORT
      LAYER M7 ;
        RECT 0.500 0.500 {W-0.500} 0.660 ;       # bottom edge
        RECT 0.500 {H-0.660} {W-0.500} {H-0.500} ; # top edge
        RECT 0.500 0.500 0.660 {H-0.500} ;       # left edge
        RECT {W-0.660} 0.500 {W-0.500} {H-0.500} ; # right edge
    END
  END VDD
  PIN VSS
    USE GROUND ;
    DIRECTION INOUT ;
    PORT
      LAYER M7 ;
        RECT 0.500 0.820 {W-0.500} 0.980 ;
        RECT 0.500 {H-0.980} {W-0.500} {H-0.820} ;
        RECT 0.500 0.820 0.980 {H-0.820} ;
        RECT {W-0.980} 0.500 {W-0.820} {H-0.500} ;
    END
  END VSS
```

VDD and VSS get distinct non-overlapping perimeter bands. VDD at the inner band
(0.50-0.66 µm from each edge), VSS at the outer band (0.82-0.98 µm).

**Critical note**: The `.gitignore` in `pnr/` has `*.lef` which hides abstract LEFs.
Add `!asap7/cpu/macro/*.lef` and `!asap7/gpu/macro/*.lef` exceptions so LEF fixes persist.

**Fix applied in**: commit `c1f7bbd` (2026-06-24), SoC M11 Run 15 confirming.

---

## ASAP7 Macro Views for Hierarchical PnR (rv32i_cpu_top / gpu_top)

Because Magic.StreamOut / KLayout.StreamOut / Magic.WriteLEF are all blocked (see above),
the Classic LibreLane flow produces **no LEF, GDS, or LIB** from an ASAP7 run.
To use `rv32i_cpu_top` or `gpu_top` as a hard macro in a top-level (Phase-5 SoC) PnR run,
generate the views post-hoc from the saved final ODB. The target takes `BLOCK=cpu|gpu`
(default `cpu`); the GPU variant uses the `sram_1rw_128x32` macro lib (CPU uses `256x32`):

```bash
cd pnr && make macro-views-asap7                                   # latest CPU run
make macro-views-asap7 BLOCK=gpu                                   # latest GPU run
make macro-views-asap7 BLOCK=gpu RUN=asap7/gpu/runs/RUN_2026-05-28_06-29-48  # specific run
```

**What this produces** (`pnr/asap7/<cpu|gpu>/macro/`, e.g. gpu):
- `gpu_top.lef` — abstract LEF via OpenROAD `write_abstract_lef -bloat_occupied_layers` (gitignored)
- `gpu_top__nom_tt_025C_0p7V.lib` — timing model via OpenROAD `write_timing_model` (committed)
- `gpu_top.nl.v.gz` — gzipped flat post-route netlist for blackbox/full-flat use (committed)

**Netlist is gzipped**: the GPU flat netlist is ~103 MB raw (over GitHub's 100 MB hard
limit); ~9.6 MB gzipped. CPU is gzipped too for a uniform convention (~635 KB). The target
runs `gzip -f` after copy; raw `*.nl.v` is gitignored, `*.nl.v.gz` is tracked (pnr/.gitignore
has `!asap7/*/macro/*.nl.v.gz` exceptions to the `*.v.gz` ignore). Run `gunzip -k <design>.nl.v.gz`
to restore for full-flat sim/LEC. LEF + LIB stay uncompressed (P&R tools read them directly).

**Why not GDS**: SRAM stub has no GDS geometry; GDS is not needed for PnR on predictive PDKs.

**Implementation** (`pnr/scripts/asap7_macro_views.tcl`): standalone `openroad -exit` script
that reads the final ODB + liberty + SDC and calls `write_abstract_lef` then `write_timing_model`.
Does NOT use librelane.steps (avoids SPEF=None hard-fail in `OpenROAD.STAPostPNR.inputs`).

**Convention**: LEF + LIB + NL matches how the SRAM macro is already provided to the run
(`sram_1rw_*_asap7.lef` + `..._TT_0p7V_25C.lib` + stub.v). Consistent across CPU and GPU.

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

## LibreLane Classic Flow Has NO Hold-Repair Step After Detailed Routing
(GH #104 Sky130 SoC Stage-2, 2026-07-24 — structural, applies to any PDK)

**Finding**: `librelane/flows/classic.py`'s `Steps` list places
`OpenROAD.ResizerTimingPostGRT` immediately before `OpenROAD.DetailedRouting`, and
`OpenROAD.STAPostPNR` (the step that produces the final sign-off timing report) runs
after `OpenROAD.DetailedRouting` with **no resizer/repair step in between**.

> **Caveat on "signed-off" (added 2026-07-31):** STAPostPNR's numbers are only as
> honest as the Liberty views behind them. On the Sky130 SoC they are a
> TYPICAL-CORNER (nom_tt) result — the SRAM macro is characterized at TT only, so
> STAPostPNR reports nine corner *labels* backed by one macro model. Never quote
> "clean at all 9 corners" from a STAPostPNR report without first checking that
> every macro in `config.json`'s `MACROS` has genuinely distinct per-corner libs
> (a `{"*": [...]}` lib entry is the tell). See GH #120 / bead `o1i`.
`OpenROAD.STAPostPNR` is pure reporting — it has no timing-repair capability at all.

**Consequence**: any hold (or setup) degradation introduced by the shift from
GRT-estimated to DRT-actual parasitics is **structurally invisible and unfixable**
within a single Classic-flow invocation. A design can show `RSZ-0033 No hold
violations found` at `OpenROAD.ResizerTimingPostGRT` and still report real hold
violations at `OpenROAD.STAPostPNR` after detailed routing — this is not the resizer
"stopping early" or an under-effort run; there is no step positioned to catch it.
Observed directly: a net (`u_cpu/axi_bready_o` fanning to 2 endpoints) went from
clean at PostGRT to a `-70.8 ps` / `-47.7 ps` hold violation at sign-off, entirely a
routing-parasitic-shift effect, roughly a 120 ps swing on that specific net.

**Available levers** (pre-route only, do not address post-route degradation
directly): `PL_RESIZER_HOLD_SLACK_MARGIN` (`OpenROAD.ResizerTimingPostCTS`, default
0.1 ns) and `GRT_RESIZER_HOLD_SLACK_MARGIN` (`OpenROAD.ResizerTimingPostGRT`, default
0.05 ns) — both are "overfix" margins that make the pre-route resizer stop above
zero slack instead of at it, building in cushion to *survive* whatever the
post-route shift turns out to be. This is probabilistic insurance, not a guarantee,
and since both margins are global (apply to every hold-violating endpoint
design-wide, not a targeted net), raising them risks perturbing nearby setup paths
if setup and hold critical paths cluster in the same region (e.g. a hard-macro
boundary) — quantify this per-design before applying, don't assume it's free.

**If you need guaranteed post-route hold closure**: this requires either (a) a
custom step/flow variant that re-invokes a resizer pass after
`OpenROAD.DetailedRouting` (not present in stock Classic), or (b) enough PostGRT
margin headroom (raised `GRT_RESIZER_HOLD_SLACK_MARGIN`) that empirically survives
your design's typical GRT-to-DRT parasitic shift — verify empirically per design/PDK,
the ~120 ps shift seen here is not a universal constant.

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

---

## SoC Synthesis Frontend: sv2v Required (Phase 5 M11 discovery, 2026-06-23)

### Problem: Synlig UHDM cannot synthesize this SoC in any mode

The SoC RTL (22 SV files, packages, packed 2D arrays) cannot be synthesized by Synlig:

- **`SYNLIG_DEFER=true`** (per-file -defer compilation): Peripheral FSM logic is silently dropped.
  Each module compiled independently; `axi_pkg.sv` types unresolved per-file → DMA, UART, crossbar,
  timer etc. elaborate to only tie cells + AXI-lite register sub-cell. Result: 0 FFs in soc_top.
  Diagnostic: yosys-synthesis.log shows hundreds of "Wire ... is used but has no driver" warnings
  for every DMA/UART/crossbar AXI master output signal.

- **`SYNLIG_DEFER=false`** (monolithic Synlig elaboration): Crashes with
  `Assert !wire->name.empty() failed in kernel/rtlil.cc:2150` during UHDM -link.
  This happens even after the soc_top.sv packed-2D intermediate wire decoupling (commit 6449de7).
  The crash occurs in the json_header step (step 03), before hierarchy or proc is reached.

- **`USE_SYNLIG=false`** (vanilla Yosys): Fails at step 03 json_header with
  `soc_addr_map_pkg.sv:24: ERROR: syntax error, unexpected TOK_ID` on the `package` keyword.
  Vanilla Yosys `read_verilog -sv` does not support SV packages.

### Solution: sv2v pre-processing

**sv2v** (version 0.0.13.1, nixpkgs `haskellPackages.sv2v`) converts all SoC SV to Verilog-2005.
Installation: `nix-build '<nixpkgs>' -A haskellPackages.sv2v --no-out-link`
Binary path after install: `/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v`

**What sv2v handles correctly:**
- SV packages (`package ... endpackage`) → inline localparams/parameters
- Packed 2D arrays (`logic [N-1:0][W-1:0] arr`) → flattened
- Generate blocks → resolved to explicit instances
- `logic` type → `wire`/`reg` as context requires
- `(* blackbox *)` attributes on module headers are PRESERVED

**Usage for soc_top:**
```bash
sv2v \
    rtl/soc/axi_pkg.sv rtl/soc/soc_addr_map_pkg.sv rtl/soc/soc_periph_map_pkg.sv \
    pnr/asap7/soc/rv32i_cpu_top_stub.sv pnr/asap7/soc/gpu_top_stub.sv \
    rtl/soc/pll/pll_clkgen_stub.sv pnr/asap7/soc/pll_clkgen_pnr.sv \
    rtl/soc/pll/pll_axil_regs.sv rtl/soc/axi4_crossbar.sv \
    rtl/soc/axi_lite_register_bank.sv rtl/soc/axi_lite_interconnect.sv \
    rtl/soc/axi4_to_axilite.sv rtl/soc/axilite_to_axi4.sv \
    rtl/soc/sram_controller.sv rtl/soc/boot_rom.sv \
    rtl/periph/dma_engine.sv rtl/periph/interrupt_controller.sv \
    rtl/periph/timer.sv rtl/periph/uart_controller.sv rtl/periph/spi_controller.sv \
    rtl/soc/soc_top.sv \
    -w pnr/asap7/soc/soc_top_sv2v.v
```

**Result:** 5193 lines, 37 clocked always blocks, `(* blackbox *)` on rv32i_cpu_top + gpu_top preserved.
Yosys `read_verilog + proc + flatten` = 5500 cells pre-techmap, 43546 DFFs after dfflibmap. No crashes.

**config.json settings for sv2v flow:**
```json
"VERILOG_FILES": ["dir::../sram_1rw_256x32_asap7_stub.v", "dir::soc_top_sv2v.v"],
"USE_SYNLIG": false,
"SYNLIG_DEFER": false,
"SYNTH_HIERARCHY_MODE": "flatten"
```

**Makefile integration:** `asap7-soc-sv2v` target generates `soc_top_sv2v.v` (gitignored).
`librelane-asap7-soc` depends on `asap7-soc-sv2v`. Skip `Checker.LintErrors` (Verilator
WIDTHEXPAND/ASCRANGE artifacts from `1'sb0` sv2v idioms — harmless to Yosys synthesis).

**Caveat:** sv2v WIDTHEXPAND artifacts (`localparam [3:0] x = 1'sb0`) cause Verilator ERRORS.
These are benign for synthesis. Always skip `Checker.LintErrors` for sv2v-generated Verilog.

### deferred_flatten synthesize.py patch (secondary fix, still in place)

The deferred_flatten second pass was patched in
`~/Downloads/Github/librelane/librelane/scripts/pyosys/synthesize.py` to load
VERILOG_FILES with `(* blackbox *)` attribute into the second-pass design, so `defparam`
assignments (e.g. `gpu_top.GPU_ENABLE_COALESCE = 1'b0`) can be resolved. This patch is
harmless but the main SoC synth now uses the sv2v path, not deferred_flatten.

### sv2v has NO automatic module-file discovery — the source list must be exhaustive
(GH #94 / bead oa7, 2026-08-02)

**sv2v only sees exactly the files passed on its command line.** Unlike Verilator, which
resolves an undefined module reference by searching any `-I<dir>` (or `-y<dir>`) directory for
a matching filename, sv2v (0.0.13.1) does no such search. If `pnr/Makefile`'s
`SKY130_SOC_SV_FILES` / `SOC_SV_FILES` lists omit a file that `soc_top.sv` (or anything it
instantiates) depends on, sv2v's Verilog-2005 output simply contains an instantiation of an
undefined module — and Yosys `read_verilog`/synthesis can blackbox that silently rather than
erroring, discarding real logic (in the discovered case: the entire GH #91/#93 CDC boundary —
`rtl/mem/rv32i_clock_gate.sv` plus all 5 `rtl/soc/cdc/*` + `async_axi_fifo.sv` +
`apb_cdc_bridge.sv` files — had been missing from both SoC sv2v lists since the PMU epoch and
the CDC epic respectively, unnoticed because neither list had been regenerated since).

**Why the cocotb regression (159/159) never caught this**: `tb/cocotb/soc/Makefile` passes
`EXTRA_ARGS="-I$(RTL)/mem -I$(RTL)/soc/cdc ..."` to Verilator for every SoC-level target, so
Verilator auto-resolves `rv32i_clock_gate`/`cdc_2ff_sync`/etc. even though `SOC_BOOT_SOURCES`
never lists them explicitly either. Two different SystemVerilog frontends, reading the same
`soc_top.sv`, with two different module-resolution semantics — a clean simulation regression is
*not* evidence that a from-scratch sv2v/Yosys synthesis of the same RTL will elaborate cleanly.

**Rule going forward**: whenever a new module is added anywhere in `soc_top.sv`'s instantiation
tree (directly, or nested inside another RTL file `soc_top.sv` already includes), add it
explicitly to *both* `SKY130_SOC_SV_FILES` and `SOC_SV_FILES` in `pnr/Makefile` in the same
commit — do not rely on the cocotb suite passing as a proxy for the sv2v list being complete.
After any such edit, regenerate for real (`make sky130-soc-sv2v` / `make asap7-soc-sv2v`) and
grep the output for the new module's `module <name> (` definition and its instance name, not
just a clean exit code — sv2v does not reliably print a warning for an unresolved instantiation.

---

## Sky130A PDK — LibreLane Issues and Fixes

### Magic DRC — li.3 Standard Cell Boundary Artifact (sky130A, 27M+ violations)

> ⚠️ **SUPERSEDED 2026-07-28 — the attribution in this section is WRONG.** It was written from
> a partial reading of the violation report. An exhaustive streaming classification of all
> 27,730,498 coordinates (reproduced twice, independently) proved the violations are **100.0000 %
> inside the 10 SRAM macro footprints**, with **zero** in the standard-cell array or routing
> channels, and that `li.3` is **not** the dominant rule family. See
> "Quantitative confirmation (2026-07-28, bead 45a)" further down this section for the corrected
> data. The three specific claims below that are now known false are struck through inline.
> The *conclusion* (KLayout + Netgen authoritative, Magic waived) is unchanged and still correct —
> only the mechanism was misattributed.

**Symptom**: Magic DRC reports ~27.7M violations regardless of `MAGIC_DRC_USE_GDS` setting.
KLayout DRC on the identical merged GDS reports **0 violations**. *(Symptom is accurate; see the
KLayout caveat below — that 0 excludes SRAM internals by deck design.)*

**~~True root cause (confirmed by reading violation report, Run 4 + Run 6)~~** — WRONG, superseded:
~~The violations are **NOT** from SRAM GDS unknown layers.~~ Both GDS mode (Run 4) and
DEF+LEF mode (Run 6) produce the same count *(this part is correct — 27,730,498 vs 27,733,913,
Δ 0.01 %)*, with this violation type present:
```
Local interconnect spacing < 0.17um (li.3)
```
~~These occur at **standard cell boundaries**~~ — **FALSE**: measured `li.3` count is 922,628 of
27,730,498 (3.3 %), and every one of them lies inside an SRAM footprint. Zero violations of any
rule family occur in the standard-cell array (max reported y = 907.87 µm; the logic zone starts at
917.5 µm).

~~The SRAM-specific violations (diff/tap.2 "SRAM core", poly.8 "SRAM core transistor") each
appear only ONCE — they are NOT the bulk. The 27.7M count is entirely li.3 cell-boundary
artifacts.~~ — **FALSE on both counts**: the actual dominant families are `diff/tap.9` 3,017,505;
`licon.1` 2,572,862; `li.1` 2,278,399; `licon.5a` 2,262,998; `licon.8` 1,850,092;
`poly.8` 1,833,708 (i.e. the "SRAM core transistor" rule fires ~1.8M times, not once).

**Why the original reading went wrong**: the report is 1.1 GB and was sampled from the top rather
than classified in full. Rule-family headers near the start are dominated by `li.3`, which is not
representative of the body. Always stream-classify the whole file — see the corrected method
below.

**Non-fixes (tried and confirmed not to work)**:
- `MAGIC_DRC_USE_GDS: false` (DEF+LEF mode) → same li.3 count
- `"magic.DRC": {"EXTRA_GDS_FILES": []}` → INVALID LibreLane v2 JSON config key
  (rejected: "Unknown key 'magic.DRC' provided"; LibreLane v2 has NO per-step JSON
  override support — step config overrides are only available via the Python interactive API)

**KLayout DRC=0 is the authoritative sign-off**: KLayout uses the foundry-equivalent
deck (same as SkyWater MPW submission). For sky130 hardening, KLayout DRC=0 + Netgen
LVS=MATCH = Stage 1 physical sign-off.

**Theoretical fixes for Magic DRC=0** (not pursued, out of scope):
1. Patch `sky130A.tech` to add `notouch`/same-net exception for li1 abutting cells
2. Use `drc style drc(fast)` instead of `drc(full)` in drc.tcl
3. Use Magic interactive Python API to run Magic DRC with per-step config

### Sky130A SRAM Macro Placement — Routing Channel Sizing

**Macro**: `sky130_sram_1kbyte_1rw1r_32x256_8` — 479.78 × 397.5 µm
**SRAM LEF** already declares full met1+met2 blockage (OBS block at line 889 of LEF):
```
OBS
LAYER  met1 ; RECT  0.62 0.62 479.16 396.88
LAYER  met2 ; RECT  0.62 0.62 479.16 396.88
```
Do NOT add `ROUTING_OBSTRUCTIONS` for the SRAM met1/met2 — the native LEF OBS already
covers the full footprint. Redundant obstructions disrupt GPL's congestion cost map
and cause DRT to enter pathological rip-up-reroute loops (Run 5: 100-160 violations,
6+ hours hung).

**Minimum inter-SRAM routing channel**: 200 µm between adjacent data SRAMs.
- tag → data[0]: 100 µm gap adequate (no routing between them)
- data[i] → data[i+1]: 200 µm gap required (routing channels pass between)

**Die sizing for 10 × sky130_sram_1kbyte (2 rows of 5 SRAMs)**:
- 5 SRAMs in X: 5 × 479.78 + 4 × 200 = 3299 µm stdcell footprint → die width ≥ 3600 µm
- 2 rows of SRAMs: 2 × 397.5 + 500 = ~1300 µm stdcell → die height ≥ 1800 µm
- Confirmed working: `DIE_AREA: [0, 0, 3600, 1800]`, `CORE_AREA: [20, 20, 3580, 1780]`

### json_header_patched.py — Nix Store / PYTHONPATH Fix

`librelane/scripts/pyosys/json_header_patched.py` is an untracked local patch in the
source repo but NOT in the read-only nix store at
`/nix/store/.../site-packages/librelane/scripts/pyosys/`. Without it, `Yosys.Synthesis`
fails at `json_header_patched` import.

**Fix**: Prepend `PYTHONPATH` to force Python to load librelane from local source first:
```bash
cd pnr/sky130/cpu && PYTHONPATH=/home/neuromorphic/Downloads/Github/librelane \
  nix-shell /home/neuromorphic/Downloads/Github/librelane \
  --run 'openlane config.json' 2>&1 | tee /tmp/sky130_cpu_run.log
```
Nix `sitecustomize.py` adds `PYTHONPATH` entries to `sys.path` BEFORE `NIX_PYTHONPATH`,
so the local librelane source takes precedence over the nix store.

### Sky130A Netgen LVS — SRAM Subcircuit Missing

**Symptom**: Netgen LVS reports "no matching pin" or subcircuit not found for SRAM.
**Fix**: Add SRAM SPICE model to `EXTRA_SPICE_MODELS`:
```json
"EXTRA_SPICE_MODELS": [
    "/home/neuromorphic/.volare/sky130A/libs.ref/sky130_sram_macros/spice/sky130_sram_1kbyte_1rw1r_32x256_8.spice"
]
```

### Sky130A SDC — Scalar Port Bus Expansion Error

**Symptom**: STA-0366 on `debug_pc_src_o[*]` — port is 1-bit scalar, not an array.
**Fix**: Use `get_ports debug_pc_src_o` (no index) instead of `{debug_pc_src_o[*]}`.

### Sky130A CPU Run 8 — Authoritative PPA (2026-06-30, honest timing with set_driving_cell)

Run 8 is the authoritative sign-off run. Run 6 (+0.366 ns) was optimistic — no input drive
modelling. Run 8 adds `set_driving_cell sky130_fd_sc_hd__buf_4` (CodeRabbit #2).

- Run tag: `RUN_2026-06-30_05-37-56` at `/nobackup/sky130_cpu_runs/`
- CLOCK_PERIOD: 13.333 ns → fmax: 75 MHz
- Setup WNS: +0.2285 ns (nom_tt) / TNS: 0 — PASS  [Run 6 was +0.366 ns without input drive]
- Hold R2R WNS: +0.6191 ns — PASS at all corners (0 R2R violations)
- Hold I/O WNS: -0.2930 ns (nom_tt, 87 paths) — block-level artifact (same class as Run 6 -0.102)
- max_tt corner: 2 setup violations, WNS -0.188 ns — marginal; nom/FF corners all clean
- KLayout DRC: 0 — PASS
- Netgen LVS: MATCH (0 errors) — PASS
- Magic DRC (Run 8): 27,733,913 — SRAM full .mag loaded (same root cause as Run 6)
- Magic DRC (standalone fix test, 2026-06-29): 3,626 total coord-pair entries — read_extra_lef fix
  applied; SRAM li.3 violations GONE; remaining = 3,626 nwell.4 DEF+LEF abstract-view artifacts
  (906 distinct nwell.4 rule instances × ~4 coord pairs each ≈ 3,626; full-die uniform)
- Antenna: 91 nets (I/O ports) — block-level artifact
- Power: 88.5 mW total (nom_tt, 75 MHz)
- Die: 3600 × 1800 µm; Core util: 40.67%
- AXI4 burst ports in LEF: arlen[7:0], arsize[2:0], arburst[1:0], awlen[7:0], awsize[2:0],
  awburst[1:0] — bead g0o CLOSED (confirmed in Run 8 LEF)
- Macro views: `pnr/sky130/cpu/macro/rv32i_cpu_top.lef` + `rv32i_cpu_top__nom_tt_025C_1v80.lib`
  (regenerated from Run 8)

### Sky130A CPU Run 6 — Baseline PPA (2026-06-29, superseded by Run 8)

- Run tag: `RUN_2026-06-29_09-15-44`
- Setup WNS: +0.366 ns (nom_tt) — OPTIMISTIC (no set_driving_cell; input slew = 0)
- All other metrics similar to Run 8; superseded by Run 8 for sign-off purposes

### Sky130A Magic DRC — SRAM Full Layout Loading (CONFIRMED 2026-06-29)

**Root cause**: In LibreLane DEF+LEF mode (`MAGIC_DRC_USE_GDS: false`), `drc.tcl` calls
`read_macro_lef` (reads from `MACRO_LEFS` env var) before `def read`. When `MACRO_LEFS` is
empty (no `MACROS` object in config.json), `read_macro_lef` loads nothing. When `def read`
then processes an SRAM instance, Magic searches its addpath for the cell definition and finds:
`/sky130A/libs.ref/mag/sky130_sram_macros/sky130_sram_1kbyte_1rw1r_32x256_8.mag`
(full layout: 72,269 lines, 40,000+ rects when expanded). The SRAM internal li1 geometry
at SRAM-specific sub-0.17µm pitches causes 27.7M `li.3` violations inside the SRAM footprints.

**Evidence confirming root cause**:
1. SRAM-core specific rules (`poly.8`, `diff/tap.2`) appear in report → Magic read SRAM internals
2. Violation coordinates cluster at x≈239-258µm, y≈313-314µm → inside SRAM bounding boxes
3. After fix: all li.3 violations disappear

**Fix layer 1** (drc.tcl patch — permanent):
Added `read_extra_lef` before `read_def` in
`/home/neuromorphic/Downloads/Github/librelane/librelane/scripts/magic/drc.tcl`:
```tcl
read_macro_lef
read_extra_lef     ← NEW (loads SRAM LEF abstract from EXTRA_LEFS before def read)
read_def
```
This causes Magic to find the SRAM cell already defined (from LEF abstract, 554 lines,
no li1 geometry) when `def read` encounters SRAM instances → full `.mag` NOT loaded.

**Fix layer 2** (config.json MACROS object — proper LibreLane approach):
```json
"MACROS": {
    "sky130_sram_1kbyte_1rw1r_32x256_8": {
        "gds": ["/path/to/sram.gds"],
        "lef": ["/path/to/sram.lef"],
        "lib": {"*": ["/path/to/sram.lib"]},
        "spice": ["/path/to/sram.spice"]
    }
}
```
With `MACROS`, LibreLane sets `MACRO_LEFS` from `MACROS.lef` → `read_macro_lef` (already in
`drc.tcl`) loads the SRAM LEF abstract. No `drc.tcl` patch needed for future full runs.
Both fixes applied for belt-and-suspenders: `EXTRA_LEFS` → `read_extra_lef`, `MACROS.lef`
→ `read_macro_lef` (both load the same SRAM abstract, idempotent in Magic).

**Result after fix** (standalone test on Run 6 DEF, 2026-06-29):
- Before: 27,733,913 (27.7M li.3 from SRAM internals)
- After: 3,626 total coord-pair entries (906 distinct `nwell.4` rule instances × ~4 coord pairs each)

**Remaining 3,626 coord pairs = nwell.4 DEF+LEF artifact** (906 distinct instances):
Rule: "All nwells must contain metal-connected N+ taps". In DEF+LEF mode, abstract LEF views
don't expose the actual N-well geometry inside stdcells. Magic can't verify tap-to-nwell
connectivity from abstracts → false `nwell.4` fires. Distribution: full die (X: 20–3460µm,
Y: 23–1774µm), ~1.4 violations per stdcell row. KLayout DRC = 0 on same design (full merged
GDS) confirms these are artifacts (no real nwell violations in the design).

To get Magic DRC = 0:
- Set `MAGIC_DRC_USE_GDS: true` + `MACROS` declared (SRAM black-boxed in merged GDS)
- Requires full LibreLane re-run (~4 hours) for Magic to read full merged GDS

**Decision for Sky130 CPU Stage 1 (FINAL 2026-06-30)**: Accept KLayout DRC=0 + Netgen LVS=MATCH
as the authoritative sign-off. Magic DRC=27,733,913 is a documented stock-tool artifact.

**Final config choice (Option A)**: EXTRA_LEFS-based config with MAGIC_DRC_USE_GDS=false and NO
MACROS object. This is the exact Run-6 validated state (RUN_2026-06-29_09-15-44). Reproducible
with stock LibreLane tools, no drc.tcl patch required.

#### Quantitative confirmation (2026-07-28, bead 45a — re-derived, then closed)

⚠️ Bead 45a was filed 2026-07-27 asking whether the 27.7M were real, **unaware this section
already answered it on 2026-06-29**. Read this section first before re-opening the question.
The 2026-07-28 pass added hard numbers and three genuinely new facts (marked NEW below).

Exhaustive streaming classification of **every** coordinate in the 1.1 GB report from
`RUN_2026-07-27_20-33-10/63-magic-drc` (not sampled; reproduced twice with independent awk passes):

| Zone | Count | % |
|------|-------|---|
| Inside one of the 10 SRAM footprints | 27,730,498 | **100.0000 %** |
| Routing channel (417.5 < y < 520) | 0 | 0 % |
| Standard-cell logic zone (y > 917.5) | 0 | 0 % |

Coordinate extents x 0..3189.11 µm, y 0..**907.87** µm. The logic zone begins at y=917.5 —
nothing is reported above 907.87. Rightmost SRAM's right edge = 2719.12+479.78 = 3198.90.

Per-rule-family (all 26 families 100 % SRAM-internal, none leak outside): diff/tap.9 3,017,505;
licon.1 2,572,862; li.1 2,278,399; licon.5a 2,262,998; licon.8 1,850,092; poly.8 1,833,708;
diff/tap.1 1,820,192; licon.14 1,697,877; via.1a+2·via.4a 1,597,260; poly.4 1,339,088;
met1.4 841,738; **li.3 922,628**. Note li.3 is *not* the dominant family once counted —
earlier notes calling this "27.7M li.3" overstate that one rule.

**NEW 1 — why KLayout reports 0 on the identical GDS.** `sky130A_mr.drc` has explicit,
hierarchy-aware SRAM exclusion: `SRAM_EXCLUDE=true` →
`not_sram = layout(source.cell_obj).select("-*sky130_sram_*kbyte_*")`, subtracting all shapes in
cells matching the SRAM macro name from the nsdm/psdm/nwell rule groups. The deck log states it:
`nwell.6 | sky130_fd_io__gpiov2_amux, sky130_fd_io__simple_pad_and_busses, sram` and
`nsd.1/nsd.2/psd.1/psd.2 | sram` — the foundry deck groups this SRAM with the I/O pad cells and
treats it as a pre-verified hard macro by convention. KLayout also splits li1 via an `areaid:ce`
scope (strict li.1/li.3 0.17 µm outside, relaxed li.7/li.8 0.14 µm in core) — the same intent as
Magic's `COREID`/`coreli`, but it works here where Magic's does not.

**NEW 2 — SoC-vs-CPU asymmetry reconciled.** The Sky130 SoC run reports only 9,081 on a *larger*
die = 9,049 `nwell.4` + 32 `met4.4a`, a **completely disjoint** rule set (zero li.3/licon/poly/diff),
not a diluted CPU flood. `pnr/sky130/soc/config.json` declares the CPU as a hard `MACROS` entry
with `MAGIC_DRC_USE_GDS=false`, so `read_macro_lef` loads the CPU LEF abstract before `def read`
and Magic never reaches CPU-internal (hence SRAM-internal) geometry. **The SRAM-flood failure mode
is structurally impossible at SoC level.** The 9,049 `nwell.4` is the same DEF+LEF-abstract artifact
class documented above at 3,626 on the smaller CPU-only test — same phenomenon, larger die.

**NEW 3 — sky130A techfile layer/datatype gap (bead y0w).** `sky130A.tech` maps GDS layer 235 only
at datatype 4 (→ CELLBOUND), but `sky130_fd_bd_sram__openram_dp_cell{,_dummy,_replica,_cap_row}`
draw their boundary at 235/**0**; layers 33 (42/43) and 22 (21/22) are unmapped entirely. This is
the exact cause of the fatal `Unknown layer/datatype in boundary` abort under
`MAGIC_DRC_USE_GDS=true`. It is mechanistically relevant — `coreli` classification derives from
`COREID`, bloated off the same CELLBOUND geometry Magic can't read — but it is **not** the driver
of the flood: DEF+LEF mode never invokes that GDS calma path and still gives 27,733,913 (Δ 0.01 %).
Filed low-priority; only matters if GDS mode is ever wanted again.

**Bottom line, unchanged**: Magic's flat `drc(full)` engine cannot validate this dense custom
OpenRAM macro's internals regardless of read path. KLayout DRC=0 + Netgen LVS=MATCH + DRT 0 are
authoritative for Sky130 Stage-1. Stages 2–4 inherit the waiver cleanly. Keep
`MAGIC_DRC_USE_GDS: false` — `true` aborts the flow and produces the same count anyway.

> ⚠️ **Scope of the KLayout DRC=0 result — state this whenever the sign-off is cited.**
> `sky130A_mr.drc` runs with `SRAM_EXCLUDE = true`, implemented as
> `layout(source.cell_obj).select("-*sky130_sram_*kbyte_*")`, which subtracts every shape
> belonging to the SRAM macro cells from the nsdm/psdm/nwell rule groups. So **KLayout DRC = 0
> validates the design *surrounding* the SRAM macros — it does not verify SRAM internal
> geometry.** Neither tool independently signs off the macro interior: Magic sees it and floods,
> KLayout excludes it by deck design.
>
> The sign-off contract is therefore conditional, and should be written that way:
> **(a)** the non-SRAM design is clean — KLayout DRC 0, Netgen LVS MATCH, DRT 0; **(b)** the
> `sky130_sram_1kbyte_1rw1r_32x256_8` macro interior is accepted as **pre-verified vendor IP**,
> on the strength of the foundry deck grouping it with the `sky130_fd_io__*` pad cells (the same
> treatment given to hardened I/O), not on the strength of any check run in this project.
> If (b) is ever unacceptable — e.g. a real tape-out on this macro — the macro interior needs
> independent verification (vendor DRC report, or a Magic run with a techfile that matches the
> macro GDS vintage; see bead y0w for why the current techfile cannot do that).
> Related precedent: GH #121 found 4 real macro-internal KLayout violations in the *OpenRAM*
> SRAM used at SoC level, which is direct evidence that these macro interiors are not
> automatically clean.

**GDS-mode investigation conclusion (2026-06-30)**:
- `MAGIC_DRC_USE_GDS: true` + `MACROS` cannot achieve Magic DRC=0 because `gds write` embeds
  the full SRAM cell hierarchy into the merged GDS via the `GDS_FILE` property pointer mechanism.
  Magic's `gds write` reads `GDS_FILE` at write time and copies SRAM cells into the output.
  The 224 MB merged GDS in GDS mode = same SRAM geometry as the 216 MB DEF-mode GDS.
- Magic DRC in GDS mode reads all embedded SRAM cells → same li.3 violations return.
- `read_extra_gds` override via `EXTRA_GDS_FILES` removal: correctly prevents double-loading,
  but does not prevent the `GDS_FILE` property expansion at `gds write` time.

**LibreLane upstream fix candidate** (requires tool-repo PR):
Add `read_extra_lef` before `read_def` in DEF+LEF mode of `drc.tcl`:
```tcl
} else {
    source $::env(SCRIPTS_DIR)/magic/common/read.tcl
    read_tech_lef
    read_pdk_lef
    read_macro_lef
+   read_extra_lef        ; # loads EXTRA_LEFS (e.g. OpenRAM SRAM) as abstracts
    read_def
}
```
This gives 3,626 nwell.4 DEF+LEF artifacts (vs 27.7M li.3 without it). The nwell.4 artifacts
require GDS mode (`MAGIC_DRC_USE_GDS: true`) to eliminate — GDS mode loads full stdcell geometry
and resolves nwell tap connectivity. However, GDS mode with OpenRAM SRAM macros embeds full SRAM
geometry, causing a different set of SRAM-internal violations. The complete zero-violation solution
requires hierarchical DRC with SRAM cells marked as pre-verified (Magic `-nocheck` property or
equivalent), which is not supported in the current stock `drc.tcl`.

## Local LibreLane patch: heuristic diode insertion skips clock-network nets
### (Sky130 SoC bead 58q, 2026-07-30)

**Applies to**: `~/Downloads/Github/librelane` local checkout only. **NOT tracked by this project
repo** — same class of patch as the `pdn.tcl`/`drt.tcl` non-fatal-error patches above. Re-apply
after any librelane reinstall/update. Files: `librelane/scripts/odbpy/diodes.py`,
`librelane/steps/odb.py`.

**Problem**: `Odb.HeuristicDiodeInsertion` (`RUN_HEURISTIC_DIODE_INSERTION: true`), when enabled
on the Sky130 SoC (large die, 6700×3100 µm), inserts diodes on ~24× more cells than needed
(1,934 → 47,385 `ANTENNA_*` instances measured on this design) because its net-selection loop
(`DiodeInserter.execute()` in `diodes.py`) has no clock-awareness:
1. It walks **every** net in the design and inserts a diode on every sink pin of any net whose
   Manhattan bounding-box span exceeds `HEURISTIC_ANTENNA_THRESHOLD` (default 90 µm on sky130A).
   The CTS clock tree is not uniformly short-hop — measured span distribution on this design shows
   1,345 clock-related nets with median 68.7 µm but a real tail: 226 nets ≥90 µm, 208 nets ≥105 µm
   (deep in the same range as genuine long-route antenna violators, 105–4517 µm, median 686 µm).
   No threshold value cleanly separates the two populations — verified by direct measurement, not
   assumed (see `memory/pd/run_state.md`, bead 58q run3→run4 investigation, for the full
   distribution data and the ruled-out threshold experiment).
2. Independently of (1): `Odb.FuzzyDiodePlacement.get_command()` (the step wrapping the heuristic
   pass) never passes `--port-protect` to `diodes.py place`, so it silently inherits that CLI
   option's own hardcoded default of `"in"` — **independent of the `DIODE_ON_PORTS` LibreLane
   variable entirely**. This means the heuristic pass always force-inserts a diode on every design
   input port net (`clk_i` included) regardless of threshold or `DIODE_ON_PORTS`.

Diode placement (`DiodeInserter.place_diode_stdcell`, default `side_strategy="source"`) always
abuts the diode directly against the **first sink instance** of the protected net. For a clock net
this lands the diode directly on the clock-tree root/leaf buffer's input pin, physically disrupting
placement/legalization at that exact point. Measured on this design: `clk_i -> u_cpu/clk_i` clock
latency at nom_tt grew from 0.870159 ns (clean) to 1.439363 ns (heuristic on, +0.569 ns) — this
single mechanism was traced (grep the netlist for `ANTENNA_clkbuf_0_clk_i_A` etc., confirmed via a
post-CTS-vs-post-repair step comparison that ruled out CTS variation as the cause) to a hold
regression at 5 of 9 corners that had previously been clean.

**Root cause confirmed NOT threshold-fixable**: raising `HEURISTIC_ANTENNA_THRESHOLD` cannot
separate the two populations (see distribution above) and cannot avoid the `clk_i`-port-forced
diode at any threshold value (the io-protect path bypasses the span check unconditionally).

**Fix**: add clock-net awareness via `dbNet.getSigType() == "CLOCK"` — the odb-native,
CTS-assigned classification that correctly covers both the clock root net (`clk_i`) and every
downstream CTS-inserted buffer-to-buffer segment (confirmed via direct odb query: 1,327 CLOCK-typed
nets on this design, vs 1,345 nets found by a fragile `"clk"` substring match — do not use name
matching, it was explicitly considered and rejected for robustness). Opt-in via a new
`--skip-clock-nets` CLI flag / `HEURISTIC_ANTENNA_SKIP_CLOCK_NETS` LibreLane Variable, default
`False`, so CPU/SRAM/GPU stage-1 macro configs that already use
`RUN_HEURISTIC_DIODE_INSERTION: true` are completely unaffected unless they opt in.

`diodes.py` — `DiodeInserter.__init__` gains `skip_clock_nets: bool = False`; `execute()` gains,
right after the existing `isSpecial()` check:
```python
if self.skip_clock_nets and net.getSigType() == "CLOCK":
    self.debug(f"[d] Skipping clock-network net {net.getConstName():s}")
    continue
```
The `place` click command gains a `--skip-clock-nets` flag (`is_flag=True, default=False`), threaded
through to the constructor.

`steps/odb.py` — `FuzzyDiodePlacement.config_vars` gains:
```python
Variable(
    "HEURISTIC_ANTENNA_SKIP_CLOCK_NETS",
    bool,
    "... exclude SigType CLOCK nets from heuristic diode insertion and "
    "disable port-forcing ...",
    default=False,
),
```
and `get_command()` gains:
```python
skip_clock_opts = []
if self.config["HEURISTIC_ANTENNA_SKIP_CLOCK_NETS"]:
    skip_clock_opts = ["--skip-clock-nets", "--port-protect", "none"]
```
(appended to the returned command list). `--port-protect none` is passed alongside
`--skip-clock-nets` specifically to also kill the independent port-forcing default described above
— both are needed to fully stop `clk_i` from being diode-protected by this step.

**Verified working** (smoke test, `openroad -exit -no_splash -python librelane/scripts/odbpy/
diodes.py place -v --skip-clock-nets --port-protect none -t 90 <odb>`, run against
`RUN_2026-07-30_06-42-17/37-openroad-repairdesignpostgrt/soc_top.odb`): exactly 1,327 "Skipping
clock-network net" debug lines (matches the odb CLOCK-sigtype count exactly), zero `clk_i` diode
insertions, non-clock long nets still correctly protected (e.g. `_00000_` at 428 µm still gets a
diode). Full-flow result (`HEURISTIC_ANTENNA_SKIP_CLOCK_NETS: true` +
`RUN_HEURISTIC_DIODE_INSERTION: true`, keeping `GRT_ANTENNA_ITERS=8`/`GRT_ANTENNA_MARGIN=25`/
`CLOCK_PERIOD=25.0` from the accepted run3 baseline) is bead 58q run4 — see
`memory/pd/run_state.md` for the outcome once landed.

**How to re-apply after a librelane reinstall**: the exact diff is checked into THIS repo (not
just the local librelane checkout) at
`memory/pd/patches/58q_librelane_heuristic_diode_skip_clock_nets.diff` — apply with
`cd ~/Downloads/Github/librelane && git apply /path/to/that/diff` (or by hand, it's ~127 lines
across the two files, both edits shown in full above). No other files touched. Any future design
that wants this behavior sets `HEURISTIC_ANTENNA_SKIP_CLOCK_NETS: true` in its own `config.json`;
the default is off everywhere
else.

---

### Odb.HeuristicDiodeInsertion costs ~0.5 ns of clock latency — BINARY, not tunable (bead 58q, 2026-07-31)

**The single most reusable finding of the Sky130 SoC antenna campaign.** If a design is
hold-sensitive, `RUN_HEURISTIC_DIODE_INSERTION` is an all-or-nothing choice. Do not spend runs
trying to tune it down — three separate levers were tried and all failed identically.

Six-run evidence, `clk_i -> u_cpu/clk_i` at nom_tt on the same design:

| run | heuristic pass | stdcells | clk latency | hold |
|-----|---------------|----------|-------------|------|
| baseline | off | 226,454 | **0.870159** | clean 9/9 |
| run 3 | off | 226,952 | **0.933178** | clean 9/9 |
| run 5 | **ON** | 234,371 | **1.381585** | fails 5/9 |
| run 4 | **ON** | 270,217 | **1.410208** | fails 5/9 |
| run 2 | **ON** | 272,003 | **1.388234** | fails 5/9 |
| run 1 | **ON** | 271,858 | **1.439363** | fails 5/9 |

Latency is binary on whether the step runs. Among the ON runs, cell count spans 234k-272k — a
38k spread — with no material latency effect (1.38-1.44 ns). Off: 0.87-0.93 ns.

**Mechanism**: the step is not just diode insertion. It wraps
`1-odb-fuzzydiodeplacement` -> `2-openroad-detailedplacement` -> `3-openroad-globalrouting`,
i.e. it **re-legalizes placement and re-routes globally** after inserting. That perturbation
lengthens the clock-root route by ~0.45-0.5 ns whether it placed 7,970 diodes or 44,742.

**Levers that do NOT help** (all reduce *what* is inserted; the cost comes from the pass
*running*):
- `DIODE_ON_PORTS: none` — no effect on latency
- clock-net exclusion (`HEURISTIC_ANTENNA_SKIP_CLOCK_NETS`, the patch documented above) —
  achieves literally zero diodes on any CLOCK-sigtype net, no effect on latency
- `HEURISTIC_ANTENNA_THRESHOLD: 800` — 5.6x fewer diodes (7,970 vs 44,742), no effect on latency

**Which hold paths break**: only the I/O-boundary class — input ports carry no clock-network
delay on the data side but the full clock-tree latency on the capture side, so there is no
cancellation cushion and a clock-latency increase hits them directly. Here that was
`apb_paddr_i/psel_i/penable_i/pwdata_i -> u_cpu`, 100% of violators, zero reg-to-reg. The SDC
multicycle on that group is correctly paired (`2 -setup` / `1 -hold`) — this is physical, not a
constraint bug.

**What it buys**, for the cost/benefit call: heuristic ON gives antenna 40-90 violations vs
140/120 with it off (baseline 147/127). GRT repair alone (`GRT_ANTENNA_ITERS=8`,
`GRT_ANTENNA_MARGIN=25`) delivers only 147 -> 140.

**Untried lever, recorded for whoever needs better antenna on a hold-sensitive design**:
GRT-based `RepairAntennas` does *not* trigger the legalization sub-steps, so pushing
`GRT_ANTENNA_ITERS`/`GRT_ANTENNA_MARGIN` harder should improve antenna without the hold cost.
Run 3 already used 8/25 for 140/120, so expect incremental gains.

**Process note worth carrying forward**: four successive root-cause claims on this campaign were
wrong — cell-count pressure (raised, retracted, wrongly re-adopted), `DIODE_ON_PORTS`,
clock-tree diodes, and a cell-volume model. Every one was caught by attaching a falsifiable
prediction to the next run, never by a run coming back green. Attach a guard to any claim here.

### RCX_RULESETS 0-byte stub — FIXED 2026-08-16 (bead claude_verilog_test-e69)

`~/pdk/asap7/libs.tech/openlane/rcx_rules.pex` used to be a 0-byte stub, so `OpenROAD.RCX`
could never emit a SPEF and `OpenROAD.STAPostPNR`/`OpenROAD.IRDropReport` (both hard-require
SPEF as a step input) were unusable — every ASAP7 sign-off's final metrics were post-GRT
*estimated* RC, never post-route extraction.

**Fix**: vendored the real OpenRCX ruleset from OpenROAD-flow-scripts
(`flow/platforms/asap7/rcx_patterns.rules`, commit `8ad0ff779`, 117122 bytes; ORFS itself uses
it as `RCX_RULES`). Geometry-equivalence with this repo's tech LEF was hand-verified first (all
76 WIDTH/PITCH/SPACING/THICKNESS/DIRECTION lines across the 10 ROUTING layers match byte-for-
byte). Reproducible install: `tools/setup/install_asap7_rcx_rules.py` (stdlib, `--check-only`
mode) + `pnr/Makefile` targets `install-asap7-rcx-rules` / `check-asap7-rcx-rules` — the latter
is now a prerequisite of `librelane-asap7` (CPU target only; GPU/SoC configs left at
`RUN_SPEF_EXTRACTION: false`, unvalidated). `~/pdk/asap7` is not git-tracked, so this installer
must be re-run on every fresh machine/clone.

Standalone validation (`read_db` + `define_process_corner` + `extract_parasitics
-ext_model_file <rcx_rules.pex>` against a real ODB, no LibreLane needed): the ruleset loads
and is consumed by OpenRCX with zero parse/format errors. If you see `[WARNING RCX-0107]
Nothing is extracted out of N nets!` and `write_spef` no-ops, that means the ODB you handed it
has no routed wires — check `route__wirelength__max` in that step's `or_metrics_out.json`
before blaming the ruleset. See the next entry.

### CRITICAL — ASAP7 detailed routing has been silently producing ZERO committed wires (bead claude_verilog_test-xy6, P1, filed 2026-08-16)

**Do not trust "0 routing DRC" on any ASAP7 CPU or SoC run from 2026-08-08 onward (including
the celebrated run 23, `RUN_2026-08-09_14-36-16`, and the `#96` CPU pin-order tuning runs)
until this bead is resolved.** Measured, not inferred:

- `openroad-detailedrouting.log` dies during **pin access**, before the main track-assignment /
  search-and-repair loop ever starts: `[ERROR DRT-0073] No access point for
  u_gpu/m_axi_araddr[19]` (SoC) or 401× `[ERROR DRT-0074] No access point for
  PIN/apb_prdata_o[N]` / `apb_pslverr_o` / `apb_pready_o` (CPU — exactly the 3 pins bead
  `cyb`/`g0o` made "pure registered outputs"). LibreLane's wrapper treats this as non-fatal
  (`WARNING: detailed_route reported errors; continuing (DRT may be incomplete)`) and writes
  out the DB as-is — which is the pre-route placed/CTS'd netlist, not a routed one.
- Proof the DB really has no routing: `<run>/*/or_metrics_out.json` →
  `route__wirelength__max: 0`; `wire_lengths.csv` has only a header row; the final DEF has zero
  `ROUTED ` occurrences (`grep -c 'ROUTED ' <run>/final/def/*.def`); a direct odb query
  (`foreach n [$block getNets] { $n getWire }`) returns `NULL` for every net.
  `antenna__violating__nets/pins: 0` and `flow__errors__count: 0` in the final aggregate are
  trivially true with nothing routed to check — they are not evidence of a clean route.
- **Check this on any ASAP7 run before citing its DRC/antenna/wirelength numbers**:
  `python3 -c "import json; print(json.load(open('<run>/*-odb-reportwirelength/or_metrics_out.json'))['route__wirelength__max'])"`
  — if it prints `0`, the run's checker-stage "0 violations" is a null result, not a pass.
- Suspected (unconfirmed) trigger: the run-23-era change registering
  `apb_prdata_o`/`apb_pslverr_o`/`apb_pready_o` as pure outputs, and/or the `FP_PIN_ORDER_CFG`
  macro-boundary pinning from bead `g0o`, may have moved these pins into a position/geometry
  DRT can't find a legal access point for. Not root-caused yet.
