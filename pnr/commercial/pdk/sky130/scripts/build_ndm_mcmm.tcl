# build_ndm_mcmm.tcl -- b6: ONE std-cell reference NDM with three PVT panes (tt / ss / ff) instead of three NDMs that share cell names.
#   Why: with sky130_hd_{tt,ss,ff}.ndm linked together ICC2 binds every instance to the first library (sky130_hd_tt) and reports "Library has 1 pane" / PVT mismatches in the
#   ss and ff corners (measured, b6_03a_mcmmtest).  A multi-pane library keeps one set of frames and a timing view (pane) per characterization point; the per-corner
#   set_process_number / set_voltage / set_temperature then select the pane (PVT matching).
# Run:  icc2_lm_shell -f build_ndm_mcmm.tcl   (env REPO, PDK_ROOT; NDM_OUT default <this>/../build/ndm)
set _here [file dirname [file normalize [info script]]]
set OUT   [expr {[info exists ::env(NDM_OUT)] ? $::env(NDM_OUT) : [file normalize $_here/../build/ndm]}]
set DBDIR [file normalize $_here/../build/db]
set PDK   "$::env(PDK_ROOT)/sky130A/libs.ref"
set TLEF  "$OUT/sky130_hd.tf"
set HDLEF "$PDK/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef"
set ws sky130_hd_mcmm
create_workspace -technology $TLEF -flow normal -scale_factor 1000 $ws
source $OUT/sky130_layer_dirs.tcl
read_lef $HDLEF
foreach c {tt ss ff} {
  array set HDDB [list tt "$DBDIR/sky130_fd_sc_hd__tt_025C_1v80.db" ss "$DBDIR/sky130_fd_sc_hd__ss_100C_1v60.db" ff "$DBDIR/sky130_fd_sc_hd__ff_n40C_1v95.db"]
  read_db $HDDB($c)
}
check_workspace -allow_missing -details arcs_progress
file delete -force $OUT/$ws.ndm
commit_workspace -output $OUT/$ws.ndm
remove_workspace
exit
