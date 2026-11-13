#!/usr/bin/env python3 -I
"""update_doc_tables.py -- refresh the generated b6 / b7 / b8 tables of docs/COMMERCIAL_FLOW_COMPARISON.md section 4.9 from comparison.json.
The doc holds `<!-- GEN-TABLE icc2 -->` ... `<!-- /GEN-TABLE -->` blocks; the text between a pair is replaced by make_gen_table.py output."""
import re, subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__)); DOC = os.path.join(HERE, "../../../docs/COMMERCIAL_FLOW_COMPARISON.md")
s = open(DOC).read()
def sub(m):
    out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "make_gen_table.py"), m.group(1)], capture_output=True, text=True, check=True).stdout
    return f"<!-- GEN-TABLE {m.group(1)} -->\n{out}<!-- /GEN-TABLE -->"
def subr(m):
    out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "regress_check.py"), m.group(1), m.group(2)] + ([m.group(3)] if m.group(3) else []), capture_output=True, text=True, check=True).stdout
    return f"<!-- GEN-REGRESS {m.group(1)} {m.group(2)}{' ' + m.group(3) if m.group(3) else ''} -->\n{out}<!-- /GEN-REGRESS -->"
def subf(m):
    out = subprocess.run([sys.executable, "-I", os.path.join(HERE, "make_final_tables.py"), m.group(1)], capture_output=True, text=True, check=True).stdout
    return out.rstrip("\n")
s2 = re.sub(r"<!-- FINAL-TABLE (\w+) -->.*?<!-- /FINAL-TABLE -->", subf, s, flags=re.S)
s2 = re.sub(r"<!-- GEN-TABLE (\w+) -->.*?<!-- /GEN-TABLE -->", sub, s2, flags=re.S)
s2 = re.sub(r"<!-- GEN-REGRESS (\w+) (\w+)(?: (\w+))? -->.*?<!-- /GEN-REGRESS -->", subr, s2, flags=re.S)
open(DOC, "w").write(s2)
print("updated" if s2 != s else "unchanged")
