# mmmc.tcl -- Innovus / Genus multi-mode multi-corner template for Sky130 (sky130_fd_sc_hd) -- WRITTEN, NOT RUN.
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

set _here [file dirname [file normalize [info script]]]
set REPO  [expr {[info exists ::env(REPO)] ? $::env(REPO) : [file normalize $_here/../../../../..]}]
set SDC   [expr {[info exists ::env(SDC)]  ? $::env(SDC)  : "$REPO/pnr/sky130/cpu/constraints/sky130_cpu.sdc"}]
set QRC   [expr {[info exists ::env(QRC_DIR)] ? $::env(QRC_DIR) : [file normalize $_here/../build/qrc]}]
set HDLIB "$::env(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/lib"
set SRAM  "$REPO/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib"

create_library_set -name lib_tt -timing [list $HDLIB/sky130_fd_sc_hd__tt_025C_1v80.lib $SRAM]
create_library_set -name lib_ss -timing [list $HDLIB/sky130_fd_sc_hd__ss_100C_1v60.lib $SRAM]
create_library_set -name lib_ff -timing [list $HDLIB/sky130_fd_sc_hd__ff_n40C_1v95.lib $SRAM]

# RC corners: qrcTechFile from Techgen (scripts/run_techgen.sh); -temperature drives the (absent) TC1/TC2 scaling.
create_rc_corner -name rc_nom -temperature  25 -qrc_tech $QRC/nom/qrcTechFile
create_rc_corner -name rc_max -temperature 100 -qrc_tech $QRC/max/qrcTechFile
create_rc_corner -name rc_min -temperature -40 -qrc_tech $QRC/min/qrcTechFile

create_delay_corner -name dc_tt -library_set lib_tt -rc_corner rc_nom
create_delay_corner -name dc_ss -library_set lib_ss -rc_corner rc_max
create_delay_corner -name dc_ff -library_set lib_ff -rc_corner rc_min

create_constraint_mode -name func -sdc_files [list $SDC]

create_analysis_view -name av_tt -constraint_mode func -delay_corner dc_tt
create_analysis_view -name av_ss -constraint_mode func -delay_corner dc_ss
create_analysis_view -name av_ff -constraint_mode func -delay_corner dc_ff

set_analysis_view -setup {av_ss av_tt} -hold {av_ff av_tt}

# Innovus only (ignored by Genus): map tech-LEF layer names to ICT layer names (qrc cap-table needs it for "via").
#   setExtractRCMode -lefTechFileMap $QRC/../tech/map/quantus_lef2ict.map
