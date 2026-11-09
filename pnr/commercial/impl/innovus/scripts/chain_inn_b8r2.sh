#!/bin/bash
# chain_inn_b8r2.sh -- Innovus b8 ECO round 2: the 5 residual deck-antenna sinks of the b8 final layout get a buf_6 (08m_eco ANTBUFLIST, FROM_LABEL=08_eco), then re-finish + restream.  Resumable (b6done/*_r2.done).
cd "$(dirname "$0")/.."; export T=b8_innovus MACRO_CFG=macro_placement_flipic.cfg; source scripts/b6lib.sh
stage 08b_eco 08m_eco 08b_eco ANTBUFLIST=$PWD/runs/$T/b8_ant_buf_r2.tcl FROM_LABEL=08_eco OUT_LABEL=08b_eco || exit 1
stage 06_final_r2 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=08b_eco || exit 1
stage 07_restream_r2 07_restream "" SKIP_CONN=1 || exit 1
echo "$(date +%T) chain b8 round 2 done (final out/ re-written)" >> $L
