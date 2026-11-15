#!/bin/bash
# run_b3.sh -- OpenROAD generation B3 (step 9): LibreLane CVTClassicB3 flow on pnr/sky130/cpu/config_b3.json, in the librelane 2.4.13 container,
# <= 2 threads, one heavy job, host gate (load < 6, MemAvailable > 6 GB decimal), MemAvailable watchdog, peak-RSS accounting (item 10 / step 9 A).
#   Peak RSS: (1) host `/usr/bin/time -v` around `podman run` (that is the podman CLIENT, tiny: kept as the literal wrapper), (2) inside the container a python
#   wrapper prints getrusage(RUSAGE_CHILDREN).ru_maxrss = the largest single process of the flow (OpenROAD / Yosys / Magic), (3) a sampler logs the summed RSS of every
#   process in the container's cgroup every 15 s (peak = max of that column).  Files: runs_b3/{time_v.txt,rusage.txt,rss_samples.tsv,flow.stdout}
# Usage: run_b3.sh [extra librelane args, e.g. --from X --last-run]   (resume = rerun with --last-run --from <step>)
set -u
REPO=$(cd "$(dirname "$0")/../../../.." && pwd)
CPU=$REPO/pnr/sky130/cpu
OUT=$REPO/pnr/commercial/impl/openroad/runs_b3; mkdir -p "$OUT"
TAG=${B3_TAG:-b3_openroad}; NAME=b3_openroad_ctr
IMG=${LIBRELANE_IMAGE:-ghcr.io/librelane/librelane:2.4.13}
PDK_ROOT=${PDK_ROOT:-$HOME/pdk}
LL=$HOME/tools/librelane-3562a8d
PYP=$LL:$REPO/pnr/plugins:$CPU/plugin_b3
while :; do   # host gate
  l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1000000}' /proc/meminfo)
  [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; echo "$(date +%T) gate: load $l avail ${a}GB, wait" >> "$OUT/gate.log"; sleep 30
done
pgrep -x podman >/dev/null && { echo "another podman client is running; abort" >&2; exit 3; }
cat > "$OUT/sampler.sh" <<'S'
#!/bin/bash
# sampler.sh <container-name> <out.tsv>: every 15 s, sum RSS (kB) of all processes in the container cgroup + MemAvailable (kB)
n=$1; o=$2; echo -e "time\tsum_rss_kB\tmax_rss_kB\tmemavail_kB\tnproc" > "$o"; id=
while sleep 15; do
  [ -z "$id" ] && id=$(podman inspect -f '{{.Id}}' "$n" 2>/dev/null)
  [ -z "$id" ] && continue
  ps -eo rss=,cgroup= | awk -v id="$id" -v t="$(date +%T)" -v av="$(awk '/MemAvailable/{print $2}' /proc/meminfo)" \
    'index($0,id){s+=$1; if($1>m)m=$1; n++} END{if(n>0) printf "%s\t%d\t%d\t%d\t%d\n",t,s,m,av,n}' >> "$o"
done
S
chmod +x "$OUT/sampler.sh"
"$OUT/sampler.sh" $NAME "$OUT/rss_samples.tsv" & SPID=$!
WRAP='import resource,subprocess,sys,json
rc=subprocess.call(sys.argv[1:])
r=resource.getrusage(resource.RUSAGE_CHILDREN)
open("'$OUT'/rusage.txt","w").write(json.dumps({"rc":rc,"ru_maxrss_kB_largest_single_process":r.ru_maxrss,"utime_s":r.ru_utime,"stime_s":r.ru_stime})+"\n")
sys.exit(rc)'
cd "$CPU"
SAFE_TIMEOUT=${SAFE_TIMEOUT:-28800} SAFE_MIN_AVAIL_GB=6 SAFE_THREADS=2 GUARD_RSS_GB=99 GUARD_MIN_GB=1.5 \
/usr/bin/time -v -o "$OUT/time_v.txt" \
  "$REPO/pnr/commercial/signoff/drclvs/scripts/guard_run.sh" "$OUT/flow.stdout" $NAME \
  podman run --rm --name $NAME -v "$HOME:$HOME" -v "$PDK_ROOT:$PDK_ROOT" -e PDK_ROOT="$PDK_ROOT" -e PDK=sky130A -e STD_CELL_LIBRARY=sky130_fd_sc_hd \
    -e PYTHONPATH="$PYP" -w "$CPU" "$IMG" \
    python3 -c "$WRAP" python3 -m librelane --pdk-root "$PDK_ROOT" --pdk sky130A --run-tag $TAG -j 2 "$@" "$CPU/config_b3.json"
rc=$?
kill $SPID 2>/dev/null
echo "$(date +%T) run_b3 rc=$rc" >> "$OUT/gate.log"
exit $rc
