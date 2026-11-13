# asap7.sdc - Timing constraints for rv32i_hazard_unit (ASAP7, purely combinational block)
#
# Scope: the config.json of this directory sets PNR_SDC_FILE, SIGNOFF_SDC_FILE and FALLBACK_SDC_FILE to this file.
#   Make target: librelane-asap7-hazard-rtl.
# Contents: set_units in picoseconds; virtual clock vclk (no port); zero input and output delay on all ports.
# Inputs: none. This file sets its own period. config.json CLOCK_PERIOD is in ns and CLOCK_PORT is empty.
# User rules:
#   All time values in this file are picoseconds. CLOCK_PERIOD in config.json is in ns.
#   The block has no clock port, no reset and no register, so it has no register-to-register path.
#   Do not use report_clock_min_period or fmax for it. Both are meaningless here.
#   The whole period is available to the combinational cone. The setup slack gives the input-to-output delay:
#   the period minus the slack. That delay is the primary number of this block.
#   Compare it with the HLS arm on throughput (HLS period times cycle count).
#   The zero I/O budget is the same as in the clocked arms, so both are measured on the same basis.
# Doc: tm:pd:asap7-hazard-rtl-sdc

set_units -time 1ps

create_clock -name vclk -period 705

set_input_delay  0 -clock vclk [all_inputs]
set_output_delay 0 -clock vclk [all_outputs]
