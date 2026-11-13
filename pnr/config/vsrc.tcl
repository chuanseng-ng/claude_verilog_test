#=================================================================
# PSM supply-voltage declarations for IR-drop analysis
#
# Sourced by pnr/scripts/08_power.tcl, which skips IR-drop analysis
# entirely when this file is absent. GH #96 / bead claude_verilog_test-8nz.
#
#
# Voltage matches the ASAP7 RVT TT corner used throughout this flow
# (nom_tt_025C_0p7V -- 0.7 V nominal, 25 C).
#=================================================================
# Doc: tm:pd:config-vsrc-tcl

set_pdnsim_net_voltage -net VDD -voltage 0.7
set_pdnsim_net_voltage -net VSS -voltage 0.0
