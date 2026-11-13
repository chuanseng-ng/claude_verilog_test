# Doc: cr:pd:sky130-soc-plugin-librelane-cvt-tcl-rc-calibration
# HOW: scripts under librelane/scripts/openroad source common/set_rc.tcl and then estimate. The
# wrapper script (see steps.py) renames `source` so that this proc runs immediately after every
# `.../common/set_rc.tcl`, leaving the shared LibreLane install untouched.
#
# CVT_RC_CALIBRATION: "nom=1.88,1.02 min=1.69,0.62 max=2.04,1.91", i.e. <rc corner>=<C>,<R>
# multipliers applied to the tech-LEF per-layer values for STA corners whose name starts with
# nom_/min_/max_.
proc cvt_apply_rc_calibration {} {
    if { ![info exists ::env(CVT_RC_CALIBRATION)] || $::env(CVT_RC_CALIBRATION) eq "" } {
        return
    }
    set cal [dict create]
    foreach ent $::env(CVT_RC_CALIBRATION) {
        lassign [split $ent "="] key vals
        dict set cal $key [split $vals ","]
    }
    # Same layer walk as set_rc.tcl: RT_MIN_LAYER .. RT_MAX_LAYER, routing layers only.
    set names [list]
    set adding 0
    foreach layer [$::tech getLayers] {
        if { [$layer getRoutingLevel] >= 1 } {
            set n [$layer getName]
            if { $::env(RT_MIN_LAYER) eq $n } { set adding 1 }
            if { $adding } { lappend names $n }
            if { $::env(RT_MAX_LAYER) eq $n } { set adding 0 }
        }
    }
    if { [info exists ::env(SIGNAL_WIRE_RC_LAYERS)] } {
        set names $::env(SIGNAL_WIRE_RC_LAYERS)
    }
    foreach c [ol_compat_corners] {
        set cn [ol_compat_corner_name $c]
        set key [string range $cn 0 2]
        if { ![dict exists $cal $key] } { continue }
        lassign [dict get $cal $key] fc fr
        foreach n $names {
            set dbl [$::tech findLayer $n]
            lassign [rsz::dblayer_wire_rc $dbl] r_si c_si   ;# ohm/m, F/m
            # set_layer_rc takes liberty-unit values: kohm/um, pF/um
            set r_k [expr {$r_si * 1e-9 * $fr}]
            set c_p [expr {$c_si * 1e6 * $fc}]
            set_layer_rc -layer $n -corner $cn -resistance $r_k -capacitance $c_p
        }
        if { [llength $names] > 1 } {
            set_wire_rc -corner $cn -signal -layers $names
        } else {
            set_wire_rc -corner $cn -signal -layer $names
        }
    }
    puts "\[INFO\] cvt: calibrated signal wire RC per corner with '$cal' over layers $names"
}
