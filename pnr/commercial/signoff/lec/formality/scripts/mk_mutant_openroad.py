#!/usr/bin/env python3
"""mk_mutant_openroad.py <in.nl.v> <out.nl.v> <mode> -- negative-control mutants of the OpenROAD/LibreLane B2 netlist (flat; OpenROAD write_verilog style:
anonymous cells `_54171_`, named nets, `.PIN(net)` with no spaces).  Anchors are found by STRUCTURE and edited exactly once; the script fails if none exists.
  fwdb_inv : inverter on the D pin of the forwarding-select flop whose Q net is \\u_core.fwd_b_ex1c_r (the dud4 flop class, same flop as the b6 controls)
  swap     : swap A2<->B2 of an a22oi_1 (four distinct nets) with a pin on an ex1a_ex1b / ex1b_ex2 / ex1c operand bus (operand mux cone): function really changes
  bufinv   : (OpenROAD-specific) turn one resizer/hold buffer (dlygate4sd3_1 sitting on a flop D-input path) into an inverter, i.e. 'a buffer the optimiser inserted is mis-typed'
  tiehi    : (OpenROAD-specific) swap the output of one conb_1 tie cell HI<->LO (tie-cell polarity)"""
import sys, re
src, dst, mode = sys.argv[1:4]
t = open(src).read()
inst = re.compile(r"^ (sky130_fd_sc_hd__\w+) (\S+) \((.*?)\);\n", re.S | re.M)
pin = lambda body: {k: v for k, v in re.findall(r"\.(\w+)\(([^()]*?)\)", body)}
if mode == "fwdb_inv":
    m = [x for x in inst.finditer(t) if x.group(1).startswith("sky130_fd_sc_hd__dfxtp") and pin(x.group(3)).get("Q", "").strip() == "\\u_core.fwd_b_ex1c_r"]
    assert len(m) == 1, len(m)
    x = m[0]; d = pin(x.group(3))["D"]
    new = x.group(0).replace(".D(%s)" % d, ".D(mut_n)", 1)
    assert new != x.group(0)
    new = " wire mut_n;\n sky130_fd_sc_hd__inv_1 mut_inv (.A(%s), .Y(mut_n));\n" % d + new
    t = t[:x.start()] + new + t[x.end():]
    print("fwdb_inv: flop", x.group(2), "D net", d)
elif mode == "swap":
    c = []
    for x in inst.finditer(t):
        if x.group(1) != "sky130_fd_sc_hd__a22oi_1": continue
        p = pin(x.group(3))
        if len({p.get("A1"), p.get("A2"), p.get("B1"), p.get("B2")}) == 4 and any(("ex1a_ex1b" in v or "ex1b_ex2" in v or "ex1c" in v) for v in p.values()):
            c.append((x, p))
    assert c, "no suitable a22oi_1"
    x, p = c[0]
    new = x.group(0).replace(".A2(%s)" % p["A2"], ".A2(@@)", 1).replace(".B2(%s)" % p["B2"], ".B2(%s)" % p["A2"], 1).replace(".A2(@@)", ".A2(%s)" % p["B2"], 1)
    assert new != x.group(0)
    t = t[:x.start()] + new + t[x.end():]
    print("swap: inst", x.group(2), "pins", p, "candidates", len(c))
elif mode == "bufinv":
    dnets = set()
    for x in inst.finditer(t):
        if x.group(1).startswith("sky130_fd_sc_hd__dfxtp"):
            dnets.add(pin(x.group(3)).get("D", "").strip())
    c = [x for x in inst.finditer(t) if x.group(1).startswith("sky130_fd_sc_hd__dlygate4sd3") and pin(x.group(3)).get("X", "").strip() in dnets]
    assert c, "no dlygate on a flop D"
    x = c[0]; p = pin(x.group(3))
    new = " sky130_fd_sc_hd__inv_1 %s (.A(%s), .Y(%s));\n" % (x.group(2), p["A"], p["X"])
    t = t[:x.start()] + new + t[x.end():]
    print("bufinv: inst", x.group(2), "A", p["A"], "X", p["X"], "candidates", len(c))
elif mode == "tiehi":
    c = [x for x in inst.finditer(t) if x.group(1).startswith("sky130_fd_sc_hd__conb") and pin(x.group(3)).get("LO", "").strip() and pin(x.group(3)).get("HI", "").strip() == "" ]
    c2 = [x for x in inst.finditer(t) if x.group(1).startswith("sky130_fd_sc_hd__conb")]
    assert c2, "no conb"
    # use a LO-only tie that feeds a non-port, non-physical sink
    for x in c2:
        p = pin(x.group(3))
        if "LO" in p and "HI" not in p:
            n = p["LO"].strip()
            if t.count(n) > 2 and n not in re.findall(r"^ output\s+(?:\[[^\]]*\]\s+)?(\S+);", t, re.M):
                new = x.group(0).replace(".LO(", ".HI(", 1)
                t = t[:x.start()] + new + t[x.end():]
                print("tiehi: inst", x.group(2), "net", n); break
    else:
        raise SystemExit("no LO tie with an internal sink")
else:
    raise SystemExit("bad mode")
open(dst, "w").write(t)
print("mutant written:", dst, mode)
