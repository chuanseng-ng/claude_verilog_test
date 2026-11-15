#!/bin/bash
# window_ob.sh <arm-dir-name: openroad|openroad_b3> -- std-cell-GDS Magic (drc(full), STD=gds) on the OpenROAD arm by the WINDOW method (step 9 C; user decision 2026-11-09).  NEVER the full layout.
#   1. mk_windows.py -> windows.tsv (42 windows covering everything but SRAM interiors)   2. ONE KLayout run clips all windows from the arm's Magic-streamed GDS (via ctr.sh, guard_run.sh)
#   3. the TINY window (100 x 100 um) first: if it fails or hangs the driver stops (report NOT RUN)   4. every other window, strictly one at a time.
#   Before every Magic start: load1 < 6 and MemAvailable >= 12 GB (decimal), >= 60 s after the previous start.  Each window = podman container (guard_run: MemAvailable < 1.5 GB or container RSS > 6 GB kills it).
#   Resumable: <out>/<name>.done.  Summary: summarize_windows.py.  Run detached: setsid nohup ./window_ob.sh openroad_b3 > ... &
set -u
ARM=${1:?openroad|openroad_b3}
HERE=$(cd "$(dirname "$0")" && pwd); D=$(cd "$HERE/.." && pwd); R=$(cd "$D/../../../.." && pwd)
O=$HERE/out_$ARM; mkdir -p $O
SRC=$R/pnr/commercial/runs/$ARM/rv32i_cpu_top.gds
[ -s $SRC ] || { echo "no GDS $SRC"; exit 1; }
LAST=0
gate() { # $1 = min MemAvailable GB (decimal)
  local now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1000000}' /proc/meminfo)
    pgrep -x magic >/dev/null && { sleep 20; continue; }
    [ "$l" -lt 6 ] && [ "$a" -ge $1 ] && break; echo "$(date +%T) gate: load $l avail ${a}GB (need >= $1)" >> $O/gate.log; sleep 30; done
  LAST=$(date +%s)
}
python3 -I $HERE/mk_windows.py $O/windows.tsv > /dev/null
if [ ! -f $O/clip.done ]; then
  gate 8; mkdir -p $O/clips
  SAFE_MIN_AVAIL_GB=6 SAFE_TIMEOUT=3600 GUARD_RSS_GB=11 $D/scripts/guard_run.sh $O/clip.log ob_clip $D/scripts/ctr.sh ob_clip klayout -b -r $HERE/clip_multi.py -rd gds=$SRC -rd top=rv32i_cpu_top -rd wins=$O/windows.tsv -rd outdir=$O/clips -rd margin=8 && touch $O/clip.done || { echo "clip failed"; exit 2; }
fi
ENVBASE=$D/runs/icc2_b6/mdrc_real/env.tcl
run_win() {
  local n=$1; [ -f $O/$n.done ] && return 0
  gate 12; echo "$(date +%T) magic window $n start" >> $O/chain.log
  local e=$O/m_$n.env.tcl; { cat $ENVBASE; echo "set ::env(DESIGN_NAME) clip_top"; echo "set ::env(CURRENT_GDS) $O/clips/clip_$n.gds"; echo "set ::env(STD) gds"; echo "set ::env(STEP_ID) Magic.DRC"; } > $e
  SAFE_MIN_AVAIL_GB=10 SAFE_TIMEOUT=2400 GUARD_MIN_GB=3 GUARD_RSS_GB=6 $D/scripts/guard_run.sh $O/m_$n.log ob_m_$n $D/scripts/ctr.sh ob_m_$n bash $D/scripts/in_container/magic_step.sh $e $O/m_$n $HERE/magic_drc_variant.tcl
  local rc=$?; echo "$(date +%T) magic window $n end rc=$rc" >> $O/chain.log
  [ $rc -eq 0 ] && [ -s $O/m_$n/reports/drc_violations.magic.rpt ] && touch $O/$n.done || return 1
}
run_win TINY || { echo "TINY window failed: stop (NOT RUN)"; exit 3; }
echo "TINY ok" >> $O/chain.log
for n in $(cut -f1 $O/windows.tsv | grep -v '^TINY$'); do run_win $n || echo "$n FAILED" >> $O/chain.log; done
echo "$(date +%T) window_ob done" >> $O/chain.log
