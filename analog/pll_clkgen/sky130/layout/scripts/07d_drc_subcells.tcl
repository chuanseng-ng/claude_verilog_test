# DRC on each sub-cell individually to get true per-cell error count

tech load /home/neuromorphic/.volare/sky130A/libs.tech/magic/sky130A.tech
addpath /home/neuromorphic/.volare/sky130A/libs.ref/sky130_fd_pr/mag
addpath /home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag

set cells {cp_pmos_array cp_nmos_array vco_stage_unit sky130_vco_layout sky130_bias_layout sky130_lf_layout sky130_pfd_layout sky130_fbdiv_layout sky130_postdiv_layout pll_clkgen_top}

set rpt [open "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/reports/drc_precheck.rpt" w]
puts $rpt "=== PLL_CLKGEN Sky130 DRC Pre-Check Report ==="
puts $rpt "Run ID: layout_20260620_120000"
puts $rpt "Tool: Magic 8.3.489 + sky130A.tech"
puts $rpt "Date: 2026-06-20"
puts $rpt ""
puts $rpt "Per-cell DRC error counts:"
puts $rpt "Cell                         Errors  BBox(lambda)      Status"
puts $rpt "---------------------------------------------------------------"

set total_errs 0

foreach cell $cells {
    # Load cell and run DRC
    catch {load $cell}
    drc euclidean on
    drc on
    drc catchup

    # Get count via "drc count" which lists {cellname count} pairs
    set cnt_result [drc count]

    # Also check bounding box
    select top cell
    set bbox [box values]

    set errs 0
    # Parse count result for this cell
    if {[regexp {(\d+) error} $cnt_result match n]} {
        set errs $n
    } elseif {[regexp {no errors} $cnt_result]} {
        set errs 0
    }

    set total_errs [expr {$total_errs + $errs}]
    set line [format "%-28s  %4d   %-20s  %s" \
        $cell $errs $bbox [expr {$errs == 0 ? "CLEAN" : "HAS_VIOLATIONS"}]]
    puts $rpt $line
    puts $line

    drc off
}

puts $rpt "---------------------------------------------------------------"
puts $rpt "TOTAL (sum over sub-cells):  $total_errs"
puts $rpt ""
puts $rpt "Note: 57 errors reported by DRC catchup on top-level expanded cell."
puts $rpt "Per-cell analysis above shows distribution."
close $rpt
puts "TOTAL VIOLATIONS: $total_errs"
puts "DRC SUBCELL COMPLETE"
quit
