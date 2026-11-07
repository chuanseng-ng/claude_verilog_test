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
set_app_var target_library [list sky130_fd_sc_hd__tt_025C_1v80.db]
set_app_var link_library   [list * sky130_fd_sc_hd__tt_025C_1v80.db ${SRAM}_TT_1p8V_25C.db]
if {[file exists $RUN/WORK.dlib]} { file delete -force $RUN/WORK.dlib }
create_lib -technology $B/ndm/sky130_hd.tf \
  -ref_libs [list $B/ndm/sky130_hd_tt.ndm $B/ndm/sky130_hd_phys.ndm $B/ndm/${SRAM}.ndm] $RUN/WORK.dlib
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

# ---------------- parasitics (TLU+ from StarRC grdgenxo, nominal only; see report) ----------------
set TLUP $B/nxtgrd/nom/sky130A_nom.tluplus
set LMAP $B/tech/map/starrc_layer.map
if {[info exists ::env(NO_TLUP)]} {
  puts "TLUP: skipped (NO_TLUP set) -> tech-LEF RC"
} else {
  # nominal TLU+ for both min and max (min/max grdgenxo outputs were never built); dcnxt has no read_parasitic_tech.
  set_tlu_plus_files -max_tluplus $TLUP -min_tluplus $TLUP -tech2itf_map $LMAP
  puts "TLUP: set_tlu_plus_files $TLUP"
  redirect $RUN/reports/check_tlu_plus.rpt { check_tlu_plus_files }
  check_tlu_plus_files
}

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

# ---------------- constraints: sky130_cpu.sdc UNCHANGED (md5 recorded by the Makefile) ----------------
# The SDC already sets set_max_transition 0.5 / set_max_fanout 16 / set_max_capacitance 0.1 on outputs, so the
# OpenROAD arm's MAX_FANOUT_CONSTRAINT 8 and MAX_TRANSITION_CONSTRAINT 0.5 are NOT re-applied (instruction: only if the SDC is silent).
# Routing layers: OpenROAD arm routes met1..met4 (RT_MAX_LAYER met4); li1 is cell-internal. SPG estimates wires on the same layers.
set_ignored_layers -min_routing_layer met1 -max_routing_layer met4
read_sdc -echo $SDC
redirect $RUN/reports/check_timing_precompile.rpt { check_timing }
redirect $RUN/reports/pre_compile_constraints.rpt { report_clock -skew; report_port -verbose }
write -format ddc -hierarchy -output $RUN/out/${TOP}_precompile.ddc
if {$STOP eq "compile_setup"} { puts "STOP=compile_setup"; exit }

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
write_sdc -nosplit $RUN/out/${TOP}.sdc
catch {write_floorplan -all $RUN/out/${TOP}_fp}

# ---------------- reports ----------------
set R $RUN/reports
redirect $R/qor.rpt          { report_qor }
redirect $R/area_hier.rpt    { report_area -hierarchy -nosplit }
redirect $R/area.rpt         { report_area -nosplit }
redirect $R/timing_max10.rpt { report_timing -max_paths 10 -nworst 1 -nosplit -transition_time -nets -input_pins -capacitance }
redirect $R/timing_summary.rpt { report_timing -max_paths 1 -nosplit }
redirect $R/timing_min.rpt   { report_timing -delay_type min -max_paths 5 -nosplit }
redirect $R/constraints.rpt  { report_constraint -all_violators -nosplit }
redirect $R/power.rpt        { report_power -hierarchy -levels 1 }
redirect $R/reference.rpt    { report_reference -nosplit }
redirect $R/cell.rpt         { report_cell -nosplit }
redirect $R/check_design.rpt { check_design }
redirect $R/check_timing.rpt { check_timing }
redirect $R/clock.rpt        { report_clock -skew }
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
