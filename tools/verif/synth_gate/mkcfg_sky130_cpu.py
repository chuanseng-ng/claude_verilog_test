#!/usr/bin/env python3
"""Generate scratch LibreLane configs for the dud4 synthesis-only experiment.
usage: mkcfg.py <src_root> <arm: synlig|sv2v> <outdir>
Only USE_SYNLIG / VERILOG_FILES differ between arms."""
import json, sys, os, re
src, arm, out = sys.argv[1:4]
cfgp = f"{src}/pnr/sky130/cpu/config.json"
c = json.load(open(cfgp))
def absd(p):
    return os.path.normpath(f"{src}/pnr/sky130/cpu/{p[5:]}") if p.startswith("dir::") else p
def conv(v):
    if isinstance(v, str): return absd(v)
    if isinstance(v, list): return [conv(x) for x in v]
    return v
orig_files = [absd(f) for f in c["VERILOG_FILES"]]
for k in list(c):
    c[k] = conv(c[k])
stub = orig_files[0]
sv = orig_files[1:]
if arm == "synlig":
    c["VERILOG_FILES"] = orig_files
    assert c["USE_SYNLIG"] is True
else:
    c["VERILOG_FILES"] = [stub, f"{out}/rv32i_cpu_top_sv2v.v"]
    c["USE_SYNLIG"] = False
    open(f"{out}/sv_files.txt","w").write("\n".join(sv)+"\n")
json.dump(c, open(f"{out}/config.json","w"), indent=2)
