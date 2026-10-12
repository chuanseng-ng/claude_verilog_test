#!/usr/bin/env bash
# oldnew_eq.sh - old-vs-new RTL equivalence of one module (bead ainf, wire-first rewrite).
#
# usage: oldnew_eq.sh <outdir> <top> <old-root> <new-root> "<files, relative to a root>" ["<modules to blackbox>"]
#
# <old-root>/<new-root> are two repository trees (e.g. `git archive <rev> rtl | tar -x`); the SAME
# relative file list is read from each.  For each of two independent front ends the module is
# elaborated from old and from new, flattened, flop-exposed (`expose -evert-dff`, so every flop
# becomes a port and the check is combinational equivalence of next-state + outputs given identical
# state/inputs) and miter + SAT-proven:
#   sv2v  : sv2v -> yosys read_verilog   (the frontend the Sky130 / ASAP7 SoC flows actually use)
#   slang : yosys-slang read_slang       (independent of sv2v)
# Prints one line per frontend:  <top> | <frontend> | EQUIV | NOT-EQUIV | UNKNOWN
# Because gold and gate go through the SAME frontend, a frontend quirk cancels; what is proven is
# that the source edit is behaviour-preserving, which is what a pure refactor needs.
# Run under: systemd-run --user --scope -q -p MemoryMax=4G -p MemorySwapMax=0 <this>
set -u
OUT=$1; TOP=$2; OLD=$3; NEW=$4; FILES=$5; BB=${6:-}
Y_SV2V=${Y_SV2V:-/nix/store/9r0bh7sp051dpm8km8bqlb028anpd3v3-yosys/bin/yosys}
Y_SLANG=${Y_SLANG:-/nix/store/4bmfi4470w0i3ixcaidfki18d3fyqvva-yosys-with-plugins-0.62/bin/yosys}
SLANG_SO=${SLANG_SO:-/nix/store/07xn6zd11qvkp8h65gwycfisr3x9hk4f-yosys-slang/share/yosys/plugins/slang.so}
SV2V=${SV2V:-/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v}
mkdir -p "$OUT"; cd "$OUT" || exit 2
BBCMD=""; [ -n "$BB" ] && BBCMD="blackbox $BB"
EXPOSE='expose -evert-dff t:$dff t:$dffe t:$sdff t:$sdffe t:$adff t:$adffe t:$adffe t:$dlatch'

abs() { local r=$1 f out=""; for f in $FILES; do out="$out $r/$f"; done; echo "$out"; }

build() {   # build <frontend> <tag> <root>
  local fe=$1 tag=$2 root=$3 files; files=$(abs "$root")
  local ys="$fe.$tag.ys" il="$OUT/$fe.$tag.il"
  if [ "$fe" = sv2v ]; then
    # shellcheck disable=SC2086
    "$SV2V" $files -w "$OUT/$tag.sv2v.v" > "$fe.$tag.sv2v.log" 2>&1 || { echo "sv2v failed ($tag)"; return 1; }
    { echo "read_verilog -sv $OUT/$tag.sv2v.v"; echo "hierarchy -top $TOP"; } > "$ys"
    yosys=$Y_SV2V
  else
    { echo "plugin -i $SLANG_SO"; echo "read_slang --top $TOP $files"; echo "hierarchy -top $TOP"; } > "$ys"
    yosys=$Y_SLANG
  fi
  { echo "proc"; echo "$BBCMD"; echo "flatten"; echo "$EXPOSE"; echo "opt_clean"; echo "write_rtlil $il"; } >> "$ys"
  timeout 600 "$yosys" -q -l "$fe.$tag.log" "$ys" > /dev/null 2>&1
  [ -s "$il" ] || { echo "yosys produced no netlist ($fe $tag), see $OUT/$fe.$tag.log"; return 1; }
}

for fe in sv2v slang; do
  if [ "$fe" = sv2v ]; then yosys=$Y_SV2V; else yosys=$Y_SLANG; fi
  if ! build "$fe" old "$OLD" || ! build "$fe" new "$NEW"; then echo "$TOP | $fe | UNKNOWN(build)"; continue; fi
  {
    echo "read_rtlil $OUT/$fe.old.il"; echo "rename $TOP gold"
    echo "read_rtlil $OUT/$fe.new.il"; echo "rename $TOP gate"
    echo "miter -equiv -flatten -make_assert gold gate miter"
    echo "hierarchy -top miter"; echo "flatten"; echo "opt_clean"
    echo "sat -verify -prove-asserts -show-inputs -show-outputs miter"
  } > "$fe.eq.ys"
  timeout 900 "$yosys" -q -l "$fe.eq.log" "$fe.eq.ys" > /dev/null 2>&1; rc=$?
  if grep -q 'SUCCESS' "$fe.eq.log"; then v=EQUIV; elif grep -q 'FAIL' "$fe.eq.log"; then v=NOT-EQUIV; else v="UNKNOWN(rc=$rc)"; fi
  echo "$TOP | $fe | $v"
done
