#!/usr/bin/env python3
"""Generate behavioural Verilog cell models from a Liberty file (sky130_fd_sc_hd).

Why: Tessent's read_liberty only attaches *attributes* (scan pins, test_cell, clock gating) to cell models; the
behaviour must still come from Verilog (read_verilog / read_cell_library).  This host has no PDK install, so the vendor
Verilog models are not available either.  The models here are derived from the Liberty `function`, `ff`, `latch` and
`statetable` groups, are plain Verilog-2001 (no UDPs, no specify blocks, no delays), and double as the zero-delay gate
simulation models for the VCS pattern check.  Cells that cannot be modelled (three-state, unparsed constructs) are
listed in the report, never silently dropped.

Usage: lib2v.py <liberty> <out.v> <report.txt> [--cells regex]
"""
import re
import sys


def tokenize(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    text = text.replace("\\\n", " ")
    return re.findall(r'"(?:[^"\\]|\\.)*"|[{}();:,]|[^\s{}();:,"]+', text)


def parse(tokens):
    """Return a tree of (kind, args, attrs, children)."""
    pos = 0
    n = len(tokens)

    def group():
        nonlocal pos
        name = tokens[pos]
        pos += 1
        assert tokens[pos] == "("
        pos += 1
        args = []
        while tokens[pos] != ")":
            if tokens[pos] != ",":
                args.append(tokens[pos].strip('"'))
            pos += 1
        pos += 1
        node = {"kind": name, "args": args, "attrs": {}, "kids": []}
        if pos < n and tokens[pos] == "{":
            pos += 1
            body(node)
        elif pos < n and tokens[pos] == ";":
            pos += 1
        return node

    def body(node):
        nonlocal pos
        while tokens[pos] != "}":
            if tokens[pos + 1] == ":":
                key = tokens[pos]
                pos += 2
                val = tokens[pos].strip('"')
                pos += 1
                if tokens[pos] == ";":
                    pos += 1
                node["attrs"][key] = val
            elif tokens[pos + 1] == "(":
                node["kids"].append(group())
            else:
                pos += 1
        pos += 1

    root = group()
    return root


def fn(expr):
    """Liberty boolean function -> Verilog expression."""
    e = expr.strip()
    e = e.replace("*", "&").replace("+", "|").replace("!", "~")
    # postfix ' complement is not used in sky130; fail loudly if present
    if "'" in e:
        raise ValueError("postfix complement in " + expr)
    # implicit AND by juxtaposition (e.g. "A B") -> '&'
    e = re.sub(r"([A-Za-z0-9_\)])\s+(?=[A-Za-z0-9_\(~])", r"\1 & ", e)
    return e


def model(cell):
    name = cell["args"][0]
    pins = [k for k in cell["kids"] if k["kind"] == "pin"]
    ins, outs = [], []
    for p in pins:
        d = p["attrs"].get("direction", "")
        for pn in p["args"]:
            (ins if d == "input" else outs if d in ("output", "inout") else []).append(pn)
        if p["attrs"].get("three_state"):
            raise ValueError("three_state")
        if d == "inout":
            raise ValueError("inout")
    lines = []
    ports = ins + outs
    lines.append("module %s (%s);" % (name, ", ".join(ports)))
    for i in ins:
        lines.append("  input %s;" % i)
    for o in outs:
        lines.append("  output %s;" % o)
    ffs = [k for k in cell["kids"] if k["kind"] == "ff"]
    lats = [k for k in cell["kids"] if k["kind"] == "latch"]
    sts = [k for k in cell["kids"] if k["kind"] == "statetable"]
    if len(ffs) > 1 or len(lats) > 1 or len(sts) > 1:
        raise ValueError("multiple state groups")
    states = set()
    for ff in ffs:
        q, qn = ff["args"][0], (ff["args"][1] if len(ff["args"]) > 1 else None)
        states.add(q)
        a = ff["attrs"]
        lines.append("  reg %s;" % q)
        if qn:
            lines.append("  wire %s = ~%s;" % (qn, q))
        clk = fn(a["clocked_on"])
        lines.append("  wire %s_clk = %s;" % (q, clk))
        clr = fn(a["clear"]) if "clear" in a else "1'b0"
        pre = fn(a["preset"]) if "preset" in a else "1'b0"
        lines.append("  wire %s_clr = %s;" % (q, clr))
        lines.append("  wire %s_pre = %s;" % (q, pre))
        lines.append("  wire %s_nxt = %s;" % (q, fn(a["next_state"])))
        lines.append("  always @(posedge %s_clk or posedge %s_clr or posedge %s_pre)" % (q, q, q))
        lines.append("    if (%s_clr) %s <= 1'b0; else if (%s_pre) %s <= 1'b1; else %s <= %s_nxt;" % (q, q, q, q, q, q))
    for lt in lats:
        q, qn = lt["args"][0], (lt["args"][1] if len(lt["args"]) > 1 else None)
        states.add(q)
        a = lt["attrs"]
        lines.append("  reg %s;" % q)
        if qn:
            lines.append("  wire %s = ~%s;" % (qn, q))
        clr = fn(a["clear"]) if "clear" in a else "1'b0"
        pre = fn(a["preset"]) if "preset" in a else "1'b0"
        lines.append("  always @* if (%s) %s = 1'b0; else if (%s) %s = 1'b1; else if (%s) %s = %s;" %
                     (clr, q, pre, q, fn(a["enable"]), q, fn(a["data_in"])))
    for st in sts:
        stin = st["args"][0].split()
        stout = st["args"][1].split()
        rows = st["attrs"]["table"].split(",")
        for s in stout:
            states.add(s)
            lines.append("  reg %s;" % s)
        lines.append("  always @* begin")
        for r in rows:
            parts = [x.strip() for x in r.split(":")]
            pat = parts[0].split()
            nxt = parts[2].split()
            conds = []
            for sig, v in zip(stin, pat):
                if v == "L":
                    conds.append("%s == 1'b0" % sig)
                elif v == "H":
                    conds.append("%s == 1'b1" % sig)
            assigns = []
            for s, v in zip(stout, nxt):
                if v == "L":
                    assigns.append("%s = 1'b0;" % s)
                elif v == "H":
                    assigns.append("%s = 1'b1;" % s)
            if assigns:
                lines.append("    if (%s) begin %s end" % (" && ".join(conds) or "1'b1", " ".join(assigns)))
        lines.append("  end")
    for p in pins:
        func = p["attrs"].get("function") or p["attrs"].get("state_function")
        if p["attrs"].get("direction") == "output" and func:
            for pn in p["args"]:
                lines.append("  assign %s = %s;" % (pn, fn(func)))
        elif p["attrs"].get("direction") == "output":
            raise ValueError("output %s has no function" % p["args"][0])
    lines.append("endmodule")
    return "\n".join(lines)


def main():
    lib, out, rep = sys.argv[1:4]
    pat = None
    if "--cells" in sys.argv:
        pat = re.compile(sys.argv[sys.argv.index("--cells") + 1])
    root = parse(tokenize(open(lib).read()))
    ok, bad = [], []
    chunks = []
    for c in root["kids"]:
        if c["kind"] != "cell":
            continue
        name = c["args"][0]
        if pat and not pat.search(name):
            continue
        try:
            chunks.append(model(c))
            ok.append(name)
        except (ValueError, KeyError, AssertionError) as e:
            bad.append((name, str(e)))
    open(out, "w").write("// Generated from %s by lib2v.py: zero-delay behavioural models, no power pins.\n" % lib
                         + "\n\n".join(chunks) + "\n")
    with open(rep, "w") as f:
        f.write("modelled %d cells, could not model %d\n" % (len(ok), len(bad)))
        for n, why in bad:
            f.write("UNMODELLED %s: %s\n" % (n, why))
    print("modelled %d cells, could not model %d (see %s)" % (len(ok), len(bad), rep))


if __name__ == "__main__":
    main()
