#!/usr/bin/env python3
"""stage0_report.py -- resource table + logic-depth proxy from a yosys write_json netlist (bead hlrm, FPGA Stage 0).

usage: stage0_report.py <netlist.json> <xc7|ecp5>

Counts primitives from the top module and computes the longest combinational path in LUT-LEVEL EQUIVALENTS
between sequential endpoints (FF, latch, BRAM, DSP, LUT-RAM write side, ports). It is a DEPTH PROXY, not
timing: no placement, no routing, no delays from a device model. fmax below is a bracketed order-of-magnitude
estimate (depth x assumed ns/level) and must be read as such. Combinational loops (clock-gate latch paths,
dft clock mux) are cut where first detected and counted.
"""
import json
import sys
from collections import Counter

net, fam = sys.argv[1], sys.argv[2]
d = json.load(open(net))
mods = d["modules"]
top = mods["soc_top"]
cells = top["cells"]

LUT_W = {"xc7": {"LUT1": 1, "LUT2": 1, "LUT3": 1, "LUT4": 1, "LUT5": 1, "LUT6": 1, "MUXF7": 0.5, "MUXF8": 0.5,
                 "CARRY4": 0.25, "INV": 0.0, "BUFG": 0.0, "LUT6_2": 1},
         "ecp5": {"LUT4": 1, "L6MUX21": 0.5, "CCU2C": 0.5, "PFUMX": 0.5}}[fam]
SEQ_PREFIX = {"xc7": ("FD", "LD", "RAM", "DSP", "BUFG"), "ecp5": ("TRELLIS_FF", "DP16KD", "MULT18X18D", "ALU54B",
                                                              "TRELLIS_DPR16X4", "LUT4_RAM", "DPR16X4")}[fam]
# xc7: RAM32M etc. are LUT-RAM: read is combinational (treated as 1 level), write is a sequential endpoint.
LUTRAM = ("RAM32M", "RAM64M", "RAM32X1D", "RAM64X1D", "RAM32X1S", "RAM64X1S", "RAM128X1D", "RAM256X1D")

cnt = Counter(c["type"] for c in cells.values())
print("== primitive counts (soc_top, flattened) ==")
for k, v in sorted(cnt.items()):
    print(f"{k:24s}{v:8d}")

# Summary
if fam == "xc7":
    lut = sum(v for k, v in cnt.items() if k.startswith("LUT"))
    ff = sum(v for k, v in cnt.items() if k.startswith("FD"))
    lram = sum(v for k, v in cnt.items() if k in LUTRAM)
    # RAM32M = 4 x (32x2) + ... occupies 4 LUT6 sites (SLICEM); RAM32X1D 2; RAM64M 4; RAM64X1D 2; RAM128X1D 4; RAM256X1D 4
    lutram_sites = (cnt["RAM32M"] * 4 + cnt["RAM64M"] * 4 + cnt["RAM32X1D"] * 2 + cnt["RAM64X1D"] * 2 +
                    cnt["RAM32X1S"] + cnt["RAM64X1S"] + cnt["RAM128X1D"] * 4 + cnt["RAM128X1S"] * 2 + cnt["RAM256X1D"] * 4)
    b18, b36 = cnt["RAMB18E1"], cnt["RAMB36E1"]
    print(f"\nSUMMARY xc7: LUT(logic)={lut} LUTRAM_cells={lram} (~{lutram_sites} LUT sites) FF={ff} "
          f"LATCH={cnt['LDCE']+cnt['LDPE']} BRAM18={b18} BRAM36={b36} (=> {b36 + (b18+1)//2} RAMB36-equivalents) "
          f"DSP48E1={cnt['DSP48E1']} CARRY4={cnt['CARRY4']} MUXF7/8={cnt['MUXF7']}/{cnt['MUXF8']}")
else:
    lut = cnt["LUT4"]
    ff = cnt["TRELLIS_FF"]
    print(f"\nSUMMARY ecp5: LUT4={lut} FF={ff} CCU2C(carry, 2 bits each)={cnt['CCU2C']} "
          f"DP16KD(BRAM 18Kb)={cnt['DP16KD']} MULT18X18D={cnt['MULT18X18D']} ALU54B={cnt['ALU54B']} "
          f"TRELLIS_DPR16X4(LUT-RAM)={cnt['TRELLIS_DPR16X4']} L6MUX21={cnt['L6MUX21']} PFUMX={cnt['PFUMX']}")

# ---- logic depth proxy ----
OUT_DIRS = {"output", "inout"}
drv = {}          # net bit -> cell name (combinational driver)
cell_in = {}
for name, c in cells.items():
    t = c["type"]
    if t not in LUT_W and t not in LUTRAM:
        continue
    pd = c.get("port_directions", {})
    ins, outs = [], []
    for p, bits in c["connections"].items():
        dr = pd.get(p, "input")
        for b in bits:
            if isinstance(b, int):
                (outs if dr in OUT_DIRS else ins).append(b)
    if t in LUTRAM:
        # only the read-address -> read-data arc is combinational; treat the cell as 1 level from all inputs
        pass
    cell_in[name] = ins
    for b in outs:
        drv[b] = name

sys.setrecursionlimit(1000000)
depth = {}
state = {}
loops = 0
def lev(name):
    global loops
    if name in depth:
        return depth[name]
    if state.get(name) == 1:
        loops += 1
        return 0.0
    state[name] = 1
    t = cells[name]["type"]
    w = 1.0 if t in LUTRAM else LUT_W[t]
    m = 0.0
    for b in cell_in[name]:
        dn = drv.get(b)
        if dn is not None:
            v = lev(dn)
            if v > m:
                m = v
    depth[name] = m + w
    state[name] = 2
    return depth[name]

best = 0.0
bestc = None
# endpoints: any cell input that is not a pure combinational primitive's input (i.e. seq/port sinks)
sink_bits = []
for name, c in cells.items():
    if name in cell_in and c["type"] not in LUTRAM:
        continue
    pd = c.get("port_directions", {})
    for p, bits in c["connections"].items():
        if pd.get(p, "input") == "input":
            sink_bits.extend(b for b in bits if isinstance(b, int))
for p in top["ports"].values():
    if p["direction"] in OUT_DIRS:
        sink_bits.extend(b for b in p["bits"] if isinstance(b, int))
for b in sink_bits:
    dn = drv.get(b)
    if dn is not None:
        v = lev(dn)
        if v > best:
            best, bestc = v, dn
print(f"\nDEPTH PROXY: longest combinational path = {best:.2f} LUT-level equivalents (loops cut: {loops}); "
      f"end cell {bestc}")
if fam == "xc7":
    lo, hi, tov = 0.45, 0.80, 0.9     # ns/level (7-series -1, routed incl. LUT), clk->Q + setup + clock skew
else:
    lo, hi, tov = 0.80, 1.30, 1.3     # ECP5 -6/-7 class, LUT4 + routing
tmin = tov + best * lo
tmax = tov + best * hi
print(f"ROUGH fmax bracket (NOT MEASURED; depth x {lo}-{hi} ns/level + {tov} ns overhead): "
      f"{1000.0/tmax:.0f} .. {1000.0/tmin:.0f} MHz")
