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
> synthesis netlists. The I/O latency model leaves artefacts at ss/ff. The IR figures are
> indicative.

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
| **judge** own SDC, worst setup / hold (ns) | n/a | -2.268 / -2.412 | **-0.050 / -0.254** (4 / 4 viol.) |
| **judge** PrimePower nom_tt (mW) | 93.1 (clock 42.8) | **70.8** (clock 25.2) | 76.2 (clock 24.1) |
| **judge** max_tran / max_cap pins, nom_tt | 3,613 / 268 | **4** / 159 | 7 / 160 |
| **derived** logical std-cell area (um2) / util | 472,827 / 10.9 % | **357,158 / 8.2 %** | 477,024 / 11.0 % |
| **derived** logical cells / flops / buffers | 42,578 / 5,299 / 16,176 | 40,926 / 5,284 / **8,501** | 45,895 / 5,208 / 16,083 |
| **native** routed wirelength (um) / vias | 5,586,306 / 517,723 | **4,634,225** / 393,701 | 7,342,159 / **362,426** |
| **signoff** KLayout DRC / deck antenna nets | 0 / 116 | 0 / **1** | 0 / 2 |
| **signoff** Netgen LVS (GDS) | 0 errors (LibreLane) | match uniquely | nets/devices equal; top pin match fails (3 `assign` pairs) |
| **signoff** LEC (post-route vs RTL, 4 neg. controls) | **not run** | Formality 4/4, 4/4 caught | Conformal 4/4, 4/4 caught |
| **signoff** Magic DRC outside SRAM (all `nwell.4`) | 3,626 | **3,035** (+592 straddle) | 4,226 (+737 straddle) |
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
   fails hold on I/O-port paths at all 9 corners. Under the iolat SDC (a virtual I/O clock),
   OpenROAD is hold-clean at 9/9. ICC2 b6 fails at the three ss corners and at nom/max_ff.
   Innovus b6 fails at the three ss corners and at nom/max_tt. Innovus' failures are all I/O paths
   measured against the fixed clk_io latency (caveat 4). Only ICC2
   has reg-to-reg hold violators (10, at ff).
3. **Power and area favour ICC2.** ICC2 b6 uses the least logic (357k um2, half the buffers of the
   others), the shortest wire and the lowest power (70.8 mW). The 22 mW gap to OpenROAD is almost
   all clock network (42.8 vs 25.2 mW). Memory power (29 mW, constant) is the same in every arm.
4. **Physical sign-off.** KLayout DRC is 0 on all three. LVS matches on ICC2. On Innovus the nets
   and devices match but top-level pin matching fails on 3 netlist `assign` pairs. OpenROAD passes
   LibreLane's LVS. Deck antenna is 1 (ICC2), 2 (Innovus) and 116 (OpenROAD, whose LibreLane
   repair left those). The open sign-off deck is clean, but the Magic `nwell.4` items outside the
   SRAMs remain open on every arm (caveat 6).
5. **IR is grid-healthy everywhere but decap-sensitive.** Static drop is 18 to 25 mV
   (VDD+VSS, 1.0 to 1.4 %) on every arm. Dynamic worst-case drop ranks OpenROAD < Innovus < ICC2.
   That ranking follows the estimated decap (ICC2 has 4,210 decap cells against roughly 300k on the
   others). It is not a statement about the grid.

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
4. **The fixed clk_io 3.295 ns latency causes ss/ff I/O artefacts.** The Innovus own SDC (and the
   iolat SDC, which uses 1.778 ns) applies one I/O clock latency to every view. The b6 CTS tree is
   5.66 / 6.66 ns (ss early / late), 3.05 ns (tt) and 1.95 ns (ff). Every remaining ss/ff I/O
   setup or hold item on the Innovus and ICC2 iolat/own rows carries that modelling error. The
   shared SDC has no I/O latency at all, which is why all arms show I/O hold failures under it.
5. **IR is indicative.** The RedHawk tech is authored and uncorrelated. Cell currents are RedHawk
   defaults (no APL). Decap capacitance is estimated from spice W/L. The supply is an ideal edge
   feed (met5 stripe ends, no package). Power is PrimePower vectorless at 0.1 / 0.5.
6. **The Magic `nwell.4` items are open.** Inside the SRAM footprints, Magic reports about 27.7 to
   28.3 M items. These are the waived SRAM-abstract artefact (bead `45a`). Outside or straddling
   the footprints, every arm has `nwell.4` items that are **not** waived: OpenROAD 3,626, ICC2 b6
   3,035 + 592 straddling, Innovus b6 4,226 + 737 straddling. Of Innovus' 4,226, **1,191 are
   Innovus-specific**: tap-sized wells in the left pocket (x < 125 um, y < 920 um) that are not in
   the ICC2 class (`reports/innovus_b6_report.md` section 8). The island checker, KLayout and Netgen
   are clean there. Not root-caused.
7. One run per arm. Native tool numbers use each tool's own RC, SDC and engine, so they are not
   ranked against each other. Runtimes were measured on a shared 8-core / 15 GB host, often under
   load, so they are not a tool-speed benchmark.

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
| Magic straddle / outside (all `nwell.4`) | 0 / 3,626 | 592 / 3,035 | 737 / 4,226 |
| LEC post-route | not run | Formality: 4/4 SUCCEEDED, 6,233 passing / 0 failing; controls `fwdb_inv` 1 and `swap` 43 failing points (4/4 caught) | Conformal: 4/4 EQUIVALENT, 5,597 (Genus golden) / 5,791 (RTL golden, merged points) compare points; 4/4 controls NOT_EQUIVALENT |
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

### 4.8 Quantus cross-check of the StarRC judge (nom; min and max pending)

Cadence Quantus 23.1.1 with a qrcTechFile built by Techgen from the same authored ICT was run on the three b6 DEFs and compared per net with the
StarRC SPEFs the judge read (JSON `quantus_crosscheck`; full method, gotchas and tables in `pnr/commercial/reports/quantus_crosscheck.md`).
Both extractors read the same authored stack, so this checks engine agreement, not silicon.

| Arm | Total C median error | Total C p95 abs error | Total R median error | Total R p95 abs error | Design C ratio (Quantus/StarRC) |
|---|---:|---:|---:|---:|---:|
| ICC2 b6 | -3.12 % | 9.75 % | +1.53 % | 2.59 % | 0.963 |
| Innovus b6 | +2.10 % | 19.59 % | +1.34 % | 4.98 % | 1.019 |
| OpenROAD | -2.33 % | 12.68 % | +1.60 % | 3.08 % | 0.986 |

Median total C and R are inside the plan's +-10 % gate for all three arms. The total-C tail is beyond +-10 % at p95 for Innovus and OpenROAD
(label: tail indicative). Ground C alone differs by 12 to 19 % median because the tools split ground and coupling differently; total C does not.
**Judge sensitivity (PrimeTime nom_tt, base SDC, Quantus SPEF instead of StarRC SPEF, same netlist):** setup WNS +18 to +66 ps, hold WNS +2 to +43 ps,
power at most 0.7 %, no verdict or ranking change. Quantus takes about 2.5 min and 1.0 to 1.2 GB per extraction.
The nom qrcTechFile comes from the 2026-10 Techgen cell-level run plus `Techgen -migrate`; min and max are generated by a running chain
(`pnr/commercial/signoff/quantus/scripts/chain_all.sh`) and are not in the JSON yet.

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

1. **OpenROAD post-route LEC** was never run. Run Formality or Conformal of `runs/openroad`
   `rv32i_cpu_top.nl.v` against RTL, with negative controls.
2. **Magic `nwell.4` outside the SRAMs** is open on all arms (3,626 / 3,035 + 592 / 4,226 + 737).
   Root-cause the 1,191 Innovus-specific pocket tap wells and the +145 straddle items
   (`reports/innovus_b6_report.md` section 8). Then decide waiver vs fix per class with the owner.
3. **Per-view clk_io latency** (6.66 / 3.05 / 1.95 ns) in the Innovus own SDC and in the iolat
   variant, to remove the ss/ff I/O artefacts (caveat 4).
4. **ICC2 b6 ss hold** (42 / 31 / 66 I/O-port violators in iolat) and its ff reg-to-reg hold
   (2 / 8). Add ss as a hold scenario, or close them with a PrimeTime ECO.
5. **Deck antenna**: ICC2 b6 1 net (`u_core_u_dcache/n3594`), Innovus b6 2 side-area nets,
   OpenROAD 116.
6. **Max-cap on the 160 SRAM `dout0` pins** (all arms) depends on the TT-only SRAM Liberty. It
   needs per-corner SRAM characterisation (bead `o1i`).
7. **Extraction calibration to silicon or a foundry deck** does not exist. Optionally recalibrate
   the corner multipliers on design total C (0.8988 / 1.0933) rather than on wire slope. The Quantus
   cross-check is done for nom (section 4.8); min and max are pending.
8. **RedHawk** needs characterised decap and APL, a package model, and a decap ECO on ICC2 before
   any dynamic IR verdict.
9. **Single-variable P&R comparison**: run all three P&R tools on one netlist (for example the DC v2
   or Genus netlist through OpenROAD) to separate synthesis from P&R.
10. **OpenROAD peak RSS** is not recorded. Wrap the LibreLane run in `/usr/bin/time -v` next time.
11. Phase D (FreePDK45, ASAP7, the Sky130 SoC) and the Phase C suite back-port, per the plan.

## 8. Files

- `pnr/commercial/compare/compare.py`: builds `comparison.json`. It reads committed files only and
  starts no EDA tool.
- `pnr/commercial/compare/snapshot_sources.py`: one-time copy of run-directory results into
  `compare/snapshot/`, plus the b6 LEC report copies into `signoff/lec/*/reports/`.
- `pnr/commercial/compare/test_compare.py`: checks that every JSON value has a source in the git
  index, that the final arms are complete with no md5 warnings, and that the committed JSON is
  current.
- Underlying reports: `pnr/commercial/reports/` (`pt_judge_summary.md` sections 13 and 14,
  `icc2_pnr_summary.md`, `innovus_b6_report.md`, `redhawk_ir_summary.md`,
  `starrc_extraction_summary.md`, `lec_*.md`, `synth_ss_probe_step1.md`,
  `dc_synth_v2_summary.md`).
