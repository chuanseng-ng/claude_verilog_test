set_context dft -rtl -design_id rtl1
set_tsdb_output_directory ./tsdb_outdir
set_multiprocessing_options -processors 2
set_design_sources -format tcd_memory -y [file join $::env(MBIST_HERE) lib] -extension tcd_memory
read_verilog $::env(MBIST_HERE)/lib/sky130_sram_4kbyte_1rw1r_32x1024_8.v_interface -interface_only -exclude_from_file_dictionary
read_verilog $::env(MBIST_BUILD)/mbist_eval_top_sv2v.v
set_current_design mbist_eval_top
set_design_level physical_block
if {[info exists ::env(MBIST_VARIANT)] && $::env(MBIST_VARIANT) eq "tap"} {
    set_dft_specification_requirements -memory_test on -host_scan_interface_type tap
} else {
    set_dft_specification_requirements -memory_test on
}
add_clocks clk -period 25ns
