#!/usr/bin/env bash
# stage0_pnr_ecp5.sh -- ECP5 (LFE5U-85F-6BG381C) place-and-route lower bound for soc_top (bead hlrm, GH #245).
# ONE job per call.
#
# usage: stage0_pnr_ecp5.sh <repo-root> <out-dir> <gpu|nogpu> synth
#        stage0_pnr_ecp5.sh <repo-root> <out-dir> <gpu|nogpu> pnr <tag> <seed> <freq-MHz> [extra nextpnr args...]
#
#   synth: sv2v (--define=FPGA --define=__pnr__, file list + tools/fpga/ecp5_timing_harness.sv) -> yosys
#          synth_ecp5 -flatten -run :check (same settings as stage0_synth.sh, but WITH iopad insertion because the
#          harness has only 6 pins) -> JSON.
#   pnr:   nextpnr-ecp5 --85k --package CABGA381 --speed 6 on that JSON, no LPF (nextpnr places the 6 IO freely),
#          --timing-allow-fail so the run completes whatever the slack. Log, JSON report, /usr/bin/time -v under
#          <out-dir>/<tag>.*. Memory capped with ulimit -v (11 GB); wall clock capped by TIMEOUT (default 10800 s).
#
# A job that does not finish inside the caps is a FINDING, not retried. NOT a vendor-tool result: ECP5 is a slower
# family than the Artix-7 the board recommendation is about, so this is a LOWER BOUND for it.
#
# Tools (nix store paths, none in the project flake; override with the env vars):
#   NEXTPNR  = nixpkgs#nextpnr 0.11.1 (nextpnr-ecp5), trellis database is compiled into it
#   YOSYS / SV2V as in stage0_synth.sh
set -uo pipefail
root=$1; out=$2; gpu=$3; phase=$4
NEXTPNR=${NEXTPNR:-/nix/store/z9dl8x2hkcnwa71b9fwjsqxdhgx7q4xc-nextpnr-0.11.1/bin/nextpnr-ecp5}
SV2V=${SV2V:-/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v}
YOSYS=${YOSYS:-/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys}
TIMEOUT=${TIMEOUT:-10800}
here=$(dirname "$0")
mkdir -p "$out"

case $phase in
  synth)
    v=$out/soc_${gpu}_harness.v
    { "$here/stage0_filelist.sh" "$root" "$gpu" fpga; echo "$here/ecp5_timing_harness.sv"; } > "$out/list_${gpu}_harness.txt"
    # shellcheck disable=SC2046
    "$SV2V" --define=FPGA --define=__pnr__ $(cat "$out/list_${gpu}_harness.txt") -w "$v" 2> "$out/sv2v_${gpu}.err"
    echo "sv2v: $(wc -l < "$v") lines (stderr: $out/sv2v_${gpu}.err)"
    cat > "$out/${gpu}.ys" <<EOF
read_verilog $v
hierarchy -check -top ecp5_timing_harness
synth_ecp5 -top ecp5_timing_harness -flatten -run :check
tee -o $out/${gpu}.stat.txt stat
blackbox =A:whitebox
write_json $out/${gpu}.json
EOF
    ( ulimit -v 10485760
      /usr/bin/time -v timeout "$TIMEOUT" "$YOSYS" -q -l "$out/${gpu}.synth.log" -s "$out/${gpu}.ys" \
        > "$out/${gpu}.synth.stdout" 2> "$out/${gpu}.synth.time"
      echo "yosys rc=$?" > "$out/${gpu}.synth.rc" )
    cat "$out/${gpu}.synth.rc"
    grep -E "Maximum resident|Elapsed" "$out/${gpu}.synth.time"
    ;;
  pnr)
    tag=$5; seed=$6; freq=$7; shift 7
    ( ulimit -v 11534336
      /usr/bin/time -v timeout "$TIMEOUT" "$NEXTPNR" --85k --package CABGA381 --speed 6 \
        --json "$out/${gpu}.json" --freq "$freq" --seed "$seed" --timing-allow-fail \
        --report "$out/$tag.report.json" --log "$out/$tag.log" "$@" \
        > "$out/$tag.stdout" 2> "$out/$tag.time"
      echo "nextpnr rc=$?" > "$out/$tag.rc" )
    cat "$out/$tag.rc"
    grep -E "Maximum resident|Elapsed" "$out/$tag.time"
    ;;
  *) echo "bad phase $phase"; exit 2 ;;
esac
