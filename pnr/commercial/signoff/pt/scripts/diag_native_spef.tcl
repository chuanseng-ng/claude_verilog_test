# diag_native_spef.tcl -- DIAGNOSTIC ONLY.  PrimeTime on ICC2's NATIVE SPEF (nominal TLU+, no coupling) instead of StarRC, same netlist/SDC/lib:
# separates the extractor effect from the engine/SDC effect when comparing the judge with ICC2's native numbers.  J_SPEF is given by the caller.
set ROOT $::env(J_ROOT)
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var search_path [list $ROOT/pnr/commercial/pdk/sky130/build/db]
set_app_var link_path [list * sky130_fd_sc_hd__tt_025C_1v80.db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST); current_design rv32i_cpu_top; link_design
read_sdc $::env(J_SDC); set_propagated_clock [all_clocks]
if {[info exists ::env(J_EXTRA_LATENCY)]} { set_clock_latency $::env(J_EXTRA_LATENCY) [get_clocks clk_i]; puts "EXTRA network latency $::env(J_EXTRA_LATENCY)" }
read_parasitics -format spef $::env(J_SPEF)
update_timing
puts "SPEF $::env(J_SPEF)"
report_global_timing
report_constraint -all_violators -max_transition -max_capacitance -nosplit
report_annotated_parasitics -check -internal_nets -boundary_nets -driverless_nets -loadless_nets -pin_to_pin_nets -max_nets 5
exit
