#=================================================================
# report_per_clock_timing.tcl — per-clock-domain WNS / TNS / skew
#
# GH #96 / bead claude_verilog_test-8nz.
#
# WHY: LibreLane's final/metrics.json carries only GLOBAL timing keys
# (timing__setup__ws, timing__setup__tns, ...). On a multi-domain design the
# global WNS is the minimum across every domain, so a single failing domain
# masks a passing one entirely and the metrics file cannot answer "did
# sys_clk close?" and "did cpu_clk close?" separately. OpenSTA's report_tns
# takes no -path_group, but report_checks/find_timing_paths do, and the
# default path groups are named after the clocks.
#
# USAGE
#   PC_RUN_DIR=/nobackup/asap7_soc_runs/RUN_...  \
#   [PC_SDC=<sdc>] [PC_CLOCKS="sys_clk cpu_clk"] \
#     sta -no_init -exit pnr/scripts/report_per_clock_timing.tcl
#
# Defaults to the run's own final/sdc/soc_top.sdc — the constraints the run
# was actually implemented with, not whatever is currently checked out.
#=================================================================

proc pc_env {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
    return $default
}

# Do NOT derive paths from [info script]: OpenSTA leaves it empty under
# `sta -no_init -exit <file>`. See check_multiclock_sdc.tcl for the same trap.
proc pc_find_root {} {
    if {[info exists ::env(PC_ROOT)] && $::env(PC_ROOT) ne ""} {
        return [file normalize $::env(PC_ROOT)]
    }
    set dir [file normalize [pwd]]
    while {1} {
        if {[file exists [file join $dir pnr/scripts/report_per_clock_timing.tcl]]} { return $dir }
        set parent [file dirname $dir]
        if {$parent eq $dir} { return "" }
        set dir $parent
    }
}

set ROOT    [pc_find_root]
set RUN_DIR [pc_env PC_RUN_DIR ""]
set CLOCKS  [pc_env PC_CLOCKS "sys_clk cpu_clk"]
set PDK_LIB [pc_env PC_PDK_LIB /home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib]

if {$ROOT eq ""} { puts "PC-SETUP-ERROR: repo root not found; set PC_ROOT"; exit 2 }
if {$RUN_DIR eq "" || ![file isdirectory $RUN_DIR]} {
    puts "PC-SETUP-ERROR: set PC_RUN_DIR to a completed run directory"; exit 2
}

set NETLIST $RUN_DIR/final/nl/soc_top.nl.v
set SDC     [pc_env PC_SDC $RUN_DIR/final/sdc/soc_top.sdc]
foreach f [list $NETLIST $SDC] {
    if {![file exists $f]} { puts "PC-SETUP-ERROR: missing $f"; exit 2 }
}

foreach lib [concat \
        [glob -nocomplain [file join $PDK_LIB *.lib]] \
        [glob -nocomplain [file join $ROOT pnr/asap7/soc/macro *.lib]] \
        [glob -nocomplain [file join $ROOT pnr/asap7 sram_*_TT_*.lib]]] {
    read_liberty $lib
}

read_verilog $NETLIST
link_design soc_top
read_sdc $SDC

puts "PC-RUN: $RUN_DIR"
puts "PC-SDC: $SDC"

foreach clk $CLOCKS {
    set c [get_clocks -quiet $clk]
    if {[llength $c] == 0} { puts "PC-CLOCK $clk: ABSENT"; continue }

    set period [get_property $c period]
    set nregs  [llength [all_registers -clock $c]]

    # WNS: worst setup slack inside this path group.
    set wns "n/a"
    set paths [find_timing_paths -path_group $clk -path_delay max \
                   -sort_by_slack -group_count 1]
    if {[llength $paths] > 0} {
        set wns [get_property [lindex $paths 0] slack]
    }

    # TNS: sum of NEGATIVE slacks in the group, one path per endpoint so a
    # single bad endpoint is not counted once per path through it.
    set tns 0.0
    set nviol 0
    foreach p [find_timing_paths -path_group $clk -path_delay max \
                   -slack_max 0 -group_count 1000000 -unique_paths_to_endpoint] {
        set s [get_property $p slack]
        if {$s < 0} { set tns [expr {$tns + $s}]; incr nviol }
    }

    set hold "n/a"
    set hpaths [find_timing_paths -path_group $clk -path_delay min \
                    -sort_by_slack -group_count 1]
    if {[llength $hpaths] > 0} { set hold [get_property [lindex $hpaths 0] slack] }

    puts "-----------------------------------------------------------"
    puts [format "PC-CLOCK %-8s period=%s ps registers=%d" $clk $period $nregs]
    puts [format "PC-SETUP %-8s WNS=%s ps  TNS=%.2f ps  violating_endpoints=%d" \
              $clk $wns $tns $nviol]
    puts [format "PC-HOLD  %-8s WNS=%s ps" $clk $hold]
    if {$wns ne "n/a" && $wns < 0} {
        puts [format "PC-FMAX  %-8s achieved=%.2f MHz (period %.2f ps) vs target %.2f MHz" \
                  $clk [expr {1e6/($period - $wns)}] [expr {$period - $wns}] [expr {1e6/$period}]]
        puts "PC-RESULT $clk: FAIL (misses its target period)"
    } else {
        puts [format "PC-FMAX  %-8s target %.2f MHz MET" $clk [expr {1e6/$period}]]
        puts "PC-RESULT $clk: PASS"
    }
    puts "--- worst 5 setup paths ---"
    report_checks -path_group $clk -path_delay max -sort_by_slack \
        -group_count 5 -format short
}

puts "-----------------------------------------------------------"
report_clock_skew -setup
exit 0
