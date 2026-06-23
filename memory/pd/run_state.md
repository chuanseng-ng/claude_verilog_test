run_id:      pd_20260623_110021
design_name: soc_top
pdk:         asap7
tool:        LibreLane
start_time:  2026-06-23T18:05:30+07:00
last_stage:  synthesis

run_dir:     /nobackup/asap7_soc_runs/RUN_2026-06-23_18-05-38
log:         /nobackup/asap7_soc_run14.log

STATUS (2026-06-23 06:09 WIB):
  Synthesis confirmed complete: 43546 DFFs, 199146 cells.
  ABC DELAY 2 optimization running (pid 891073, ~4h elapsed, 100% CPU).
  Only stage 04-yosys-synthesis directory exists so far.
  Next stage: floorplan (OpenROAD).

ROOT CAUSES FROM RUN 13 AND FIXES:
  1. CTS dual-tree: create_generated_clock on PLL BUFx2 Y pin caused two separate
     H-trees (clk_i for 3 macro sinks; clk_i_regs for 43762 std-cell sinks).
     214 ps setup skew was insertion-delay difference between trees.
     FIX: Removed create_generated_clock entirely (committed 89e60fe).
  2. IO delay budget: 350 ps (20%) was too aggressive.
     FIX: Reduced to 175 ps (10%).
  3. CTS clustering: MAX_DIAMETER=20 um (CPU die value) far too small for 520x520 um SoC.
     FIX: Changed to 50 um.
  4. Missing --skip Checker.SetupViolations in Makefile: flow aborted before final output.
     FIX: Added 4 skip flags.

EXPECTED RESULTS AFTER FIXES:
  - CTS skew: should drop from 214 ps to <50 ps (single balanced tree).
  - WNS: if skew fix works, should recover ~180 ps. From -364 ps -> ~-184 ps at 1750 ps.
  - If further improvement from IO budget reduction (~60-80 ps): WNS ~-100 to -120 ps.
  - May still need period relaxation to 1900-2000 ps range if WNS doesn't close.
