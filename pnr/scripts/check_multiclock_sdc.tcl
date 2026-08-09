#=================================================================
# check_multiclock_sdc.tcl — prove the 2-domain SDC actually bound
#
# GH #96 / bead claude_verilog_test-8nz.
#
# WHY THIS EXISTS
# ---------------
# OpenSTA does NOT error when a create_clock's object list resolves to
# nothing. `create_clock -name cpu_clk -period 780 [get_ports cpu_clk_i]`
# against a netlist with no cpu_clk_i port silently produces a VIRTUAL
# cpu_clk: the clock object exists, reports its period, and shows up as a
# second "Clock:" block in OpenROAD's clock.rpt — but it has no source pin
# and no registers, so CTS builds no tree for it and every cpu-domain path
# goes untimed.
#
# Verified on 2026-08-05 against the run-14 netlist (which predates GH #93
# and has no cpu_clk_i port):
#     PORT-CHECK cpu_clk_i exists: 0
#     CLOCK cpu_clk is_virtual=1 nsources=0 registers=0
#     CLOCK sys_clk is_virtual=0 nsources=1 registers=43764
#
# So "clock.rpt contains two Clock: blocks" is NOT sufficient evidence of a
# real two-domain run. The binding checks below are. Run this against the
# synthesis netlist BEFORE committing to a multi-hour P&R.
#
# USAGE
#   MC_NETLIST=<path to .nl.v>  \
#   MC_SDC=<path to phase5_soc_multiclock.sdc> \
#   [MC_MACRO_DIR=<dir with macro .lib files>] \
#     sta -no_init -exit pnr/scripts/check_multiclock_sdc.tcl
#
# EXIT CODES
#   0  PASS — every expected clock is real, sourced and has registers
#   1  FAIL — a clock is virtual / unsourced / sink-less
#   2  SETUP ERROR — inputs missing
#
# Emits MC-CHECK-RESULT: PASS|FAIL and MC-CHECK-SETUP-ERROR markers so a
# calling Makefile can gate on grep as well as on the exit code (same
# belt-and-braces rationale as check_cdc_timing.tcl / bead dwp: OpenSTA
# batch mode does not reliably propagate a Tcl error into the process
# exit status).
#=================================================================

proc mc_env {name default} {
    if {[info exists ::env($name)] && $::env($name) ne ""} {
        return $::env($name)
    }
    return $default
}

# Repo root. Do NOT derive this from [info script]: under `sta -no_init -exit
# <file>` OpenSTA leaves it empty, so [file dirname [info script]] silently
# becomes "." and every default path is then computed relative to whatever
# directory the caller happened to be in. Walk up from the cwd looking for a
# marker file instead, and let MC_ROOT override.
proc mc_find_root {} {
    if {[info exists ::env(MC_ROOT)] && $::env(MC_ROOT) ne ""} {
        return [file normalize $::env(MC_ROOT)]
    }
    set dir [file normalize [pwd]]
    while {1} {
        if {[file exists [file join $dir pnr/scripts/check_multiclock_sdc.tcl]]} {
            return $dir
        }
        set parent [file dirname $dir]
        if {$parent eq $dir} { return "" }
        set dir $parent
    }
}

set ROOT [mc_find_root]
if {$ROOT eq ""} {
    puts "MC-CHECK-SETUP-ERROR: could not locate repo root from [pwd] — set MC_ROOT"
    exit 2
}
set NETLIST   [mc_env MC_NETLIST ""]
set SDC       [mc_env MC_SDC     [file join $ROOT pnr/asap7/soc/constraints/phase5_soc_multiclock.sdc]]
set MACRO_DIR [mc_env MC_MACRO_DIR [file join $ROOT pnr/asap7/soc/macro]]
set PDK_LIB   [mc_env MC_PDK_LIB /home/neuromorphic/pdk/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib]

# Clocks that must be REAL (not virtual), with the port each must bind to.
set EXPECTED {sys_clk clk_i cpu_clk cpu_clk_i}

if {$NETLIST eq "" || ![file exists $NETLIST]} {
    puts "MC-CHECK-SETUP-ERROR: netlist not found (set MC_NETLIST): '$NETLIST'"
    exit 2
}
if {![file exists $SDC]} {
    puts "MC-CHECK-SETUP-ERROR: SDC not found: '$SDC'"
    exit 2
}

foreach lib [concat \
        [glob -nocomplain [file join $PDK_LIB *.lib]] \
        [glob -nocomplain [file join $MACRO_DIR *.lib]] \
        [glob -nocomplain [file join $ROOT pnr/asap7 sram_*_TT_*.lib]]] {
    read_liberty $lib
}

read_verilog $NETLIST
link_design soc_top

if {[catch {read_sdc $SDC} err]} {
    puts "MC-CHECK-SETUP-ERROR: read_sdc aborted: $err"
    exit 2
}

set failures 0
foreach {clk_name port_name} $EXPECTED {
    set clk [get_clocks -quiet $clk_name]
    if {[llength $clk] == 0} {
        puts "MC-CHECK-FAIL: clock '$clk_name' does not exist at all"
        incr failures
        continue
    }

    set virtual [get_property $clk is_virtual]
    set sources [get_property $clk sources]
    set regs    [llength [all_registers -clock $clk]]
    set period  [get_property $clk period]
    set ports   [llength [get_ports -quiet $port_name]]

    puts [format "MC-CHECK-CLOCK: %-8s period=%-9s port(%s)=%d virtual=%s sources=%d registers=%d" \
              $clk_name $period $port_name $ports $virtual [llength $sources] $regs]
    foreach s $sources { puts "    source pin: [get_full_name $s]" }

    if {$ports == 0} {
        puts "MC-CHECK-FAIL: port '$port_name' absent from the netlist — '$clk_name' cannot bind"
        incr failures
    }
    if {$virtual != 0} {
        puts "MC-CHECK-FAIL: '$clk_name' is VIRTUAL — create_clock matched nothing, no CTS tree will be built"
        incr failures
    }
    if {[llength $sources] == 0} {
        puts "MC-CHECK-FAIL: '$clk_name' has no source pin"
        incr failures
    }
    if {$regs == 0} {
        puts "MC-CHECK-FAIL: '$clk_name' clocks zero registers — nothing in this domain is timed"
        incr failures
    }
}

if {$failures > 0} {
    puts "MC-CHECK-RESULT: FAIL ($failures problem(s))"
    exit 1
}
puts "MC-CHECK-RESULT: PASS — both domains are real, sourced and populated"
exit 0
