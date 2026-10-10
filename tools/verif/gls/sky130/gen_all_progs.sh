#!/usr/bin/env bash
# Generate every program of the dud4 differential into <progdir>:
#   ma7_straight.hex   u99's 6-instruction straight-line program (debug-read x4)
#   ma7_branch.hex     ma7 step-1 branch-dependent program (BEQ x2,x3 must be TAKEN)
#   sweepA/B/C.hex     31-register sweep (see gen_regsweep_rom.py), three B/D choices
#   haltcyc.txt        cycles the testbench runs before halting + debug-dumping
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLS="$HERE/.."
D="$1"
mkdir -p "$D"
python3 "$GLS/gen_cpu_check_rom.py" "$D/ma7_straight.hex" 64
python3 "$GLS/gen_cpu_check_rom_branch.py" "$D/ma7_branch.hex" 64
python3 "$HERE/gen_regsweep_rom.py" --base 31 --dest 30 --seed 1 --out "$D/sweepA"
python3 "$HERE/gen_regsweep_rom.py" --base 1 --dest 2 --seed 2 --out "$D/sweepB"
python3 "$HERE/gen_regsweep_rom.py" --base 15 --dest 16 --seed 3 --out "$D/sweepC"
cat > "$D/haltcyc.txt" <<EOF
ma7_straight 400
ma7_branch 800
sweepA 4500
sweepB 4500
sweepC 4500
EOF
