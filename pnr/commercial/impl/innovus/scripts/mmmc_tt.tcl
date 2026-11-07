# mmmc_tt.tcl -- tt-only MMMC for the Innovus implementation arm (Step B5b).  Same library files, SDC and rc-corner style as
# pdk/sky130/scripts/mmmc.tcl (Innovus delay-corner form) but ONLY the tt view (setup and hold), like the OpenROAD/ICC2 arms (multi-corner is the judge's job).
set _here $::env(HERE)/scripts
set REPO  $::env(REPO)
set SDC   $::env(SDC)
set QRC   $::env(HERE)/build/qrc
set HDLIB "$::env(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/lib"
set SRAMLIB "$REPO/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib"
create_library_set -name lib_tt -timing [list $HDLIB/sky130_fd_sc_hd__tt_025C_1v80.lib $SRAMLIB]
if {[file exists $QRC/nom/qrcTechFile]} {
  create_rc_corner -name rc_nom -temperature 25 -qrc_tech $QRC/nom/qrcTechFile
  puts "mmmc_tt: rc_nom uses qrcTechFile"
} elseif {[info exists ::env(CAPTBL)] && [file exists $::env(CAPTBL)]} {
  create_rc_corner -name rc_nom -temperature 25 -cap_table $::env(CAPTBL)
  puts "mmmc_tt: rc_nom uses capTable $::env(CAPTBL)"
} else {
  create_rc_corner -name rc_nom -temperature 25
  puts "mmmc_tt: WARNING rc_nom has NO qrcTechFile / capTable -> tech-LEF RC only"
}
create_delay_corner -name dc_tt -library_set lib_tt -rc_corner rc_nom
create_constraint_mode -name func -sdc_files [list $SDC]
create_analysis_view -name av_tt -constraint_mode func -delay_corner dc_tt
set_analysis_view -setup {av_tt} -hold {av_tt}
