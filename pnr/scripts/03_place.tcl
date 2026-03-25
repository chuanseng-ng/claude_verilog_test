#================================================================
# OpenROAD Flow — Stage 3: Placement
# Tool: OpenROAD (global + detailed placement)
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

set IN_DEF  "$RESULTS_DIR/${TOP_MODULE}_fp.def"
set OUT_DEF "$RESULTS_DIR/${TOP_MODULE}_place.def"

# Placement target density.
# Phase 3 has many flip-flops (cache arrays = FF-based SRAM).
# 0.55 gives ~15% headroom above the 45% floorplan utilisation for
# buffer insertion during CTS and routing detours.
set PLACE_DENSITY 0.55

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
# Read Netlist and Floorplan DEF
#----------------------------------------------------------------

puts "================================================================"
puts "Reading netlist and floorplan DEF"
puts "================================================================"

set NETLIST "$RESULTS_DIR/${TOP_MODULE}.v"
if {![file exists $NETLIST]} {
    error "Netlist not found: $NETLIST — run 'make synth' first."
}
if {![file exists $IN_DEF]} {
    error "Floorplan DEF not found: $IN_DEF — run 'make floorplan' first."
}

read_verilog $NETLIST
link_design $TOP_MODULE
read_def $IN_DEF

#----------------------------------------------------------------
# Read Timing Constraints
#----------------------------------------------------------------

puts "================================================================"
puts "Reading SDC: $SDC_FILE"
puts "================================================================"

read_sdc $SDC_FILE

#----------------------------------------------------------------
# Global Placement
#----------------------------------------------------------------

puts "================================================================"
puts "Running global placement (timing-driven, density $PLACE_DENSITY)"
puts "================================================================"

# global_placement uses RePlAce under the hood.
# -timing_driven: weights nets by criticality; essential at 75 MHz.
# -density: target cell density (matches PLACE_DENSITY variable).
# -pad_left / -pad_right: leave room for filler/decap cells.
global_placement \
    -timing_driven \
    -density $PLACE_DENSITY \
    -pad_left 2 \
    -pad_right 2

#----------------------------------------------------------------
# Repair Design Before Detailed Placement
# (handles max fanout, max slew, max cap violations)
#----------------------------------------------------------------

puts "================================================================"
puts "Repairing design (fanout, slew, cap)"
puts "================================================================"

# Estimate parasitics from placement (wire length) for repair decisions
estimate_parasitics -placement

repair_design \
    -max_wire_length 200

repair_timing \
    -setup \
    -max_buffer_percent 20

#----------------------------------------------------------------
# Detailed Placement
#----------------------------------------------------------------

puts "================================================================"
puts "Running detailed placement"
puts "================================================================"

detailed_placement

# Optimise placement further with timing awareness
optimize_mirroring

#----------------------------------------------------------------
# Filler Cell Insertion
#----------------------------------------------------------------

puts "================================================================"
puts "Inserting filler cells"
puts "================================================================"

# sky130_fd_sc_hd filler cells — ordered largest first for efficiency
filler_placement \
    sky130_fd_sc_hd__fill_8 \
    sky130_fd_sc_hd__fill_4 \
    sky130_fd_sc_hd__fill_2 \
    sky130_fd_sc_hd__fill_1

#----------------------------------------------------------------
# Legality Check
#----------------------------------------------------------------

puts "================================================================"
puts "Checking placement legality"
puts "================================================================"

check_placement -verbose

#----------------------------------------------------------------
# Reports
#----------------------------------------------------------------

puts "================================================================"
puts "Placement reports"
puts "================================================================"

estimate_parasitics -placement
report_design_area
report_cell_usage
report_checks -path_delay max -fields {slew cap input nets fanout} \
    -format full_clock_expanded \
    -digits 3 \
    > $REPORTS_DIR/place_timing.rpt
report_wns  >> $REPORTS_DIR/place_timing.rpt
report_tns  >> $REPORTS_DIR/place_timing.rpt

puts "Post-placement timing summary written to $REPORTS_DIR/place_timing.rpt"

#----------------------------------------------------------------
# Write Output DEF
#----------------------------------------------------------------

puts "================================================================"
puts "Writing placed DEF: $OUT_DEF"
puts "================================================================"

write_def $OUT_DEF

puts "Placement complete."

#----------------------------------------------------------------
# End of script
#----------------------------------------------------------------
