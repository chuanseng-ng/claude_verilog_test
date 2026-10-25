# mmmc.tcl -- Innovus / Genus multi-mode multi-corner file for Sky130 (sky130_fd_sc_hd).  Part 2a: load-tested in Genus and Innovus.
#
# Usage:  source mmmc.tcl     (Innovus: read_mmmc this file;  Genus: read_mmmc this file)
#   env  REPO       repo root (default: 4 levels above this script)
#        SDC        constraint file   (default: pnr/sky130/cpu/constraints/sky130_cpu.sdc)
#        QRC_DIR    dir holding nom/ min/ max/ sub-dirs each with qrcTechFile (Techgen output, build/qrc)
#        PDK_ROOT / SKY130_HD_LIB_{TT,SS,FF}   from tools/eda/pd_env.sh
#
# CORNERS (indicative PVT -> RC mapping; all RC from the AUTHORED qrcTechFile, correlate in part 2):
#   tt  = tt_025C_1v80 lib, rc_nom (25C)       ss = ss_100C_1v60 lib, rc_max (100C)     ff = ff_n40C_1v95 lib, rc_min (-40C)
#   setup views: ss + tt ; hold views: ff + tt.
#
# SRAM NOTE: sky130_sram_1kbyte_1rw1r_32x256_8 is characterised at TT 1.8V 25C ONLY (no ss/ff Liberty ships).
#   The same patched TT SRAM lib is therefore added to ALL three library sets -> ss/ff results use a TT macro model
#   (see docs/SKY130_CPU_SS_SETUP_R51P.md; physical gates unaffected, per-corner SRAM timing is bead o1i).
#   The patched copy (max_transition 0.04 -> 0.5, bead 0ro) is used, NOT the PDK copy; the PDK copy makes
#   repair/optimisation abort with RSZ-0090-class "unachievable max_transition" errors.

# Innovus sources init_mmmc_file in a context where [info script] is not this file; prefer env HERE (= pdk/sky130 dir).
set _here [expr {[info exists ::env(HERE)] ? "$::env(HERE)/scripts" : [file dirname [file normalize [info script]]]}]
set REPO  [expr {[info exists ::env(REPO)] ? $::env(REPO) : [file normalize $_here/../../../../..]}]
set SDC   [expr {[info exists ::env(SDC)]  ? $::env(SDC)  : "$REPO/pnr/sky130/cpu/constraints/sky130_cpu.sdc"}]
set QRC   [expr {[info exists ::env(QRC_DIR)] ? $::env(QRC_DIR) : [file normalize $_here/../build/qrc]}]
set HDLIB "$::env(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/lib"
set SRAM  "$REPO/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib"

create_library_set -name lib_tt -timing [list $HDLIB/sky130_fd_sc_hd__tt_025C_1v80.lib $SRAM]
create_library_set -name lib_ss -timing [list $HDLIB/sky130_fd_sc_hd__ss_100C_1v60.lib $SRAM]
create_library_set -name lib_ff -timing [list $HDLIB/sky130_fd_sc_hd__ff_n40C_1v95.lib $SRAM]

# RC corners: qrcTechFile from Techgen (scripts/run_techgen.sh) WHEN IT EXISTS.  Techgen needs hours per corner, so until
# build/qrc/<c>/qrcTechFile is present the corner is created WITHOUT -qrc_tech: both tools then fall back to the
# per-layer RPERSQ / CPERSQDIST / EDGECAPACITANCE of the tech LEF (pre-route RC estimate only; no post-route
# extraction is possible in that mode).  The rc corner NAMES and temperatures are identical in both modes, so the
# analysis views below do not change when the qrcTechFile appears.   -temperature drives the (absent) TC1/TC2 scaling.
proc _cvt_rc {name temp dir} {
  global QRC
  if {[file exists $QRC/$dir/qrcTechFile]} {
    create_rc_corner -name $name -temperature $temp -qrc_tech $QRC/$dir/qrcTechFile
    puts "mmmc: $name uses qrcTechFile $QRC/$dir/qrcTechFile"
  } else {
    create_rc_corner -name $name -temperature $temp
    puts "mmmc: WARNING $name has NO qrcTechFile (not built yet) -> tech-LEF RC only"
  }
}
_cvt_rc rc_nom  25 nom
_cvt_rc rc_max 100 max
_cvt_rc rc_min -40 min

# Delay-corner style differs by tool (measured, part 2a):
#   Genus 23.14  : create_delay_corner has NO -library_set; it needs create_timing_condition + -timing_condition (TUI-64/TIM-414)
#   Innovus 23.1 : rejects the timing_condition form here ("Mixed usage of library_set and timing_condition", TCLCMD-992);
#                  uses the classic create_delay_corner -library_set form.
# Auto-detected (place_design exists only in Innovus); override with env CVT_MMMC_STYLE=timing_condition|library_set.
if {[info exists ::env(CVT_MMMC_STYLE)]} {
  set _style $::env(CVT_MMMC_STYLE)
} else {
  set _style [expr {[llength [info commands place_design]] ? "library_set" : "timing_condition"}]
}
if {$_style eq "timing_condition"} {
  create_timing_condition -name tc_tt -library_sets lib_tt
  create_timing_condition -name tc_ss -library_sets lib_ss
  create_timing_condition -name tc_ff -library_sets lib_ff
  create_delay_corner -name dc_tt -timing_condition tc_tt -rc_corner rc_nom
  create_delay_corner -name dc_ss -timing_condition tc_ss -rc_corner rc_max
  create_delay_corner -name dc_ff -timing_condition tc_ff -rc_corner rc_min
} else {
  create_delay_corner -name dc_tt -library_set lib_tt -rc_corner rc_nom
  create_delay_corner -name dc_ss -library_set lib_ss -rc_corner rc_max
  create_delay_corner -name dc_ff -library_set lib_ff -rc_corner rc_min
}

create_constraint_mode -name func -sdc_files [list $SDC]

create_analysis_view -name av_tt -constraint_mode func -delay_corner dc_tt
create_analysis_view -name av_ss -constraint_mode func -delay_corner dc_ss
create_analysis_view -name av_ff -constraint_mode func -delay_corner dc_ff

set_analysis_view -setup {av_ss av_tt} -hold {av_ff av_tt}

# Innovus only (ignored by Genus): map tech-LEF layer names to ICT layer names (qrc cap-table needs it for "via").
#   setExtractRCMode -lefTechFileMap $QRC/../tech/map/quantus_lef2ict.map
