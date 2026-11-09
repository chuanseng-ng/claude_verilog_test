# diag_dout_paths.tcl -- DIAGNOSTIC: worst setup slack of the paths THROUGH each SRAM dout0 pin listed in env DOUT_PINS (one pt-name per line), and the
# SRAM load seen by the pin (net total cap, pin cap) -- one corner, base SDC.  Used for the b6 -> b7 read-path timing cost.
set ROOT $::env(J_ROOT)
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set_host_options -max_cores 2
set_app_var report_default_significant_digits 5
set_app_var search_path [list $ROOT/pnr/commercial/pdk/sky130/build/db]
set_app_var link_path [list * $LIBN($::env(J_LIB)).db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST); current_design rv32i_cpu_top; link_design
read_sdc $::env(J_SDC); set_propagated_clock [get_clocks clk_i]
read_parasitics -format spef $::env(J_SPEF)
update_timing
set fh [open $::env(DOUT_PINS) r]
while {[gets $fh l] >= 0} {
  set l [string trim $l]; if {$l eq ""} continue
  set pn [lindex $l 0]
  set p [get_pins -quiet $pn]
  if {[sizeof_collection $p] == 0} { puts "DOUTPATH $pn NOPIN"; continue }
  set sl NA; set ep NA
  catch { set pp [get_timing_paths -delay_type max -through $p -max_paths 1]; set sl [get_attribute $pp slack]; set ep [get_object_name [get_attribute $pp endpoint]] }
  set cap NA
  catch { set cap [get_attribute [get_nets -of_objects $p] total_capacitance_max] }
  puts "DOUTPATH $pn slack=$sl endpoint=$ep netcap_max=$cap"
}
close $fh
set allp [get_pins -hierarchical -quiet {*/dout0*}]
set pp [get_timing_paths -delay_type max -through $allp -max_paths 1]
puts "ALLDOUT0 n=[sizeof_collection $allp] worst_slack=[get_attribute $pp slack] start=[get_object_name [get_attribute $pp startpoint]] end=[get_object_name [get_attribute $pp endpoint]]"
set h [get_timing_paths -delay_type max -from [all_registers -clock_pins] -to [all_registers -data_pins] -max_paths 1]
puts "R2RSETUP wns=[get_attribute $h slack]"
exit
