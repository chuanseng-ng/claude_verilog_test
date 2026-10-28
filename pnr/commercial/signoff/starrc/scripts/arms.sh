#!/bin/bash
# arms.sh -- single source of truth for the DEF of each arm.  Source it; defines arm_def <arm>.
# Paths are relative to the repo root.
arm_def() {
  case "$1" in
    openroad) echo pnr/commercial/runs/openroad/rv32i_cpu_top.def ;;
    icc2)     echo pnr/commercial/impl/icc2/runs/b5a_icc2/out/rv32i_cpu_top.def ;;
    innovus)  echo pnr/commercial/impl/innovus/runs/b5c_innovus_s2/out/rv32i_cpu_top.def ;;   # b5c reroute (b5b superseded, not extracted for results)
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}
