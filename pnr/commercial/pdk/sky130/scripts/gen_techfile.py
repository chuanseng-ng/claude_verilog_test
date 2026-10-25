#!/usr/bin/env python3
"""gen_techfile.py -- Sky130 tech LEF  ->  Synopsys ICC2 technology file (.tf) + ICC2 tech setup Tcl.

ICC2's library manager (icc2_lm_shell create_workspace -technology) takes a Milkyway-style .tf, NOT a
tech LEF; Sky130 ships none.  This script derives one from the nominal tech LEF
(sky130_fd_sc_hd__nom.tlef) so that the layer geometry/rules are the same ones OpenROAD uses.

Outputs (under --out, default ../build/ndm):
  sky130_hd.tf             technology file: Technology / Tile / Layer / ContactCode
  sky130_tech_setup.tcl    design-library side settings ICC2 does NOT keep in the tf:
                           routing directions, track patterns, antenna rules, ignored li1 routing
  sky130_layer_map.txt     tech-LEF name -> ICC2 mask name table (for StarRC/ICC2 layer mapping)

Layer-stack decision (documented in pdk_enablement_sky130.md, Part 2a):
  ICC2 mask names must run metal1..metalN / via1..viaN without gaps.  Sky130 has a local interconnect
  (li1) below met1, so li1 becomes mask `metal1` and met1..met5 become metal2..metal6 (cuts mcon..via4 =
  via1..via5).  Layer NAMES in the tf are the tech-LEF names (li1, mcon, met1, via, ...), so scripts and
  the LEF/DEF read-back use the Sky130 names; only the internal mask index is shifted.  li1 is excluded
  from routing in tech_setup (OpenROAD/LibreLane also routes met1..met5 only).
"""
import argparse
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def parse_layers(text):
    layers = []
    for m in re.finditer(r"^LAYER\s+(\S+)\s*(.*?)^END\s+\1\s*$", text, re.S | re.M):
        name, body = m.group(1), m.group(2)
        body = re.sub(r"#.*", "", body)
        d = {"name": name, "body": body}
        t = re.search(r"TYPE\s+(\w+)", body)
        d["type"] = t.group(1) if t else ""
        for key in ("DIRECTION", "AREA", "THICKNESS", "MINENCLOSEDAREA"):
            k = re.search(key + r"\s+([\w.\-]+)\s*;", body)
            d[key] = k.group(1) if k else None
        k = re.search(r"\bWIDTH\s+([\d.]+)\s*;", body)
        d["WIDTH"] = float(k.group(1)) if k else None
        k = re.search(r"\bSPACING\s+([\d.]+)\s*;", body)
        d["SPACING"] = float(k.group(1)) if k else None
        k = re.search(r"PITCH\s+([\d.]+)(?:\s+([\d.]+))?\s*;", body)
        d["PITCH"] = (float(k.group(1)), float(k.group(2)) if k.group(2) else float(k.group(1))) if k else None
        k = re.search(r"OFFSET\s+([\d.]+)(?:\s+([\d.]+))?\s*;", body)
        d["OFFSET"] = (float(k.group(1)), float(k.group(2)) if k.group(2) else float(k.group(1))) if k else None
        k = re.search(r"SPACINGTABLE\s+PARALLELRUNLENGTH\s+([\d.\s]+?)\s*((?:WIDTH.*?)+);", body, re.S)
        if k:
            prl = [float(x) for x in k.group(1).split()]
            rows = re.findall(r"WIDTH\s+([\d.]+)\s+([\d.\s]+?)(?=WIDTH|$)", k.group(2).strip(), re.S)
            d["SPT"] = (prl, [(float(w), [float(x) for x in s.split()]) for w, s in rows])
        else:
            d["SPT"] = None
        k = re.search(r"ENCLOSURE\s+BELOW\s+([\d.]+)\s+([\d.]+)", body)
        d["ENC_BELOW"] = (float(k.group(1)), float(k.group(2))) if k else (0.0, 0.0)
        k = re.search(r"ENCLOSURE\s+ABOVE\s+([\d.]+)\s+([\d.]+)", body)
        d["ENC_ABOVE"] = (float(k.group(1)), float(k.group(2))) if k else (0.0, 0.0)
        k = re.search(r"RESISTANCE\s+RPERSQ\s+([\d.]+)", body)
        d["RPERSQ"] = float(k.group(1)) if k else None
        k = re.search(r"\n\s*RESISTANCE\s+([\d.]+)\s*;", body)
        d["RCUT"] = float(k.group(1)) if k else None
        k = re.search(r"ANTENNADIFFSIDEAREARATIO\s+PWL\s+\((.*?)\)\s*;", body, re.S)
        d["ANT_SIDE_DIFF"] = k.group(1) if k else None
        k = re.search(r"ANTENNADIFFAREARATIO\s+PWL\s+\((.*?)\)\s*;", body, re.S)
        d["ANT_DIFF"] = k.group(1) if k else None
        k = re.search(r"ANTENNAAREARATIO\s+([\d.]+)", body)
        d["ANT_AREA"] = float(k.group(1)) if k else None
        k = re.search(r"ANTENNACUMAREARATIO", body)
        layers.append(d)
    return layers


def parse_viarules(text):
    """cut-layer -> ((lower enc x,y), (upper enc x,y)) from the base (un-suffixed) VIARULE ... GENERATE."""
    out = {}
    for m in re.finditer(r"^VIARULE\s+(\S+)\s+GENERATE\s*(.*?)^END\s+\1\s*$", text, re.S | re.M):
        if re.search(r"_(R|M|MR|C)$", m.group(1)):
            continue
        ls = re.findall(r"LAYER\s+(\S+)\s*;\s*(?:ENCLOSURE\s+([\d.]+)\s+([\d.]+)\s*;)?", m.group(2))
        if len(ls) == 3:
            (_, lx, ly), (_, ux, uy), (cut, _, _) = ls
            out[cut] = ((float(lx), float(ly)), (float(ux), float(uy)))
    return out


def parse_sites(text):
    out = []
    for m in re.finditer(r"^SITE\s+(\S+)\s*(.*?)^END\s+\1", text, re.S | re.M):
        s = re.search(r"SIZE\s+([\d.]+)\s+BY\s+([\d.]+)", m.group(2))
        out.append((m.group(1), float(s.group(1)), float(s.group(2))))
    return out


def pwl(s):
    pts = re.findall(r"\(\s*([\d.]+)\s+([\d.]+)\s*\)", "(" + s + ")")
    return [(float(a), float(b)) for a, b in pts]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tlef", default=os.path.expandvars("$PDK_ROOT/sky130A/libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef"))
    ap.add_argument("--out", default=os.path.join(HERE, "..", "build", "ndm"))
    a = ap.parse_args()
    text = open(a.tlef).read()
    layers = parse_layers(text)
    sites = parse_sites(text)
    vr = parse_viarules(text)
    os.makedirs(a.out, exist_ok=True)

    # ---- mask-name assignment ------------------------------------------------------------------
    mask = {}
    mid = 0
    vid = 0
    for L in layers:
        n = L["name"]
        if n == "nwell":
            mask[n] = "nwell"
        elif n == "pwell":
            mask[n] = "pwell"
        elif n == "licon":
            mask[n] = "polyCont"   # poly/diffusion -> li1 contact
        elif L["type"] == "ROUTING":
            mid += 1
            mask[n] = "metal%d" % mid
        elif L["type"] == "CUT":
            vid += 1
            mask[n] = "via%d" % vid
    num = {}
    nxt = {"nwell": 1, "pwell": 2, "polyCont": 10}
    for L in layers:
        m = mask[L["name"]]
        if m in nxt and not m.startswith("metal") and not m.startswith("via"):
            num[L["name"]] = nxt[m]
        elif m.startswith("metal"):
            num[L["name"]] = 20 + 2 * int(m[5:])        # metal1=22, metal2=24 ...
        elif m.startswith("via"):
            num[L["name"]] = 20 + 2 * int(m[3:]) - 1     # via1=21 ... between metal(n) and metal(n+1)

    f = []
    f.append("""Technology {
    name                    = "sky130_fd_sc_hd"
    date                    = "generated by scripts/gen_techfile.py from sky130_fd_sc_hd__nom.tlef"
    dielectric              = 4.0
    unitTimeName            = "ns"
    timePrecision           = 1000
    unitLengthName          = "micron"
    lengthPrecision         = 1000
    gridResolution          = 5
    unitVoltageName         = "v"
    voltagePrecision        = 100000
    unitCurrentName         = "mA"
    currentPrecision        = 100
    unitPowerName           = "pw"
    powerPrecision          = 1000
    unitResistanceName      = "kohm"
    resistancePrecision     = 10000000
    unitCapacitanceName     = "pf"
    capacitancePrecision    = 10000000
    unitInductanceName      = "nh"
    inductancePrecision     = 100
}
""")
    for (n, w, h) in sites:
        f.append('Tile "%s" {\n    width                   = %g\n    height                  = %g\n}\n' % (n, w, h))
    for L in layers:
        n = L["name"]
        m = mask[n]
        f.append('Layer "%s" {' % n)
        f.append("    layerNumber             = %d" % num[n])
        f.append('    maskName                = "%s"' % m)
        if L["type"] == "ROUTING":
            f.append("    isDefaultLayer          = 1")
            # LEF PITCH is "x y"; for a single value it applies to both
            p = L["PITCH"]
            pitch = p[0] if L["DIRECTION"] == "VERTICAL" else p[1]
            if n == "li1":
                pitch = p[0]
            f.append("    pitch                   = %g" % pitch)
            f.append("    defaultWidth            = %g" % L["WIDTH"])
            f.append("    minWidth                = %g" % L["WIDTH"])
            minsp = L["SPT"][1][0][1][0] if L["SPT"] else (L["SPACING"] or L["WIDTH"])
            f.append("    minSpacing              = %g" % minsp)
            if L["AREA"]:
                f.append("    minArea                 = %s" % L["AREA"])
            if L["SPT"] and len(L["SPT"][1]) > 1:
                # Tech LEF: PARALLELRUNLENGTH 0 / WIDTH 0 -> s0 / WIDTH w1 -> s1 (one PRL column, i.e. width>=w1
                # needs s1 at any positive parallel run).  ICC2's fat table is NxN, rejects identical rows/columns
                # (TECH-032) and needs a leading 0 threshold.  The non-redundant 2x2 below is symmetric under
                # transpose (so row/column order cannot matter) and is equivalent for any real overlap
                # (parallel run >= 0.001 um); only exactly-zero-overlap (corner-to-corner) pairs differ.
                prl, rows = L["SPT"]
                s0, s1 = rows[0][1][0], rows[1][1][0]
                f.append("    fatTblDimension         = 2")
                f.append("    fatTblThreshold         = (0,%g)" % rows[1][0])
                f.append("    fatTblParallelLength    = (0,0.001)")
                f.append("    fatTblSpacing           = (%g,%g,%g,%g)" % (s0, s0, s0, s1))
        elif L["type"] == "CUT":
            f.append("    isDefaultLayer          = 1")
            # licon has no WIDTH/SPACING in the tech LEF: Sky130 DRM licon.1/licon.2 = 0.17 / 0.17 um (assumed)
            w = L["WIDTH"] or 0.17
            sp = L["SPACING"] or 0.17
            f.append("    pitch                   = %g" % (w + sp))
            f.append("    defaultWidth            = %g" % w)
            f.append("    minWidth                = %g" % w)
            f.append("    minSpacing              = %g" % sp)
        else:
            f.append("    isDefaultLayer          = 1")
        f.append("}\n")

    # ContactCodes for the cut layers (lower/upper neighbour = adjacent ROUTING layers in LEF order)
    names = [L["name"] for L in layers]
    cc = 0
    for i, L in enumerate(layers):
        if L["type"] != "CUT" or L["name"] == "licon":
            continue
        low = next(layers[j]["name"] for j in range(i - 1, -1, -1) if layers[j]["type"] == "ROUTING")
        up = next(layers[j]["name"] for j in range(i + 1, len(layers)) if layers[j]["type"] == "ROUTING")
        cc += 1
        f.append('ContactCode "%s_cc" {' % L["name"])
        f.append("    contactCodeNumber       = %d" % cc)
        f.append('    cutLayer                = "%s"' % L["name"])
        f.append('    lowerLayer              = "%s"' % low)
        f.append('    upperLayer              = "%s"' % up)
        f.append("    isDefaultContact        = 1")
        f.append("    cutWidth                = %g" % L["WIDTH"])
        f.append("    cutHeight               = %g" % L["WIDTH"])
        # enclosure (x, y) of the default via (base VIARULE); falls back to the layer ENCLOSURE if absent
        (lex, ley), (uex, uey) = vr.get(L["name"], (L["ENC_BELOW"], L["ENC_ABOVE"]))
        f.append("    lowerLayerEncWidth      = %g" % lex)
        f.append("    lowerLayerEncHeight     = %g" % ley)
        f.append("    upperLayerEncWidth      = %g" % uex)
        f.append("    upperLayerEncHeight     = %g" % uey)
        f.append("}\n")
    tf = os.path.join(a.out, "sky130_hd.tf")
    open(tf, "w").write("\n".join(x for x in f if x != "") + "\n")

    # ---- design-lib setup Tcl ------------------------------------------------------------------
    t = ["# sky130_tech_setup.tcl -- GENERATED by scripts/gen_techfile.py; source in icc2_shell AFTER create_lib",
         "# (these settings live in the design library, not in the .tf / reference NDM)",
         "# li1 = mask metal1: excluded from signal routing (cell-internal local interconnect).", ""]
    for L in layers:
        if L["type"] != "ROUTING":
            continue
        d = {"VERTICAL": "vertical", "HORIZONTAL": "horizontal"}[L["DIRECTION"]]
        t.append("set_attribute -objects [get_layers %s] -name routing_direction -value %s" % (L["name"], d))
    t.append("")
    t.append("# Track patterns (pitch/offset from the tech LEF; li1 has 0.46 x 0.34 pitch, offset .23 x .17)")
    t.append("proc sky130_create_tracks {} {")
    for L in layers:
        if L["type"] != "ROUTING" or L["name"] == "li1":
            continue
        p = L["PITCH"][0]
        o = L["OFFSET"][0]
        dirn = "x" if L["DIRECTION"] == "VERTICAL" else "y"
        t.append("  create_track -layer %s -space %g -coord %g -dir %s" % (L["name"], p, o, "X" if dirn == "x" else "Y"))
    t.append("}")
    t.append("")
    t.append("# Antenna rules from the tech LEF (ANTENNAMODEL OXIDE1; PWL tables, diff-area ratios).")
    t.append("# Cell-pin gate/diff areas come from the cell LEF (ANTENNAGATEAREA/ANTENNADIFFAREA).")
    t.append("proc sky130_antenna_rules {} {")
    t.append("  define_antenna_rule -mode 1 -diode_mode 2 -metal_ratio 400 -cut_ratio 6")
    for L in layers:
        if L["type"] == "ROUTING" and L["ANT_SIDE_DIFF"]:
            pts = pwl(L["ANT_SIDE_DIFF"])
            t.append("  # %s side-area/diff PWL: %s" % (L["name"], pts))
            t.append("  define_antenna_layer_rule -mode 1 -layer %s -ratio %g -diode_ratio {%s}" % (
                L["name"], pts[0][1], " ".join("{%g %g}" % p for p in pts)))
        if L["type"] == "CUT" and L["ANT_DIFF"]:
            pts = pwl(L["ANT_DIFF"])
            t.append("  define_antenna_layer_rule -mode 1 -layer %s -ratio %g -diode_ratio {%s}" % (
                L["name"], pts[0][1], " ".join("{%g %g}" % p for p in pts)))
    t.append("}")
    open(os.path.join(a.out, "sky130_tech_setup.tcl"), "w").write("\n".join(t) + "\n")

    d = ["# sky130_layer_dirs.tcl -- GENERATED; sourced by build_ndm.tcl right after create_workspace so the",
         "# reference NDM carries the Sky130 preferred routing directions (a .tf has no direction field; without",
         "# this DC/ICC2 assume alternating H/V starting at the bottom layer, i.e. li1=H, met1=V -- wrong for Sky130)."]
    for L in layers:
        if L["type"] == "ROUTING":
            d.append("set_attribute [get_layers %s] routing_direction %s" % (L["name"], {"VERTICAL": "vertical", "HORIZONTAL": "horizontal"}[L["DIRECTION"]]))
    open(os.path.join(a.out, "sky130_layer_dirs.tcl"), "w").write("\n".join(d) + "\n")

    tk = ["# sky130_tracks_innovus.tcl -- GENERATED.  Innovus' automatic tracks deviate from the tech LEF (measured:",
          "# met3 y 0.61 vs 0.68, met4 x 0.69 vs 0.92, met5 y 3.66 vs 3.4; -honor_pitch does not change that).  Source after floorPlan.",
          "# Pitches are the tech-LEF PITCH values; start offsets are left to Innovus (it aligns them to the lower layer; the",
          "# -offsets form was accepted but did not reproduce the LEF OFFSETs for the preferred direction).",
          "set _P {}"]
    for L in layers:
        if L["type"] == "ROUTING":
            px, py = L["PITCH"][0], L["PITCH"][1]
            tk.append("lappend _P [list %s vert %g] [list %s horiz %g]" % (L["name"], px, L["name"], py))
    tk.append("add_tracks -mode replace -pitches $_P")
    open(os.path.join(a.out, "sky130_tracks_innovus.tcl"), "w").write("\n".join(tk) + "\n")

    mp = ["# tech-LEF layer  ICC2-mask  layerNumber  type"]
    for L in layers:
        mp.append("%-8s %-9s %3d %s" % (L["name"], mask[L["name"]], num[L["name"]], L["type"]))
    open(os.path.join(a.out, "sky130_layer_map.txt"), "w").write("\n".join(mp) + "\n")
    print("wrote", tf)


if __name__ == "__main__":
    sys.exit(main())
