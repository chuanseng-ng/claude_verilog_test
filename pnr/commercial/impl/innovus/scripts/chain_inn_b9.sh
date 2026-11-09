#!/bin/bash
# chain_inn_b9.sh -- Innovus b9 = b8 final pre-fill db (08b_eco, copied into runs/b9_innovus/dbs) + ONE optDesign ECO round (09m_eco) + the b6/b8 finish + restream recipe.  Resumable (b6lib.sh markers in runs/b9_innovus/b6done).
#   09_eco     : scripts/09m_eco.tcl FROM_LABEL=08b_eco -> label 09_eco
#   09_final   : 06m_finish NPC2FIX=1 FROM_LABEL=09_eco -> out/ (netlists, DEF, GDS, SDC, SPEF)   (verifyConnectivity -type all RUNS: the b8 skip was unnecessary, doc caveat 8)
#   09_restream: 07_restream SKIP_CONN=1
cd "$(dirname "$0")/.."; export T=b9_innovus MACRO_CFG=macro_placement_flipic.cfg; source scripts/b6lib.sh
SO=../../signoff; D=$SO/drclvs
stage 09_eco 09m_eco 09_eco ${ECO_ENV:-SETUP_TS=0.20} FROM_LABEL=08b_eco OUT_LABEL=09_eco || exit 1
mkdir -p $D/runs/innovus_b9pre/logs
job pre_antenna $LK bash -c "make -C $D ARM=innovus_b9pre PIN_MODE=none antenna > $D/runs/innovus_b9pre/logs/make_antenna.log 2>&1"
stage 09_final 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=09_eco || exit 1
stage 09_restream 07_restream "" SKIP_CONN=1 || exit 1
echo "$(date +%T) chain b9 done (final out/ written)" >> $L
