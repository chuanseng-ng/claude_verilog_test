###############################################################################
# pdn_asap7_orfs.tcl — ASAP7 PDN grid that actually builds (beads `gyx` / `4l8`)
#
# THE FIX — follow the ORFS ASAP7 reference grid
# ----------------------------------------------
# Ported from OpenROAD-flow-scripts
# `flow/platforms/asap7/openRoad/pdn/BLOCKS_grid_strategy.tcl`: put followpins
# on BOTH M1 and M2 (0.018 µm wide, 0.54 µm pitch — one per row), then climb
# M2→M5→M6.  Every rail now has an M2 partner directly above it, so there are
# no channels to repair.
# NOTE: IR drop additionally needs `VIAS_R` in the config — ASAP7 shipped no
# via resistances, so PSM aborted with `PSM-0021` ("Resistance map contains
# invalid values") even once connectivity was clean.  Values in the configs are
# ORFS's (`flow/platforms/asap7/setRC.tcl`).
#
# The macro grid connects M4↔M5 because the SRAM macro PG pins are on M4
# (`sram_1rw_256x32_asap7.lef`); ORFS's own ElementGrid only needs M5↔M6.
###############################################################################
# Doc: tm:pd:asap7-pdn-orfs-tcl, cr:pd:asap7-pdn-orfs-tcl

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
