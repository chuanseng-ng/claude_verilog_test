#================================================================
# OpenROAD Flow — Stage 7: Static Timing Analysis
# Tool: OpenSTA (invoked as 'sta' standalone binary)
# Phase: 3 (RV32I CPU + L1 I-Cache + L1 D-Cache)
# Target: 75 MHz (13.333 ns), Sky130 HD
# Sign-off corners: TT/SS/FF @ nominal voltage
#================================================================
#
# This script is designed to be run with the standalone 'sta' binary
# (OpenSTA), not via openroad.  The Makefile target 'sta' invokes:
#   sta scripts/07_sta.tcl | tee logs/sta.log
#
# The script checks for a SPEF from 06_parasitics.tcl; if not found it
# falls back to reading the routed DEF and using layer-RC estimates so
# that the flow can proceed even without a full RC extraction.
#================================================================

#----------------------------------------------------------------
# Configuration
#----------------------------------------------------------------

# OpenSTA does not inherit Makefile env vars directly; the Makefile
# exports them, so they are accessible via $::env().
set TOP_MODULE  $::env(TOP_MODULE)
set SDC_FILE    $::env(SDC_FILE)

set RESULTS_DIR "results"
set REPORTS_DIR "reports"

if {[info exists ::env(SKY130_ROOT)]} {
    set SKY130_ROOT $::env(SKY130_ROOT)
} elseif {[file exists /usr/share/pdk/sky130A]} {
    set SKY130_ROOT /usr/share/pdk/sky130A
} elseif {[file exists /usr/local/share/pdk/sky130A]} {
    set SKY130_ROOT /usr/local/share/pdk/sky130A
} else {
    error "Sky130 PDK not found. Set SKY130_ROOT environment variable."
}

set SCL_LIB_DIR "$SKY130_ROOT/libs.ref/sky130_fd_sc_hd/lib"

# Use TT corner for primary analysis; add SS/FF if available.
set LIB_TT "$SCL_LIB_DIR/sky130_fd_sc_hd__tt_025C_1v80.lib"
set LIB_SS "$SCL_LIB_DIR/sky130_fd_sc_hd__ss_100C_1v60.lib"
set LIB_FF "$SCL_LIB_DIR/sky130_fd_sc_hd__ff_n40C_1v95.lib"

set NETLIST  "$RESULTS_DIR/${TOP_MODULE}.v"
set SPEF     "$RESULTS_DIR/${TOP_MODULE}.spef"

file mkdir $REPORTS_DIR

#----------------------------------------------------------------
# Read Liberty Files
#----------------------------------------------------------------

puts "================================================================"
puts "Reading liberty files"
puts "================================================================"

if {![file exists $LIB_TT]} {
    error "Liberty file not found: $LIB_TT"
}

read_liberty $LIB_TT

if {[file exists $LIB_SS]} {
    read_liberty $LIB_SS
    puts "  SS corner: $LIB_SS"
} else {
    puts "  SS corner not found — skipping (single-corner analysis)"
}

if {[file exists $LIB_FF]} {
    read_liberty $LIB_FF
    puts "  FF corner: $LIB_FF"
} else {
    puts "  FF corner not found — skipping"
}

#----------------------------------------------------------------
# Read Gate-Level Netlist
#----------------------------------------------------------------

puts "================================================================"
puts "Reading gate-level netlist: $NETLIST"
puts "================================================================"

if {![file exists $NETLIST]} {
    error "Netlist not found: $NETLIST — run 'make synth' first."
}

read_verilog $NETLIST
link_design $TOP_MODULE

#----------------------------------------------------------------
# Read SDC Constraints
# Post-CTS: use tighter clock uncertainty (0.3 ns)
#----------------------------------------------------------------

puts "================================================================"
puts "Reading SDC: $SDC_FILE"
puts "================================================================"

read_sdc $SDC_FILE

# Override pre-CTS uncertainty with post-CTS value
set_clock_uncertainty 0.3 [get_clocks clk_i]
set_propagated_clock [all_clocks]

#----------------------------------------------------------------
# Read Parasitics (SPEF if available, layer-RC otherwise)
#----------------------------------------------------------------

puts "================================================================"
puts "Reading parasitics"
puts "================================================================"

if {[file exists $SPEF]} {
    puts "  Reading SPEF: $SPEF"
    read_spef $SPEF
} else {
    puts "  SPEF not found: $SPEF"
    puts "  Using layer-RC wire model for estimation."
    # These RC values match the Sky130 process corner at TT/25°C/1.8V.
    # Values from the sky130 OpenROAD platform defaults.
    set_wire_rc -signal -resistance 1.45e-04 -capacitance 1.32e-04
    set_wire_rc -clock  -resistance 1.45e-04 -capacitance 1.32e-04
}

#----------------------------------------------------------------
# Setup Timing Analysis
#----------------------------------------------------------------

puts "================================================================"
puts "Setup (max-delay) timing analysis"
puts "================================================================"

# Report the 20 worst setup paths — full_clock_expanded shows CTS buffers
report_checks \
    -path_delay max \
    -fields {slew cap input nets fanout} \
    -format full_clock_expanded \
    -digits 3 \
    -nworst 20 \
    > $REPORTS_DIR/timing_setup.rpt

report_wns >> $REPORTS_DIR/timing_setup.rpt
report_tns >> $REPORTS_DIR/timing_setup.rpt

puts "Setup timing written to $REPORTS_DIR/timing_setup.rpt"

#----------------------------------------------------------------
# Hold Timing Analysis
#----------------------------------------------------------------

puts "================================================================"
puts "Hold (min-delay) timing analysis"
puts "================================================================"

report_checks \
    -path_delay min \
    -fields {slew cap input nets fanout} \
    -format full_clock_expanded \
    -digits 3 \
    -nworst 20 \
    > $REPORTS_DIR/timing_hold.rpt

report_wns -min >> $REPORTS_DIR/timing_hold.rpt

puts "Hold timing written to $REPORTS_DIR/timing_hold.rpt"

#----------------------------------------------------------------
# Clock Skew and Tree Report
#----------------------------------------------------------------

puts "================================================================"
puts "Clock skew report"
puts "================================================================"

report_clock_skew \
    > $REPORTS_DIR/clock_skew.rpt

report_clock_properties \
    >> $REPORTS_DIR/clock_skew.rpt

puts "Clock report written to $REPORTS_DIR/clock_skew.rpt"

#----------------------------------------------------------------
# Critical Path Analysis
#
# Report unconstrained paths and paths by path group so the engineer
# can see which pipeline stages are the bottleneck.
#----------------------------------------------------------------

puts "================================================================"
puts "Path group analysis"
puts "================================================================"

# Pipeline critical paths (PIPELINE group defined in SDC)
report_checks \
    -group_count 5 \
    -path_delay max \
    -format full_clock_expanded \
    -digits 3 \
    > $REPORTS_DIR/timing_critical_paths.rpt

report_checks \
    -unconstrained \
    -format full_clock_expanded \
    >> $REPORTS_DIR/timing_critical_paths.rpt

puts "Critical path report written to $REPORTS_DIR/timing_critical_paths.rpt"

#----------------------------------------------------------------
# Per-instance Timing Summary
#----------------------------------------------------------------

puts "================================================================"
puts "Instance-level timing summary"
puts "================================================================"

report_check_types \
    -max_slew \
    -max_cap \
    -max_fanout \
    -violators \
    > $REPORTS_DIR/timing_violations.rpt

puts "Constraint violation summary written to $REPORTS_DIR/timing_violations.rpt"

#----------------------------------------------------------------
# Final Summary to stdout
#----------------------------------------------------------------

puts ""
puts "================================================================"
puts "TIMING SIGN-OFF SUMMARY — Phase 3, 75 MHz (13.333 ns)"
puts "================================================================"
puts ""
puts "--- Setup (max) ---"
report_wns
report_tns
puts ""
puts "--- Hold (min) ---"
report_wns -min
puts ""
puts "--- Clock ---"
report_clock_skew
puts ""
puts "Reports written to $REPORTS_DIR/timing_*.rpt"
puts "================================================================"

#----------------------------------------------------------------
# End of script
#----------------------------------------------------------------
