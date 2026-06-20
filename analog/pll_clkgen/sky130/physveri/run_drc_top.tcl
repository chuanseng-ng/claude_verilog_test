# Magic DRC script — top-level pll_clkgen_top and per-block checks
# Run with PDK_ROOT set so magicrc sources the correct sky130A.tcl

set MAG_DIR "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag"
set RPT_DIR "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/physveri"

# ------------------------------------------------------------------
# Helper: load cell, run drc(full), report count
# ------------------------------------------------------------------
proc run_drc_cell {cellname mag_dir rpt_dir} {
    set outfile [file join $rpt_dir "drc_${cellname}.rpt"]
    set fd [open $outfile w]

    puts $fd "=== DRC: $cellname ==="
    puts $fd "Tool: Magic + sky130A.tech drc(full)"
    puts $fd ""

    load [file join $mag_dir "${cellname}.mag"]
    select top cell
    drc euclidean on
    drc style drc(full)
    drc check
    drc catchup
    set count [drc list count total]
    puts $fd "drc_violations: $count"

    if {$count > 0} {
        puts $fd ""
        puts $fd "--- Violation Details ---"
        set why [drc listall why]
        foreach item $why {
            puts $fd "  $item"
        }
    } else {
        puts $fd "CLEAN -- 0 violations"
    }
    close $fd
    puts "DRC $cellname: $count violations"
    return $count
}

# ------------------------------------------------------------------
# Per-block DRC: complete analog cells
# ------------------------------------------------------------------
set total_analog 0
foreach cell {cp_pmos_array cp_nmos_array vco_stage_unit sky130_vco_layout sky130_lf_layout sky130_bias_layout} {
    set n [run_drc_cell $cell $MAG_DIR $RPT_DIR]
    incr total_analog $n
}

# ------------------------------------------------------------------
# Stub cells
# ------------------------------------------------------------------
set total_stub 0
foreach cell {sky130_pfd_layout sky130_fbdiv_layout sky130_postdiv_layout} {
    set n [run_drc_cell $cell $MAG_DIR $RPT_DIR]
    incr total_stub $n
}

# ------------------------------------------------------------------
# Top-level assembly
# ------------------------------------------------------------------
set n_top [run_drc_cell pll_clkgen_top $MAG_DIR $RPT_DIR]

# ------------------------------------------------------------------
# Summary file
# ------------------------------------------------------------------
set sumfd [open [file join $RPT_DIR "drc_summary.rpt"] w]
puts $sumfd "=== DRC SUMMARY: pll_clkgen_sky130 ==="
puts $sumfd "Tool: Magic 8.3 + sky130A.tech drc(full)"
puts $sumfd ""
puts $sumfd "Analog blocks (complete layout): $total_analog violations"
puts $sumfd "Stub blocks (bbox only):          $total_stub violations"
puts $sumfd "Top-level assembly:               $n_top violations"
puts $sumfd ""
if {$total_analog == 0} {
    puts $sumfd "ANALOG BLOCK DRC: PASS (0 violations)"
} else {
    puts $sumfd "ANALOG BLOCK DRC: FAIL ($total_analog violations)"
}
if {$n_top == 0} {
    puts $sumfd "TOP-LEVEL DRC:    PASS (0 violations)"
} else {
    puts $sumfd "TOP-LEVEL DRC:    FAIL ($n_top violations)"
}
close $sumfd

puts "--- DRC COMPLETE ---"
puts "Analog blocks: $total_analog | Stubs: $total_stub | Top: $n_top"
quit
