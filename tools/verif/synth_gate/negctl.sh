#!/usr/bin/env bash
# Negative + positive control of the flow gate (bead gc0y deliverable 2).
# neg: make -C pnr librelane-sky130-cpu on a scratch RTL copy with the 2 hazard lines reverted -> must FAIL naming them
# pos: same recipe env, current RTL, --to Checker.NetlistAssignStatements (synthesis only) -> must PASS the gate
set -u
WT=/home/neuromorphic/Downloads/Github/claude_verilog_test/.claude/worktrees/agent-a04c889d44fbc5a06
G=/nobackup/claude_sim_build/gc0y/neg
LL=$HOME/Downloads/Github/librelane
rm -rf $G; mkdir -p $G
for arm in neg pos; do
  S=$G/$arm/src; mkdir -p $S/pnr/sky130
  cp -r $WT/rtl $S/rtl
  cp -r $WT/pnr/sky130/cpu $S/pnr/sky130/cpu
  cp $WT/pnr/sky130/sky130_sram_1kbyte_1rw1r_32x256_8_stub.v $S/pnr/sky130/
  rm -rf $S/pnr/sky130/cpu/runs $S/pnr/sky130/cpu/macro
  mkdir -p $G/$arm/cfg
  python3 /nobackup/claude_sim_build/dud4/synth/mkcfg.py $S synlig $G/$arm/cfg
done
# revert the two hazard lines in the NEG copy to the old struct-field part-select form
CORE=$G/neg/src/rtl/cpu/core/rv32i_core.sv
sed -i 's/(if_id_rs1_addr_w),/(if_id_reg.instruction[19:15]),/; s/(if_id_rs2_addr_w),/(if_id_reg.instruction[24:20]),/' $CORE
grep -n "if_id_reg.instruction\[" $CORE > $G/neg/reverted_lines.txt
cat $G/neg/reverted_lines.txt

echo "=== NEG: make librelane-sky130-cpu on reverted RTL"
mkdir -p $G/neg/privcwd
( cd $WT/pnr && systemd-run --user --scope -p MemoryMax=5G -p MemorySwapMax=0 timeout 1800 \
    make librelane-sky130-cpu LIBRELANE_SKY130_CPU_DIR=$G/neg/cfg ) > $G/neg/make.log 2>&1
echo "neg make rc=$?" | tee $G/neg/rc.txt

echo "=== POS: same env, current RTL, synthesis only"
CMD="PYTHONPATH=$WT/pnr/plugins python3 -m librelane --run-tag synth --to Checker.NetlistAssignStatements $G/pos/cfg/config.json"
( cd $LL && systemd-run --user --scope -p MemoryMax=5G -p MemorySwapMax=0 timeout 1800 \
    nix-shell $LL/shell.nix --run "$CMD" ) > $G/pos/run.log 2>&1
echo "pos rc=$?" | tee $G/pos/rc.txt
touch $G/DONE
