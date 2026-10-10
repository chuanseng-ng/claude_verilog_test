#!/usr/bin/env bash
# Combinational equivalence of ONE module: (gate) real-Synlig elaboration run
# through the proc sequence + librelane_opt(nodffe,nosdff)x5 (the frontend/opt
# stage whose OPT_MUXTREE misbehaviour ma7/u99 allege) versus (gold) sv2v ->
# read_verilog -sv with proc only (no optimisation). `miter` + SAT proves or
# produces a counter-example. Only valid for modules with no state.
#
# usage: equiv_synlig_comb.sh <module> <file.sv> <out_dir>
set -euo pipefail
MOD="$1"; SRC="$2"; OUT="$3"
SYN46=/nix/store/y4lsl792fjahppq4xk68s5ckh7mwks70-yosys-with-plugins/bin/yosys
Y62=/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys
SV2V=/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v
mkdir -p "$OUT"
OPT='opt_expr
opt_merge -nomux
opt_muxtree
opt_reduce
opt_merge
opt_dff -nodffe -nosdff
opt_clean'
cat > "$OUT/$MOD.gate.ys" <<EOF
plugin -i synlig-sv
read_systemverilog -sverilog -top $MOD $SRC
hierarchy -top $MOD -nokeep_prints -nokeep_asserts
proc_clean
proc_rmdead
proc_prune
proc_init
proc_arst
proc_rom
proc_mux
proc_dff
proc_memwr
proc_clean
opt_expr
opt_clean
$OPT
$OPT
$OPT
$OPT
$OPT
opt_expr
opt_clean
rename $MOD gate
tee -o $OUT/$MOD.gate.stat stat
write_rtlil $OUT/$MOD.gate.il
EOF
"$SYN46" -q -l "$OUT/$MOD.gate.log" -s "$OUT/$MOD.gate.ys" > /dev/null 2>&1
grep -c "Removed .* multiplexer ports" "$OUT/$MOD.gate.log" | sed 's/^/opt_muxtree invocations logging removals: /' || true
"$SV2V" "$SRC" > "$OUT/$MOD.sv2v.v"
cat > "$OUT/$MOD.gold.ys" <<EOF
read_verilog -sv $OUT/$MOD.sv2v.v
hierarchy -top $MOD
proc
opt_clean
rename $MOD gold
write_rtlil $OUT/$MOD.gold.il
EOF
"$Y62" -q -l "$OUT/$MOD.gold.log" -s "$OUT/$MOD.gold.ys" > /dev/null 2>&1
cat > "$OUT/$MOD.miter.ys" <<EOF
read_rtlil $OUT/$MOD.gold.il
read_rtlil $OUT/$MOD.gate.il
miter -equiv -flatten -make_assert gold gate miter
hierarchy -top miter
sat -verify -prove-asserts -show-inputs -show-outputs -timeout 600 miter
EOF
"$Y62" -l "$OUT/$MOD.miter.log" -s "$OUT/$MOD.miter.ys" > /dev/null 2>&1 || true
grep -E "SUCCESS|FAIL|Counter|QED|failed" "$OUT/$MOD.miter.log" | head -5
