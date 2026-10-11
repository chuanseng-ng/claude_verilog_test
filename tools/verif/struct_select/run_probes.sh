#!/usr/bin/env bash
# usage: run_probes.sh <probe_dir> <outdir> [name-glob]
# For every probe: elaborate with Synlig (yosys 0.46 + synlig plugin) and with sv2v+yosys, dump
# the net connections each produced for the output `y`, and miter+SAT-compare the two.
# Run under:  systemd-run --user --scope -p MemoryMax=4G -p MemorySwapMax=0 timeout 900 <this>
# and from a PRIVATE cwd (Surelog's slpp_all cache is written to the cwd).
set -u
PD=$1; OUT=$2; GLOB=${3:-*}
Y=${Y46:-/nix/store/9r0bh7sp051dpm8km8bqlb028anpd3v3-yosys/bin/yosys}
SO=${SYNLIG_SO:-/nix/store/7vsbsrhbj6kx5lfdc8qs9wlccxfb8f7h-yosys-synlig-sv/share/yosys/plugins/synlig-sv.so}
SV2V=${SV2V:-/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v}
mkdir -p "$OUT"
cd "$OUT" || exit 2
for f in "$PD"/$GLOB.sv; do
  n=$(basename "$f" .sv)
  printf 'plugin -i %s\nread_systemverilog -sverilog -top top %s\nhierarchy -top top\nproc\nflatten\nopt_clean\nwrite_rtlil %s/%s.synlig.il\n' \
    "$SO" "$f" "$OUT" "$n" > "$n.synlig.ys"
  timeout 300 "$Y" -q -l "$n.synlig.log" "$n.synlig.ys" > /dev/null 2>&1
  echo "rc=$?" >> "$n.synlig.log"
  "$SV2V" "$f" -w "$n.v" > "$n.sv2v.log" 2>&1
  printf 'read_verilog -sv %s/%s.v\nhierarchy -top top\nproc\nflatten\nopt_clean\nwrite_rtlil %s/%s.sv2v.il\n' \
    "$OUT" "$n" "$OUT" "$n" > "$n.sv2v.ys"
  timeout 300 "$Y" -q -l "$n.sv2v.ylog" "$n.sv2v.ys" > /dev/null 2>&1
  echo "rc=$?" >> "$n.sv2v.ylog"
  # miter + SAT (sequential bound 4 so the flop probe is covered)
  printf 'read_rtlil %s/%s.synlig.il\nrename top gold\nread_rtlil %s/%s.sv2v.il\nrename top gate\nmiter -equiv -flatten -make_assert gold gate miter\nhierarchy -top miter\nflatten\nopt_clean\nsat -verify -prove-asserts -seq 4 -set-init-zero miter\n' \
    "$OUT" "$n" "$OUT" "$n" > "$n.eq.ys"
  timeout 300 "$Y" -q -l "$n.eq.log" "$n.eq.ys" > /dev/null 2>&1
  rc=$?
  if grep -q 'SUCCESS' "$n.eq.log"; then v=EQUIV; elif grep -q 'FAIL' "$n.eq.log"; then v=NOT-EQUIV; else v="UNKNOWN(rc=$rc)"; fi
  w=$(grep -c -i 'out of bounds' "$n.synlig.log")
  cs=$(grep -h '^ *connect .y ' "$n.synlig.il" | tr -s ' ' | tr -d '\n')
  cv=$(grep -h '^ *connect .y ' "$n.sv2v.il" | tr -s ' ' | tr -d '\n')
  echo "$n | $v | oob=$w | synlig:$cs | sv2v:$cv"
done
