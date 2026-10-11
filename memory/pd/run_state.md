run_id:      pd_20261011_dud4_sky130_cpu_sv2v
design_name: rv32i_cpu_top (Sky130 CPU macro) then soc_top
pdk:         sky130A
tool:        LibreLane (nix), make -C pnr librelane-sky130-cpu / librelane-sky130-soc-rccal-noklayout
start_time:  2026-10-11
branch:      pd/sky130-cpu-sv2v-reharden-dud4 (worktree .claude/worktrees/agent-a30c85f22b16e994e)
bead:        dud4 (claimed; do not close; never git add .beads/)
last_stage:  S4 DONE: post-P&R netlist (54-openroad-fillinsertion nl.v) census 4868 flops + fwd_b present; differential 6/6 identical, matrix 124/124; neg control (63 x1 read cells tie1) detected 4/6 programs, matrix FAIL 90. Next S5 views.
old_macro_backup: /nobackup/dud4_reharden/old_macro (+ old_macro.sha256)
helper_scripts: /nobackup/dud4_reharden/{s2_build.sh,diff_run.sh,magic_footprint.py}; S2 sim dir /nobackup/claude_sim_build/dud4_reharden/s2
runs_symlinks: pnr/sky130/cpu/runs -> /nobackup/sky130_cpu_runs ; pnr/sky130/soc/runs -> /nobackup/sky130_soc_runs (gitignored)
