// Stage 3: simulate the Tessent-generated MBIST testbench on VCS against the project's behavioural SRAM model.
// Fault-free run; the fault-injection run is mbist_sim_fi.do.
set_context patterns -ijtag
set_tsdb_output_directory ./tsdb_outdir
read_verilog $::env(MBIST_HERE)/lib/sky130_sram_4kbyte_1rw1r_32x1024_8.v_interface -interface_only -exclude_from_file_dictionary
read_design mbist_eval_top -design_id rtl1 -verbose
set_current_design mbist_eval_top
check_design_rules
create_patterns_specification
process_patterns_specification
set_simulation_library_sources -v $::env(MBIST_ROOT)/sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv
run_testbench_simulations -simulator vcs -compilation_options {-sverilog -full64} -simulation_timeout 3600s
check_testbench_simulations -report_status
exit
