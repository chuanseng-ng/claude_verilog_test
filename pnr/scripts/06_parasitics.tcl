#================================================================
# OpenROAD Flow — Stage 6: Parasitic Extraction
# Tool: OpenRCX (integrated in OpenROAD)
# Phase: 3 (RV32I CPU + L1 I-Cache + L1 D-Cache)
# Target: 75 MHz (13.333 ns), Sky130 HD
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

# OpenRCX extraction rules for sky130.
# The .rules file is provided by the sky130 PDK in the OpenRCX package.
# Typical paths (one of these should exist):
#   $SKY130_ROOT/libs.ref/sky130_fd_sc_hd/rcx/sky130_openrcx.rules
#   $SKY130_ROOT/libs.tech/openrcx/sky130.rules
set RCX_RULES_CANDIDATES [list \
    "$SKY130_ROOT/libs.ref/sky130_fd_sc_hd/rcx/sky130_openrcx.rules" \
    "$SKY130_ROOT/libs.tech/openrcx/sky130.rules" \
    "$SKY130_ROOT/libs.tech/openrcx/sky130A.rules" \
]

set RCX_RULES ""
foreach candidate $RCX_RULES_CANDIDATES {
    if {[file exists $candidate]} {
        set RCX_RULES $candidate
        break
    }
}

set IN_DEF   "$RESULTS_DIR/${TOP_MODULE}_route.def"
set OUT_SPEF "$RESULTS_DIR/${TOP_MODULE}.spef"

file mkdir $RESULTS_DIR
file mkdir $REPORTS_DIR

#----------------------------------------------------------------
# Read LEF and Liberty
#----------------------------------------------------------------

puts "================================================================"
puts "Reading LEF files"
puts "================================================================"

read_lef $TECH_LEF
read_lef $CELL_LEF
read_liberty $LIB_TT

#----------------------------------------------------------------
# Read Netlist and Routed DEF
#----------------------------------------------------------------

puts "================================================================"
puts "Reading netlist and routed DEF"
puts "================================================================"

set NETLIST "$RESULTS_DIR/${TOP_MODULE}.v"
if {![file exists $NETLIST]} {
    error "Netlist not found: $NETLIST"
}
if {![file exists $IN_DEF]} {
    error "Routed DEF not found: $IN_DEF — run 'make route' first."
}

read_verilog $NETLIST
link_design $TOP_MODULE
read_def $IN_DEF
read_sdc $SDC_FILE

#----------------------------------------------------------------
# OpenRCX Parasitic Extraction
#----------------------------------------------------------------

puts "================================================================"
puts "Running OpenRCX parasitic extraction"
puts "================================================================"

if {$RCX_RULES ne ""} {
    puts "  Using extraction rules: $RCX_RULES"
    define_process_corner -ext_model_index 0 $RCX_RULES
    extract_parasitics \
        -ext_model_index 0 \
        -coupling_threshold 0.1 \
        -cc_model 10
} else {
    # Fallback: use the built-in wire RC model when no rules file is found.
    # This is less accurate but allows the flow to proceed.
    puts "WARNING: No OpenRCX rules file found under $SKY130_ROOT"
    puts "         Falling back to layer RC estimates."
    puts "         Set SKY130_ROOT correctly or install sky130 OpenRCX rules."
    set_wire_rc -signal -layer met2
    set_wire_rc -clock  -layer met3
    estimate_parasitics -detailed_routing
}

#----------------------------------------------------------------
# Write SPEF
#----------------------------------------------------------------

puts "================================================================"
puts "Writing SPEF: $OUT_SPEF"
puts "================================================================"

if {$RCX_RULES ne ""} {
    write_spef $OUT_SPEF
} else {
    # When using estimated parasitics, there is no SPEF to write.
    # The STA script will use in-memory parasitics directly via read_sdc.
    puts "NOTE: Estimated parasitics are in-memory only (no SPEF file)."
    puts "      STA (07_sta.tcl) will use layer-RC estimates."
    set OUT_SPEF ""
}

#----------------------------------------------------------------
# Reports
#----------------------------------------------------------------

puts "================================================================"
puts "Parasitic extraction summary"
puts "================================================================"

if {$RCX_RULES ne ""} {
    report_net_wire_length > $REPORTS_DIR/parasitics_summary.rpt
    puts "Parasitic summary written to $REPORTS_DIR/parasitics_summary.rpt"
}

puts "================================================================"
if {$OUT_SPEF ne ""} {
    puts "Parasitic extraction complete."
    puts "  SPEF: $OUT_SPEF"
} else {
    puts "Parasitic extraction complete (estimated, no SPEF)."
}
puts "================================================================"

#----------------------------------------------------------------
# End of script
#----------------------------------------------------------------
