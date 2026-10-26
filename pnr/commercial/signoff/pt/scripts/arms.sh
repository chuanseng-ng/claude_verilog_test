#!/bin/bash
# arms.sh -- single source of truth for the netlist and SPEF of each judged arm.  Source it.
#   arm_netlist <arm>            routed post-route netlist (repo-root relative)
#   arm_spef    <arm> <rc>       SPEF for RC corner rc (nom|min|max), repo-root relative
# Arms:  openroad      OpenROAD netlist + StarRC SPEFs      (judge)
#        icc2          ICC2 netlist     + StarRC SPEFs      (judge)
#        innovus       Innovus b5c      + StarRC SPEFs      (judge; PENDING until b5c out/ and starrc innovus_* exist)
#        openroad_rcx  OpenROAD netlist + OpenRCX SPEFs     (sanity: separates extractor from STA engine)
# PT_STARRC_DIR overrides where the StarRC SPEFs are read from (the "untuned" pass reads the frozen runs/_superseded_untuned copies).
STARRC=${PT_STARRC_DIR:-pnr/commercial/signoff/starrc/runs}
arm_netlist() {
  case "$1" in
    openroad|openroad_rcx) echo pnr/commercial/runs/openroad/rv32i_cpu_top.nl.v ;;
    icc2)    echo pnr/commercial/impl/icc2/runs/b5a_icc2/out/rv32i_cpu_top.nl.v ;;
    innovus) echo pnr/commercial/impl/innovus/runs/b5c_innovus_s2/out/rv32i_cpu_top.nl.v ;;
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}
arm_spef() {
  case "$1" in
    openroad|icc2|innovus) echo $STARRC/$1_$2/rv32i_cpu_top.$2.spef ;;
    openroad_rcx)          echo pnr/commercial/runs/openroad/rv32i_cpu_top.$2.spef ;;
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}
# StarRC completion marker (star/.starrc_complete) -- only for StarRC arms
arm_spef_marker() {
  case "$1" in
    openroad|icc2|innovus) echo $STARRC/$1_$2/star/.starrc_complete ;;
    *) echo "" ;;
  esac
}
