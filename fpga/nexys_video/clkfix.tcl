# clkfix.tcl -- put every PMU clock-gate BUFGCE in PARALLEL with the ungated BUFG (bead hlrm.2, decision #1).
#
# rv32i_clock_gate (FPGA_BUFGCE arm) is `BUFGCE (.I(clk) ...)` and its `clk` is the SoC's core_clk / cpu_core_clk, i.e. the
# OUTPUT of the board top's BUFG. Left alone that is a BUFG -> BUFGCE cascade: the gated domain would be one full clock
# buffer later than the ungated one (the bus -> GPU hold failure measured on Kintex-7, WHS -0.312 ns, 118 endpoints).
# RTL cannot reach the pre-BUFG net without a new port on soc_top, so this script re-sources each BUFGCE.I pin from the
# MMCM output that feeds the driving BUFG. The ungated BUFG and the BUFGCE then both hang off the same MMCM output.
#
# Run after synth_design, before opt_design. Prints one `NV-CLKFIX` line per BUFGCE; a BUFGCE whose I pin is not driven
# by a BUFG (a constant, or a LUT = a clock mux that survived constant propagation) is reported as SKIP, not rewired.

proc nv_bufgce_parallel_fix {} {
    set done 0
    set skipped 0
    foreach c [get_cells -hierarchical -quiet -filter {REF_NAME == BUFGCE}] {
        set ipin [get_pins -quiet $c/I]
        set net  [get_nets -quiet -of_objects $ipin]
        if {$net eq ""} { puts "NV-CLKFIX SKIP $c: I pin unconnected"; incr skipped; continue }
        # driver of the net: the (single) leaf output pin
        set drv [get_pins -quiet -of_objects $net -filter {DIRECTION == OUT && IS_LEAF}]
        if {[llength $drv] != 1} {
            puts "NV-CLKFIX SKIP $c: net $net has [llength $drv] leaf drivers (constant or port)"
            incr skipped; continue
        }
        set dcell [get_cells -of_objects $drv]
        set dref  [get_property REF_NAME $dcell]
        if {$dref ne "BUFG"} {
            puts "NV-CLKFIX SKIP $c: I is driven by $dref ($dcell), not a BUFG"
            incr skipped; continue
        }
        set raw [get_nets -of_objects [get_pins $dcell/I]]
        disconnect_net -net $net -objects $ipin
        connect_net -hierarchical -net $raw -objects $ipin
        puts "NV-CLKFIX OK   $c: I re-sourced from $raw (parallel with $dcell)"
        incr done
    }
    puts "NV-CLKFIX summary: rewired=$done skipped=$skipped"
    return $done
}
