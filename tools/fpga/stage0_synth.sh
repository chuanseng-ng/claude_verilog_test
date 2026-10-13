#!/usr/bin/env bash
# stage0_synth.sh -- FPGA Stage 0 open-tool synthesis of soc_top (bead hlrm, GH #245). ONE job per call.
#
# usage: stage0_synth.sh <repo-root> <out-dir> <gpu|nogpu> <xc7|ecp5>
#
#   sv2v (--define=FPGA --define=__pnr__)  ->  yosys read_verilog / hierarchy -check / synth_xilinx|synth_ecp5
#   -flatten, then stat + ltp -noff (logic depth). Memory capped at ~10 GB (ulimit -v) so the 15 GB host
#   stays usable; a job that cannot finish inside the cap or the wall-clock timeout is a FINDING, not retried.
#
# Tools are the nix-store builds already used by pnr/Makefile (sv2v 0.0.13.1) and the librelane-environment
# yosys 0.62; neither is in this repo's flake devShells. Override with SV2V= / YOSYS=.
# NOT a P&R run: no nextpnr is available, so there is no placement, no routing and no real timing.
set -uo pipefail
root=$1; out=$2; gpu=$3; fam=$4
SV2V=${SV2V:-/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v}
YOSYS=${YOSYS:-/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys}
TIMEOUT=${TIMEOUT:-7200}
here=$(dirname "$0")
tag=${gpu}_${fam}
mkdir -p "$out"

# sv2v once per gpu/nogpu (shared by both families)
v=$out/soc_${gpu}_fpga.v
if [ ! -s "$v" ]; then
  "$here/stage0_filelist.sh" "$root" "$gpu" fpga > "$out/list_${gpu}_fpga.txt"
  # shellcheck disable=SC2046
  "$SV2V" --define=FPGA --define=__pnr__ $(cat "$out/list_${gpu}_fpga.txt") -w "$v" 2> "$out/sv2v_${gpu}.err"
  echo "sv2v: $(wc -l < "$v") lines (stderr: $out/sv2v_${gpu}.err)"
fi

case $fam in
  xc7)  synth="synth_xilinx -top soc_top -family xc7 -flatten -noiopad" ;;
  ecp5) synth="synth_ecp5 -top soc_top -flatten -noiopad" ;;
  *) echo "bad family $fam"; exit 2 ;;
esac

cat > "$out/$tag.ys" <<EOF
read_verilog $v
hierarchy -check -top soc_top
tee -o $out/$tag.hier.txt stat
$synth
tee -o $out/$tag.stat.txt stat
write_json $out/$tag.json
EOF

( ulimit -v 10485760
  /usr/bin/time -v timeout "$TIMEOUT" "$YOSYS" -q -l "$out/$tag.log" -s "$out/$tag.ys" > "$out/$tag.stdout" 2> "$out/$tag.time"
  echo "yosys rc=$?" > "$out/$tag.rc" )
cat "$out/$tag.rc"
grep -E "Maximum resident|Elapsed" "$out/$tag.time"
