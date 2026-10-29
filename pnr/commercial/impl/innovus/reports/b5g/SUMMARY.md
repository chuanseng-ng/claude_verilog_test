# B5g: in-place repair of b5f (Innovus 23.14, Sky130, rv32i_cpu_top, 13.333 ns clk_i)

Start: `runs/b5f_innovus/dbs/05_route` (post-route-opt, PRE-fill; chosen over 06_finish because it avoids trimming fill; fill/decap is re-added by 06_finish). No re-placement, no CTS re-run. b5f is untouched.

## Root cause of the b5f setup failure (axi_rdata_i -> D-cache din0)
The AXI input ports sit on the bottom die edge (e.g. axi_rdata_i[30] at x=2867 um) but their first buffer is at x~600 um: the port nets are 2-6 mm routed, unbuffered
(port slew 3.3 ns, first buf_12 stage 13.45 ns, max_cap -0.593 pF). 28 nets (axi_rdata_i x25, axi_rresp_i x2, axi_rvalid_i) were > 2 mm; list: reports/b5g/g_nets.txt (scripts/b5g_nets.py on the b5f DEF).
post-route optDesign had not buffered them. Not a placement problem.

## Commands that fixed it
1. `05g_repair.tcl`: `ecoAddRepeater -net <port net> -cell sky130_fd_sc_hd__buf_8 -firstSpreadDist 40 -spreadDist 600` on the 28 nets (233 repeaters), `ecoRoute`, `ecoRoute -fix_drc` loop.
   Setup WNS -2.702 -> +0.392 ns. The original met1 short at (8.9, 923) is gone (rerouted). One repeater (B5G16__inst_131, on axi_rdata_i[27]) could not be legalised (IMPSP-2020) and sat on the PG rail: 2 NEW met1 shorts vs VPWR/VGND.
2. `05h_fix.tcl`: `ecoDeleteRepeater -inst B5G16__inst_131`, `ecoRoute`, `ecoRoute -fix_drc` -> verify_drc 0. (Also tried `attachDiode` diode_2 on the 4 antenna-violating clock-tree pins: no effect, the instances are not in the final DEF, antenna unchanged at 4.)
3. `06_finish.tcl` (FROM_LABEL=05h_final): decap + fill, reports, DEF/netlists/GDS; `07_restream.tcl`: re-stream with FIXED map gds_layer_map.innovus + per-net PG connectivity.

## Before / after (Innovus-native, tt, tech-LEF RC, OCV; NOT signoff)
| Metric | b5f | **b5g** |
|---|---|---|
| verify_drc | 1 (met1 short) | **0** |
| verifyConnectivity (regular/special) | 144 IMPVFC-92 + 1 IMPVFC-200 (baseline class, see b5f/b5d) | **unchanged: 144 + 1** (no new opens) |
| verifyProcessAntenna | 5 viol / 4 nets | **4 viol / 3 nets** (clock-tree nets CTS_84, CTS_77, u_core/CTS_77; NOT 0; b5d had 1) |
| PDN self-check pieces VPWR / VGND | 1 / 1 | **1 / 1** (re-run on 05h_final and on 06_finish) |
| Setup WNS / TNS / violators | -2.702 / -31.576 / 21 | **+0.394 ns / 0 / 0** (reg2reg +1.854) |
| Hold WNS / violators | +0.264 / 0 | **+0.252 ns / 0** |
| max_cap / max_tran nets | 457 / 111 | 433 / 100 (still unrepaired: SRAM-pin / output nets) |
| power (default activity) | 91.65 mW | 92.65 mW |
| wirelength | 6,524,044 um | 6,557,473 um |
| total area incl. macros | 2,261,987 | 2,265,508 um2 |
| checkPlace | 5 preplaced out-of-core (SRAMs) | same 5 |

## Files (runs/b5g_innovus/out/) md5
    0376e5f74902464849bb328cc9476089  rv32i_cpu_top.def
    3c8d320e1df88c385b772ce6dd716344  rv32i_cpu_top.nl.v
    b63a3ad986d121ca5ff949bb5d2d932f  rv32i_cpu_top.pg.pnl.v
    2baa2689ff3c2db4069459e334cb8d9d  rv32i_cpu_top.gds
    97ae278d75b2ea41b09dab61bb12151c  rv32i_cpu_top.sdc
    e693931b52180a3654fc0563d1fdb5f0  rv32i_cpu_top.innovus_native.spef

DBs: runs/b5g_innovus/dbs/{05_route,05g_pre_eco_route,05g_eco,05h_pre_route,05h_final,06_finish}.enc. Logs/reports: runs/b5g_innovus/{logs,reports}; tracked copies in pnr/commercial/impl/innovus/reports/b5g/.

## Open items (honest)
- Antenna is 4 (3 clock-tree nets), not 0. Pre-existing class from CTS routing (b5f 5, b5d 1). Not fixed.
- LEC (Conformal), LVS, KLayout/Magic DRC, Quantus/StarRC and signoff STA were NOT re-run on b5g; everything above is Innovus-native. 232 buf_8 repeaters were added, so the netlist differs from b5f/Genus: LEC must be re-run.
- 144 regular "opens" (VPB endcap well-pin class) unchanged from b5d/b5f.
- max_tran/max_cap DRVs remain (433/100 nets), as in every Innovus run.
- Host note: first launch of 05g_repair was killed when its launching Monitor expired (no data lost, b5f untouched); relaunched.
