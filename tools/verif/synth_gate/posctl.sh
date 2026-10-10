#!/usr/bin/env bash
WT=/home/neuromorphic/Downloads/Github/claude_verilog_test/.claude/worktrees/agent-a04c889d44fbc5a06
G=/nobackup/claude_sim_build/gc0y/neg
LL=$HOME/Downloads/Github/librelane
rm -rf $G/pos/cfg/runs
CMD="PYTHONPATH=$WT/pnr/plugins python3 -m librelane --run-tag synth --to Checker.NetlistAssignStatements $G/pos/cfg/config.json"
( cd $LL && systemd-run --user --scope -p MemoryMax=5G -p MemorySwapMax=0 timeout 1800 \
    nix-shell $LL/shell.nix --run "$CMD" ) > $G/pos/run.log 2>&1
echo "pos rc=$?" | tee $G/pos/rc.txt
touch $G/POSDONE
