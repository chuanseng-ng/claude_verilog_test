# 07_write_verilog.tcl -- Step B5a: the three netlist variants from the final block (06_finish).  Supersedes the verilog files 06_finish wrote.
#   nl.v        no PG (ports/connections), no physical-only cells (taps/endcaps/fillers); keeps the 115 port-protection diodes -> LEC / PrimeTime
#   pg.nl.v     PG netlist (VPWR/VGND, SRAM vccd1/vssd1), no physical-only cells
#   full.pnl.v  everything incl. taps, endcaps, fillers and PG -> LVS
source [file join [file dirname [info script]] common.tcl]
view_stage 06_finish
set O $RUN/out
foreach {name args} [list \
  rv32i_cpu_top.nl.v      {-exclude {pg_netlist physical_only_cells}} \
  rv32i_cpu_top.pg.nl.v   {-exclude {physical_only_cells}} \
  rv32i_cpu_top.full.pnl.v {-include {all}} ] {
  set rc [catch {write_verilog {*}$args $O/$name} e]; puts "WRITE_VERILOG $name rc=$rc $e"
}
exit
