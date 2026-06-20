# Magic extraction script: cp_pmos_array
# Produces cp_pmos_array.ext then ext2spice

set MAG_DIR "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/layout/mag"
set EXT_DIR "/home/neuromorphic/Downloads/Github/claude_verilog_test/analog/pll_clkgen/sky130/physveri"

load [file join $MAG_DIR "cp_pmos_array.mag"]
select top cell

# Extract
cd $EXT_DIR
extract do local
extract all

# Generate SPICE
ext2spice lvs
ext2spice format ngspice
ext2spice -o [file join $EXT_DIR "cp_pmos_array_layout.spice"]

puts "Extraction complete: cp_pmos_array"
quit
