#================================================================
# Load a finished Sky130 SoC (or CPU macro) LibreLane run into OpenSTA for ad-hoc post-route timing queries.
# bead claude_verilog_test-j41m.8 (DFT Stage 2): used for the functional view vs scan view hold/setup comparison.
#
#   STA_RUN_DIR   (required) run directory
#   STA_CORNER    default nom_tt_025C_1v80 (one of {nom,min,max}_{tt_025C_1v80,ss_100C_1v60,ff_n40C_1v95})
#   STA_VIEW      func (default) | scan.  scan sets CVT_SDC_SCAN_VIEW=1 before sourcing the SDC, i.e. the gray-pointer
#                 hold exemption is NOT applied (sky130_soc.sdc, bead j41m.5).
#   STA_DESIGN    default soc_top  (rv32i_cpu_top for the CPU macro)
#   STA_SDC       default pnr/sky130/soc/constraints/sky130_soc.sdc (macro: pnr/sky130/cpu/constraints/sky130_cpu.sdc)
#   STA_MACRO_LIBS  Tcl list of macro Liberty files for the corner (default: the committed SoC macro views)
#   STA_PNR       pnr/ directory (override if the script is reached through a symlink)
#   STA_CMDS      Tcl file sourced after the design is loaded (reports)
#
#   sta -no_init -exit pnr/scripts/sta_load_sky130_soc.tcl      (inside the librelane nix-shell)
#
# Clocks are propagated. No exceptions are added here; the SDC is the project's own.
#================================================================
proc env_or {n d} { return [expr {[info exists ::env($n)] && $::env($n) ne "" ? $::env($n) : $d}] }

set RUN_DIR [file normalize $::env(STA_RUN_DIR)]
set CORNER  [env_or STA_CORNER nom_tt_025C_1v80]
set VIEW    [env_or STA_VIEW func]
set DESIGN  [env_or STA_DESIGN soc_top]
set PDK_ROOT [env_or PDK_ROOT /home/neuromorphic/.ciel/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af]
set SCRIPT_DIR [file dirname [file normalize [info script]]]
set PNR [env_or STA_PNR [file normalize [file join $SCRIPT_DIR ..]]]
if {![regexp {^(nom|min|max)_(tt_025C_1v80|ss_100C_1v60|ff_n40C_1v95)$} $CORNER -> RC PVT]} { puts "ERROR: bad corner $CORNER"; exit 2 }

if {$DESIGN eq "soc_top"} {
    set SDC [env_or STA_SDC [file join $PNR sky130 soc constraints sky130_soc.sdc]]
    set MLIBS [env_or STA_MACRO_LIBS [list \
        [file join $PNR sky130 cpu macro rv32i_cpu_top__${CORNER}.lib] \
        [file join $PNR sky130 soc macro sky130_sram_4kbyte_1rw1r_32x1024_8_TT_1p8V_25C.lib]]]
} else {
    set SDC [env_or STA_SDC [file join $PNR sky130 cpu constraints sky130_cpu.sdc]]
    set MLIBS [env_or STA_MACRO_LIBS [list [file join $PNR sky130 cpu pdk_lib_patched sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib]]]
}

read_liberty [file join $PDK_ROOT sky130A libs.ref sky130_fd_sc_hd lib sky130_fd_sc_hd__${PVT}.lib]
foreach l $MLIBS { read_liberty $l }

set nl [env_or STA_NETLIST ""]
if {$nl eq ""} {
    set c [concat [glob -nocomplain $RUN_DIR/final/nl/$DESIGN.nl.v] [glob -nocomplain $RUN_DIR/*-openroad-fillinsertion/$DESIGN.nl.v]]
    if {[llength $c] == 0} { puts "ERROR: no netlist under $RUN_DIR"; exit 2 }
    set nl [lindex $c 0]
}
read_verilog $nl
link_design $DESIGN

set spef [env_or STA_SPEF ""]
if {$spef eq ""} {
    set c [glob -nocomplain $RUN_DIR/*-openroad-rcx/$RC/$DESIGN.$RC.spef]
    if {[llength $c] > 0} { set spef [lindex $c 0] }
}
if {$spef ne "" && $spef ne "none"} { read_spef $spef } else { puts "WARN: no SPEF, wire parasitics ignored" }

if {$VIEW eq "scan"} { set ::env(CVT_SDC_SCAN_VIEW) 1 } else { catch {unset ::env(CVT_SDC_SCAN_VIEW)} }
read_sdc $SDC
set_propagated_clock [all_clocks]
puts "STA-LOAD: design=$DESIGN corner=$CORNER view=$VIEW netlist=$nl spef=$spef"

if {[info exists ::env(STA_CMDS)] && $::env(STA_CMDS) ne ""} { source $::env(STA_CMDS) }
exit 0
