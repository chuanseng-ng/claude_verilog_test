# ============================================================
# Pre-DRC Check Script — sky130A
# Stage: layout_check
# Tool: Magic 8.3.489
# run_id: layout_20260620_120000
#
# Runs magic's built-in DRC against sky130A.tech rules
# and writes a report to:
#   analog/pll_clkgen/sky130/layout/reports/drc_precheck.rpt
# ============================================================

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag
addpath /home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag

# Load the top cell
load pll_clkgen_top

# Run full DRC
drc on
drc check
drc catchup

# Get violation count
set count [drc listcount]
set violations [drc list count total]

puts "=== DRC PRE-CHECK RESULTS ==="
puts "Total DRC violations: $count"

# Write to report file
set rpt [open "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/reports/drc_precheck.rpt" w]
puts $rpt "=== PLL_CLKGEN Sky130 DRC Pre-Check ==="
puts $rpt "Run ID: layout_20260620_120000"
puts $rpt "Tool: Magic 8.3.489 + sky130A.tech"
puts $rpt "Date: 2026-06-20"
puts $rpt ""
puts $rpt "Total violations: $count"
puts $rpt ""
puts $rpt "Violation list:"
foreach v [drc list] {
    puts $rpt "  $v"
}
close $rpt

puts "DRC report written to layout/reports/drc_precheck.rpt"
puts "DRC CHECK COMPLETE"
quit
