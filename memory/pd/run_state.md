run_id:      pd_20261011_dud4_sky130_cpu_sv2v
design_name: rv32i_cpu_top (Sky130 CPU macro) then soc_top
pdk:         sky130A
tool:        LibreLane (nix), make -C pnr librelane-sky130-cpu / librelane-sky130-soc-rccal-noklayout
start_time:  2026-10-11
branch:      pd/sky130-cpu-sv2v-reharden-dud4 (worktree .claude/worktrees/agent-a30c85f22b16e994e)
bead:        dud4 (claimed; do not close; never git add .beads/)
last_stage:  S3 DONE: CPU P&R RUN_2026-10-11_06-00-12 (/nobackup/sky130_cpu_runs), rc 2 = deferred Magic DRC + nom_tt I/O hold only. LVS match, KLayout 0, routing DRC 0, setup tt/ff clean (+3.44 nom_tt), ss reg-to-reg FAIL (-3.20 nom_ss, -3.70 max_ss; icache tag SRAM half-cycle paths), hold r2r clean / I/O -0.379 nom_tt. Magic 27,733,913 (99.9869 % in SRAM footprints, 3626 nwell.4 outside = known). No final/ dir (deferred errors): views come from step dirs 54 (nl/pnl/def/odb), 59 (gds), 61 (lef), 67 (spice), 57/<corner>/*.lib.
next:        S4 post-P&R gate-vs-RTL on 54-openroad-fillinsertion/rv32i_cpu_top.nl.v (+ pnl.v), then S5 views, S6 SoC rccal run, S7 docs+draft PR
old_macro_backup: /nobackup/dud4_reharden/old_macro (+ old_macro.sha256)
helper_scripts: /nobackup/dud4_reharden/{s2_build.sh,diff_run.sh,magic_footprint.py}; S2 sim dir /nobackup/claude_sim_build/dud4_reharden/s2
runs_symlinks: pnr/sky130/cpu/runs -> /nobackup/sky130_cpu_runs ; pnr/sky130/soc/runs -> /nobackup/sky130_soc_runs (gitignored)
