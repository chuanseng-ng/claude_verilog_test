#!/bin/bash
# chain_b5j_pt.sh -- neutral PT judge of Innovus b5j (arm innovusb5j): 3 SDC variants x 9 corners, strictly one pt_shell at a time, gated on the host.
# NOTE: the "own" variant deliberately reuses b5h's PT-readable own SDC (b5j's exported SDC is identical to b5h's; md5 checked in the report).
#   variants: base (shared SDC, runs/), iolat (runs_iolat/), own (Innovus b5j's own exported SDC, runs_own/)
cd "$(dirname "$0")/.."
OWN=pnr/commercial/constraints/sky130_cpu_innovus_b5h_own_pt.sdc
run() { # <set> <sdc> <rc> <lib>
  pw=0; [ $3 = nom ] && [ $4 = tt ] && pw=1
  GATE_LIGHT=1 ../../impl/innovus/scripts/gate_licensed.sh || exit 1
  if [ "$2" = base ]; then env PT_SET= scripts/run_one.sh innovusb5j $3 $4 $pw
  elif [ "$2" = own ]; then PT_SET=own PT_SDC=own PT_SDC_FILE=$OWN scripts/run_one.sh innovusb5j $3 $4 $pw
  else PT_SET=$1 PT_SDC=$2 scripts/run_one.sh innovusb5j $3 $4 $pw; fi
  echo "$(date +%T) $2 $3_$4 rc=$?"
}
for v in ${VARIANTS:-own base iolat}; do for rc in nom min max; do for lib in tt ss ff; do run $v $v $rc $lib; done; done; done
echo "$(date +%T) PT chain done"
