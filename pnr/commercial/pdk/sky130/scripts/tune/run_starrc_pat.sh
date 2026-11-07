#!/bin/bash
# run_starrc_pat.sh <nxtgrd file> <outdir> [corner]  -- StarRC (same keywords as signoff/starrc/scripts/gen_cmd.sh) on build/tune/pat.def
set -eu
nx=$1; out=$2; corner=${3:-nom}
HERE=$(cd "$(dirname "$0")" && pwd); SK=$HERE/../..; ROOT=$(cd "$SK/../../../.." && pwd)
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
mkdir -p "$out"; rm -rf "$out/star"
case $corner in nom) TLEF=$SKY130_HD_TLEF ;; min) TLEF=$SKY130_HD_TLEF_MIN ;; max) TLEF=$SKY130_HD_TLEF_MAX ;; esac
grep -v '^#' "$SK/build/tech/map/starrc_layer.map" > "$out/sky130.map"
cat > "$out/starrc.cmd" <<CMD
BLOCK: pat
TCAD_GRD_FILE: $nx
MAPPING_FILE: $out/sky130.map
LEF_FILE: $TLEF
LEF_FILE: $SKY130_HD_LEF
TOP_DEF_FILE: $SK/build/tune/pat.def
STAR_DIRECTORY: $out/star
EXTRACTION: RC
COUPLE_TO_GROUND: NO
REDUCTION: NO_EXTRA_LOOPS
OPERATING_TEMPERATURE: 25
NETS: *
POWER_EXTRACT: NO
NETLIST_FORMAT: SPEF
NETLIST_FILE: $out/pat.$corner.spef
SHORTS_LIMIT: 1000000
NUM_CORES: 2
CMD
cd "$out"
SAFE_THREADS=2 SAFE_TIMEOUT=900 "$SK/scripts/safe_run.sh" "$out/starrc.log" StarXtract "$out/starrc.cmd"
