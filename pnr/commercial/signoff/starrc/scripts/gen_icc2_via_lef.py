#!/usr/bin/env python3
"""gen_icc2_via_lef.py > icc2_via_names.lef

ICC2 writes the default-contact via names (ContactCode names of pnr/commercial/pdk/sky130/build/ndm/sky130_hd.tf:
mcon_cc, via_cc, via2_cc, via3_cc, via4_cc) into the routed DEF.  The PDK LEF has no such VIA (it calls them
L1M1_PR, M1M2_PR ...), so StarRC raises SX-2064 and reports ~33k open nets.  This emits LEF VIAs with the .tf
ContactCode geometry (single cut, centred, per-layer enclosure) so the DEF connects.  Same LEF is given to every arm.
"""
cc = [("mcon_cc", "mcon", "li1", "met1", 0.17, 0.17, 0, 0, 0.06, 0.03),
      ("via_cc", "via", "met1", "met2", 0.15, 0.15, 0.085, 0.055, 0.055, 0.085),
      ("via2_cc", "via2", "met2", "met3", 0.2, 0.2, 0.04, 0.085, 0.065, 0.065),
      ("via3_cc", "via3", "met3", "met4", 0.2, 0.2, 0.09, 0.06, 0.065, 0.065),
      ("via4_cc", "via4", "met4", "met5", 0.8, 0.8, 0.19, 0.19, 0.31, 0.31)]
o = ["VERSION 5.7 ;", 'BUSBITCHARS "[]" ;', 'DIVIDERCHAR "/" ;', ""]
for n, cut, lo, up, w, h, lw, lh, uw, uh in cc:
    o.append("VIA %s DEFAULT" % n)
    o.append("  LAYER %s ; RECT %.3f %.3f %.3f %.3f ;" % (lo, -(w/2+lw), -(h/2+lh), w/2+lw, h/2+lh))
    o.append("  LAYER %s ; RECT %.3f %.3f %.3f %.3f ;" % (cut, -w/2, -h/2, w/2, h/2))
    o.append("  LAYER %s ; RECT %.3f %.3f %.3f %.3f ;" % (up, -(w/2+uw), -(h/2+uh), w/2+uw, h/2+uh))
    o.append("END %s\n" % n)
o.append("END LIBRARY")
print("\n".join(o))
