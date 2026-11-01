#!/bin/bash
# chain_b5i_pt.sh -- neutral PT judge of ICC2 b5i (arm icc2b5i): base + iolat SDC x 9 corners, one pt_shell at a time under the host-wide flock.
cd "$(dirname "$0")/.."
run() { # <set> <sdc> <rc> <lib>
  pw=0; [ $3 = nom ] && [ $4 = tt ] && pw=1
  # host-wide licensed-tool lock held for the whole pt_shell lifetime (flock), then the memory gate
  LK="flock /tmp/claude-1001/licensed_tool.lock"
  GT="GATE_LIGHT=1 ../../impl/innovus/scripts/gate_host.sh || exit 1"
  if [ "$2" = base ]; then $LK bash -c "$GT; env PT_SET= scripts/run_one.sh icc2b5i $3 $4 $pw"
  elif [ "$2" = own ]; then $LK bash -c "$GT; PT_SET=own PT_SDC=own PT_SDC_FILE=$OWN scripts/run_one.sh icc2b5i $3 $4 $pw"
  else $LK bash -c "$GT; PT_SET=$1 PT_SDC=$2 scripts/run_one.sh icc2b5i $3 $4 $pw"; fi
  echo "$(date +%T) $2 $3_$4 rc=$?"
}
for v in ${VARIANTS:-base iolat}; do for rc in nom min max; do for lib in tt ss ff; do run $v $v $rc $lib; done; done; done
echo "$(date +%T) PT chain done"
