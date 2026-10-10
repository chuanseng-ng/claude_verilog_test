#!/usr/bin/env bash
# Initialisation-sensitivity check: rerun both arms with Verilator's randomised
# initial state (+verilator+rand+reset+2) under several seeds and report
#   (a) rtl arm vs gate arm for each seed, and
#   (b) each arm vs its own zero-initialised run (must be IDENTICAL, else the
#       result depends on power-up state and the comparison is not trustworthy).
# usage: rand_check.sh <work_dir containing rtl_arm/ gate_arm/ progs/> seed...
set -u
W="$1"; shift
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
for s in "$@"; do
  for a in rtl_arm gate_arm; do
    RUN_TAG="rand$s" bash "$HERE/run_arm.sh" "$W/$a" "$W/progs" +verilator+rand+reset+2 "+verilator+seed+$s" > /dev/null 2>&1
  done
  echo "== seed $s: rtl vs gate"
  python3 "$HERE/compare_arms.py" diff "$W/rtl_arm/rand$s" "$W/gate_arm/rand$s" | grep -E "IDENTICAL|DIVERGES"
  echo "== seed $s: rtl rand vs rtl zero-init"
  python3 "$HERE/compare_arms.py" diff "$W/rtl_arm/run" "$W/rtl_arm/rand$s" | grep -E "IDENTICAL|DIVERGES"
  echo "== seed $s: gate rand vs gate zero-init"
  python3 "$HERE/compare_arms.py" diff "$W/gate_arm/run" "$W/gate_arm/rand$s" | grep -E "IDENTICAL|DIVERGES"
done
