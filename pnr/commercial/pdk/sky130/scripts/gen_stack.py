#!/usr/bin/env python3 -I
"""gen_stack.py -- author the Sky130 interconnect stack for commercial extraction tools.

Single source of truth for the stack numbers.  Emits, for corners nom / min / max:
    <out>/itf/sky130A_<corner>.itf     Synopsys ITF   (StarRC grdgenxo -> nxtgrd, TLU+)
    <out>/ict/sky130A_<corner>.ict     Cadence ICT    (Quantus Techgen -> qrcTechFile)
    <out>/map/starrc_layer.map         tech-LEF layer name -> ITF layer name (StarRC / ICC2 tech2itf)
    <out>/map/quantus_lef2ict.map      tech-LEF layer name -> ICT layer name (Innovus lefTechFileMap)
    <out>/stack_summary.txt            human-readable parameter table with sources

NO foundry ITF/ICT/nxtgrd ships with Sky130.  Everything below is INDICATIVE until the extraction
correlation (part 2) passes.  Source tags used in the comments of the generated files:

  [FIG]  SkyWater PDK metal-stack figure, https://skywater-pdk.readthedocs.io/en/main/_images/metal_stack.svg
         (raw SVG parsed, not summarised): layer bottoms 0.3262 poly / 0.9361 li / 1.3761 m1 / 2.0061 m2 /
         2.7861 m3 / 4.0211 m4 / 5.3711 m5; thicknesses 0.18 poly, 0.1 li, 0.36 m1, 0.36 m2, 0.845 m3,
         0.845 m4, 1.26 m5; cuts 0.265+0.075(LINT) mcon, 0.27 via1, 0.42 via2, 0.39 via3, 0.505 via4;
         dielectric names/K: FOX 3.9, PSG 3.9, LINT 7.3, NILD2 4.05, NILD3 4.5, NILD3_C 3.5, NILD4 4.2,
         NILD4_C 3.5, NILD5 4.1, NILD6 4.0, TOPOX 3.9, PI1 2.94, TOPNIT 7.5.
         The same z-heights appear as `height` lines in Magic's sky130A.tech ([MAGIC]).
  [TLEF] sky130_fd_sc_hd__{nom,min,max}.tlef: WIDTH/SPACING(min), RESISTANCE RPERSQ (per corner),
         via RESISTANCE (per corner), cut WIDTH, DC/AC current-density limits (EM).
  [MAGIC] libs.tech/magic/sky130A.tech extract section: heights, poly/diff/contact resistances.
  [FIT]  Dielectric K per slab: chosen from the K values printed in the figure by coordinate descent so
         that a 1-D plate-capacitance model reproduces Magic's PEX-cap-model area caps (scripts/
         stack_calibrate.py, RMS error printed there).  Not a field solve; indicative.
  [ORCX] OpenRCX rule decks (libs.tech/openlane/rules.openrcx.sky130A.*) -> min/max capacitance corner
         multiplier on every ER (scripts/corner_scale.py).
  [DRM]  SkyWater SKY130 design rules (poly/diff min width/space).
  [ABSENT] Not published for Sky130 -> left at 0 / omitted (temperature coefficients, etch/width bias,
         density-dependent thickness (erosion), per-layer CMP variation).
"""
import argparse, math, os, re, sys

# --------------------------------------------------------------------------------------------------
# geometry [FIG]/[MAGIC]  (um, z measured from substrate/ground reference)
Z = {  # name: (bottom, thickness)
    "poly": (0.3262, 0.18), "li1": (0.9361, 0.10), "met1": (1.3761, 0.36), "met2": (2.0061, 0.36),
    "met3": (2.7861, 0.845), "met4": (4.0211, 0.845), "met5": (5.3711, 1.26)}
GOX = 0.0041               # gate-oxide gap between diffusion top and poly bottom [ASSUMED: sky130 nfet_01v8 toxe ~4.1 nm]
DIFF_TOP = 0.3262 - GOX    # diffusion top = poly bottom - GOX.  Techgen REJECTS DIFF_TOP == poly height (error
                           # LBMISC-215479 "metal layer poly thickness -0.43 must be >= 0.0001"); any GOX > 0 passes parse [MAGIC alldiff 0.2062+0.12 -> 0.3262]
# planar dielectric slabs bottom-up (name, z0, z1, K_nom, source) -- [FIG] names, [FIT] K
LI_TOP = 0.9361 + 0.10
SLABS = [
    ("FOX",        0.0,           0.3262,        3.9, "FIG FOX K=3.9"),
    ("PSG_poly",   0.3262,        0.9361,        3.9, "FIG PSG K=3.9 (poly + licon level)"),
    ("PSG_li",     0.9361,        LI_TOP,        3.9, "FIG PSG K=3.9 (li1 level)"),
    ("LINT",       LI_TOP,        LI_TOP + 0.075, 7.3, "FIG LINT K=7.3, 0.075 um nitride on li1"),
    ("NILD2_mcon", LI_TOP + 0.075, 1.3761,       3.9, "FIT (fig NILD2 K=4.05 nearest published 3.9..4.05)"),
    ("IMD1",       1.3761,        1.7361,        3.9, "FIT met1 level"),
    ("NILD_v1",    1.7361,        2.0061,        4.1, "FIT via1 gap (fig NILD5 K=4.1 value)"),
    ("IMD2",       2.0061,        2.3661,        3.9, "FIT met2 level"),
    ("NILD_v2",    2.3661,        2.7861,        4.1, "FIT via2 gap (fig NILD5 K=4.1 value)"),
    ("IMD3",       2.7861,        3.6311,        3.9, "FIT met3 level"),
    ("NILD_v3",    3.6311,        4.0211,        3.5, "FIT via3 gap (fig NILD4_C/NILD3_C K=3.5 value)"),
    ("IMD4",       4.0211,        4.8661,        4.0, "FIT met4 level (fig NILD6 K=4.0)"),
    ("NILD_v4",    4.8661,        5.3711,        3.9, "FIT via4 gap (fig TOPOX K=3.9)"),
    ("IMD5",       5.3711,        6.6311,        3.9, "FIT met5 level"),
]
PI1 = ("PI1", 6.6311, 6.6311 + 5.2523, 2.94, "FIG PI1 K=2.94, 5.2523 um (6.6311 -> 11.8834)")
# conductors: name -> (tlef WMIN, SMIN, RPSQ nom, min, max, source)   RPSQ from [TLEF] per-corner decks
COND = {
    "li1":  (0.17, 0.17, 12.8,   9.2,   17.0),
    "met1": (0.14, 0.14, 0.125,  0.105, 0.145),
    "met2": (0.14, 0.14, 0.125,  0.105, 0.145),
    "met3": (0.30, 0.30, 0.047,  0.038, 0.056),
    "met4": (0.30, 0.30, 0.047,  0.038, 0.056),
    "met5": (1.60, 1.60, 0.0285, 0.0212, 0.0358),
}
POLY = dict(wmin=0.15, smin=0.21, rpsq=(48.2, 42.2, 55.8))          # [DRM] poly.1a/.2 ; [MAGIC] resist allpolynonres nom/lrlc/hrhc
DIFF = {"ndiff": (120.0, 108.0, 132.0), "pdiff": (197.0, 166.0, 228.0)}  # ohm/sq [MAGIC] nom/lr/hr
# cuts: name -> (from(lower), to(upper), cut width um [TLEF], RPV nom, min, max [TLEF])
VIAS = [
    ("mcon", "li1",  "met1", 0.17, (9.30, 1.6, 23.0)),
    ("via1", "met1", "met2", 0.15, (4.50, 2.0, 15.0)),
    ("via2", "met2", "met3", 0.20, (3.41, 0.5, 8.0)),
    ("via3", "met3", "met4", 0.20, (3.41, 0.5, 8.0)),
    ("via4", "met4", "met5", 0.80, (0.38, 0.012, 0.891)),
]
LICON_W = 0.17
LICON_RPV = {"poly": (152.0, 52.0, 252.0), "ndiff": (185.0, 95.0, 280.0), "pdiff": (585.0, 345.0, 840.0)}  # [MAGIC] contact pc/ndc/pdc nom/lr/hr
TLEF_NAME = {"mcon": "mcon", "via1": "via", "via2": "via2", "via3": "via3", "via4": "via4"}
CORNERS = ("nom", "min", "max")
ER_SCALE = {"nom": 1.0, "min": 0.7919, "max": 1.2131}   # [ORCX] scripts/corner_scale.py
ci = {"nom": 0, "min": 1, "max": 2}


def slab_for(zlo, zhi):
    """series-equivalent K of the dielectric stack between zlo and zhi (nom)"""
    acc = 0.0
    for (_, a, b, k, _) in SLABS:
        lo, hi = max(a, zlo), min(b, zhi)
        if hi > lo: acc += (hi - lo) / k
    return (zhi - zlo) / acc


def itf_text(corner):
    """ITF is emitted in the conventional multi-line block style with every comment on its own '$' line
    (StarRC accepts both styles; Ansys' adsTechConverter.pl only parses the multi-line style and
    mis-parses keywords that appear inside comments, so comments avoid the upper-case block keywords)."""
    s = ER_SCALE[corner]; c = ci[corner]
    o = []
    A = o.append
    def blk(kind, name, attrs, note):
        A(f"$ {note}")
        A(f"{kind} {name} {{")
        for k, v in attrs: A(f"   {k}={v}")
        A("}")
    A("$ ====================================================================================")
    A(f"$ Sky130A interconnect ITF, corner {corner}.  INDICATIVE, AUTHORED (no foundry ITF ships with Sky130)")
    A("$ generated by scripts/gen_stack.py ; source tags [FIG] [TLEF] [MAGIC] [FIT] [ORCX] [DRM] [ABSENT]")
    A("$ are defined in that file's docstring.")
    A(f"$ ER corner multiplier = {s:.4f} [ORCX]; R corner from [TLEF] {corner}.tlef (poly/contact R from [MAGIC]).")
    A("$ Convention: stack is listed top to bottom; each conductor is embedded in the dielectric listed")
    A("$ immediately above it, so that dielectric's thickness is the distance from this conductor's bottom")
    A("$ to the next conductor's bottom (z-bottoms from [FIG]).  Per-slab ER = series-equivalent of the")
    A("$ [FIG]/[FIT] sub-layers.  CRT1/CRT2/ETCH are [ABSENT] (not published for Sky130).")
    A("$ ====================================================================================")
    A(f"TECHNOLOGY = sky130A_{corner}")
    A("GLOBAL_TEMPERATURE = 25.0")
    A("BACKGROUND_ER = 1.0")
    A("")
    blk("DIELECTRIC", PI1[0], [("THICKNESS", f"{PI1[2]-PI1[1]:.4f}"), ("ER", f"{PI1[3]*s:.4f}")], PI1[4])
    names = ["met5", "met4", "met3", "met2", "met1", "li1", "poly"]
    tops = {"met5": 6.6311, "met4": Z["met5"][0], "met3": Z["met4"][0], "met2": Z["met3"][0], "met1": Z["met2"][0],
            "li1": Z["met1"][0], "poly": Z["li1"][0]}
    labs = {"met5": "IMD5", "met4": "ILD4", "met3": "ILD3", "met2": "ILD2", "met1": "ILD1", "li1": "ILDLI", "poly": "ILDPOLY"}
    for n in names:
        zb = Z[n][0]; zt = tops[n]
        k = slab_for(zb, zt) * s
        blk("DIELECTRIC", labs[n], [("THICKNESS", f"{zt-zb:.4f}"), ("ER", f"{k:.4f}")], f"z {zb} -> {zt}, embeds {n} [FIG,FIT]")
        if n == "poly":
            blk("CONDUCTOR", "poly", [("THICKNESS", Z[n][1]), ("WMIN", POLY["wmin"]), ("SMIN", POLY["smin"]), ("RPSQ", POLY["rpsq"][c])],
                "poly: thickness [FIG]; w/s [DRM] poly.1a/poly.2; Rsq [MAGIC]")
        else:
            wmin, smin, *rs = COND[n]
            blk("CONDUCTOR", n, [("THICKNESS", Z[n][1]), ("WMIN", wmin), ("SMIN", smin), ("RPSQ", rs[c])],
                f"{n}: thickness [FIG]; w/s/Rsq [TLEF {corner}]")
    blk("DIELECTRIC", "FOX", [("THICKNESS", f"{SLABS[0][2]-SLABS[0][1]:.4f}"), ("ER", f"{SLABS[0][3]*s:.4f}")],
        f"{SLABS[0][4]}; diffusion is not modelled in the ITF (see ICT)")
    A("")
    A("$ Contacts and cuts (listed after the layer stack, as in conventional ITF files)")
    blk("VIA", "licon", [("FROM", "poly"), ("TO", "li1"), ("AREA", f"{LICON_W**2:.4f}"), ("RPV", LICON_RPV["poly"][c])],
        "licon to poly: Rc [MAGIC contact pc]; cut width [TLEF licon]")
    for (vn, lo, hi, w, rpv) in VIAS:
        blk("VIA", vn, [("FROM", lo), ("TO", hi), ("AREA", f"{w*w:.4f}"), ("RPV", rpv[c])],
            f"{vn}: cut {w} um [TLEF {TLEF_NAME[vn]}]; per-cut R [TLEF {corner}]")
    return "\n".join(o) + "\n"


def ict_text(corner):
    s = ER_SCALE[corner]; c = ci[corner]
    o = []; A = o.append
    A(f"# ====================================================================================")
    A(f"# Sky130A interconnect ICT -- corner {corner} -- INDICATIVE, AUTHORED (no foundry ICT ships with Sky130)")
    A(f"# generated by scripts/gen_stack.py ; sources: [FIG] [TLEF] [MAGIC] [FIT] [ORCX] [DRM] (see docstring)")
    A(f"# ER corner multiplier {s:.4f} [ORCX]; sheet/contact R corner [TLEF]/[MAGIC] {corner}.")
    A(f"# Heights are absolute (z from substrate reference).  Planar dielectrics laterally intersect conductors.")
    A(f"# ====================================================================================")
    A(f'process "sky130A_{corner}" {{')
    A(f"    background_dielectric_constant 1.0")
    A(f"    temp_reference 25")
    A(f"}}")
    A("# wells are not declared: Techgen ignores the well statement (warns) and Quantus does not use it at runtime.")
    A("")
    A(f'diffusion "ndiff" {{\n    thickness {DIFF_TOP:.4f}\n    resistivity {DIFF["ndiff"][c]}\n}}   # top at poly bottom [MAGIC alldiff]; Rsq [MAGIC] n+ ; TC [ABSENT]'.replace("}}", "}"))
    A(f'diffusion "pdiff" {{\n    thickness {DIFF_TOP:.4f}\n    resistivity {DIFF["pdiff"][c]}\n}}   # Rsq [MAGIC] p+'.replace("}}", "}"))
    A("")
    A(f'conductor "poly" {{\n    min_spacing {POLY["smin"]}\n    min_width {POLY["wmin"]}\n    height {Z["poly"][0]}\n    thickness {Z["poly"][1]}\n    resistivity {POLY["rpsq"][c]}\n    gate_forming_layer true\n}}')
    for n in ("li1", "met1", "met2", "met3", "met4", "met5"):
        wmin, smin, *rs = COND[n]
        A(f'conductor "{n}" {{\n    min_spacing {smin}\n    min_width {wmin}\n    height {Z[n][0]}\n    thickness {Z[n][1]}\n    resistivity {rs[c]}\n    gate_forming_layer false\n}}')
    A("")
    for (nm, z0, z1, k, src) in SLABS:
        A(f'dielectric "{nm}" {{\n    conformal FALSE\n    height {z0}\n    thickness {z1-z0:.4f}\n    dielectric_constant {k*s:.4f}\n}}   # {src}'.replace("}}", "}"))
    A(f'dielectric "{PI1[0]}" {{\n    conformal FALSE\n    height {PI1[1]}\n    thickness {PI1[2]-PI1[1]:.4f}\n    dielectric_constant {PI1[3]*s:.4f}\n}}   # {PI1[4]}'.replace("}}", "}"))
    A("")
    A(f'via "licon" {{\n    top_layer li1\n    bottom_layer poly\n    contact_resistance {LICON_RPV["poly"][c]}\n}}   # [MAGIC] pc'.replace("}}", "}"))
    A(f'via "licon" {{\n    top_layer li1\n    bottom_layer ndiff\n    contact_resistance {LICON_RPV["ndiff"][c]}\n}}   # [MAGIC] ndc'.replace("}}", "}"))
    A(f'via "licon" {{\n    top_layer li1\n    bottom_layer pdiff\n    contact_resistance {LICON_RPV["pdiff"][c]}\n}}   # [MAGIC] pdc'.replace("}}", "}"))
    for (vn, lo, hi, w, rpv) in VIAS:
        A(f'via "{vn}" {{\n    top_layer {hi}\n    bottom_layer {lo}\n    contact_resistance {rpv[c]}\n}}   # [TLEF {TLEF_NAME[vn]} {corner}], cut {w} um'.replace("}}", "}"))
    # Techgen only accepts '#' comments on their own line: hoist the trailing "}   # note" comments above their block.
    flat = "\n".join(o).split("\n"); res = []; start = None
    for l in flat:
        if l.rstrip().endswith("{"): start = len(res)
        m = re.match(r"^\}\s+#(.*)$", l)
        if m and start is not None:
            res.insert(start, "#" + m.group(1)); res.append("}"); start = None
        else:
            res.append(l)
    return "\n".join(res) + "\n"


def summary():
    o = ["Sky130A stack parameter table (nom) -- all INDICATIVE; source tags in gen_stack.py docstring", ""]
    o.append("%-6s %8s %8s %8s %8s | %8s %8s %8s | %s" % ("layer", "z_bot", "thick", "wmin", "smin", "Rsq_nom", "Rsq_min", "Rsq_max", "source"))
    for n in ("poly", "li1", "met1", "met2", "met3", "met4", "met5"):
        if n == "poly":
            o.append("%-6s %8.4f %8.4f %8.3f %8.3f | %8.4g %8.4g %8.4g | z,t [FIG]; w/s [DRM]; Rsq [MAGIC]" % ("poly", *Z[n], POLY["wmin"], POLY["smin"], *POLY["rpsq"]))
        else:
            w, sp, a, b, cc = COND[n]
            o.append("%-6s %8.4f %8.4f %8.3f %8.3f | %8.4g %8.4g %8.4g | z,t [FIG]; w/s/Rsq [TLEF]" % (n, *Z[n], w, sp, a, b, cc))
    o.append("")
    o.append("%-6s %-6s %-6s %7s | %8s %8s %8s | source" % ("via", "from", "to", "cut_um", "RPV_nom", "RPV_min", "RPV_max"))
    for (vn, lo, hi, w, r) in VIAS:
        o.append("%-6s %-6s %-6s %7.3f | %8.4g %8.4g %8.4g | [TLEF %s]" % (vn, lo, hi, w, *r, TLEF_NAME[vn]))
    for k, v in LICON_RPV.items():
        o.append("%-6s %-6s %-6s %7.3f | %8.4g %8.4g %8.4g | [MAGIC contact %s]" % ("licon", k, "li1", LICON_W, *v, k))
    o.append("")
    o.append("%-11s %8s %8s %7s | source" % ("dielectric", "z0", "z1", "K_nom"))
    for (nm, z0, z1, k, src) in SLABS + [PI1]:
        o.append("%-11s %8.4f %8.4f %7.3f | %s" % (nm, z0, z1, k, src))
    o.append("")
    o.append("ITF per-conductor-slab series-equivalent ER (nom):")
    tops = {"met5": 6.6311, "met4": Z["met5"][0], "met3": Z["met4"][0], "met2": Z["met3"][0], "met1": Z["met2"][0], "li1": Z["met1"][0], "poly": Z["li1"][0]}
    for n in ("met5", "met4", "met3", "met2", "met1", "li1", "poly"):
        o.append("  %-5s slab %.4f -> %.4f  ER %.4f" % (n, Z[n][0], tops[n], slab_for(Z[n][0], tops[n])))
    o.append("")
    o.append("Corner multipliers: ER min %.4f / max %.4f [ORCX]; R from [TLEF]/[MAGIC] per corner." % (ER_SCALE["min"], ER_SCALE["max"]))
    o.append("ABSENT (not published): temperature coefficients CRT1/CRT2, etch/width bias, erosion/density thickness, side-wall tangent.")
    return "\n".join(o) + "\n"


def maps(out):
    os.makedirs(f"{out}/map", exist_ok=True)
    with open(f"{out}/map/starrc_layer.map", "w") as f:
        f.write("# tech-LEF layer name -> ITF layer name (StarRC MAPPING_FILE / ICC2 tech2itf map).  Generated by gen_stack.py\n")
        f.write("conducting_layers\n")
        for n in ("li1", "met1", "met2", "met3", "met4", "met5"): f.write(f"{n} {n}\n")
        f.write("via_layers\n")
        for (vn, *_r) in VIAS: f.write(f"{TLEF_NAME[vn]} {vn}\n")
    with open(f"{out}/map/quantus_lef2ict.map", "w") as f:
        f.write("# tech-LEF layer name -> ICT layer name (Innovus setExtractRCMode -lefTechFileMap).  Generated by gen_stack.py\n")
        for n in ("li1", "met1", "met2", "met3", "met4", "met5"): f.write(f"{n} {n}\n")
        for (vn, *_r) in VIAS: f.write(f"{TLEF_NAME[vn]} {vn}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--out", required=True)
    a = ap.parse_args()
    for sub in ("itf", "ict", "map"): os.makedirs(f"{a.out}/{sub}", exist_ok=True)
    for c in CORNERS:
        open(f"{a.out}/itf/sky130A_{c}.itf", "w").write(itf_text(c))
        open(f"{a.out}/ict/sky130A_{c}.ict", "w").write(ict_text(c))
    maps(a.out)
    open(f"{a.out}/stack_summary.txt", "w").write(summary())
    print(f"wrote ITF/ICT/maps for {CORNERS} under {a.out}")
