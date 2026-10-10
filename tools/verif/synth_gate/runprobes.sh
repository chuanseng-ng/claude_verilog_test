#!/usr/bin/env bash
# usage: runprobes.sh <probe_dir> <yosys_bin> <synlig.so|none> <sv2v|none> <outdir>
set -u
PD=$1; Y=$2; SO=$3; SV2V=$4; OUT=$5
mkdir -p "$OUT"
for f in "$PD"/p*.sv; do
  n=$(basename "$f" .sv)
  # Synlig arm
  if [ "$SO" != none ]; then
    cat > "$OUT/$n.synlig.ys" <<EOF
plugin -i $SO
read_systemverilog -sverilog -top top $f
hierarchy -top top
proc
opt_clean
check
write_rtlil $OUT/$n.synlig.il
EOF
    ( cd "$OUT" && timeout 300 "$Y" -q -l "$OUT/$n.synlig.log" "$OUT/$n.synlig.ys" > /dev/null 2>&1 ; echo "rc=$?" >> "$OUT/$n.synlig.log" )
  fi
  # sv2v arm
  if [ "$SV2V" != none ]; then
    "$SV2V" "$f" -w "$OUT/$n.v" > "$OUT/$n.sv2v.log" 2>&1
    echo "sv2v rc=$?" >> "$OUT/$n.sv2v.log"
    cat > "$OUT/$n.sv2v.ys" <<EOF
read_verilog -sv $OUT/$n.v
hierarchy -top top
proc
opt_clean
check
write_rtlil $OUT/$n.sv2v.il
EOF
    ( cd "$OUT" && timeout 300 "$Y" -q -l "$OUT/$n.sv2v.ylog" "$OUT/$n.sv2v.ys" > /dev/null 2>&1 ; echo "rc=$?" >> "$OUT/$n.sv2v.ylog" )
  fi
done
