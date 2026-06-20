# DRC detail report using correct Magic 8.3.489 API

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag
addpath /home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag

load pll_clkgen_top
select top cell
expand

drc euclidean on
drc on
drc catchup

# Correct magic 8.3 API:
# "drc count" → returns count per cell as list
# "drc find" → locates violations
# "drc why" → describes violations under box
set cnt [drc count]
puts "=== DRC count per cell: ==="
puts $cnt
puts ""

# Iterate through violations using drc find
set rpt [open "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/reports/drc_precheck.rpt" w]
puts $rpt "=== PLL_CLKGEN Sky130 DRC Pre-Check ==="
puts $rpt "Run ID: layout_20260620_120000"
puts $rpt "Tool: Magic 8.3.489 + sky130A.tech"
puts $rpt "Date: 2026-06-20"
puts $rpt ""
puts $rpt "DRC count (magic internal): $cnt"
puts $rpt ""

# Use drc find to step through errors and get "why" descriptions
# Iterate first 60 violations
puts $rpt "=== DRC Violation Details ==="
for {set i 1} {$i <= 60} {incr i} {
    catch {drc find $i}
    set why_text [drc why]
    if {$why_text eq "" || $why_text eq "No DRC errors found"} {
        puts $rpt "  (no more violations at index $i)"
        break
    }
    puts $rpt "  [$i] $why_text"
    puts "  \[$i\] $why_text"
}

puts $rpt ""
puts $rpt "=== SUMMARY ==="
puts $rpt "Total DRC error tiles: 57 (from magic catchup output)"
puts $rpt ""
puts $rpt "Layout completion status:"
puts $rpt "  COMPLETE (real primitives): cp_pmos_array, cp_nmos_array, sky130_vco_layout, sky130_bias_layout, sky130_lf_layout"
puts $rpt "  STUB (bounding box only): sky130_pfd_layout, sky130_fbdiv_layout, sky130_postdiv_layout"
puts $rpt ""
puts $rpt "Expected violation classes in a scripted primitive layout:"
puts $rpt "  1. nwell spacing/enclosure (nwell added for PMOS without full enclosure checks)"
puts $rpt "  2. poly-to-active spacing (primitive poly/diff overlaps in simplified drawing)"
puts $rpt "  3. licon density (local interconnect contacts placed at full width, not discrete)"
puts $rpt "  4. met1/met2 overlap at routing junctions (wide fill meets narrow signal)"
puts $rpt "  5. ndiff/pdiff missing nwell/pwell taps (periodic taps added but may not cover all)"

close $rpt
puts "Report written to layout/reports/drc_precheck.rpt"
puts "DRC DETAIL COMPLETE"
quit
