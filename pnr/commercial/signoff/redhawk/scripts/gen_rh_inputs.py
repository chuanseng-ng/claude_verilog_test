#!/usr/bin/env python3
"""gen_rh_inputs.py <arm> -- write runs/<arm>/rh/{rh.gsr,run_static.tcl,run_dynamic.tcl} for one arm.  Paths from signoff/pt/scripts/arms.sh conventions.
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
       "innovusb6": com + "/impl/innovus/runs/b6_innovus/out/rv32i_cpu_top.def"}[arm]
SPEF = com + "/signoff/starrc/runs/%s_nom/rv32i_cpu_top.nom.spef" % arm
run = com + "/signoff/redhawk/runs/" + arm
rh = run + "/rh"; os.makedirs(rh, exist_ok=True)
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
open(rh + "/decap_estimate.txt", "w").write("".join("%s C_pF=%.5f R_ohm=%.0f\n" % (n, c, r) for n, (c, r, _) in dec.items()))
g = []
g.append("TECH_FILE %s/pnr/commercial/pdk/sky130/build/redhawk/sky130A_nom.tech" % root)
g.append("LEF_FILES {\n %s/techlef/sky130_fd_sc_hd__nom.tlef\n %s/lef/sky130_fd_sc_hd.lef\n %s/lef/sky130_ef_sc_hd.lef\n %s/sky130_sram_macros/lef/sky130_sram_1kbyte_1rw1r_32x256_8.lef\n}" % (hd, hd, hd, pdk))
g.append("DEF_FILES {\n %s\n}" % DEF)
# custom lib: PG arcs for the multi-PG-pin cells the Liberty does not describe (fill/ef cells: VPWR-VGND; VPB/VNB are well ties, not supply arcs)
cl = "".join("cell %s {\n    pgarc {\n        VPWR VGND\n    }\n}\n" % c for c in ("sky130_fd_sc_hd__fill_1", "sky130_fd_sc_hd__fill_2", "sky130_fd_sc_hd__fill_4", "sky130_fd_sc_hd__fill_8",
      "sky130_ef_sc_hd__fill_4", "sky130_ef_sc_hd__fill_8", "sky130_ef_sc_hd__fill_12", "sky130_ef_sc_hd__decap_12"))
open(rh + "/custom_pgarc.lib", "w").write(cl)
g.append("LIB_FILES {\n %s/lib/sky130_fd_sc_hd__tt_025C_1v80.lib\n %s/pnr/sky130/cpu/pdk_lib_patched/sky130_sram_1kbyte_1rw1r_32x256_8_TT_1p8V_25C.lib\n %s/custom_pgarc.lib custom\n}" % (hd, root, rh))
g.append("IGNORE_DEF_ERROR 1")
g.append("VDD_NETS {\n VPWR 1.8\n}\nGND_NETS {\n VGND 0\n}")
g.append("PAD_FILES {\n %s/pg.ploc\n}" % rh)
g.append("FREQUENCY 75e6")
g.append("INSTANCE_POWER_FILES {\n %s/power.ipf\n}" % rh)
g.append("STA_FILE {\n rv32i_cpu_top %s/pt/rv32i_cpu_top.timing.gz\n}" % run)
g.append("CELL_RC_FILE {\n EXTRACT_RC 1\n rv32i_cpu_top %s\n}" % SPEF)
g.append("MULTI_THREADS 1 2")
g.append("ENABLE_AUTO_EM 1\nEM_REPORT_PERCENTAGE 50\nEM_REPORT_LINE_NUMBER 100000")
g.append("DECAP_CELL {\n" + "".join(" %s %.2f 2.72 %.5f %.0f met1 0\n" % (n, WID[n], c, r) for n, (c, r, _) in dec.items()) + "}")
g.append("DYNAMIC_SIMULATION_TIME 2.8e-8\nDYNAMIC_TIME_STEP 20e-12")
open(rh + "/rh.gsr", "w").write("\n".join(g) + "\n")
open(rh + "/run_static.tcl", "w").write("import gsr rh.gsr\nsetup design\nperform pwrcalc\nperform extraction -power -ground -c\nperform analysis -static\nexit\n")
dyn = "import gsr rh.gsr\nsetup design\nperform pwrcalc\nperform extraction -power -ground -c\nperform analysis -vectorless\n"
for md in ("AVG", "RMS"):   # default dynamic EM mode is PEAK; snapshot each mode (each emcheck overwrites the previous report)
    dyn += "catch {file copy -force adsRpt/Dynamic/rv32i_cpu_top.em.worst adsRpt/Dynamic/em.worst.%s}\nperform emcheck -mode %s\n" % ("PEAK" if md == "AVG" else "AVG", md)
dyn += "catch {file copy -force adsRpt/Dynamic/rv32i_cpu_top.em.worst adsRpt/Dynamic/em.worst.RMS}\nexit\n"
open(rh + "/run_dynamic.tcl", "w").write(dyn)
# sensitivity arm: identical, but WITHOUT the DECAP_CELL estimate (RedHawk then sees no explicit decap cells beyond what the Liberty/LEF give it)
nd = os.path.join(run, "rh_nodecap"); os.makedirs(nd, exist_ok=True)
gs = open(rh + "/rh.gsr").read()
gs = gs[:gs.index("DECAP_CELL {")] + gs[gs.index("}", gs.index("DECAP_CELL {")) + 1:]
open(nd + "/rh.gsr", "w").write(gs)
for fn in ("pg.ploc", "power.ipf", "custom_pgarc.lib", "run_dynamic.tcl"):
    if os.path.lexists(nd + "/" + fn): os.remove(nd + "/" + fn)
    os.symlink("../rh/" + fn, nd + "/" + fn)
print("wrote", rh)
