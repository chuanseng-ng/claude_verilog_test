#!/usr/bin/env bash
# usage: modeq.sh <outdir> <top> "<space separated .sv files, absolute>" ["<modules to blackbox>"] ["<defines>"]
# Elaborate <top> with Synlig and with sv2v+yosys, flop-expose both (expose -evert-dff) and
# miter + SAT them.  Prints  <top> | EQUIV | NOT-EQUIV | UNKNOWN  plus sat counterexample ports.
# Run under: systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=0 timeout 900 <this>
# from a PRIVATE cwd (Surelog slpp_all cache).
set -u
OUT=$1; TOP=$2; FILES=$3; BB=${4:-}; DEFS=${5:-}
Y=${Y46:-/nix/store/9r0bh7sp051dpm8km8bqlb028anpd3v3-yosys/bin/yosys}
SO=${SYNLIG_SO:-/nix/store/7vsbsrhbj6kx5lfdc8qs9wlccxfb8f7h-yosys-synlig-sv/share/yosys/plugins/synlig-sv.so}
SV2V=${SV2V:-/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v}
mkdir -p "$OUT"; cd "$OUT" || exit 2
BBCMD=""; [ -n "$BB" ] && BBCMD="blackbox $BB"
# Synlig arm
{
  echo "plugin -i $SO"
  echo "read_systemverilog -sverilog -top $TOP $DEFS $FILES"
  echo "hierarchy -top $TOP"
  echo "proc"; echo "memory"; echo "opt_clean"; echo "$BBCMD"; echo "flatten"; echo "opt_clean"
  echo 'expose -evert-dff t:$dff t:$dffe t:$sdff t:$sdffe t:$adff t:$adffe'; echo "opt_clean"
  echo "write_rtlil $OUT/$TOP.synlig.il"
} > synlig.ys
timeout 600 "$Y" -q -l synlig.log synlig.ys > /dev/null 2>&1; echo "synlig rc=$?" >> synlig.log
# sv2v arm
SVD=""; for d in $DEFS; do SVD="$SVD --define=${d#-D}"; done
"$SV2V" $SVD ${FILES_SV2V:-$FILES} -w "$TOP.sv2v.v" > sv2v.log 2>&1
{
  echo "read_verilog -sv $OUT/$TOP.sv2v.v"
  echo "hierarchy -top $TOP"
  echo "proc"; echo "memory"; echo "opt_clean"; echo "$BBCMD"; echo "flatten"; echo "opt_clean"
  echo 'expose -evert-dff t:$dff t:$dffe t:$sdff t:$sdffe t:$adff t:$adffe'; echo "opt_clean"
  echo "write_rtlil $OUT/$TOP.sv2v.il"
} > sv2v.ys
timeout 600 "$Y" -q -l sv2v.ylog sv2v.ys > /dev/null 2>&1; echo "sv2v rc=$?" >> sv2v.ylog
# miter + SAT
{
  echo "read_rtlil $OUT/$TOP.synlig.il"; echo "rename $TOP gold"
  echo "read_rtlil $OUT/$TOP.sv2v.il";   echo "rename $TOP gate"
  echo "miter -equiv -flatten -make_assert gold gate miter"
  echo "hierarchy -top miter"; echo "flatten"; echo "opt_clean"
  echo "sat -verify -prove-asserts -show-inputs -show-outputs miter"
} > eq.ys
timeout 600 "$Y" -q -l eq.log eq.ys > /dev/null 2>&1; rc=$?
if grep -q 'SUCCESS' eq.log; then v=EQUIV; elif grep -q 'FAIL' eq.log; then v=NOT-EQUIV; else v="UNKNOWN(rc=$rc)"; fi
w=$(grep -c -i 'out of bounds' synlig.log)
echo "$TOP | $v | synlig-oob-warnings=$w | miter-cells=$(grep -c '' eq.log)"
