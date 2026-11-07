#!/bin/bash
# chain_b5k.sh -- b5k round 2.  In place on b5j's 05j_taps db.  Stage A: 05k_mc_eco (mc, hold, drv phases; env PHASES), every Innovus under the host-wide flock.  Waits for the min/max capTables.
cd "$(dirname "$0")/.."
export B5H=1 B5C_SCREEN=1 B5D=1 B5F=1 B5C_STRAP=0
T=b5k_innovus; mkdir -p runs/$T/dbs; L=runs/$T/chain.log; LOCK=/tmp/claude-1001/licensed_tool.lock
until [ -s captbl6/sky130A_min_li1m1.captbl ] && [ -s captbl6/sky130A_max_li1m1.captbl ]; do sleep 120; done
[ -d runs/$T/dbs/05j_taps.enc.dat ] || { cp -r runs/b5j_innovus/dbs/05j_taps.enc runs/b5j_innovus/dbs/05j_taps.enc.dat runs/$T/dbs/; echo "copied b5j 05j_taps db" >> $L; }
lrun() { # <stage> [label-env]
  echo "$(date +%T) wait lock $1" >> $L
  flock $LOCK bash -c "scripts/gate_host.sh || exit 1; echo \"\$(date +%T) start $1\" >> $L; scripts/run_stage.sh $1 $T > runs/$T/$1.out 2>&1; echo \"\$(date +%T) end $1 rc=\$?\" >> $L"
}
PHASES=${PHASES:-mc} lrun 05k_mc_eco
