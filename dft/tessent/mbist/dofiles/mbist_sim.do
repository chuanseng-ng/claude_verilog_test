// Stage 3: simulate Tessent-generated MBIST patterns on VCS.
//   MBIST_MODEL=real (default)  the project's behavioural model sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv, fault-free
//   MBIST_MODEL=fi              tb/sky130_sram_fi_tess.sv (fault-injecting; faults set by plusargs when running simv)
// One pattern per algorithm, FULL address count (reduced_address_count off), per-memory go compare on.
set_context dft -rtl -design_id rtl1
set_tsdb_output_directory ./tsdb_outdir
set_design_sources -format tcd_memory -y $::env(MBIST_HERE)/lib -extension tcd_memory
read_verilog $::env(MBIST_HERE)/lib/sky130_sram_4kbyte_1rw1r_32x1024_8.v_interface -interface_only -exclude_from_file_dictionary
read_design mbist_eval_top -design_id rtl1 -verbose
set_current_design mbist_eval_top
set_design_level physical_block
check_design_rules

set ctl mbist_eval_top_rtl1_tessent_mbist_c1_controller_inst
set body "PatternsSpecification(mbist_eval_top,rtl1,full) {\n"
append body "  Patterns(ICLNetwork) { ICLNetworkVerify(mbist_eval_top) { } }\n"
foreach {pname algo} {
    P_CHKBCIL  SMARCHCHKBCIL
    P_MARCHCM  LVMARCHCMINUS
    P_SMARCH   SMARCH
    P_CHKB     SMARCHCHKB
    P_CHKBCI   SMARCHCHKBCI
    P_CKBD1X1  LVCHECKERBOARD1X1
} {
    append body "  Patterns($pname) {\n    ClockPeriods { clk : 25.0ns; }\n    TestStep(go_nogo) {\n      MemoryBist {\n"
    append body "        run_mode : run_time_prog;\n        Controller($ctl) {\n          AdvancedOptions { apply_algorithm : $algo; }\n"
    append body "          DiagnosisOptions { compare_go : on; compare_memory_go : on; }\n        }\n      }\n    }\n  }\n"
}
// retention: write, pause (programmable, here 200 us), read.  hw_default run mode = controller default algorithm.
append body "  Patterns(P_RETENTION) {\n    ClockPeriods { clk : 25.0ns; }\n    TestStep(ret) {\n      MemoryBist {\n"
append body "        run_mode : hw_default;\n        parallel_retention_time : 200us;\n        Controller($ctl) {\n          parallel_retention_group : 1;\n"
append body "          DiagnosisOptions { compare_go : on; compare_memory_go : on; }\n        }\n      }\n    }\n  }\n"
append body "}\n"
read_config_data -from_string $body
process_patterns_specification -pattern_id full

if {$::env(MBIST_MODEL) eq "fi"} {
    set_simulation_library_sources -v $::env(MBIST_ROOT)/tb/cocotb/soc/sram_fi_core.sv -v $::env(MBIST_HERE)/tb/sky130_sram_fi_tess.sv
    set simid fi
} else {
    set_simulation_library_sources -v $::env(MBIST_ROOT)/sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv
    set simid real
}
run_testbench_simulations -pattern_id full -simulator vcs -compilation_options {-sverilog -full64} \
    -simulation_timeout 3600s -simulation_id $simid -keep_simulation_data on -parallel_simulations 2
check_testbench_simulations -pattern_id full -report_status
exit
