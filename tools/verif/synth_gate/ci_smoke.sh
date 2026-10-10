#!/usr/bin/env bash
# CI smoke for the synthesis undef gate (bead gc0y). Tool-independent of LibreLane/Synlig/PDK:
#   1. sv2v the CPU (same source list/defines as pnr/sky130/cpu/config.json), elaborate with yosys,
#      and run tools/verif/check_synth_undef.py (log scan + structural header check) -> must PASS.
#   2. SELF-TEST: inject an out-of-range select into a scratch copy of rv32i_core.sv -> the same
#      gate MUST FAIL (proves the gate is live on this frontend; the dud4 lines themselves are
#      elaborated correctly by sv2v, which is why the PD flow can use it).
#   3. synthesise the sv2v netlist to yosys generic gates (no PDK) and run the gate-vs-RTL
#      differential (trivial, ma7_straight, ma7_branch) in Verilator; any divergence fails.
# Usage: ci_smoke.sh <workdir>     env: YOSYS SV2V VERILATOR_BIN VERILATOR_ROOT (defaults: on PATH)
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
W="$(mkdir -p "$1" && cd "$1" && pwd)"
YOSYS="${YOSYS:-yosys}"
SV2V="${SV2V:-sv2v}"
VBIN="${VERILATOR_BIN:-$(command -v verilator)}"
VBIN="$(readlink -f "$VBIN")"
export VERILATOR_ROOT="${VERILATOR_ROOT:-$(cd "$(dirname "$VBIN")/../share/verilator" && pwd)}"
GATE="$REPO/tools/verif/check_synth_undef.py"
GLS="$REPO/tools/verif/gls/sky130"
CFG="$REPO/pnr/sky130/cpu/config.json"

# ---- source list = config VERILOG_FILES minus the SRAM stub (the stub is read as a blackbox)
python3 - "$CFG" "$REPO" "$W/sv_files.txt" <<'PY'
import json, os, sys
cfg, repo, out = sys.argv[1:4]
files = json.load(open(cfg, encoding="utf-8"))["VERILOG_FILES"]
base = os.path.dirname(cfg)
res = [os.path.normpath(os.path.join(base, f[5:])) if f.startswith("dir::") else f for f in files]
res = [f for f in res if "sram" not in os.path.basename(f)]
open(out, "w", encoding="utf-8").write("\n".join(res) + "\n")
PY
STUB="$REPO/pnr/sky130/sky130_sram_1kbyte_1rw1r_32x256_8_stub.v"
DEFS=(--define=PDK_sky130A --define=SCL_sky130_fd_sc_hd --define=__librelane__ --define=__pnr__ --define=SRAM_SKY130)

# elaborate <tag> <file-list>: sv2v + yosys proc, writes $W/<tag>.{log,h.json,v}
elaborate() {
  local tag="$1" list="$2"
  "$SV2V" "${DEFS[@]}" $(cat "$list") -w "$W/$tag.sv2v.v" 2> "$W/$tag.sv2v.err"
  cat > "$W/$tag.ys" <<EOF
read_verilog -sv -lib $STUB
read_verilog -sv $W/$tag.sv2v.v
hierarchy -check -top rv32i_cpu_top
proc
opt_clean -purge
write_json $W/$tag.h.json
EOF
  "$YOSYS" -l "$W/$tag.log" "$W/$tag.ys" > /dev/null
}

echo "== 1. elaborate current RTL + gate"
elaborate main "$W/sv_files.txt"
python3 -I "$GATE" --header-json "$W/main.h.json" -v "$W/main.log"

echo "== 2. self-test: injected out-of-range select must FAIL the gate"
mkdir -p "$W/inject"
sed 's/(if_id_rs1_addr_w),/(if_id_instr_w[40:36]),/' "$REPO/rtl/cpu/core/rv32i_core.sv" > "$W/inject/rv32i_core.sv"
cmp -s "$W/inject/rv32i_core.sv" "$REPO/rtl/cpu/core/rv32i_core.sv" && { echo "injection did not apply"; exit 3; }
sed "s#$REPO/rtl/cpu/core/rv32i_core.sv#$W/inject/rv32i_core.sv#" "$W/sv_files.txt" > "$W/sv_files_inject.txt"
elaborate inject "$W/sv_files_inject.txt"
set +e
python3 -I "$GATE" --header-json "$W/inject.h.json" "$W/inject.log" > "$W/inject.gate.out"
rc=$?
set -e
cat "$W/inject.gate.out" | cut -c1-200
[ "$rc" = 1 ] || { echo "SELF-TEST FAILED: gate returned $rc on an injected undef (expected 1)"; exit 4; }
echo "self-test OK (gate failed as required)"

echo "== 3. generic-gate synthesis + gate-vs-RTL differential"
cat > "$W/gen.ys" <<EOF
read_verilog -sv -lib $STUB
read_verilog -sv $W/main.sv2v.v
hierarchy -check -top rv32i_cpu_top
synth -flatten -top rv32i_cpu_top
techmap
abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX
opt_clean -purge
write_verilog -noattr $W/gate.v
EOF
timeout 1500 "$YOSYS" -q -l "$W/gen.log" "$W/gen.ys"
SRAM_MODEL="$REPO/sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv"
COMMON=(--binary --timing -Wno-fatal -Wno-lint -Wno-style -Wno-TIMESCALEMOD --build-jobs 2
        --top-module tb_sky130_cpu_check -o Vtb)
"$VBIN" "${COMMON[@]}" --Mdir "$W/gate_obj" "$SRAM_MODEL" "$W/gate.v" "$GLS/tb_sky130_cpu_check.sv" > "$W/gate_build.log" 2>&1
RTL_ROOT="$REPO" VERILATOR_BIN="$VBIN" bash "$GLS/build_arm.sh" rtl "$W/rtl_arm" > "$W/rtl_build.log" 2>&1
bash "$GLS/gen_all_progs.sh" "$W/progs" > /dev/null
grep -E '^(trivial|ma7_straight|ma7_branch) ' "$W/progs/haltcyc.txt" > "$W/progs/haltcyc.smoke.txt"
status=0
while read -r name cyc; do
  mkdir -p "$W/rtl_arm/run" "$W/gate_run"
  "$W/rtl_arm/obj/Vtb" +rom="$W/progs/$name.hex" +haltcyc="$cyc" +trace="$W/rtl_arm/run/$name.trc" > "$W/rtl_arm/run/$name.log" 2>&1 || true
  "$W/gate_obj/Vtb" +rom="$W/progs/$name.hex" +haltcyc="$cyc" +trace="$W/gate_run/$name.trc" > "$W/gate_run/$name.log" 2>&1 || true
  if grep -q '^DONE' "$W/rtl_arm/run/$name.log" && grep -q '^DONE' "$W/gate_run/$name.log" \
     && diff <(grep -E '^(COMMIT|APBR|AXIW)' "$W/rtl_arm/run/$name.log") \
             <(grep -E '^(COMMIT|APBR|AXIW)' "$W/gate_run/$name.log") > /dev/null; then
    echo "  $name: RTL == generic-gate netlist ($(grep -c '^APBR' "$W/gate_run/$name.log") APB reads)"
  else
    echo "  $name: DIVERGES or did not finish"; status=1
  fi
done < "$W/progs/haltcyc.smoke.txt"
exit "$status"
