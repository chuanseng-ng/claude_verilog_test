#!/bin/bash
# run_techgen_cell.sh <corner> [dir] -- Cadence Quantus Techgen, cell-level (DEF/Innovus flow): ICT -> RCGEN -> unified qrcTechFile.
#
# Why this and not run_techgen.sh (Techgen -simulation_FS_off): the unified -simulation flow adds a transistor-level 2-D pass (~6 h) that the
# DEF flow never reads, and its final "cell-level models update" step needs rcxfs.dat, which -simulation_FS_off never writes (nebula
# NEBULAM-135091 segfault loop; reproduced 2026-11-07, see knowledge.md).  The Quantus cell-level flow reads only the RCgen part:
#   1. Techgen -cell -plan -multi_cpu N <ict>                   writes the job scripts
#   2. Techgen -cell -parallel -autoconcat -hideprocess <ict> RCGEN   runs the model jobs, concatenates RCGEN (cell-level models)
#   3. Techgen -migrate -rcgen RCGEN qrcTechFile                wraps RCGEN into the unified file Quantus' cell-level flow requires
#      (a bare RCGEN is rejected: "EXTGRMP-354 no cell-level data in the unified techfile")
# Each step runs under licensed_lock.sh + safe_run.sh (load/memory gate, process-group kill) with GNU time and a whole-session RSS sampler.
# Resumable: a step whose marker <dir>/.done_<step> exists is skipped; step 2 is restartable by re-running (already-finished jobs are kept).
# Output: <dir>/qrcTechFile, <dir>/techgen_cell.timing (wall s and peak RSS per step).   dir default: build/qrc/<corner>.
set -u
here=$(cd "$(dirname "$0")" && pwd); b=$here/../build; root=$(cd "$here/../../../../.." && pwd)
c=$1; d=${2:-$b/qrc/$c}; mkdir -p "$d" "$b/logs"
. "$root/tools/eda/pd_env.sh" >/dev/null 2>&1 || true
ict=sky130A_$c.ict
[ -f "$d/$ict" ] || cp "$b/tech/ict/$ict" "$d/"
cmp -s "$b/tech/ict/$ict" "$d/$ict" || { echo "ICT in $d differs from build/tech/ict/$ict" >&2; exit 4; }
N=${TECHGEN_CPUS:-2}
sampler() {  # sampler <tag>: sum RSS over the session of the first Techgen process, every 20 s
  ( while :; do l=$(pgrep -x Techgen | head -1); if [ -n "$l" ]; then s=$(ps -o sid= -p "$l" | tr -d ' ');
      [ -n "$s" ] && echo "$(date +%s) $(ps -e -o sid=,rss= | awk -v s="$s" '$1==s{t+=$2} END{print t+0}')" >> "$d/rss_$1.txt"; fi; sleep 20; done ) >/dev/null 2>&1 &
  echo $!
}
step() {  # step <name> <timeout_s> <cmd...>
  nm=$1; to=$2; shift 2
  sleep "${STEP_GAP:-60}"   # >= 60 s between job starts (host rule)
  [ -f "$d/.done_$nm" ] && { echo "skip $nm (done)"; return 0; }
  t0=$(date +%s); smp=$(sampler "$nm")
  ( cd "$d" && SAFE_TIMEOUT=$to SAFE_THREADS=$N SAFE_MEM_MAX=${SAFE_MEM_MAX:-8G} SAFE_MIN_AVAIL_GB=${SAFE_MIN_AVAIL_GB:-6} "$here/licensed_lock.sh" "$here/safe_run.sh" "$b/logs/techgen_cell_${c}_$nm.log" \
      /usr/bin/time -v -o "$d/time_$nm.txt" "$@" ); rc=$?
  kill "$smp" 2>/dev/null; wait "$smp" 2>/dev/null
  t1=$(date +%s); pk=0; [ -f "$d/rss_$nm.txt" ] && pk=$(sort -k2 -n "$d/rss_$nm.txt" | tail -1 | cut -d' ' -f2)
  echo "$nm rc=$rc wall_s=$((t1-t0)) session_peak_rss_kb=$pk" | tee -a "$d/techgen_cell.timing"
  [ $rc -eq 0 ] && touch "$d/.done_$nm"; return $rc
}
step plan 1800 Techgen -cell -plan -multi_cpu "$N" "$ict" || exit 1
step parallel ${TECHGEN_TIMEOUT:-50400} Techgen -cell -parallel -autoconcat -hideprocess "$ict" RCGEN || exit 2
[ -s "$d/RCGEN" ] || { echo "RCGEN missing/empty" >&2; exit 3; }
step migrate 900 Techgen -migrate -rcgen RCGEN qrcTechFile || exit 5
[ -s "$d/qrcTechFile" ] && echo "OK $d/qrcTechFile ($(stat -c %s "$d/qrcTechFile") bytes)"
