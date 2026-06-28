run_id:      pd_20260628_080000
design_name: rv32i_cpu_top
pdk:         sky130A
tool:        LibreLane
start_time:  2026-06-28T08:00:00+07:00
last_stage:  floorplan

run_dir:     /nobackup/sky130_cpu_runs
log:         /tmp/sky130_cpu_run1.log

STATUS (2026-06-28 08:00 WIB):
  Run 1 LAUNCHING — Stage 1 Sky130 CPU standalone.
  GitHub issue: #103 (epic #102)
  Branch: feat/sky130-cpu-drc-lvs-gh103
  tmux session: sky130_cpu_run1

  KEY DIFFERENCES vs pnr/librelane/ (Phase 3):
  - RUN_MAGIC_DRC=true, RUN_KLAYOUT_DRC=true, RUN_LVS=true (REAL sign-off)
  - Full current RTL: includes axi_pkg.sv, rv32i_clock_gate.sv,
    rv32i_pipeline_ex.sv + ex1b + ex1c + ex2 (M4/M5/M7 additions)
  - AXI4 burst ports in SDC (arlen/arsize/arburst/rlast/awlen/awsize/awburst/wlast)
  - Config: pnr/sky130/cpu/config.json
  - Runs: /nobackup/sky130_cpu_runs

  Target metrics:
    WNS: >= 0 ns (75 MHz / 13.333 ns period)
    DRC: 0 violations (Magic sky130A.tech)
    LVS: MATCH (Netgen)
    Util: <= 85%
