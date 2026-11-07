# b6_08_write_verilog.tcl -- full PG netlist for LVS (the b5m recipe: write_verilog -include {pg_netlist}; -include cannot be combined with -exclude).  Supply statements are checked afterwards by the chain.
source [file join [file dirname [info script]] b6_common.tcl]
view_stage 07_finish
set rc [catch {write_verilog -include {pg_netlist} $RUN/out/rv32i_cpu_top.full.pnl.v} e]; puts "WRITE_VERILOG rv32i_cpu_top.full.pnl.v rc=$rc $e"
exit
