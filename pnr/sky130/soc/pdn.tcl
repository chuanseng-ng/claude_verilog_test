###############################################################################
# pdn.tcl — Power Distribution Network for sky130_soc on Sky130A HD
#
# Doc: cr:pd:sky130-soc-pdn-tcl

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
# met1 followpins -> met4 V-stripes -> met5 H-stripes
###############################################################################

define_pdn_grid \
    -name stdcell_grid \
    -starts_with POWER \
    -voltage_domain CORE \
    -pins "met5 met4"

# met5 horizontal stripes (coarsest — top-level H distribution)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer met5 \
    -width 3.1 \
    -pitch $::env(FP_PDN_HPITCH) \
    -offset $::env(FP_PDN_HOFFSET) \
    -spacing 2.0 \
    -starts_with POWER -extend_to_core_ring

# met4 vertical stripes (primary distribution)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer met4 \
    -width 3.1 \
    -pitch $::env(FP_PDN_VPITCH) \
    -offset $::env(FP_PDN_VOFFSET) \
    -spacing 2.0 \
    -starts_with POWER -extend_to_core_ring

# met1 followpins rails (standard-cell power rails)
add_pdn_stripe \
    -grid stdcell_grid \
    -layer met1 \
    -width $::env(FP_PDN_RAIL_WIDTH) \
    -followpins \
    -starts_with POWER

# Via connections: met1->met4 (OpenROAD generates via1/via2/via3 stack)
add_pdn_connect -grid stdcell_grid -layers "met1 met4"
# met4->met5 via4 stack
add_pdn_connect -grid stdcell_grid -layers "met4 met5"


define_pdn_grid \
    -macro \
    -default \
    -name macro_grid \
    -starts_with POWER \
    -halo "10 10"

add_pdn_connect -grid macro_grid -layers "met4 met5"
