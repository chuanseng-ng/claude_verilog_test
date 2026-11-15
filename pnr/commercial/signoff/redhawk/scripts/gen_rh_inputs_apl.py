#!/usr/bin/env python3
"""gen_rh_inputs_apl.py <arm> -- STEP 8 (2026-11-15) variant of gen_rh_inputs.py: write runs/<arm>/rh_apl/{rh.gsr,run_static.tcl,run_dynamic.tcl} (+ rh_apl_nodecap/) for one arm.
DIFFERENCES to gen_rh_inputs.py: (1) cell models: APL (apl/runs/main/results: switching current + intrinsic cap/ESR/leakage for the 12 most-used std cells, intrinsic cap/ESR for every decap cell)
 replace the Liberty-derived defaults for those cells and the DECAP_CELL spice-W/L ESTIMATE; (2) an ASSUMED generic package model (setup pad / wirebond / package, values below) is applied to every supply connection;
 (3) arms icc2b9 / innovusb11 / icc2b12 added.  pg.ploc, power.ipf, custom_pgarc.lib are the ones of runs/<arm>/rh/ (made by gen_ploc.py / gen_ipf.py / gen_rh_inputs.py).
ORIGINAL DOC of gen_rh_inputs.py follows.  
write runs/<arm>/rh/{rh.gsr,run_static.tcl,run_dynamic.tcl} for one arm.  Paths from signoff/pt/scripts/arms.sh conventions.
ASSUMPTIONS (all arms identical; documented in reports/redhawk_ir_summary.md):
  tech: build/redhawk/sky130A_nom.tech (authored ITF -> Ansys converter, uncorrelated); LEF/lib: sky130_fd_sc_hd + sky130_ef_sc_hd + SRAM abstract
  power: PrimePower nom_tt vectorless variant B per-instance (INSTANCE_POWER_FILE); SRAM macros = lumped sinks on vccd1/vssd1 (DEF-tied to VPWR/VGND)
  pads: ideal sources at both ends of every met5 stripe (gen_ploc.py); no package
  cell current/cap models: RedHawk defaults derived from Liberty (no APL characterised); decap cells: ESTIMATED from the spice W/L (gate-oxide C, channel R)
"""
import os, sys
arm = sys.argv[1]
here = os.path.dirname(os.path.abspath(__file__))
root = os.path.abspath(os.path.join(here, "../../../../.."))
com = root + "/pnr/commercial"
pdk = os.path.expanduser("~/pdk/ciel/sky130/versions/0fe599b2afb6708d281543108caf8310912f54af/sky130A/libs.ref")
if not os.path.isdir(pdk): pdk = os.environ.get("PDK_ROOT", os.path.expanduser("~/pdk")) + "/sky130A/libs.ref"
DEF = {"openroad": com + "/runs/openroad/rv32i_cpu_top.def",
       "icc2b6": com + "/impl/icc2/runs/b6_icc2/out/rv32i_cpu_top.def",
       "innovusb6": com + "/impl/innovus/runs/b6_innovus/out/rv32i_cpu_top.def",
       "icc2b9": com + "/impl/icc2/runs/b9_icc2/out/rv32i_cpu_top.def",
       "icc2b12": com + "/impl/icc2/runs/b12_icc2/out/rv32i_cpu_top.def",
       "innovusb11": com + "/impl/innovus/runs/b11_innovus/out/rv32i_cpu_top.def"}[arm]
SPEF = com + "/signoff/starrc/runs/%s_nom/rv32i_cpu_top.nom.spef" % arm
run = com + "/signoff/redhawk/runs/" + arm
base = run + "/rh"; rh = run + "/rh_apl"; os.makedirs(rh, exist_ok=True)   # base = pg.ploc / power.ipf / custom_pgarc.lib (shared with the b6-era recipe)
APL = com + "/signoff/redhawk/apl/runs/main/results/TT_25_1v80"
hd = pdk + "/sky130_fd_sc_hd"
# ---- decap model (ASSUMED): C = sum(W*L)*Cox (Cox = 3.9*eps0/4.1nm = 8.42 fF/um2), R = (Rn || Rp)/3 with Ron = (L/W)/(uCox*Vov), nfet 200uA/V2 Vov 1.2, pfet-hvt 60uA/V2 Vov 0.9
COX = 8.42  # fF/um2
dec = {}
WID = {"sky130_fd_sc_hd__decap_3": 1.38, "sky130_fd_sc_hd__decap_4": 1.84, "sky130_fd_sc_hd__decap_6": 2.76, "sky130_fd_sc_hd__decap_8": 3.68, "sky130_fd_sc_hd__decap_12": 5.52, "sky130_ef_sc_hd__decap_12": 5.52}   # LEF SIZE x (height 2.72)
for n, L in (("sky130_fd_sc_hd__decap_3", .59), ("sky130_fd_sc_hd__decap_4", 1.05), ("sky130_fd_sc_hd__decap_6", 1.97), ("sky130_fd_sc_hd__decap_8", 2.89),
             ("sky130_fd_sc_hd__decap_12", 4.73), ("sky130_ef_sc_hd__decap_12", 4.73)):
    wn, wp = .55, .87
    c = (wn + wp) * L * COX * 1e-3        # pF
    rn = (L / wn) / (200e-6 * 1.2) / 3; rp = (L / wp) / (60e-6 * 0.9) / 3
    r = 1 / (1 / rn + 1 / rp)
    dec[n] = (c, r, L * 2.0 + 0.0)
g = []
g.append("TECH_FILE %s/pnr/commercial/pdk/sky130/build/redhawk/sky130A_nom.tech" % root)
g.append("LEF_FILES {\n %s/techlef/sky130_fd_sc_hd__nom.tlef\n %s/lef/sky130_fd_sc_hd.lef\n %s/lef/sky130_ef_sc_hd.lef\n %s/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef\n}" % (hd, hd, hd, pdk))
g.append("DEF_FILES {\n %s\n}" % DEF)
# custom lib: PG arcs for the multi-PG-pin cells the Liberty does not describe (fill/ef cells: VPWR-VGND; VPB/VNB are well ties, not supply arcs)
cl = "".join("cell %s {\n    pgarc {\n        VPWR VGND\n    }\n}\n" % c for c in ("sky130_fd_sc_hd__fill_1", "sky130_fd_sc_hd__fill_2", "sky130_fd_sc_hd__fill_4", "sky130_fd_sc_hd__fill_8",
      "sky130_ef_sc_hd__fill_4", "sky130_ef_sc_hd__fill_8", "sky130_ef_sc_hd__fill_12", "sky130_ef_sc_hd__decap_12"))
open(base + "/custom_pgarc.lib", "w").write(cl)   # unchanged recipe (fill / ef cells); fd decap cells get their P/G arc from the APL cdev
g.append("LIB_FILES {\n %s/lib/sky130_fd_sc_hd__tt_025C_1v80.lib\n %s/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib\n %s/custom_pgarc.lib custom\n}" % (hd, root, base))
g.append("IGNORE_DEF_ERROR 1")
g.append("VDD_NETS {\n VPWR 1.8\n}\nGND_NETS {\n VGND 0\n}")
g.append("PAD_FILES {\n %s/pg.ploc\n}" % base)
g.append("FREQUENCY 75e6")
g.append("INSTANCE_POWER_FILES {\n %s/power.ipf\n}" % base)
g.append("STA_FILE {\n rv32i_cpu_top %s/pt/rv32i_cpu_top.timing.gz\n}" % run)
g.append("CELL_RC_FILE {\n EXTRACT_RC 1\n rv32i_cpu_top %s\n}" % SPEF)
g.append("MULTI_THREADS 1 2")
g.append("ENABLE_AUTO_EM 1\nEM_REPORT_PERCENTAGE 50\nEM_REPORT_LINE_NUMBER 100000")
g.append("# APL (step 8): characterised with Ansys apldi from the Sky130 TT SPICE models; cells not listed keep the RedHawk defaults derived from the Liberty\nAPL_FILES {\n %s/CURRENT current\n %s/CAP cdev\n}" % (APL, APL))
g.append("IGNORE_APL_CHECK 1")
g.append("DYNAMIC_SIMULATION_TIME 2.8e-8\nDYNAMIC_TIME_STEP 20e-12")
open(rh + "/rh.gsr", "w").write("\n".join(g) + "\n")
# ---- ASSUMED generic package model (NOT a model of any real package or board).  Values = the "simple package" example of the RedHawk manual (ch. 12 "Package and Board Models"):
#      pad R 0.01 ohm C 0.5 pF; wirebond/bump R 0.245 ohm L 1420 pH C 5 pF; package R 0.001 ohm L 10 pH C 10 pF; applied identically to VDD and VSS, to every one of the 72 supply connections
#      (one per met5 stripe end, gen_ploc.py).  Static analysis is R only; dynamic uses L and C.  This is a placeholder so the dynamic runs include a supply impedance at all;
#      replace it with a real package SPICE subcircuit (PACKAGE_SPICE_SUBCKT_INFO) when one exists.
PKG = "\n".join(["# ASSUMED generic package model (RedHawk manual simple-package example values; not a real package) -- R in ohm, L in pH, C in pF",
                 "setup pad -power -r 0.01 -c 0.5", "setup pad -ground -r 0.01 -c 0.5",
                 "setup wirebond -power -r 0.245 -l 1420 -c 5", "setup wirebond -ground -r 0.245 -l 1420 -c 5",
                 "setup package -r 0.001 -l 10 -c 10", ""])
ext = "perform extraction -power -ground -c\n"
open(rh + "/run_static.tcl", "w").write("import gsr rh.gsr\nsetup design\nperform pwrcalc\n" + ext + PKG + "perform analysis -static\nexit\n")
dyn = "import gsr rh.gsr\nsetup design\nperform pwrcalc\n" + ext + PKG + "perform analysis -vectorless\n"
for md in ("AVG", "RMS"):   # default dynamic EM mode is PEAK; snapshot each mode (each emcheck overwrites the previous report)
    dyn += "catch {file copy -force adsRpt/Dynamic/rv32i_cpu_top.em.worst adsRpt/Dynamic/em.worst.%s}\nperform emcheck -mode %s\n" % ("PEAK" if md == "AVG" else "AVG", md)
dyn += "catch {file copy -force adsRpt/Dynamic/rv32i_cpu_top.em.worst adsRpt/Dynamic/em.worst.RMS}\nexit\n"
open(rh + "/run_dynamic.tcl", "w").write(dyn)
# sensitivity arm "no decap": identical, but the intentional decap cells have NO APL cdev (only the std-cell cdev + all current profiles), so RedHawk sees no characterised decap cell
nd = os.path.join(run, "rh_apl_nodecap"); os.makedirs(nd, exist_ok=True)
cap = APL + "/CAP"; capstd = APL + "/CAP_stdonly"
os.makedirs(capstd, exist_ok=True)
for f in sorted(os.listdir(cap)):
    if f.endswith(".cdev") and "decap" not in f and not os.path.lexists(capstd + "/" + f): os.symlink("../CAP/" + f, capstd + "/" + f)
gs = open(rh + "/rh.gsr").read().replace(" %s/CAP cdev\n" % APL, " %s/CAP_stdonly cdev\n" % APL)
assert capstd in gs
open(nd + "/rh.gsr", "w").write(gs)
for fn, tgt in (("run_dynamic.tcl", "../rh_apl/run_dynamic.tcl"), ("pg.ploc", "../rh/pg.ploc"), ("power.ipf", "../rh/power.ipf"), ("custom_pgarc.lib", "../rh/custom_pgarc.lib")):
    if os.path.lexists(nd + "/" + fn): os.remove(nd + "/" + fn)
    os.symlink(tgt, nd + "/" + fn)
# sensitivity "estimated decap": APL for the std cells (as above, no decap cdev) + the b6-era DECAP_CELL spice-W/L ESTIMATE for the decap cells (C = (Wn+Wp) L Cox, R = channel Ron/3).
# Isolates the decap model: same APL std-cell data, same ASSUMED package, same everything else.
ed = os.path.join(run, "rh_apl_estdecap"); os.makedirs(ed, exist_ok=True)
dc = "DECAP_CELL {\n" + "".join(" %s %.2f 2.72 %.5f %.0f met1 0\n" % (n, WID[n], c, r) for n, (c, r, _) in dec.items()) + "}\n"
open(ed + "/rh.gsr", "w").write(gs + dc)
for fn, tgt in (("run_dynamic.tcl", "../rh_apl/run_dynamic.tcl"), ("pg.ploc", "../rh/pg.ploc"), ("power.ipf", "../rh/power.ipf"), ("custom_pgarc.lib", "../rh/custom_pgarc.lib")):
    if os.path.lexists(ed + "/" + fn): os.remove(ed + "/" + fn)
    os.symlink(tgt, ed + "/" + fn)
print("wrote", rh)
