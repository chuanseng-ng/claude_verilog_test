# mmmc_b6.tcl -- b6: FULL MMMC for the Innovus implementation arm (Genus v1 netlist, rv32i_cpu_top).
#   Views: av_ss (lib ss_100C_1v60 + rc_max), av_tt (tt_025C_1v80 + rc_nom), av_ff (ff_n40C_1v95 + rc_min).  Setup {av_ss av_tt}, hold {av_ff av_tt}.
#   RC corners = layer-correct capTables of captbl6 (li1 -> met0 ICT trick): nom / min / max.  -temperature 25 for all three, as in b5k (the tables carry no TC coefficients).
#   Every view gets an EXPLICIT -latency_file (b6 lesson from b5k: a new view otherwise starts with an EMPTY latency.sdc and clk_io then has network latency 0).
#   SRAM Liberty: sky130_sram_1kbyte_1rw1r_32x256_8 is characterised at TT 1.8 V 25 C ONLY, so the SAME TT macro model is in all three library sets (bead o1i):
#   ss and ff results use a TT macro model.  env: SDC (constraint file), LATF (latency file; default b6 pre-CTS file), REPO, HERE, PDK_ROOT
set REPO  $::env(REPO)
set SDC   $::env(SDC)
set CT    $REPO/pnr/commercial/impl/innovus/captbl6
set LATF  [expr {[info exists ::env(LATF)] ? $::env(LATF) : "$REPO/pnr/commercial/constraints/sky130_cpu_innovus_b6_latency_pre.sdc"}]
set HDLIB "$::env(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/lib"
set SRAMLIB "$REPO/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib"
create_library_set -name lib_tt -timing [list $HDLIB/sky130_fd_sc_hd__tt_025C_1v80.lib $SRAMLIB]
create_library_set -name lib_ss -timing [list $HDLIB/sky130_fd_sc_hd__ss_100C_1v60.lib $SRAMLIB]
create_library_set -name lib_ff -timing [list $HDLIB/sky130_fd_sc_hd__ff_n40C_1v95.lib $SRAMLIB]
create_rc_corner -name rc_nom -temperature 25 -cap_table $CT/sky130A_nom_li1m1.captbl
create_rc_corner -name rc_min -temperature 25 -cap_table $CT/sky130A_min_li1m1.captbl
create_rc_corner -name rc_max -temperature 25 -cap_table $CT/sky130A_max_li1m1.captbl
create_delay_corner -name dc_tt -library_set lib_tt -rc_corner rc_nom
create_delay_corner -name dc_ss -library_set lib_ss -rc_corner rc_max
create_delay_corner -name dc_ff -library_set lib_ff -rc_corner rc_min
create_constraint_mode -name func -sdc_files [list $SDC]
create_analysis_view -name av_tt -constraint_mode func -delay_corner dc_tt -latency_file $LATF
create_analysis_view -name av_ss -constraint_mode func -delay_corner dc_ss -latency_file $LATF
create_analysis_view -name av_ff -constraint_mode func -delay_corner dc_ff -latency_file $LATF
set_analysis_view -setup {av_ss av_tt} -hold {av_ff av_tt}
puts "mmmc_b6: views av_ss(rc_max) av_tt(rc_nom) av_ff(rc_min), latency file $LATF"
