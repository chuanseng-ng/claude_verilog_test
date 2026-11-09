# b8_05b_write.tcl -- view-only: write the 05_route label (netlist without PG, SDC of func_tt, DEF) for the pre-ECO extraction + judge (hold / dout0 / antenna ECO lists).  Never saves the library.
source [file join [file dirname [info script]] b8_common.tcl]
view_stage 05_route
file mkdir $RUN/out/pre
set rc [catch {write_verilog -exclude {pg_netlist physical_only_cells supply_statements} $RUN/out/pre/rv32i_cpu_top.nl.v} e]; puts "WRITE_VERILOG pre rc=$rc $e"
set rc [catch {write_def $RUN/out/pre/rv32i_cpu_top.def} e]; puts "WRITE_DEF pre rc=$rc $e"
puts "WRITE_PRE_DONE"
exit
