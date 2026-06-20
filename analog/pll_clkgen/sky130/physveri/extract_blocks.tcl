# Magic ext2spice for block-level LVS
# Extracts CP (pmos+nmos arrays) and VCO layout cells

set MAG_DIR "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag"
set OUT_DIR "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/physveri"

# Must run from OUT_DIR so .ext files land there
cd $OUT_DIR

proc extract_cell {cellname mag_dir out_dir} {
    puts "--- Extracting: $cellname ---"
    load [file join $mag_dir "${cellname}.mag"]
    select top cell

    # Extraction settings for LVS
    extract do local
    extract no capacitance
    extract all

    # SPICE output (LVS style: no parasitics)
    ext2spice lvs
    ext2spice scale off
    ext2spice format ngspice
    ext2spice -o [file join $out_dir "${cellname}_layout.spice"]

    # Also write the .ext file name
    puts "Done: ${cellname}_layout.spice"
}

extract_cell cp_pmos_array $MAG_DIR $OUT_DIR
extract_cell cp_nmos_array $MAG_DIR $OUT_DIR
extract_cell vco_stage_unit $MAG_DIR $OUT_DIR
extract_cell sky130_vco_layout $MAG_DIR $OUT_DIR
extract_cell sky130_bias_layout $MAG_DIR $OUT_DIR

puts "=== All extractions complete ==="
quit
