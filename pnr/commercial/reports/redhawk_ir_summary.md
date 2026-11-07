# RedHawk static and vectorless dynamic IR, three flows, Sky130 `rv32i_cpu_top` (phase B7)

**Every figure here is indicative.** The RedHawk tech file is authored from the public Sky130 stack (ITF, uncorrelated), cell current models are RedHawk defaults (no APL characterised), decap capacitance is an estimate from the cell spice, and the supply is an assumed edge feed. Read the static numbers as "the grid is not the problem" and the dynamic numbers as a comparison under one stated model, not as a signoff verdict.

Tool: Ansys RedHawk 2025 R2.2 (`redhawk -b`), power and STA windows from PrimeTime/PrimePower X-2025.06. Scripts in `pnr/commercial/signoff/redhawk/scripts/`, run dirs `signoff/redhawk/runs/<arm>/` (gitignored), compact JSON per arm in `signoff/redhawk/reports/`.

## 1. Inputs (identical recipe for the three arms)

| | ICC2 b6 | Innovus b6 | OpenROAD |
|---|---|---|---|
| final DEF | `impl/icc2/runs/b6_icc2/out/rv32i_cpu_top.def` | `impl/innovus/runs/b6_innovus/out/rv32i_cpu_top.def` | `runs/openroad/rv32i_cpu_top.def` |
| SPEF (StarRC, tuned ITF, nom) | `signoff/starrc/runs/icc2b6_nom/` | `.../innovusb6_nom/` | `.../openroad_nom/` |
| netlist for power | `rv32i_cpu_top.nl.v` of the same run | same | same |
| DEF components | 632 459 (523 316 `fill_N`, 4 210 decap_3) | 471 051 | 556 962 |
| decap cells in DEF / estimated C | 4 210 / 0.03 nF | 357 658 / 12.9 nF | 307 531 / 11.8 nF |
| PrimePower power fed to RedHawk | 70.764 mW | 76.215 mW | 93.131 mW |

- **Power source (same for all arms).** `signoff/redhawk/scripts/pt_export.tcl`: the judge's PrimeTime setup (shared base SDC, md5 `3c696350...`, propagated `clk_i`, StarRC nom SPEF, tt lib plus TT SRAM db), PrimePower vectorless variant B (0.1 toggle / 0.5 static probability on the primary inputs and on every register output pin). Per-leaf-cell `internal + switching + leakage` is written as the RedHawk `INSTANCE_POWER_FILES`. The totals reproduce `pt_judge_summary.md` sections 13/14 (70.8 / 76.2 / 93.1 mW) and RedHawk's own `power_summary.rpt` total equals them to 3 digits. 100 % of the IPF instances matched a DEF instance in all three arms.
- **STA windows.** `write_rh_file -filetype irdrop` from the same PrimeTime session (clock `clk_i`, 75 MHz, 13.333 ns).
- **Tech / LEF / Liberty.** `pdk/sky130/build/redhawk/sky130A_nom.tech` (B1: ITF run through Ansys `adsTechConverter.pl`; DC-average EM limits from the tech LEF; no li1/poly EM limit, no temperature coefficients, no AC-RMS limits), `sky130_fd_sc_hd__nom.tlef`, `sky130_fd_sc_hd.lef`, `sky130_ef_sc_hd.lef`, SRAM LEF; tt Liberty plus the patched SRAM Liberty; a small custom lib giving PG arcs (`VPWR VGND`) for the fill and `ef_sc_hd` cells.
- **Supply.** The macro has no pad ring. Ideal 1.8 V / 0 V sources, zero pad, bondwire and package R/L, one at each end (2 um inside) of every met5 PG stripe: 18 VPWR plus 18 VGND stripes, 72 sources per arm (`scripts/gen_ploc.py`). Total pad current equals P/1.8 V (39.31 / 42.34 / 51.74 mA).
- **SRAM macros.** The 10 `sky130_sram_1kbyte_1rw1r_32x256_8` instances are treated as lumped current sinks at their PrimePower power (2.89 mW each, 29.0 mW total, 41 % of the ICC2 total) drawn through their `vccd1`/`vssd1` pins, which every DEF ties to VPWR/VGND. No per-pin current profile exists for them; RedHawk builds a default virtual memory model (AVM warning `AVM-233`, `C_DECAP` missing).
- **Decap (assumption).** RedHawk does not read capacitance from the Sky130 decap cells, so `DECAP_CELL` is declared from the spice W/L: C = (Wn + Wp) L Cox with Cox 8.4 fF/um2 (tox 4.1 nm), R = Rn || Rp / 3 (`reports/decap_estimate.txt`; decap_12: 56.6 fF, 8.8 kohm). These are estimates, not characterised values.
- **Dynamic.** `perform analysis -vectorless`, 20 ps step, 28 ns window, presim 3.5 ns, `MULTI_THREADS 1 2`. Cell currents are the Liberty-derived defaults ("All slews in APL cell current profiles are the same"; no APL for standard cells).

## 2. Result: static IR (VPWR drop / VGND bounce, 1.8 V)

| | ICC2 b6 | Innovus b6 | OpenROAD |
|---|---|---|---|
| RedHawk total power (mW) | 70.76 | 76.22 | 93.13 |
| **VPWR drop, worst** (mV / % of 1.8 V) | **12.1 / 0.67 %** | **9.0 / 0.50 %** | **12.4 / 0.69 %** |
| **VGND bounce, worst** (mV / %) | **11.8 / 0.66 %** | **9.0 / 0.50 %** | **12.3 / 0.68 %** |
| VPWR + VGND, worst instance (mV / %) | 23.9 / 1.33 % | 18.0 / 1.00 % | 24.7 / 1.37 % |
| VPWR + VGND, mean over logic cells (mV) | 15.3 | 11.9 | 19.2 |
| worst SRAM macro, VPWR + VGND (mV) | 21.7 | 18.0 | 22.9 |
| static EM, metal / via violations | 0 / 0 | 0 / 0 | 0 / 0 |
| worst static EM ratio (DC average vs tech-LEF limit) | 6.4 % met5 wire, 5.9 % via4 | 6.9 % met5 wire, 6.1 % M4M5 via | 8.4 % met5 wire, 6.5 % via5 |

Instance values are printed at 0.1 mV resolution. "Worst instance" includes fill and tap cells because they sit on the same rails; the logic-cell and SRAM populations give the same worst values within 0.1 to 2 mV (full split in `reports/*_static_summary.json`).

Top static hotspots (200 um tiles, mean VPWR+VGND over logic and SRAM instances):
- ICC2: x 2000-2200 / y 0-200 (21.7 mV), x 1800-2000 / y 0-200, x 2000-2200 / y 200-400. Worst instance `u_core_u_dcache/U2824` at (2061, 453), worst wire on met1 at (2074, 454).
- Innovus: same three tiles (17.9 / 17.8 / 17.6 mV). Worst instance `B6REP_57` at (2033, 31).
- OpenROAD: x 2000-2200 / y 200-400 (22.9 mV), x 1600-1800 / y 400-600, x 2000-2200 / y 0-200. Worst instance `clkbuf_0_clk_i` at (1857, 896).

All three put the static worst region in the middle of the die, 1500 to 2000 um from the stripe-end sources, around the I/D-cache SRAM row (y 200 to 600). With the edge feed the drop is dominated by the met1 rail and by the met5 stripe length, so the spread across tools mostly follows the total current (93 mW for OpenROAD against 71 mW for ICC2) and the rail/tap pattern, not a defect.

## 3. Result: vectorless dynamic IR (default current models, estimated decap)

Drop = 1.8 V - (VDD-VSS) seen by the instance. `avgTW` is the average over the instance's switching window (RedHawk's headline instance number); `minWC` is the lowest value of the waveform at any time.

| | ICC2 b6 | Innovus b6 | OpenROAD |
|---|---|---|---|
| **worst avgTW, logic + SRAM** (mV / %) | **192.6 / 10.7 %** | **163.2 / 9.1 %** | **79.1 / 4.4 %** |
| worst minWC (mV / %) | 208.0 / 11.6 % | 171.8 / 9.5 % | 123.8 / 6.9 % |
| **mean avgTW** over logic + SRAM (mV / %) | **59.9 / 3.3 %** | **22.1 / 1.2 %** | **40.7 / 2.3 %** |
| instances with avgTW above 5 % / 10 % of VDD | 19.9 % / 0 % | 0 % / 0 % | 0 % / 0 % |
| worst SRAM macro avgTW / minWC (mV) | 113.4 / 170.9 | 71.8 / 109.2 | 53.2 / 95.0 |
| worst wire drop VPWR / VGND (mV) | 105.2 / 102.8 | 96.5 / 75.8 | 63.0 / 60.8 |
| dynamic EM, AVG mode: segments at or above 50 % | 0 (worst 7.2 %) | 0 (worst 8.6 %) | 0 (worst 9.0 %) |
| dynamic EM, RMS mode: segments at or above 50 % | 0 (worst 27.6 %) | 0 (worst 22.8 %) | 0 (worst 26.3 %) |
| dynamic EM, PEAK mode: segments at or above 100 % | 658 (worst 164 %, met1) | 384 (worst 213 %, met4) | 451 (worst 152 %, met1) |
| **no-decap sensitivity**: worst avgTW (mV / %) | 193.4 / 10.7 % | 248.6 / 13.8 % | 209.7 / 11.6 % |
| no-decap sensitivity: mean avgTW (mV) | 59.6 | 42.5 | 56.8 |
| decap instances RedHawk used | 4 210 | 357 658 | 307 531 |

Top dynamic hotspots (mean avgTW per 200 um tile):
- ICC2: x 2000-2200 / y 200-400 (86.5 mV), x 1400-1600 / y 1200-1400, x 2000-2200 / y 400-600. Worst instances are `u_core_u_dcache/refill_buf_q_reg_3__21_` (2234, 453; 193 mV) and `..._1__15_`: the d-cache refill buffer next to the data SRAM row.
- Innovus: x 2800-3000 / y 400-600 (46.2 mV), x 1000-1200 / y 600-800. Worst instances `u_core/FE_OFC1360_u_dcache_data_dout0_3__9` at (2900, 518) and `FE_OFC2889_...` (d-cache data output buffers, 163 mV).
- OpenROAD: x 1000-1200 / y 0-200 (52.0 mV), x 1800-2200 / y 1000-1200. Worst instances are antenna diodes and wire repeaters near the i-cache data SRAM output at (1317, 37), 79 mV.

How to read the dynamic table:
1. **The ranking is decap-dependent, not only grid-dependent.** Without any decap model the worst-case drop is 193 / 249 / 210 mV (ICC2 / Innovus / OpenROAD); with the estimated decap it becomes 193 / 163 / 79 mV. ICC2 is unchanged because its layout carries almost no decap (it was filled with `fill_N`, 4 210 endcap decap_3 only); Innovus and OpenROAD gain 85 and 130 mV from roughly 12 nF each. The large gap between Innovus and OpenROAD at equal total decap was not isolated (INFERRED: local decap density and current concentration near the d-cache data outputs differ; not measured).
2. **Mean drop** (3.3 % ICC2, 2.3 % OpenROAD, 1.2 % Innovus) is the more stable figure; the worst-instance figure is set by a few hundred flops and buffers with unlucky local decap and a default current shape.
3. **PEAK-mode EM** compares peak current with the DC-average limit from the tech LEF, which the vendor does not publish as a peak limit. The 384 to 658 "violations" are all on met1 rails (Innovus also met4/met5) and are an artefact of that comparison. AVG (true average) and RMS (against the DC limit, no AC-RMS limit exists) show no violation and a worst ratio of 7 to 28 %. Treat EM as: no violation on power/ground metal in static or in dynamic AVG/RMS, peak not judged.

## 4. Against the signoff criterion (`ir_drop_pct < 5 %`, worst of static and dynamic)

| | ICC2 b6 | Innovus b6 | OpenROAD |
|---|---|---|---|
| static | 1.37 % max across arms: **pass** (indicative) | **pass** | **pass** |
| dynamic, worst instance avgTW | 10.7 % (above 5 %) | 9.1 % (above 5 %) | 4.4 % (below 5 %) |

This is not a verdict. The dynamic numbers rest on estimated decap and default currents, so the criterion is reported as measured and labelled indicative; a fair dynamic gate needs decap characterised for the real cells (and ICC2/Innovus ECO'd with decap), APL, and a package model.

## 5. Assumptions and what is not closed

- Tech file uncorrelated (authored ITF, nominal only, no temperature coefficient, no li1/poly EM limit, no AC-RMS limit, `EM_Adjust` 1.0). R of the grid has not been checked against any other extractor (Totem or Voltus were not available here); only the three arms are compared with each other.
- Supply is an idealised edge feed (met5 stripe ends). In a parent SoC the macro is overlaid by the parent grid on met4/met5, so the static drop of a real integration would be smaller; no package or board R/L is included, so dynamic would be worse than here at the package level.
- No APL: standard-cell currents, intrinsic cell capacitance and the SRAM current profile are RedHawk defaults; SRAM is a constant sink at its PrimePower average, with no access-pattern peak.
- Decap values are estimates from spice W/L (unvalidated); decap is the dominant dynamic lever in this analysis.
- Power is PrimePower variant B at nom_tt with activity 0.1 / 0.5. It is an average-power operating point, not a worst-case activity vector; the vectorless dynamic switching scenario is RedHawk's default, not a real workload.
- Signal-net EM and thermal were not run (tech has no signal EM data). The ICC2 DEF has five `DEF-019` errors (signal-net vias `mcon_cc/via_cc/via2_cc` absent from the tech LEF and DEF `VIAS`); the run used `IGNORE_DEF_ERROR 1`, which drops only those signal vias and cannot affect PG analysis.
- ICC2 and Innovus layouts differ from OpenROAD in more than the tool: fill versus decap choice (ICC2 `fill_N` only) and PDN details. The comparison is of the delivered layouts, not of the router or PDN engines.
- Quantus / StarRC SPEF correlation is out of scope here; the SPEFs used are the tuned StarRC ones the judge uses.

## 6. Reproduce

```
bash pnr/commercial/signoff/redhawk/scripts/run_pt_export.sh <icc2b6|innovusb6|openroad>   # PrimePower per-instance power + .timing
python3 -I scripts/gen_ploc.py <def> runs/<arm>/rh/pg.ploc ; python3 -I scripts/gen_ipf.py <def> runs/<arm>/pt/instance_power.txt runs/<arm>/rh/power.ipf
python3 -I scripts/gen_rh_inputs.py <arm>                                                # GSR + tcl (+ no-decap variant)
scripts/chain.sh static ; scripts/chain.sh dynamic ; scripts/chain.sh dynamic-nodecap    # sequential, .done markers, licensed_lock + safe_run
python3 -I scripts/collect_static.py <arm> ; python3 -I scripts/collect_dynamic.py <arm> rh-dynamic[-nodecap] ; python3 -I scripts/tables.py
```
Cost per run (2 threads): static 40 to 46 s wall, dynamic 64 to 78 s wall, peak RSS 1.0 to 1.4 GB by `time -v`.
