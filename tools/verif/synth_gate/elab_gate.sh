#!/usr/bin/env bash
# Elaboration gate for one flow target, exactly as the PD flow sees it (bead j1b7, builds on gc0y).
#   sv2v (source list + defines from `make -C pnr <target>-sv2v-inputs`) -> yosys hierarchy -> write_rtlil
#   (PRE-proc, the proof for the function-temporary exemption) -> proc -> write_json (the same view the
#   flow's Yosys.JsonHeader step writes: proc, NO opt_clean) -> tools/verif/check_synth_undef.py.
# usage: elab_gate.sh <sky130-cpu|sky130-soc|asap7-soc> <workdir> [inject]
#   inject (negative controls, each must make the gate FAIL, exit status 1):
#     cpu-hazard      rv32i_core.sv: hazard-unit port fed by an out-of-range select      (sky130-cpu)
#     soc-oob         timer.sv: out-of-range struct-member select reaching irq_o        (any SoC)
#     soc-x-port      timer.sv: instance input port tied to 'x reaching irq_o           (any SoC)
#     soc-leaky       timer.sv: function result left unassigned on a path, reaching irq_o (any SoC)
# env: YOSYS SV2V (default: on PATH). Prints "RESULT elapsed_s=<n> peak_rss_kb=<n>" for the elaboration.
# exit: 0 gate PASS, 1 gate FAIL, 2 input/tool problem (the tool's own error is printed).
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
TARGET="${1:?target}"
W="$(mkdir -p "${2:?workdir}" && cd "$2" && pwd)"
INJECT="${3:-}"
YOSYS="${YOSYS:-yosys}"
SV2V="${SV2V:-sv2v}"
TAG="$TARGET${INJECT:+.$INJECT}"
GATE="$REPO/tools/verif/check_synth_undef.py"

case "$TARGET" in
  sky130-cpu) TOP=rv32i_cpu_top; LIBS=("$REPO/pnr/sky130/sky130_sram_1kbyte_1rw1r_32x256_8_stub.v") ;;
  sky130-soc) TOP=soc_top; LIBS=() ;;
  asap7-soc)  TOP=soc_top; LIBS=("$HERE/stubs/asap7_icg_stub.v" "$REPO/pnr/asap7/sram_1rw_256x32_asap7_stub.v") ;;
  *) echo "ERROR: unknown target '$TARGET'" >&2; exit 2 ;;
esac

die() { echo "ERROR: $*" >&2; exit 2; }
MAKE_OUT="$(make -s -C "$REPO/pnr" "$TARGET-sv2v-inputs")" || die "make $TARGET-sv2v-inputs failed"
echo "$MAKE_OUT" | sed -n 's/^FILE //p' > "$W/$TAG.files"
read -r -a DEFS <<< "$(echo "$MAKE_OUT" | sed -n 's/^DEFINES //p')"
[ -s "$W/$TAG.files" ] && [ "${#DEFS[@]}" -gt 0 ] || die "empty source list or defines from the Makefile"
while read -r f; do [ -f "$f" ] || die "listed source missing: $f"; done < "$W/$TAG.files"

replace_in_list() {  # <basename of file in the list> <replacement path>
  local victim; victim="$(grep "/$1\$" "$W/$TAG.files")" || die "$1 not in the source list"
  sed -i "s#^$victim\$#$2#" "$W/$TAG.files"
}
case "$INJECT" in
  "") ;;
  cpu-hazard)
    mkdir -p "$W/inject"
    sed 's/(if_id_rs1_addr_w),/(if_id_instr_w[40:36]),/' "$REPO/rtl/cpu/core/rv32i_core.sv" > "$W/inject/rv32i_core.sv"
    cmp -s "$W/inject/rv32i_core.sv" "$REPO/rtl/cpu/core/rv32i_core.sv" && die "injection did not apply"
    replace_in_list rv32i_core.sv "$W/inject/rv32i_core.sv" ;;
  soc-oob|soc-x-port|soc-leaky)
    mkdir -p "$W/inject"
    case "$INJECT" in soc-oob) SNIP=soc_oob_select;; soc-x-port) SNIP=soc_x_port;; *) SNIP=soc_leaky_function;; esac
    python3 -I "$HERE/inject_snippet.py" "$REPO/rtl/periph/timer.sv" "$W/inject/timer.sv" \
      "$HERE/inject/$SNIP.sv.inc" "assign irq_o = irq_en & irq_pending_q;" || die "injection did not apply"
    replace_in_list timer.sv "$W/inject/timer.sv" ;;
  *) die "unknown inject '$INJECT'" ;;
esac

# shellcheck disable=SC2046
"$SV2V" "${DEFS[@]}" $(cat "$W/$TAG.files") -w "$W/$TAG.sv2v.v" 2> "$W/$TAG.sv2v.err" \
  || { echo "ERROR: sv2v failed ($TAG):" >&2; cat "$W/$TAG.sv2v.err" >&2; exit 2; }
{
  for l in "${LIBS[@]}"; do echo "read_verilog -sv -lib $l"; done
  echo "read_verilog -defer -noautowire -sv $W/$TAG.sv2v.v"
  echo "hierarchy -check -top $TOP"
  echo "write_rtlil $W/$TAG.pre.il"
  echo "proc"
  echo "write_json $W/$TAG.h.json"
} > "$W/$TAG.ys"
TIMEV=(); [ -x /usr/bin/time ] && TIMEV=(/usr/bin/time -v -o "$W/$TAG.time")
"${TIMEV[@]}" "$YOSYS" -l "$W/$TAG.log" "$W/$TAG.ys" > /dev/null \
  || { echo "ERROR: yosys elaboration failed ($TAG), last log lines:" >&2; tail -n 30 "$W/$TAG.log" >&2; exit 2; }
if [ -f "$W/$TAG.time" ]; then
  el="$(sed -n 's/.*Elapsed (wall clock) time.*: //p' "$W/$TAG.time")"
  rss="$(sed -n 's/.*Maximum resident set size (kbytes): //p' "$W/$TAG.time")"
  echo "RESULT $TAG yosys_elapsed=$el peak_rss_kb=$rss"
fi

set +e
python3 -I "$GATE" --header-json "$W/$TAG.h.json" --pre-rtlil "$W/$TAG.pre.il" "$W/$TAG.log" > "$W/$TAG.gate.out"
rc=$?
set -e
cut -c1-220 "$W/$TAG.gate.out" | tail -n 40
exit "$rc"
