# gds_abs_drc.tcl -- Magic DRC (drc style drc(full), same report format as librelane/scripts/magic/drc.tcl) on a layout GDS.
# Std cells are the PDK LEF abstracts (exactly what LibreLane's DEF-mode Magic.DRC uses); routing, vias, PG come from the GDS.
# SRAM_MODE=real (default): the SRAM top structure is the GDS one => its OpenRAM internals are DRC'd flat (the 27.7 M-violation flood
#   the OpenROAD arm shows, bead 45a; ~9-10 GB peak). SRAM_MODE=abstract: SRAM = its LEF abstract (no flood, ~3 GB): only
#   routing-vs-macro-boundary rules remain.
source $::env(SCRIPTS_DIR)/magic/common/read.tcl
read_tech_lef
read_pdk_lef
if {[info exists ::env(SRAM_MODE)] && $::env(SRAM_MODE) eq "abstract"} { read_extra_lef }
gds noduplicates true
gds rescale true
puts "> gds read $::env(CURRENT_GDS)"
gds read $::env(CURRENT_GDS)
set report_dir $::env(STEP_DIR)/reports
file mkdir $report_dir
set drc_rpt_path $report_dir/drc_violations.magic.rpt
set fout [open $drc_rpt_path w]
set oscale [cif scale out]
set cell_name $::env(DESIGN_NAME)
magic::suspendall
puts stdout "\[INFO\] Loading $cell_name\n"
flush stdout
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
        set bllx [expr {$oscale * [lindex $coord 0]}]
        set blly [expr {$oscale * [lindex $coord 1]}]
        set burx [expr {$oscale * [lindex $coord 2]}]
        set bury [expr {$oscale * [lindex $coord 3]}]
        puts $fout [format " %.3fum %.3fum %.3fum %.3fum" $bllx $blly $burx $bury]
        incr count
    }
    puts $fout "----------------------------------------"
}
puts $fout "\[INFO\] COUNT: $count"
puts $fout "\[INFO\] Should be divided by 3 or 4"
puts $fout ""
close $fout
puts stdout "\[INFO\] COUNT: $count"
puts stdout "\[INFO\] DRC Checking DONE ($drc_rpt_path)"
flush stdout
