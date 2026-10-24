#!/usr/bin/env python3
"""Netlist fix-ups between yosys and Tessent (generated artefact only; RTL is untouched).

1. The RTL drives scan_out_o[5:0] with a placeholder tie (soc_top.sv `assign scan_out_o[..] = '0; // DFT_PLACEHOLDER`,
   DFT_ARCHITECTURE 14.4 contract step (a): "delete that tie").  Remove those six bits from the port assign so that Tessent
   can drive them from the real chain ends.  Bits [7:6] (CPU macro chain ends) are kept.
2. yosys names the parametrised CPU macro `$paramod\\rv32i_cpu_top\\RESET_PC=...`; rename it to the plain macro name so the
   black-box handling and the reports are readable.
Usage: fixup_gate.py in.v out.v
"""
import re
import sys

src = open(sys.argv[1]).read()

pat = re.compile(r"  assign \{ \\scan_out_o\[7\] , \\scan_out_o\[6\] , \\scan_out_o\[5\] , \\scan_out_o\[4\] , "
                 r"\\scan_out_o\[3\] , \\scan_out_o\[2\] , \\scan_out_o\[1\] , \\scan_out_o\[0\]  \} = "
                 r"\{ \\cpu_scan_out_w\[1\] , \\cpu_scan_out_w\[0\] , (?:gpu_irq_o(?:, )?){6} \};")
new, n = pat.subn(r"  assign { \\scan_out_o[7] , \\scan_out_o[6]  } = { \\cpu_scan_out_w[1] , \\cpu_scan_out_w[0]  };", src)
if n != 1:
    sys.exit("fixup_gate: scan_out_o placeholder assign not found exactly once (%d)" % n)

new, m = re.subn(r"\\\$paramod\\rv32i_cpu_top\\RESET_PC=32'[01]+ ", "rv32i_cpu_top ", new)
if m < 1:
    sys.exit("fixup_gate: CPU macro instance rename did not match")
open(sys.argv[2], "w").write(new)
print("fixup_gate: removed scan_out_o[5:0] placeholder tie, renamed %d CPU macro reference(s)" % m)
