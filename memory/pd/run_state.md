run_id:      pd_20261025_sky130_soc_reharden_batch
design_name: soc_top (Sky130)
pdk:         sky130A
tool:        LibreLane (nix) make -C pnr librelane-sky130-soc-noklayout (config_rccal.json), CVT_SYNTH_GATE=warn, MAKEFLAGS=-j2, systemd scope MemoryMax=12G (unit sky130-soc-batch)
branch:      feat/sky130-soc-reharden-batch (base a196947, SDC commit 82069c7), worktree .claude/worktrees/agent-adbabb48c270c511c
start_time:  2026-10-25 (relaunch ~08:28 host time after attempt 1 died at config load: untracked GDS/spice macro files missing in the worktree)
run_dir:     /nobackup/sky130_soc_runs/RUN_2026-10-25_08-28-45
launcher:    /tmp/sdcwork/launch.sh ; log /tmp/claude-1000/-home-neuromorphic-Downloads-Github-claude-verilog-test/70a8ff8f-92d6-4c5d-ba05-a9f7b2890a43/tasks/bubu3bcnn.output
baseline:    RUN_2026-10-17_23-06-56 (newest completed SoC run, j41m4 run5) and RUN_2026-10-11_08-39-41 (dud4)
last_stage:  running (synthesis/lint); expect 4-10 h
after_run:   make -C pnr check-cdc-timing-sky130-soc RUN_DIR=<run> (default nom_tt+max_ss), negative control CDC_CHECK_MBIST_BUDGET_NS=0.001, make -C pnr sky130-soc-maxcap-check, then hold on u_cpu apb_pwdata_i/apb_psel_i/axi_rdata_i/axi_rresp_i
