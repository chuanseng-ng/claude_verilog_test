run_id:      pd_20261011_dud4_sky130_cpu_sv2v
design_name: rv32i_cpu_top (Sky130 CPU macro) then soc_top
pdk:         sky130A
tool:        LibreLane (nix), make -C pnr librelane-sky130-cpu / librelane-sky130-soc-rccal-noklayout
start_time:  2026-10-11
branch:      pd/sky130-cpu-sv2v-reharden-dud4 (worktree .claude/worktrees/agent-a30c85f22b16e994e)
bead:        dud4 (claimed; do not close; never git add .beads/)
last_stage:  S5 DONE: new CPU macro views installed in pnr/sky130/cpu/macro from RUN_2026-10-11_06-00-12 (LEF step61, 9 libs step57, nl.v.gz step54, gds step59, spice step67; tracked: lef/libs/nl.v.gz; gds/spice gitignored in worktree). sha table old/new: /nobackup/dud4_reharden/macro_sha_table.md. LEF: 403 pins, all position+layer identical to old (pin_order.cfg already pinned); ports 401 = RTL = stub = LEF. Libs: 9 distinct, per-corner temp/volt correct; 0 combinational in->out arcs now (old 462: registered APB outputs).
next:        S6 SoC run: cd worktree; make -C pnr sky130-soc-sv2v ; make -C pnr librelane-sky130-soc-rccal-noklayout (log /nobackup/dud4_reharden/logs/s6_soc.log). Check max_cap_waivers.json for u_cpu*/axi_rdata_i[12] vs new lib pin caps. Then S7 docs + draft PR.
old_macro_backup: /nobackup/dud4_reharden/old_macro (+ old_macro.sha256)
helper_scripts: /nobackup/dud4_reharden/{s2_build.sh,s4_build.sh,s4_negctl.sh,s5_install.sh,diff_run.sh,magic_footprint.py}; sim dirs /nobackup/claude_sim_build/dud4_reharden/{s2,s4}
runs_symlinks: pnr/sky130/cpu/runs -> /nobackup/sky130_cpu_runs ; pnr/sky130/soc/runs -> /nobackup/sky130_soc_runs (gitignored)
