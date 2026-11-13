#!/bin/bash
# chain_inn_b11.sh -- Innovus b11 = b10 final pre-fill db (10_eco, copied into runs/b11_innovus/dbs) + ONE targeted slew ECO (11m_eco: the three b10 repeaters B10N1, u_core/B10N2, u_core/B10N3 resized in place buf_6 -> buf_12; nothing else changes)
#   + the b6/b8/b9 finish + restream recipe.  Resumable (b6lib.sh markers in runs/b11_innovus/b6done).
#   11_eco     : scripts/11m_eco.tcl FROM_LABEL=10_eco -> label 11_eco
#   11_final   : 06m_finish NPC2FIX=1 FROM_LABEL=11_eco -> out/ (netlists, DEF, GDS, SDC, SPEF)
#   11_restream: 07_restream SKIP_CONN=1
cd "$(dirname "$0")/.."; export T=b11_innovus MACRO_CFG=macro_placement_flipic.cfg; source scripts/b6lib.sh
SO=../../signoff; D=$SO/drclvs
stage 11_eco 11m_eco 11_eco B11=1 FROM_LABEL=10_eco OUT_LABEL=11_eco || exit 1
mkdir -p $D/runs/innovus_b11pre/logs
job pre_antenna $LK bash -c "make -C $D ARM=innovus_b11pre PIN_MODE=none antenna > $D/runs/innovus_b11pre/logs/make_antenna.log 2>&1"
stage 11_final 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=11_eco || exit 1
stage 11_restream 07_restream "" SKIP_CONN=1 || exit 1
echo "$(date +%T) chain b11 done (final out/ written)" >> $L
