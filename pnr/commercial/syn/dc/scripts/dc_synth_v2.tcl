# dc_synth_v2.tcl -- Step B3c (syn v2): DC-NXT topographical MCMM synthesis of the Sky130 CPU macro rv32i_cpu_top (75 MHz).
#   v2 = v1 (dc_synth.tcl) with 4 scenarios instead of tt only: setup ss+tt, hold ff+tt, TLU+ max/nom/min matching ss/tt/ff.
#   Everything else is identical to v1 (same RTL list/defines, SRAM .db hard macro + dont_touch, dont_use, floorplan, SPG, compile_ultra -spg default effort, SDC unchanged).
#   SRAM lib is TT-only at EVERY scenario (bead o1i).
# (v1 header follows)
# dc_synth.tcl -- Step B3a: Synopsys DC-NXT topographical synthesis of the Sky130 CPU macro rv32i_cpu_top (75 MHz).
#   COMPARISON RUN, NO PPA TARGET: constraints are exactly pnr/sky130/cpu/constraints/sky130_cpu.sdc; nothing is tuned to close.
#   dcnxt_shell -topographical_mode -f dc_synth.tcl      env: REPO PDKDIR RUN [STOP=elab|fp|compile|all]
# RTL is read natively (analyze -format sverilog), no sv2v.  File list + defines = `make -C pnr sky130-cpu-sv2v-inputs`
# (28 files, minus nothing: the SRAM stub .v is NOT in that list and must never be added; the SRAM links from the .db/NDM).
set REPO   $::env(REPO)
set PDKDIR $::env(PDKDIR)
set RUN    $::env(RUN)
set STOP   [expr {[info exists ::env(STOP)] ? $::env(STOP) : "all"}]
set B      $PDKDIR/build
set TOP    rv32i_cpu_top
set SRAM   sky130_sram_1kbyte_1rw1r_32x256_8
set SDC    $REPO/pnr/sky130/cpu/constraints/sky130_cpu.sdc
file mkdir $RUN/reports $RUN/out

set_host_options -max_cores 2
suppress_message {LBDB-272 LBDB-1054 LBDB-607 LBDB-396 LBDB-301 LBDB-172}
set_app_var sh_continue_on_error false

# ---------------- libraries: tt corner (OpenROAD/yosys synthesises against sky130_fd_sc_hd__tt_025C_1v80) ----------
set_app_var search_path   [list $B/db $B/ndm]
set LIBS [list sky130_fd_sc_hd__tt_025C_1v80 sky130_fd_sc_hd__ss_100C_1v60 sky130_fd_sc_hd__ff_n40C_1v95]
set LIBDB {}
foreach l $LIBS { lappend LIBDB ${l}.db }
set_app_var target_library $LIBDB
set_app_var link_library   [concat [list *] $LIBDB [list ${SRAM}_TT_1p8V_25C.db]]
if {[file exists $RUN/WORK.dlib]} { file delete -force $RUN/WORK.dlib }
create_lib -technology $B/ndm/sky130_hd.tf \
  -ref_libs [list $B/ndm/sky130_hd_tt.ndm $B/ndm/sky130_hd_ss.ndm $B/ndm/sky130_hd_ff.ndm $B/ndm/sky130_hd_phys.ndm $B/ndm/${SRAM}.ndm] $RUN/WORK.dlib
open_lib $RUN/WORK.dlib

# ---------------- SVF for Formality: MUST be set before reading the RTL ----------------
set_svf $RUN/out/${TOP}.svf

# ---------------- RTL (native SystemVerilog) ----------------
set defines {PDK_sky130A SCL_sky130_fd_sc_hd __librelane__ __pnr__ SRAM_SKY130}
set files {}
set fh [open $::env(RTL_LIST) r]
while {[gets $fh l] >= 0} { if {[string trim $l] ne ""} { lappend files [string trim $l] } }
close $fh
puts "RTL files: [llength $files]"
foreach f $files { if {![file exists $f]} { error "missing RTL file $f" }; if {[string match *stub* $f]} { error "SRAM stub must not be read: $f" } }
set rc [analyze -format sverilog -define $defines $files]
puts "ANALYZE_RESULT: $rc"
set rc [elaborate $TOP]
puts "ELABORATE_RESULT: $rc"
current_design $TOP
set lr [link]
puts "LINK_RESULT: $lr"
puts "SRAM cells: [sizeof_collection [get_cells -hier -filter "ref_name==$SRAM"]]"
foreach_in_collection c [get_cells -hier -filter "ref_name==$SRAM"] { puts "  sram: [get_object_name $c]" }
check_design -summary
redirect $RUN/reports/check_design_elab.rpt { check_design }
write -format ddc -hierarchy -output $RUN/out/${TOP}_elab.ddc
if {$STOP eq "elab"} { puts "STOP=elab"; exit }

# ---------------- dont_use / dont_touch ----------------
source $PDKDIR/scripts/dont_use.tcl
set_dont_touch [get_cells -hier -filter "ref_name==$SRAM"]

# ---------------- parasitics: per-scenario TLU+ (set inside each scenario below) ----------------
set LMAP $B/tech/map/starrc_layer.map
set TLUP_nom $B/nxtgrd/nom/sky130A_nom.tluplus
set TLUP_max $B/nxtgrd/max/sky130A_max.tluplus
set TLUP_min $B/nxtgrd/min/sky130A_min.tluplus

# ---------------- floorplan: die/core/pins from the OpenROAD arm, macros from macro_placement.cfg ----------------
exec python3 -I $::env(SCRIPTDIR)/mk_fp_def.py $REPO $RUN/out/fp.def
extract_physical_constraints $RUN/out/fp.def
set cfg [open $REPO/pnr/sky130/cpu/macro_placement.cfg r]
set nplaced 0
while {[gets $cfg l] >= 0} {
  regsub {#.*} $l {} l; set l [string trim $l]; if {$l eq ""} continue
  lassign $l nm x y o
  # yosys-style "u_core.u_icache.gen_data_sram[0].u_data_sram" -> DC "u_core/u_icache/gen_data_sram[0].u_data_sram"
  set parts [split $nm .]; set out {}; set i 0
  while {$i < [llength $parts]} {
    set p [lindex $parts $i]
    if {[string match {gen_data_sram\[*\]} $p]} { set p "$p.[lindex $parts [expr {$i+1}]]"; incr i }
    lappend out $p; incr i
  }
  set dcname [join $out /]
  set c [get_cells -quiet $dcname]
  if {[sizeof_collection $c] != 1} { error "macro $dcname not found ($nm)" }
  set_cell_location -coordinates [list $x $y] -orientation $o -fixed $c
  incr nplaced
}
close $cfg
puts "FLOORPLAN: placed $nplaced macros"
redirect $RUN/reports/floorplan.rpt {
  puts "design boundary_bbox: [catch {get_attribute [current_design] boundary_bounding_box} r1] $r1"
  puts "design core_bbox: [catch {get_attribute [current_design] core_bounding_box} r2] $r2"
  foreach_in_collection c [get_cells -hier -filter "ref_name==$SRAM"] {
    puts "[get_object_name $c] bbox=[get_attribute $c bbox] orient=[get_attribute $c orientation] status=[get_attribute $c physical_status]"
  }
  puts "pins fixed: [sizeof_collection [get_ports -filter {physical_status==fixed}]] of [sizeof_collection [get_ports]]"
}
puts [exec cat $RUN/reports/floorplan.rpt]
if {[info exists ::env(DIAG)]} { source $::env(DIAG) }
if {$STOP eq "fp"} { puts "STOP=fp"; exit }

# ---------------- constraints: sky130_cpu.sdc UNCHANGED (md5 recorded by the Makefile), read once per scenario ----------------
# MCMM mapping (same as pdk/sky130/scripts/mmmc.tcl): ss = ss_100C_1v60 lib + max RC; tt = tt_025C_1v80 + nom RC; ff = ff_n40C_1v95 + min RC.
# Setup scenarios: ss, tt.  Hold scenarios: ff, tt.   The SRAM macro .db is TT 1.8V 25C in every scenario (bead o1i).
set_ignored_layers -min_routing_layer met1 -max_routing_layer met4
array set SCN {
  setup_ss {sky130_fd_sc_hd__ss_100C_1v60 ss_100C_1v60 max true  false}
  setup_tt {sky130_fd_sc_hd__tt_025C_1v80 tt_025C_1v80 nom true  false}
  hold_ff  {sky130_fd_sc_hd__ff_n40C_1v95 ff_n40C_1v95 min false true}
  hold_tt  {sky130_fd_sc_hd__tt_025C_1v80 tt_025C_1v80 nom false true}
}
foreach sc {setup_ss setup_tt hold_ff hold_tt} {
  lassign $SCN($sc) lib opc rc su hu
  create_scenario $sc
  current_scenario $sc
  set_operating_conditions -library $lib $opc
  set_tlu_plus_files -max_tluplus [set TLUP_$rc] -min_tluplus [set TLUP_$rc] -tech2itf_map $LMAP
  redirect $RUN/reports/check_tlu_plus_$sc.rpt { check_tlu_plus_files }
  read_sdc -echo $SDC
  set_scenario_options -setup $su -hold $hu
  if {$hu eq "true"} { set_fix_hold [get_clocks clk_i] }   ;# hold scenarios: DC repairs hold only when asked
  puts "SCENARIO $sc: lib $lib opcond $opc tluplus $rc setup=$su hold=$hu"
}
puts "ALL_SCENARIOS: [all_scenarios]  ACTIVE: [all_active_scenarios]"
foreach sc [all_scenarios] {
  current_scenario $sc
  redirect $RUN/reports/check_timing_precompile_$sc.rpt { check_timing }
}
write -format ddc -hierarchy -output $RUN/out/${TOP}_precompile.ddc
if {$STOP eq "compile_setup"} {
  # quick MCMM sanity probe: per-scenario worst slack on the UNOPTIMISED elaborated design
  foreach sc [all_scenarios] { current_scenario $sc; redirect $RUN/reports/precompile_timing_$sc.rpt { report_timing -max_paths 1 -nosplit } }
  puts "STOP=compile_setup"; exit
}

# ---------------- compile ----------------
# compile_ultra -spg: physical-guidance (placement-aware) mapping on the floorplan above.  Default auto-ungroup is KEPT
# (Formality is guided by the SVF); -no_autoungroup is only needed if LEC naming turns out to need it.
set t0 [clock seconds]
set rc [compile_ultra -spg]
puts "COMPILE_RESULT: $rc  ([expr {[clock seconds]-$t0}] s)"
if {$rc eq "0" || $rc eq ""} { puts "COMPILE_FAILED"; exit 1 }

# ---------------- outputs ----------------
change_names -rules verilog -hierarchy
write -format ddc     -hierarchy -output $RUN/out/${TOP}.ddc
write -format verilog -hierarchy -output $RUN/out/${TOP}.nl.v
foreach sc [all_scenarios] { current_scenario $sc; write_sdc -nosplit $RUN/out/${TOP}.$sc.sdc }
catch {write_floorplan -all $RUN/out/${TOP}_fp}

# ---------------- reports ----------------
set R $RUN/reports
foreach sc [all_scenarios] {
  current_scenario $sc
  redirect $R/qor_$sc.rpt          { report_qor -nosplit }
  redirect $R/timing_max10_$sc.rpt { report_timing -delay_type max -max_paths 10 -nworst 1 -nosplit -transition_time -nets -input_pins -capacitance }
  redirect $R/timing_min5_$sc.rpt  { report_timing -delay_type min -max_paths 5 -nosplit }
  redirect $R/timing_summary_$sc.rpt { report_timing -delay_type [expr {[string match setup* $sc] ? "max" : "min"}] -max_paths 1 -nosplit }
  redirect $R/constraints_$sc.rpt  { report_constraint -all_violators -nosplit }
  redirect $R/check_timing_$sc.rpt { check_timing }
  redirect $R/clock_$sc.rpt        { report_clock -skew }
}
redirect $R/qor.rpt          { report_qor -nosplit -scenarios [all_scenarios] }
redirect $R/area_hier.rpt    { report_area -hierarchy -nosplit }
redirect $R/area.rpt         { report_area -nosplit }
redirect $R/reference.rpt    { report_reference -nosplit }
redirect $R/cell.rpt         { report_cell -nosplit }
redirect $R/check_design.rpt { check_design }
redirect $R/power.rpt        { report_power -hierarchy -levels 1 }
redirect $R/physical.rpt     { catch {report_placement_utilization}; catch {report_congestion} }
catch {report_qor -summary}
set seq [get_cells -hier -filter "is_sequential==true && is_hierarchical==false"]
set leaf [get_cells -hier -filter "is_hierarchical==false"]
puts "CELLCOUNT: leaf=[sizeof_collection $leaf] sequential=[sizeof_collection $seq]"
set fh [open $R/cellcount.txt w]
array set cnt {}
foreach_in_collection c $leaf { set r [get_attribute $c ref_name]; if {![info exists cnt($r)]} {set cnt($r) 0}; incr cnt($r) }
foreach r [lsort [array names cnt]] { puts $fh "$r $cnt($r)" }
close $fh
set fh [open $R/flops.txt w]
foreach_in_collection c $seq { puts $fh "[get_object_name $c] [get_attribute $c ref_name]" }
close $fh
puts "FWD_B flops: [sizeof_collection [get_cells -hier -filter {is_sequential==true && full_name=~*fwd_b*}]]"
puts "SRAM_dont_touch: [sizeof_collection [get_cells -hier -filter "ref_name==$SRAM && dont_touch==true"]]"
set_svf -off
write_file -format ddc -hierarchy -output $RUN/out/${TOP}_final.ddc
puts "DC_DONE"
exit
