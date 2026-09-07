# Minimal leaf-block SDC — GH #119 Stage 2 (bead r8r).
#
# ALL TIME VALUES ARE PICOSECONDS. ASAP7 Liberty declares time_unit : "1ps",
# while config.json's CLOCK_PERIOD is in ns (0.705 ns = 705 ps). Getting this
# wrong silently constrains the design ~1000x loose (bead: ASAP7 SDC units).
#
# Deliberately minimal: the template SDC is 300 lines of CPU-specific AXI/APB/
# SRAM/ICG constraints whose get_ports/get_pins references do not exist here.
#
# set_input_delay/set_output_delay are 0 so the FULL period is available to the
# logic. That makes the I/O-bounded paths directly comparable between the
# hand-RTL and HLS arms, which is the whole point of this comparison.

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
