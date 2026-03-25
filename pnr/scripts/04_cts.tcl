#================================================================
# OpenROAD Flow — Stage 4: Clock Tree Synthesis
# Tool: TritonCTS (integrated in OpenROAD)
# Phase: 3 (RV32I CPU + L1 I-Cache + L1 D-Cache)
# Target: 75 MHz (13.333 ns), skew < 100 ps, Sky130 HD
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

set IN_DEF  "$RESULTS_DIR/${TOP_MODULE}_place.def"
set OUT_DEF "$RESULTS_DIR/${TOP_MODULE}_cts.def"

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
# Read Netlist and Placed DEF
#----------------------------------------------------------------

puts "================================================================"
puts "Reading netlist and placed DEF"
puts "================================================================"

set NETLIST "$RESULTS_DIR/${TOP_MODULE}.v"
if {![file exists $NETLIST]} {
    error "Netlist not found: $NETLIST — run 'make synth' first."
}
if {![file exists $IN_DEF]} {
    error "Placed DEF not found: $IN_DEF — run 'make place' first."
}

read_verilog $NETLIST
link_design $TOP_MODULE
read_def $IN_DEF

#----------------------------------------------------------------
# Read SDC Constraints
#----------------------------------------------------------------

puts "================================================================"
puts "Reading SDC: $SDC_FILE"
puts "================================================================"

read_sdc $SDC_FILE

#----------------------------------------------------------------
# Configure Clock Buffers / Inverters for TritonCTS
#
# Sky130 HD clock-capable buffers/inverters — ordered by drive strength.
# CLKBUF cells are characterised for clock use (lower skew contribution).
# BUF cells are used as fallback when CLKBUF cells run out.
#----------------------------------------------------------------

set_wire_rc -clock -layer met3

clock_tree_synthesis \
    -root_buf  sky130_fd_sc_hd__clkbuf_16 \
    -buf_list  {sky130_fd_sc_hd__clkbuf_2
                sky130_fd_sc_hd__clkbuf_4
                sky130_fd_sc_hd__clkbuf_8
                sky130_fd_sc_hd__clkbuf_16} \
    -sink_clustering_enable \
    -sink_clustering_size 30 \
    -sink_clustering_max_diameter 60 \
    -distance_between_buffers 100

#----------------------------------------------------------------
# Post-CTS repair of timing hold violations
# (setup violations are addressed here too before routing)
#----------------------------------------------------------------

puts "================================================================"
puts "Post-CTS timing repair"
puts "================================================================"

estimate_parasitics -placement

# Tighten clock uncertainty post-CTS per SDC_TIMING_SPEC.md guidance
# (pre-CTS uses 0.5 ns, post-CTS tightens to 0.3 ns)
set_propagated_clock [all_clocks]
set_clock_uncertainty 0.3 [get_clocks clk_i]

repair_timing \
    -setup \
    -hold  \
    -hold_margin 0.1 \
    -max_buffer_percent 20

detailed_placement

check_placement -verbose

#----------------------------------------------------------------
# Reports
#----------------------------------------------------------------

puts "================================================================"
puts "CTS reports"
puts "================================================================"

report_cts \
    > $REPORTS_DIR/cts.rpt

report_clock_skew \
    >> $REPORTS_DIR/cts.rpt

estimate_parasitics -placement
report_checks -path_delay max -fields {slew cap input nets fanout} \
    -format full_clock_expanded \
    -digits 3 \
    > $REPORTS_DIR/cts_timing_setup.rpt
report_checks -path_delay min -fields {slew cap input nets fanout} \
    -format full_clock_expanded \
    -digits 3 \
    >> $REPORTS_DIR/cts_timing_setup.rpt

report_wns  > $REPORTS_DIR/cts_wns.rpt
report_tns >> $REPORTS_DIR/cts_wns.rpt

puts "CTS reports written to $REPORTS_DIR/cts*.rpt"

#----------------------------------------------------------------
# Write Output DEF
#----------------------------------------------------------------

puts "================================================================"
puts "Writing CTS DEF: $OUT_DEF"
puts "================================================================"

write_def $OUT_DEF

puts "CTS complete."

#----------------------------------------------------------------
# End of script
#----------------------------------------------------------------
