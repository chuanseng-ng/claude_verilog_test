#!/usr/bin/env bash
# run_rung.sh RUNG        RUNG in: npu crypto dma fabric timer
#
# One rung of the j41m.15 Quaigh ladder: (synth) -> exclusions/prep -> full-scan cut -> capped Quaigh atpg -> coverage report.
# Heavy outputs go to $W/<rung>/ (default /nobackup/claude_sim_build/j41m15), never into git.  FORCE=1 redoes finished stages.
# The Quaigh step runs under run_capped.sh (12 GB, 24 h): its metrics.json is what the DFT_ARCHITECTURE section 18 table quotes.
set -eu
rung=$1
here=$(cd "$(dirname "$0")" && pwd)
root=$(cd "$here/../../.." && pwd)
W=${W:-/nobackup/claude_sim_build/j41m15}
QUAIGH=${QUAIGH:-$W/bin/quaigh}
PY=${PY:-python3}
out=$W/$rung
SRAM_HDR=$root/pnr/sky130/soc/macro/sky130_sram_4kbyte_1rw1r_32x1024_8.v
CPU_HDR=$root/pnr/sky130/cpu/macro/rv32i_cpu_top.nl.v.gz
FAB_NL=${FAB_NL:-$W/in/fabric_1028.nl.v}   # symlink to .../runs/RUN_2026-10-28_05-14-30/49-openroad-fillinsertion/soc_top.nl.v (run dirs are untracked)
mkdir -p "$out"

prep_args=(--full-scan); cut_args=(); netlist=""
case $rung in
  npu)    top=npu_top;       cut_args=(--const rst_n=1 --bbox "sky130_sram_4kbyte_1rw1r_32x1024_8=$SRAM_HDR") ;;
  crypto) top=crypto_accel;  cut_args=(--const rst_n=1 --const scan_mode_i=1)
          prep_args=(--full-scan --key-qrx '^(key_q|g_aes\.u_aes\.rk_q)\[') ;;
  dma)    top=dma_engine;    cut_args=(--const rst_n=1) ;;
  fabric) top=soc_top;       netlist=$FAB_NL
          prep_args=(--hold-mask --key-qrx 'u_crypto\.(key_q|g_aes\.u_aes\.rk_q)\[')
          cut_args=(--const scan_mode_i=1 --const scan_en_i=0 --const trst_ni=0 --const tck_i=0 --const scan_rst_ni=1
                    --bbox "rv32i_cpu_top=$CPU_HDR" --bbox "sky130_sram_4kbyte_1rw1r_32x1024_8=$SRAM_HDR") ;;
  *) echo "unknown rung $rung" >&2; exit 64 ;;
esac

step() { # step NAME DONE_FILE CMD...
  local name=$1 done=$2; shift 2
  if [ -s "$done" ] && [ -z "${FORCE:-}" ]; then echo "[$rung] $name: up to date"; return; fi
  echo "[$rung] $name"; "$@"
}

if [ -z "$netlist" ]; then
  netlist=$out/$top.v
  step synth "$netlist" "$here/synth_module.sh" "$top" "$out"
fi
step prep "$out/prep.v" "$PY" "$here/netlist_prep.py" "$netlist" "$out/prep.v" --exclusions "$out/exclusions.json" "${prep_args[@]}"
step cut "$out/cut/cut.blif" "$PY" "$here/mk_cut.py" "$out/prep.v" --top "$top" --out "$out/cut" "${cut_args[@]}"
step atpg "$out/q/metrics.json" "$here/run_capped.sh" "$out/q" -- "$QUAIGH" atpg "$out/cut/cut.blif" -o "$out/q/cut.test"
"$PY" "$here/atpg_coverage_report.py" "$out/q/run.log" --metrics "$out/q/metrics.json" --exclusions "$out/exclusions.json" \
    --label "$rung" --out "$out/q/report.json" --md || true
