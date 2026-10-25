#!/bin/bash
# load_redhawk.sh -- RedHawk batch import of build/redhawk/sky130A_nom.tech + LEFs + libs + the Innovus floorplan DEF
# (needs `make load-innovus` first).  Expected: "Finish Importing Technology File" with no TEC errors; the design import
# reaches "126 nets, 2 instances".  A full `setup design` needs real PG shapes, pads and a Liberty/UPF PG-arc view -> part 2b.
set -u
HERE=${HERE:-$(cd "$(dirname "$0")/.." && pwd)}
B=$HERE/build; W=$B/work/redhawk; PK=${PDK_ROOT:?}/sky130A/libs.ref
REPO=${REPO:-$(cd "$HERE/../../../.." && pwd)}
mkdir -p "$W"; cd "$W" || exit 1
[ -s "$B/work/innovus/link_trivial_fp.def" ] || { echo "run 'make load-innovus' first (needs the DEF)"; exit 2; }
printf 'pad_vdd 100 100 met5 POWER\npad_vss 200 100 met5 GROUND\n' > pg.ploc
cat > link_trivial.gsr <<G
TECH_FILE $B/redhawk/sky130A_nom.tech
LEF_FILES {
 $PK/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef
 $PK/sky130_fd_sc_hd/lef/sky130_fd_sc_hd.lef
 $PK/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef
}
DEF_FILES {
 $B/work/innovus/link_trivial_fp.def
}
LIB_FILES {
 $PK/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib
 $REPO/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib
}
VDD_NETS {
 VPWR 1.8
 vccd1 1.8
}
GND_NETS {
 VGND 0
 vssd1 0
}
PAD_FILES {
 $W/pg.ploc
}
FREQUENCY 40e6
G
printf 'import gsr link_trivial.gsr\nsetup design\nexit\n' > run.tcl
rm -rf adsRpt
"$HERE/scripts/safe_run.sh" "$B/logs/redhawk_load.log" redhawk -b run.tcl
if grep -q "Finish Importing Technology File" "$B/logs/redhawk_load.log" && ! grep -qE "ERROR\(TEC-|ERROR\(GSR-|ERROR\(LEF-" "$B/logs/redhawk_load.log"; then
  echo "REDHAWK TECH+LEF IMPORT OK"; else echo "REDHAWK LOAD FAILED"; exit 1; fi
