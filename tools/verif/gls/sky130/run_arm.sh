#!/usr/bin/env bash
# Run every program of <progdir> on a built arm.
#   run_arm.sh <arm_outdir> <progdir> [extra simulator args, e.g. +verilator+rand+reset+2 +verilator+seed+7]
# Writes <arm_outdir>/run[_tag]/<prog>.{log,trc}.
set -euo pipefail
ARM="$1"
PROGS="$2"
shift 2
TAG="${RUN_TAG:-run}"
OUT="$ARM/$TAG"
mkdir -p "$OUT"
while read -r name cyc; do
  [ -z "$name" ] && continue
  "$ARM/obj/Vtb" +rom="$PROGS/$name.hex" +haltcyc="$cyc" +trace="$OUT/$name.trc" "$@" > "$OUT/$name.log" 2>&1 || true
  echo "$name: $(grep -c '^COMMIT' "$OUT/$name.log") commits, $(grep -c '^AXIW' "$OUT/$name.log") axi writes, $(grep -c '^APBR' "$OUT/$name.log") apb reads, $(grep -E '^(DONE|TIMEOUT)' "$OUT/$name.log")"
done < "$PROGS/haltcyc.txt"
