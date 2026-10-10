#!/usr/bin/env bash
# usage: equiv_probe.sh <yosys> <outdir> <probe-name>  -- miter-compare synlig vs sv2v elaboration
set -u
Y=$1; OUT=$2; N=$3
cat > "$OUT/$N.eq.ys" <<EOF
read_rtlil $OUT/$N.synlig.il
hierarchy -top top
proc; flatten; opt_clean
design -stash a
read_rtlil $OUT/$N.sv2v.il
hierarchy -top top
proc; flatten; opt_clean
design -stash b
design -reset
design -copy-from a -as gold top
design -copy-from b -as gate top
miter -equiv -make_assert gold gate miter
hierarchy -top miter
flatten
opt_clean
sat -verify -prove-asserts -show-ports miter
EOF
"$Y" -q -l "$OUT/$N.eq.log" "$OUT/$N.eq.ys" > /dev/null 2>&1
echo "$N rc=$?"
grep -E "SUCCESS|FAIL|Warning|ERROR" "$OUT/$N.eq.log" | head -5
