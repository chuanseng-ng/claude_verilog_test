# Commercial vs open P&R flow comparison, Sky130 `rv32i_cpu_top` (phase B8)

Status: **comparison, indicative, not sign-off** (2026-11-07). No arm meets the sign-off criteria
(setup/hold WNS >= 0 and TNS = 0 at all 9 corners).

Machine-readable source of every number below: `pnr/commercial/compare/comparison.json`, built by
`pnr/commercial/compare/compare.py` from committed files only. Each JSON entry carries `label`
(`judge` / `native` / `signoff` / `derived`) and `source` (repo path). Figures that exist only in
prose carry `kind: "prose"` and a `locator`. The judge corner tables in section 4 are printed from
the JSON. Files that lived only in gitignored run directories were copied once into
`pnr/commercial/compare/snapshot/` by `snapshot_sources.py`. `snapshot/MANIFEST.tsv` records the
origin path and sha256 of each copy.

```
python3 -I pnr/commercial/compare/compare.py            # rebuild comparison.json
python3 -I pnr/commercial/compare/compare.py --check    # fail if stale
python3 -m pytest -q pnr/commercial/compare/test_compare.py
```

> **Read the caveats (section 2) before any number.** StarRC is calibrated to OpenRCX, not to
> silicon. The SRAM Liberty is TT-only at every corner. The three arms use three different
> synthesis netlists. The fixed I/O latency of the iolat and Innovus-own SDCs leaves artefacts at ss/ff
> (removed for iolat by the per-view variant, section 4.2b). The IR figures are indicative.

## 1. Executive summary

Design: the Sky130 CPU hard macro `rv32i_cpu_top` with 10 `sky130_sram_1kbyte_1rw1r_32x256_8`, at
13.333 ns (75 MHz). All arms share the die (3600 x 1800 um), the SRAM placement, the 503 pins, the
PDN pitch, max layer met4 and the CTS cell set. All three P&R flows are judged by **one extractor
(StarRC, tuned ITF) and one STA (PrimeTime / PrimePower X-2025.06)**.

| (judge = StarRC -> PrimeTime; label per row) | OpenROAD/LibreLane B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| Synthesis netlist | Yosys/ABC | DC-NXT v2 (MCMM) | Genus v1 (tt only) |
| P&R views | 9 corners (LibreLane) | MCMM ss/tt/ff | MMMC ss/tt/ff |
| **judge** setup WNS nom_tt, shared SDC (ns) | +3.172 | +3.314 | +2.455 |
| **judge** worst setup WNS over 9 corners, shared SDC (ns) | -4.326 (max_ss) | -2.268 (max_ss) | -3.028 (max_ss) |
| **judge** setup violators summed over 9 corners, shared / iolat | 3,069 / 2,957 | 45 / 5 | 227 / 44 |
| **judge** reg-to-reg setup violators, 9 corners | **2,870** (ss only) | **3** (max_ss) | **0** |
| **judge** reg-to-reg hold violators, 9 corners | 0 | 10 (nom_ff 2, max_ff 8) | **0** |
| **judge** worst hold WNS, iolat SDC (ns) | **+0.212 (clean, 9/9)** | -0.634 (149 viol.) | -1.771 (155 viol.) |
| **judge** per-view iolat SDC (4.2b): I/O + reg-to-reg setup violators / hold violators, 9 corners | 2,290 + 2,870 / **0** | 0 + 3 / 10 (all reg-to-reg) | 891 + 0 / **0** |
| **judge** worst hold WNS, per-view iolat (ns) | **+0.212 (clean, 9/9)** | -0.027 (8 reg-to-reg) | **+0.190 (clean, 9/9)** |
| **judge** own SDC, worst setup / hold (ns) | n/a | -2.268 / -2.412 | **-0.050 / -0.254** (4 / 4 viol.) |
| **judge** PrimePower nom_tt (mW) | 93.1 (clock 42.8) | **70.8** (clock 25.2) | 76.2 (clock 24.1) |
| **judge** max_tran / max_cap pins, nom_tt | 3,613 / 268 | **4** / 159 | 7 / 160 |
| **derived** logical std-cell area (um2) / util | 472,827 / 10.9 % | **357,158 / 8.2 %** | 477,024 / 11.0 % |
| **derived** logical cells / flops / buffers | 42,578 / 5,299 / 16,176 | 40,926 / 5,284 / **8,501** | 45,895 / 5,208 / 16,083 |
| **native** routed wirelength (um) / vias | 5,586,306 / 517,723 | **4,634,225** / 393,701 | 7,342,159 / **362,426** |
| **signoff** KLayout DRC / deck antenna nets | 0 / 116 | 0 / **1** | 0 / 2 |
| **signoff** Netgen LVS (GDS) | 0 errors (LibreLane) | match uniquely | nets/devices equal; top pin match fails (3 `assign` pairs) |
| **signoff** LEC (post-route vs RTL, 4 neg. controls) | **EQUIVALENT** by chain: RTL==sv2v (Formality 6,302 / 0), sv2v==final (Yosys `equiv_induct` 6,156 / 0); Formality 6/6 and Yosys 4/4 controls caught; Formality/Conformal fail on the Yosys leg (unresolved), `reports/lec_openroad.md` | Formality 4/4, 4/4 caught | Conformal 4/4, 4/4 caught |
| **signoff** Magic DRC outside SRAM (all `nwell.4`, LEF-abstract artefact, waiver PROPOSED, caveat 6) | 3,626 | **3,035** (+592 straddle) | 4,226 (+737 straddle) |
| **signoff** RedHawk static worst VDD+VSS (mV) | 24.7 | 23.9 | **18.0** |
| **signoff** RedHawk dynamic worst avgTW (mV) | **79.1** | 192.6 | 163.2 |
| **derived** P&R wall (s) / peak RSS (GB) | 3,249 / not recorded | 4,206 / 4.07 | 3,365 / 7.11 |

What the numbers say:

1. **Reg-to-reg timing.** Both commercial arms remove the ss reg-to-reg loss once ss is an active
   view during optimisation. OpenROAD keeps 987 / 761 / 1,122 reg-to-reg violators at
   nom/min/max_ss (max_ss -4.326 ns). ICC2 b6 keeps 3 (max_ss, -0.059 ns). Innovus b6 keeps 0 at
   all 27 judge runs. The earlier tt-only arms lost 7 to 15 ns at ss (section 5). At tt and ff, all
   three have about +2.5 to +4.3 ns of setup margin.
2. **Hold depends on the I/O latency model, not on the router.** Under the shared SDC, every arm
   fails hold on I/O-port paths at all 9 corners (it has no I/O latency). The fixed-latency iolat SDC
   (1.778 ns for every view) still left ICC2 b6 with 149 and Innovus b6 with 155 hold violators.
   With a **per-view I/O latency** (each arm's own measured clock tree at that corner, sections 4.2b
   and 4.2c), **all 139 + 155 of those I/O hold violators disappear**. They were artefacts of the
   fixed latency (caveat 4). OpenROAD stays hold-clean. The only hold violators left anywhere are
   ICC2's 10 reg-to-reg ones at nom/max_ff (-0.004 / -0.027 ns), which are real.
   The same correction **unmasks I/O setup at ss**: the fixed 1.778 ns launched I/O data 1.3 to 3.9 ns
   earlier than the ss trees, so it hid I/O setup failures. With per-view latency, ICC2 has no I/O
   violator in 9 corners, while OpenROAD (2,290 I/O endpoints) and Innovus b6 (891) fail I/O setup at
   the three ss corners. The diagnostic keeps most of them after removing the intra-macro skew
   (section 4.2d), so they are real for this SDC.
3. **Power and area favour ICC2.** ICC2 b6 uses the least logic (357k um2, half the buffers of the
   others), the shortest wire and the lowest power (70.8 mW). The 22 mW gap to OpenROAD is almost
   all clock network (42.8 vs 25.2 mW). Memory power (29 mW, constant) is the same in every arm.
4. **Physical sign-off.** KLayout DRC is 0 on all three. LVS matches on ICC2. On Innovus the nets
   and devices match but top-level pin matching fails on 3 netlist `assign` pairs. OpenROAD passes
   LibreLane's LVS. Deck antenna is 1 (ICC2), 2 (Innovus) and 116 (OpenROAD, whose LibreLane
   repair left those). The open sign-off deck is clean, but the Magic `nwell.4` items outside the
   SRAMs are a root-caused LEF-abstract artefact with a PROPOSED waiver, not waived (caveat 6).
5. **IR is grid-healthy everywhere but decap-sensitive.** Static drop is 18 to 25 mV
   (VDD+VSS, 1.0 to 1.4 %) on every arm. Dynamic worst-case drop ranks OpenROAD < Innovus < ICC2.
   That ranking follows the estimated decap (ICC2 has 4,210 decap cells against roughly 300k on the
   others). It is not a statement about the grid.

6. **Update 2026-11-09 (b7, b8; section 4.9).** The table above is still b6. Two further generations were built and judged: b7 (ECO pass: ICC2 ff hold, deck antenna, dcache dout0 buffers) and b8 (I-cache SRAMs
   flipped so every dout0 pin faces the channel, plus the b7 ECO set). b8 clears the SRAM dout0 max-cap pins (163 / 161 -> 0 at all 9 corners), the deck antenna (1 / 2 -> 0) and the ICC2 ff hold (10 -> 0) and makes the ICC2
   per-view iolat judge fully clean, but it also regresses a few marginal checks (list in section 4.9), so **b6 stays the final arm**. The sign-off Magic now loads the std cells from the GDS (caveat 6).

## 2. Caveats (apply to every number)

1. **StarRC is calibrated to OpenRCX, not to silicon.** The ITF was authored from the public Sky130
   stack and tuned so that StarRC matches the OpenRCX decks the OpenROAD flow uses. Design total C
   is within 0.7 % (nom), +1.6 % (min) and +1.6 % (max). The per-net total-C median is still
   1.078 / 1.104 / 1.091 (StarRC/OpenRCX), because StarRC extracts about 0.16 fF per pin that
   OpenRCX does not. 45 to 54 % of nets fall outside +-10 %. The R median is 0.958 to 0.987 (JSON
   `extraction_calibration`). The tuned ITF has **no correlation to silicon or to a foundry deck**.
   The TLU+, captbl and RedHawk tech files derived from it carry the same limitation.
2. **The SRAM Liberty is TT 1.8 V 25 C at every corner (bead `o1i`).** The ss and ff runs time the
   10 SRAMs with a TT model. The cache `*_dout_r` and tag paths are therefore optimistic at ss and
   at ff hold, in P&R and in the judge alike.
3. **Different synthesis netlists per arm.** The arms use Yosys/ABC, DC-NXT v2 (MCMM) and Genus v1
   (tt only), so this is **not a single-variable P&R comparison**. The zero-wire PrimeTime probe
   puts the netlists at ss WNS -1.919 (Yosys, 152 violators), +1.163 (DC v2) and +0.606 (Genus v1)
   ns, and at 30,369 / 35,644 / 26,347 leaf cells (`syn/ss_probe/reports/*.tsv`). Part of the ss
   gap between OpenROAD and the commercial arms is already present in the netlist.
4. **A fixed clk_io latency causes ss/ff I/O artefacts. Section 4.2b removes them for the iolat
   variant; the Innovus own SDC is not yet re-run.** The Innovus own SDC (3.295 ns) and the iolat
   SDC (1.778 ns) apply one I/O clock latency to every view. Measured on the judge inputs (StarRC
   SPEFs, PrimeTime, mean over all register clock pins, **network latency = arrival minus the 1.0 ns
   source latency**), the trees are OpenROAD 2.9 / 5.0 / 2.0 ns, ICC2 b6 1.8 / 3.1 / 1.3 ns and
   Innovus b6 3.2 / 5.3 / 2.3 ns at nom tt / ss / ff (section 4.2c, spread over the sinks about 0.4
   ns at ff to 1.4 ns at ss). The earlier text of this caveat quoted 5.66 / 6.66 ns (ss early /
   late), 3.05 ns (tt) and 1.95 ns (ff). Those figures were not measured on the judge inputs and
   mixed arrival with network latency, so they are superseded by the table in 4.2c. Every ss/ff I/O
   setup or hold item on the fixed-latency iolat rows and on the Innovus own row carries that
   modelling error. The shared SDC has no I/O latency at all, which is why all arms show I/O hold
   failures under it.
5. **IR is indicative.** The RedHawk tech is authored and uncorrelated. Cell currents are RedHawk
   defaults (no APL). Decap capacitance is estimated from spice W/L. The supply is an ideal edge
   feed (met5 stripe ends, no package). Power is PrimePower vectorless at 0.1 / 0.5.
6. **Sign-off Magic DRC loads the std cells from the layout GDS (user decision 2026-11-08); the LEF-abstract mode is history.**
   The earlier sign-off mode read the std cells as PDK LEF abstracts, which carry the n-well but no tap contact (`nsc`), so
   every n-well strip outside the SRAMs was reported as `nwell.4` (OpenROAD 3,626; ICC2 b6 3,035 + 592 straddling; Innovus b6
   4,226 + 737 straddling) and the clipped A/B windows also showed LU.2, LU.3 and met1.7 items. With the real std-cell GDS
   (`make ARM=<arm> SRAM_MODE=real MDRC_STD=gds mdrc mdrc-class`, default since 2026-11-08; `MDRC_STD=lef` keeps the old mode) the full-die
   result on the b6, b7 and b8 arms of both commercial tools is **0 items outside or straddling the SRAM footprints** (the OpenROAD B2 run in this mode is NOT RUN: attempt 3 was killed by the memory watchdog at container RSS 10.18 GiB, item 16; its LEF-mode numbers stay as measured): all 30 reported rules sit inside the
   SRAM footprints, `nwell.4`, LU.2, LU.3, `met1.7` and `can't overlap` have 0 items anywhere. The four proposed waivers W1 to W4
   in `reports/magic_nwell4_rootcause.md` are **WITHDRAWN by the user** (not needed). The inside-SRAM items stay under the bead `45a`
   SRAM-abstract waiver; the new inside counts are 27,733,502 (ICC2 b6 and b7), 28,315,303 (Innovus b6 and b7), 27,731,549 (ICC2 b8) and 28,317,685 (Innovus b8; the flipped macros tile differently), against 27,733,486 and
   28,315,092 in LEF mode. The +16 (ICC2) and +211 (Innovus) come from four rules that are all inside the SRAM footprints: `licon.5a` +8,
   `licon.5c` +4, `poly.8` +4 (both arms) and `poly.7` +195 (Innovus only). Measured for `poly.7`: the 195 LEF-mode boxes (y 860.525 to 860.655
   um, D-cache SRAMs, x 238 to 2201 um) are each reported as two boxes in GDS mode (split at y 860.645 um), so it is the same SRAM-internal
   geometry counted in more tiles, not new defects (the +8 / +4 / +4 were not inspected; same class, inferred). No change is a layout defect. The
   LEF-mode figures stay in the JSON as `magic_lef_*` and the per-rule dictionary as `magic_drc_by_rule`.
7. One run per arm. Native tool numbers use each tool's own RC, SDC and engine, so they are not
   ranked against each other. Runtimes were measured on a shared 8-core / 15 GB host, often under
   load, so they are not a tool-speed benchmark.

8. **Innovus b7 and b8 skip `verifyConnectivity -type all`.** On the b7 database (after `ecoAddRepeater`) this check ran for more than an hour
   (b6: 6 s) in two attempts, so `06m_finish.tcl` skips it when `TAG` is `b7_innovus` or `b8_innovus` (or `SKIP_VC=1`). Connectivity of
   those arms rests on the `verify_connectivity -type special` PDN check (still run) and on Netgen LVS (nets and devices equal); the cause of the
   hang is not understood. b6 and the ICC2 arms ran the full check.

## 3. Method and fairness rules

- **Same inputs.** The floorplan, SRAM placement (`pnr/sky130/cpu/macro_placement.cfg`), pins
  (`pin_template.def`), PDN, max layer met4 and CTS cells clkbuf_2/4/8/16 are the same for every
  arm (`reports/icc2_pnr_summary.md`, `reports/innovus_b6_report.md` section 2). The RTL is the
  same 28 SV files with `SRAM_SKY130`.
- **One judge extractor and one judge STA.** StarRC (tuned ITF, `COUPLING_ABS_THRESHOLD 0.1`,
  `LEF_USE_OBS NO`) produces nom/min/max SPEF from each arm's final DEF. PrimeTime X-2025.06 then
  times 9 corners ({nom,min,max} RC x {tt,ss,ff} lib), SI off. PrimePower runs at nom_tt with
  vectorless variant B (0.1 toggle / 0.5 static probability on primary inputs and every register
  output). An annotation gate shows 0 unannotated pin-to-pin nets in every run.
- **SDC variants** (md5 from JSON `sdc`):

  | variant | file | md5 |
  |---|---|---|
  | base (shared) | `pnr/sky130/cpu/constraints/sky130_cpu.sdc` | `3c69635042a9d65cb87e71a9db713e4e` |
  | iolat (comparison only) | `pnr/commercial/constraints/sky130_cpu_iolat.sdc` | `e90bdba8b93f8f4e985c5fbaa6d4ab90` |
  | iolat_pv (per-view, comparison only) | `pnr/commercial/constraints/sky130_cpu_iolat_pv.sdc` | `57e67934c24b53f40489ad30eeb3c1cf` |
  | own, ICC2 b6 (func_tt write_sdc) | `pnr/commercial/constraints/sky130_cpu_icc2_b6_own_pt.sdc` | `44ce62ce6e6075a2110cd5f62a5b4100` |
  | own, Innovus b6 | `pnr/commercial/constraints/sky130_cpu_innovus_b6_own_pt.sdc` | `99df2bf2e7b03449bfad4cd01e1c9936` |
  | own, Innovus b5k | `.../sky130_cpu_innovus_b5k_own_pt.sdc` | `4518e91562d3e0ced3bffaeef7ca9cba` |
  | own, Innovus b5h/b5j | `.../sky130_cpu_innovus_b5h_own_pt.sdc` | `23e90b26751c7f1405b17d9ee427f366` |

  compare.py checks the `sdc_md5` recorded in every judge run against these files. All runs
  agree (JSON `warnings` is empty). OpenROAD has no own variant: it writes no SDC of its own, and
  its native STA uses the base file.
- **Uniform census** (`derived`). Each arm's cell list (the ICC2/Innovus `final_cellcount`, and
  the OpenROAD post-route netlist) is classified by one rule. Logical cells are all standard cells
  except tap/fill/decap/diode/SRAM. Flops are `df*`/`edf*`/`sdf*`/`dl[xr]*`. Buffers are
  buf/bufbuf/clkbuf/clkdlybuf/dlygate/dlymetal. Area is count x LEF `SIZE`. Utilisation is that
  area / (OpenROAD core area 6,254,430 um2 - SRAM area 1,907,130 um2). Every arm uses the same
  denominator because the floorplan is identical. Native utilisation figures use incompatible
  definitions (OpenROAD (std + macro) / core 41.8 %, ICC2 site-row 8.28 %, Innovus density
  22.4 %). The JSON keeps them, labelled.
- **Sign-off decks** run identically on every GDS/DEF: KLayout `sky130A_mr.drc`, Magic (real SRAM
  mode, items classified inside / straddling / outside the SRAM footprints), Netgen LVS on a
  GDS-mode Magic extraction, and OpenROAD `check_antennas` as the deck antenna rule. LEC uses
  Formality for the DC/ICC2 netlists and Conformal for the Genus/Innovus netlists. Each runs 4
  compares (RTL and synthesis goldens, with and without antenna diodes) plus 4 mutant negative
  controls (`fwdb_inv`, `swap`, against both goldens).

## 4. Final arms: judge results per corner

Each cell is `setup WNS / TNS / violators ; hold WNS / TNS / violators` (ns). Violators are
violating endpoints. Source: `judge.<arm>.<variant>.corners.<corner>` in the JSON, which points to
`compare/snapshot/pt/<variant>/<arm>_<corner>/metrics.tsv`.

### 4.1 Shared SDC (base)

| corner | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| nom_tt | +3.172 / 0.00 / 0 ; -0.319 / -3.50 / 51 | +3.314 / 0.00 / 0 ; -1.230 / -240.58 / 556 | +2.455 / 0.00 / 0 ; -1.929 / -218.17 / 455 |
| nom_ss | -3.426 / -1221.52 / 1062 ; -0.800 / -25.60 / 121 | -1.594 / -7.27 / 12 ; -2.234 / -541.68 / 577 | -1.993 / -70.72 / 71 ; -3.182 / -453.08 / 472 |
| nom_ff | +3.928 / 0.00 / 0 ; -0.136 / -0.48 / 8 | +4.015 / 0.00 / 0 ; -0.780 / -109.28 / 374 | +4.131 / 0.00 / 0 ; -1.323 / -111.97 / 356 |
| min_tt | +3.548 / 0.00 / 0 ; -0.174 / -0.48 / 5 | +3.505 / 0.00 / 0 ; -1.145 / -212.83 / 544 | +2.992 / 0.00 / 0 ; -1.732 / -183.36 / 422 |
| min_ss | -2.777 / -776.62 / 800 ; -0.588 / -7.43 / 78 | -1.079 / -3.15 / 7 ; -2.107 / -502.86 / 571 | -1.253 / -34.71 / 49 ; -2.899 / -403.62 / 449 |
| min_ff | +4.066 / 0.00 / 0 ; -0.015 / -0.04 / 3 | +4.165 / 0.00 / 0 ; -0.722 / -96.88 / 325 | +4.277 / 0.00 / 0 ; -1.168 / -88.96 / 308 |
| max_tt | +2.679 / 0.00 / 0 ; -0.522 / -21.81 / 169 | +3.028 / 0.00 / 0 ; -1.345 / -278.22 / 570 | +1.686 / 0.00 / 0 ; -2.193 / -265.11 / 504 |
| max_ss | -4.326 / -1948.46 / 1207 ; -1.071 / -55.27 / 155 | -2.268 / -16.85 / 26 ; -2.412 / -599.32 / 586 | -3.028 / -140.75 / 107 ; -3.549 / -518.42 / 488 |
| max_ff | +3.713 / 0.00 / 0 ; -0.307 / -3.30 / 43 | +3.774 / 0.00 / 0 ; -0.865 / -130.99 / 441 | +3.536 / 0.00 / 0 ; -1.534 / -143.09 / 419 |

Reg-to-reg violators (setup / hold): OpenROAD has 987 / 761 / 1,122 setup at nom/min/max_ss and
none elsewhere. ICC2 b6 has 3 setup at max_ss (-0.059 ns) and 2 / 8 hold at nom/max_ff (-0.004 /
-0.027 ns). Innovus b6 has none at any corner. Every hold violation in this table is an I/O path,
except ICC2's 10 ff reg-to-reg (`report_global_timing` split, JSON `io_split`).

### 4.2 iolat SDC (virtual I/O clock, comparison only)

| corner | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| nom_tt | +3.123 / 0.00 / 0 ; +0.526 / 0.00 / 0 | +3.314 / 0.00 / 0 ; +0.114 / 0.00 / 0 | +3.628 / 0.00 / 0 ; -0.151 / -0.36 / 3 |
| nom_ss | -3.426 / -1192.96 / 1014 ; +0.978 / 0.00 / 0 | +0.184 / 0.00 / 0 ; -0.456 / -10.22 / 42 | -0.215 / -0.53 / 4 ; -1.404 / -16.55 / 39 |
| nom_ff | +3.928 / 0.00 / 0 ; +0.243 / 0.00 / 0 | +4.015 / 0.00 / 0 ; -0.004 / -0.01 / 2 | +4.131 / 0.00 / 0 ; +0.197 / 0.00 / 0 |
| min_tt | +3.186 / 0.00 / 0 ; +0.542 / 0.00 / 0 | +3.505 / 0.00 / 0 ; +0.115 / 0.00 / 0 | +3.772 / 0.00 / 0 ; +0.046 / 0.00 / 0 |
| min_ss | -2.777 / -774.75 / 788 ; +1.190 / 0.00 / 0 | +0.699 / 0.00 / 0 ; -0.329 / -6.14 / 31 | +0.525 / 0.00 / 0 ; -1.121 / -10.36 / 29 |
| min_ff | +4.066 / 0.00 / 0 ; +0.250 / 0.00 / 0 | +4.165 / 0.00 / 0 ; +0.003 / 0.00 / 0 | +4.277 / 0.00 / 0 ; +0.190 / 0.00 / 0 |
| max_tt | +3.019 / 0.00 / 0 ; +0.495 / 0.00 / 0 | +3.028 / 0.00 / 0 ; +0.112 / 0.00 / 0 | +3.439 / 0.00 / 0 ; -0.415 / -1.19 / 6 |
| max_ss | -4.326 / -1880.28 / 1155 ; +0.707 / 0.00 / 0 | -0.490 / -0.61 / 5 ; -0.634 / -18.72 / 66 | -1.250 / -23.49 / 40 ; -1.771 / -31.26 / 78 |
| max_ff | +3.713 / 0.00 / 0 ; +0.212 / 0.00 / 0 | +3.774 / 0.00 / 0 ; -0.027 / -0.07 / 8 | +3.927 / 0.00 / 0 ; +0.202 / 0.00 / 0 |

### 4.2b Per-view iolat SDC (clk_io latency = each arm's own tree at that corner)

`sky130_cpu_iolat_pv.sdc` is the iolat SDC with one change: the virtual clock `clk_io` takes its
early and late latency (1.0 ns source latency + the table value) from a per-arm, per-corner table
(`signoff/pt/iolat_pv/iolat_pv_arm.tsv`) read when the SDC is read. **One SDC file, one md5
(`57e67934...`), identical for every arm and corner**, and the old iolat SDC is untouched. The
table is the mean network latency of `clk_i` over all register clock pins, measured in PrimeTime on
the same netlist and StarRC SPEF as the judge run (section 4.2c). Same netlists, SPEFs, judge
script and settings as sections 4.1 to 4.3. Source: `judge.<arm>.iolat_pv.corners.<corner>`.

| corner | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| nom_tt | +2.002 / 0.00 / 0 ; +0.526 / 0.00 / 0 | +3.314 / 0.00 / 0 ; +0.114 / 0.00 / 0 | +2.948 / 0.00 / 0 ; +0.411 / 0.00 / 0 |
| nom_ss | -4.543 / -2080.20 / 1769 ; +1.345 / 0.00 / 0 | +0.417 / 0.00 / 0 ; +0.453 / 0.00 / 0 | -1.788 / -154.58 / 282 ; +0.998 / 0.00 / 0 |
| nom_ff | +3.928 / 0.00 / 0 ; +0.243 / 0.00 / 0 | +4.015 / 0.00 / 0 ; -0.004 / -0.01 / 2 | +4.131 / 0.00 / 0 ; +0.197 / 0.00 / 0 |
| min_tt | +2.233 / 0.00 / 0 ; +0.542 / 0.00 / 0 | +3.505 / 0.00 / 0 ; +0.115 / 0.00 / 0 | +3.294 / 0.00 / 0 ; +0.401 / 0.00 / 0 |
| min_ss | -4.153 / -1405.97 / 1435 ; +1.335 / 0.00 / 0 | +0.715 / 0.00 / 0 ; +0.453 / 0.00 / 0 | -1.391 / -52.79 / 105 ; +0.989 / 0.00 / 0 |
| min_ff | +4.066 / 0.00 / 0 ; +0.250 / 0.00 / 0 | +4.165 / 0.00 / 0 ; +0.003 / 0.00 / 0 | +4.277 / 0.00 / 0 ; +0.190 / 0.00 / 0 |
| max_tt | +1.669 / 0.00 / 0 ; +0.495 / 0.00 / 0 | +3.028 / 0.00 / 0 ; +0.112 / 0.00 / 0 | +2.420 / 0.00 / 0 ; +0.416 / 0.00 / 0 |
| max_ss | -5.057 / -3166.75 / 1956 ; +1.306 / 0.00 / 0 | -0.059 / -0.12 / 3 ; +0.452 / 0.00 / 0 | -2.435 / -458.57 / 504 ; +1.017 / 0.00 / 0 |
| max_ff | +3.713 / 0.00 / 0 ; +0.212 / 0.00 / 0 | +3.774 / 0.00 / 0 ; -0.027 / -0.07 / 8 | +3.927 / 0.00 / 0 ; +0.202 / 0.00 / 0 |

Violators summed over the 9 corners (violating endpoints; I/O = total minus the reg-to-reg
`-from` register clock pins `-to` register data pins count, JSON `r2r_*_viol_sum`):

| | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| setup, fixed iolat (I/O / reg-to-reg) | 87 / 2,870 | 2 / 3 | 44 / 0 |
| setup, **per-view iolat** | 2,290 / 2,870 | **0** / 3 | 891 / 0 |
| setup, shared latency per corner (4.2e) | 1,757 / 2,870 | 105 / 3 | 327 / 0 |
| hold, fixed iolat | 0 / 0 | 139 / 10 | 155 / 0 |
| hold, **per-view iolat** | 0 / 0 | **0** / 10 | **0** / 0 |
| hold, shared latency per corner (4.2e) | 0 / 0 | 1 / 10 | 0 / 0 |

PrimePower at nom_tt does not change: 93.1 / 70.8 / 76.2 mW (fixed iolat, per-view and shared
variants identical to the printed digits, `power_B.txt` of each run).

### 4.2c Measured `clk_i` insertion latency (network latency, ns)

Method: PrimeTime X-2025.06 on the base SDC (md5 `3c696350...`), `clk_i` propagated, no derate,
SI off, the judge's own SPEF copy (md5 checked against the judge run and against the StarRC
output) and netlist, 0 unannotated clock nets. Script `signoff/pt/scripts/measure_clk_latency.tcl`:
for every register clock pin (flops and the 20 SRAM macros, 5,300 pins per arm) it reads the
rising-edge arrival (`min_/max_rise_arrival`, which is what a path report prints as capture clock
arrival) and subtracts the 1.0 ns source latency. At every pin early and late agree to
under 0.5 ps (no OCV), so "early / late" of the tree means the sink-to-sink spread, shown
below as min..max. The table value is the mean. The mean over only the registers that capture
input-port paths or launch output-port paths differs from the all-register mean by 0.01 to 0.07 ns.

| corner | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| nom_tt | 2.900 (2.47..3.13) | 1.819 (1.32..2.08) | 3.177 (3.02..3.30) |
| nom_ss | 5.035 (4.21..5.41) | 3.080 (2.22..3.53) | 5.261 (4.97..5.44) |
| nom_ff | 2.002 (1.77..2.17) | 1.263 (0.91..1.44) | 2.273 (2.16..2.37) |
| min_tt | 2.731 (2.33..2.93) | 1.725 (1.24..1.96) | 2.959 (2.79..3.06) |
| min_ss | 4.761 (4.03..5.08) | 2.938 (2.10..3.34) | 4.946 (4.65..5.10) |
| min_ff | 1.881 (1.66..2.02) | 1.198 (0.86..1.35) | 2.098 (1.98..2.18) |
| max_tt | 3.128 (2.65..3.41) | 1.943 (1.41..2.23) | 3.469 (3.32..3.62) |
| max_ss | 5.378 (4.45..5.82) | 3.277 (2.37..3.78) | 5.679 (5.39..5.89) |
| max_ff | 2.159 (1.91..2.39) | 1.355 (0.99..1.56) | 2.506 (2.40..2.62) |

Values are `mean (min..max over sinks)`. Source: `clock_latency.measured.<arm>.<corner>` in the
JSON.

### 4.2d What is artefact and what is real

`signoff/pt/scripts/diag_io_viol.tcl` lists every violating I/O endpoint (worst path per
endpoint) of the per-view runs, and recomputes its slack as if `clk_io` arrived exactly when the
clock reaches the macro register on the other end of that path. If that slack is >= 0, the
violation exists only because the external clock is modelled at the tree mean while this register
sits at the early or late end of the tree (**skew-limited**). If it is < 0, the port-to-register
path itself is too slow or too fast (**real** for this SDC). Counts below are per-view
endpoints with an input as worst startpoint (JSON `clock_latency.io_violators`).

| | fixed iolat | per-view iolat | verdict |
|---|---|---|---|
| ICC2 b6 ss hold (42 / 31 / 66) | 139 I/O violators | **0** (hold +0.45 ns at all three ss) | **artefact, does not survive** |
| ICC2 b6 max_ss setup I/O (2) | 2 | 0 (3 left are reg-to-reg) | artefact |
| ICC2 b6 ff hold (nom 2, max 8) | 10 reg-to-reg | 10 reg-to-reg | **real** (not an I/O path, latency-independent) |
| ICC2 b6 max_ss setup reg-to-reg (3) | 3 | 3 | real |
| Innovus b6 hold (nom_tt 3, ss 39 / 29 / 78, max_tt 6) | 155 | **0** | **artefact** |
| Innovus b6 ss I/O setup | 4 / 0 / 40 (nom / min / max_ss) | 282 / 105 / 504 | **real**: 94 of 891 are skew-limited, 797 survive alignment (worst -2.44 ns, starts `apb_paddr_i`, `axi_rlast_i`) |
| OpenROAD ss I/O setup | 27 / 27 / 33 (nom / min / max_ss) | 782 / 674 / 834 (total minus reg-to-reg; 847 / 738 / 907 endpoints have an input as worst startpoint) | **real**: 125 of those 2,492 are skew-limited (starts `axi_rvalid_i`, `axi_bvalid_i`, `apb_paddr_i`, `axi_rlast_i`) |

Why the I/O setup grows at ss: with the fixed 1.778 ns the I/O data launched 1.3 to 3.9 ns before
the ss tree, which is optimistic for setup. Aligning the launch to the tree shows high-fanout
control inputs (`axi_rlast_i`, `axi_rvalid_i`, `axi_bvalid_i`, `apb_paddr_i`) reaching hundreds of
flops through slow ss logic, more than the 13.333 ns period minus the 2.0 / 3.5 ns input delay.
The reg-to-reg ss violators of OpenROAD (987 / 761 / 1,122) are unchanged. The SRAM Liberty is
TT-only (caveat 2), so none of the ss figures is a silicon claim.

### 4.2e Shared latency per corner (sensitivity)

Same SDC and judge; the table `iolat_pv_shared.tsv` has ONE value per corner (the mean of the
three arms' values), the same for every arm. Per-arm is the recommended judge: SoC clock-tree
synthesis balances the clock to the macro's insertion delay, so the external registers follow the
macro's own tree, and the trees differ by up to 2.4 ns (ICC2 vs Innovus at max_ss). A shared value
credits deep-tree arms and charges shallow ones: ICC2 b6 gets 105 **extra** I/O setup violators
(all 105 skew-limited, i.e. artefacts of the later shared clock) and one extra hold violator,
while OpenROAD (5,160 -> 4,627) and Innovus (891 -> 327) lose violators because the shared value is
shallower than their trees. The 327 Innovus ones are all real after alignment. Full table:

| corner | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| nom_tt | +2.269 / 0.00 / 0 ; +0.526 / 0.00 / 0 | +3.314 / 0.00 / 0 ; +0.114 / 0.00 / 0 | +3.493 / 0.00 / 0 ; +0.411 / 0.00 / 0 |
| nom_ss | -3.967 / -1656.21 / 1529 ; +1.345 / 0.00 / 0 | -0.720 / -12.83 / 34 ; +0.047 / 0.00 / 0 | -0.986 / -27.00 / 69 ; +0.998 / 0.00 / 0 |
| nom_ff | +3.928 / 0.00 / 0 ; +0.243 / 0.00 / 0 | +4.015 / 0.00 / 0 ; -0.004 / -0.01 / 2 | +4.131 / 0.00 / 0 ; +0.197 / 0.00 / 0 |
| min_tt | +2.492 / 0.00 / 0 ; +0.542 / 0.00 / 0 | +3.505 / 0.00 / 0 ; +0.115 / 0.00 / 0 | +3.772 / 0.00 / 0 ; +0.401 / 0.00 / 0 |
| min_ss | -3.608 / -1079.08 / 1228 ; +1.335 / 0.00 / 0 | -0.376 / -3.62 / 18 ; +0.148 / 0.00 / 0 | -0.660 / -10.56 / 30 ; +0.989 / 0.00 / 0 |
| min_ff | +4.066 / 0.00 / 0 ; +0.250 / 0.00 / 0 | +4.165 / 0.00 / 0 ; +0.003 / 0.00 / 0 | +4.277 / 0.00 / 0 ; +0.190 / 0.00 / 0 |
| max_tt | +1.950 / 0.00 / 0 ; +0.495 / 0.00 / 0 | +3.028 / 0.00 / 0 ; +0.112 / 0.00 / 0 | +3.043 / 0.00 / 0 ; +0.416 / 0.00 / 0 |
| max_ss | -4.457 / -2644.44 / 1870 ; +1.306 / 0.00 / 0 | -1.163 / -34.87 / 56 ; -0.078 / -0.08 / 1 | -1.533 / -115.73 / 228 ; +1.017 / 0.00 / 0 |
| max_ff | +3.713 / 0.00 / 0 ; +0.212 / 0.00 / 0 | +3.774 / 0.00 / 0 ; -0.027 / -0.07 / 8 | +3.927 / 0.00 / 0 ; +0.202 / 0.00 / 0 |

### 4.3 Own SDC (what each commercial tool closed against)

| corner | ICC2 b6 (= base: its written SDC carries no I/O latency) | Innovus b6 |
|---|---|---|
| nom_tt | +3.314 / 0.00 / 0 ; -1.230 / -240.58 / 556 | +2.830 / 0.00 / 0 ; +0.411 / 0.00 / 0 |
| nom_ss | -1.594 / -7.27 / 12 ; -2.234 / -541.68 / 577 | +0.177 / 0.00 / 0 ; +0.113 / 0.00 / 0 |
| nom_ff | +4.015 / 0.00 / 0 ; -0.780 / -109.28 / 374 | +3.830 / 0.00 / 0 ; +0.197 / 0.00 / 0 |
| min_tt | +3.505 / 0.00 / 0 ; -1.145 / -212.83 / 544 | +2.958 / 0.00 / 0 ; +0.401 / 0.00 / 0 |
| min_ss | -1.079 / -3.15 / 7 ; -2.107 / -502.86 / 571 | +0.260 / 0.00 / 0 ; +0.396 / 0.00 / 0 |
| min_ff | +4.165 / 0.00 / 0 ; -0.722 / -96.88 / 325 | +3.947 / 0.00 / 0 ; -0.007 / -0.01 / 1 |
| max_tt | +3.028 / 0.00 / 0 ; -1.345 / -278.22 / 570 | +2.594 / 0.00 / 0 ; +0.416 / 0.00 / 0 |
| max_ss | -2.268 / -16.85 / 26 ; -2.412 / -599.32 / 586 | -0.050 / -0.09 / 4 ; -0.254 / -0.61 / 3 |
| max_ff | +3.774 / 0.00 / 0 ; -0.865 / -130.99 / 441 | +3.630 / 0.00 / 0 ; +0.202 / 0.00 / 0 |

Its fixed 3.295 ns clk_io is close to the measured tt tree (3.1 to 3.5 ns) but not to ss (5.2 to 5.7 ns) or ff (2.3 to 2.5 ns), so its ss/ff I/O items (max_ss setup and hold, min_ff hold) carry the caveat 4 error. A per-view own SDC was not run.
Innovus b6 against its own SDC is the closest any arm comes to sign-off. 3 of its 18 corner checks
fail (max_ss setup, max_ss hold, min_ff hold), with 8 violating endpoints in total. All are I/O
paths and none is reg-to-reg.

### 4.4 Power (PrimePower, nom_tt, vectorless variant B, mW, judge)

| | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| total | 93.1 | 70.8 | 76.2 |
| clock network | 42.8 | 25.2 | 24.1 |
| combinational | 18.3 | 14.3 | 21.3 |
| register | 2.9 | 2.3 | 1.8 |
| memory (10 SRAM) | 29.1 | 29.0 | 29.0 |

### 4.5 Native tool view (own RC, own SDC; not ranked across tools)

| native | OpenROAD B2 (OpenSTA + OpenRCX) | ICC2 b6 (report_qor, TLU+) | Innovus b6 (timeDesign, captbl6, SI on) |
|---|---|---|---|
| setup WNS | nom_tt +3.031; worst over 9 corners -3.996 (2,785 viol., 2,578 r2r) | func_ss -0.02 (3, TNS -0.04); func_tt +3.34 | all views -0.683 (30; r2r -0.089, 3); SI off -0.514 (5, r2r 0) |
| hold WNS | nom_tt -0.458 (156); worst -1.296 (1,038, 0 r2r) | func_ff 0.00 (0); func_tt +0.11 | +0.145 (0); SI off +0.197 |
| route DRC | 0 | 0 (shorts 0, opens 0) | 0 |
| native antenna | (deck: 116 nets) | 0 (lenient ICC2 rule) | 0 (verifyProcessAntenna, no side area) |
| DRV | nom_tt max_slew 3,437 / max_cap 270 / max_fanout 3,670 pins | max_tran 114 / max_cap 160 nets | max_cap 369 / max_tran 41 / max_fanout 209 nets |
| power (mW) | 103.43 (OpenSTA, default activity) | 58.0 (func_tt) | 69.07 (av_ss view, activity 0.1; not comparable) |
| std-cell area (tool definition, um2) | 707,819 (incl. tap/decap/diode) | 359,059 (comb + noncomb) | 2,384,855 incl. SRAM (report_area) |
| util (tool definition) | 41.8 % (std + macro) / 16.3 % std | 8.28 % site-row | 22.4 % density |
| IR (native) | PSM worst VPWR drop 1.43 mV | not run | not run |

The judge does not reproduce the native numbers exactly. It uses StarRC instead of each tool's RC,
the shared or iolat SDC instead of each tool's own SDC, and SI off. Section 5 of
`reports/pt_judge_summary.md` and `reports/innovus_b6_report.md` section 5 explain the offsets
(for example, a native-to-PT ff hold offset of about 0.15 to 0.2 ns on Innovus).

### 4.6 Physical and sign-off detail

| | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| logical cells / flops / buffers / inverters (derived) | 42,578 / 5,299 / 16,176 / 958 | 40,926 / 5,284 / 8,501 / 5,659 | 45,895 / 5,208 / 16,083 / 5,469 |
| buffer area (um2, derived) | 157,011 | 71,933 | 139,938 |
| antenna diodes in netlist | 64,086 | 760 | 282 |
| KLayout DRC (items) | 0 | 0 | 0 |
| Netgen LVS, layout / schematic nets | 0 errors (LibreLane, DEF/LEF mode) | 41,741 / 41,741, match uniquely (as delivered, clean, merged) | 47,113 / 47,113, devices 46,175 = 46,175; top-level pin matching fails on `axi_awlen_o[1]`, `axi_arlen_o[1]`, `axi_arburst_o[0]` (`assign` pairs) and the layout-only VPWR/VGND labels |
| deck antenna nets / pins | 116 / 119 | 1 / 1 | 2 / 2 |
| Magic total / inside SRAM | 27,733,913 / 27,730,287 | 27,737,113 / 27,733,486 | 28,320,055 / 28,315,092 |
| Magic straddle / outside (all `nwell.4`; LEF-abstract artefact, 0 n-well regions without tap contact in the real GDS; waiver PROPOSED, not waived) | 0 / 3,626 | 592 / 3,035 | 737 / 4,226 |
| LEC post-route | **EQUIVALENT** by chain: RTL==sv2v SUCCEEDED (Formality 6,302 / 0); sv2v==final netlist (Yosys `equiv_induct`, 6,156 proven / 0 unproven, 4/4 controls); final==Yosys netlist SUCCEEDED (Formality 6,248 / 0, with and without 64,086 diodes); Formality (3,902 failing) and Conformal (NOT_EQUIVALENT) fail on the Yosys-netlist-vs-sv2v compare, unresolved | Formality: 4/4 SUCCEEDED, 6,233 passing / 0 failing; controls `fwdb_inv` 1 and `swap` 43 failing points (4/4 caught) | Conformal: 4/4 EQUIVALENT, 5,597 (Genus golden) / 5,791 (RTL golden, merged points) compare points; 4/4 controls NOT_EQUIVALENT |
| LEC synthesis netlist vs RTL | not run | Formality DC v2: SUCCEEDED, 6,233 / 0 | Conformal Genus v1 (hierarchical): EQUIVALENT, 1,076 points |
| RedHawk static VPWR / VGND worst (mV) | 12.4 / 12.3 | 12.1 / 11.8 | 9.0 / 9.0 |
| RedHawk static EM violations | 0 | 0 | 0 |
| RedHawk dynamic worst avgTW / minWC / mean avgTW (mV) | 79.1 / 123.8 / 40.7 | 192.6 / 208.0 / 59.9 | 163.2 / 171.8 / 22.1 |
| RedHawk dynamic, instances above 5 % VDD | 0 % | 19.9 % | 0.04 % |
| RedHawk dynamic with no decap, worst avgTW (mV) | 209.7 | 193.4 | 248.6 |
| decap instances seen by RedHawk | 307,531 | 4,210 | 357,658 |

### 4.7 Run cost (derived from `/usr/bin/time` and LibreLane `runtime.txt`)

| | OpenROAD B2 | ICC2 b6 | Innovus b6 |
|---|---|---|---|
| synthesis wall | 89 s (Yosys step) | 333.6 s (DC compile wall, host contended; prose) | 704 s session (prose) |
| synthesis peak RSS | not recorded | 1.55 GB (prose) | 2.03 GB (prose) |
| P&R wall | 3,249 s (steps 13..74, excl. sign-off decks) | 4,206 s (stages 01..08, incl. 3 ECO passes) | 3,365 s (stages 01..07 of the final chain) |
| P&R peak RSS | not recorded | 4.07 GB (CTS) | 7.11 GB (finish) |
| full LibreLane flow incl. sign-off | 4,468 s | n/a | n/a |
| judge PT run at nom_tt, incl. PrimePower | 17 s to 55 s typical; outliers up to 19:57 under host load (`snapshot/pt/*/*_nom_tt/time.txt`) | same | same |

### 4.8 Quantus cross-check of the StarRC judge (nom, min, max)

Cadence Quantus 23.1.1 with a qrcTechFile built by Techgen from the same authored ICT was run on the three b6 DEFs and compared per net with the
StarRC SPEFs the judge read (JSON `quantus_crosscheck`; full method, gotchas and tables in `pnr/commercial/reports/quantus_crosscheck.md`).
Both extractors read the same authored stack, so this checks engine agreement, not silicon.

| Arm | Total C median error | Total C p95 abs error | Total R median error | Total R p95 abs error | Design C ratio (Quantus/StarRC) |
|---|---:|---:|---:|---:|---:|
| ICC2 b6 | -3.12 % | 9.75 % | +1.53 % | 2.59 % | 0.963 |
| Innovus b6 | +2.10 % | 19.59 % | +1.34 % | 4.98 % | 1.019 |
| OpenROAD | -2.33 % | 12.68 % | +1.60 % | 3.08 % | 0.986 |

min / max corners (total C median, p95 abs; total R median, p95 abs):
ICC2 b6 -3.11 % / 9.39 %, +2.71 % / 5.89 % and -3.13 % / 9.96 %, +0.81 % / 1.26 %;
Innovus b6 +2.02 % / 19.13 %, +2.05 % / 7.53 % and +1.69 % / 19.19 %, +0.78 % / 4.10 %;
OpenROAD -2.23 % / 12.03 %, +2.93 % / 7.07 % and -2.39 % / 13.16 %, +0.80 % / 1.54 %.
So the corner dependence is small and the Innovus/OpenROAD total-C tail is the same at every corner.

Median total C and R are inside the plan's +-10 % gate for all three arms. The total-C tail is beyond +-10 % at p95 for Innovus and OpenROAD
(label: tail indicative). Ground C alone differs by 12 to 19 % median because the tools split ground and coupling differently; total C does not.
**Judge sensitivity (PrimeTime nom_tt, base SDC, Quantus SPEF instead of StarRC SPEF, same netlist):** setup WNS +18 to +66 ps, hold WNS +2 to +43 ps,
power at most 0.7 %, no verdict or ranking change. Quantus takes about 2.5 min and 1.0 to 1.2 GB per extraction.
The nom qrcTechFile comes from the 2026-10 Techgen cell-level run plus `Techgen -migrate`. min and max are fresh `Techgen -cell` runs
(`run_techgen_cell.sh`, 2 CPUs): 3 h 19 min / 440 MB and 3 h 17 min / 445 MB session RSS. Quantus extraction took 1 to 9 min and 1.0 to 1.25 GB per run (nine runs, 0 errors).

### 4.9 Generations b6, b7, b8 of the two commercial arms (generated from `comparison.json` by `make_gen_table.py`)

- **b6**: the arm of sections 1 to 4.8.
- **b7** = b6 + ONE combined ECO pass (user task of 2026-11-08, scripts `impl/icc2/scripts/b7_06_eco.tcl`, `impl/innovus/scripts/07m_eco.tcl`):
  ICC2 21 `buf_1` in front of the ff reg-to-reg hold endpoints (judge hold slack < +12 ps at nom/min/max ff) + one `buf_6` on the deck-antenna sink of
  `u_core_u_dcache/n3594` + 4 dcache dout0 buffers; Innovus 2 `buf_6` on the two deck-antenna sinks + 1 dcache dout0 buffer. **b7 is an intermediate
  generation and is not the final arm.** Why only the dcache dout0 pins: the five I-cache SRAMs have their port-0 pins on the macro's bottom edge (y = 20 um) outside the row
  lattice (rows start at y = 24.48 um and the macro covers them), so the nearest legal site is 139 to 340 um away. A first b7 run that buffered all 163 ICC2 dout0
  pins displaced the 159 I-cache buffers by 100 to 283 um (median 226 um) and took the ICC2 native ss setup from -0.022 to -0.97 ns; it was reverted
  (`impl/icc2/runs/b7_icc2/logs/b7_06_eco.run1_icache_all.log`, not committed).
- **b8** = the b6 flow on the **flipped I-cache floorplan** (the five I-cache SRAMs mirrored about X, `pnr/sky130/cpu/macro_placement_flipic.cfg`, shared by ICC2, Innovus and, later,
  OpenROAD; D-cache unchanged) + the b7 ECO set + dout0 buffers on every max-cap pin. Feasibility (`impl/check_flipic_feasibility.py`, `impl/flipic_feasibility.txt`): the flipped dout0
  pins sit at y = 417.5 um, 0.48 to 1.38 um from the first of 37 channel rows (y 418.88 to 516.80 um, full die width) shared with the D-cache pins; pin pitch 6.8 um; the
  met4 PG straps end flush at the macro edge exactly as at the D-cache pins (11 of 160 dout0 pins sit within 0.4 um of a strap, the same pins as the D-cache's).

**ICC2** (b6 -> b7 -> b8)

<!-- GEN-TABLE icc2 -->
| metric | ICC2 b6 | ICC2 b7 | ICC2 b8 |
|---|---|---|---|
| judge shared SDC: worst setup WNS (ns) / setup violators, 9 corners | -2.268 / 45 | -2.267 / 45 | -1.840 / 47 |
| judge shared SDC: worst hold WNS (ns) / hold violators, 9 corners | -2.412 / 4544 | -2.412 / 4532 | -3.300 / 5761 |
| judge per-view iolat SDC: worst setup WNS (ns) / setup violators, 9 corners | -0.059 / 3 | -0.060 / 3 | 0.022 / 0 |
| judge per-view iolat SDC: worst hold WNS (ns) / hold violators, 9 corners | -0.027 / 10 | 0.013 / 0 | 0.011 / 0 |
| judge own SDC: worst setup WNS (ns) / setup violators, 9 corners | -2.268 / 45 | -2.267 / 45 | -1.840 / 47 |
| judge own SDC: worst hold WNS (ns) / hold violators, 9 corners | -2.412 / 4544 | -2.412 / 4532 | -3.300 / 5761 |
| judge reg-to-reg setup / hold violators, 9 corners (shared SDC) | 3 / 10 | 3 / 0 | 0 / 0 |
| judge SRAM dout0 max-cap pins, nom_tt / worst corner | 159 / 163 | 159 / 159 | 0 / 0 |
| judge max-cap pins other than dout0, worst corner | 0 | 0 | 2 |
| judge max-tran pins, nom_tt / worst corner | 4 / 1073 | 4 / 1083 | 9 / 722 |
| judge PrimePower nom_tt (mW) | 70.80 | 70.80 | 69.20 |
| native routed DRC / native antenna (tool rule) | 0 / 0 | 0 / 0 | 1 / 0 |
| signoff KLayout DRC items | 0 | 0 | 0 |
| signoff deck antenna nets | 1 | 0 | 0 |
| signoff Netgen LVS (GDS, as delivered) | Circuits match uniquely | Circuits match uniquely | Circuits match uniquely |
| signoff LEC (positive / negative controls) | 4/4 equivalent; 4/4 negative controls caught | 4/4 equivalent; 4/4 negative controls caught | 4/4 equivalent; 4/4 negative controls caught |
| signoff Magic (std cells from GDS): inside SRAM / straddle / outside | 27733502 / 0 / 0 | 27733502 / 0 / 0 | 27731549 / 0 / 0 |
| derived logical cells | 40926 | 40952 | 40331 |
<!-- /GEN-TABLE -->

**Innovus** (b6 -> b7 -> b8)

<!-- GEN-TABLE innovus -->
| metric | Innovus b6 | Innovus b7 | Innovus b8 |
|---|---|---|---|
| judge shared SDC: worst setup WNS (ns) / setup violators, 9 corners | -3.028 / 227 | -3.028 / 227 | -3.026 / 202 |
| judge shared SDC: worst hold WNS (ns) / hold violators, 9 corners | -3.549 / 3873 | -3.549 / 3873 | -3.028 / 3118 |
| judge per-view iolat SDC: worst setup WNS (ns) / setup violators, 9 corners | -2.435 / 891 | -2.435 / 891 | -1.777 / 96 |
| judge per-view iolat SDC: worst hold WNS (ns) / hold violators, 9 corners | 0.190 / 0 | 0.190 / 0 | 0.175 / 0 |
| judge own SDC: worst setup WNS (ns) / setup violators, 9 corners | -0.050 / 4 | -0.050 / 4 | -0.112 / 2 |
| judge own SDC: worst hold WNS (ns) / hold violators, 9 corners | -0.254 / 4 | -0.254 / 4 | -0.010 / 1 |
| judge reg-to-reg setup / hold violators, 9 corners (shared SDC) | 0 / 0 | 0 / 0 | 0 / 0 |
| judge SRAM dout0 max-cap pins, nom_tt / worst corner | 160 / 161 | 160 / 160 | 0 / 0 |
| judge max-cap pins other than dout0, worst corner | 0 | 0 | 0 |
| judge max-tran pins, nom_tt / worst corner | 7 / 29 | 7 / 29 | 7 / 33 |
| judge PrimePower nom_tt (mW) | 76.20 | 76.20 | 74.50 |
| native routed DRC / native antenna (tool rule) | 0 / 0 | 0 / 0 | - / 0 |
| signoff KLayout DRC items | 0 | 0 | 0 |
| signoff deck antenna nets | 2 | 0 | 0 |
| signoff Netgen LVS (GDS, as delivered) | Top level cell failed pin matching | Top level cell failed pin matching | Top level cell failed pin matching |
| signoff LEC (positive / negative controls) | 4/4 equivalent; 4/4 negative controls caught | 4/4 equivalent; 4/4 negative controls caught | 4/4 equivalent; 4/4 negative controls caught |
| signoff Magic (std cells from GDS): inside SRAM / straddle / outside | 28315303 / 0 / 0 | 28315303 / 0 / 0 | 28317685 / 0 / 0 |
| derived logical cells | 45895 | 45898 | 45168 |
<!-- /GEN-TABLE -->

Measured read-path cost of the dout0 buffers (b6 -> b7, ICC2, the 4 buffered dcache pins, PrimeTime base SDC, worst setup slack through the pin, `diag_dout_paths.tcl`,
`signoff/pt/diag_dout/`): nom_ss slack 4.403 -> 4.146, 4.984 -> 4.764, 4.317 -> 4.094, 8.012 -> 7.789 ns (**-0.22 to -0.26 ns per buffered read path**, still 4 ns or more of slack); pin load
0.026 -> 0.011, 0.027 -> 0.004, 0.025 -> 0.003, 0.026 -> 0.003 pF (limit 0.02756 pF).

**Read-path cost of the b8 dout0 buffers, measured** (`reports/dout0_readpath_b6_b8.tsv`, PrimeTime base SDC, worst setup slack through any of the 320 SRAM dout0 pins): ICC2 nom_ss +1.586 -> +3.497 ns, max_ss +1.198 -> +3.372 ns, nom_tt +3.314 -> +4.495 ns;
Innovus nom_ss +2.247 -> +3.351 ns, max_ss +2.069 -> +3.230 ns. The flip shortens the pin-to-logic wires (largest dout0 net load 0.096 -> 0.025 pF on ICC2, 0.117 -> 0.024 pF on Innovus), which more than pays for the 5 ICC2 / 1 Innovus buffers (each costs
about 0.2 to 0.26 ns, section above). It is not better for every pin: 34 of the 163 ICC2 pins that violated in b6 (3 of 161 on Innovus) have a lower slack in b8, 14 of them by more than 0.3 ns (worst -1.15 ns ICC2, -0.68 ns Innovus), and all of them keep at least +3.4 / +3.3 ns of slack at nom_ss.

**b8 ECO set and counts.** ICC2 b8: 30 hold `buf_1` (judge endpoints with hold slack below +12 ps at nom/min/max ff on the pre-ECO route), 576 antenna diodes (deck pins on the routed DEF), dout0 buffers on the 3 pins the judge flagged
after routing (b6: 163 pins; the flip alone removed 160 of them) + 2 more in round 2 (two pins that crept to 0.0282 / 0.0279 pF at the max RC corner after round 1), 3 antenna-sink `buf_6` in round 2 (deck had 3 nets after round 1).
Innovus b8: 48 KLayout pin stubs, the draft-deck antenna diodes, 1 dout0 buffer (`dout0[30]`, 0.0284 pF), 5 antenna-sink `buf_6` in round 2 (deck had 5 nets after round 1). Round 1 of both arms is superseded by round 2 (all numbers here are round 2).
PDN check of the flipped macros: ICC2 `check_pg_connectivity` 0 floating wires / vias / std cells / hard macros at the PDN stage and at the end; `check_pg_drc` 95 errors at the PDN stage, identical to b6 (95), 302 at the end (b6 280; the 22 extra were not analysed, ICC2-native count, the KLayout deck is 0); Innovus `PDN_SELFCHECK` PASS (one special-wire piece per PG net), n-well islands without tap 767 -> 474 after the tap fix, both identical to b6.
The flipped pins face the channel as planned: the five I-cache SRAMs are placed MX (the cfg's FS) in both tools, bounding boxes unchanged, KLayout DRC 0 on both arms (no met4-strap versus pin conflict).

**b6 vs b7 vs b8 regression check** (generated by `compare/regress_check.py` from `comparison.json`; worse = a count that rose or a WNS that fell by more than 2 ps; the hold rows of the base, own and fixed-latency iolat SDC are the I/O-latency artefact of caveat 4 and are flagged):

*ICC2 b7 vs b6*

<!-- GEN-REGRESS icc2 b7 -->
### icc2_b7 vs icc2_b6: 6 worse, 52 better, 258 equal (WNS tolerance 2 ps)

- judge DRV max_tran: 1 item(s); DRV base max_ss: 1073 -> 1083
- judge iolat_pvs setup_viol: 1 item(s); iolat_pvs min_ss: 18 -> 19
- judge iolat_pvs setup_wns: 3 item(s); iolat_pvs nom_ss: -0.719835 -> -0.838366; iolat_pvs min_ss: -0.376226 -> -0.508438; iolat_pvs max_ss: -1.162956 -> -1.307976
- signoff/native  : 1 item(s); native_max_tran_viol: 114 -> 115
<!-- /GEN-REGRESS -->

*ICC2 b8 vs b6*

<!-- GEN-REGRESS icc2 b8 -->
### icc2_b8 vs icc2_b6: 71 worse, 110 better, 135 equal (WNS tolerance 2 ps)

- judge DRV max_cap_other: 5 item(s); DRV base nom_tt: 0 -> 1; DRV base nom_ss: 0 -> 2; DRV base min_ss: 0 -> 1; DRV base max_tt: 0 -> 1; DRV base max_ss: 0 -> 2
- judge DRV max_fanout: 9 item(s); DRV base nom_tt: 164 -> 177; DRV base nom_ss: 164 -> 177; DRV base nom_ff: 164 -> 177; DRV base min_tt: 164 -> 177; DRV base min_ss: 164 -> 177; DRV base min_ff: 164 -> 177; DRV base max_tt: 164 -> 177; DRV base max_ss: 164 -> 177; DRV base max_ff: 164 -> 177
- judge DRV max_tran: 6 item(s); DRV base nom_tt: 4 -> 9; DRV base nom_ff: 0 -> 7; DRV base min_tt: 0 -> 7; DRV base min_ss: 16 -> 19; DRV base min_ff: 0 -> 7; DRV base max_ff: 1 -> 7
- judge base hold_viol (fixed / missing I/O latency, caveat 4: not a layout measure): 9 item(s); base nom_tt: 556 -> 666; base nom_ss: 577 -> 683; base nom_ff: 374 -> 567; base min_tt: 544 -> 656; base min_ss: 571 -> 679; base min_ff: 325 -> 544; base max_tt: 570 -> 678; base max_ss: 586 -> 686; base max_ff: 441 -> 602
- judge base hold_wns (fixed / missing I/O latency, caveat 4: not a layout measure): 9 item(s); base nom_tt: -1.230087 -> -1.747214; base nom_ss: -2.23379 -> -3.068645; base nom_ff: -0.780111 -> -1.116899; base min_tt: -1.145291 -> -1.62631; base min_ss: -2.107156 -> -2.897244; base min_ff: -0.722342 -> -1.037162; base max_tt: -1.345457 -> -1.904405; base max_ss: -2.412113 -> -3.299777; base max_ff: -0.865396 -> -1.233392
- judge base setup_viol: 1 item(s); base nom_ss: 12 -> 15
- judge iolat hold_viol (fixed / missing I/O latency, caveat 4: not a layout measure): 4 item(s); iolat nom_ss: 42 -> 156; iolat min_ss: 31 -> 125; iolat max_tt: 0 -> 1; iolat max_ss: 66 -> 192
- judge iolat hold_wns (fixed / missing I/O latency, caveat 4: not a layout measure): 5 item(s); iolat nom_tt: 0.113885 -> 0.030786; iolat nom_ss: -0.455791 -> -1.290645; iolat min_ss: -0.329156 -> -1.119244; iolat max_tt: 0.111586 -> -0.126405; iolat max_ss: -0.634113 -> -1.521777
- judge iolat setup_wns: 1 item(s); iolat min_ss: 0.69887 -> 0.499584
- judge iolat_pv setup_wns: 2 item(s); iolat_pv nom_ss: 0.416538 -> 0.299618; iolat_pv min_ss: 0.714773 -> 0.499584
- judge own hold_viol (fixed / missing I/O latency, caveat 4: not a layout measure): 9 item(s); own nom_tt: 556 -> 666; own nom_ss: 577 -> 683; own nom_ff: 374 -> 567; own min_tt: 544 -> 656; own min_ss: 571 -> 679; own min_ff: 325 -> 544; own max_tt: 570 -> 678; own max_ss: 586 -> 686; own max_ff: 441 -> 602
- judge own hold_wns (fixed / missing I/O latency, caveat 4: not a layout measure): 9 item(s); own nom_tt: -1.230087 -> -1.747214; own nom_ss: -2.23379 -> -3.068645; own nom_ff: -0.780111 -> -1.116899; own min_tt: -1.145291 -> -1.62631; own min_ss: -2.107156 -> -2.897244; own min_ff: -0.722342 -> -1.037162; own max_tt: -1.345457 -> -1.904405; own max_ss: -2.412113 -> -3.299777; own max_ff: -0.865396 -> -1.233392
- judge own setup_viol: 1 item(s); own nom_ss: 12 -> 15
- signoff/native  : 1 item(s); native_route_drc: 0 -> 1
<!-- /GEN-REGRESS -->

*Innovus b7 vs b6*

<!-- GEN-REGRESS innovus b7 -->
### innovus_b7 vs innovus_b6: 0 worse, 6 better, 310 equal (WNS tolerance 2 ps)

<!-- /GEN-REGRESS -->

*Innovus b8 vs b6*

<!-- GEN-REGRESS innovus b8 -->
### innovus_b8 vs innovus_b6: 46 worse, 92 better, 177 equal (WNS tolerance 2 ps)

- judge DRV max_tran: 4 item(s); DRV base nom_ss: 14 -> 24; DRV base max_tt: 10 -> 21; DRV base max_ss: 29 -> 33; DRV base max_ff: 8 -> 17
- judge base setup_wns: 5 item(s); base nom_tt: 2.455122 -> 2.389312; base nom_ss: -1.992781 -> -2.093926; base min_tt: 2.99192 -> 2.926162; base min_ss: -1.252728 -> -1.526114; base max_tt: 1.686182 -> 1.614152
- judge iolat hold_wns (fixed / missing I/O latency, caveat 4: not a layout measure): 3 item(s); iolat nom_ff: 0.197131 -> 0.182235; iolat min_ff: 0.190276 -> 0.175173; iolat max_ff: 0.202114 -> 0.188768
- judge iolat setup_wns: 3 item(s); iolat nom_ss: -0.214781 -> -0.315927; iolat min_ss: 0.525272 -> 0.251886; iolat max_tt: 3.43884 -> 3.392152
- judge iolat_pv hold_wns: 6 item(s); iolat_pv nom_ss: 0.998494 -> 0.991661; iolat_pv nom_ff: 0.197131 -> 0.182235; iolat_pv min_ss: 0.988532 -> 0.962012; iolat_pv min_ff: 0.190276 -> 0.175173; iolat_pv max_ss: 1.01689 -> 1.011201; iolat_pv max_ff: 0.202114 -> 0.188768
- judge iolat_pvs hold_wns: 6 item(s); iolat_pvs nom_ss: 0.998494 -> 0.991661; iolat_pvs nom_ff: 0.197131 -> 0.182235; iolat_pvs min_ss: 0.988532 -> 0.962012; iolat_pvs min_ff: 0.190276 -> 0.175173; iolat_pvs max_ss: 1.01689 -> 1.011201; iolat_pvs max_ff: 0.202114 -> 0.188768
- judge iolat_pvs setup_viol: 1 item(s); iolat_pvs min_ss: 30 -> 32
- judge iolat_pvs setup_wns: 6 item(s); iolat_pvs nom_tt: 3.493258 -> 3.442099; iolat_pvs nom_ss: -0.986462 -> -1.062656; iolat_pvs min_tt: 3.772328 -> 3.726544; iolat_pvs min_ss: -0.660007 -> -0.698271; iolat_pvs max_tt: 3.042707 -> 3.0062; iolat_pvs max_ss: -1.533331 -> -1.595213
- judge own hold_wns (fixed / missing I/O latency, caveat 4: not a layout measure): 3 item(s); own nom_ff: 0.197131 -> 0.180034; own min_ff: -0.00681 -> -0.010338; own max_ff: 0.202114 -> 0.188768
- judge own setup_wns: 9 item(s); own nom_tt: 2.830258 -> 2.779099; own nom_ss: 0.17724 -> 0.101046; own nom_ff: 3.830317 -> 3.802921; own min_tt: 2.958437 -> 2.903245; own min_ss: 0.259792 -> 0.221527; own min_ff: 3.946805 -> 3.929875; own max_tt: 2.594408 -> 2.557899; own max_ss: -0.050232 -> -0.112114; own max_ff: 3.629773 -> 3.598508
<!-- /GEN-REGRESS -->

Other b8 differences that the JSON does not rank: Innovus-native `verify_drc` reports 24 `ParallelRunLength Spacing` items (regular wires 0.14 um from the SRAM LEF blockage at y = 416.88 to 417.03 um, at the flipped I-cache
pins; 27 after route, 24 after the b8 ECO; b6: 0), the KLayout deck on the same layout is 0; ICC2 `check_routes` reports 1 DRC on met3 or above (b6: 0; located nowhere: the error-data query returned no objects), the KLayout deck is 0.
Innovus LVS keeps the b6 pin-match failure on 3 `assign` pairs (`axi_awlen_o[1]`, `axi_arburst_o[0]`, `debug_pc_src_o` in b8; b6: `axi_awlen_o[1]`, `axi_arlen_o[1]`, `axi_arburst_o[0]`), nets and devices equal.

**Final-arm decision (2026-11-09): b6 stays final; b7 and b8 are history arms** (`FINAL_GEN = "b6"` in `compare.py`). Rule given for the adoption of b8: no check may be worse than b6 apart from the measured buffer timing cost.
b8 is better on the targets (SRAM dout0 max-cap 163 / 161 -> 0 at all 9 corners, deck antenna 1 / 2 -> 0, ICC2 ff reg-to-reg hold 10 -> 0, ICC2 per-view iolat fully clean, Innovus per-view iolat setup violators 891 -> 96, Magic 0 outside the SRAMs, KLayout 0, LVS and LEC unchanged),
but the regression lists above are not empty on either arm (ICC2: 2 new input-port max-cap pins, +13 max-fanout, +5 max-tran at nom_tt, 1 native DRC, setup margin at nom_ss / min_ss 0.12 to 0.2 ns lower; Innovus: 24 native DRC items, own-SDC max_ss setup -0.112 vs -0.050 ns,
max-tran +4 to +10 at four corners), so the rule is not met and b8 is not adopted. Next actions are in section 7 (items 6, 12 and 13).

## 5. History arms (earlier commercial iterations, judge on the same chain)

Source: `judge.<arm>` and `arms.<arm>.metrics` in the JSON. Figures marked (p) are prose-only
(`kind: prose`).

| | ICC2 b5e | ICC2 b5i | ICC2 b5m | Innovus b5h | Innovus b5j | Innovus b5k |
|---|---|---|---|---|---|---|
| netlist / P&R views | DC v1 / tt | DC v1 / tt | DC v1 / tt | Genus v1 / tt | Genus v1 / tt | Genus v1 / tt (+ ff hold ECO) |
| judge base nom_tt setup ; hold (ns) | +0.085 ; -1.226 | +0.085 ; -1.228 | +0.085 ; -1.232 | -0.456 ; -2.200 | -0.456 ; -2.200 | -0.594 ; -2.224 |
| judge base worst setup / hold (ns) | -14.668 / -2.406 | -14.671 / -2.409 | -14.670 / -2.416 | -9.761 / -4.039 | -9.761 / -4.039 | -9.759 / -4.085 |
| judge base reg-to-reg setup viol. (9 corners) | 4,099 | 4,089 | 4,082 | 2,543 | 2,543 | 2,553 |
| judge iolat worst hold / hold viol. | -0.628 / 445 | -0.631 / 447 | -0.638 / 451 | -2.261 / 218 | -2.261 / 218 | -2.307 / 269 |
| judge own nom_tt setup ; hold | n/a | n/a | n/a | +0.706 ; +0.140 | +0.706 ; +0.140 | +1.006 ; +0.140 |
| judge PrimePower nom_tt (mW) | 67.8 | 67.8 | 67.8 | 69.5 | 69.5 | 70.5 |
| judge max_tran / max_cap pins nom_tt | 855 / 172 | 907 / 171 | 950 / 172 | 347 / 213 | 347 / 213 | 392 / 155 |
| native setup / hold WNS tt (p) | +0.0725 / +0.0037 | +0.0746 / -0.0016 | +0.0746 / -0.0032 | +0.215 / +0.139 | +0.215 / +0.139 | +0.065 / +0.011 |
| native route DRC (p) | 1 | 0 | 0 | 0 | 0 | 0 |
| KLayout DRC | 132 | 1 | 0 | not run | 60 | 0 |
| deck antenna nets | 488 (p) | 492 | 3 | not run | 10 | 2 |
| Netgen LVS (GDS, as delivered / clean) | pin-match fail / pin-match fail | pin-match fail / match | match / match | not run | pin-match fail (3 `assign` pairs) | pin-match fail (same 3) |
| LEC | EQUIVALENT (p) | (content = b5e) | 6,233 / 0, 4/4 (p) | not run | 4/4, 4/4 controls (p) | Conformal 4/4 EQ, 4/4 controls |
| Magic outside SRAM | 4,019 (3,035 `nwell.4` + 984 `met4.5ab`) | not run | not run | not run | not run | not run |

Lessons from the history: (a) the tt-only arms lose 7.8 to 14.7 ns at ss, and almost all of it is
reg-to-reg. The b6 MCMM/MMMC arms remove it. (b) The b5 -> b5m/b5k ECO rounds fix layout (DRC,
antenna, taps, LVS) at a few ps of hold each, and the judge moves by less than 0.3 ns at every
corner. (c) b5j is identical to b5h in all 27 judge runs: the tap ECO changed no timing.

## 6. Lessons by tool

- **OpenROAD / LibreLane.** It reproduces bit for bit (B2 matched the recorded run exactly). It has
  the best hold behaviour, because LibreLane's I/O model is tied to its own tree: iolat hold is
  clean at 9/9. It also has the most buffers, the most clock power (42.8 mW) and 3.6k
  max_tran pins. It is the only arm that keeps the ss reg-to-reg loss: Yosys starts at -1.92 ns
  zero-wire, and the flow ends at -4.33 ns. The antenna repair leaves 116 deck nets with 64k
  diodes inserted. Magic DRC was killed by the 10 GB watchdog while LibreLane parsed its report.
- **Synopsys DC -> ICC2.** DC v1 (tt only, area recovery) built a slow ripple adder and lost
  10.5 ns at ss before any wire existed. DC v2 MCMM fixed that at +10 % cells. ICC2 has no
  per-scenario link library: an MCMM flow needs **one reference NDM with three PVT panes**
  (`build_ndm_mcmm.tcl`). `route.common.global_min_layer_mode` defaults to `soft`, so the li1 ban
  must be set to `hard`. ICC2's own antenna rule is lenient, so the deck check has to come from
  OpenROAD `check_antennas`. Its `write_sdc` carries no I/O latency, so the judge's own variant
  equals base. Result: the smallest, lowest-power layout, 3 reg-to-reg setup violators at max_ss,
  and ss hold left open (ss was a setup-only scenario).
- **Cadence Genus -> Innovus.** Genus v1 was already +0.61 ns at ss zero-wire, so no Genus v2 was
  needed. Innovus keeps clock latencies in each view's `latency.sdc`, so a view created without
  `-latency_file` silently drops clk_io. `create_inst` fails silently: use `addInst -physical`.
  `verifyProcessAntenna` has no side-area rule, so the deck count has to come from OpenROAD.
  Taps must abut endcaps at the source (293 taps). npc.2 needs a decap -> fill swap next to
  mirrored `and2_0`. Full MMMC removed every reg-to-reg violation at +105 % buffers and +5.6 mW of
  combinational power. Innovus has the longest wire (7.34 M um) but the fewest vias.
- **Judge chain (StarRC / PrimeTime / PrimePower).** The annotation gate (0 unannotated pin-to-pin
  nets) and the md5 assertions on SDC, SPEF and netlist made 27-run sweeps per arm trustworthy.
  StarRC needed `COUPLING_ABS_THRESHOLD 0.1` / `REL 0` and `LEF_USE_OBS NO` to match OpenRCX's
  coupling share. The remaining per-pin C term is the main calibration residual.
- **LEC.** Both tools caught every mutant. Formality needs the SVF for DC netlists. Conformal's
  `swap` mutant anchor had to follow an optimiser resize (`a211o_[12]`). Antenna diodes appear as
  unmatched or unreachable points, so a diode-stripped compare is run alongside.
- **RedHawk.** It does not read the Sky130 decap cells' capacitance, so decap had to be declared
  from spice W/L. The decap estimate, not the grid, sets the dynamic ranking. PEAK-mode EM against
  a DC limit is an artefact and is not judged.

## 7. Open items and follow-ups

Beads are not available on this host, so the follow-ups are tracked here.

1. **OpenROAD post-route LEC: closed 2026-11-08** (`reports/lec_openroad.md`). The routed netlist (md5 `a0f07319...`, the judge's) is
   EQUIVALENT to the RTL by three proofs: RTL == `rv32i_cpu_top_sv2v.v` (Formality, 6,302 / 0), sv2v == OpenROAD final netlist (Yosys
   `equiv_induct` in the LibreLane 2.4.13 container, 6,156 `$equiv` cells, 0 unproven; fill/decap/tap and the 64,086 diodes stripped, all
   without signal pins), and final == Yosys synthesis netlist (Formality, 6,248 / 0). Negative controls: Formality 6/6, Yosys 4/4
   (`e6`/`e8`/`e9` collapse the induction, `e7` leaves a partial set of 346 unproven points; both are detections). **Limits:** the Yosys
   gold goes through the same Yosys `proc`/`fsm`/`opt`/`memory_map` passes as the netlist, so a common-mode Yosys bug would not be
   seen (the `synth -nofsm` independence check was not run). The Yosys log shows `fsm` re-encoded `fwd_a_sel_r`, `fwd_b_sel_r`
   and `grant_q` to one-hot; Formality (3,902 failing) and Conformal (4,335 non-equivalent) could not match that and fail on the
   Yosys-netlist-vs-sv2v compare. That is unresolved, not waived, and not contradicted by the Yosys result.
2. **Magic `nwell.4` outside the SRAMs: closed 2026-11-09 by the sign-off mode change** (user decision 2026-11-08: sign-off Magic loads the std cells from the GDS;
   waivers W1 to W4 WITHDRAWN). Full-die std-cell-GDS Magic on ICC2 b6/b7 and Innovus b6/b7: 0 items outside or straddling the SRAM footprints, all 30 rules inside
   (caveat 6, `reports/magic_nwell4_rootcause.md` section 10). The inside-SRAM items remain under the bead `45a` waiver (new values in caveat 6).
3. **Per-view clk_io latency**: done for the iolat variant (sections 4.2b to 4.2e, per-arm and
   shared). Still open: the same correction for the **Innovus own SDC** (fixed 3.295 ns), which
   needs a per-view copy of `sky130_cpu_innovus_b6_own_pt.sdc` and 9 more PrimeTime runs, and a
   decision on the 797 + 2,367 ss I/O setup endpoints of Innovus and OpenROAD that survive
   (4.2d): relax the input delays, add multicycle exceptions for the quasi-static APB inputs, or
   accept them as real.
4. **ICC2 ff reg-to-reg hold: closed in b7 (2026-11-09).** b6 ss hold was closed as an artefact earlier; what remained was ICC2's ff reg-to-reg hold (2 violators at nom_ff, 8 at
   max_ff, -0.004 / -0.027 ns). 21 `buf_1` in front of the capture D pins (endpoints with judge hold slack below +12 ps at nom/min/max ff, `impl/icc2/eco_b7/hold_endpoints.txt`) bring
   the reg-to-reg hold violators to 0 at all 9 corners and the per-view iolat worst hold WNS from -0.027 to +0.013 ns (section 4.9). Cost: 21 `buf_1`; setup on those endpoints
   has more than 7 ns of slack. Innovus b6 hold was already 0 and stays 0.
5. **Deck antenna: closed on ICC2 and Innovus in b7 (2026-11-09).** ICC2 b6 `u_core_u_dcache/n3594` (met1 side-area ratio 592 vs 400 on the gate-attached met1 island; the four diodes of the
   three b6 rounds are connected on upper layers, so the deck does not credit them) and Innovus b6 `FE_OFN20491_n` / `FE_OFN21807_n` (met3 / met2 side area 457 / 581 vs 400) are fixed by
   one `buf_6` in front of each sink pin (gate area 0.495 um2 against 0.126 / 0.252 um2: the long wire then ends on a gate 3.9 / 2.0 times larger). Re-routing the ICC2 net with layer hopping
   reproduced the same 104 um met1 run, so that alternative was dropped. Deck result (OpenROAD `check_antennas`): 0 nets / 0 pins on both b7 arms. OpenROAD's 116 nets move to item 9
   (a separate agent folds its flip, dout0 buffers and antenna fix into the single-variable run).
6. **Max-cap on the SRAM `dout0` pins (160 per commercial arm in b6).** **Correction of the earlier premise:** the limit is not a TT-only-Liberty artefact and needs no per-corner SRAM
   characterisation (bead `o1i` is not the cause). The SRAM Liberty gives `dout0` `max_capacitance` 0.02756 pF, which is the top of its load table (`index_2`, 0.0017 / 0.0069 / 0.0276
   pF); a load above it is extrapolated, and the limit is the same at every corner (the 163 / 161 violators are the same pins at all 9 corners). **Decision:** fix with a buffer ECO, not a
   waiver (user, 2026-11-08). **Finding:** in b6 the violators are 159 of 163 (ICC2) and 160 of 161 (Innovus) on the five I-cache SRAMs, whose dout0 pins are on the bottom edge at
   y = 20 um outside the row lattice, so no buffer can be placed within 139 um of them (section 4.9). b7 buffers only the dcache pins (4 ICC2, 1 Innovus: 163 -> 159 and 161 -> 160 violators).
   The flip of the five I-cache SRAMs (user decision 2026-11-08, shared floorplan `macro_placement_flipic.cfg`) is b8 and **clears the dout0 max-cap pins at all 9 corners on both arms**
   (163 / 161 -> 0): after the flip only 3 (ICC2) and 1 (Innovus) pins were left to buffer, the buffers land next to the pins in the channel, and the measured cost is in section 4.9. **Status:
   target met in b8, b8 not adopted** (section 4.9 decision); b6 stays final with 159 / 160 violating pins. Next: item 12.
7. **Extraction calibration to silicon or a foundry deck** does not exist. Optionally recalibrate
   the corner multipliers on design total C (0.8988 / 1.0933) rather than on wire slope. The Quantus
   cross-check is done at nom, min and max (section 4.8).
8. **RedHawk** needs characterised decap and APL, a package model, and a decap ECO on ICC2 before
   any dynamic IR verdict.
9. **Single-variable P&R comparison** (and the OpenROAD fixes for items 4 to 6: the flipped floorplan `macro_placement_flipic.cfg`, dout0 buffers, the 116 deck-antenna nets; and the OpenROAD B2 std-cell-GDS Magic run, which is NOT RUN, item 16): run all three P&R tools on one netlist (for example the DC v2
   or Genus netlist through OpenROAD) to separate synthesis from P&R.
10. **OpenROAD peak RSS** is not recorded. Wrap the LibreLane run in `/usr/bin/time -v` next time.
11. Phase D (FreePDK45, ASAP7, the Sky130 SoC) and the Phase C suite back-port, per the plan.
12. **ICC2 b8: two input-port max-cap pins** (`axi_rdata_i[16]`: 0.5741 pF against 0.5612 at nom_tt and 0.6374 against 0.3534 at max_ss; `axi_rdata_i[15]`: 0.4194 against 0.3534 at max_ss; b6 has none). A b8 ECO round 3 should
    buffer these two port nets (insert a buffer at the port) and then re-run the judge; the same round can look at the +13 max-fanout and +5 max-tran pins at nom_tt, which are marginal.
13. **Innovus b8: 24 Innovus-native spacing items at the flipped I-cache pins** (wire to SRAM LEF blockage, y 416.88 to 417.03 um) while KLayout is 0, and the own-SDC max_ss setup WNS -0.112 ns (b6 -0.050).
    Next: decide whether the LEF blockage check is pessimistic (compare with the SRAM GDS obstruction) or re-route those pin stubs with a halo; re-time the two max_ss paths.
14. **ICC2 b8: 1 native `check_routes` DRC** (met3 or above, unlocated; KLayout 0, b6 0). Next: open the error browser (`zroute.err`) in an interactive `icc2_shell` and repair or document it.
15. **b8 margins**: ICC2 nom_ss / min_ss setup margin of the per-view run fell from +0.417 / +0.715 to +0.300 / +0.500 ns, Innovus per-view setup is still 96 violators at the three ss corners (b6 891; the item 3 decision on the ss I/O endpoints stays open).
16. **OpenROAD B2 Magic with std cells from the GDS: NOT RUN.** The first attempt read a missing GDS and reported 0 (invalid); the second coincided with a host hang at 07:36 and a reboot at 08:26 on 2026-11-09. It was
    re-run last and alone with `GUARD_RSS_GB=10 GUARD_MIN_GB=3` and was killed by the watchdog at container RSS 10.18 GiB after 22 min (host load 1.0, MemAvailable >= 3.7 GB, no hang); not retried. A 32 GB host, or the window method on the OpenROAD GDS, is the safe route.
17. **Innovus `verifyConnectivity -type all` hang on the b7 / b8 databases** (> 1 h, b6: 6 s) is not understood; b7 and b8 skip it (caveat 8). Next: run it alone on the saved `07_eco` / `08b_eco` database with `-type regular` and `-limit 100` to see
    which net it stalls on, or ask Cadence; until then connectivity rests on the special-net check and Netgen LVS.
18. **Not re-run for b7 / b8**: RedHawk static / dynamic IR (b8 has a different placement; the PG grid is unchanged), the Quantus cross-check (section 4.8) and the Innovus own-SDC per-view latency. They are open for b8 only if b8 is adopted.

## 8. Files

- `pnr/commercial/compare/compare.py`: builds `comparison.json`. It reads committed files only and
  starts no EDA tool.
- `pnr/commercial/compare/snapshot_sources.py`: one-time copy of run-directory results into
  `compare/snapshot/`, plus the b6 LEC report copies into `signoff/lec/*/reports/`.
- `pnr/commercial/compare/test_compare.py`: checks that every JSON value has a source in the git
  index, that the final arms are complete with no md5 warnings, and that the committed JSON is
  current.
- Per-view iolat study: `pnr/commercial/constraints/{gen_iolat_pv_sdc.py,sky130_cpu_iolat_pv.sdc}`,
  `pnr/commercial/signoff/pt/scripts/{measure_clk_latency.tcl,measure_one.sh,mk_iolat_tables.py,run_iolat_pv.sh,diag_io_viol.tcl,run_diag_pv.sh,summ_io_viol.py}`,
  tables in `pnr/commercial/signoff/pt/iolat_pv/`, chain `pnr/commercial/signoff/chain_clkio_pv*.sh`.
- b7 / b8 (2026-11-08/09): ECO scripts `impl/icc2/scripts/b7_06_eco.tcl`, `b8_*.tcl`, `b8_chain.sh`; `impl/innovus/scripts/07m_eco.tcl`, `08m_eco.tcl`, `chain_inn_b7.sh`, `chain_inn_b8.sh`, `chain_inn_b8r2.sh`;
  lists and flows `signoff/b8_lists.sh`, `b8_icc2_flow.sh`, `b8r2_flow.sh`, `chain_b7_all.sh`, `chain_b8_all.sh`, `step4_fixups.sh`, `step4_finish.sh`; shared floorplan `pnr/sky130/cpu/macro_placement_flipic.cfg`
  with `impl/check_flipic_feasibility.py` and `impl/flipic_feasibility.txt`; tables `compare/make_gen_table.py`, `compare/regress_check.py`, `compare/update_doc_tables.py`, `signoff/pt/scripts/table_b8.py`;
  Magic mode switch `signoff/drclvs/Makefile` (`MDRC_STD=gds|lef`) and `scripts/magic/gds_abs_drc.tcl`; `pdk/sky130/scripts/dropcache.sh` (page-cache eviction for the 15 GB host).
- Underlying reports: `pnr/commercial/reports/` (`pt_judge_summary.md` sections 13 and 14,
  `icc2_pnr_summary.md`, `innovus_b6_report.md`, `redhawk_ir_summary.md`,
  `starrc_extraction_summary.md`, `lec_*.md`, `synth_ss_probe_step1.md`,
  `dc_synth_v2_summary.md`).
