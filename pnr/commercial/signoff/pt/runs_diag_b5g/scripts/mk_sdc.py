#!/usr/bin/env python3
"""mk_sdc.py <out.sdc> <rise_ns> <fall_ns|-> -- DIAGNOSTIC SDC variant of the shared SDC (never modifies it).
Re-references every set_input_delay/set_output_delay from clk_i to a virtual IDEAL clock clk_io whose network latency is
<rise_ns> (rise edge) / <fall_ns> (fall edge), source latency 1.0 as clk_i.  This models Innovus's auto 'update I/O latency'
(set_clock_latency -source -1.90877 rise / -1.65153 fall on pin clk_i) in PT's frame where clk_i keeps source latency 1.0:
I/O reference = 1.0 + 2.90877 (rise) / 1.0 + 2.65153 (fall).  Same structure as gen_iolat_sdc.py."""
import re, sys, hashlib
src = "/home/RD/ryan/Desktop/Github/claude_verilog_test/pnr/sky130/cpu/constraints/sky130_cpu.sdc"
raw = open(src, "rb").read()
assert hashlib.md5(raw).hexdigest() == "3c69635042a9d65cb87e71a9db713e4e"
out_path, rise, fall = sys.argv[1], sys.argv[2], sys.argv[3]
out = []
for line in raw.decode().splitlines():
    if re.match(r"^(set_input_delay|set_output_delay)\s+-clock\s+clk_i\b", line):
        line = line.replace("-clock clk_i", "-clock clk_io", 1)
    out.append(line)
    if line.strip() == "set_clock_latency -source 1.0 [get_clocks clk_i]":
        out += ["create_clock -name clk_io -period 13.333",
                "set_clock_latency -source 1.0 [get_clocks clk_io]",
                f"set_clock_latency -rise {rise} [get_clocks clk_io]"]
        if fall != "-":
            out.append(f"set_clock_latency -fall {fall} [get_clocks clk_io]")
        out += ["set_clock_uncertainty        0.5 [get_clocks clk_io]", "set_clock_uncertainty -hold  0.2 [get_clocks clk_io]"]
    if line.strip() == "group_path -name PIPELINE -from [get_clocks clk_i] -to [get_clocks clk_i]":
        out += ["group_path -name IO -from [get_clocks clk_io]", "group_path -name IO -to [get_clocks clk_io]"]
open(out_path, "w").write("\n".join(out) + "\n")
print("wrote", out_path)
