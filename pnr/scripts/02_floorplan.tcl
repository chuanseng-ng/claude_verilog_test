#================================================================
# OpenROAD Flow — Stage 2: Floorplanning
# Tool: OpenROAD
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

# PDK root — same resolution logic as 01_synth.tcl
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

# Verify files exist
foreach f [list $TECH_LEF $CELL_LEF $LIB_TT] {
    if {![file exists $f]} {
        error "Required PDK file not found: $f"
    }
}

set NETLIST_FILE "$RESULTS_DIR/${TOP_MODULE}.v"
set OUT_DEF      "$RESULTS_DIR/${TOP_MODULE}_fp.def"

# Floorplan parameters
# Phase 3 cell estimate: ~15k-25k standard cells (pipeline + caches synthesised to FFs).
# Sky130 HD site: 0.46 µm wide × 2.72 µm tall.
# At 45% utilisation a 350×350 µm core gives sufficient headroom.
# Die margins: 10 µm on each side → die = 370×370 µm.
set DIE_AREA_LL_X 0.0
set DIE_AREA_LL_Y 0.0
set DIE_AREA_UR_X 370.0
set DIE_AREA_UR_Y 370.0
set CORE_MARGIN   10.0
set CORE_UTIL     0.45

file mkdir $RESULTS_DIR
file mkdir $REPORTS_DIR

#----------------------------------------------------------------
# Read Technology and Cell LEF
#----------------------------------------------------------------

puts "================================================================"
puts "Reading LEF files"
puts "================================================================"

read_lef $TECH_LEF
read_lef $CELL_LEF

#----------------------------------------------------------------
# Read Timing Library
#----------------------------------------------------------------

puts "================================================================"
puts "Reading liberty: $LIB_TT"
puts "================================================================"

read_liberty $LIB_TT

#----------------------------------------------------------------
# Read Gate-Level Netlist
#----------------------------------------------------------------

puts "================================================================"
puts "Reading gate-level netlist: $NETLIST_FILE"
puts "================================================================"

if {![file exists $NETLIST_FILE]} {
    error "Netlist not found: $NETLIST_FILE — run 'make synth' first."
}
read_verilog $NETLIST_FILE
link_design $TOP_MODULE

#----------------------------------------------------------------
# Read SDC Constraints
#----------------------------------------------------------------

puts "================================================================"
puts "Reading SDC constraints: $SDC_FILE"
puts "================================================================"

read_sdc $SDC_FILE

#----------------------------------------------------------------
# Floorplan Initialisation
#----------------------------------------------------------------

puts "================================================================"
puts "Initialising floorplan"
puts "  Die  : ${DIE_AREA_LL_X} ${DIE_AREA_LL_Y} ${DIE_AREA_UR_X} ${DIE_AREA_UR_Y} µm"
puts "  Core : margin ${CORE_MARGIN} µm, utilisation ${CORE_UTIL}"
puts "================================================================"

# initialize_floorplan sets the die area and derives the core area from the
# margin.  utilization drives cell density during placement (not floorplan
# itself, but recorded here for consistency with 03_place.tcl).
initialize_floorplan \
    -die_area  "$DIE_AREA_LL_X $DIE_AREA_LL_Y $DIE_AREA_UR_X $DIE_AREA_UR_Y" \
    -core_area "$CORE_MARGIN $CORE_MARGIN [expr {$DIE_AREA_UR_X - $CORE_MARGIN}] [expr {$DIE_AREA_UR_Y - $CORE_MARGIN}]" \
    -site      unithd

#----------------------------------------------------------------
# Insert Tap Cells and End Caps
#----------------------------------------------------------------

puts "================================================================"
puts "Inserting tap cells and end caps"
puts "================================================================"

# sky130_fd_sc_hd requires tap cells every ≤ 14.46 µm (31 pitches).
# Use 15 µm max distance to stay well within the rule.
tapcell \
    -tapcell_master sky130_fd_sc_hd__tapvpwrvgnd_1 \
    -endcap_master  sky130_fd_sc_hd__decap_3 \
    -distance 15

#----------------------------------------------------------------
# I/O Pin Placement
#----------------------------------------------------------------

puts "================================================================"
puts "Placing I/O pins"
puts "================================================================"

# Distribute all pins evenly around the four die edges.
# Fine-grained per-signal ordering is handled by the LibreLane
# pin_order.cfg; here we use a uniform spread for the OpenROAD flow.
place_pins \
    -hor_layers met3 \
    -ver_layers met2 \
    -random

#----------------------------------------------------------------
# Power Grid
#----------------------------------------------------------------

puts "================================================================"
puts "Building power grid"
puts "================================================================"

# Add VDD/VSS rings around the core boundary on met4/met5.
add_global_connection -net VDD -pin_pattern "^VPB$"  -power
add_global_connection -net VDD -pin_pattern "^VPWR$" -power
add_global_connection -net VSS -pin_pattern "^VNB$"  -ground
add_global_connection -net VSS -pin_pattern "^VGND$" -ground

# Core power ring on met4 (horizontal) and met5 (vertical).
# Ring width and spacing chosen to handle estimated ~5 mA peak current.
set_voltage_domain -name CORE -power VDD -ground VSS

define_pdn_grid -name core_grid -voltage_domains {CORE}

add_pdn_ring \
    -grid core_grid \
    -layers {met4 met5} \
    -widths {3.1 3.1} \
    -spacings {1.6 1.6} \
    -core_offset {2.0 2.0}

# Horizontal power straps on met4, vertical on met5
add_pdn_stripe \
    -grid core_grid \
    -layer met4 \
    -width 1.6 \
    -pitch 50.0 \
    -offset 10.0

add_pdn_stripe \
    -grid core_grid \
    -layer met5 \
    -width 1.6 \
    -pitch 50.0 \
    -offset 10.0

# met1 followpin rails — standard-cell VDD/VSS power rails
# (provides the met1 geometry that the connects below land on)
add_pdn_stripe \
    -grid core_grid \
    -layer met1 \
    -width 0.48 \
    -followpins

# Intermediate straps: met2 (horizontal) and met3 (vertical)
add_pdn_stripe \
    -grid core_grid \
    -layer met2 \
    -width 0.48 \
    -pitch 50.0 \
    -offset 10.0

add_pdn_stripe \
    -grid core_grid \
    -layer met3 \
    -width 0.48 \
    -pitch 50.0 \
    -offset 10.0

# Connect adjacent layer pairs: met1→met2→met3→met4→met5
add_pdn_connect \
    -grid core_grid \
    -layers {met1 met2}

add_pdn_connect \
    -grid core_grid \
    -layers {met2 met3}

add_pdn_connect \
    -grid core_grid \
    -layers {met3 met4}

add_pdn_connect \
    -grid core_grid \
    -layers {met4 met5}

pdngen

#----------------------------------------------------------------
# Reports
#----------------------------------------------------------------

puts "================================================================"
puts "Floorplan summary"
puts "================================================================"

report_design_area
report_cell_usage

#----------------------------------------------------------------
# Write Output
#----------------------------------------------------------------

puts "================================================================"
puts "Writing floorplan DEF: $OUT_DEF"
puts "================================================================"

write_def $OUT_DEF

puts "Floorplan complete."

#----------------------------------------------------------------
# End of script
#----------------------------------------------------------------
