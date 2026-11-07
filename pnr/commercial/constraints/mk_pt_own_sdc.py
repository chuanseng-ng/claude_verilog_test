#!/usr/bin/env python3 -I
"""mk_pt_own_sdc.py <innovus exported out/rv32i_cpu_top.sdc> <out_pt.sdc> <arm label> -- PT-readable copy of an Innovus-exported SDC.  ONLY two syntax edits (PT rejects both and read_sdc then
silently drops the rest): the line `current_design <top>` is removed and `[get_designs {<top>}]` becomes `[current_design]`.  A one-line header records the source md5."""
import hashlib, re, sys
src, out, lab = sys.argv[1:4]
raw = open(src).read(); md5 = hashlib.md5(raw.encode()).hexdigest()
lines = [l for l in raw.splitlines() if not re.match(r"current_design\s+\S+\s*$", l)]
txt = "\n".join(lines) + "\n"
txt = re.sub(r"\[get_designs \{[^}]*\}\]", "[current_design]", txt)
hdr = f"# PT-readable copy of the Innovus {lab} exported SDC ({src}, md5 {md5}). ONLY two syntax edits: line \"current_design <top>\" removed and \"[get_designs {{<top>}}]\" -> \"[current_design]\" (PT rejects both; read_sdc stops at the first error and silently drops the rest).\n"
open(out, "w").write(hdr + txt)
print(out, hashlib.md5(open(out, "rb").read()).hexdigest())
