#!/bin/bash
# chain_or.sh -- detached, resumable B2 OpenROAD LEC chain (hop structure: RTL == sv2v [fm_lec_or_frontend.tcl]; sv2v == Yosys netlist == OpenROAD final netlist [fm_lec_icc2.tcl REFMODE=sv2v|dc]).
# One fm_shell at a time (licensed_lock.sh), >=60 s between job starts, safe_run.sh gates load<6 and MemAvailable>=6G.  A job is skipped when runs/<tag>/CHAIN_DONE exists.
set -u
HERE=/home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/commercial/signoff/lec/formality
REPO=/home/RD/ryan/Desktop/Github/claude_verilog_test
LOCK=$REPO/pnr/commercial/pdk/sky130/scripts/licensed_lock.sh
export SAFE_MIN_AVAIL_GB=6 SAFE_MAX_LOAD=6
OR_SYN=$REPO/pnr/sky130/cpu/runs/b2_openroad/06-yosys-synthesis/rv32i_cpu_top.nl.v
SV2V=$REPO/pnr/sky130/cpu/rv32i_cpu_top_sv2v.v
cd "$HERE"
last=0
gate() { local now=$(date +%s); [ $((now-last)) -lt 60 ] && sleep $((60-(now-last))); last=$(date +%s); }
job() { # tag impl ref(syn|sv2v)
  local tag=$1 impl=$2 ref=$3 dcnl
  [ -f runs/$tag/CHAIN_DONE ] && { echo "skip $tag"; return; }
  [ $ref = syn ] && dcnl=$OR_SYN || dcnl=$SV2V
  gate; echo "$(date +%T) START $tag"
  $LOCK make -s lec-or-run IMPL=$impl REF=$ref DCNL=$dcnl TAG=$tag > runs/${tag}.make.log 2>&1
  local rc=$?
  echo "$(date +%T) END $tag rc=$rc : $(grep -E '^Verification (SUCCEEDED|FAILED|INCONCLUSIVE)' runs/$tag/fm.log 2>/dev/null | tail -1)"
  touch runs/$tag/CHAIN_DONE
}
fe() { # tag sv2v-file
  local tag=$1 f=$2
  [ -f runs/$tag/CHAIN_DONE ] && { echo "skip $tag"; return; }
  gate; echo "$(date +%T) START $tag"
  $LOCK make -s lec-or-fe OR_SV2V=$f TAG=$tag > runs/${tag}.make.log 2>&1
  local rc=$?
  echo "$(date +%T) END $tag rc=$rc : $(grep -E '^Verification (SUCCEEDED|FAILED|INCONCLUSIVE)' runs/$tag/fm.log 2>/dev/null | tail -1)"
  touch runs/$tag/CHAIN_DONE
}
make -s lec-or-prep > runs/or_prep.log 2>&1 || { echo "PREP FAILED"; exit 1; }
cat runs/or_prep.log
fe  or_fe_rtl_vs_sv2v $SV2V
job or_phys_vs_sv2v    $HERE/runs/or_phys.nl.v    sv2v
job or_nodiode_vs_sv2v $HERE/runs/or_nodiode.nl.v sv2v
job or_syn_vs_sv2v     $OR_SYN                    sv2v
job or_nodiode_vs_syn  $HERE/runs/or_nodiode.nl.v syn
job or_phys_vs_syn     $HERE/runs/or_phys.nl.v    syn
for m in fwdb_inv swap bufinv tiehi; do python3 -I scripts/mk_mutant_openroad.py runs/or_phys.nl.v runs/mutant_or_$m.nl.v $m || exit 1; done
for m in fwdb_inv swap; do python3 -I scripts/mk_mutant_sv2v.py $SV2V runs/mutant_sv2v_$m.v $m || exit 1; done
job or_negctl_sv2v_fwdb_inv $HERE/runs/mutant_or_fwdb_inv.nl.v sv2v
job or_negctl_syn_fwdb_inv  $HERE/runs/mutant_or_fwdb_inv.nl.v syn
job or_negctl_sv2v_swap     $HERE/runs/mutant_or_swap.nl.v     sv2v
job or_negctl_syn_swap      $HERE/runs/mutant_or_swap.nl.v     syn
job or_negctl_sv2v_bufinv   $HERE/runs/mutant_or_bufinv.nl.v   sv2v
job or_negctl_sv2v_tiehi    $HERE/runs/mutant_or_tiehi.nl.v    sv2v
fe  or_negctl_fe_fwdb_inv $HERE/runs/mutant_sv2v_fwdb_inv.v
fe  or_negctl_fe_swap     $HERE/runs/mutant_sv2v_swap.v
echo "CHAIN COMPLETE $(date +%T)"; touch runs/CHAIN_OR_COMPLETE
