#!/bin/bash
# chain_inn_b7.sh -- Innovus b7 = b6 + one combined ECO pass (dcache dout0 buffer, 2 deck-antenna sinks), then the b6 finish + restream recipe.  Resumable (b6lib.sh markers in runs/b7_innovus/b6done).
#   07_eco     : scripts/07m_eco.tcl  FROM_LABEL=05m_eco (copied into runs/b7_innovus/dbs)  -> label 07_eco
#   07_final   : 06m_finish NPC2FIX=1 FROM_LABEL=07_eco  -> out/ (netlists, DEF, GDS, SDC, SPEF)
#   07_restream: 07_restream SKIP_CONN=1
cd "$(dirname "$0")/.."; export T=b7_innovus; source scripts/b6lib.sh
stage 07_eco 07m_eco 07_eco DOUTLIST=$PWD/runs/$T/dout0_violators_b6.txt ANTLIST=$PWD/runs/$T/ant_pins_b6.tcl FROM_LABEL=05m_eco OUT_LABEL=07_eco || exit 1
stage 07_final 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=07_eco || exit 1
stage 07_restream 07_restream "" SKIP_CONN=1 || exit 1
echo "$(date +%T) chain b7 done (final out/ written)" >> $L
