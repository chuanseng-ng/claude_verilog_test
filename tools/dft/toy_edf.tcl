read_lef tech.lef
read_lef cells.lef
read_liberty tt.lib
read_verilog toy.v
link_design toy
create_clock -name clka -period 25 [get_ports clka]
create_clock -name clkb -period 25 [get_ports clkb]
foreach mode {clock_mix} {
  puts "######## clock_mixing=$mode"
  set_dft_config -max_chains 1 -clock_mixing $mode
  catch {scan_replace} e; puts "scan_replace: $e"
  catch {preview_dft -verbose} e; puts $e
}
catch {insert_dft} e; puts "insert_dft: $e"
write_verilog toy_scan_edf.v
