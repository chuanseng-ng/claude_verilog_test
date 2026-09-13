# Thin wrapper around the shared ASAP7 grid (see ../pdn_asap7_orfs.tcl).
#
# NOT yet referenced by any SoC config. `config.json` and `config_multiclock.json`
# still point at `pdn.tcl`, which carries the same M1->M5 defect, because run 14 and
# run 23 must stay byte-reproducible (CLAUDE.md). Point `PDN_CFG` here when the SoC
# is re-closed on the fixed grid.
#
# Verified 2026-09-12 on run 23's step-15 ODB with the standalone harness:
#   0 remaining channels, 372 594 VDD / 373 316 VSS shapes,
#   check_power_grid PASS on both nets, 0 unconnected shapes and instances.
#
# ⚠️ Macro PG pin layers change when the blocks are re-run on this grid. The shared
# file declares `-pins {M6}`, so a regenerated rv32i_cpu_top / gpu_top LEF will expose
# its PG pins on M6, not the current M4 (CPU) / M5 (GPU). The shared file's macro grid
# already connects M4<->M5 and M5<->M6, which covers that transition -- do not re-declare
# either pair here, pdngen rejects a duplicate with PDN-0186.
source [file join [file dirname [file normalize [info script]]] .. pdn_asap7_orfs.tcl]
