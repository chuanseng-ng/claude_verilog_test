run_id:      pd_20260629_021153
design_name: rv32i_cpu_top
pdk:         sky130A
tool:        LibreLane/OpenLane2-Classic
start_time:  2026-06-29T09:15:44+07:00
last_stage:  signoff (Option C ACCEPTED)

run8_rerun:
  run_id:      pd_20260630_run8
  run_tag:     RUN_2026-06-30_05-37-56
  start_time:  2026-06-30T05:37:56+07:00
  reason:      CodeRabbit finding #2 — add set_driving_cell for honest timing
  change:      sky130_cpu.sdc: added set_driving_cell sky130_fd_sc_hd__buf_4 on all_inputs
  status:      COMPLETE
  log:         /nobackup/sky130_cpu_run8.log
  honest_timing_results:
    setup_wns_nom_tt_ns:   +0.2285   (was +0.366 optimistic before set_driving_cell)
    setup_tns_nom_tt_ps:   0
    hold_r2r_wns_ns:       +0.6191   (0 R2R violations all corners)
    hold_io_wns_nom_tt_ns: -0.2930   (87 paths — block-level artifact, same class as Run 6)
    klayout_drc:           0
    lvs:                   MATCH
    drt_violations:        0         (13 routing iterations)
    power_mw:              88.5
    util_pct:              40.67
    max_tt_marginal:       2 setup violations (WNS -0.188 ns) — nom/FF corners clean

run_dir:     /nobackup/sky130_cpu_runs/RUN_2026-06-30_05-37-56
run_tag:     RUN_2026-06-30_05-37-56

status:
  synthesis:          PASS
  floorplan:          PASS
  placement:          PASS
  cts:                PASS
  routing:            PASS (0 DRT violations after 13 iters)
  spef_extraction:    PASS
  stapostpnr:         WARN (hold I/O violations — block-level artifact; setup nom_tt PASS)
  klayout_drc:        0 (PASS — authoritative foundry DRC)
  netgen_lvs:         MATCH (PASS — "Circuits match uniquely.")
  magic_drc:          27,733,913 (DOCUMENTED TOOL ARTIFACT — see magic_drc_analysis below)
  signoff_overall:    PASS (Option C accepted, Run 8 honest numbers)

config_choice:  run8_honest (CodeRabbit fixes applied)
config_file:    pnr/sky130/cpu/config.json
config_note:    Run 8 config (authoritative sign-off run):
                - MAGIC_DRC_USE_GDS: false
                - EXTRA_GDS_FILES/LEFS/LIBS/SPICE_MODELS: pdk_dir:: portable paths (CR #1)
                - sky130_cpu.sdc: set_driving_cell sky130_fd_sc_hd__buf_4 (CR #2)
                - NO MACROS object
                - Stock drc.tcl (no read_extra_lef patch)

key_metrics:  (Run 8 — RUN_2026-06-30_05-37-56 — AUTHORITATIVE)
  fmax_mhz:              75
  setup_wns_nom_tt_ns:   +0.2285  (honest: was +0.366 without set_driving_cell)
  setup_tns_nom_tt_ps:   0
  hold_r2r_wns_ns:       +0.6191  (0 R2R violations, all corners)
  hold_io_wns_nom_tt_ns: -0.2930  (87 paths — block-level artifact)
  power_mw:              88.5
  util_pct:              40.67
  die_um:                3600x1800
  klayout_drc:           0
  lvs_errors:            0
  magic_drc:             27,733,913 (SRAM artifact — see below)
  antenna_nets:          91 (I/O ports)
  drt_violations:        0
  max_tt_note:           2 setup violations (WNS -0.188 ns) — marginal regression from set_driving_cell

magic_drc_analysis:
  ROOT CAUSE CONFIRMED (2026-06-29):
  Magic DEF mode resolves SRAM instances by searching magic addpath.
  Finds sky130_sram_1kbyte_1rw1r_32x256_8.mag (72,269 lines, full layout).
  Loads all internal SRAM geometry -> 27.7M li.3 (locali spacing) + poly.8/licon.*/diff.tap.3.

  Proof: KLayout DRC=0 on the IDENTICAL 216 MB merged GDS.

  Standalone test result: 27.7M -> 3,626 (nwell.4 DEF+LEF abstract artifacts)
  with read_extra_lef added before read_def in drc.tcl.

  GDS mode investigation (2026-06-30):
  MAGIC_DRC_USE_GDS=true cannot achieve 0: gds write copies SRAM cells via GDS_FILE property.
  Merged GDS in GDS mode = 224 MB (same SRAM geometry, different path to get there).
  Magic DRC in GDS mode reads full SRAM geometry -> li.3 returns.

  Final recommendation:
  - Accept KLayout DRC=0 as authoritative for this SRAM-macro design
  - Upstream LibreLane fix: add read_extra_lef before read_def in drc.tcl DEF+LEF path

macro_views:  (regenerated from Run 8)
  lef:     pnr/sky130/cpu/macro/rv32i_cpu_top.lef
  lib:     pnr/sky130/cpu/macro/rv32i_cpu_top__nom_tt_025C_1v80.lib
  nl_v_gz: pnr/sky130/cpu/macro/rv32i_cpu_top.nl.v.gz
  gds:     /nobackup/sky130_cpu_runs/RUN_2026-06-30_05-37-56/58-magic-streamout/rv32i_cpu_top.gds
  axi4_burst_ports_in_lef: confirmed (arlen, awlen, arburst, awburst, rlast, wlast, arsize, awsize)

staged_files:
  - pnr/sky130/cpu/config.json          (Run-6 validated state restored)
  - pnr/sky130/cpu/constraints/sky130_cpu.sdc
  - pnr/sky130/cpu/macro_placement.cfg
  - pnr/sky130/cpu/macro/rv32i_cpu_top.lef
  - pnr/sky130/cpu/macro/rv32i_cpu_top__nom_tt_025C_1v80.lib
  - pnr/sky130/cpu/macro/rv32i_cpu_top.nl.v.gz
  - design_state.json
  - memory/pd/experiences.jsonl
  - memory/pd/knowledge.md
  - memory/pd/run_state.md

pending:
  - DO NOT COMMIT -- awaiting user authorization
  - User must review staged files and approve commit + PR push
  - PR target: feat/sky130-cpu-drc-lvs-gh103
