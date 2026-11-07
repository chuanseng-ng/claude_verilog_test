#!/bin/bash
# chain_b5k_pt_rest.sh -- resume the b5k PT judge after the host crash (chain_b5k_all.log stopped 2026-11-03 02:19:02, last write; last DONE = base min_ss; no shutdown record for that boot):
#   missing = base min_ff, base max_tt/ss/ff, iolat x 9.  run_one.sh skips anything already DONE with an identical input stamp.  One pt_shell at a time under licensed_lock.sh,
#   host-staggered: loadavg1 < 6, MemAvailable > 6 GB, >= 60 s between job starts.
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
LK=../../pdk/sky130/scripts/licensed_lock.sh
echo "$(date +%T) resume PT after host crash" >> $L
for job in "base min ff" "base max tt" "base max ss" "base max ff" $(for rc in nom min max; do for lib in tt ss ff; do echo "iolat_${rc}_${lib}"; done; done); do
  case "$job" in iolat_*) IFS=_ read v rc lib <<< "$job" ;; *) read v rc lib <<< "$job" ;; esac
  stagger; echo "$(date +%T) start PT $v $rc $lib" >> $L
  (cd pt && pw=0; [ $rc = nom ] && [ $lib = tt ] && pw=1
   if [ $v = base ]; then $LK env PT_SET= scripts/run_one.sh innovusb5k $rc $lib $pw
   else $LK env PT_SET=iolat PT_SDC=iolat scripts/run_one.sh innovusb5k $rc $lib $pw; fi) >> $L 2>&1
done
echo "$(date +%T) end PT chain" >> $L
