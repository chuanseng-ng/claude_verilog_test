# magic_drc_variant.tcl -- same report format as scripts/magic/gds_abs_drc.tcl, but the std-cell source is selectable:
#   ::env(STD) = lef : PDK LEF abstracts + 'gds noduplicates true'   (production mode of the sign-off flow)
#   ::env(STD) = gds : std cells exactly as stored in the layout GDS (full geometry, no LEF abstracts)
source $::env(SCRIPTS_DIR)/magic/common/read.tcl
read_tech_lef
if {$::env(STD) eq "lef"} { read_pdk_lef; gds noduplicates true }
gds rescale true
puts "> gds read $::env(CURRENT_GDS)"
gds read $::env(CURRENT_GDS)
set report_dir $::env(STEP_DIR)/reports
file mkdir $report_dir
set fout [open $report_dir/drc_violations.magic.rpt w]
set oscale [cif scale out]
set cell_name $::env(DESIGN_NAME)
magic::suspendall
load $cell_name
select top cell
drc euclidean on
drc style drc(full)
drc check
set drcresult [drc listall why]
set count 0
puts $fout "$cell_name"
puts $fout "----------------------------------------"
foreach {errtype coordlist} $drcresult {
    puts $fout $errtype
    puts $fout "----------------------------------------"
    foreach coord $coordlist {
        puts $fout [format " %.3fum %.3fum %.3fum %.3fum" [expr {$oscale*[lindex $coord 0]}] [expr {$oscale*[lindex $coord 1]}] [expr {$oscale*[lindex $coord 2]}] [expr {$oscale*[lindex $coord 3]}]]
        incr count
    }
    puts $fout "----------------------------------------"
}
puts $fout "\[INFO\] COUNT: $count"
close $fout
puts "\[INFO\] COUNT: $count"
