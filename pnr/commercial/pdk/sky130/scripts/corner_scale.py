#!/usr/bin/env python3 -I
"""corner_scale.py -- min/max capacitance corner multipliers for the Sky130 ITF/ICT.

HISTORY (B1c, 2026-10-26).  The first version of this script read the 4th column of the 'Metal n OVER 0' tables of
libs.tech/openlane/rules.openrcx.sky130A.{nom,min,max}.spef_extractor and called it "area capacitance".  Two errors:
  1. the 4th column of an OpenRCX rules table is RESISTANCE per unit length (value = Rsq/(2 w), e.g. met1
     0.125/(2*0.14) = 4.46e-4, li1 12.8/(2*0.17) = 0.0376), so the min/max "capacitance" ratios (0.719 .. 1.33 per
     layer, geomean 0.7919 / 1.2131) were the sheet-resistance corner ratios;
  2. the OpenROAD/LibreLane flow does not use the *.spef_extractor decks at all: the PDK config.tcl prefers
     rules.openrcx.sky130A.{nom,min,max}.calibre when it exists (it does), and that is what the OpenROAD arm of the
     comparison ran (RCX_RULESETS in the run's 56-openroad-rcx/config.json).  The .spef_extractor decks are flat
     (every table row identical, coupling column 0) and produce no coupling at all.
The authored min/max ITFs therefore had a +-21 % dielectric spread against OpenRCX's -10.7 % / +8.6 %.

NOW.  The capacitance corner is a uniform multiplier on every dielectric constant (a plate/fringe/lateral
capacitance is linear in ER for fixed geometry), calibrated so that StarRC reproduces the OpenRCX corner spread on
the OpenROAD DEF:

    ER_SCALE_c = ( sum_nets C_OpenRCX(c) / sum_nets C_OpenRCX(nom) ) / K_NOM

with K_NOM = 0.9772 the slope of the wire-proportional part of StarRC(nom) against OpenRCX(nom)
(least squares C_StarRC = K*C_OpenRCX + 0.161 fF * n_pins + c, LEF_USE_OBS NO over nets with C < 50 fF; the per-pin term is the
pin/via shape capacitance that StarRC extracts and OpenRCX does not).  The nominal stack is NOT changed.
The result is "calibrated to OpenRCX (Calibre-PEX-derived rcx_patterns decks)", not correlated to silicon.

Prints ER_SCALE_MIN / ER_SCALE_MAX.  With --remeasure the OpenRCX SPEF totals are re-read from the OpenROAD arm
(pnr/commercial/runs/openroad/rv32i_cpu_top.{min,nom,max}.spef); otherwise the recorded totals are used.
"""
import os, sys

# total design capacitance of the OpenRCX SPEFs of the OpenROAD arm, pF (sum of *D_NET totals, incl. coupling)
ORCX_TOTAL_PF = {"min": 888.048, "nom": 995.003, "max": 1080.149}
K_NOM = 0.9772   # StarRC(nom, authored ITF) wire-proportional slope against OpenRCX(nom), final StarRC settings (LEF_USE_OBS NO, coupling thresholds as OpenRCX); was 1.0067 with StarRC defaults


def measure():
    here = os.path.dirname(os.path.abspath(__file__))
    d = os.path.join(here, "../../../runs/openroad")
    out = {}
    for c in ("min", "nom", "max"):
        t = 0.0
        for l in open(os.path.join(d, f"rv32i_cpu_top.{c}.spef"), errors="replace"):
            if l.startswith("*D_NET"):
                t += float(l.split()[2])
        out[c] = t
    return out


def er_scales(tot=None):
    tot = tot or ORCX_TOTAL_PF
    return {"nom": 1.0, "min": tot["min"] / tot["nom"] / K_NOM, "max": tot["max"] / tot["nom"] / K_NOM}


if __name__ == "__main__":
    tot = measure() if "--remeasure" in sys.argv else ORCX_TOTAL_PF
    s = er_scales(tot)
    for c in ("min", "max"):
        print(c, "OpenRCX total %.3f pF  ratio to nom %.4f  /K_NOM -> ER scale %.4f" % (tot[c], tot[c] / tot["nom"], s[c]))
    print("ER_SCALE_MIN=%.4f" % s["min"]); print("ER_SCALE_MAX=%.4f" % s["max"])
