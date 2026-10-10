#!/usr/bin/env bash
# Attribution experiment (bead dud4): is the gate-vs-RTL failure introduced by the
# FRONTEND + coarse optimisation (the stage ma7/u99 blame), or by something later
# in the flow (ABC / resizer / ECO repair / PD)?
#
# Elaborates the full rv32i_cpu_top (Sky130 CPU config file list, +define SRAM_SKY130)
# two ways, takes each through proc + flatten + the librelane_opt(nodffe,nosdff) x5
# loop -- and STOPS there (no memory_map/techmap/abc/PD) -- then simulates each
# result with the unmodified ma7 yosys harness (tb_cpu_macro_check.v):
#   synlig: real Synlig frontend (the yosys-0.46 binary LibreLane invokes)
#   sv2v  : sv2v -> yosys read_verilog -sv (what the Sky130 SoC fabric flow uses)
# usage: frontend_sim_check.sh <rtl_root> <rom.hex> <out_dir> <halt_cyc> <read_cyc> <n_cycles>
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GLS="$HERE/.."
R="$1/rtl"; ROM="$2"; OUT="$3"; HALT="$4"; READ="$5"; NCYC="$6"
SYN46=/nix/store/y4lsl792fjahppq4xk68s5ckh7mwks70-yosys-with-plugins/bin/yosys
Y62=/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62/bin/yosys
SV2V=/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v
SRAM_MODEL="$1/sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv"
mkdir -p "$OUT"; cp "$ROM" "$OUT/rom_cpu_check.hex"
FILES="$R/soc/axi_pkg.sv $R/soc/soc_addr_map_pkg.sv $R/cpu/core/rv32i_pipeline_pkg.sv $R/mem/rv32i_cache_pkg.sv
$R/cpu/core/rv32i_alu.sv $R/cpu/core/rv32i_branch_comp.sv $R/cpu/core/rv32i_imm_gen.sv $R/cpu/core/rv32i_regfile.sv
$R/cpu/core/rv32i_decode.sv $R/cpu/core/rv32i_forwarding_unit.sv $R/cpu/core/rv32i_hazard_unit.sv
$R/cpu/core/rv32i_interrupt_ctrl.sv $R/cpu/core/rv32i_csr_file.sv
$R/cpu/core/pipeline/rv32i_pipeline_if.sv $R/cpu/core/pipeline/rv32i_pipeline_id.sv $R/cpu/core/pipeline/rv32i_pipeline_ex.sv
$R/cpu/core/pipeline/rv32i_pipeline_ex1c.sv $R/cpu/core/pipeline/rv32i_pipeline_ex1b.sv $R/cpu/core/pipeline/rv32i_pipeline_ex2.sv
$R/cpu/core/pipeline/rv32i_pipeline_mem.sv $R/cpu/core/pipeline/rv32i_pipeline_wb.sv
$R/mem/rv32i_icache.sv $R/mem/rv32i_dcache.sv $R/mem/rv32i_cache_arbiter.sv $R/cpu/core/rv32i_core.sv $R/cpu/rv32i_cpu_top.sv"
FILES="$(echo $FILES)"   # collapse newlines: a yosys script command must be one line
STUB="$HERE/../../../../pnr/sky130/sky130_sram_1kbyte_1rw1r_32x256_8_stub.v"
OPT='opt_expr
opt_merge -nomux
opt_muxtree
opt_reduce
opt_merge
opt_dff -nodffe -nosdff
opt_clean'
PROC='proc_clean
proc_rmdead
proc_prune
proc_init
proc_arst
proc_rom
proc_mux
proc_dff
proc_memwr
proc_clean'

cat > "$OUT/synlig.ys" <<EOF
plugin -i synlig-sv
read_systemverilog -sverilog -DSRAM_SKY130 -top rv32i_cpu_top $STUB $FILES
hierarchy -top rv32i_cpu_top -nokeep_prints -nokeep_asserts
$PROC
opt_expr
flatten
opt_expr
opt_clean
$OPT
$OPT
$OPT
$OPT
$OPT
opt_expr
opt_clean
tee -o $OUT/synlig.stat stat
write_rtlil $OUT/synlig.il
EOF
"$SYN46" -q -l "$OUT/synlig.log" -s "$OUT/synlig.ys" > /dev/null 2>&1

# sv2v reference: SRAM_SKY130 selects the macro instances; the SRAM model stays a separate module
"$SV2V" --define=SRAM_SKY130 $FILES > "$OUT/cpu_sv2v.v"
cat > "$OUT/sv2v.ys" <<EOF
read_verilog -sv -DSRAM_SKY130 $SRAM_MODEL
read_verilog -sv $OUT/cpu_sv2v.v
hierarchy -top rv32i_cpu_top
$PROC
opt_expr
flatten
opt_expr
opt_clean
$OPT
$OPT
$OPT
$OPT
$OPT
opt_expr
opt_clean
tee -o $OUT/sv2v.stat stat
write_rtlil $OUT/sv2v.il
EOF
"$Y62" -q -l "$OUT/sv2v.log" -s "$OUT/sv2v.ys" > /dev/null 2>&1

for arm in synlig sv2v; do
  cat > "$OUT/sim_$arm.ys" <<EOF
read_rtlil $OUT/$arm.il
$( [ $arm = synlig ] && echo "read_verilog -sv $SRAM_MODEL" )
read_verilog $GLS/tb_cpu_macro_check.v
hierarchy -top tb_cpu_macro_check
chparam -set HALT_START_CYC $HALT -set READ_START_CYC $READ tb_cpu_macro_check
proc
flatten
sim -vcd $OUT/$arm.vcd -clock clk_i -resetn rst_n_i -rstlen 5 -n $NCYC -zinit tb_cpu_macro_check
EOF
  (cd "$OUT" && timeout 3000 "$Y62" -Q -T -l "$OUT/sim_$arm.log" "$OUT/sim_$arm.ys" > /dev/null 2>&1) || true
  echo "== $arm: yosys errors: $(grep -c ERROR "$OUT/sim_$arm.log" || true)"
  python3 "$HERE/vcd_last.py" "$OUT/$arm.vcd" apb_prdata_captured
  python3 "$GLS/parse_cpu_commit_trace.py" "$OUT/$arm.vcd" | awk 'NR<=1 || /pc=0x00(10|14|18|20|24|28)/' | head -12
done
