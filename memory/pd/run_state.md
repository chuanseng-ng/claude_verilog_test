run_id:      pd_20261016_j41m4_sky130_cpu_scan_boundary
design_name: rv32i_cpu_top (Sky130 CPU macro) then soc_top
pdk:         sky130A
tool:        LibreLane (nix), make -C pnr librelane-sky130-cpu / librelane-sky130-soc-rccal-noklayout
start_time:  2026-10-16
branch:      feat/dft-cpu-macro-scan-j41m4 (draft PR #287, worktree .claude/worktrees/agent-add69c1269db2b169)
beads:       j41m.4 (CPU macro scan boundary, PD step) + j41m.5 (cpu_clk_i SDC), batched in one PD cycle; never git add .beads/, do not modify beads
last_stage:  S0 CPU SDC edited (scan ports false-pathed), committed 4fe1656; CPU macro re-harden about to launch
baselines:   CPU macro RUN_2026-10-11_06-00-12 (/nobackup/sky130_cpu_runs, PR #269 dud4); SoC RUN_2026-10-11_08-39-41 and RUN_2026-10-09_06-18-39 (/nobackup/sky130_soc_runs)
old_macro_backup: /nobackup/j41m4_reharden/old_macro (copy of committed pnr/sky130/cpu/macro before any replacement)
runs_symlinks: pnr/sky130/cpu/runs -> /nobackup/sky130_cpu_runs ; pnr/sky130/soc/runs -> /nobackup/sky130_soc_runs (gitignored)
