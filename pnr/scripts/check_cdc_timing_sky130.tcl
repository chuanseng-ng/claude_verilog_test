#================================================================
# Post-route CDC budget verification for the 2-domain Sky130 SoC
# Tool: OpenSTA (standalone 'sta' from the librelane nix-shell)
# bead claude_verilog_test-j41m.5 (2026-10-16). Sky130 sibling of check_cdc_timing.tcl
# (ASAP7); that script is left untouched.
#
# Reads a finished LibreLane Sky130 SoC run (netlist + OpenRCX SPEF), the std-cell / CPU-macro /
# SRAM Liberty of ONE corner, and pnr/sky130/soc/constraints/sky130_soc_cdc_check.sdc, then
# reports the slack of every CDC group the SDC budgets. See that SDC for why the budgets live
# in a file separate from the implementation SDC.
#
# Usage:
#   CDC_CHECK_RUN_DIR=/nobackup/sky130_soc_runs/RUN_... [CDC_CHECK_CORNER=nom_tt_025C_1v80] \
#     sta -no_init -exit pnr/scripts/check_cdc_timing_sky130.tcl
# or: make -C pnr check-cdc-timing-sky130-soc RUN_DIR=... [CDC_CORNER=...]
#
# Env:
#   CDC_CHECK_RUN_DIR   (required) LibreLane run dir.
#   CDC_CHECK_SKEW_FRAC  default 0.25. Per-pointer bit-skew limit as a fraction of min(source, destination) period
#                        (see the skew section for the justification). CDC_CHECK_SKEW_LIMIT (ns) overrides it.
#   CDC_CHECK_CORNER    default nom_tt_025C_1v80 (one corner per sta run; `make check-cdc-timing-sky130-soc` loops nom_tt AND
#                       max_ss by default, bead j41m.5). One of {nom,min,max}_{tt_025C_1v80,ss_100C_1v60,ff_n40C_1v95}.
#                       The prefix picks the SPEF (OpenRCX writes nom/min/max), the rest the Liberty.
#   CDC_CHECK_NETLIST   default <run>/final/nl/soc_top.nl.v, else the fill-insertion step's nl.v.
#   CDC_CHECK_SPEF      default <run>/*-openroad-rcx/<nom|min|max>/soc_top.<..>.spef; "none" = no parasitics.
#   CDC_CHECK_SDC       default pnr/sky130/soc/constraints/sky130_soc_cdc_check.sdc.
#   CDC_CHECK_REPORTS   default ./reports/cdc_sky130.
#   CDC_CHECK_PNR_DIR   default: the pnr/ directory this script lives in (override when it is reached through a symlink).
#   PDK_ROOT            default the ciel path the flow uses.
#
# Clocks are IDEAL (never set_propagated_clock): the budgets are datapath bounds (launch CK->Q
# plus wires/logic to the capture D pin), and OpenSTA has no -datapath_only to say so, so
# keeping the clock ideal is the available approximation (ASAP7 script, CDC_CHECK_PROPAGATED_CLOCK
# header). Parasitics are real (post-route OpenRCX SPEF), which the ASAP7 netlist-only path is not.
#
# EXIT CODE: 0 PASS, 1 CDC finding(s) (unbound exception or a violated/unconstrained group),
# 2 setup error (missing input). OpenSTA batch mode does not turn a Tcl `error` into an exit
# code, so every path ends in an explicit `exit`.
#================================================================

proc cdc_fatal_setup {msg} {
    puts "ERROR: CDC-CHECK-SETUP-ERROR: $msg"
    exit 2
}

set ::cdc_check_findings 0
set ::cdc_check_finding_msgs {}
proc cdc_record_finding {msg} {
    incr ::cdc_check_findings
    lappend ::cdc_check_finding_msgs $msg
}

proc cdc_env {name default} {
    return [expr {[info exists ::env($name)] && $::env($name) ne "" ? $::env($name) : $default}]
}

if {![info exists ::env(CDC_CHECK_RUN_DIR)]} {
    cdc_fatal_setup "CDC_CHECK_RUN_DIR is not set (a LibreLane Sky130 SoC run directory)."
}
set RUN_DIR [file normalize $::env(CDC_CHECK_RUN_DIR)]
set CORNER  [cdc_env CDC_CHECK_CORNER nom_tt_025C_1v80]
set PDK_ROOT [cdc_env PDK_ROOT /home/neuromorphic/.ciel/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af]
set REPORTS_DIR [cdc_env CDC_CHECK_REPORTS [file join [pwd] reports cdc_sky130]]
file mkdir $REPORTS_DIR

set SCRIPT_DIR [file dirname [file normalize [info script]]]
set REPO_PNR [cdc_env CDC_CHECK_PNR_DIR [file normalize [file join $SCRIPT_DIR ..]]]
set CHECK_SDC [cdc_env CDC_CHECK_SDC [file join $REPO_PNR sky130 soc constraints sky130_soc_cdc_check.sdc]]

if {![regexp {^(nom|min|max)_(tt_025C_1v80|ss_100C_1v60|ff_n40C_1v95)$} $CORNER -> RC_CORNER PVT]} {
    cdc_fatal_setup "bad CDC_CHECK_CORNER '$CORNER'"
}

# ---- netlist
set NETLIST [cdc_env CDC_CHECK_NETLIST ""]
if {$NETLIST eq ""} {
    set _cands [concat [glob -nocomplain $RUN_DIR/final/nl/soc_top.nl.v] \
                       [glob -nocomplain $RUN_DIR/*-openroad-fillinsertion/soc_top.nl.v]]
    if {[llength $_cands] == 0} { cdc_fatal_setup "no soc_top.nl.v under $RUN_DIR (final/nl or *-openroad-fillinsertion)" }
    set NETLIST [lindex $_cands 0]
}
if {![file exists $NETLIST]} { cdc_fatal_setup "netlist not found: $NETLIST" }

# ---- liberty: std cell, CPU macro (this corner), SRAM macro (TT only, as in config)
set STD_LIB "$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__${PVT}.lib"
set CPU_LIB [file join $REPO_PNR sky130 cpu macro rv32i_cpu_top__${CORNER}.lib]
set SRAM_LIB [file join $REPO_PNR sky130 soc macro sky130_sram_4kbyte_1rw1r_32x1024_8_TT_1p8V_25C.lib]
foreach _l [list $STD_LIB $CPU_LIB $SRAM_LIB] {
    if {![file exists $_l]} { cdc_fatal_setup "liberty not found: $_l" }
}
puts "================================================================"
puts "CDC check (Sky130 SoC): run=$RUN_DIR corner=$CORNER"
puts "  netlist: $NETLIST"
puts "  libs   : $STD_LIB, $CPU_LIB, $SRAM_LIB"
puts "================================================================"
read_liberty $STD_LIB
read_liberty $CPU_LIB
read_liberty $SRAM_LIB

read_verilog $NETLIST
link_design soc_top

# ---- parasitics
set SPEF [cdc_env CDC_CHECK_SPEF ""]
if {$SPEF eq ""} {
    set _s [glob -nocomplain $RUN_DIR/*-openroad-rcx/$RC_CORNER/soc_top.$RC_CORNER.spef]
    if {[llength $_s] == 0} { cdc_fatal_setup "no OpenRCX SPEF for $RC_CORNER under $RUN_DIR (set CDC_CHECK_SPEF=none to run without parasitics)" }
    set SPEF [lindex $_s 0]
}
if {$SPEF ne "none"} {
    puts "Reading SPEF: $SPEF"
    read_spef $SPEF
} else {
    puts "WARNING: no parasitics (CDC_CHECK_SPEF=none): datapath-shape-only result"
}

# ---- check SDC (an unbound exception raises an error from the SDC itself; fold it in)
if {![file exists $CHECK_SDC]} { cdc_fatal_setup "check SDC not found: $CHECK_SDC" }
if {[catch {read_sdc $CHECK_SDC} _sdc_err]} {
    if {[info exists ::cdc_exception_misses] && [llength $::cdc_exception_misses] > 0} {
        foreach _m $::cdc_exception_misses { cdc_record_finding "unbound CDC exception: $_m" }
    } else {
        cdc_fatal_setup "read_sdc failed on $CHECK_SDC: $_sdc_err"
    }
}

#----------------------------------------------------------------
# Per-group report. The SDC records the capture D pins of each group in ::cdc_groups and the
# budget it applied in ::cdc_group_budget. The slack table (-format end) is parsed for the
# worst slack; the budget actually applied is READ BACK from the worst path's "max_delay"
# line, because a non-empty match proves a name matched, not that the exception bound.
#----------------------------------------------------------------
proc cdc_group_report {group} {
    set pins [expr {[dict exists $::cdc_groups $group] ? [dict get $::cdc_groups $group] : {}}]
    if {[llength $pins] == 0} {
        cdc_record_finding "group $group: no capture pins recorded (exception never applied)"
        return
    }
    set want [dict get $::cdc_group_budget $group]
    set rpt_tab  [file join $::REPORTS_DIR cdc_${group}.slack.rpt]
    set rpt_full [file join $::REPORTS_DIR cdc_${group}.worst.rpt]
    report_checks -to $pins -path_delay max -format end -group_count 2000 -digits 3 > $rpt_tab
    report_checks -to $pins -path_delay max -format full -digits 3 > $rpt_full
    set fh [open $rpt_tab r]; set tab [read $fh]; close $fh
    set fh [open $rpt_full r]; set full [read $fh]; close $fh

    set worst ""
    set n 0
    foreach line [split $tab "\n"] {
        # endpoint line: <name> <required> <actual> <slack>   (numbers, possibly negative)
        if {[regexp {^\s*\S+\s+\(\S+\)\s+(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+\((MET|VIOLATED)\)\s*$} $line -> req act sl st]} {
            incr n
            if {$worst eq "" || $sl < $worst} { set worst $sl }
        }
    }
    set applied ""
    # path report line: "  25.000   25.000   max_delay" (delay, time, label)
    if {![regexp {(-?[0-9]+\.[0-9]+)\s+-?[0-9]+\.[0-9]+\s+max_delay} $full -> applied]} { set applied "n/a" }
    if {$n == 0 || [string match "*No paths found*" $tab] || [string match "*unconstrained*" $tab]} {
        cdc_record_finding "group $group: unconstrained / no timed path to its ${n} capture endpoints (see $rpt_tab)"
        puts [format "CDC-GROUP %-12s endpoints=%-3d worst_slack=%-8s budget=%s  UNCONSTRAINED" $group $n "-" $want]
        return
    }
    set verdict "MET"
    if {$worst < 0} {
        set verdict "VIOLATED"
        cdc_record_finding "budget VIOLATED: group $group worst slack $worst ns (budget $want ns) (see $rpt_full)"
    }
    puts [format "CDC-GROUP %-12s endpoints=%-3d worst_slack=%-8s budget=%-6s applied=%-6s %s" $group $n $worst $want $applied $verdict]
    if {$applied ne "" && $applied ne "n/a" && abs($applied - $want) > 1e-6} {
        cdc_record_finding "group $group: applied max_delay $applied differs from intended $want (an overlapping exception won; see $rpt_full)"
    }
}

foreach g [lsort [dict keys $::cdc_groups]] { cdc_group_report $g }

# Domain-wide fallback (mem_q + apb cmd_/resp_ payload): worst data-pin path per direction.
foreach {dir f t} {cpu2core cpu_clk core_clk core2cpu core_clk cpu_clk} {
    set rpt [file join $REPORTS_DIR cdc_domain_wide_${dir}.rpt]
    report_checks -from [get_clocks $f] -to [get_clocks $t] -path_delay max -format full -digits 3 > $rpt
    set fh [open $rpt r]; set c [read $fh]; close $fh
    if {[string match "*VIOLATED*" $c]} {
        cdc_record_finding "budget VIOLATED: domain-wide fallback $f -> $t (see $rpt)"
        puts "CDC-GROUP domain_wide_${dir} VIOLATED"
    } elseif {[string match "*No paths found*" $c] || [string match "*unconstrained*" $c]} {
        cdc_record_finding "domain-wide fallback $f -> $t found no timed path (see $rpt)"
        puts "CDC-GROUP domain_wide_${dir} UNCONSTRAINED"
    } else {
        puts "CDC-GROUP domain_wide_${dir} MET"
    }
}

#----------------------------------------------------------------
# Per-pointer bit-skew (Cummings Gray-code criterion; bead j41m.5 option C).
#
# A gray pointer is safe across the boundary only if its bits arrive within a window narrower
# than the time between two successive pointer updates. The pointer changes at most once per
# SOURCE clock cycle, so the hard limit is skew < 1 source period (above that, the capture flop
# can see bits of update k and update k+1 mixed, which is not a gray neighbour). The budget
# above bounds the ABSOLUTE delay; this bounds the SPREAD, which is what makes gray coding
# work, and it keeps holding when a future change makes the absolute delay small but uneven.
#
# Skew of a pointer = max - min over its bits of the data ARRIVAL at the stage-0 D pin (launch
# clock latency + CK->Q + wire), measured with the launch/capture clocks PROPAGATED (set after
# the budget reports above, because the budgets are deliberately timed on ideal clocks): with
# ideal clocks the launch-tree skew between the bits' source flops would be invisible.
#
# Default limit = CDC_CHECK_SKEW_FRAC (0.25) x min(source, destination period). 0.25 is a 4x
# derate of the 1-source-period hard limit for what this single-corner, SPEF-only measurement
# cannot see (OCV between the bit paths, source-clock jitter, the ss/ff spread of the next
# run). min() because the period that matters is whichever clock is faster; they are both 25 ns
# here, so the limit is 6.25 ns. CDC_CHECK_SKEW_LIMIT (ns) overrides it absolutely.
#----------------------------------------------------------------
proc cdc_skew_report {} {
    set frac [cdc_env CDC_CHECK_SKEW_FRAC 0.25]
    set abs_limit [cdc_env CDC_CHECK_SKEW_LIMIT ""]
    set period [expr {[info exists ::clock_period] ? $::clock_period : 25.0}]
    if {$abs_limit ne ""} { set limit $abs_limit } else { set limit [expr {$frac * $period}] }
    if {[dict size $::cdc_ptr_info] == 0} {
        cdc_record_finding "bit-skew: no gray-pointer crossings recorded (the SDC's sec. 11 never ran)"
        return
    }
    set_propagated_clock [get_clocks {core_clk cpu_clk}]
    foreach ptr [lsort [dict keys $::cdc_ptr_info]] {
        lassign [dict get $::cdc_ptr_info $ptr] fc tc pins
        set nbits [llength $pins]
        set rpt [file join $::REPORTS_DIR cdc_skew_${ptr}.rpt]
        report_checks -to $pins -path_delay max -format end -group_count 1000 -endpoint_count 1 -digits 3 > $rpt
        set fh [open $rpt r]; set tab [read $fh]; close $fh
        set want [dict create]
        foreach p $pins { dict set want [string map {"\\" ""} [get_full_name $p]] 1 }
        set arrs {}
        foreach line [split $tab "\n"] {
            if {[regexp {^\s*(\S+)\s+\(\S+\)\s+(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+(-?[0-9]+\.[0-9]+)\s+\((MET|VIOLATED)\)\s*$} $line -> ep req act sl st]} {
                if {[dict exists $want [string map {"\\" ""} $ep]]} { lappend arrs $act }
            }
        }
        if {$nbits == 0 || [llength $arrs] != $nbits} {
            cdc_record_finding "bit-skew: pointer $ptr: [llength $arrs] of $nbits capture bits have a timed path (see $rpt)"
            puts [format "CDC-SKEW %-14s bits=%-2d UNCONSTRAINED" $ptr $nbits]
            continue
        }
        set sorted [lsort -real $arrs]
        set amin [lindex $sorted 0]
        set amax [lindex $sorted end]
        set skew [expr {$amax - $amin}]
        set verdict MET
        if {$skew > $limit} {
            set verdict VIOLATED
            cdc_record_finding "bit-skew VIOLATED: pointer $ptr ($fc -> $tc) skew [format %.3f $skew] ns > limit [format %.3f $limit] ns (see $rpt)"
        }
        puts [format "CDC-SKEW %-14s %s->%s bits=%-2d arr_min=%-7s arr_max=%-7s skew=%-6s limit=%-6s %s" \
            $ptr $fc $tc $nbits $amin $amax [format %.3f $skew] [format %.3f $limit] $verdict]
    }
}
cdc_skew_report

puts ""
puts "================================================================"
if {$::cdc_check_findings > 0} {
    puts "CDC-CHECK-RESULT: FAIL -- $::cdc_check_findings CDC finding(s):"
    foreach _m $::cdc_check_finding_msgs { puts "  - $_m" }
    puts "================================================================"
    exit 1
}
puts "CDC-CHECK-RESULT: PASS -- every CDC exception bound to a real object and every budget was met (corner $CORNER)."
puts "================================================================"
exit 0
