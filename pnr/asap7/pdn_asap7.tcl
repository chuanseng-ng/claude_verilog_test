# pdn_asap7.tcl - Power grid script for an ASAP7 block: M1 followpins, M2 V-stripes, M5 H-stripes
#
# Scope: no config.json in pnr/asap7 names this file today. pnr/asap7/soc/pdn.tcl extends this pattern.
# Contents: global connections; secondary VDD and GND nets; voltage domain CORE; grid stdcell_grid with M5 and M2 stripes
#   and M1 followpin rails; M1-M2 and M2-M5 connections; default macro grid with an M2-M5 connection.
# Inputs: environment variables SCRIPTS_DIR, VDD_NET, VDD_NETS, GND_NET, GND_NETS, FP_PDN_HPITCH, FP_PDN_HOFFSET,
#   FP_PDN_RAIL_WIDTH, FP_PDN_HORIZONTAL_HALO and FP_PDN_VERTICAL_HALO.
# User rules:
#   Pass only VDD nets to -secondary_power. It does not accept ground nets.
#   The M5 stripe width must come from the M5 WIDTHTABLE.
#   The CPU and GPU blocks use pdn_asap7_orfs.tcl through their pdn_orfs.tcl wrappers.
# Doc: tm:pd:asap7-pdn-tcl
source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set secondary []

# Secondary VDD nets only — -secondary_power accepts power nets, not ground nets.
foreach vdd $::env(VDD_NETS) {
    if { $vdd != $::env(VDD_NET) } {
        lappend secondary $vdd
        set db_net [[ord::get_db_block] findNet $vdd]
        if { $db_net == "NULL" } {
            set net [odb::dbNet_create [ord::get_db_block] $vdd]
            $net setSpecial
            $net setSigType "POWER"
        }
    }
}

# Secondary GND nets — create dbNets so PDN can reference them, but do NOT pass
# these to -secondary_power (which accepts VDD nets only).  Route additional
# ground domains via a separate set_voltage_domain -ground call when needed.
foreach gnd $::env(GND_NETS) {
    if { $gnd != $::env(GND_NET) } {
        set db_net [[ord::get_db_block] findNet $gnd]
        if { $db_net == "NULL" } {
            set net [odb::dbNet_create [ord::get_db_block] $gnd]
            $net setSpecial
            $net setSigType "GROUND"
        }
    }
}

set_voltage_domain -name CORE -power $::env(VDD_NET) -ground $::env(GND_NET) \
    -secondary_power $secondary

# ASAP7 PDN: M1 followpins, M2 V-stripes, M5 H-stripes. M2 connects the M1 rails by vias. M5 connects the M2 stripes.
define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    -pins "M5 M2"

# M5 horizontal stripes (coarse).
# Width must be from M5 WIDTHTABLE: 0.024, 0.120, 0.216, ... Use 0.120
add_pdn_stripe \
    -grid stdcell_grid \
    -layer M5 \
    -width 0.120 \
    -pitch $::env(FP_PDN_HPITCH) \
    -offset $::env(FP_PDN_HOFFSET) \
    -spacing 0.120 \
    -starts_with POWER -extend_to_core_ring

# M2 vertical stripes (dense) - connect the M1 rails to the M5 grid.
add_pdn_stripe \
    -grid stdcell_grid \
    -layer M2 \
    -width 0.018 \
    -pitch 1.62 \
    -offset 0.5 \
    -spacing 0.018 \
    -starts_with POWER

# M1 followpins rails (every cell row)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer M1 \
    -width $::env(FP_PDN_RAIL_WIDTH) \
    -followpins \
    -starts_with POWER

# Via connections: M1→M2, M2→M5
add_pdn_connect -grid stdcell_grid -layers "M1 M2"
add_pdn_connect -grid stdcell_grid -layers "M2 M5"

# Macro default grid
define_pdn_grid \
    -macro \
    -default \
    -name macro \
    -starts_with POWER \
    -halo "$::env(FP_PDN_HORIZONTAL_HALO) $::env(FP_PDN_VERTICAL_HALO)"

add_pdn_connect \
    -grid macro \
    -layers "M2 M5"
