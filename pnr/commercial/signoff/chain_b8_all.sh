#!/bin/bash
# chain_b8_all.sh <icc2|innovus> -- b8 re-sign-off of one commercial arm, resumable, ONE heavy tool at a time (open tools included, licensed_lock.sh), host-staggered
#   (before each job: load1 < 6 and MemAvailable > 6 GB, then >= 60 s since the previous job started).  A step with chain_b8_<arm>/<step>.done is skipped (delete the marker to redo); a FAIL is a result and does not stop the chain.
#   Order: GDS integrity + fix -> Magic extraction + Netgen LVS -> KLayout DRC -> OpenROAD antenna deck -> LEC (Formality / Conformal + negative controls) -> StarRC nom/min/max
#          -> PT judge base/own/iolat x 9 corners (PrimePower at nom_tt) -> clk_i latency measurement x 9 -> per-view iolat tables -> PT iolat_pv arm + shared x 9
#          -> Magic DRC (sign-off mode = std cells from the GDS, user decision 2026-11-08; alone, ~11 GiB) only if B8_MAGIC=1.
#   Env: B8_ONLY="step step" runs just those; B8_MAGIC=1 adds magic (run it ALONE: B8_ONLY=magic_drc B8_MAGIC=1); MDRC_STD=lef reproduces the old LEF-abstract Magic mode.
cd "$(dirname "$0")"
ARM=${1:?icc2|innovus}
L=chain_b8_${ARM}_all.log; M=chain_b8_$ARM; mkdir -p $M; LAST=0
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
  if [ -n "${B8_ONLY:-}" ] && ! echo " $B8_ONLY " | grep -q " $n "; then return; fi
  if [ -f $M/$n.done ]; then echo "$(date +%T) skip $n (done: rc=$(cat $M/$n.done))" >> $L; return; fi
  stagger; echo "$(date +%T) start $n" >> $L
  "$@" > $M/$n.out 2>&1; local rc=$?
  echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > $M/$n.done
}
case $ARM in
  icc2)    A=icc2_b8; PA=icc2b8; OUT=../impl/icc2/runs/b8_icc2/out; DT="lvs-gds-netgen lvs-gds-variants kdrc antenna" ;;
  innovus) A=innovus_b8; PA=innovusb8; OUT=../impl/innovus/runs/b8_innovus/out; DT="lvs-gds-variants lvs-gds-netgen kdrc antenna" ;;
  *) echo "arm icc2|innovus" >&2; exit 2 ;;
esac
mkdir -p drclvs/runs/$A/logs
D="make -C drclvs ARM=$A PIN_MODE=none"
[ -s $OUT/rv32i_cpu_top.gds ] && [ -s $OUT/rv32i_cpu_top.def ] || { echo "$(date +%T) final out/ missing - verification not started" >> $L; exit 1; }
for t in inspect fixgds; do step drclvs_$t $LK bash -c "$D $t > drclvs/runs/$A/logs/make_$t.log 2>&1"; done
step drclvs_lvs-gds-extract $LK bash -c "$D EXTRACT_TIMEOUT=18000 lvs-gds-extract > drclvs/runs/$A/logs/make_lvs-gds-extract.log 2>&1"
for t in $DT; do step drclvs_$t $LK bash -c "$D $t > drclvs/runs/$A/logs/make_$t.log 2>&1"; done
step drclvs_summary bash -c "$D summary > drclvs/runs/$A/logs/make_summary.log 2>&1"
if [ $ARM = icc2 ]; then step lec $LK make -C lec/formality lec-icc2-b8
else step lec $LK make -C lec/conformal lec-innovus-all INNTAG=b8_innovus STEP=b8m; fi
for c in nom min max; do step starrc_$c $LK bash -c "GATE_LIGHT=1 ../impl/innovus/scripts/gate_host.sh && cd starrc && scripts/run_starrc.sh $PA $c > runs/${PA}_$c.out 2>&1"; done
if [ $ARM = icc2 ]; then OWN=pnr/commercial/impl/icc2/runs/b8_icc2/out/rv32i_cpu_top.sdc
else OWN=pnr/commercial/constraints/sky130_cpu_innovus_b8_own_pt.sdc
  step own_sdc bash -c "cd ../../.. && python3 -I pnr/commercial/constraints/mk_pt_own_sdc.py pnr/commercial/impl/innovus/runs/b8_innovus/out/rv32i_cpu_top.sdc $OWN b8"; fi
for v in base own iolat; do for rc in nom min max; do for lib in tt ss ff; do
  pw=0; [ $rc = nom ] && [ $lib = tt ] && pw=1
  case $v in
    base)  e="env PT_SET= GATE_LIGHT=1" ;;
    own)   e="env PT_SET=own PT_SDC=own PT_SDC_FILE=$OWN GATE_LIGHT=1" ;;
    iolat) e="env PT_SET=iolat PT_SDC=iolat GATE_LIGHT=1" ;;
  esac
  step pt_${v}_${rc}_${lib} $LK bash -c "cd pt && $e scripts/run_one.sh $PA $rc $lib $pw"
done; done; done
for rc in nom min max; do for lib in tt ss ff; do step measure_${rc}_${lib} $LK bash -c "cd pt && scripts/measure_one.sh $PA $rc $lib"; done; done
step iolat_tables bash -c "cd pt && python3 -I scripts/mk_iolat_tables.py"
for v in arm shared; do for rc in nom min max; do for lib in tt ss ff; do
  step pv_${v}_${rc}_${lib} $LK bash -c "cd pt && scripts/run_iolat_pv.sh $v $PA $rc $lib"
done; done; done
if [ "${B8_MAGIC:-0}" = 1 ]; then
  step magic_drc $LK bash -c "cd drclvs && GUARD_RSS_GB=11 MDRC_TIMEOUT=${MDRC_TIMEOUT:-43200} EXTRACT_TIMEOUT=${EXTRACT_TIMEOUT:-18000} make ARM=$A SRAM_MODE=real MDRC_STD=${MDRC_STD:-gds} mdrc mdrc-class > runs/${A}_mdrc_real.make.log 2>&1"
fi
echo "$(date +%T) chain_b8_${ARM}_all done" >> $L
