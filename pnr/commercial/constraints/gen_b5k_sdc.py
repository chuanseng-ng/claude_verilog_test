#!/usr/bin/env python3 -I
"""gen_b5k_sdc.py <in_post.sdc> <out.sdc> -- Innovus b5k constraint file = b5h/b5j post-CTS SDC (clk_io model, latency 3.295 ns, propagated clk_i) + input delays for the
26 previously unconstrained mbist inputs (mbist_run_i, mbist_cfg_i[25:0]).  Values = the synchronous 'ready' class of the shared SDC (-max 2.0 / -min 0.5, referenced to clk_io
like every other input): rv32i_cpu_top.sv:113-120 says these pins come from the CPU-domain holding register of soc_top's soc_mbist (same frequency and source as clk_i),
'quasi-static, no timing path other than the ordinary sync-to-clk_i'; so they are TIMED as ordinary synchronous inputs (not false-pathed).  The shared SDC itself is never modified."""
import sys
src, out = sys.argv[1], sys.argv[2]
t = open(src).read()
assert "mbist" not in t, "source SDC already mentions mbist"
add = """
# --- b5k: the 26 mbist inputs (mbist_run_i, mbist_cfg_i[25:0]) were unconstrained.  Synchronous holding-register outputs of the CPU domain -> ordinary sync input class.
set_input_delay -clock clk_io -max 2.0 [get_ports {mbist_run_i mbist_cfg_i[*]}]
set_input_delay -clock clk_io -min 0.5 [get_ports {mbist_run_i mbist_cfg_i[*]}]
"""
open(out, "w").write(t.rstrip("\n") + "\n" + add)
print(out)
