read_lef tech.lef
read_lef cells.lef
read_liberty tt.lib
read_verilog timer_syn.v
link_design timer
create_clock -name clk -period 25 [get_ports clk]
puts "=== instances before: [llength [get_cells *]]"
puts "=== config"
set_dft_config -max_chains 1 -clock_mixing no_mix
puts "=== scan_replace"
scan_replace
puts "=== preview"
preview_dft -verbose
puts "=== insert"
insert_dft
write_verilog timer_scan.v
puts "=== done"
