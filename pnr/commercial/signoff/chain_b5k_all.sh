#!/bin/bash
# chain_b5k_all.sh -- b5k verification, ONE heavy tool at a time (open tools included), host-staggered: before each job wait for loadavg1 < 6 and MemAvailable > 6 GB, then >= 60 s since the previous job started.
#   (run 2: legalised antenna diodes; run 1 superseded; DEF-mode LVS dropped, GDS-mode LVS only; LEC tags b4l_*)  open decks (arm innovus_b5k, no Magic DRC by user decision) -> Conformal LEC (flock) -> StarRC nom/min/max (flock) -> PT judge 27 runs (flock).
cd "$(dirname "$0")"
L=chain_b5k_all.log; LAST=0
stagger() {
  local now; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do
    l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo)
    [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; sleep 20
  done
  LAST=$(date +%s)
}
A=innovus_b5k; mkdir -p drclvs/runs/$A/logs
for t in inspect fixgds lvs-gds-extract lvs-gds-variants lvs-gds-netgen kdrc antenna; do
  stagger; echo "$(date +%T) start drclvs $t" >> $L
  (cd drclvs && make ARM=$A PIN_MODE=none $t > runs/$A/logs/make_$t.log 2>&1); echo "$(date +%T) end drclvs $t rc=$?" >> $L
done
(cd drclvs && make ARM=$A summary > runs/$A/logs/make_summary.log 2>&1)
stagger; echo "$(date +%T) start LEC" >> $L
flock /tmp/claude-1001/licensed_tool.lock make -C lec/conformal lec-innovus-all INNTAG=b5k_innovus STEP=b4l > lec/conformal/b4l_make.log 2>&1; echo "$(date +%T) end LEC rc=$?" >> $L
for c in nom min max; do
  stagger; echo "$(date +%T) start starrc $c" >> $L
  CORNERS=$c bash starrc/scripts/chain_b5k_starrc.sh >> $L 2>&1
done
echo "$(date +%T) end StarRC" >> $L
for v in own base iolat; do for rc in nom min max; do for lib in tt ss ff; do
  stagger; VARIANTS=$v bash -c 'cd pt; true' ; echo "$(date +%T) start PT $v $rc $lib" >> $L
  (cd pt && pw=0; [ $rc = nom ] && [ $lib = tt ] && pw=1
   LK="flock /tmp/claude-1001/licensed_tool.lock"
   if [ $v = base ]; then $LK env PT_SET= GATE_LIGHT=1 scripts/run_one.sh innovusb5k $rc $lib $pw
   elif [ $v = own ]; then $LK env PT_SET=own PT_SDC=own PT_SDC_FILE=pnr/commercial/constraints/sky130_cpu_innovus_b5k_own_pt.sdc GATE_LIGHT=1 scripts/run_one.sh innovusb5k $rc $lib $pw
   else $LK env PT_SET=iolat PT_SDC=iolat GATE_LIGHT=1 scripts/run_one.sh innovusb5k $rc $lib $pw; fi) >> $L 2>&1
done; done; done
echo "$(date +%T) end PT chain" >> $L
