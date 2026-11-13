#!/bin/bash
# chain_soc_budget.sh -- step 4b: PT judge, per-view iolat + SoC-context input budgets, final arms (openroad, icc2b9, innovusb11) x 9 corners = 27 runs,
# strictly serial (licensed_lock + safe_run inside run_one.sh), load<6 / MemAvailable>6 GB / >=60 s between starts.  Marker chain_soc_budget/<arm>_<rc>_<lib>.done skips a finished run (delete to redo).
cd "$(dirname "$0")"
L=chain_soc_budget.log; M=chain_soc_budget; mkdir -p $M; LAST=0
LK=../pdk/sky130/scripts/licensed_lock.sh
stagger() {
  local now l a; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do
    l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo)
    [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; sleep 20
  done
  LAST=$(date +%s)
}
for arm in icc2b9 innovusb11 openroad; do for rc in nom min max; do for lib in tt ss ff; do
  k=${arm}_${rc}_${lib}
  [ -f $M/$k.done ] && { echo "$(date +%T) skip $k" >> $L; continue; }
  stagger; echo "$(date +%T) start $k" >> $L
  $LK bash -c "cd pt && scripts/run_iolat_pv_soc.sh $arm $rc $lib" > $M/$k.out 2>&1; rc_=$?
  echo "$(date +%T) end $k rc=$rc_" >> $L; echo $rc_ > $M/$k.done
done; done; done
echo "$(date +%T) chain_soc_budget done" >> $L
