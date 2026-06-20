# Netgen LVS script — block-level verification
# The sky130A_setup.tcl is passed to the lvs command, NOT sourced first.

set SETUP "/home/neuromorphic/.volare/sky130A/libs.tech/netgen/sky130A_setup.tcl"
set CIRC  "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/circuit"
set PV    "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/physveri"

# ------------------------------------------------------------------
# LVS: CP PMOS array
# ------------------------------------------------------------------
puts "--- Running LVS: cp_pmos_array vs sky130_cp ---"
set rpt [file join $PV "lvs_cp_pmos.rpt"]
lvs \
    "$PV/cp_pmos_array_layout.spice cp_pmos_array" \
    "$CIRC/sky130_cp.sp sky130_cp" \
    $SETUP \
    $rpt
puts "LVS cp_pmos done -> $rpt"

# ------------------------------------------------------------------
# LVS: VCO layout vs schematic
# ------------------------------------------------------------------
puts "--- Running LVS: sky130_vco_layout vs sky130_vco ---"
set rpt [file join $PV "lvs_vco.rpt"]
lvs \
    "$PV/sky130_vco_layout_layout.spice sky130_vco_layout" \
    "$CIRC/sky130_vco.sp sky130_vco" \
    $SETUP \
    $rpt
puts "LVS vco done -> $rpt"

puts "=== Netgen LVS runs complete ==="
quit
