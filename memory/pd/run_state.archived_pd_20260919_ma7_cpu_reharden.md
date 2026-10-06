run_id:      pd_20260919_ma7_cpu_reharden
design_name: rv32i_cpu_top (ASAP7 CPU block, bead ma7 sv2v re-harden)
pdk:         asap7
tool:        LibreLane 2.4.13 (nix-shell), pinned OpenROAD 26Q2 / OpenSTA 2.6.0 (check-asap7-openroad shim)
start_time:  2026-09-19T14:58:50+07:00
last_stage:  routing (BLOCKED — see below, not resumed)

Task: bead claude_verilog_test-ma7 remedy — switch rv32i_cpu_top's ASAP7 config from
USE_SYNLIG:true (proven-corrupt frontend, beads u99/ma7) to USE_SYNLIG:false + sv2v,
mirroring the already-applied valu_hls fix, then re-harden the macro.

Config changes (committed): pnr/asap7/cpu/config.json + config_3014.json ->
USE_SYNLIG:false, VERILOG_FILES -> sv2v-generated rv32i_cpu_top_sv2v.v. New Makefile
targets asap7-cpu-sv2v (wired into librelane-asap7) and asap7-gpu-sv2v (wired into
librelane-asap7-gpu, NOT run — GPU re-harden stays deferred, host-gated).

3 run attempts this session, terminal state BLOCKED (not resolved):
  1. RUN_2026-09-19_14-59-15 — Checker.LintErrors failure (sv2v stripped a
     verilator lint_off/on BLKLOOPINIT pragma the RTL relies on). FIXED: sed-inject
     the pragma back into the generated file inside the asap7-cpu-sv2v target.
  2. (no run dir) — OpenROAD.ResizerTimingPostCTS oscillated 1650+ Iter / 35+ min,
     known LibreLane 2.4.13 unbounded-repair_timing defect (bead bpp). FIXED: added
     PL_RESIZER_TIMING_MAX_PASSES=2 to both CPU configs (project's own validated hook).
  3. RUN_2026-09-19_15-42-11 (KEPT on disk for investigation, NOT pruned) — reached
     OpenROAD.DetailedRouting cleanly, then 108716 DRC violations (~53x this block's
     own best routed baseline of 2045), DRT-0255 on SRAM macro pins, RCX extracted
     ZERO parasitics, STAPostPNR hard-failed. ROOT CAUSE NOT PINNED DOWN — tracked as
     bead claude_verilog_test-lxv (P1). Ruled out: wrong OpenROAD binary, simple
     netlist-size growth (+9% only). Leading candidate (not yet tried): PL_MACRO_HALO
     2 2 -> 4 4 (matches GPU's value) to relieve SRAM-pin-access congestion.

No macro views were regenerated — pnr/asap7/soc/macro/rv32i_cpu_top.* remain the OLD
Synlig-built, proven-corrupt views. ma7 stays OPEN. Do not resume this run_id blindly:
the next session should read bead lxv's notes and decide on the PL_MACRO_HALO (or
other floorplan) experiment before relaunching `make librelane-asap7`.
