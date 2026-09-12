#!/usr/bin/env bash
# equiv_sv2v_module.sh — prove one module of the sv2v netlist equivalent to its source RTL.
#
# WHY MODULE LEVEL (bead q7n). sv2v is source-to-source, so module boundaries survive into
# pnr/asap7/soc/soc_top_sv2v.v (28 modules). Proving per module is dramatically cheaper than
# the flat soc_top miter, which on a 15.9 GB host cannot go deeper than equiv_induct -seq 5:
#
#            front end      deepest induction that fits   peak
#   flat     ~90 min        -seq 5                        11.5 GB   (seq 7/10/20 all die ~12.57 GB)
#   module   seconds        -seq 20 ran to completion      7.5 GB
#
# Yosys reads the SOURCE RTL through yosys-slang (an independent frontend), so "gold" here is
# the real RTL and not another sv2v artefact — that is what makes this a genuine check of sv2v
# rather than a self-consistency test.
#
# Usage:  tools/verif/equiv_sv2v_module.sh <module> [induct_depth] [simple_depth]
# Exit:   0 = all points proven      1 = some unproven (no counterexample)
#         2 = DISPROVEN (real mismatch — investigate)
#         3 = tool or input missing
#
# Override the toolchain with YOSYS= and SLANG_PLUGIN= if the nix store paths move; they are
# hardcoded for the same GC-root reason as ASAP7_OPENROAD_BIN in pnr/Makefile, and this script
# fails loudly rather than silently falling back to a yosys without the slang plugin.
set -uo pipefail

MODULE="${1:-}"
INDUCT_DEPTH="${2:-20}"
SIMPLE_DEPTH="${3:-5}"

if [ -z "$MODULE" ]; then
    echo "usage: $0 <module> [induct_depth] [simple_depth]" >&2
    exit 3
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
YOSYS="${YOSYS:-/nix/store/4bmfi4470w0i3ixcaidfki18d3fyqvva-yosys-with-plugins-0.62/bin/yosys}"
SLANG_PLUGIN="${SLANG_PLUGIN:-/nix/store/07xn6zd11qvkp8h65gwycfisr3x9hk4f-yosys-slang/share/yosys/plugins/slang.so}"
SV2V_OUT="${SV2V_OUT:-$ROOT/pnr/asap7/soc/soc_top_sv2v.v}"
OUT_DIR="${OUT_DIR:-${TMPDIR:-/tmp}/equiv_sv2v}"

for f in "$YOSYS" "$SLANG_PLUGIN" "$SV2V_OUT"; do
    if [ ! -e "$f" ]; then
        echo "ERROR: missing '$f'." >&2
        echo "       Re-resolve the nix store paths (YOSYS=, SLANG_PLUGIN=) or regenerate the" >&2
        echo "       sv2v netlist with 'make -C pnr asap7-soc-sv2v'." >&2
        exit 3
    fi
done

mkdir -p "$OUT_DIR"
YS="$OUT_DIR/$MODULE.ys"
LOG="$OUT_DIR/$MODULE.log"

# Source file list — mirrors SOC_SV_FILES in pnr/Makefile, plus the SRAM stub the SoC needs.
SRC_FILES=(
    "$ROOT/pnr/asap7/sram_1rw_256x32_asap7_stub.v"
    "$ROOT/rtl/soc/axi_pkg.sv"
    "$ROOT/rtl/soc/soc_addr_map_pkg.sv"
    "$ROOT/rtl/soc/soc_periph_map_pkg.sv"
    "$ROOT/pnr/asap7/soc/rv32i_cpu_top_stub.sv"
    "$ROOT/pnr/asap7/soc/gpu_top_stub.sv"
    "$ROOT/rtl/soc/pll/pll_clkgen_stub.sv"
    "$ROOT/pnr/asap7/soc/pll_clkgen_pnr.sv"
    "$ROOT/rtl/soc/pll/pll_apb_regs.sv"
    "$ROOT/rtl/soc/pll/pll_subsystem.sv"
    "$ROOT/rtl/soc/axi4_crossbar.sv"
    "$ROOT/rtl/soc/axi_lite_register_bank.sv"
    "$ROOT/rtl/soc/apb4_register_bank.sv"
    "$ROOT/rtl/soc/pmu.sv"
    "$ROOT/rtl/soc/axi_lite_interconnect.sv"
    "$ROOT/rtl/soc/axi4_to_axilite.sv"
    "$ROOT/rtl/soc/axilite_to_axi4.sv"
    "$ROOT/rtl/soc/axil_to_apb.sv"
    "$ROOT/rtl/soc/apb_interconnect.sv"
    "$ROOT/rtl/soc/soc_bus.sv"
    "$ROOT/rtl/soc/sram_controller.sv"
    "$ROOT/rtl/soc/boot_rom.sv"
    "$ROOT/rtl/periph/dma_engine.sv"
    "$ROOT/rtl/periph/interrupt_controller.sv"
    "$ROOT/rtl/periph/timer.sv"
    "$ROOT/rtl/periph/uart_controller.sv"
    "$ROOT/rtl/periph/spi_controller.sv"
    "$ROOT/rtl/mem/rv32i_clock_gate.sv"
    "$ROOT/rtl/soc/cdc/cdc_2ff_sync.sv"
    "$ROOT/rtl/soc/cdc/cdc_reset_sync.sv"
    "$ROOT/rtl/soc/cdc/cdc_gray_fifo.sv"
    "$ROOT/rtl/soc/async_axi_fifo.sv"
    "$ROOT/rtl/soc/apb_cdc_bridge.sv"
    "$ROOT/rtl/soc/soc_top.sv"
)

# --allow-use-before-declare and --compat vcs are required: soc_top instantiates two IRQ
# synchronisers ~190 lines above where ext_irq/timer_irq are declared, and the __pnr__ shims
# redeclare two `parameter string` as `int unsigned`. Both are tracked on bead q7n.
{
    echo "plugin -i $SLANG_PLUGIN"
    printf 'read_slang -D USE_ICG_CELL -D __pnr__ --ignore-unknown-modules --allow-use-before-declare --compat vcs'
    for inc in rtl/soc rtl/soc/cdc rtl/soc/pll rtl/periph rtl/mem; do printf ' -I %s/%s' "$ROOT" "$inc"; done
    printf ' --top %s' "$MODULE"
    printf ' %s' "${SRC_FILES[@]}"
    printf '\n'
    echo "hierarchy -top $MODULE; proc; flatten; opt_clean; memory; opt_clean; async2sync"
    echo "rename $MODULE gold"
    echo "design -stash gold"
    echo "read_verilog -sv -D USE_ICG_CELL $SV2V_OUT"
    echo "hierarchy -top $MODULE; proc; flatten; opt_clean; memory; opt_clean; async2sync"
    echo "rename $MODULE gate"
    echo "design -stash gate"
    echo "design -copy-from gold -as gold gold"
    echo "design -copy-from gate -as gate gate"
    echo "equiv_make gold gate equiv"
    echo "hierarchy -top equiv"
    echo "equiv_simple -seq $SIMPLE_DEPTH"
    echo "equiv_status"
    echo "equiv_induct -seq $INDUCT_DEPTH"
    echo "equiv_status"
} > "$YS"

"$YOSYS" -l "$LOG" -s "$YS" > /dev/null 2>&1
rc=$?

unproven=$(grep -oE "Found a total of [0-9]+ unproven" "$LOG" | tail -1 | grep -oE "[0-9]+")
disproven=$(grep -ciE "^Unproven.*disproven|equiv_status.*disproven|Found a total of [0-9]+ disproven" "$LOG")
total=$(grep -oE "Found [0-9]+ unproven \\\$equiv cells" "$LOG" | head -1 | grep -oE "[0-9]+")

if [ $rc -ne 0 ] && [ -z "$unproven" ]; then
    echo "module=$MODULE result=TOOL_ERROR rc=$rc log=$LOG" >&2
    tail -3 "$LOG" >&2
    exit 3
fi

if grep -qiE "Found a total of [0-9]+ disproven|equivalence check failed" "$LOG"; then
    echo "module=$MODULE result=DISPROVEN log=$LOG"
    exit 2
fi

if [ "${unproven:-0}" = "0" ]; then
    echo "module=$MODULE result=PROVEN points=${total:-?} induct_seq=$INDUCT_DEPTH log=$LOG"
    exit 0
fi

echo "module=$MODULE result=UNPROVEN unproven=$unproven of=${total:-?} induct_seq=$INDUCT_DEPTH log=$LOG"
grep "^Unproven" "$LOG" | grep -oE "\\\\[a-zA-Z0-9_.]+_gold" | sed 's/_gold//;s/^\\//' \
    | sed -E 's/\[[0-9]+\]$//' | sort | uniq -c | sort -rn | head -10
exit 1
