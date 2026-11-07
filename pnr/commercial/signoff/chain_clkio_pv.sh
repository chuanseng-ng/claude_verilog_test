#!/bin/bash
# chain_clkio_pv.sh -- per-view clk_io latency study (judge-only, no P&R re-run), resumable, ONE heavy tool at a time under licensed_lock.sh, host-staggered:
#   before each job wait for loadavg1 < 6 and MemAvailable > 6 GB, then >= 60 s since the previous job started.  Each step writes chain_clkio_pv/<step>.done (rc) and
#   logs to chain_clkio_pv_all.log; a step with a done marker is skipped on re-run (delete the marker to redo).  A failing step does not stop the chain but is logged.
#   Stage 1  measure_<arm>_<rc>_<lib>   clk_i insertion latency at every register clock pin (pt/scripts/measure_one.sh)   3 arms x 9 corners = 27
#   Stage 2  (needs pt/iolat_pv/*.tcl tables, built by pt/scripts/mk_iolat_tables.py from stage 1)
#            pt_<variant>_<arm>_<rc>_<lib>  PT judge with the per-view iolat SDC (pt/scripts/run_iolat_pv.sh)
#   Env: CK_STAGES="measure judge"  CK_VARIANTS="arm shared"  CK_ONLY="step step"
cd "$(dirname "$0")"
L=chain_clkio_pv_all.log; M=chain_clkio_pv; mkdir -p $M; LAST=0
LK=../pdk/sky130/scripts/licensed_lock.sh
stagger() {
  local now l a; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do
    l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo)
    [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; sleep 20
  done
  LAST=$(date +%s)
}
step() { # step <name> <cmd...>
  local n=$1; shift
  if [ -n "${CK_ONLY:-}" ] && ! echo " $CK_ONLY " | grep -q " $n "; then return; fi
  if [ -f $M/$n.done ]; then echo "$(date +%T) skip $n (done: rc=$(cat $M/$n.done))" >> $L; return; fi
  stagger; echo "$(date +%T) start $n" >> $L
  "$@" > $M/$n.out 2>&1; local rc=$?
  echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > $M/$n.done
}
ARMS="openroad icc2b6 innovusb6"
if echo " ${CK_STAGES:-measure} " | grep -q " measure "; then
  for a in $ARMS; do for rc in nom min max; do for lib in tt ss ff; do
    step measure_${a}_${rc}_${lib} $LK bash -c "cd pt && scripts/measure_one.sh $a $rc $lib"
  done; done; done
fi
if echo " ${CK_STAGES:-measure} " | grep -q " judge "; then
  for v in ${CK_VARIANTS:-arm}; do for a in $ARMS; do for rc in nom min max; do for lib in tt ss ff; do
    pw=0
    step pt_${v}_${a}_${rc}_${lib} $LK bash -c "cd pt && scripts/run_iolat_pv.sh $v $a $rc $lib"
  done; done; done; done
fi
echo "$(date +%T) chain_clkio_pv done (stages: ${CK_STAGES:-measure})" >> $L
