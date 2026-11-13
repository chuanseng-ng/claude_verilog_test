# pdn.tcl - Power grid for sky130_soc on Sky130A HD: met1 followpins, met4 V-stripes, met5 H-stripes
#
# Scope: pnr/sky130/soc/config.json and config_rccal.json set FP_PDN_CFG to this file.
# Contents: global connections; voltage domain CORE; grid stdcell_grid (met5 and met4 stripes, met1 followpin rails,
#   met1-met4 and met4-met5 connections); macro grid macro_grid with a halo and a met4-met5 connection.
# Inputs: environment variables SCRIPTS_DIR, VDD_NET, VDD_NETS, GND_NET, GND_NETS, FP_PDN_HPITCH, FP_PDN_HOFFSET,
#   FP_PDN_VPITCH, FP_PDN_VOFFSET and FP_PDN_RAIL_WIDTH.
# User rules:
#   The SoC has a single power domain (VPWR and VGND).
#   IR-drop analysis (OpenROAD.IRDropReport) is not meaningful in this flow.
#   VSRC_LOC_FILES is not set in pnr/sky130/soc/config.json, config_rccal.json or pnr/sky130/cpu/config.json.
#   Do not write a VSRC_LOC_FILES file until a pad or bump plan exists. The meaningful PDN check is PSM-0040 connectivity.
#   Do not add add_pdn_ring around the macros. Do not add a met3-met4 macro connect:
#   it adds met4 minimum-area DRC errors on the SRAM, and the met4 pins connect without it.
#   The 4 KB SRAM macro is not KLayout-DRC clean. Its violations are inside its own OpenRAM-generated cells and are accepted and documented.
#   State the result as: KLayout DRC has violations, all macro-internal, from the upstream OpenRAM generator. Do not state it as clean.
#   Timing is a typical-corner sign-off. The SRAM macro has one corner only. See the header of constraints/sky130_soc.sdc.
# Doc: tm:pd:sky130-soc-pdn-tcl, cr:pd:sky130-soc-pdn-tcl

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
