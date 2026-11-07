#!/bin/bash
# measure_one.sh <arm> <rc> <lib> -- ONE pt_shell (safe_run.sh: load/mem gate, <=2 threads, process-group kill) measuring the clk_i insertion latency
# at every register clock pin.  Reads the SPEF snapshot of the arm's existing BASE judge run (runs/<arm>_<rc>_<lib>/spef) after checking its md5 against
# that run's inputs.txt AND against the current StarRC output, and the same netlist md5.  Output: runs_clklat/<arm>_<rc>_<lib>/.  Resumable (.done).
set -eu
arm=$1; rc=$2; lib=$3
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
. "$HERE/arms.sh"
tag=${arm}_${rc}_${lib}
base=$ROOT/pnr/commercial/signoff/pt/runs/$tag
out=$ROOT/pnr/commercial/signoff/pt/runs_clklat/$tag
NL=$ROOT/$(arm_netlist "$arm"); SPsrc=$ROOT/$(arm_spef "$arm" "$rc"); SP=$base/spef/$(basename "$SPsrc")
SDC=$ROOT/pnr/sky130/cpu/constraints/sky130_cpu.sdc
[ -s "$SP" ] && [ -s "$NL" ] && [ -f "$base/inputs.txt" ] || { echo "missing base judge run inputs for $tag" >&2; exit 3; }
want_sp=$(sed -n 's/^spef_md5=//p' "$base/inputs.txt"); want_nl=$(sed -n 's/^netlist_md5=//p' "$base/inputs.txt")
sp=$(md5sum "$SP" | cut -d' ' -f1); spsrc=$(md5sum "$SPsrc" | cut -d' ' -f1); nl=$(md5sum "$NL" | cut -d' ' -f1)
[ "$sp" = "$want_sp" ] && [ "$spsrc" = "$want_sp" ] && [ "$nl" = "$want_nl" ] || { echo "input md5 drift for $tag: spef snap $sp src $spsrc want $want_sp; netlist $nl want $want_nl" >&2; exit 4; }
mkdir -p "$out"
stamp="spef=$sp netlist=$nl scripts=$(cat "$HERE/measure_clk_latency.tcl" | md5sum | cut -d' ' -f1)"
if [ -f "$out/.done" ] && [ "$(cat "$out/.done")" = "$stamp" ]; then echo "UP-TO-DATE $tag"; exit 0; fi
rm -f "$out/.done"
{ echo "spef_src=$SPsrc"; echo "spef_snapshot=$SP"; echo "spef_md5=$sp"; echo "netlist_src=$NL"; echo "netlist_md5=$nl"; echo "sdc_md5=3c69635042a9d65cb87e71a9db713e4e"; } > "$out/inputs.txt"
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
cd "$out"
export J_ROOT=$ROOT J_NETLIST=$NL J_SPEF=$SP J_RC=$rc J_LIB=$lib J_SDC=$SDC M_ARM=$arm
export SAFE_THREADS=2 SAFE_MEM_MAX=${SAFE_MEM_MAX:-6G} SAFE_TIMEOUT=${SAFE_TIMEOUT:-1800}
rc_=0
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/pt.log" /usr/bin/time -v -o "$out/time.txt" pt_shell -f "$HERE/measure_clk_latency.tcl" || rc_=$?
echo "rc=$rc_" >> "$out/time.txt"
if [ $rc_ -eq 0 ] && grep -q '^all_rise_late_max' clk_latency.tsv && [ -s clk_pins.tsv ]; then echo "$stamp" > .done; echo "DONE $tag"
else echo "FAILED $tag rc=$rc_ (see $out/pt.log)" >&2; exit 1; fi
# drop the page cache of the big SPEF / netlist files (the host thrashed in kcompactd with 12 GB of cache over the 27 x 100 MB SPEFs)
for f in "$SP" "$SPsrc" "$NL"; do dd if="$f" iflag=nocache count=0 status=none 2>/dev/null || true; done
