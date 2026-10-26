# diag_sram_path.tcl -- DIAGNOSTIC ONLY.  Re-time OpenSTA's native worst nom_ff setup path (SRAM[2].dout0[18] -> _52883_/D, falling-edge
# launch) in PrimeTime on the SAME OpenRCX SPEF, to see where the 0.5-0.75 ns ff-corner setup-slack delta vs OpenSTA comes from.
set ROOT $::env(J_ROOT)
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var search_path [list $ROOT/pnr/commercial/pdk/sky130/build/db]
set_app_var link_path [list * $LIBN($::env(J_LIB)).db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST); current_design rv32i_cpu_top; link_design
read_sdc $::env(J_SDC); set_propagated_clock [all_clocks]
read_parasitics -format spef $::env(J_SPEF)
update_timing
report_timing -delay_type max -from [get_pins {u_core.u_icache.gen_data_sram[2].u_data_sram/clk0}] -to [get_pins _52883_/D] -path_type full_clock_expanded -input_pins -transition_time -capacitance -nets
report_timing -delay_type max -from [get_pins {u_core.u_icache.gen_data_sram[2].u_data_sram/clk0}] -through [get_pins {u_core.u_icache.gen_data_sram[2].u_data_sram/dout0[18]}] -max_paths 1 -path_type end
exit
