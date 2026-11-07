# measure_clk_latency.tcl -- clock insertion latency of one (arm, RC corner, lib corner), measured in PrimeTime on the judge's own inputs.
# Same loading and settings as judge.tcl (base SDC md5 3c69..., clk_i propagated, no derate/OCV, SI off, StarRC SPEF), no timing report beyond that.
# Driven by environment: J_ROOT J_NETLIST J_SPEF J_RC J_LIB J_SDC (base SDC) M_ARM, cwd = output dir.
# Writes  clk_latency.tsv   key<TAB>value   (statistics of the arrival of the clk_i rising/falling edge at every register clock pin)
#         clk_pins.tsv      pin<TAB>group<TAB>ref<TAB>rise_early<TAB>rise_late<TAB>fall_early<TAB>fall_late   (arrival INCLUDING the 1.0 ns source latency)
# 'arrival' = pin attribute {min,max}_{rise,fall}_arrival = what a path report prints as the capture clock arrival (source latency + network).
# network latency = arrival - source latency (1.0 ns in the shared SDC).
set ROOT $::env(J_ROOT)
set DB   $ROOT/pnr/commercial/pdk/sky130/build/db
array set LIBN {tt sky130_fd_sc_hd__tt_025C_1v80 ss sky130_fd_sc_hd__ss_100C_1v60 ff sky130_fd_sc_hd__ff_n40C_1v95}
set SRAMDB sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db
set lib $::env(J_LIB); set rc $::env(J_RC)
set fh [open clk_latency.tsv w]
proc m {k v} { global fh; puts $fh "$k\t$v"; flush $fh }
m pt_version [get_app_var sh_product_version]
m arm $::env(M_ARM)
m lib_corner $LIBN($lib)
m rc_corner $rc
m netlist $::env(J_NETLIST)
m spef $::env(J_SPEF)
set_host_options -max_cores 2
set_app_var report_default_significant_digits 4
set_app_var si_enable_analysis false
set_app_var search_path [list $DB]
set_app_var link_path [list * $LIBN($lib).db $SRAMDB]
read_verilog $::env(J_NETLIST)
current_design rv32i_cpu_top
link_design
set md5 [lindex [exec md5sum $::env(J_SDC)] 0]
m sdc_md5 $md5
if {$md5 ne "3c69635042a9d65cb87e71a9db713e4e"} { puts "FATAL: SDC md5 $md5"; m FATAL sdc_md5; close $fh; exit 3 }
read_sdc $::env(J_SDC)
set_propagated_clock [get_clocks clk_i]
read_parasitics -format spef $::env(J_SPEF)
update_timing
redirect -file annot.txt { report_annotated_parasitics -check -internal_nets -boundary_nets -driverless_nets -loadless_nets -pin_to_pin_nets -max_nets 30 }
set clkpins [all_fanout -flat -clock_tree]
set clknets [get_nets -quiet -of_objects $clkpins]
m clock_nets [sizeof_collection $clknets]
redirect -file annot_clock.txt { report_annotated_parasitics -check -internal_nets -boundary_nets -driverless_nets -loadless_nets -pin_to_pin_nets -list_not_annotated -max_nets 30 $clknets }

m source_latency_sdc 1.0
set pf [open clk_pins.tsv w]
foreach g {flop sram other in_capture out_launch} { foreach k {re rl fe fl} { set v($g,$k) {} } }
foreach_in_collection pin [all_registers -clock_pins] {
  set pn [get_object_name $pin]
  set c [get_cells -of_objects $pin]
  set ref [get_attribute $c ref_name]
  if {[regexp {__(s?df|edf|sedf|dl[xr])} $ref]} { set g flop } elseif {[regexp {sram} $ref]} { set g sram } else { set g other }
  set re [get_attribute $pin min_rise_arrival]; set rl [get_attribute $pin max_rise_arrival]
  set fe [get_attribute $pin min_fall_arrival]; set fl [get_attribute $pin max_fall_arrival]
  puts $pf "$pn\t$g\t$ref\t$re\t$rl\t$fe\t$fl"
  set CELLRL([get_object_name $c]) [list $re $rl]
  foreach {k x} [list re $re rl $rl fe $fe fl $fl] { if {$x ne "" && $x ne "NA"} { lappend v($g,$k) $x } }
}
close $pf
# registers that actually face the macro boundary: capture flops of input-port paths and launch flops of output-port paths
# (rst_n_i and the irq inputs are false-pathed in the SDC and are left out)
set inp [remove_from_collection [all_inputs] [get_ports {clk_i rst_n_i ext_irq_i timer_irq_i}]]
set epins [filter_collection [all_fanout -flat -endpoints_only -from $inp] "object_class==pin"]
set incells {}
foreach_in_collection pp $epins { set cn [get_object_name [get_cells -of_objects $pp]]; if {[info exists CELLRL($cn)]} { lappend incells $cn } }
set incells [lsort -unique $incells]
set spins [filter_collection [all_fanin -flat -startpoints_only -to [all_outputs]] "object_class==pin"]
set outcells {}
foreach_in_collection pp $spins { set cn [get_object_name [get_cells -of_objects $pp]]; if {[info exists CELLRL($cn)]} { lappend outcells $cn } }
set outcells [lsort -unique $outcells]
foreach {nm cl} [list in_capture $incells out_launch $outcells] {
  set re_l {}; set rl_l {}
  foreach cn $cl { lassign $CELLRL($cn) a b; if {$a ne "" && $a ne "NA"} { lappend re_l $a }; if {$b ne "" && $b ne "NA"} { lappend rl_l $b } }
  set v($nm,re) $re_l; set v($nm,rl) $rl_l
}
proc stats {name lst} {
  set n [llength $lst]
  m ${name}_n $n
  if {$n == 0} return
  set s [lsort -real $lst]
  set sum 0.0; foreach x $s { set sum [expr {$sum + $x}] }
  m ${name}_min    [lindex $s 0]
  m ${name}_p05    [lindex $s [expr {int(0.05*($n-1))}]]
  m ${name}_median [lindex $s [expr {int(0.50*($n-1))}]]
  m ${name}_mean   [expr {$sum/$n}]
  m ${name}_p95    [lindex $s [expr {int(0.95*($n-1))}]]
  m ${name}_max    [lindex $s end]
}
foreach g {flop sram other} {
  foreach {k nm} {re rise_early rl rise_late fe fall_early fl fall_late} { stats ${g}_${nm} $v($g,$k) }
}
foreach g {in_capture out_launch} { foreach {k nm} {re rise_early rl rise_late} { stats ${g}_${nm} $v($g,$k) } }
# all register clock pins together (flops + SRAM + other)
foreach {k nm} {re rise_early rl rise_late fe fall_early fl fall_late} { stats all_${nm} [concat $v(flop,$k) $v(sram,$k) $v(other,$k)] }
close $fh
exit
