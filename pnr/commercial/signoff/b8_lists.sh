#!/bin/bash
# b8_lists.sh <icc2|innovus> -- derive the b8 ECO lists from the pre-ECO design: StarRC nom/min/max on the pre-ECO DEF, PT judge (base SDC) at 9 corners, then
#   eco_in/dout0_all.txt   union over the 9 corners of the SRAM dout0 max-cap violators ("pt-name cap", worst cap per pin)
#   eco_in/hold_endpoints.txt (icc2 only)  reg->reg endpoints with hold slack < +12 ps at nom/min/max ff (diag_hold_r2r.tcl)
# Resumable (signoff/b8_lists/<arm>_<step>.done); one licensed tool at a time (licensed_lock.sh); host-staggered like chain_b7_all.sh.
cd "$(dirname "$0")"; ARM=$1; M=b8_lists; mkdir -p $M; L=b8_lists.log; LAST=0
LK=../pdk/sky130/scripts/licensed_lock.sh
case $ARM in
  icc2) PA=icc2b8pre; ECO=../impl/icc2/runs/b8_icc2/eco_in ;;
  innovus) PA=innovusb8draft; ECO=../impl/innovus/runs/b8_innovus ;;
esac
stagger() { local now l a; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1048576}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; sleep 20; done; LAST=$(date +%s); }
step() { local n=${ARM}_$1; shift; [ -f $M/$n.done ] && return; stagger; echo "$(date +%T) start $n" >> $L; "$@" > $M/$n.out 2>&1; local rc=$?; echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > $M/$n.done; }
for c in nom min max; do step starrc_$c $LK bash -c "GATE_LIGHT=1 ../impl/innovus/scripts/gate_host.sh && cd starrc && scripts/run_starrc.sh $PA $c > runs/${PA}_$c.out 2>&1"; done
for rc in nom min max; do for lib in tt ss ff; do step pt_${rc}_${lib} $LK bash -c "cd pt && env PT_SET= GATE_LIGHT=1 scripts/run_one.sh $PA $rc $lib 0"; done; done
mkdir -p $ECO
for c in nom_tt nom_ss nom_ff min_tt min_ss min_ff max_tt max_ss max_ff; do grep VIOLATED pt/runs/${PA}_$c/constraint_drv.txt | grep 'dout0\[' | awk '{print $1, $3}'; done | sort -k1,1 -k2,2gr | awk '!s[$1]++' > $ECO/dout0_all.txt
echo "$(date +%T) dout0 list: $(wc -l < $ECO/dout0_all.txt) pins -> $ECO/dout0_all.txt" >> $L
if [ $ARM = icc2 ]; then
  S=$PWD/b8_lists/hold; for r in nom min max; do step hold_$r $LK bash -c "cd pt && HOLD_BELOW=0.012 scripts/diag_one.sh $PA $r ff diag_hold_r2r.tcl $S"; done
  for r in nom min max; do grep "^HOLDR2R" $S/diag_hold_r2r_${PA}_${r}_ff.log | awk '$2<0.012{print $5}'; done | sort -u > $ECO/hold_endpoints.txt
  echo "$(date +%T) hold endpoints: $(wc -l < $ECO/hold_endpoints.txt) -> $ECO/hold_endpoints.txt" >> $L
fi
echo "$(date +%T) b8_lists $ARM done" >> $L
