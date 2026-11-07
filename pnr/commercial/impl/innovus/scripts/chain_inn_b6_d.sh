#!/bin/bash
# chain_inn_b6_d.sh -- b6 re-finish after the npc.2 rule extension (left-neighbour decap of a non-mirrored and2_0), then the verification chain (markers redone for the layout-dependent steps).
cd "$(dirname "$0")/.."; source scripts/b6lib.sh
stage 06_final 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=05m_eco || exit 1
stage 07_restream 07_restream "" SKIP_CONN=1 || exit 1
echo "$(date +%T) chain D re-finish done" >> $L
bash ../../signoff/chain_innb6_all.sh >> $L 2>&1
echo "$(date +%T) chain D+verification done" >> $L
