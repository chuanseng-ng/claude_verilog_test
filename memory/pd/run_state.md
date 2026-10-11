run_id:      pd_20261011_dud4_sky130_cpu_sv2v
design_name: rv32i_cpu_top (Sky130 CPU macro) then soc_top
pdk:         sky130A
tool:        LibreLane (nix), make -C pnr librelane-sky130-cpu / librelane-sky130-soc-rccal-noklayout
start_time:  2026-10-11
branch:      pd/sky130-cpu-sv2v-reharden-dud4 (worktree .claude/worktrees/agent-a30c85f22b16e994e)
bead:        dud4 (claimed; do not close; never git add .beads/)
last_stage:  S6 DONE: SoC RUN_2026-10-11_08-39-41 (rccal flow; CVT_SYNTH_GATE=warn passed via shell export only, nothing baked into Makefile/config). LVS 0, routing DRC 0, Magic 8984 (same), setup/hold 0 violators at all 9 corners (worst setup +2.48 max_ss, hold +0.287 min_ff), antenna 187/265, util 45.22 %, 84.6 mW. CVT.MaxCapViolations FAIL: 4 unwaived on 3 flat nets at ss corners; axi_rdata_i[12] waiver STALE (new pin cap 0.0469 pF). No waiver touched, gate not edited (owner decisions). S7 (docs, experience record, draft PR) IN PROGRESS.
S4 proof runner:   tools/verif/gls/sky130/run_netlist_proof.sh (validated on the committed nl.v.gz: 6/6, 124/124, negctl 4/6 detected, census 4868)
old_macro_backup: /nobackup/dud4_reharden/old_macro (+ old_macro.sha256); new sha table /nobackup/dud4_reharden/macro_sha_table.md
runs_symlinks: pnr/sky130/cpu/runs -> /nobackup/sky130_cpu_runs ; pnr/sky130/soc/runs -> /nobackup/sky130_soc_runs (gitignored)
