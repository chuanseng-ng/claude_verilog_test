# build_ndm.tcl -- ICC2 library-manager NDM build for sky130_fd_sc_hd + sky130 SRAM macro (part 2a: RUN, see report).
#
# Run (part 2):  icc2_lm_shell -f build_ndm.tcl     (single-thread; env CORNER=tt|ss|ff, default all three)
#   env  REPO, PDK_ROOT (pd_env.sh), NDM_OUT (default <this>/../build/ndm)
#
# Inputs
#   technology : build/ndm/sky130_hd.tf -- icc2_lm_shell cannot take a tech LEF; scripts/gen_techfile.py derives the .tf
#                from sky130_fd_sc_hd__nom.tlef (layers, pitches, widths, spacing tables, cut enclosures, sites).
#   std cells  : sky130_fd_sc_hd.lef + .db from build/db (scripts/lib2db.sh, lc_shell)
#   SRAM       : sky130_sram_1kbyte_1rw1r_32x256_8.lef + the .db built from the PATCHED liberty
#                (pnr/sky130/cpu/pdk_lib_patched, max_transition 0.04->0.5 -- do not use the PDK lib)
#
# One NDM per corner (cells have identical frames, different timing views) -> ICC2 links the set it needs.
# The SRAM has a single (TT) .db, so the same SRAM .db is read into every corner workspace.
#
# Known caveats to check in part 2:
#   * tlef has no PROPERTYDEFINITIONS-backed site symmetry issues expected, but "unithd"/"unithddbl" SITE
#     names must match the cell LEF (they do in the shipped pair).
#   * tlef carries no TLU+; parasitics come from build/nxtgrd -> TLU+ (set_tlu_plus_files in the ICC2 flow).
#   * check_workspace must show 428 stdcell frames + 1 macro; lib/LEF pin mismatches here are the thing
#     lc_shell's check_library could not verify (it produced no physical report).

set _here [file dirname [file normalize [info script]]]
set REPO  [expr {[info exists ::env(REPO)] ? $::env(REPO) : [file normalize $_here/../../../../..]}]
set OUT   [expr {[info exists ::env(NDM_OUT)] ? $::env(NDM_OUT) : [file normalize $_here/../build/ndm]}]
set DBDIR [file normalize $_here/../build/db]
set PDK   "$::env(PDK_ROOT)/sky130A/libs.ref"
set TLEF  "$OUT/sky130_hd.tf"
set HDLEF "$PDK/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"
set SRLEF "$PDK/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef"
set SRDB  "$DBDIR/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db"

array set HDDB [list \
  tt "$DBDIR/sky130_fd_sc_hd__tt_025C_1v80.db" \
  ss "$DBDIR/sky130_fd_sc_hd__ss_100C_1v60.db" \
  ff "$DBDIR/sky130_fd_sc_hd__ff_n40C_1v95.db"]

# CORNER=tt|ss|ff builds that stdcell corner; phys = physical-only cells (fill/tap); sram = macro NDM; unset builds all.
set corners [expr {[info exists ::env(CORNER)] ? [list $::env(CORNER)] : {tt ss ff phys sram}}]
file mkdir $OUT

# The normal flow requires every logic .db in a workspace to carry the same cell set as the physical (LEF)
# source, and the same PG rail names.  The hd cells and the SRAM macro differ in both (VPWR/VGND/VPB/VNB vs
# vccd1/vssd1), so the stdcell corners and the macro are separate reference libraries:
#   sky130_hd_<c>.ndm  (one per corner)       sky130_sram_1kbyte_1rw1r_32x256_8.ndm  (TT only: single .db)
foreach c $corners {
  if {$c eq "phys"} {
    # 9 LEF cells have no Liberty (fill_1/2/4/8, tap_1/2, tapvgnd_1, tapvgnd2_1, tapvpwrvgnd_1): physical-only flow.
    set ws sky130_hd_phys
    create_workspace -technology $TLEF -flow physical_only -scale_factor 1000 $ws
    source $OUT/sky130_layer_dirs.tcl
    read_lef $HDLEF
    read_db  $HDDB(tt)
  } elseif {$c eq "sram"} {
    set ws sky130_sram_1kbyte_1rw1r_32x256_8
    create_workspace -technology $TLEF -flow normal -scale_factor 1000 $ws
    source $OUT/sky130_layer_dirs.tcl
    read_lef $SRLEF
    read_db  $SRDB
  } else {
    set ws sky130_hd_$c
    create_workspace -technology $TLEF -flow normal -scale_factor 1000 $ws
    source $OUT/sky130_layer_dirs.tcl
    read_lef $HDLEF
    read_db  $HDDB($c)
  }
  check_workspace
  file delete -force $OUT/$ws.ndm
  commit_workspace -output $OUT/$ws.ndm
  remove_workspace
}
exit
