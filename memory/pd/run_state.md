run_id:      pd_20261011_dud4_sky130_cpu_sv2v
design_name: rv32i_cpu_top (Sky130 CPU macro) then soc_top
pdk:         sky130A
tool:        LibreLane (nix), make -C pnr librelane-sky130-cpu / librelane-sky130-soc-rccal-noklayout
start_time:  2026-10-11
branch:      pd/sky130-cpu-sv2v-reharden-dud4 (worktree .claude/worktrees/agent-a30c85f22b16e994e)
bead:        dud4 (claimed; do not close; never git add .beads/)
last_stage:  S5 DONE; S6 RUNNING (launched 08:39 WIB): RUN_2026-10-11_08-39-41, make -C pnr librelane-sky130-soc-rccal-noklayout with CVT_SYNTH_GATE=warn (gate FAILED 509 x-driven-net func-temp false positives on SoC at first attempt RUN_2026-10-11_08-37-28). Log /nobackup/dud4_reharden/logs/s6_soc.log. If dead: check pgrep librelane, start a FRESH run (not -F).
old_macro_backup: /nobackup/dud4_reharden/old_macro (+ old_macro.sha256)
helper_scripts: /nobackup/dud4_reharden/{s2_build.sh,s4_build.sh,s4_negctl.sh,s5_install.sh,diff_run.sh,magic_footprint.py}; sim dirs /nobackup/claude_sim_build/dud4_reharden/{s2,s4}
runs_symlinks: pnr/sky130/cpu/runs -> /nobackup/sky130_cpu_runs ; pnr/sky130/soc/runs -> /nobackup/sky130_soc_runs (gitignored)
