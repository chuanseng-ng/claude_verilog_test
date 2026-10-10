# Does OpenROAD dft honour set_dont_touch for excluding flops? (env MODE, NCH, EXCL=file of instance names)
set W /nobackup/claude_sim_build/dft_stage0/wt/pnr/sky130
read_lef tech.lef
read_lef cells.lef
read_lef $W/cpu/macro/rv32i_cpu_top.lef
read_lef $W/soc/macro/sky130_sram_4kbyte_1rw1r_32x1024_8.lef
read_liberty tt.lib
read_liberty $W/cpu/macro/rv32i_cpu_top__nom_tt_025C_1v80.lib
read_liberty $W/soc/macro/sky130_sram_4kbyte_1rw1r_32x1024_8_TT_1p8V_25C.lib
read_verilog /nobackup/sky130_soc_runs/RUN_2026-10-06_22-43-34/04-yosys-synthesis/soc_top.nl.v
link_design soc_top
create_clock -name core_clk -period 25 [get_ports clk_i]
create_clock -name cpu_clk -period 12.5 [get_ports cpu_clk_i]
set fh [open $::env(EXCL) r]
set names [split [string trim [read $fh]] "\n"]
close $fh
set n 0
foreach nm $names { set_dont_touch [get_cells $nm]; incr n }
puts "dont_touch applied to $n instances"
set_dft_config -max_chains $::env(NCH) -clock_mixing $::env(MODE)
scan_replace
preview_dft
insert_dft
write_verilog soc_scan_excl.v
