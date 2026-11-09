#!/bin/bash
# chain_inn_b8.sh -- Innovus b8: the b6 flow on the FLIPPED I-cache floorplan (MACRO_CFG=macro_placement_flipic.cfg) + the b7 ECO set with dout0 buffers on every max-cap pin.  Resumable (b6lib.sh markers in runs/b8_innovus/b6done).
#   A/B : 01_floorplan 02_pdn 03_place 04_cts 05a_route 05m_post          (as chain_inn_b6_a/b)
#   C   : draft finish (06m_finish FROM_LABEL=05_route) -> out_draft -> deck KLayout + OpenROAD antenna on it -> pin-stub / diode lists -> StarRC + PT judge on the draft (b8_lists.sh) -> dout0 list
#         -> 08m_eco (stubs, diodes, dout0 buffers) -> deck antenna on its pre-fill DEF -> FINAL finish + restream.  Residual deck antenna after 08_eco is NOT auto-fixed: see runs/b8_innovus/chain.log.
cd "$(dirname "$0")/.."; export T=b8_innovus MACRO_CFG=macro_placement_flipic.cfg; source scripts/b6lib.sh
SO=../../signoff; D=$SO/drclvs
stage 01_floorplan 01_floorplan 01_floorplan || exit 1
stage 02_pdn 02_pdn 02_pdn || exit 1
stage 03_place 03_place 03_place || exit 1
stage 04_cts 04_cts 04_cts || exit 1
stage 05a_route 05a_route 05a_routed || exit 1
stage 05m_post 05m_post 05_route || exit 1
stage 06_draft 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=05_route || exit 1
[ -d runs/$T/out_draft ] || cp -r runs/$T/out runs/$T/out_draft
mkdir -p $D/runs/innovus_b8draft/logs
for t in inspect fixgds kdrc antenna; do
  job draft_$t $LK bash -c "make -C $D ARM=innovus_b8draft PIN_MODE=none $t > $D/runs/innovus_b8draft/logs/make_$t.log 2>&1"
done
python3 -I scripts/mk_pinstub_list.py $D/runs/innovus_b8draft/kdrc/drc_violations.klayout.xml runs/$T/out_draft/rv32i_cpu_top.def runs/$T/b8_pinstub_list.tcl >> $L 2>&1
python3 -I scripts/ant_to_pins.py $D/reports/innovus_b8draft_antenna.rpt runs/$T/b8_ant_list.tcl >> $L 2>&1
job lists $SO/b8_lists.sh innovus
stage 08_eco 08m_eco 08_eco STUBLIST=$PWD/runs/$T/b8_pinstub_list.tcl ANTLIST=$PWD/runs/$T/b8_ant_list.tcl DOUTLIST=$PWD/runs/$T/dout0_all.txt FROM_LABEL=05_route OUT_LABEL=08_eco || exit 1
mkdir -p $D/runs/innovus_b8pre/logs
job pre_antenna $LK bash -c "make -C $D ARM=innovus_b8pre PIN_MODE=none antenna > $D/runs/innovus_b8pre/logs/make_antenna.log 2>&1"
stage 06_final 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=08_eco || exit 1
stage 07_restream 07_restream "" SKIP_CONN=1 || exit 1
echo "$(date +%T) chain b8 done (final out/ written)" >> $L
