#!/usr/bin/env bash
# Inner half of run_capped.sh: runs inside the memory-capped systemd scope.
set -u
out=$1; shift
t0=$(date +%s.%N)
/usr/bin/time -v -o "$out/time.txt" timeout --signal=KILL "${WALL_MAX:-24h}" "$@" >"$out/run.log" 2>&1
rc=$?
t1=$(date +%s.%N)
cg=/sys/fs/cgroup$(sed -n 's/^0:://p' /proc/self/cgroup)
peak=$(cat "$cg/memory.peak" 2>/dev/null || echo -1)
oom=$(awk '$1=="oom_kill"{print $2}' "$cg/memory.events" 2>/dev/null || echo -1)
python3 - "$out" "$rc" "$t0" "$t1" "$peak" "${oom:--1}" "${WALL_MAX:-24h}" "$@" <<'PY'
import json, os, re, sys
out, rc, t0, t1, peak, oom, wall_max = sys.argv[1:8]
cmd = sys.argv[8:]
rc = int(rc)
rss = -1
try:
    for line in open(out + "/time.txt"):
        m = re.search(r"Maximum resident set size \(kbytes\): (\d+)", line)
        if m:
            rss = int(m.group(1))
except OSError:
    pass


def secs(s):
    n, u = re.fullmatch(r"(\d+(?:\.\d+)?)([smhd]?)", s).groups()
    return float(n) * {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}[u]


wall = float(t1) - float(t0)
# timeout --signal=KILL exits 137 (128+9); the cgroup OOM killer also yields 137,
# so tell them apart by the cgroup oom_kill counter and the wall time.
oom_kill = int(oom)
timed_out = rc == 137 and oom_kill <= 0 and wall >= secs(wall_max) - 2
killed_by_cap = oom_kill > 0
json.dump({
    "rc": rc, "wall_s": round(wall, 2), "maxrss_kb": rss, "cgroup_peak_bytes": int(peak),
    "oom_kill": oom_kill, "timed_out": timed_out, "killed_by_cap": killed_by_cap,
    "completed": rc == 0 and not timed_out and not killed_by_cap,
    "cmd": cmd, "mem_max": os.environ.get("MEM_MAX"), "wall_max": wall_max,
}, open(out + "/metrics.json", "w"), indent=1)
PY
exit $rc
