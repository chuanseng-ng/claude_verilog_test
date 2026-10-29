run_id:      pd_20261025_commercial_pdk_sky130_b1p1
design_name: sky130 commercial PDK enablement (rv32i_cpu_top target)
pdk:         sky130A (sky130_fd_sc_hd + sky130_sram_1kbyte_1rw1r_32x256_8)
tool:        lc_shell, grdgenxo, Techgen (authoring only)
start_time:  2026-10-25T21:12:09+08:00
last_stage:  starrc extraction (OpenROAD+ICC2 done, Innovus PENDING b5c)

# --- B5e task (ICC2 corrective rerun), added by physical-design-orchestrator subagent ---
run_id:      pd_20261028_b5e_icc2
design_name: rv32i_cpu_top (Sky130, ICC2 arm)
pdk:         sky130A
tool:        icc2_shell X-2025.06-SP1 (2 threads, safe_run.sh)
start_time:  2026-10-28T19:45:00+08:00
run_dir:     pnr/commercial/impl/icc2/runs/b5e_icc2  (chain: scripts/run_chain.sh; markers: reports/stage_markers.txt; dlib backup rv32i.dlib.bak)
last_stage:  05y_repair done (1 DRC/1 short); 05z_fix+06_finish+07 queued via scripts/finish_chain.sh behind load gate
