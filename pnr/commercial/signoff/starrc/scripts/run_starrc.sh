#!/bin/bash
# run_starrc.sh <arm> <corner>  -- one StarRC extraction under safe_run.sh (load/mem gate, process-group kill).
# Records wall time and peak RSS in runs/<arm>_<corner>/time.txt.  Run ONE at a time.
set -eu
arm=$1; corner=$2
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
DEFF=$ROOT/$(. "$HERE/arms.sh"; arm_def "$arm")
[ -f "$DEFF" ] && tail -c 200 "$DEFF" | grep -q "END DESIGN" || { echo "DEF missing or incomplete: $DEFF" >&2; exit 3; }
out=$ROOT/pnr/commercial/signoff/starrc/runs/${arm}_${corner}
rm -rf "$out/star" "$out/rv32i_cpu_top.$corner.spef"
"$HERE/gen_cmd.sh" "$arm" "$corner" >/dev/null
cd "$out"
export SAFE_THREADS=${STARRC_CORES:-2} SAFE_MEM_MAX=${SAFE_MEM_MAX:-10G} SAFE_TIMEOUT=${SAFE_TIMEOUT:-14400}
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/starrc.log" \
  /usr/bin/time -v -o "$out/time.txt" StarXtract "$out/starrc.cmd"
rc=$?
echo "rc=$rc" >> "$out/time.txt"
exit $rc
