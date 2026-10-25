# build_ndm.tcl -- ICC2 library-manager NDM build for sky130_fd_sc_hd + sky130 SRAM macro -- WRITTEN, NOT RUN.
#
# Run (part 2):  icc2_lm_shell -f build_ndm.tcl     (single-thread; env CORNER=tt|ss|ff, default all three)
#   env  REPO, PDK_ROOT (pd_env.sh), NDM_OUT (default <this>/../build/ndm)
#
# Inputs
#   technology : $SKY130_HD_TLEF  (sky130_fd_sc_hd__nom.tlef -- routing layers, cuts, antenna, EM densities)
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
set TLEF  "$PDK/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"
set HDLEF "$PDK/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"
set SRLEF "$PDK/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef"
set SRDB  "$DBDIR/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.db"

array set HDDB [list \
  tt "$DBDIR/sky130_fd_sc_hd__tt_025C_1v80.db" \
  ss "$DBDIR/sky130_fd_sc_hd__ss_100C_1v60.db" \
  ff "$DBDIR/sky130_fd_sc_hd__ff_n40C_1v95.db"]

set corners [expr {[info exists ::env(CORNER)] ? [list $::env(CORNER)] : {tt ss ff}}]
file mkdir $OUT

foreach c $corners {
  set ws sky130_hd_$c
  create_workspace -technology $TLEF -flow normal $ws
  read_lef $HDLEF
  read_lef $SRLEF
  read_db  $HDDB($c)
  read_db  $SRDB
  check_workspace
  commit_workspace -output $OUT/$ws.ndm
  remove_workspace
}
exit
