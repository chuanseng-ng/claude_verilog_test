#=================================================================
# PSM supply-voltage declarations for IR-drop analysis
#
# Sourced by pnr/scripts/08_power.tcl, which skips IR-drop analysis
# entirely when this file is absent. GH #96 / bead claude_verilog_test-8nz.
#
# Why this file exists instead of RUN_IRDROP_REPORT: LibreLane's
# OpenROAD.IRDropReport step declares SPEF as a hard step input and its
# irdrop.tcl opens with `read_spef`, so it requires OpenROAD.RCX --
# and ASAP7's extraction ruleset (libs.tech/openlane/rcx_rules.pex) is a
# zero-byte file (bead claude_verilog_test-e69). analyze_power_grid itself
# needs no parasitics, so IR analysis is run standalone against the final
# ODB instead of in-flow.
#
# Voltage matches the ASAP7 RVT TT corner used throughout this flow
# (nom_tt_025C_0p7V -- 0.7 V nominal, 25 C).
#
# Caveat for whoever reads the resulting report: PSM uses the same M1-only
# connectivity model that produces the ~8.28 M benign PSM-0039
# "Unconnected instance TAP_TAPCELL_ROW_*" violations on this design. Expect
# the same unconnected-tap noise in the IR result; it is a tool artifact,
# not a real supply break.
#=================================================================

set_pdnsim_net_voltage -net VDD -voltage 0.7
set_pdnsim_net_voltage -net VSS -voltage 0.0
