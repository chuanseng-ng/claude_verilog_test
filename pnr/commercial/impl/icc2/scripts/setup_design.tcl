# setup_design.tcl -- constraints/parasitics/library setup shared by stages 03..07 (sourced after open_stage).  Single scenario at tt 1.80V 25C
# (OpenROAD placed/routed with the tt libs; multi-corner timing is the judge's job).  SDC = original sky130_cpu.sdc (NOT DC's written SDC).
set TLUP $B/nxtgrd/nom/sky130A_nom.tluplus
set LMAP $B/tech/map/starrc_layer.map
# ---- dont_use: the PDK-enablement list (dont_use.tcl, 21 cells) + LibreLane's PNR exclusion list (drc_exclude.cells + EXTRA_EXCLUDED_CELLS)
source $PDKDIR/scripts/dont_use.tcl
set fh [open $::env(HOME)/pdk/sky130A/libs.tech/openlane/sky130_fd_sc_hd/drc_exclude.cells r]
set _excl [list sky130_fd_sc_hd__probe_p_8 sky130_fd_sc_hd__probec_p_8]
while {[gets $fh l] >= 0} { set l [string trim $l]; if {$l ne "" && ![string match #* $l]} { lappend _excl $l } }
close $fh
foreach c [lsort -unique $_excl] { set _lc [get_lib_cells -quiet */$c]; if {[sizeof_collection $_lc]} { set_dont_use $_lc } }
# diode_2 is a protection cell (no logic function): dont_use.tcl blocks it for synthesis, but the antenna fixer must be allowed to insert it
set_attribute [get_lib_cells -quiet */sky130_fd_sc_hd__diode_2] dont_use false
# physical-only / filler cells must never be picked by optimisation
set_dont_use [get_lib_cells -quiet {*/sky130_fd_sc_hd__decap_* */sky130_fd_sc_hd__fill_* */sky130_fd_sc_hd__tap*}]
# ---- routing layers: li1 is cell-internal; signals met1..met4 (RT_MAX_LAYER met4)
set_ignored_layers -min_routing_layer met1 -max_routing_layer met4
# ---- parasitics: nominal TLU+ for early and late (no min/max TLU+ exist)
catch {remove_parasitic_tech -all}
read_parasitic_tech -tlup $TLUP -layermap $LMAP -name tlu_nom
set_parasitic_parameters -early_spec tlu_nom -late_spec tlu_nom
# ---- constraints
if {[llength [all_clocks]] == 0} { read_sdc $SDC }
