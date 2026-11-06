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
last_stage:  B5e COMPLETE 2026-10-29 20:41 (out/ ready; 1 DRC/1 short; not LEC/DRC/LVS checked)
run_id: pd_20261031_b7_drclvs_b5e_b5g
last_stage: B7 complete (ICC2 b5e, Innovus b5g)

# --- B6 task (ICC2 MCMM arm from the DC v2 netlist), physical-design-orchestrator subagent ---
run_id:      pd_20261106_b6_icc2_mcmm
design_name: rv32i_cpu_top (Sky130, ICC2 b6 arm, DC v2 MCMM netlist syn/dc/runs/b3c_dc_mcmm)
tool:        icc2_shell X-2025.06-SP1; chain scripts/b6_chain.sh (resumable: runs/b6_icc2/markers/*.done, runs/b6_icc2/reports/chain.log); verification signoff/chain_b6_all.sh (markers signoff/chain_b6/*.done)
start_time:  2026-11-06T23:15+08:00
last_stage:  b6 floorplan re-run on the 3-pane NDM sky130_hd_mcmm.ndm (built by pdk/sky130/scripts/build_ndm_mcmm.tcl, check_workspace -allow_missing: only 316 pulse-width checks differ)
resume:      cd pnr/commercial/impl/icc2; scripts/b6_chain.sh <first> <last>   (stages b6_01_floorplan b6_02_pdn b6_03_place b6_04_cts b6_05_route [antenna: ant_pins.py] b6_06_eco b6_07_finish)
