#!/bin/bash
# chain_inn_b6_c.sh -- b6 part C (waits for part B): DRAFT finish -> open-deck KLayout DRC + OpenROAD antenna on the draft -> pin-stub and antenna-diode lists -> 05m_eco -> FINAL finish + restream.
#   Then calls the verification chain (signoff/chain_innb6_all.sh).
cd "$(dirname "$0")/.."; source scripts/b6lib.sh
SO=../../signoff; D=$SO/drclvs
until [ -f runs/$T/b6done/05m_post.done ]; do grep -q "STOP:" $L && { echo "part B stopped - part C exits" >> $L; exit 1; }; sleep 60; done
stage 06_draft 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=05_route || exit 1
if [ ! -d runs/$T/out_draft ]; then cp -r runs/$T/out runs/$T/out_draft; fi
mkdir -p $D/runs/innovus_b6draft/logs
for t in inspect fixgds kdrc antenna; do
  job draft_$t $LK bash -c "make -C $D ARM=innovus_b6draft PIN_MODE=none $t > $D/runs/innovus_b6draft/logs/make_$t.log 2>&1"
done
python3 -I scripts/mk_pinstub_list.py $D/runs/innovus_b6draft/kdrc/drc_violations.klayout.xml runs/$T/out_draft/rv32i_cpu_top.def runs/$T/b6_pinstub_list.tcl >> $L 2>&1
python3 -I scripts/ant_to_pins.py $D/reports/innovus_b6draft_antenna.rpt runs/$T/b6_ant_list.tcl >> $L 2>&1
stage 05m_eco 05m_eco 05m_eco STUBLIST=$PWD/runs/$T/b6_pinstub_list.tcl ANTLIST=$PWD/runs/$T/b6_ant_list.tcl FROM_LABEL=05_route || exit 1
stage 06_final 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=05m_eco || exit 1
stage 07_restream 07_restream "" SKIP_CONN=1 || exit 1
echo "$(date +%T) chain C done (final out/ written)" >> $L
bash ../../signoff/chain_innb6_all.sh >> $L 2>&1
echo "$(date +%T) chain C+verification done" >> $L
