#================================================================
# OpenROAD Flow — Stage 8: Power Analysis
# Tool: OpenROAD power estimation
# Phase: 3 (RV32I CPU + L1 I-Cache + L1 D-Cache)
# Target: 75 MHz (13.333 ns), Sky130 HD
#================================================================
#
# Power estimation approach:
#   1. Static (leakage) power — from liberty data, no activity needed.
#   2. Dynamic (switching + internal) power — from switching activity.
#
# Activity source priority:
#   a. VCD file pointed to by VCD_FILE env var (from cocotb simulation)
#   b. Default toggle rate of 0.20 (20%) applied globally
#
# The 20% toggle rate is conservative for a running pipeline; it errs
# on the side of overestimating dynamic power, which is safe for
# thermal and IR-drop budgeting.
#================================================================

#----------------------------------------------------------------
# Configuration
#----------------------------------------------------------------

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

set SCL_DIR  "$SKY130_ROOT/libs.ref/sky130_fd_sc_hd"
set TECH_LEF "$SCL_DIR/techlef/sky130_fd_sc_hd__nom.tlef"
set CELL_LEF "$SCL_DIR/lef/sky130_fd_sc_hd.lef"
set LIB_TT   "$SCL_DIR/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"

set NETLIST  "$RESULTS_DIR/${TOP_MODULE}.v"
set SPEF     "$RESULTS_DIR/${TOP_MODULE}.spef"
set ROUTE_DEF "$RESULTS_DIR/${TOP_MODULE}_route.def"

# Optional VCD for activity-based power estimation
set VCD_FILE ""
if {[info exists ::env(VCD_FILE)] && [file exists $::env(VCD_FILE)]} {
    set VCD_FILE $::env(VCD_FILE)
}

# Default toggle rate (used when no VCD is provided)
set DEFAULT_TOGGLE_RATE 0.20

file mkdir $REPORTS_DIR

#----------------------------------------------------------------
# Read LEF and Liberty
#----------------------------------------------------------------

puts "================================================================"
puts "Reading LEF and liberty"
puts "================================================================"

read_lef $TECH_LEF
read_lef $CELL_LEF
read_liberty $LIB_TT

# SRAM macro LEF and Liberty — required for accurate leakage and dynamic power of
# sky130_sram_1kbyte_1rw1r_32x256_8 instances (I-cache and D-cache).
set SRAM_LEF "$SKY130_ROOT/libs.ref/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef"
set SRAM_LIB "$SKY130_ROOT/libs.ref/sky130_sram_macros/lib/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib"
if {[file exists $SRAM_LEF]} {
    read_lef $SRAM_LEF
    puts "Loaded SRAM LEF: $SRAM_LEF"
} else {
    puts "WARNING: SRAM LEF not found: $SRAM_LEF"
}
if {[file exists $SRAM_LIB]} {
    read_liberty $SRAM_LIB
    puts "Loaded SRAM Liberty: $SRAM_LIB"
} else {
    puts "WARNING: SRAM Liberty not found: $SRAM_LIB — SRAM leakage excluded from power report"
}

#----------------------------------------------------------------
# Read Netlist and DEF
#----------------------------------------------------------------

puts "================================================================"
puts "Reading netlist: $NETLIST"
puts "================================================================"

if {![file exists $NETLIST]} {
    error "Netlist not found: $NETLIST — run 'make synth' first."
}

read_verilog $NETLIST
link_design $TOP_MODULE

# Prefer the routed DEF; fall back to placed DEF if route hasn't run yet.
if {[file exists $ROUTE_DEF]} {
    puts "  Reading routed DEF: $ROUTE_DEF"
    read_def $ROUTE_DEF
} elseif {[file exists "$RESULTS_DIR/${TOP_MODULE}_cts.def"]} {
    set CTS_DEF "$RESULTS_DIR/${TOP_MODULE}_cts.def"
    puts "  WARNING: Routed DEF not found. Using CTS DEF: $CTS_DEF"
    read_def $CTS_DEF
} else {
    error "No DEF found in $RESULTS_DIR — run at least 'make cts' first."
}

read_sdc $SDC_FILE

#----------------------------------------------------------------
# Read Parasitics
#----------------------------------------------------------------

puts "================================================================"
puts "Reading parasitics"
puts "================================================================"

if {[file exists $SPEF]} {
    puts "  Reading SPEF: $SPEF"
    read_spef $SPEF
} else {
    puts "  SPEF not found. Using layer-RC estimates."
    set_wire_rc -signal -layer met2
    set_wire_rc -clock  -layer met3
    estimate_parasitics -global_routing
}

#----------------------------------------------------------------
# Switching Activity
#----------------------------------------------------------------

puts "================================================================"
puts "Setting switching activity"
puts "================================================================"

if {$VCD_FILE ne ""} {
    puts "  Reading VCD: $VCD_FILE"
    # read_vcd annotates toggle rates from simulation directly onto nets.
    # Scope must match the testbench instantiation path (adjust as needed).
    read_vcd $VCD_FILE -scope "tb_rv32i_cpu_top/u_dut"
    puts "  Activity loaded from VCD."
} else {
    puts "  No VCD file provided. Applying default toggle rate: $DEFAULT_TOGGLE_RATE"
    puts "  (Set VCD_FILE env var to use simulation activity data)"
    # set_power_activity applies a uniform toggle rate to all registers.
    # -input = input ports toggle rate; -input_activity for sequential.
    set_power_activity -global \
        -activity $DEFAULT_TOGGLE_RATE \
        -duty 0.5
}

#----------------------------------------------------------------
# Power Analysis
#----------------------------------------------------------------

puts "================================================================"
puts "Running power analysis"
puts "================================================================"

# report_power writes a hierarchical breakdown to stdout and the report file.
# Columns: internal, switching, leakage, total (in mW for this design)
set PWR_RPT $REPORTS_DIR/power.rpt

# Initialise the report file with the flat-power section header, then append
# each report so earlier content is never overwritten.
set f [open $PWR_RPT "w"]
puts $f "--- Total power (flat) ---"
close $f
redirect -append -file $PWR_RPT { report_power }

set f [open $PWR_RPT "a"]
puts $f ""
puts $f "--- Hierarchical power breakdown ---"
close $f
redirect -append -file $PWR_RPT { report_power -hierarchy }

# Also report to stdout
report_power
report_power -hierarchy

#----------------------------------------------------------------
# IR Drop Analysis (PDN)
#
# analyse_power_grid requires a VDD supply location specification.
# If the Vsrc file does not exist we skip IR-drop analysis gracefully.
# Create pnr/config/vsrc.tcl with set_pdnsim_net_voltage calls to enable.
#----------------------------------------------------------------

set VSRC_TCL "config/vsrc.tcl"
if {[file exists $VSRC_TCL]} {
    puts "================================================================"
    puts "Running IR drop analysis"
    puts "================================================================"
    source $VSRC_TCL
    analyze_power_grid \
        -net VDD \
        -outfile $REPORTS_DIR/ir_drop.rpt
    puts "IR drop report: $REPORTS_DIR/ir_drop.rpt"
} else {
    puts "================================================================"
    puts "IR drop analysis skipped (config/vsrc.tcl not found)"
    puts "To enable: create config/vsrc.tcl with set_pdnsim_net_voltage"
    puts "================================================================"
}

#----------------------------------------------------------------
# Final Summary to stdout
#----------------------------------------------------------------

puts ""
puts "================================================================"
puts "POWER SIGN-OFF SUMMARY — Phase 3, 75 MHz"
puts "  VDD = 1.8 V, corner = TT/25°C/1.8V"
if {$VCD_FILE ne ""} {
    puts "  Activity source: VCD ($VCD_FILE)"
} else {
    puts "  Activity source: uniform $DEFAULT_TOGGLE_RATE toggle rate"
}
puts "================================================================"
report_power
puts ""
puts "Full report written to $PWR_RPT"
puts "================================================================"

#----------------------------------------------------------------
# End of script
#----------------------------------------------------------------
