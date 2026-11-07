# Minimal SDC for the link/load tests of tests/link_trivial.v
create_clock -name clk -period 25.0 [get_ports clk]
set_input_delay  2.0 -clock clk [remove_from_collection [all_inputs] [get_ports clk]]
set_output_delay 2.0 -clock clk [all_outputs]
