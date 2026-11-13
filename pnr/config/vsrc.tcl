# vsrc.tcl - PSM supply-voltage declarations for IR-drop analysis (ASAP7)
#
# Scope: sourced by pnr/scripts/08_power.tcl. The script skips IR-drop analysis entirely when this file is absent.
# Contents: set_pdnsim_net_voltage for the VDD net (nominal supply) and the VSS net (ground).
# User rules:
#   The VDD value matches the ASAP7 RVT TT corner nom_tt_025C_0p7V used throughout this flow. Change it when the corner changes.
#   IR drop runs standalone because the LibreLane IR-drop step needs SPEF and the ASAP7 RCX rule file is empty.
#   Expect unconnected-tap noise in the IR result. It is a tool artifact, not a real supply break.
# Doc: tm:pd:config-vsrc-tcl

set_pdnsim_net_voltage -net VDD -voltage 0.7
set_pdnsim_net_voltage -net VSS -voltage 0.0
