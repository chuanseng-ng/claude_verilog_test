# asap7.sdc - Minimal timing constraints for rv32i_hazard_unit_hls (ASAP7, one clock port clk)
#
# Scope: the config.json of this directory sets PNR_SDC_FILE, SIGNOFF_SDC_FILE and FALLBACK_SDC_FILE to this file.
#   Make target: librelane-asap7-hazard-hls.
# Contents: set_units in picoseconds; clock clk on port clk; clock uncertainty and transition; zero input and output
#   delay on all ports; false path from rst_n.
# Inputs: none. This file sets its own clock period. config.json CLOCK_PERIOD is in ns.
# User rules:
#   All time values in this file are picoseconds. CLOCK_PERIOD in config.json is in ns.
#   A wrong unit silently constrains the design about 1000 times too loose.
#   Input and output delays are 0, so the full period is available to the logic.
#   This keeps the I/O-bounded paths comparable between the hand-RTL arm and the HLS arm.
#   The file is deliberately minimal. Do not copy the CPU-specific AXI, APB, SRAM and ICG
#   constraints of the template SDC here. Their get_ports and get_pins references do not exist in this design.
# Doc: tm:pd:asap7-hazard-hls-sdc

set_units -time 1ps

create_clock -name clk -period 705 [get_ports clk]

set_clock_uncertainty  10 [get_clocks clk]
set_clock_transition    5 [get_clocks clk]

# NOTE: [all_inputs] deliberately includes the clock port. OpenSTA has no
# remove_from_collection (that is a Synopsys command), and an input delay on a
# port that drives only the clock network is inert.
set_input_delay  0 -clock clk [all_inputs]
set_output_delay 0 -clock clk [all_outputs]

set_false_path -from [get_ports rst_n]
