#!/bin/bash
# run_quantus.sh <arm> <corner> [outdir] -- one Quantus extraction under safe_run.sh (load/memory gate, <= 2 threads, process-group kill).
# Records wall time and peak RSS (largest single process, GNU time) in <out>/time.txt and a whole-session RSS sampler trace in <out>/rss_trace.txt.
# Run ONE at a time, wrapped in licensed_lock.sh by the caller (see chain.sh).
set -eu
arm=$1; corner=$2
HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$(cd "$HERE/../../../../.." && pwd)
. "$ROOT/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
out=${3:-$ROOT/pnr/commercial/signoff/quantus/runs/${arm}_${corner}}
. "$ROOT/pnr/commercial/signoff/starrc/scripts/arms.sh"
DEFF=$ROOT/$(arm_def "$arm")
[ -f "$DEFF" ] && tail -c 200 "$DEFF" | grep -q "END DESIGN" || { echo "DEF missing or incomplete: $DEFF" >&2; exit 3; }
rm -rf "$out/qtmp" "$out/rv32i_cpu_top.$corner.spef"*
"$HERE/gen_cmd.sh" "$arm" "$corner" "$out" >/dev/null
cd "$out"
# whole-session peak RSS sampler: sums RSS of every process in the session of the quantus leader
( while :; do
    l=$(pgrep -x quantus | head -1); [ -n "$l" ] && { s=$(ps -o sid= -p "$l" | tr -d ' '); \
      [ -n "$s" ] && echo "$(date +%s) $(ps -e -o sid=,rss= | awk -v s="$s" '$1==s{t+=$2} END{print t+0}')" >> "$out/rss_trace.txt"; }
    sleep 10; done ) &
smp=$!
export SAFE_THREADS=${QUANTUS_CORES:-2} SAFE_MEM_MAX=${SAFE_MEM_MAX:-10G} SAFE_TIMEOUT=${SAFE_TIMEOUT:-7200}
set +e
"$ROOT/pnr/commercial/pdk/sky130/scripts/safe_run.sh" "$out/quantus.log" \
  /usr/bin/time -v -o "$out/time.txt" quantus -multi_cpu "$SAFE_THREADS" -cmd "$out/quantus.cmd" -log_file "$out/quantus_run.log"
rc=$?
kill $smp 2>/dev/null; wait $smp 2>/dev/null
echo "rc=$rc" >> "$out/time.txt"
[ -f "$out/rss_trace.txt" ] && echo "session_peak_rss_kb=$(sort -k2 -n "$out/rss_trace.txt" | tail -1 | cut -d' ' -f2)" >> "$out/time.txt"
exit $rc
