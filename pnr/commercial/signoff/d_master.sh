#!/bin/bash
# d_master.sh -- step 9 D: single-netlist P&R comparison.  ONE netlist = the OpenROAD B2 Yosys netlist (06-yosys-synthesis, md5 cb24a60d..., flat, no assigns), run through the
# ICC2 b6 flow and the Innovus b6 flow with NO ECO (floorplan, PDN, place, CTS, route, [post-route opt], finish, write); the OpenROAD arm is B2 itself (same netlist, plain flow, not flipped).
# Same floorplan (macro_placement.cfg, pin template), SDC (sky130_cpu.sdc), PDK, StarRC -> PrimeTime base-SDC judge.  Resumable: d_master/<step>.done.  One heavy tool at a time.
cd "$(dirname "$0")"; M=d_master; mkdir -p $M; L=d_master.log; REPO=$(cd ../../.. && pwd)
export NETLIST_OVERRIDE=$REPO/pnr/sky130/cpu/runs/b2_openroad/06-yosys-synthesis/rv32i_cpu_top.nl.v NL_YOSYS=1
LK=../pdk/sky130/scripts/licensed_lock.sh; LAST=0
stagger() { local now l a; now=$(date +%s); [ $((now-LAST)) -lt 60 ] && sleep $((60-(now-LAST)))
  while :; do l=$(awk '{printf "%d",$1}' /proc/loadavg); a=$(awk '/MemAvailable/{printf "%d",$2/1000000}' /proc/meminfo); [ "$l" -lt 6 ] && [ "$a" -gt 6 ] && break; sleep 20; done; LAST=$(date +%s); }
step() { local n=$1; shift; [ -f $M/$n.done ] && return 0; stagger; echo "$(date +%T) start $n" >> $L; "$@" > $M/$n.out 2>&1; local rc=$?; echo "$(date +%T) end $n rc=$rc" >> $L; echo $rc > $M/$n.done; return 0; }
# ---- ICC2
step icc2_flow env B6_TAG=b6y_icc2 B6_STAGES="b6_01_floorplan b6_02_pdn b6_03_place b6_04_cts b6_05_route b6_07_finish b6_08_write_verilog" B5E_FINISH_BASE=05_route bash ../impl/icc2/scripts/b6_chain.sh
# ---- Innovus (stages as chain_inn_b6_b/c: 01..05m_post, 06m_finish)
cat > $M/inn_chain.sh <<'S'
cd "$(dirname "$0")/../../impl/innovus"; export T=b6y_innovus; source scripts/b6lib.sh
stage 01_floorplan 01_floorplan 01_floorplan || exit 1
stage 02_pdn 02_pdn 02_pdn || exit 1
stage 03_place 03_place 03_place || exit 1
stage 04_cts 04_cts 04_cts || exit 1
stage 05a_route 05a_route 05a_routed || exit 1
stage 05m_post 05m_post 05_route || exit 1
stage 06_final 06m_finish 06_finish NPC2FIX=1 FROM_LABEL=05_route || exit 1
S
step innovus_flow bash $M/inn_chain.sh
# ---- judge: StarRC nom/min/max + PT base x 9 for the two new arms
for PA in icc2b6y innovusb6y; do
  for c in nom min max; do step starrc_${PA}_$c $LK bash -c "GATE_LIGHT=1 ../impl/innovus/scripts/gate_host.sh && cd starrc && scripts/run_starrc.sh $PA $c > runs/${PA}_$c.out 2>&1"; done
  for rc in nom min max; do for lib in tt ss ff; do pw=0; [ $rc = nom ] && [ $lib = tt ] && pw=1
    step pt_${PA}_${rc}_${lib} $LK bash -c "cd pt && env PT_SET= GATE_LIGHT=1 scripts/run_one.sh $PA $rc $lib $pw"; done; done
done
echo "$(date +%T) d_master done" >> $L
