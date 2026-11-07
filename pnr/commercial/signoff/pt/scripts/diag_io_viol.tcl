# diag_io_viol.tcl -- DIAGNOSTIC for the per-view iolat judge: list EVERY violating I/O endpoint (worst path per endpoint) and say how much of it is
# the intra-macro clock skew between the external clock (clk_io, one latency per view) and the macro register on the other end of the path.
# Same loading / SDC (pnr/commercial/constraints/sky130_cpu_iolat_pv.sdc + table via IOLAT_PV_TABLE/IOLAT_PV_KEY) / settings as judge.tcl.
# Env: J_ROOT J_NETLIST J_SPEF J_RC J_LIB J_SDC IOLAT_PV_TABLE IOLAT_PV_KEY; cwd = output dir.  Output io_viol.tsv:
#   kind  type  startpoint  endpoint  slack  reg_clk_arrival  io_clk_latency  slack_matched
# kind: in2reg | reg2out | in2out | r2r;  type: setup | hold;  reg_clk_arrival: clk_i arrival (incl. 1.0 source latency) at the macro register of the path;
# io_clk_latency: clk_io latency that path used (setup launch/capture and hold launch/capture as the SDC dictates);
# slack_matched: slack if clk_io had exactly the macro register's own arrival (= intra-tree skew removed).  matched >= 0  =>  the violation is skew-limited,
# matched < 0 => it survives with the external clock aligned to the register, i.e. the port-to-register path itself is short/long.
set ROOT $::env(J_ROOT)
set DB   $ROOT/pnr/commercial/pdk/sky130/build/db
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set lib $::env(J_LIB)
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var si_enable_analysis false
set_app_var search_path [list $DB]
set_app_var link_path [list * $LIBN($lib).db sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db]
read_verilog $::env(J_NETLIST)
current_design rv32i_cpu_top
link_design
read_sdc $::env(J_SDC)
set_propagated_clock [get_clocks clk_i]
read_parasitics -format spef $::env(J_SPEF)
update_timing
# the clk_io latency used by the SDC: re-read from the same table row (the SDC echoes it too)
set key $::env(IOLAT_PV_KEY)
set fh [open $::env(IOLAT_PV_TABLE) r]
foreach line [split [read $fh] "\n"] {
  if {[string match "#*" $line] || [string trim $line] eq ""} continue
  lassign [split $line "\t"] a r l e lt
  if {"${a}_${r}_${l}" eq $key} { set E [expr {1.0+$e}]; set L [expr {1.0+$lt}] }
}
close $fh
proc reg_arrival {obj} {
  # clk_i arrival at the clock pin of the register that owns pin/cell obj (max rise arrival; early==late: no derate)
  set c [get_cells -of_objects $obj]
  set best ""
  foreach_in_collection p [get_pins -of_objects $c -filter "is_clock_pin==true"] {
    set x [get_attribute $p max_rise_arrival]
    if {$x ne "" && ($best eq "" || $x > $best)} { set best $x }
  }
  return $best
}
set fo [open io_viol.tsv w]
puts $fo "kind\ttype\tstartpoint\tendpoint\tslack\treg_clk_arrival\tio_clk_latency\tslack_matched"
foreach {dt tp} {max setup min hold} {
  set vp [get_timing_paths -delay_type $dt -max_paths 1000000 -nworst 1 -slack_lesser_than 0]
  array unset worst; array unset wpath
  foreach_in_collection p $vp {
    set e [get_object_name [get_attribute $p endpoint]]
    set s [get_attribute $p slack]
    if {![info exists worst($e)] || $s < $worst($e)} { set worst($e) $s; set wpath($e) $p }
  }
  foreach e [array names worst] {
    set p $wpath($e)
    set sp [get_attribute $p startpoint]; set ep [get_attribute $p endpoint]
    set spc [get_attribute $sp object_class]; set epc [get_attribute $ep object_class]
    set sn [get_object_name $sp]; set en [get_object_name $ep]; set sl $worst($e)
    if {$spc eq "port" && $epc eq "pin"} {
      set kind in2reg; set ra [reg_arrival $ep]
      if {$tp eq "setup"} { set io $L; set m [expr {$sl + ($L - $ra)}] } else { set io $E; set m [expr {$sl + ($ra - $E)}] }
    } elseif {$spc eq "pin" && $epc eq "port"} {
      set kind reg2out; set ra [reg_arrival $sp]
      if {$tp eq "setup"} { set io $E; set m [expr {$sl + ($ra - $E)}] } else { set io $L; set m [expr {$sl + ($L - $ra)}] }
    } elseif {$spc eq "port" && $epc eq "port"} {
      set kind in2out; set ra NA; set io NA; set m NA
    } else {
      set kind r2r; set ra NA; set io NA; set m NA
    }
    puts $fo "$kind\t$tp\t$sn\t$en\t$sl\t$ra\t$io\t$m"
  }
}
close $fo
exit
