#!/usr/bin/env python3
"""mk_ref_fsm_onehot.py <in sv2v.v> <out.v>
Re-encode, in a COPY of the sv2v file, the three 2-bit state registers that the Yosys FSM_RECODE pass of the B2 run re-encoded to one-hot
(pnr/sky130/cpu/runs/b2_openroad/06-yosys-synthesis/yosys-synthesis.log, section 48.6, lines 7626-7644): u_core.fwd_a_sel_r, u_core.fwd_b_sel_r, u_core.u_cache_arb.grant_q.
Encoding stated in the log (old code -> new one-hot code): 00 -> 0001, 10 -> 0010, 01 -> 0100, 11 -> 1000.  The one-hot register keeps the ORIGINAL name (fwd_a_sel_r, ...)
so the flops match the Yosys netlist's Q nets fwd_a_sel_r[1..3] by name; the 2-bit value is a decoded wire.  Every edit is an exact-string replacement that must match
the expected number of times (the script fails otherwise).  The result is NOT trusted: it is proven equivalent to the input file by scripts/yosys_fsm_equiv.sh (Yosys equiv_make/equiv_induct)."""
import sys, re
src, dst = sys.argv[1:3]
t = open(src).read()
def sub(s, a, b, n=1):
    assert s.count(a) == n, (a, s.count(a))
    return s.replace(a, b)
ENC = "{%s == 2'b11, %s == 2'b01, %s == 2'b10, %s == 2'b00}"
for r, pre in (("fwd_a_sel_r", "fwd_a_sel_pre_w"), ("fwd_b_sel_r", "fwd_b_sel_pre_w")):
    dec = r.replace("_r", "_dec")
    t = sub(t, "\treg [1:0] %s;\n" % r, "\treg [3:0] %s;\n\twire [1:0] %s = {%s[1] | %s[3], %s[2] | %s[3]};\n" % (r, dec, r, r, r, r))
    t = sub(t, "\t\t\t%s <= 2'b00;\n" % r, "\t\t\t%s <= 4'b0001;\n" % r)
    t = sub(t, "\t\t\t%s <= %s;\n" % (r, pre), "\t\t\t%s <= %s;\n" % (r, ENC % ((pre,) * 4)))
    t = sub(t, "\t\t.%s(%s)," % (r.replace("_r", ""), r), "\t\t.%s(%s)," % (r.replace("_r", ""), dec))
# arbiter
a = t.index("module rv32i_cache_arbiter")
b = t.index("endmodule", a)
m = t[a:b]
m = sub(m, "\treg [1:0] grant_q;\n", "\treg [3:0] grant_q;\n\twire [1:0] grant_dec = {grant_q[1] | grant_q[3], grant_q[2] | grant_q[3]};\n\treg [1:0] grant_nxt;\n")
i0 = m.index("\talways @(posedge clk)\n\t\tif (!rst_n)\n\t\t\tgrant_q <= 2'b00;")
i1 = m.index("\t\t\tendcase\n", i0) + len("\t\t\tendcase\n")
blk = m[i0:i1]
body = blk.split("\t\telse\n", 1)[1]            # the case statement
body = body.replace("case (grant_q)", "case (grant_dec)").replace("grant_q <=", "grant_nxt =")
new = ("\talways @(*) begin\n\t\tgrant_nxt = grant_dec;\n" + body + "\tend\n"
       "\talways @(posedge clk)\n\t\tif (!rst_n)\n\t\t\tgrant_q <= 4'b0001;\n\t\telse\n\t\t\tgrant_q <= " + (ENC % (("grant_nxt",) * 4)) + ";\n")
m = m.replace(blk, new)
head, tail = m.split(new, 1)
tail = tail.replace("grant_q", "grant_dec")
head = head.replace("(grant_q ==", "(grant_dec ==")
m = head + new + tail
t = t[:a] + m + t[b:]
open(dst, "w").write(t)
print("written", dst)
