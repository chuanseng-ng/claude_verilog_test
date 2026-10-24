// Tessent MemoryBIST insertion into the Sky130 SoC RTL (sv2v output, SRAM_SKY130 arm).
// Run from dft/tessent/mbist/build/run via the Makefile target mbist-insert.
set_context dft -rtl -design_id rtl1
set_tsdb_output_directory ./tsdb_outdir

// memory description (TCD)
set_design_sources -format tcd_memory -y ../../lib -extension tcd_memory

// design: the same sv2v output the Sky130 SoC flow synthesises (pnr/Makefile sky130-soc-sv2v)
read_verilog ../soc_top_sv2v.v

set_current_design soc_top
set_design_level physical_block

set_dft_specification_requirements -memory_test on

add_clocks clk_i -period 25ns

check_design_rules
report_memory_instances

set spec [create_dft_specification]
report_config_data $spec
exit
