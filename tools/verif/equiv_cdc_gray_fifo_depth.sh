#!/usr/bin/env bash
# equiv_cdc_gray_fifo_depth.sh -- prove the DEPTH>=4 behaviour of rtl/soc/cdc/cdc_gray_fifo.sv
# is unchanged by bead 3snb's DEPTH=2 generate branch.
#
# gold = cdc_gray_fifo.sv as it was at OLD_REF (default origin/main), module renamed
#        cdc_gray_fifo_old so both can coexist; cdc_sync is shared and untouched.
# gate = the working-tree cdc_gray_fifo.sv.
# Both are read through yosys-slang (an independent front end), flattened, async2sync'd and
# compared with equiv_make + equiv_simple + equiv_induct per DEPTH.
#
# Usage:  tools/verif/equiv_cdc_gray_fifo_depth.sh [depth ...]      (default: 4 8 16)
# Exit:   0 all proven, 1 unproven (no counterexample), 3 tool/input missing.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
YOSYS="${YOSYS:-/nix/store/4bmfi4470w0i3ixcaidfki18d3fyqvva-yosys-with-plugins-0.62/bin/yosys}"
SLANG_PLUGIN="${SLANG_PLUGIN:-/nix/store/07xn6zd11qvkp8h65gwycfisr3x9hk4f-yosys-slang/share/yosys/plugins/slang.so}"
OLD_REF="${OLD_REF:-origin/main}"
WIDTH="${WIDTH:-8}"
OUT_DIR="${OUT_DIR:-${TMPDIR:-/tmp}/equiv_cdc_gray_fifo}"
DEPTHS=("$@")
[ ${#DEPTHS[@]} -eq 0 ] && DEPTHS=(4 8 16)

for f in "$YOSYS" "$SLANG_PLUGIN"; do
    [ -e "$f" ] || { echo "ERROR: missing '$f' (set YOSYS= / SLANG_PLUGIN=)" >&2; exit 3; }
done
mkdir -p "$OUT_DIR"
OLD_SV="$OUT_DIR/cdc_gray_fifo_old.sv"
git -C "$ROOT" show "$OLD_REF:rtl/soc/cdc/cdc_gray_fifo.sv" \
    | sed 's/module cdc_gray_fifo/module cdc_gray_fifo_old/; s/endmodule : cdc_gray_fifo/endmodule : cdc_gray_fifo_old/' \
    > "$OLD_SV"
[ -s "$OLD_SV" ] || { echo "ERROR: cannot read cdc_gray_fifo.sv at $OLD_REF" >&2; exit 3; }
NEW_SV="${NEW_SV:-$ROOT/rtl/soc/cdc/cdc_gray_fifo.sv}"   # override only for the negative control
SYNC_SV="$ROOT/rtl/soc/cdc/cdc_sync.sv"

rc=0
for d in "${DEPTHS[@]}"; do
    YS="$OUT_DIR/depth$d.ys"
    LOG="$OUT_DIR/depth$d.log"
    {
        echo "plugin -i $SLANG_PLUGIN"
        echo "read_slang --top cdc_gray_fifo_old -G DEPTH=$d -G WIDTH=$WIDTH $SYNC_SV $OLD_SV"
        echo "hierarchy -top cdc_gray_fifo_old; proc; flatten; opt_clean; memory; opt_clean; async2sync"
        echo "rename cdc_gray_fifo_old gold"
        echo "design -stash gold"
        echo "read_slang --top cdc_gray_fifo -G DEPTH=$d -G WIDTH=$WIDTH $SYNC_SV $NEW_SV"
        echo "hierarchy -top cdc_gray_fifo; proc; flatten; opt_clean; memory; opt_clean; async2sync"
        echo "rename cdc_gray_fifo gate"
        echo "design -stash gate"
        echo "design -copy-from gold -as gold gold"
        echo "design -copy-from gate -as gate gate"
        echo "equiv_make gold gate equiv"
        echo "hierarchy -top equiv"
        echo "equiv_simple -seq 5"
        echo "equiv_status"
        echo "equiv_induct -seq 20"
        echo "equiv_status -assert"
    } > "$YS"
    if "$YOSYS" -q -l "$LOG" -s "$YS" > /dev/null 2>&1; then
        echo "DEPTH=$d WIDTH=$WIDTH: PROVEN equivalent to $OLD_REF (equiv_status -assert passed)  log=$LOG"
    else
        echo "DEPTH=$d WIDTH=$WIDTH: NOT proven -- see $LOG"
        grep -E "nproven|Found|ERROR" "$LOG" | tail -4
        rc=1
    fi
done
exit $rc
