#!/usr/bin/env bash
# Run equiv_synlig_comb.sh over the stateless CPU core modules.
# usage: equiv_all_comb.sh <rtl_root (contains rtl/)> <out_dir>
set -u
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
R="$1"; O="$2"
for m in rv32i_hazard_unit rv32i_forwarding_unit rv32i_alu rv32i_branch_comp rv32i_decode rv32i_imm_gen; do
  printf '%s: ' "$m"
  bash "$HERE/equiv_synlig_comb.sh" "$m" "$R/rtl/cpu/core/$m.sv" "$O" 2>&1 | tr '\n' ' '
  echo
done
