#!/usr/bin/env bash
# run_capped.sh OUTDIR -- CMD [ARGS...]
#
# Runs CMD under the j41m.15 spike box and writes OUTDIR/metrics.json.
#   memory cap  : MEM_MAX  (default 12G)  systemd-run --user --scope -p MemoryMax -p MemorySwapMax=0
#   wall cap    : WALL_MAX (default 24h)  coreutils timeout
# stdout+stderr of CMD go to OUTDIR/run.log.
# metrics.json: rc, wall_s, maxrss_kb (GNU time), cgroup_peak_bytes (memory.peak), oom_kill (cgroup memory.events),
#               timed_out, killed_by_cap, cmd.  A run is "completed" only if rc==0 and neither flag is set.
# systemd-oomd can kill the whole session on a loaded host: run nothing else heavy meanwhile.
set -u
out=$1; shift
[ "${1:-}" = "--" ] && shift
[ $# -ge 1 ] || { echo "usage: run_capped.sh OUTDIR -- CMD [ARGS...]" >&2; exit 64; }
mkdir -p "$out"
here=$(cd "$(dirname "$0")" && pwd)
export MEM_MAX=${MEM_MAX:-12G} WALL_MAX=${WALL_MAX:-24h}
exec systemd-run --user --scope --quiet -p MemoryMax="$MEM_MAX" -p MemorySwapMax=0 \
    bash "$here/run_capped_inner.sh" "$out" "$@"
