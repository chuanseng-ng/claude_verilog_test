###############################################################################
# pdn.tcl — Power Distribution Network for phase5_soc on ASAP7
#
# Extends the shared pdn_asap7.tcl pattern used by CPU and GPU blocks.
# SoC uses a denser M5/M7 strap grid to serve both hard macros.
#
# Single-domain topology: PD_CPU / PD_GPU / PD_SRAM / PD_PERIPH all share
# the single VDD/VSS rail at 0.7 V.  UPF isolation is a design-intent model;
# OpenROAD does not differentiate physical supply nets in this flow.
###############################################################################

source $::env(SCRIPTS_DIR)/openroad/common/set_global_connections.tcl
set_global_connections

set secondary []
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

set_voltage_domain -name CORE \
    -power $::env(VDD_NET) \
    -ground $::env(GND_NET) \
    -secondary_power $secondary

###############################################################################
# Standard-cell PDN grid
# M1 followpins → M2 V-stripes → M5 H-stripes → M7 V-stripes (coarser)
# Wider pitches than CPU/GPU because flat logic area is ~360×700 µm.
###############################################################################

define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    -pins "M7 M5 M2"

# M7 vertical stripes (coarsest — top-level SoC strap)
# M7 WIDTHTABLE: 0.032 0.160 0.288 0.416 0.544 — must use 0.160 (0.144 is invalid)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer M7 \
    -width 0.160 \
    -pitch $::env(FP_PDN_VPITCH) \
    -offset $::env(FP_PDN_VOFFSET) \
    -spacing 0.160 \
    -starts_with POWER -extend_to_core_ring

# M5 horizontal stripes (mid-level)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer M5 \
    -width 0.120 \
    -pitch $::env(FP_PDN_HPITCH) \
    -offset $::env(FP_PDN_HOFFSET) \
    -spacing 0.120 \
    -starts_with POWER -extend_to_core_ring

# M2 vertical stripes (dense — connect M1 rails to M5 grid)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer M2 \
    -width 0.018 \
    -pitch 1.62 \
    -offset 0.5 \
    -spacing 0.018 \
    -starts_with POWER

# M1 followpins rails
add_pdn_stripe \
    -grid stdcell_grid \
    -layer M1 \
    -width $::env(FP_PDN_RAIL_WIDTH) \
    -followpins \
    -starts_with POWER

# Via connections
add_pdn_connect -grid stdcell_grid -layers "M1 M2"
add_pdn_connect -grid stdcell_grid -layers "M2 M5"
add_pdn_connect -grid stdcell_grid -layers "M5 M7"

###############################################################################
# Hard-macro PDN grid
# Macro ring on M6/M7 (outer perimeter of each hard macro).
# LibreLane's PDN_CONNECT_MACROS_TO_GRID=true connects the ring to the global
# SoC stripes automatically.
###############################################################################

define_pdn_grid \
    -macro \
    -default \
    -name macro_grid \
    -starts_with POWER \
    -halo "$::env(PL_MACRO_HALO)"

add_pdn_ring \
    -grid macro_grid \
    -layers {M6 M7} \
    -widths {0.160 0.160} \
    -spacings {0.160 0.160} \
    -core_offsets {0.5 0.5}

add_pdn_connect -grid macro_grid -layers "M6 M7"
add_pdn_connect -grid macro_grid -layers "M5 M6"
