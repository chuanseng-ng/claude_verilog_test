# b9_probe2.tcl -- view-only: geometry of the axi_rdata_i[15]/[16] nets on 06b_eco, free sites near their ports, driving-cell / max-cap data.  Never saves.
source [file join [file dirname [info script]] b8_common.tcl]
view_stage 06b_eco
source [file join $SCRIPTDIR reload.tcl]
foreach pn {axi_rdata_i[15] axi_rdata_i[16]} {
  set net [get_nets $pn]; array unset len; array set len {}
  foreach_in_collection s [get_shapes -quiet -of_objects $net] {
    set bb [get_attribute $s bbox]; set l [get_attribute $s layer_name]
    set dx [expr {[lindex $bb 1 0]-[lindex $bb 0 0]}]; set dy [expr {[lindex $bb 1 1]-[lindex $bb 0 1]}]
    set L [expr {$dx > $dy ? $dx : $dy}]
    if {![info exists len($l)]} { set len($l) 0 }
    set len($l) [expr {$len($l)+$L}]
    if {$L > 40} { puts "Q_LONG $pn $l $bb" }
  }
  foreach l [array names len] { puts "Q_LEN $pn $l [format %.1f $len($l)]" }
}
catch { report_port -verbose [get_ports {axi_rdata_i[15]}] } m
foreach sc [get_object_name [all_scenarios]] { catch { current_scenario $sc; report_constraints -max_capacitance -all_violators -nosplit } m }
foreach c {buf_2 buf_4 buf_6 buf_8 buf_12 buf_16} { catch { puts "Q_LIBCAP $c [get_attribute [get_lib_pins sky130_hd_mcmm/sky130_fd_sc_hd__$c/X] max_capacitance] tran=[get_attribute [get_lib_pins sky130_hd_mcmm/sky130_fd_sc_hd__$c/X] max_transition]" } m }
# free sites: row geometry near x 2315/2351
foreach_in_collection r [get_site_rows -quiet] { set bb [get_attribute $r bbox]; if {[lindex $bb 0 1] < 40} { puts "Q_ROW $bb" } }
foreach_in_collection c [get_cells -quiet -filter "is_hard_macro" ] { set bb [get_attribute $c bbox]; if {[lindex $bb 0 0] < 2600 && [lindex $bb 1 0] > 1900 && [lindex $bb 0 1] < 120} { puts "Q_MACRO [get_object_name $c] $bb" } }
catch { puts "Q_DIE [get_attribute [current_design] boundary_bbox]" } m
puts "Q_DONE"
exit
