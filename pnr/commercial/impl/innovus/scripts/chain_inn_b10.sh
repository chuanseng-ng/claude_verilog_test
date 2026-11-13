#!/bin/bash
# chain_inn_b10.sh -- Innovus b10 = b9 final pre-fill db (09_eco, copied into runs/b10_innovus/dbs) + ONE targeted max-transition ECO (10m_eco: spread repeaters on the three apb_prdata_o port nets, three scattered-load nets split)
#   + the b6/b8/b9 finish + restream recipe.  Resumable (b6lib.sh markers in runs/b10_innovus/b6done).
#   10_eco     : scripts/10m_eco.tcl FROM_LABEL=09_eco -> label 10_eco
#   10_final   : 06m_finish NPC2FIX=1 FROM_LABEL=10_eco -> out/ (netlists, DEF, GDS, SDC, SPEF)
#   10_restream: 07_restream SKIP_CONN=1
cd "$(dirname "$0")/.."; export T=b10_innovus MACRO_CFG=macro_placement_flipic.cfg; source scripts/b6lib.sh
SO=../../signoff; D=$SO/drclvs
stage 10_eco 10m_eco 10_eco B10=1 FROM_LABEL=09_eco OUT_LABEL=10_eco || exit 1
mkdir -p $D/runs/innovus_b10pre/logs
job pre_antenna $LK bash -c "make -C $D ARM=innovus_b10pre PIN_MODE=none antenna > $D/runs/innovus_b10pre/logs/make_antenna.log 2>&1"
stage 10_final 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=10_eco || exit 1
stage 10_restream 07_restream "" SKIP_CONN=1 || exit 1
echo "$(date +%T) chain b10 done (final out/ written)" >> $L
