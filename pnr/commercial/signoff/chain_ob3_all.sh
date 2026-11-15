#!/bin/bash
# chain_ob3_all.sh -- OpenROAD generation B3 (step 9) judge chain: export final views -> StarRC nom/min/max -> PrimeTime judge base + iolat x 9 corners (PrimePower at nom_tt)
#   -> clk_i latency x 9 -> per-view iolat tables -> PT iolat_pv arm + shared x 9 -> PT SoC-budget (step 4b SDC) x 9.  Copy of chain_b12_all.sh's judge part for the OpenROAD arm
#   (the OpenROAD arm has no own-SDC variant; its DRC / LVS / deck antenna come from the LibreLane flow's own steps, its LEC from signoff/lec/*).
#   Resumable: a step with chain_ob3/<step>.done is skipped (delete the marker to redo); a FAIL is a result and does not stop the chain.  One heavy tool at a time,
#   load1 < 6 and MemAvailable > 6 GB (decimal) before each job, >= 60 s between starts.  Env: OB3_ONLY="step step" runs just those.
cd "$(dirname "$0")"
PA=openroadb3; L=chain_ob3_all.log; M=chain_ob3; mkdir -p $M; LAST=0
LK=../pdk/sky130/scripts/licensed_lock.sh
stagger() {
  local now l a; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do
    l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1000000}' /proc/meminfo)
    [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; sleep 20
  done
  LAST=$(date +%s)
}
step() { # step <name> <cmd...>
  local n=$1; shift
  if [ -n "${OB3_ONLY:-}" ] && ! echo " $OB3_ONLY " | grep -q " $n "; then return; fi
  if [ -f $M/$n.done ]; then echo "$(date +%T) skip $n (done: rc=$(cat $M/$n.done))" >> $L; return; fi
  stagger; echo "$(date +%T) start $n" >> $L
  "$@" > $M/$n.out 2>&1; local rc=$?
  echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > $M/$n.done
}
step export python3 -I ../impl/openroad/export_b3.py
[ -s ../runs/openroad_b3/rv32i_cpu_top.def ] && [ -s ../runs/openroad_b3/rv32i_cpu_top.nl.v ] || { echo "$(date +%T) runs/openroad_b3 missing - judge not started" >> $L; exit 1; }
for c in nom min max; do step starrc_$c $LK bash -c "GATE_LIGHT=1 ../impl/innovus/scripts/gate_host.sh && cd starrc && scripts/run_starrc.sh $PA $c > runs/${PA}_$c.out 2>&1"; done
for v in base iolat; do for rc in nom min max; do for lib in tt ss ff; do
  pw=0; [ $rc = nom ] && [ $lib = tt ] && pw=1
  case $v in base) e="env PT_SET= GATE_LIGHT=1" ;; iolat) e="env PT_SET=iolat PT_SDC=iolat GATE_LIGHT=1" ;; esac
  step pt_${v}_${rc}_${lib} $LK bash -c "cd pt && $e scripts/run_one.sh $PA $rc $lib $pw"
done; done; done
for rc in nom min max; do for lib in tt ss ff; do step measure_${rc}_${lib} $LK bash -c "cd pt && scripts/measure_one.sh $PA $rc $lib"; done; done
step iolat_tables bash -c "cd pt && python3 -I scripts/mk_iolat_tables.py"
for v in arm shared; do for rc in nom min max; do for lib in tt ss ff; do
  step pv_${v}_${rc}_${lib} $LK bash -c "cd pt && scripts/run_iolat_pv.sh $v $PA $rc $lib"
done; done; done
for rc in nom min max; do for lib in tt ss ff; do
  step soc_${rc}_${lib} $LK bash -c "cd pt && scripts/run_iolat_pv_soc.sh $PA $rc $lib"
done; done
echo "$(date +%T) chain_ob3_all done" >> $L
