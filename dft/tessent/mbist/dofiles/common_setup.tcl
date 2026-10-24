set_context dft -rtl -design_id rtl1
set_tsdb_output_directory ./tsdb_outdir
set_multiprocessing_options -processors 2
set_design_sources -format tcd_memory -y [file join $::env(MBIST_HERE) lib] -extension tcd_memory
read_verilog $::env(MBIST_BUILD)/mbist_eval_top_sv2v.v
set_current_design mbist_eval_top
set_design_level physical_block
set_dft_specification_requirements -memory_test on
add_clocks clk -period 25ns
