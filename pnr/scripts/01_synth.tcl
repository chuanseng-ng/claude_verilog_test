#================================================================
# OpenROAD Flow - Stage 1: Synthesis
# Tool: Yosys
# Input: RTL (SystemVerilog)
# Output: Gate-level netlist
#================================================================

#----------------------------------------------------------------
# Configuration
#----------------------------------------------------------------

# Get environment variables (set by Makefile)
set TOP_MODULE   $::env(TOP_MODULE)
set CLOCK_PERIOD $::env(CLOCK_PERIOD)
set PDK          $::env(PDK)

# Directories
set RTL_DIR      "../rtl"
set RESULTS_DIR  "results"
set REPORTS_DIR  "reports"
set CONSTR_DIR   "constraints"

# Output files
set NETLIST_FILE "$RESULTS_DIR/${TOP_MODULE}.v"
set JSON_FILE    "$RESULTS_DIR/${TOP_MODULE}.json"

#----------------------------------------------------------------
# Read RTL
#----------------------------------------------------------------

puts "================================================================"
puts "Reading RTL files for $TOP_MODULE"
puts "================================================================"

# Read all SystemVerilog files
# NOTE: Update these paths once RTL is implemented in Phase 1
# read_verilog -sv $RTL_DIR/cpu/rv32i_cpu_top.sv
# read_verilog -sv $RTL_DIR/cpu/core/rv32i_core.sv
# read_verilog -sv $RTL_DIR/cpu/core/rv32i_control.sv
# read_verilog -sv $RTL_DIR/cpu/core/rv32i_decode.sv
# read_verilog -sv $RTL_DIR/cpu/core/rv32i_alu.sv
# read_verilog -sv $RTL_DIR/cpu/core/rv32i_regfile.sv
# read_verilog -sv $RTL_DIR/cpu/core/rv32i_imm_gen.sv

# Placeholder for Phase 0 (no RTL yet)
puts "WARNING: RTL files not yet available (Phase 0 complete, Phase 1 pending)"
puts "This script is a template for Phase 1 synthesis."

#----------------------------------------------------------------
# Read Technology Library
#----------------------------------------------------------------

puts "================================================================"
puts "Reading technology library: $PDK"
puts "================================================================"

# Sky130 PDK
if {$PDK == "sky130"} {
    # TODO: Add actual Sky130 library paths
    # read_liberty -lib sky130_fd_sc_hd__tt_025C_1v80.lib
    puts "Sky130 PDK selected (library paths to be configured)"
}

# ASAP7 PDK
if {$PDK == "asap7"} {
    # TODO: Add actual ASAP7 library paths
    # read_liberty -lib asap7_tt_1p0v_25c.lib
    puts "ASAP7 PDK selected (library paths to be configured)"
}

#----------------------------------------------------------------
# Hierarchy and Elaboration
#----------------------------------------------------------------

puts "================================================================"
puts "Elaborating design"
puts "================================================================"

# Set top module
# hierarchy -top $TOP_MODULE -check

#----------------------------------------------------------------
# High-Level Synthesis
#----------------------------------------------------------------

puts "================================================================"
puts "Running high-level synthesis"
puts "================================================================"

# Translate processes (always blocks)
# proc

# Optimize
# opt

# FSM extraction and optimization
# fsm
# opt

# Memory mapping
# memory
# opt

#----------------------------------------------------------------
# Technology Mapping
#----------------------------------------------------------------

puts "================================================================"
puts "Technology mapping to $PDK"
puts "================================================================"

# Flatten design (or preserve hierarchy)
# flatten
# opt

# Technology mapping
# techmap
# opt

# ABC optimization for timing
# abc -liberty sky130_fd_sc_hd__tt_025C_1v80.lib

# Clean up
# clean

#----------------------------------------------------------------
# Reports
#----------------------------------------------------------------

puts "================================================================"
puts "Generating reports"
puts "================================================================"

# Area report
# tee -o $REPORTS_DIR/synth_area.rpt stat -top $TOP_MODULE

# Hierarchy report
# tee -o $REPORTS_DIR/synth_hierarchy.rpt hierarchy -check

#----------------------------------------------------------------
# Write Outputs
#----------------------------------------------------------------

puts "================================================================"
puts "Writing outputs"
puts "================================================================"

# Write gate-level Verilog
# write_verilog -noattr -noexpr -nohex $NETLIST_FILE

# Write JSON (for OpenROAD)
# write_json $JSON_FILE

puts "Synthesis complete."
puts "Netlist: $NETLIST_FILE"
puts "JSON: $JSON_FILE"

#----------------------------------------------------------------
# End of Script
#----------------------------------------------------------------
