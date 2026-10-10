read_lef tech.lef
read_lef cells.lef
read_liberty tt.lib
read_verilog toy.v
link_design toy
create_clock -name clka -period 25 [get_ports clka]
create_clock -name clkb -period 25 [get_ports clkb]
set_dft_config -max_chains 1 -clock_mixing clock_mix -max_length 3
catch {scan_replace} e; puts "scan_replace: $e"
catch {report_dft_plan -verbose} e; puts $e
catch {execute_dft_plan} e; puts "execute: $e"
write_verilog toy_scan_26q2.v
