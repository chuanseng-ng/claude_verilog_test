#!/bin/bash
# chain_ob3_lec.sh -- LEC of the OpenROAD generation B3 final netlist (step 9).  Hops that do not depend on the layout (RTL == sv2v, sv2v == Yosys netlist when the B3 Yosys netlist is byte-identical to B2's)
# are NOT re-run: the md5 check below decides.  Re-run here: Formality final(no diode / with diode) == Yosys netlist, Formality negative controls (fwdb_inv, swap; each vs syn and vs rtl),
# Yosys equiv_induct sv2v == final netlist + two Yosys mutants.  One tool at a time (licensed_lock), >= 60 s between starts, resumable (runs/<tag>/CHAIN_DONE).
set -u
REPO=/home/RD/ryan/Desktop/Github/claude_verilog_test
H=$REPO/pnr/commercial/signoff/lec
F=$H/formality; Y=$H/yosys
LOCK=$REPO/pnr/commercial/pdk/sky130/scripts/licensed_lock.sh
export SAFE_MIN_AVAIL_GB=6 SAFE_MAX_LOAD=6
NL=$REPO/pnr/commercial/runs/openroad_b3/rv32i_cpu_top.nl.v
SYN=$REPO/pnr/sky130/cpu/runs/b3_openroad/06-yosys-synthesis/rv32i_cpu_top.nl.v
[ -s $NL ] && [ -s $SYN ] || { echo "B3 netlists missing"; exit 1; }
B2SYN=$REPO/pnr/sky130/cpu/runs/b2_openroad/06-yosys-synthesis/rv32i_cpu_top.nl.v
echo "syn md5 B3 $(md5sum < $SYN | cut -c1-32) B2 $(md5sum < $B2SYN | cut -c1-32)"
cd $F
MK="OR_NL=$NL OR_NL_MD5=$(md5sum < $NL | cut -c1-32) OR_SYN=$SYN OR_SYN_MD5=$(md5sum < $SYN | cut -c1-32) ORP=$F/runs/orb3_phys.nl.v ORN=$F/runs/orb3_nodiode.nl.v ORMUT=$F/runs/mutant_orb3"
last=0; gate() { local now=$(date +%s); [ $((now-last)) -lt 60 ] && sleep $((60-(now-last))); last=$(date +%s); }
make -s lec-or-prep $MK > runs/orb3_prep.log 2>&1 || { echo PREP FAILED; cat runs/orb3_prep.log; exit 1; }
job() { # tag impl ref
  local tag=$1 impl=$2 ref=$3
  [ -f runs/$tag/CHAIN_DONE ] && { echo "skip $tag"; return; }
  gate; echo "$(date +%T) START $tag"
  $LOCK make -s lec-or-run $MK IMPL=$impl REF=$ref DCNL=$SYN TAG=$tag > runs/${tag}.make.log 2>&1
  echo "$(date +%T) END $tag rc=$? : $(grep -E '^Verification (SUCCEEDED|FAILED|INCONCLUSIVE)' runs/$tag/fm.log 2>/dev/null | tail -1)"
  touch runs/$tag/CHAIN_DONE
}
job orb3_nodiode_vs_syn $F/runs/orb3_nodiode.nl.v syn
job orb3_phys_vs_syn    $F/runs/orb3_phys.nl.v    syn
for m in fwdb_inv swap; do python3 -I $F/scripts/mk_mutant_openroad.py $F/runs/orb3_phys.nl.v $F/runs/mutant_orb3_$m.nl.v $m || exit 1; done
for m in fwdb_inv swap; do job orb3_negctl_syn_$m $F/runs/mutant_orb3_$m.nl.v syn; job orb3_negctl_rtl_$m $F/runs/mutant_orb3_$m.nl.v rtl; done
cd $Y
for spec in "ob3_e5_final:$F/runs/orb3_nodiode.nl.v" "ob3_e6_neg_fwdb_inv:$F/runs/mutant_orb3_fwdb_inv.nl.v" "ob3_e7_neg_swap:$F/runs/mutant_orb3_swap.nl.v"; do
  tag=${spec%%:*}; nl=${spec#*:}
  [ -f runs/$tag/CHAIN_DONE ] && continue
  gate; bash scripts/run_equiv.sh $tag $nl; sleep 5
done
echo "$(date +%T) chain_ob3_lec done"
