#!/usr/bin/env bash
# CI smoke for the synthesis undef gate (beads gc0y, j1b7). Tool-independent of LibreLane/Synlig/PDK:
#   1. POSITIVE controls, blocking mode: sv2v + yosys elaboration of the Sky130 CPU macro, the Sky130 SoC and
#      the ASAP7 SoC (source lists/defines from `make -C pnr <target>-sv2v-inputs`, i.e. what the flows use),
#      then tools/verif/check_synth_undef.py (log scan + structural header check + dead-function-temporary
#      proof from the pre-proc RTLIL) -> every one must PASS.
#   2. NEGATIVE controls: an out-of-range select in the CPU, and in SoC scope an out-of-range struct-member
#      select, an instance port tied to 'x, and a function whose result is unassigned on a path and reaches an
#      output -> the same gate MUST FAIL each time, for the stated reason.
#   3. synthesise the sv2v CPU netlist to yosys generic gates (no PDK) and run the gate-vs-RTL
#      differential (trivial, ma7_straight, ma7_branch) in Verilator; any divergence fails.
# Usage: ci_smoke.sh <workdir>     env: YOSYS SV2V VERILATOR_EXE (NOT VERILATOR_BIN, see build_arm.sh) (defaults: on PATH)
set -euo pipefail
unset VERILATOR_BIN
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../../.." && pwd)"
W="$(mkdir -p "$1" && cd "$1" && pwd)"
YOSYS="${YOSYS:-yosys}"
SV2V="${SV2V:-sv2v}"
VBIN="${VERILATOR_EXE:-$(command -v verilator)}"
VBIN="$(readlink -f "$VBIN")"
export VERILATOR_ROOT="${VERILATOR_ROOT:-$(cd "$(dirname "$VBIN")/../share/verilator" && pwd)}"
GLS="$REPO/tools/verif/gls/sky130"
STUB="$REPO/pnr/sky130/sky130_sram_1kbyte_1rw1r_32x256_8_stub.v"
ELAB="$HERE/elab_gate.sh"
export YOSYS SV2V

# expect_gate <expected rc> <regex that must appear in the output> <target> [inject]
expect_gate() {
  local want="$1" rx="$2" tgt="$3" inj="${4:-}" rc tag t0=$SECONDS
  tag="$tgt${inj:+.$inj}"
  set +e
  bash "$ELAB" "$tgt" "$W" $inj > "$W/$tag.run.out" 2>&1
  rc=$?
  set -e
  cut -c1-220 "$W/$tag.run.out" | grep -E "^(RESULT|FAIL|EXEMPT|check_synth_undef|ERROR)" | head -n 12 || true
  if [ "$rc" != "$want" ]; then
    echo "GATE CASE FAILED: $tag returned $rc, expected $want"
    tail -n 40 "$W/$tag.run.out"
    exit 4
  fi
  if [ -n "$rx" ] && ! grep -Eq "$rx" "$W/$tag.run.out"; then
    echo "GATE CASE FAILED: $tag did not report /$rx/"
    exit 4
  fi
  echo "  [$tag] rc=$rc as required ($((SECONDS - t0)) s)"
}

echo "== 1. positive controls (blocking mode): current CPU and both SoC flows must PASS"
expect_gate 0 "" sky130-cpu
expect_gate 0 "func-temp-dead-init" sky130-soc
expect_gate 0 "func-temp-dead-init" asap7-soc

echo "== 2. negative controls: each injected defect must FAIL the same gate"
# CPU: the dud4 hazard-unit lines themselves cannot be the control (sv2v elaborates them correctly, which
# is why the PD flow uses sv2v), so an out-of-range select is injected into the u_hazard connection.
expect_gate 1 "x-driven-instance-input" sky130-cpu cpu-hazard
# SoC scope (j1b7): the same defect class, and a function result left unassigned on a path.
expect_gate 1 "undef-range-select|x-driven-net" sky130-soc soc-oob
expect_gate 1 "x-driven-instance-input" sky130-soc soc-x-port
expect_gate 1 "x-driven-net.*j1b7_leaky.*READ" sky130-soc soc-leaky
echo "negative controls OK (every injected defect failed the gate as required)"

echo "== 3. generic-gate synthesis + gate-vs-RTL differential"
cat > "$W/gen.ys" <<EOF
read_verilog -sv -lib $STUB
read_verilog -sv $W/sky130-cpu.sv2v.v
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
