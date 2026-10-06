# Wrapper that runs a stock LibreLane OpenROAD script with the project's wire-RC calibration
# (bead claude_verilog_test-e45j). CVT_REAL_SCRIPT is the stock script; CVT_PROJ_TCL this directory.
#
# `source` is renamed so that cvt_apply_rc_calibration runs right after every
# `.../common/set_rc.tcl`, whichever step script sources it and wherever in the script that
# happens -- the shared LibreLane install is not edited. With CVT_RC_CALIBRATION empty this file
# only forwards to the real script.
source $::env(CVT_PROJ_TCL)/rc_calibration.tcl

if { [info exists ::env(CVT_RC_CALIBRATION)] && $::env(CVT_RC_CALIBRATION) ne "" } {
    rename source ::cvt_orig_source
    proc source {args} {
        set rc [uplevel 1 [list ::cvt_orig_source {*}$args]]
        if { [string match "*/common/set_rc.tcl" [lindex $args end]] } {
            cvt_apply_rc_calibration
        }
        return $rc
    }
    puts "\[INFO\] cvt: RC calibration armed: $::env(CVT_RC_CALIBRATION)"
    ::cvt_orig_source $::env(CVT_REAL_SCRIPT)
} else {
    puts "\[INFO\] cvt: RC calibration disabled; running stock script"
    source $::env(CVT_REAL_SCRIPT)
}
