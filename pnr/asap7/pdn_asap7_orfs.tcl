# pdn_asap7_orfs.tcl - Shared ASAP7 PDN grid for blocks: M1 and M2 followpins, then M5 and M6 stripes
#
# Scope: cpu/pdn_orfs.tcl and gpu/pdn_orfs.tcl source this file. config_3014.json of the CPU and the GPU sets PDN_CFG to them.
#   soc/pdn_orfs.tcl sources it too, but no SoC config names that wrapper.
# Contents: global connections; voltage domain CORE; grid top with M1 and M2 followpin rails (one per row), M5 and M6 stripes
#   and the M1-M2, M2-M5 and M5-M6 connections; macro grid with M4-M5 and M5-M6 connections.
# Inputs: environment variables SCRIPTS_DIR, VDD_NET and GND_NET.
# User rules:
#   The grid follows the ORFS ASAP7 reference grid: followpins on both M1 and M2, so every rail has an M2 partner above it.
#   The macro grid connects M4 to M5 because the SRAM macro PG pins are on M4 (sram_1rw_256x32_asap7.lef).
#   IR drop analysis also needs VIAS_R in the config. ASAP7 ships no via resistances, and PSM aborts without them.
#   Take the VIAS_R values from the ORFS setRC.tcl of the ASAP7 platform.
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
# Macro halo: the ORFS value (MACRO_ROWS_HALO_X and MACRO_ROWS_HALO_Y). A larger halo made no difference to the channel failure and only costs routing area.
###############################################################################
define_pdn_grid -macro -default -name macro -halo "2 2" -voltage_domains CORE

add_pdn_connect -grid macro -layers {M4 M5}
add_pdn_connect -grid macro -layers {M5 M6}
