# cvt_wrap.tcl - Run a stock LibreLane OpenROAD script with the project's wire-RC calibration
#
# Scope: a CVT plugin step runs it in place of the stock script. CVT_REAL_SCRIPT is the stock script. CVT_PROJ_TCL is this directory.
# Contents: renames Tcl source so that cvt_apply_rc_calibration runs right after every .../common/set_rc.tcl,
#   whichever step script sources it and wherever it does so. The shared LibreLane install is not edited.
# Inputs: _TCL_ENV_IN, CVT_REAL_SCRIPT, CVT_PROJ_TCL and CVT_RC_CALIBRATION. TclStep moves every non-allowlisted variable
#   into the file named by _TCL_ENV_IN, not into the process environment. So the CVT_* variables exist only after this file sources it.
#   io.tcl sources that file again later. That is idempotent.
# User rules: with CVT_RC_CALIBRATION empty, this file only forwards to the real script.
# Doc: tm:pd:sky130-soc-plugin-librelane-cvt-tcl-wrap
source $::env(_TCL_ENV_IN)
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
