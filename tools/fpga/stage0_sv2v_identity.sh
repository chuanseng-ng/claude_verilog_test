#!/usr/bin/env bash
# stage0_sv2v_identity.sh -- sv2v the full SoC under every NON-FPGA define set and print sha256 of each output
# (bead hlrm, FPGA Stage 0 byte-identity proof).
#
# usage: stage0_sv2v_identity.sh <repo-root> <out-dir>
#
# Run once on a pristine origin/main export and once on the feature tree with the SAME file list (sim mode:
# the rtl/fpga files are deliberately NOT in the list) and compare the two sha256 columns with cmp -s/sha256sum.
# The list is generated from <repo-root> so each tree elaborates its own sources.
set -euo pipefail
root=$1; out=$2
SV2V=${SV2V:-/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v}
here=$(dirname "$0")
mkdir -p "$out"
declare -A SETS=(
  [sim]=""                                              # cocotb / Verilator default: no defines
  [simulation]="--define=SIMULATION"                    # cdc_sync RAND_CDC_DELAY arm
  [pnr]="--define=__pnr__"
  [sky130]="--define=__pnr__ --define=SRAM_SKY130 --define=USE_SKY130_CLKCELLS"  # pnr/Makefile SKY130_SOC_SV2V_DEFINES
  [asap7]="--define=USE_ICG_CELL --define=__pnr__ --define=SRAM_ASAP7"   # SOC_SV2V_DEFINES
)
for gpu in gpu nogpu; do
  "$here/stage0_filelist.sh" "$root" "$gpu" sim > "$out/list_$gpu.txt"
  for s in "${!SETS[@]}"; do
    # shellcheck disable=SC2086
    $SV2V ${SETS[$s]} $(cat "$out/list_$gpu.txt") -w "$out/${gpu}_$s.v" 2> "$out/${gpu}_$s.err" || echo "sv2v FAILED $gpu/$s"
  done
done
# sv2v embeds "<abs path>:<line>:<col>" in every elaboration-time $fatal message ($display "Fatal [elaboration] ...").
# That is a diagnostic source location, not design content: it differs between two checkouts of the SAME rtl
# and shifts whenever a file gains lines above a $fatal. Strip it (and only it) before hashing.
for f in "$out"/*_*.v; do
  case $f in *.norm.v) continue;; esac
  sed -E 's#(Fatal \[[^]]*\]) [^ ]+:[0-9]+:[0-9]+ #\1 #' -- "$f" > "${f%.v}.norm.v"
done
(cd "$out" && sha256sum ./*.norm.v | sed 's# \./# #' | sort -k2)
