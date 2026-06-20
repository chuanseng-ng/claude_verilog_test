# ============================================================
# Pre-DRC Check Script v2 — sky130A
# Uses correct Magic 8.3.489 DRC API
# ============================================================

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag
addpath /home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag

# Load top cell
load pll_clkgen_top

# Turn DRC on and run
drc euclidean on
drc on
drc catchup

# Select all to get total box
select top cell
expand

# Get bounding box and run DRC over it
set bbox [box values]
puts "Cell bbox (internal units): $bbox"

# Run DRC check on the loaded cell
drc check

# Wait for DRC to complete
drc catchup

# Get violation count using correct API
set err_count [drc count total]
puts "=== DRC PRE-CHECK RESULTS ==="
puts "DRC violations (total): $err_count"

# Get per-rule violation list
puts "=== Violation details (first 50) ==="
set viol_list [drc list]
set idx 0
foreach v $viol_list {
    if {$idx >= 50} break
    puts "  $v"
    incr idx
}

# Write report
set rpt [open "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/reports/drc_precheck.rpt" w]
puts $rpt "=== PLL_CLKGEN Sky130 DRC Pre-Check ==="
puts $rpt "Run ID: layout_20260620_120000"
puts $rpt "Tool: Magic 8.3.489 + sky130A.tech"
puts $rpt "Date: 2026-06-20"
puts $rpt ""
puts $rpt "Total violations: $err_count"
puts $rpt ""
puts $rpt "Violation details:"
foreach v $viol_list {
    puts $rpt "  $v"
}
close $rpt

puts "Report: layout/reports/drc_precheck.rpt"
puts "DRC CHECK v2 COMPLETE"
quit
