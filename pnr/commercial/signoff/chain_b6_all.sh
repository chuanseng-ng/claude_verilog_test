#!/bin/bash
# chain_b6_all.sh -- ICC2 b6 verification, resumable, ONE heavy tool at a time (open tools included, all under licensed_lock.sh), host-staggered:
#   before each job wait for loadavg1 < 6 and MemAvailable > 6 GB, then >= 60 s since the previous job started.  Each step logs start/end (rc) to chain_b6_all.log and writes
#   chain_b6/<step>.done (containing the rc); a step with a done marker is skipped on re-run (delete the marker to redo).  A failing step does not stop the chain (a FAIL is a result), but is logged.
#   Order: open decks (GDS integrity, GDS fix, GDS-mode Magic extraction + Netgen LVS variants, KLayout DRC, OpenROAD antenna) -> Formality (6 runs + 4 negative controls)
#          -> StarRC nom/min/max -> PT judge 27 runs (own, base, iolat) x (nom,min,max) x (tt,ss,ff) -> Magic DRC (ONLY with STEPS including magic; alone, ~11 GiB cap).
#   Env: B6_SKIP_MAGIC=1 (default) leaves Magic DRC out;  B6_ONLY="step step" runs just those.
cd "$(dirname "$0")"
L=chain_b6_all.log; M=chain_b6; mkdir -p $M; LAST=0
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
  if [ -n "${B6_ONLY:-}" ] && ! echo " $B6_ONLY " | grep -q " $n "; then return; fi
  if [ -f $M/$n.done ]; then echo "$(date +%T) skip $n (done: rc=$(cat $M/$n.done))" >> $L; return; fi
  stagger; echo "$(date +%T) start $n" >> $L
  "$@" > $M/$n.out 2>&1; local rc=$?
  echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > $M/$n.done
}
A=icc2_b6; mkdir -p drclvs/runs/$A/logs
D="make -C drclvs ARM=$A PIN_MODE=none"
for t in inspect fixgds; do step drclvs_$t $LK bash -c "$D $t > drclvs/runs/$A/logs/make_$t.log 2>&1"; done
step drclvs_lvs-gds-extract $LK bash -c "$D EXTRACT_TIMEOUT=18000 lvs-gds-extract > drclvs/runs/$A/logs/make_lvs-gds-extract.log 2>&1"
for t in lvs-gds-netgen lvs-gds-variants kdrc antenna; do step drclvs_$t $LK bash -c "$D $t > drclvs/runs/$A/logs/make_$t.log 2>&1"; done
step drclvs_summary bash -c "$D summary > drclvs/runs/$A/logs/make_summary.log 2>&1"
step lec $LK make -C lec/formality lec-icc2-b6
for c in nom min max; do step starrc_$c $LK bash -c "GATE_LIGHT=1 ../impl/innovus/scripts/gate_host.sh && cd starrc && scripts/run_starrc.sh icc2b6 $c > runs/icc2b6_$c.out 2>&1"; done
OWN=pnr/commercial/impl/icc2/runs/b6_icc2/out/rv32i_cpu_top.sdc
for v in own base iolat; do for rc in nom min max; do for lib in tt ss ff; do
  pw=0; [ $rc = nom ] && [ $lib = tt ] && pw=1
  case $v in
    base)  e="env PT_SET= GATE_LIGHT=1" ;;
    own)   e="env PT_SET=own PT_SDC=own PT_SDC_FILE=$OWN GATE_LIGHT=1" ;;
    iolat) e="env PT_SET=iolat PT_SDC=iolat GATE_LIGHT=1" ;;
  esac
  step pt_${v}_${rc}_${lib} $LK bash -c "cd pt && $e scripts/run_one.sh icc2b6 $rc $lib $pw"
done; done; done
if [ "${B6_SKIP_MAGIC:-1}" != 1 ]; then
  step magic_drc $LK bash -c "cd drclvs && GUARD_RSS_GB=11 MDRC_TIMEOUT=${MDRC_TIMEOUT:-43200} EXTRACT_TIMEOUT=${EXTRACT_TIMEOUT:-18000} make ARM=$A SRAM_MODE=real mdrc mdrc-class > runs/${A}_mdrc_real.make.log 2>&1"
fi
echo "$(date +%T) chain_b6_all done" >> $L
