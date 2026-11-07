#!/usr/bin/env python3
"""mk_sdc_exact.py <out.sdc> -- DIAGNOSTIC SDC that reproduces what Innovus b5g actually timed with (views/av_tt/latency.sdc):
   clk_i register clock: early (min-arrival) source latency 1.0, LATE (max-arrival) source latency -1.90877 rise / -1.65153 fall;
   I/O delays referenced to a virtual ideal clock clk_io with source latency 1.0 and NO network latency (Innovus 'Source Insertion Delay 1.000').
   Shared SDC is not modified."""
import re, sys, hashlib
src = "/home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc"
raw = open(src, "rb").read()
assert hashlib.md5(raw).hexdigest() == "3c69635042a9d65cb87e71a9db713e4e"
out = []
for line in raw.decode().splitlines():
    if re.match(r"^(set_input_delay|set_output_delay)\s+-clock\s+clk_i\b", line):
        line = line.replace("-clock clk_i", "-clock clk_io", 1)
    if line.strip() == "set_clock_latency -source 1.0 [get_clocks clk_i]":
        out += ["set_clock_latency -source -early 1.0 [get_clocks clk_i]",
                "set_clock_latency -source -late -rise -1.90877 [get_clocks clk_i]",
                "set_clock_latency -source -late -fall -1.65153 [get_clocks clk_i]",
                "create_clock -name clk_io -period 13.333",
                "set_clock_latency -source 1.0 [get_clocks clk_io]",
                "set_clock_uncertainty        0.5 [get_clocks clk_io]", "set_clock_uncertainty -hold  0.2 [get_clocks clk_io]"]
        continue
    out.append(line)
    if line.strip() == "group_path -name PIPELINE -from [get_clocks clk_i] -to [get_clocks clk_i]":
        out += ["group_path -name IO -from [get_clocks clk_io]", "group_path -name IO -to [get_clocks clk_io]"]
open(sys.argv[1], "w").write("\n".join(out) + "\n")
print("wrote", sys.argv[1])
