#!/usr/bin/env bash
# vivado_fmax.sh -- Vivado batch clock-speed sanity check of soc_top on an Artix-7 / Kintex-7 part (bead hlrm, GH #245).
# ONE Vivado job per call. Vivado is NOT in CI and not in nix: point VIVADO_SETTINGS at the install's settings64.sh.
#
# usage: VIVADO_SETTINGS=/path/to/Vivado/<ver>/settings64.sh \
#        vivado_fmax.sh <repo-root> <out-dir> <gpu|nogpu> <synth|impl|both|probe> <tag> [period-ns]
#
#   synth  read the SystemVerilog directly (+define FPGA +define __pnr__), synth_design on the timing harness, write
#          <out-dir>/<gpu>/synth.dcp and pre-implementation reports.
#   impl   open that checkpoint, apply tools/fpga/vivado_fmax_constraints.tcl at <period-ns> (default 10.0), then
#          opt_design, place_design, phys_opt_design, route_design and the timing / utilisation / clock-interaction /
#          methodology reports under <out-dir>/<gpu>/<tag>/.
#   both   synth then impl in one session.
#
# Environment (all optional except VIVADO_SETTINGS):
#   VIVADO_SETTINGS  path to Vivado settings64.sh        (REQUIRED; nothing is hard-coded)
#   VFMAX_PART       device, default xc7a200tsbg484-1    (Nexys Video); xc7k325tffg900-2 = Genesys 2
#   VFMAX_THREADS    general.maxThreads, default 4
#   VFMAX_TIMEOUT    wall-clock cap in seconds, default 14400 (4 h). A job that hits the cap is a finding, not retried.
#   VFMAX_PERIOD_CPU period of cpu_clk_i in ns (default: same as <period-ns>)
#   VFMAX_PHYS_OPT_POST  1 = also run a post-route phys_opt_design (default 0)
#
# The harness is tools/fpga/ecp5_timing_harness.sv, unchanged: it is plain SystemVerilog with no vendor primitive, so it is
# reused as-is (6 pins: the four clocks, one serial input, one folded output). Peak RSS and elapsed time are in <tag>.time.
set -uo pipefail
if [ $# -lt 5 ]; then sed -n '2,24p' "$0"; exit 2; fi
root=$(cd "$1" && pwd); out=$2; gpu=$3; phase=$4; tag=$5; period=${6:-10.0}
: "${VIVADO_SETTINGS:?set VIVADO_SETTINGS to the Vivado settings64.sh path}"
[ -r "$VIVADO_SETTINGS" ] || { echo "cannot read VIVADO_SETTINGS=$VIVADO_SETTINGS"; exit 2; }
case $gpu in gpu|nogpu) ;; *) echo "bad gpu arg $gpu"; exit 2 ;; esac
case $phase in synth|impl|both|probe|constr) ;; *) echo "bad phase $phase"; exit 2 ;; esac
here=$(cd "$(dirname "$0")" && pwd)
# shellcheck disable=SC1090
source "$VIVADO_SETTINGS" > /dev/null 2>&1
mkdir -p "$out/$gpu"
export VFMAX_ROOT=$root VFMAX_OUT=$out VFMAX_GPU=$gpu VFMAX_PHASE=$phase VFMAX_TAG=$tag VFMAX_PERIOD=$period
export VFMAX_PART=${VFMAX_PART:-xc7a200tsbg484-1} VFMAX_THREADS=${VFMAX_THREADS:-4}
export VFMAX_PERIOD_CPU=${VFMAX_PERIOD_CPU:-$period} VFMAX_PHYS_OPT_POST=${VFMAX_PHYS_OPT_POST:-0}
export VFMAX_HERE=$here
# file list = the Stage 0 list (cocotb PLL_SOURCES + rv32i_clock_gate + rtl/fpga/*.sv) + the harness
if [ "$phase" = synth ] || [ "$phase" = both ]; then
  { "$here/stage0_filelist.sh" "$root" "$gpu" fpga; echo "$here/ecp5_timing_harness.sv"; } > "$out/$gpu/filelist.txt"
fi
log=$out/$gpu/$tag.vivado.log
/usr/bin/time -v -o "$out/$gpu/$tag.time" timeout "${VFMAX_TIMEOUT:-14400}" \
  vivado -mode batch -source "$here/vivado_fmax.tcl" -nojournal -nolog > "$log" 2>&1
echo "vivado rc=$?" | tee "$out/$gpu/$tag.rc"
grep -E "Maximum resident|Elapsed" "$out/$gpu/$tag.time"
