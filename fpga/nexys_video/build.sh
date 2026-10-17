#!/usr/bin/env bash
# build.sh -- Vivado synth + impl + bitstream of the Nexys Video prototype (bead hlrm.2). ONE Vivado job per call.
#
# usage: [VIVADO_SETTINGS=/nobackup/FPGA_SW/2026.1/Vivado/settings64.sh] \
#        [NV_BOOT_HEX=/abs/boot.hex] fpga/nexys_video/build.sh <out-dir> [synth|all] [tag]
#
# Vivado is external (not in nix, not in CI). The default VIVADO_SETTINGS is this host's install.
# Peak RSS and elapsed time are written to <out-dir>/<tag>.time. Do NOT run while a PD flow holds the host's memory cap.
set -uo pipefail
if [ $# -lt 1 ]; then sed -n '2,9p' "$0"; exit 2; fi
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../.." && pwd)
out=$(mkdir -p "$1" && cd "$1" && pwd); phase=${2:-all}; tag=${3:-run}
: "${VIVADO_SETTINGS:=/nobackup/FPGA_SW/2026.1/Vivado/settings64.sh}"
[ -r "$VIVADO_SETTINGS" ] || { echo "cannot read VIVADO_SETTINGS=$VIVADO_SETTINGS"; exit 2; }
export NV_BOOT_HEX=${NV_BOOT_HEX:-$here/boot_placeholder.hex}
[ -r "$NV_BOOT_HEX" ] || { echo "cannot read NV_BOOT_HEX=$NV_BOOT_HEX"; exit 2; }
NV_BOOT_HEX=$(readlink -f "$NV_BOOT_HEX"); export NV_BOOT_HEX
export NV_ROOT=$root NV_OUT=$out NV_PHASE=$phase NV_TAG=$tag
# shellcheck disable=SC1090
source "$VIVADO_SETTINGS" > /dev/null 2>&1
log=$out/$tag.vivado.log
cd "$out" || exit 2   # Vivado drops .Xil/ and clockInfo.txt into the working directory
/usr/bin/time -v -o "$out/$tag.time" timeout "${NV_TIMEOUT:-14400}" \
  vivado -mode batch -source "$here/build.tcl" -nojournal -nolog > "$log" 2> "$out/$tag.stderr"
echo "vivado rc=$?" | tee "$out/$tag.rc"
grep -E "Maximum resident|Elapsed" "$out/$tag.time"
