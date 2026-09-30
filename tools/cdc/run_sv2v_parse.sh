#!/usr/bin/env bash
# run_sv2v_parse.sh — Verilog-2005 portability gate.
#
# Converts the SoC source list with sv2v and then PARSES AND ELABORATES the
# result with yosys. Nothing more: no CDC analysis, no synthesis, no PD.
#
# WHY THIS EXISTS
# ---------------
# Some constructs are legal SystemVerilog that Verilator accepts happily, but
# are NOT legal Verilog-2005. sv2v passes several of them through verbatim
# rather than lowering them, and yosys then rejects the generated file. The
# canonical example, which actually shipped in this repo:
#
#     pwdata[N-1:0] & strb_expand(pstrb)[N-1:0]
#                     ^^^^^^^^^^^^^^^^^^ part-select applied to a function call
#
#     sim/build/cdc/soc_top_flat.v:7355: ERROR: syntax error, unexpected '['
#
# That broke CI on PR #198 and was fixed in 2c5f351. It would also have broken
# BOTH physical-design flows, because Sky130 and ASAP7 are each sv2v-fronted.
#
# NO COCOTB SUITE CAN CATCH THIS CLASS. Verilator consumes the SystemVerilog
# directly and never sees sv2v's output, so the whole simulation regression can
# be green while the design is unsynthesisable.
#
# Before this script, the only thing that caught it was `make cdc`, which reads
# sv2v output incidentally on its way to a clock-domain analysis. That works,
# but it costs ~5 minutes and reports a parse error under a job named
# "CDC check", which is a confusing place to discover a syntax problem.
#
# WHY THE FILE LIST IS REGENERATED EVERY RUN
# ------------------------------------------
# The caller writes the flist from $(CDC_SOURCES) immediately before invoking
# this script. That is deliberate. A stale on-disk flist silently omits newly
# added modules, and a check that does not examine the thing under test passes
# for the wrong reason -- strictly worse than no check, because it manufactures
# confidence. This was hit for real: a hand-run of this check against a stale
# flist "passed" while omitting watchdog_timer entirely.
#
# Exit codes: 0 = parses and elaborates, 1 = sv2v failed, 2 = yosys rejected
# the generated Verilog, 3 = a required tool is missing.

set -uo pipefail

: "${CDC_CACHE:?CDC_CACHE must be set (cache + output directory)}"
: "${CDC_FLIST:?CDC_FLIST must be set (file list, freshly generated)}"
: "${CDC_TOP:=soc_top}"
: "${CDC_INCDIRS:=}"

export PATH="$CDC_CACHE/oss-cad-suite/bin:$CDC_CACHE/sv2v-Linux:$PATH"

command -v sv2v >/dev/null 2>&1 || {
    echo "ERROR: sv2v not found. Run tools/cdc/fetch_cdc_tools.sh" >&2; exit 3; }
command -v yosys >/dev/null 2>&1 || {
    echo "ERROR: yosys not found. Run tools/cdc/fetch_cdc_tools.sh --with-yosys" >&2; exit 3; }

mapfile -t FILES < "$CDC_FLIST"
[[ ${#FILES[@]} -gt 0 ]] || { echo "ERROR: $CDC_FLIST is empty." >&2; exit 3; }

INC_FLAGS=()
for d in $CDC_INCDIRS; do INC_FLAGS+=("-I$d"); done

OUT="$CDC_CACHE/${CDC_TOP}_sv2v_parse.v"

echo "== [1/2] sv2v: SystemVerilog -> Verilog-2005 (${#FILES[@]} files) =="
if ! sv2v "${INC_FLAGS[@]}" "--top=$CDC_TOP" "${FILES[@]}" > "$OUT"; then
    echo "ERROR: sv2v failed to convert the source list." >&2
    exit 1
fi

echo "== [2/2] yosys: parse + elaborate the generated Verilog =="
if ! yosys -q -p "read_verilog -sv $OUT; hierarchy -top $CDC_TOP"; then
    echo >&2
    echo "ERROR: yosys rejected sv2v's output -- the design is not synthesisable." >&2
    echo >&2
    echo "  Generated file: $OUT" >&2
    echo >&2
    echo "  This is a Verilog-2005 portability break, not a simulation bug. No" >&2
    echo "  cocotb suite can catch it: Verilator reads the SystemVerilog directly" >&2
    echo "  and never sees sv2v's output. It WILL break both PD flows." >&2
    echo >&2
    echo "  Most common cause -- a part-select applied to a function call:" >&2
    echo "      bad:  pwdata[N-1:0] & strb_expand(pstrb)[N-1:0]" >&2
    echo "      good: assign mask_w = strb_expand(pstrb);" >&2
    echo "            pwdata[N-1:0] & mask_w[N-1:0]" >&2
    echo >&2
    echo "  Use the file:line from the yosys error above, then map it back to the" >&2
    echo "  .sv source by the enclosing module name." >&2
    exit 2
fi

echo "OK: sv2v output parses and elaborates ($CDC_TOP)."
