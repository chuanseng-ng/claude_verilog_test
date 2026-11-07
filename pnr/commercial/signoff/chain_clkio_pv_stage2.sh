#!/bin/bash
# chain_clkio_pv_stage2.sh -- detached follow-on of chain_clkio_pv.sh (measure stage): waits for the 27 measurements, builds the tables,
#   runs the PT judge (variant arm = recommended, then shared = sensitivity), then the I/O-violator diagnostic for every run that has I/O violators.
#   Resumable through chain_clkio_pv/*.done (same step() as chain_clkio_pv.sh).  Log: chain_clkio_pv_all.log
cd "$(dirname "$0")"
L=chain_clkio_pv_all.log
while ! grep -q "chain_clkio_pv done (stages: measure)" $L; do sleep 30; done
bad=$(grep -c "end measure_.* rc=[1-9]" $L || true)
[ "$bad" = 0 ] && [ "$(ls chain_clkio_pv/measure_*.done | wc -l)" = 27 ] || { echo "$(date +%T) stage2 ABORT: measurement incomplete/failed" >> $L; exit 1; }
python3 -I pt/scripts/mk_iolat_tables.py >> $L 2>&1 || { echo "$(date +%T) stage2 ABORT: table build failed" >> $L; exit 1; }
CK_STAGES=judge CK_VARIANTS="arm shared" ./chain_clkio_pv.sh
# diagnostic: every judge run whose I/O violator count (total - reg2reg) is > 0
LK=../pdk/sky130/scripts/licensed_lock.sh; M=chain_clkio_pv
for v in arm shared; do
  case $v in arm) d=runs_iolat_pv ;; shared) d=runs_iolat_pvs ;; esac
  for a in openroad icc2b6 innovusb6; do for rc in nom min max; do for lib in tt ss ff; do
    t=${a}_${rc}_${lib}; m=pt/$d/$t/metrics.tsv; n=diag_${v}_$t
    [ -f $M/$n.done ] && continue
    [ -f $m ] || continue
    io=$(awk -F'\t' '$1=="setup_viol"{s=$2} $1=="hold_viol"{h=$2} $1=="r2rx_setup_viol"{a=$2} $1=="r2rx_hold_viol"{b=$2} END{print (s-a)+(h-b)}' $m)
    [ "${io:-0}" -gt 0 ] || { echo 0 > $M/$n.done; continue; }
    while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); a2=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$a2" -gt 6 ] && break; sleep 20; done
    sleep 60
    echo "$(date +%T) start $n" >> $L
    $LK bash -c "cd pt && scripts/run_diag_pv.sh $v $a $rc $lib" > $M/$n.out 2>&1; rc_=$?
    echo "$(date +%T) end $n rc=$rc_" >> $L; echo $rc_ > $M/$n.done
  done; done; done
done
echo "$(date +%T) chain_clkio_pv_stage2 done" >> $L
