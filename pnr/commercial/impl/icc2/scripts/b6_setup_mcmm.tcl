# b6_setup_mcmm.tcl -- b6 MCMM constraints/parasitics/library setup (sourced once, in b6_03_place; scenarios/PVT/parasitic specs are stored with the block).
#   Cell-name clash ss/ff/tt: the three std-cell NDMs (sky130_hd_tt / _ss / _ff) carry the SAME cell names with identical frames and different timing; ICC2 treats them as
#   multi-PVT views of one logical lib cell and picks the library whose characterization point (process/voltage/temperature) matches the corner.
#   So each corner sets its PVT with set_process_number / set_voltage / set_temperature (design top level); the TT-only SRAM (bead o1i) is pinned to 1.8 V / 25 C / process 1 in every corner.
#   Corners (mapping identical to pdk/sky130/scripts/mmmc.tcl and the DC v2 run):  ss = ss_100C_1v60 + max TLU+ (setup);  tt = tt_025C_1v80 + nom TLU+ (setup+hold);  ff = ff_n40C_1v95 + min TLU+ (hold).
#   The shared SDC (md5 3c696350...) is read unchanged into every scenario.
set LMAP $B/tech/map/starrc_layer.map
# ---- dont_use: PDK-enablement list + LibreLane PNR exclusion list (patterns */<cell> hit all three libs)
source $PDKDIR/scripts/dont_use.tcl
set fh [open $::env(HOME)/pdk/sky130A/libs.tech/openlane/sky130_fd_sc_hd/drc_exclude.cells r]
set _excl [list sky130_fd_sc_hd__probe_p_8 sky130_fd_sc_hd__probec_p_8]
while {[gets $fh l] >= 0} { set l [string trim $l]; if {$l ne "" && ![string match #* $l]} { lappend _excl $l } }
close $fh
foreach c [lsort -unique $_excl] { set _lc [get_lib_cells -quiet */$c]; if {[sizeof_collection $_lc]} { set_dont_use $_lc } }
set_attribute [get_lib_cells -quiet */sky130_fd_sc_hd__diode_2] dont_use false
set_dont_use [get_lib_cells -quiet {*/sky130_fd_sc_hd__decap_* */sky130_fd_sc_hd__fill_* */sky130_fd_sc_hd__tap*}]
set_ignored_layers -min_routing_layer met1 -max_routing_layer met4
# ---- parasitic techs: max / nom / min TLU+ (tuned-ITF generation, build/nxtgrd)
catch {remove_parasitic_tech -all}
foreach t {max nom min} { read_parasitic_tech -tlup $B/nxtgrd/$t/sky130A_$t.tluplus -layermap $LMAP -name tlu_$t }
# ---- mode / corners / scenarios
set _old_sc [get_object_name [all_scenarios]]
create_mode func
foreach c {ss tt ff} { create_corner $c }
foreach c {ss tt ff} { create_scenario -mode func -corner $c -name func_$c }
foreach s $_old_sc { catch {remove_scenarios [get_scenarios $s]} }
catch {remove_corners [get_corners default]}
catch {remove_modes [get_modes default]}
puts "SCENARIOS: [get_object_name [all_scenarios]]  CORNERS: [get_object_name [all_corners]]  MODES: [get_object_name [all_modes]]"
set srams [get_cells -hierarchical -filter "ref_name==$SRAM"]
array set PVT {ss {1.6 100 max} tt {1.8 25 nom} ff {1.95 -40 min}}
foreach c {ss tt ff} {
  lassign $PVT($c) v t rc
  current_scenario func_$c
  read_sdc $SDC
  set_parasitic_parameters -corners [get_corners $c] -early_spec tlu_$rc -late_spec tlu_$rc -early_temperature $t -late_temperature $t
  set_process_number 1 -corners [get_corners $c]
  set_voltage $v -corners [get_corners $c]
  set_temperature $t -corners [get_corners $c]
  # the SRAM has a single TT 1.8 V 25 C characterization (bead o1i): pin it in every corner so the PVT matcher does not look for an ss/ff view that does not exist
  catch {set_voltage 1.8 -corners [get_corners $c] -object_list $srams} e1
  catch {set_temperature 25 -corners [get_corners $c] -object_list $srams} e2
  catch {set_process_number 1 -corners [get_corners $c] -object_list $srams} e3
  puts "SRAM_PVT $c: $e1 | $e2 | $e3"
}
# ---- scenario analysis flags: setup on ss+tt, hold on ff+tt; DRV (transition/capacitance) at ss+tt; power only at tt
set_scenario_status func_ss -setup true  -hold false -max_transition true  -max_capacitance true  -min_capacitance false -leakage_power false -dynamic_power false -active true
set_scenario_status func_tt -setup true  -hold true  -max_transition true  -max_capacitance true  -min_capacitance false -leakage_power true  -dynamic_power true  -active true
set_scenario_status func_ff -setup false -hold true  -max_transition false -max_capacitance false -min_capacitance false -leakage_power false -dynamic_power false -active true
current_scenario func_tt
puts "SDC_MD5: [exec md5sum $SDC]"
redirect -file $RUN/reports/scenarios.txt { report_scenarios; report_pvt; report_parasitic_parameters -corners [all_corners] }
