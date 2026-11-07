#!/bin/bash
# safe_run.sh -- run ONE vendor tool under a memory cap, low priority, in its own
# process group, with licence-holder cleanup.  Usage: safe_run.sh <logfile> <cmd...>
#   * waits until loadavg(1min) < SAFE_MAX_LOAD (default 6) and sets *_NUM_THREADS=${SAFE_THREADS:-1}
#   * waits until MemAvailable >= SAFE_MIN_AVAIL_GB (default 4)
#   * systemd-run --user --scope -p MemoryMax=${SAFE_MEM_MAX:-3G}, nice -n 10, setsid
#   * SAFE_TIMEOUT seconds (default 1800): then the WHOLE process group is killed
#     (a bare `timeout` leaves *_exec children holding licences)
#   * on exit, any process left in the group is killed.
set -u
log=$1; shift
min=${SAFE_MIN_AVAIL_GB:-4}
for i in $(seq 1 120); do
  avail=$(awk '/MemAvailable/{printf "%d", $2/1048576}' /proc/meminfo)
  [ "$avail" -ge "$min" ] && break
  echo "safe_run: MemAvailable ${avail}G < ${min}G, waiting ($i)" >&2; sleep 30
done
[ "$avail" -ge "$min" ] || { echo "safe_run: memory never freed, aborting" >&2; exit 99; }
# Coordinator rule (host crashed on NMI-watchdog hard-lockup when all vCPUs were saturated by the
# parallel OpenROAD run): vendor tools run single-threaded (<=2 threads) and only when the
# 1-minute load average is below SAFE_MAX_LOAD (default 6).
maxload=${SAFE_MAX_LOAD:-6}
for i in $(seq 1 240); do
  load=$(awk '{printf "%d", $1}' /proc/loadavg)
  [ "$load" -lt "$maxload" ] && break
  echo "safe_run: loadavg1 $(cut -d' ' -f1 /proc/loadavg) >= ${maxload}, waiting ($i)" >&2; sleep 30
done
[ "$load" -lt "$maxload" ] || { echo "safe_run: load never dropped, aborting" >&2; exit 98; }
export OMP_NUM_THREADS=${SAFE_THREADS:-1} MKL_NUM_THREADS=${SAFE_THREADS:-1} OPENBLAS_NUM_THREADS=${SAFE_THREADS:-1} TBB_NUM_THREADS=${SAFE_THREADS:-1}
pgfile=$(mktemp)
# setsid inside the scope: the child leads its own session/process group; record its pgid.
systemd-run --user --scope -q -p MemoryMax=${SAFE_MEM_MAX:-3G} -p MemorySwapMax=0 \
  nice -n 10 setsid bash -c 'echo $$ > "$0"; exec "$@"' "$pgfile" "$@" > "$log" 2>&1 &
wrapper=$!
t=0; lim=${SAFE_TIMEOUT:-1800}
while kill -0 "$wrapper" 2>/dev/null; do
  sleep 2; t=$((t+2))
  if [ "$t" -ge "$lim" ]; then
    echo "safe_run: TIMEOUT ${lim}s -- killing process group" >&2
    [ -s "$pgfile" ] && kill -TERM -- -"$(cat "$pgfile")" 2>/dev/null; sleep 5
    [ -s "$pgfile" ] && kill -KILL -- -"$(cat "$pgfile")" 2>/dev/null
    break
  fi
done
wait "$wrapper"; rc=$?
if [ -s "$pgfile" ]; then pg=$(cat "$pgfile")
  if pgrep -g "$pg" >/dev/null 2>&1; then echo "safe_run: killing leftover group $pg" >&2; kill -KILL -- -"$pg" 2>/dev/null; fi
fi
rm -f "$pgfile"
exit $rc
