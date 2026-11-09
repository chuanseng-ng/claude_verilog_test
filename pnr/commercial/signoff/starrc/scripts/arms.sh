#!/bin/bash
# arms.sh -- single source of truth for the DEF of each arm.  Source it; defines arm_def <arm>.
# Paths are relative to the repo root.
arm_def() {
  case "$1" in
    openroad) echo pnr/commercial/runs/openroad/rv32i_cpu_top.def ;;
    icc2)     echo pnr/commercial/impl/icc2/runs/b5e_icc2/out/rv32i_cpu_top.def ;;
    innovus)  echo pnr/commercial/impl/innovus/runs/b5g_innovus/out/rv32i_cpu_top.def ;;   # b5c reroute (b5b superseded, not extracted for results)
    innovusb5h) echo pnr/commercial/impl/innovus/runs/b5h_innovus/out/rv32i_cpu_top.def ;;   # b5h: capTable + symmetric clk_io latency (arm name has no '_': the Makefile pattern splits on it)
    icc2b5m) echo pnr/commercial/impl/icc2/runs/b5m_icc2/out/rv32i_cpu_top.def ;;   # b5m: b5i + PDN strap-end trim + antenna diodes + net-name hygiene
    innovusb6) echo pnr/commercial/impl/innovus/runs/b6_innovus/out/rv32i_cpu_top.def ;;   # b6: full MMMC (ss/tt/ff) flow, taps at source, b5k ECO set folded in
    icc2b6) echo pnr/commercial/impl/icc2/runs/b6_icc2/out/rv32i_cpu_top.def ;;
    icc2b7) echo pnr/commercial/impl/icc2/runs/b7_icc2/out/rv32i_cpu_top.def ;;   # b7: b6 + hold/antenna/dout0 ECO
    innovusb7) echo pnr/commercial/impl/innovus/runs/b7_innovus/out/rv32i_cpu_top.def ;;   # b7: b6 + dout0/antenna ECO
    icc2b8pre) echo pnr/commercial/impl/icc2/runs/b8_icc2/out/pre/rv32i_cpu_top.def ;;   # b8 post-route pre-ECO
    innovusb8draft) echo pnr/commercial/impl/innovus/runs/b8_innovus/out_draft/rv32i_cpu_top.def ;;   # b8 draft finish
    icc2b8) echo pnr/commercial/impl/icc2/runs/b8_icc2/out/rv32i_cpu_top.def ;;
    icc2b9) echo pnr/commercial/impl/icc2/runs/b9_icc2/out/rv32i_cpu_top.def ;;   # b9 = b8 + ECO round 3
    innovusb8) echo pnr/commercial/impl/innovus/runs/b8_innovus/out/rv32i_cpu_top.def ;;   # b6: DC v2 MCMM netlist, ICC2 MCMM flow
    icc2b5i) echo pnr/commercial/impl/icc2/runs/b5i_icc2/out/rv32i_cpu_top.def ;;   # b5i: b5e routed + in-place met1-short / met4-spacing ECO (arm name has no '_')
    innovusb5j) echo pnr/commercial/impl/innovus/runs/b5j_innovus/out/rv32i_cpu_top.def ;;   # b5j: b5h routed + endcap n-well tie ECO (in-place)
    innovusb5k) echo pnr/commercial/impl/innovus/runs/b5k_innovus/out/rv32i_cpu_top.def ;;   # b5k: round 2 ECOs (hold, port repeaters, pin stubs, antenna diodes, npc.2 fill swap)
    *) echo "unknown arm $1" >&2; return 1 ;;
  esac
}
