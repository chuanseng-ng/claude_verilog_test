#!/bin/bash
# area.sh -- sky130_fd_sc_hd area of the in-house MBIST blocks and of the Tessent insertion delta, synthesised the
# SAME way (docs/design/DFT_ARCHITECTURE.md 16.9): yosys synth, dfflibmap, abc -liberty, no timing-driven sizing.
#   usage: area.sh inhouse | base | tessent
# Env: YOSYS (default yosys), SKY130_LIB (sky130_fd_sc_hd__tt_025C_1v80.lib), SV2V.
set -e
here="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
root="$(cd "$here/../../.." && pwd)"
[ -f "$here/host/env.sh" ] && . "$here/host/env.sh"   # optional host-specific overrides (gitignored)
YOSYS="${YOSYS:-yosys}"; SV2V="${SV2V:-sv2v}"
LIB="${SKY130_LIB:?set SKY130_LIB to sky130_fd_sc_hd__tt_025C_1v80.lib}"
out="$here/build/area"; mkdir -p "$out"
IFACE="$here/lib/sky130_sram_4kbyte_1rw1r_32x1024_8.v_interface"

run() {  # run <top> <report> <read-commands>
  local top="$1" rep="$2" rd="$3"
  "$YOSYS" -q -p "$rd ; hierarchy -top $top ; synth -top $top ; dfflibmap -liberty $LIB ; abc -liberty $LIB ; opt_clean -purge ; tee -o $rep stat -liberty $LIB" \
      > "$rep.log" 2>&1 || { tail -20 "$rep.log"; exit 1; }
  echo "== $top -> $rep"
  grep -E "Chip area for (top )?module|cells$|Number of cells|sky130_fd_sc_hd__(df|dl|sdf)" "$rep" | tail -12
}

case "$1" in
 inhouse)
  # mbist_ctrl: N_MEM=2 AW=10 P1_MASK=2'b01 (soc_mbist); mem_collar HAS_P1=1 (sram_controller) and 0 (NPU weight memory)
  "$SV2V" --define=__pnr__ "$root/rtl/soc/dft/mbist_ctrl.sv" -w "$out/mbist_ctrl.v"
  "$SV2V" --define=__pnr__ "$root/rtl/soc/dft/mem_collar.sv" -w "$out/mem_collar.v"
  run mbist_ctrl "$out/inhouse_mbist_ctrl.rpt"   "read_verilog $out/mbist_ctrl.v; chparam -set N_MEM 2 -set AW 10 -set P1_MASK 1 mbist_ctrl"
  run mem_collar "$out/inhouse_collar_p1.rpt"    "read_verilog $out/mem_collar.v; chparam -set AW 10 -set HAS_P1 1 mem_collar"
  "$SV2V" --define=__pnr__ "$root/rtl/soc/cdc/cdc_sync.sv" "$root/rtl/soc/cdc/cdc_reset_sync.sv" "$root/rtl/soc/cdc/cdc_gray_fifo.sv" \
      "$root/rtl/soc/dft/dft_rst_mux.sv" "$root/rtl/soc/dft/mbist_ctl_hold.sv" "$root/rtl/soc/dft/mbist_xing.sv" "$root/rtl/soc/dft/mbist_status_sync.sv" -w "$out/mbist_acc.v"
  run mbist_xing "$out/inhouse_xing.rpt" "read_verilog $out/mbist_acc.v; chparam -set CTL_W 29 -set DOM_BIT 27 mbist_xing"
  run mbist_status_sync "$out/inhouse_status_sync.rpt" "read_verilog $out/mbist_acc.v; chparam -set ST_W 69 mbist_status_sync"
  run mem_collar "$out/inhouse_collar_nop1.rpt"  "read_verilog $out/mem_collar.v; chparam -set AW 10 -set HAS_P1 0 mem_collar"
  ;;
 base)
  run mbist_eval_top "$out/base_top.rpt" "read_verilog -lib $IFACE; read_verilog -defer $here/build/mbist_eval_top_sv2v.v"
  ;;
 tessent)
  tsdb="${MBIST_RUN:-$here/build/run}/tsdb_outdir"
  insts=$(ls "$tsdb"/instruments/*/*.v | tr '\n' ' ')
  mod="$tsdb/dft_inserted_designs/mbist_eval_top_rtl1.dft_inserted_design/modified_rtl_files/mbist_eval_top_sv2v.v"
  run mbist_eval_top "$out/tessent_top${MBIST_VARIANT:+_$MBIST_VARIANT}.rpt" "read_verilog -lib $IFACE; read_verilog -defer $insts $mod"
  ;;
esac
