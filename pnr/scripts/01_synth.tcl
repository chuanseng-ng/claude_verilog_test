#================================================================
# OpenROAD Flow — Stage 1: RTL Synthesis
# Tool: Yosys
# Phase: 3 (RV32I CPU + L1 I-Cache + L1 D-Cache)
# Target: 75 MHz (13.333 ns), Sky130 HD
#================================================================

#----------------------------------------------------------------
# Configuration — override via env vars if needed
#----------------------------------------------------------------

set TOP_MODULE   $::env(TOP_MODULE)
set CLOCK_PERIOD $::env(CLOCK_PERIOD)
set PDK          $::env(PDK)

set RTL_DIR      "../rtl"
set RESULTS_DIR  "results"
set REPORTS_DIR  "reports"
set CONSTR_DIR   "constraints"

# PDK paths — set SKY130_ROOT env var to override if PDK is not at the
# standard OpenROAD-flow-scripts location.
# Typical locations:
#   /usr/share/pdk/sky130A                    (volare / apt installs)
#   /usr/local/share/pdk/sky130A              (manual PDK builds)
#   ~/pdk/sky130A                              (user-local)
#   /usr/share/skywater-pdk/libraries/...     (some distros)
#
if {[info exists ::env(SKY130_ROOT)]} {
    set SKY130_ROOT $::env(SKY130_ROOT)
} elseif {[file exists /usr/share/pdk/sky130A]} {
    set SKY130_ROOT /usr/share/pdk/sky130A
} elseif {[file exists /usr/local/share/pdk/sky130A]} {
    set SKY130_ROOT /usr/local/share/pdk/sky130A
} else {
    error "Sky130 PDK not found. Set the SKY130_ROOT environment variable to the sky130A directory."
}

set LIB_TT  "$SKY130_ROOT/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"

# Verify the liberty file exists before proceeding
if {![file exists $LIB_TT]} {
    error "Liberty file not found: $LIB_TT\nCheck SKY130_ROOT=$SKY130_ROOT"
}

set NETLIST_FILE  "$RESULTS_DIR/${TOP_MODULE}.v"
set JSON_FILE     "$RESULTS_DIR/${TOP_MODULE}.json"
set AREA_RPT      "$REPORTS_DIR/synth_area.rpt"
set HIER_RPT      "$REPORTS_DIR/synth_hierarchy.rpt"
set STAT_RPT      "$REPORTS_DIR/synth_stat.rpt"

#----------------------------------------------------------------
# Utility: ensure output directories exist
#----------------------------------------------------------------

file mkdir $RESULTS_DIR
file mkdir $REPORTS_DIR

#----------------------------------------------------------------
# Read Technology Library
#----------------------------------------------------------------

puts "================================================================"
puts "Reading Sky130 liberty: $LIB_TT"
puts "================================================================"

read_liberty -lib $LIB_TT

#----------------------------------------------------------------
# Read RTL (SystemVerilog packages first, then modules)
# Order matches dependency graph: pkg → leaf modules → top
#----------------------------------------------------------------

puts "================================================================"
puts "Reading RTL files for $TOP_MODULE"
puts "================================================================"

# --- Packages (must precede all modules that import them) ---
read_verilog -sv $RTL_DIR/cpu/core/rv32i_pipeline_pkg.sv
read_verilog -sv $RTL_DIR/mem/rv32i_cache_pkg.sv

# --- Leaf modules (no inter-module dependencies) ---
read_verilog -sv $RTL_DIR/cpu/core/rv32i_alu.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_branch_comp.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_imm_gen.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_regfile.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_decode.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_forwarding_unit.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_hazard_unit.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_interrupt_ctrl.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_csr_file.sv
read_verilog -sv $RTL_DIR/cpu/core/rv32i_control.sv

# --- Pipeline stages (depend on pipeline_pkg) ---
read_verilog -sv $RTL_DIR/cpu/core/pipeline/rv32i_pipeline_if.sv
read_verilog -sv $RTL_DIR/cpu/core/pipeline/rv32i_pipeline_id.sv
read_verilog -sv $RTL_DIR/cpu/core/pipeline/rv32i_pipeline_ex.sv
read_verilog -sv $RTL_DIR/cpu/core/pipeline/rv32i_pipeline_mem.sv
read_verilog -sv $RTL_DIR/cpu/core/pipeline/rv32i_pipeline_wb.sv

# --- SRAM blackbox stubs (must precede cache RTL so hierarchy -check finds them) ---
# For the Sky130 flow, also pass -DSRAM_SKY130 to select the Sky130 macro variant.
if {[info exists ::env(PDK)] && ($::env(PDK) eq "sky130A" || $::env(PDK) eq "sky130")} {
    set SRAM_DEFINE "-DSRAM_SKY130"
    set SKY130_SRAM_STUB "librelane/sky130_sram_1kbyte_1rw1r_32x256_8_stub.v"
    if {[file exists $SKY130_SRAM_STUB]} {
        read_verilog $SKY130_SRAM_STUB
        puts "Loaded Sky130 SRAM blackbox stub: $SKY130_SRAM_STUB"
    } else {
        puts "WARNING: Sky130 SRAM stub not found at $SKY130_SRAM_STUB"
    }
} else {
    set SRAM_DEFINE ""
    set FREEPDK45_STUB "freepdk45/sram_1rw_256x32_freepdk45_stub.v"
    if {[file exists $FREEPDK45_STUB]} {
        read_verilog $FREEPDK45_STUB
        puts "Loaded FreePDK45 SRAM blackbox stub: $FREEPDK45_STUB"
    } else {
        puts "WARNING: FreePDK45 SRAM stub not found at $FREEPDK45_STUB"
    }
}

# --- Cache subsystem (depend on cache_pkg) ---
read_verilog -sv {*}[split $SRAM_DEFINE] $RTL_DIR/mem/rv32i_icache.sv
read_verilog -sv {*}[split $SRAM_DEFINE] $RTL_DIR/mem/rv32i_dcache.sv
read_verilog -sv $RTL_DIR/mem/rv32i_cache_arbiter.sv

# --- Core integrations ---
read_verilog -sv $RTL_DIR/cpu/core/rv32i_core.sv
read_verilog -sv $RTL_DIR/cpu/rv32i_cpu_top.sv

puts "RTL read complete."

#----------------------------------------------------------------
# Elaboration and Hierarchy Check
#----------------------------------------------------------------

puts "================================================================"
puts "Elaborating design — top: $TOP_MODULE"
puts "================================================================"

hierarchy -top $TOP_MODULE -check

#----------------------------------------------------------------
# High-Level Synthesis Passes
#----------------------------------------------------------------

puts "================================================================"
puts "Running synthesis passes"
puts "================================================================"

# Translate processes (always blocks, initial blocks)
procs

# Optimise away constants and simplify expressions
opt -nodffe_prep

# Extract and optimise finite state machines
fsm

# Optimise after FSM extraction
opt

# Memory mapping: map behavioural memories to technology cells.
# SRAM macro instances (sky130_sram_1kbyte_1rw1r_32x256_8,
# sram_1rw_256x32_freepdk45) are preserved as blackbox instances because
# their stub modules were read above; only remaining inferred memories are
# mapped to FFs by memory_map.
memory -nomap
memory_share
memory_map

# Final optimisation after memory mapping
opt

#----------------------------------------------------------------
# Technology Mapping
#----------------------------------------------------------------

puts "================================================================"
puts "Technology mapping to sky130_fd_sc_hd"
puts "================================================================"

# Flatten the hierarchy so OpenROAD gets a single flat netlist.
# This is the standard practice for the OpenROAD standalone flow; the
# LibreLane flow preserves hierarchy via its own elaboration.
synth -top $TOP_MODULE -flatten

# Map flip-flops to sky130_fd_sc_hd D flip-flops
dfflibmap -liberty $LIB_TT

# ABC: combinational optimisation + technology mapping with timing target.
# -D sets the target period in picoseconds (13333 ps = 13.333 ns = 75 MHz).
abc -liberty $LIB_TT -D [expr {int($CLOCK_PERIOD * 1000)}]

# Remove dangling wires and unused cells
clean

#----------------------------------------------------------------
# Sanity checks
#----------------------------------------------------------------

puts "================================================================"
puts "Design statistics"
puts "================================================================"

tee -o $STAT_RPT stat -top $TOP_MODULE -liberty $LIB_TT

#----------------------------------------------------------------
# Reports
#----------------------------------------------------------------

puts "================================================================"
puts "Writing reports"
puts "================================================================"

# Chip area (mapped cell count + area estimate)
tee -o $AREA_RPT stat -top $TOP_MODULE -liberty $LIB_TT

# Hierarchy report (useful for floorplan instance-path lookup)
tee -o $HIER_RPT hierarchy -check

#----------------------------------------------------------------
# Write Outputs
#----------------------------------------------------------------

puts "================================================================"
puts "Writing gate-level outputs"
puts "================================================================"

# Gate-level Verilog — suppress Yosys-internal attributes so the file
# is consumable by OpenROAD's Verilog reader without warnings.
write_verilog -noattr -noexpr -nohex -nodec $NETLIST_FILE

# JSON representation (backup; useful for inspection with netlistsvg etc.)
write_json $JSON_FILE

puts "================================================================"
puts "Synthesis complete."
puts "  Netlist : $NETLIST_FILE"
puts "  JSON    : $JSON_FILE"
puts "  Reports : $AREA_RPT, $HIER_RPT, $STAT_RPT"
puts "================================================================"

#----------------------------------------------------------------
# End of script
#----------------------------------------------------------------
