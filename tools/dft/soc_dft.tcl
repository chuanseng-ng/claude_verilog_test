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
puts "TOTAL cells: [llength [get_cells *]]"
set mode $::env(MODE)
set_dft_config -max_chains $::env(NCH) -clock_mixing $mode
set t0 [clock seconds]
catch {scan_replace} e; puts "scan_replace: $e   ([expr [clock seconds]-$t0] s)"
catch {preview_dft} e; puts $e
catch {insert_dft} e; puts "insert_dft: $e   ([expr [clock seconds]-$t0] s)"
write_verilog soc_scan_$mode.v
