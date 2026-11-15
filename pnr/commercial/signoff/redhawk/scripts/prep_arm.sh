#!/bin/bash
# prep_arm.sh <arm> -- STEP 8: PrimePower per-instance power + .timing (run_pt_export.sh), pad list (gen_ploc.py), instance power file (gen_ipf.py) for one arm.  Skips if runs/<arm>/rh/power.ipf exists.
set -eu
arm=$1; HERE=$(cd "$(dirname "$0")" && pwd); RH=$(cd "$HERE/.." && pwd); ROOT=$(cd "$RH/../../../.." && pwd)
. $ROOT/pnr/commercial/signoff/pt/scripts/arms.sh
case $arm in
  icc2b9) DEF=$ROOT/pnr/commercial/impl/icc2/runs/b9_icc2/out/rv32i_cpu_top.def ;;
  icc2b12) DEF=$ROOT/pnr/commercial/impl/icc2/runs/b12_icc2/out/rv32i_cpu_top.def ;;
  innovusb11) DEF=$ROOT/pnr/commercial/impl/innovus/runs/b11_innovus/out/rv32i_cpu_top.def ;;
  openroad) DEF=$ROOT/pnr/commercial/runs/openroad/rv32i_cpu_top.def ;;
  *) echo "arm?" >&2; exit 2 ;;
esac
R=$RH/runs/$arm; mkdir -p $R/rh
[ -s $R/rh/power.ipf ] && { echo "skip $arm (power.ipf exists)"; exit 0; }
[ -f $R/pt/.done ] || bash $HERE/run_pt_export.sh $arm
python3.11 -I $HERE/gen_ploc.py $DEF $R/rh/pg.ploc
python3.11 -I $HERE/gen_ipf.py $DEF $R/pt/instance_power.txt $R/rh/power.ipf
echo "prep $arm done"
