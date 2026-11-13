# 05_route.tcl - Stage 5 of the OpenROAD flow: routing (FastRoute for global routing, TritonRoute for detailed routing, Sky130 HD)
#
# Scope: make target route runs it from pnr/Makefile.
# Contents: runs global routing, then detailed routing.
# Inputs: environment variables TOP_MODULE and SDC_FILE. SKY130_ROOT overrides the PDK location.
# User rules: set_routing_layers allows met1 to met4 for signals and met3 to met4 for clocks.
# Doc: tm:pd:scripts-05-route-tcl

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

set IN_DEF  "$RESULTS_DIR/${TOP_MODULE}_cts.def"
set OUT_DEF "$RESULTS_DIR/${TOP_MODULE}_route.def"

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
# Read Netlist and CTS DEF
#----------------------------------------------------------------

puts "================================================================"
puts "Reading netlist and CTS DEF"
puts "================================================================"

set NETLIST "$RESULTS_DIR/${TOP_MODULE}.v"
if {![file exists $NETLIST]} {
    error "Netlist not found: $NETLIST"
}
if {![file exists $IN_DEF]} {
    error "CTS DEF not found: $IN_DEF — run 'make cts' first."
}

read_verilog $NETLIST
link_design $TOP_MODULE
read_def $IN_DEF
read_sdc $SDC_FILE

#----------------------------------------------------------------
# Wire RC Model
# Use met3 as representative intermediate layer for estimates
#----------------------------------------------------------------

set_wire_rc -signal -layer met2
set_wire_rc -clock  -layer met3

estimate_parasitics -placement

#----------------------------------------------------------------
# Global Routing (FastRoute). Sky130 HD has five routing layers plus li1, which is local only and not used for global routing.
# met1, met3 and met5 are horizontal. met2 and met4 are vertical. met4 and met5 carry power.
# Signal routing uses met1 to met4. met4 is reserved for power straps but is available for signal where the straps do not conflict.
# set_routing_layers below allows met1 to met4 for signals and met3 to met4 for clocks.
#----------------------------------------------------------------

puts "================================================================"
puts "Running global routing (FastRoute)"
puts "================================================================"

set_global_routing_layer_adjustment met1 0.5
set_global_routing_layer_adjustment met2 0.3
set_global_routing_layer_adjustment met3 0.3
set_global_routing_layer_adjustment met4 0.4

set_routing_layers \
    -signal "met1-met4" \
    -clock  "met3-met4"

# Allow 10% routing overflow before treating it as an error.
# Overflow is normal at this stage; detailed routing resolves it.
global_route \
    -guide_file $RESULTS_DIR/${TOP_MODULE}.guide \
    -congestion_iterations 30 \
    -congestion_report_file $REPORTS_DIR/congestion.rpt \
    -verbose

#----------------------------------------------------------------
# Estimate post-global-route parasitics for a pre-route timing check
#----------------------------------------------------------------

estimate_parasitics -global_routing

report_checks -path_delay max -digits 3 \
    > $REPORTS_DIR/groute_timing.rpt
report_wns  >> $REPORTS_DIR/groute_timing.rpt
report_tns  >> $REPORTS_DIR/groute_timing.rpt

#----------------------------------------------------------------
# Detailed Routing (TritonRoute)
#----------------------------------------------------------------

puts "================================================================"
puts "Running detailed routing (TritonRoute)"
puts "================================================================"

detailed_route \
    -input_guide_file $RESULTS_DIR/${TOP_MODULE}.guide \
    -output_maze_file $RESULTS_DIR/${TOP_MODULE}_maze.log \
    -output_drc_file  $REPORTS_DIR/drc.rpt \
    -bottom_routing_layer met1 \
    -top_routing_layer    met4 \
    -verbose 1

#----------------------------------------------------------------
# Post-Route Repair
# Fix any remaining antenna violations and DRC issues.
#----------------------------------------------------------------

puts "================================================================"
puts "Post-route repair"
puts "================================================================"

repair_antennas sky130_fd_sc_hd__diode_2 \
    -iterations 5

check_antennas -report_file $REPORTS_DIR/antenna.rpt

#----------------------------------------------------------------
# DRC Check
#----------------------------------------------------------------

puts "================================================================"
puts "Running design rule check"
puts "================================================================"

# check_drc reports violations; non-zero count is logged but does not
# abort the flow so that the DEF can be inspected in KLayout.
check_drc -output_file $REPORTS_DIR/drc_final.rpt

#----------------------------------------------------------------
# Reports
#----------------------------------------------------------------

puts "================================================================"
puts "Post-route reports"
puts "================================================================"

report_design_area         >  $REPORTS_DIR/route_area.rpt
report_cell_usage          >> $REPORTS_DIR/route_area.rpt
report_net_wire_length     >  $REPORTS_DIR/wire_length.rpt

puts "Post-route area written to $REPORTS_DIR/route_area.rpt"
puts "DRC report at $REPORTS_DIR/drc_final.rpt"
puts "Antenna report at $REPORTS_DIR/antenna.rpt"
puts "Congestion report at $REPORTS_DIR/congestion.rpt"

#----------------------------------------------------------------
# Write Output DEF
#----------------------------------------------------------------

puts "================================================================"
puts "Writing routed DEF: $OUT_DEF"
puts "================================================================"

write_def $OUT_DEF

puts "Routing complete."

#----------------------------------------------------------------
# End of script
#----------------------------------------------------------------
