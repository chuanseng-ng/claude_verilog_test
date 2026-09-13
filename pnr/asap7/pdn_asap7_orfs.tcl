###############################################################################
# pdn_asap7_orfs.tcl — ASAP7 PDN grid that actually builds (beads `gyx` / `4l8`)
#
# WHY THIS FILE EXISTS
# --------------------
# Every ASAP7 run in this repo up to 2026-09-12 committed ZERO power-grid
# shapes.  `pdngen` is `check_setup; build_grids; write_to_db; reset_shapes`,
# and the previous topology made `build_grids` abort with
#   [ERROR PDN-0179] Unable to repair all channels
# *before* `write_to_db` ever ran.  The local warn-and-continue patch in
# librelane's `pdn.tcl` swallowed that error, so the flow proceeded with no PDN
# and reported it as a "benign tap-cell artifact".  See
# `docs/PHASE5_RUN_HISTORY.md` §"PDN caveat" and `memory/pd/knowledge.md`.
#
# ROOT CAUSE OF PDN-0179
# ----------------------
# The old topology connected the M1 followpin rails DIRECTLY to the M5 straps
# (a four-layer stack) and used M2 only as a sparse 4.5 µm-pitch strap running
# PARALLEL to those rails.  ASAP7 std-cell rails sit on M1 running horizontally
# (M1's non-preferred direction), so most rails had nothing reachable to
# connect to, and channel repair could not fix them: 27 unrepairable channels,
# all on M1, in the macro-free regions x 82.19–124.96 µm and y 104.19–123.42 µm.
#
# THE FIX — follow the ORFS ASAP7 reference grid
# ----------------------------------------------
# Ported from OpenROAD-flow-scripts
# `flow/platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl`: put followpins
# on BOTH M1 and M2 (0.018 µm wide, 0.54 µm pitch — one per row), then climb
# M2→M5→M6.  Every rail now has an M2 partner directly above it, so there are
# no channels to repair.
#
# MEASURED on the CPU block (`RUN_2026-09-10_05-13-18` step-18 ODB):
#   old topology : 0 channels repaired, 0 shapes committed, PSM-0069 on both nets
#   this file    : 0 remaining channels, 27 999 VDD / 27 213 VSS shapes,
#                  `check_power_grid` PASS on both nets, and
#                  [INFO PSM-0040] All shapes on net VDD/VSS are connected.
#   IR drop then runs: worst 1.28 mV VDD (0.18 %) / 1.31 mV VSS (0.19 %).
#
# NOTE: IR drop additionally needs `VIAS_R` in the config — ASAP7 shipped no
# via resistances, so PSM aborted with `PSM-0021` ("Resistance map contains
# invalid values") even once connectivity was clean.  Values in the configs are
# ORFS's (`flow/platforms/asap7/setRC.tcl`).
#
# The macro grid connects M4↔M5 because the SRAM macro PG pins are on M4
# (`sram_1rw_256x32_asap7.lef`); ORFS's own ElementGrid only needs M5↔M6.
###############################################################################

source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set_voltage_domain -name CORE \
    -power $::env(VDD_NET) \
    -ground $::env(GND_NET)

###############################################################################
# Standard-cell grid: M1 + M2 followpins (one per row) → M5 → M6
###############################################################################
define_pdn_grid -name top -voltage_domains CORE -pins {M6}

add_pdn_stripe -grid top -layer M1 -width 0.018 -pitch 0.54 -offset 0 -followpins
add_pdn_stripe -grid top -layer M2 -width 0.018 -pitch 0.54 -offset 0 -followpins

# Strap pitches are 2x ORFS's (M5 2.16 / M6 4.32). ORFS's density is aimed at much
# larger blocks; on this 130x130 um CPU it spends routing tracks we need. Measured
# worst-case IR drop on the CPU block, against a typical 5 % budget:
#   M5 2.16 / M6 4.32  -> 0.18 % VDD / 0.19 % VSS   (27 999 shapes)
#   M5 4.32 / M6 8.64  -> 0.51 % / 0.52 %           (13 988 shapes)
#   M5 6.48 / M6 12.96 -> 1.33 % / 1.37 %           ( 9 792 shapes)  <- chosen
# All three build cleanly (0 channels, check_power_grid PASS, 0 unconnected), so this
# is purely an IR-vs-routing-headroom trade, and IR has ~4x margin left even at the
# sparsest setting. The sparsest is what this host can actually route: at ORFS density
# detailed routing reached 122 121 violations and 13.4 GB at 90 % of iteration 0 (of 12)
# and was OOM-killed on a 15.9 GB machine -- twice, once taking the terminal scope with
# it via systemd-oomd. Revisit the density if this ever runs on a larger host.
add_pdn_stripe -grid top -layer M5 -width 0.12  -spacing 0.072 -pitch 6.48  -offset 1.50
add_pdn_stripe -grid top -layer M6 -width 0.288 -spacing 0.096 -pitch 12.96 -offset 1.504

add_pdn_connect -grid top -layers {M1 M2}
add_pdn_connect -grid top -layers {M2 M5}
add_pdn_connect -grid top -layers {M5 M6}

###############################################################################
# Macro grid — SRAM PG pins are on M4, so M4↔M5 is required here.
# Halo 2 µm (ORFS MACRO_ROWS_HALO_X/Y); the old 10 µm halo made no difference
# to the channel failure and only costs routing area.
###############################################################################
define_pdn_grid -macro -default -name macro -halo "2 2" -voltage_domains CORE

add_pdn_connect -grid macro -layers {M4 M5}
add_pdn_connect -grid macro -layers {M5 M6}
