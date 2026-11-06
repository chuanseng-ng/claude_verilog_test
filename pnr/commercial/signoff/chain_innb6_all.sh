#!/bin/bash
# chain_innb6_all.sh -- Innovus b6 verification, resumable, ONE heavy tool at a time (open tools included, licensed_lock.sh), host-staggered (load1 < 6, MemAvailable > 6 GB, >= 60 s between job starts).
#   Marker per step: chain_innb6/<step>.done (rc).  Order (user): GDS LVS (Netgen) -> KLayout DRC -> OpenROAD antenna -> Conformal LEC (4/4 negative controls) -> StarRC nom/min/max -> PT judge 27 runs
#   (own / base / iolat SDC x nom,min,max x tt,ss,ff; PrimePower at nom_tt) -> Magic DRC LAST, alone, ~11 GiB cap, on the final b6 layout only (only if B6_MAGIC=1 or no B6_ONLY).
cd "$(dirname "$0")"
L=chain_innb6_all.log; M=chain_innb6; mkdir -p $M; LAST=0
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
A=innovus_b6; mkdir -p drclvs/runs/$A/logs
D="make -C drclvs ARM=$A PIN_MODE=none"
OUT=../impl/innovus/runs/b6_innovus/out
[ -s $OUT/rv32i_cpu_top.gds ] && [ -s $OUT/rv32i_cpu_top.def ] || { echo "$(date +%T) final out/ missing - verification not started" >> $L; exit 1; }
for t in inspect fixgds; do step drclvs_$t $LK bash -c "$D $t > drclvs/runs/$A/logs/make_$t.log 2>&1"; done
step drclvs_lvs-gds-extract $LK bash -c "$D EXTRACT_TIMEOUT=18000 lvs-gds-extract > drclvs/runs/$A/logs/make_lvs-gds-extract.log 2>&1"
for t in lvs-gds-variants lvs-gds-netgen kdrc antenna; do step drclvs_$t $LK bash -c "$D $t > drclvs/runs/$A/logs/make_$t.log 2>&1"; done
step drclvs_summary bash -c "$D summary > drclvs/runs/$A/logs/make_summary.log 2>&1"
step lec $LK make -C lec/conformal lec-innovus-all INNTAG=b6_innovus STEP=b4m
for c in nom min max; do step starrc_$c $LK bash -c "GATE_LIGHT=1 ../impl/innovus/scripts/gate_host.sh && cd starrc && scripts/run_starrc.sh innovusb6 $c > runs/innovusb6_$c.out 2>&1"; done
OWN=pnr/commercial/constraints/sky130_cpu_innovus_b6_own_pt.sdc
step own_sdc bash -c "cd ../../.. && python3 -I pnr/commercial/constraints/mk_pt_own_sdc.py pnr/commercial/impl/innovus/runs/b6_innovus/out/rv32i_cpu_top.sdc $OWN b6"
for v in own base iolat; do for rc in nom min max; do for lib in tt ss ff; do
  pw=0; [ $rc = nom ] && [ $lib = tt ] && pw=1
  case $v in
    base)  e="env PT_SET= GATE_LIGHT=1" ;;
    own)   e="env PT_SET=own PT_SDC=own PT_SDC_FILE=$OWN GATE_LIGHT=1" ;;
    iolat) e="env PT_SET=iolat PT_SDC=iolat GATE_LIGHT=1" ;;
  esac
  step pt_${v}_${rc}_${lib} $LK bash -c "cd pt && $e scripts/run_one.sh innovusb6 $rc $lib $pw"
done; done; done
if [ "${B6_SKIP_MAGIC:-0}" != 1 ]; then
  step magic_drc $LK bash -c "cd drclvs && GUARD_RSS_GB=11 MDRC_TIMEOUT=${MDRC_TIMEOUT:-43200} EXTRACT_TIMEOUT=${EXTRACT_TIMEOUT:-18000} make ARM=$A SRAM_MODE=real mdrc mdrc-class > runs/${A}_mdrc_real.make.log 2>&1"
fi
echo "$(date +%T) chain_innb6_all done" >> $L
