# Minimal leaf-block SDC — GH #119 Stage 2 (bead r8r).
#
# ALL TIME VALUES ARE PICOSECONDS (ASAP7 Liberty time_unit : "1ps").
#
# vector_alu is PURELY COMBINATIONAL: no clock port, no reset, no
# registers, therefore ZERO register-to-register paths. report_clock_min_period
# is meaningless for it and "fmax" is undefined.
#
# So it is timed against a VIRTUAL clock with a zero I/O budget: the entire 705 ps
# is available to the combinational cone, and the reported setup slack gives the
# input-to-output path delay directly as (705 - slack) ps. That delay -- not an
# fmax -- is this block's primary number, and it is compared against the HLS arm
# on throughput (its period x cycle count). Same zero I/O budget as the clocked
# arms so the two are measured on the same basis.

set_units -time 1ps

create_clock -name vclk -period 705

set_input_delay  0 -clock vclk [all_inputs]
set_output_delay 0 -clock vclk [all_outputs]
