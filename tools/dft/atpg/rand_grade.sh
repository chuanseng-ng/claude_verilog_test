#!/usr/bin/env bash
# rand_grade.sh CUT.blif OUTDIR N [SEED]
#
# Random-pattern-only coverage of a cut (bead j41m.15): `quaigh atpg -r N` writes N random patterns WITHOUT grading or SAT
# (quaigh 0.0.6 cmd.rs: --num-random switches to random mode), then `quaigh atpg-report` grades them.  Used for the fabric rung, where the
# real deterministic flow breaks the 12 GB cap.  It is a LOWER BOUND on what a pattern set can reach, not an ATPG result: no pattern
# targets a hard fault, and nothing is proven untestable.
set -eu
cut=$1; out=$2; n=$3; seed=${4:-1}
Q=${QUAIGH:-/nobackup/claude_sim_build/j41m15/bin/quaigh}
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out"
# --num-random does not expose flops (it sizes patterns from the primary inputs only), so grade the explicit full-scan view of the cut
python3 -c "import sys; sys.path.insert(0, '$here'); import regrade; open('$out/comb.blif', 'w').write(regrade.to_comb_blif(open('$cut').read()))"
cut=$out/comb.blif
"$Q" atpg "$cut" -r "$n" --seed "$seed" -o "$out/rand_$n.test" > "$out/gen.log" 2>&1
exec "$here/run_capped.sh" "$out/grade_$n" -- "$Q" atpg-report "$cut" "$out/rand_$n.test"
