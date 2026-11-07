#!/bin/bash
# gen_cmd.sh <arm> <corner> [outdir]   -- write the Quantus command file for one (arm, corner).
# Settings mirror the StarRC run (signoff/starrc/scripts/gen_cmd.sh): same DEF, same LEF set, RC coupled,
# coupling threshold 0.1 fF absolute / 0 relative, 25 C.  Only the extractor and its qrcTechFile differ.
# QUANTUS_TECHDIR overrides the qrcTechFile directory (default pdk/sky130/build/qrc/<corner>).
set -eu
arm=$1; corner=$2
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
. "$ROOT/pnr/commercial/signoff/starrc/scripts/arms.sh"
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
out=${3:-$ROOT/pnr/commercial/signoff/quantus/runs/${arm}_${corner}}
mkdir -p "$out"
PDKB=$ROOT/pnr/commercial/pdk/sky130/build
case $corner in nom) TLEF=$SKY130_HD_TLEF ;; min) TLEF=$SKY130_HD_TLEF_MIN ;; max) TLEF=$SKY130_HD_TLEF_MAX ;; *) exit 2 ;; esac
TECHDIR=${QUANTUS_TECHDIR:-$PDKB/qrc/$corner}
# arm DEF overrides (arms.sh holds the StarRC DEFs; the openroad DEF is the same file).
cat > "$out/lefs.txt" <<LEFS
$TLEF
$SKY130_HD_LEF
$SKY130_HD/lef/sky130_ef_sc_hd.lef
$SKY130_SRAM_1K_LEF
$ROOT/pnr/commercial/signoff/starrc/scripts/icc2_via_names.lef
LEFS
echo "DEFINE ${QUANTUS_TECHNAME:-sky130A_$corner} $TECHDIR" > "$out/techlib.defs"   # cds.lib-style technology library
LMAP=$(grep -v '^#' "$PDKB/tech/map/quantus_lef2ict.map" | awk 'NF==2{printf "%s %s ", $1, $2}')   # tech-LEF layer -> ICT layer pairs (only "via -> via1" differs)
cat > "$out/quantus.cmd" <<CMD
input_db -type def \\
  -design_file $ROOT/$(arm_def "$arm") \\
  -lef_file_list_file $out/lefs.txt
extraction_setup \\
  -technology_layer_map $LMAP
process_technology \\
  -technology_library_file $out/techlib.defs \\
  -technology_name ${QUANTUS_TECHNAME:-sky130A_$corner} \\
  -temperature 25
extract -selection all -type rc_coupled
filter_coupling_cap \\
  -coupling_cap_threshold_absolute 0.1 \\
  -coupling_cap_threshold_relative 0 \\
  -total_cap_threshold 0
output_setup \\
  -directory_name $out \\
  -file_name rv32i_cpu_top.$corner \\
  -temporary_directory_name $out/qtmp
output_db -type spef -subtype STANDARD
log_file -file_name $out/quantus_cmd.log
CMD
echo "$out/quantus.cmd"
