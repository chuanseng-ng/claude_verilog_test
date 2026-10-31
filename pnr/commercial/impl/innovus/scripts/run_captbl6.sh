#!/bin/bash
# run_captbl6.sh <nom|min|max> -- ICT (li1 renamed) -> Innovus capTable with M1=li1..M6=met5; ~50 min, one Innovus licence, under safe_run.sh
C=${1:-nom}
IMPL=$(cd "$(dirname "$0")/.." && pwd); REPO=$(cd "$IMPL/../../../.." && pwd); PDKDIR=$REPO/pnr/commercial/pdk/sky130
OUTDIR=$IMPL/captbl6; mkdir -p $OUTDIR; python3 -I $IMPL/scripts/mk_ict_li1m1.py $C || exit 1
source $REPO/tools/eda/pd_env.sh >/dev/null 2>&1
export REPO PDKDIR HERE=$PDKDIR CORNER=$C OUTDIR SAFE_MEM_MAX=4G SAFE_THREADS=2 SAFE_TIMEOUT=10800
cd $OUTDIR
/usr/bin/time -v -o $OUTDIR/captbl_$C.time $PDKDIR/scripts/safe_run.sh $OUTDIR/captbl_$C.log innovus -nowin -files $IMPL/scripts/gen_captbl6.tcl -log $OUTDIR/captbl_$C.innovus.log -overwrite
echo "captbl6 $C rc=$?"
