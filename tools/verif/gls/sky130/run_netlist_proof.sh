#!/usr/bin/env bash
# Gate-vs-RTL proof of one Sky130 rv32i_cpu_top netlist against the CURRENT RTL tree (bead dud4, S2/S4).
#   run_netlist_proof.sh <netlist.nl.v> <workdir> [negctl]
# Builds the RTL arm (this checkout's rtl/) and the gate arm (given netlist, CONB_FIX), generates the six
# programs, runs both arms, then prints: census (flops, fwd_b_* nets), per-program compare, and the
# 31-register x {rs1,rs2,both,dbg} matrix. With a third arg "negctl" it also builds a fault arm (tie A1=0 on every
# x1 first-level read-mux cell) and shows that the differential detects it.
# Never run this while a LibreLane job is running (15 GB host). Verilator 5.048 via build_arm.sh defaults.
# Exit 0 only if all six programs are IDENTICAL and the matrix has 0 FAIL.
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../../.." && pwd)"
NL="$1"
W="$2"
mkdir -p "$W"
python3 "$REPO/tools/verif/check_cpu_netlist_census.py" "$NL" || echo "CENSUS FAILED"
bash "$HERE/gen_all_progs.sh" "$W/progs" > "$W/progs.log" 2>&1
RTL_ROOT="$REPO" bash "$HERE/build_arm.sh" rtl "$W/rtl_arm" > "$W/build_rtl.out" 2>&1
CONB_FIX=1 bash "$HERE/build_arm.sh" gate "$W/gate_arm" "$NL" > "$W/build_gate.out" 2>&1
bash "$HERE/run_arm.sh" "$W/rtl_arm" "$W/progs"
bash "$HERE/run_arm.sh" "$W/gate_arm" "$W/progs"
python3 "$HERE/compare_arms.py" diff "$W/rtl_arm/run" "$W/gate_arm/run" | tee "$W/compare.out"
python3 "$HERE/port_matrix.py" "$W/gate_arm/run" "$W/progs" | tee "$W/matrix.out"
if [ "${3:-}" = "negctl" ]; then
  CELLS="$(python3 "$HERE/find_x1_read_cells.py" "$NL")"
  python3 "$HERE/inject_fault.py" tie1 "$NL" "$W/fault.nl.v" $CELLS
  CONB_FIX=1 bash "$HERE/build_arm.sh" gate "$W/gate_fault" "$W/fault.nl.v" > "$W/build_fault.out" 2>&1
  bash "$HERE/run_arm.sh" "$W/gate_fault" "$W/progs"
  python3 "$HERE/compare_arms.py" diff "$W/rtl_arm/run" "$W/gate_fault/run" | grep -E "IDENTICAL|DIVERGES"
  python3 "$HERE/port_matrix.py" "$W/gate_fault/run" "$W/progs" | tail -n 1
fi
ident="$(grep -c 'IDENTICAL' "$W/compare.out")"
fails="$(tail -n 1 "$W/matrix.out" | sed -E 's/.*FAIL ([0-9]+).*/\1/')"
echo "SUMMARY: programs identical $ident/6, matrix FAIL $fails"
[ "$ident" = 6 ] && [ "$fails" = 0 ]
