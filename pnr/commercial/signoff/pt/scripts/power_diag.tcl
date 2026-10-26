# power_diag.tcl -- DIAGNOSTIC ONLY (not part of the judge tables): why PrimePower differs from OpenSTA's native power.
# Variant A = judge defaults.  B = also toggle 0.1 / prob 0.5 asserted on every register output (OpenSTA seeds sequential outputs
# differently; hypothesis).  C = B plus black-box/macro output pins.  Same netlist/SPEF snapshot as the nom_tt judge run.
set ROOT $::env(J_ROOT)
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80}
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var si_enable_analysis false
set_app_var power_enable_analysis true
set_app_var power_analysis_mode averaged
set_app_var search_path [list $ROOT/pnr/commercial/pdk/sky130/build/db]
set_app_var link_path [list * sky130_fd_sc_hd__tt_025C_1v80.db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST); current_design rv32i_cpu_top; link_design
read_sdc $::env(J_SDC); set_propagated_clock [all_clocks]
read_parasitics -format spef $::env(J_SPEF)
set_app_var power_default_toggle_rate 0.1
set_app_var power_default_static_probability 0.5
update_power
puts "=== VARIANT A (judge defaults)"; report_power -nosplit
set rq [all_registers -output_pins]
puts "register output pins: [sizeof_collection $rq]"
set_switching_activity -toggle_rate 0.1 -static_probability 0.5 -base_clock clk_i $rq
update_power
puts "=== VARIANT B (reg outputs 0.1/0.5)"; report_power -nosplit
exit
