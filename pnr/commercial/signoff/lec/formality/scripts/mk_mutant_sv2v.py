#!/usr/bin/env python3
"""mk_mutant_sv2v.py <in sv2v.v> <out.v> <mode> -- negative-control mutants of the sv2v output (hop-1 controls: RTL vs a mutated sv2v file must FAIL).
  fwdb_inv : invert the D input of the forwarding-select flop fwd_b_ex1c_r (the dud4 flop class): `fwd_b_ex1c_r <= fwd_b_ex1c_pre_w;`
  swap     : in rv32i_alu, replace one input of the SLT sign mux (operand_a[31] -> operand_b[31]); function really changes when the signs differ
Anchors are found by pattern and must match exactly once."""
import sys, re
src, dst, mode = sys.argv[1:4]
t = open(src).read()
if mode == "fwdb_inv":
    a, b = r"fwd_b_ex1c_r <= fwd_b_ex1c_pre_w;", "fwd_b_ex1c_r <= !fwd_b_ex1c_pre_w;"
elif mode == "swap":
    a, b = r"(operand_a[31] ^ operand_b[31] ? operand_a[31] : sum[31])", "(operand_a[31] ^ operand_b[31] ? operand_b[31] : sum[31])"
else:
    raise SystemExit("bad mode")
assert t.count(a) == 1, (mode, t.count(a))
open(dst, "w").write(t.replace(a, b))
print("mutant written:", dst, mode)
