# Quantus vs StarRC extraction cross-check, Sky130 `rv32i_cpu_top` (plan step B1/B6 remainder)

Status: **nom, min and max complete** (Techgen for all three corners, Quantus on the three arms at all three corners; every step rc 0). Numbers below are measured unless marked inferred.
Everything here is **INDICATIVE in the sense of the plan's calibration gate**: both extractors read the *same authored stack*
(`pdk/sky130/build/tech/ict/sky130A_<corner>.ict` for Quantus, the matching ITF for StarRC). Agreement between them says the two engines
interpret the stack alike. It says nothing about silicon or a foundry deck.

## 1. What was built

| Item | Value |
|---|---|
| Tool | Cadence Quantus / Techgen 23.1.1-p051 (`QUANTUS231_ISR1`) |
| Input | authored ICT per corner (uniform dielectric-constant and resistivity scaling for min/max), unchanged from the StarRC ITF's source data |
| Techgen flow used | `Techgen -cell -plan`, `-cell -parallel -autoconcat -hideprocess` (cell-level models, `RCGEN`), then `Techgen -migrate -rcgen RCGEN qrcTechFile`. Script: `pnr/commercial/pdk/sky130/scripts/run_techgen_cell.sh` |
| Why not `Techgen -simulation_FS_off` | it adds a transistor-level 2-D pass the DEF flow never reads (about 6 h) and its last step ("cell-level models update") needs `rcxfs.dat`, which `-simulation_FS_off` never writes: 10 `nebula` processes segfault with NEBULAM-135091 and the run never finishes (reproduced on a copy of the 2026-10-29 scratch, 2 min). The earlier partial `qrcTechFile` from that run is rejected by Quantus: `EXTGRMP-354 no cell-level data in the unified techfile` |
| Why the migrate step | a bare `RCGEN` is not accepted either (same EXTGRMP-354). `-migrate -rcgen RCGEN` wraps it into the unified file in 2 s. A `-migrate` that also adds the transistor-level `caps2d`/`cap_coeff.dat`/`paxfile_coeff` gives the same extraction: net-by-net total C differs by at most 0.096 %, R identically (Innovus b6, nom) |
| Quantus command | `input_db -type def` (same DEF and LEF set as the StarRC run), `extraction_setup -technology_layer_map` (tech-LEF `via` to ICT `via1`; the other layers have the same name), `extract -type rc_coupled`, `filter_coupling_cap` absolute 0.1 fF / relative 0 / total 0 (StarRC: `COUPLING_ABS_THRESHOLD 0.1`), 25 C, SPEF standard. Script: `pnr/commercial/signoff/quantus/scripts/gen_cmd.sh` |
| DEFs | ICC2 b6 `impl/icc2/runs/b6_icc2/out`, Innovus b6 `impl/innovus/runs/b6_innovus/out`, OpenROAD `runs/openroad` (the DEFs the StarRC SPEFs of the PT judge came from) |

### Techgen cost (nom)

| Run | Result | Wall | Peak RSS |
|---|---|---|---|
| 2026-10-25/29 `-simulation_FS_off -2d_only` (single CPU, then 2 CPUs; host powered off twice) | transistor-level 2-D done; cell level done ("CPU Time to generate technology file = 5.83 hours", `RCGEN` 2.0 MB); last step crashed | not meaningful (outages); 2-D phase 5.9 h, cell-level restarted 3 times | not recorded |
| `Techgen -migrate` over that `RCGEN` (the final step) | `qrcTechFile` 2.0 MB, rc 0 | 2 s (0.45 s `time -v`) | 22.8 MB |
| **Fresh `Techgen -cell`, min, 2 CPUs, 2026-11-07 11:52** | `RCGEN` + `qrcTechFile` 2.0 MB, rc 0 | **3 h 19 min** (11,962 s; plan 4 s, migrate 2 s) | **440 MB** session peak |
| **Fresh `Techgen -cell`, max, 2 CPUs, 2026-11-07 15:30** | `RCGEN` + `qrcTechFile` 2.0 MB, rc 0 | **3 h 17 min** (11,849 s; plan 4 s, migrate 3 s) | **445 MB** session peak |
| Fresh `Techgen -cell` re-run of nom, 2 CPUs, 2026-11-07 09:41 | **stopped at 39 % after 1 h 45 min** to free the host (resumable, `build/qrc/nom.fresh_partial_20261107_39pct`); rate fell from 2 %/3 min to 1 %/6-9 min after 36 % | 1 h 45 min for 39 % (inferred total about 3.3 h, from the min/max runs: the rate falls after 36 %) | 455 MB session peak (sum over the process session, 20 s samples) |

min and max are single fresh end-to-end `run_techgen_cell.sh` runs (`build/qrc/{min,max}/techgen_cell.timing`).

**The nom `qrcTechFile` used below is therefore the one from the 2026-10 `RCGEN` (same ICT: `cmp` identical to the current `sky130A_nom.ict`) plus the migrate step, not a single fresh end-to-end run.** `build/qrc/nom/PROVENANCE.txt` says so.

## 2. Quantus run cost (2 CPUs requested, `safe_run.sh`)

| Arm | Wall | Session peak RSS | Nets extracted | Errors |
|---|---:|---:|---:|---:|
| ICC2 b6 | 2 min 17 s | 0.97 GB | 41,413 | 0 |
| Innovus b6 | 2 min 32 s | 1.23 GB | 46,661 | 0 |
| OpenROAD | 2 min 24 s | 1.17 GB | 42,196 | 0 |

min: ICC2 133 s / 1.05 GB, Innovus 514 s / 1.25 GB (cold cache after the 3.3 h Techgen run), OpenROAD 86 s / 1.18 GB. max: ICC2 69 s / 1.02 GB, Innovus 73 s / 1.24 GB, OpenROAD 107 s / 1.19 GB. All 9 runs: 0 errors, same net counts at every corner.

(StarRC: about 2.3 min and 0.52 GB for the ICC2 case.) Quantus used one CPU for most stages despite `-multi_cpu 2`. The incomplete-net lists
(16 to 660 nets, "no physical wire") are the loadless/driverless nets StarRC also leaves out.

## 3. Per-net correlation, Quantus against StarRC (nom, then min and max)

Population: nets present in both SPEFs with StarRC total C above 1 fF (the calibration-gate population). Error = (Quantus / StarRC - 1) x 100.
"Outside" = share of nets with |error| above 10 %.

| Arm | Quantity | Nets | Median error % | Median \|error\| % | p95 \|error\| % | Outside 10 % | r (log-log) |
|---|---|---:|---:|---:|---:|---:|---:|
| ICC2 b6 | total C | 39,348 | -3.12 | 3.75 | 9.75 | 4.5 % | 0.9995 |
| ICC2 b6 | total R | 39,348 | +1.53 | 1.58 | 2.59 | 2.4 % | 0.9890 |
| ICC2 b6 | ground C | 39,348 | -16.49 | 18.73 | 45.47 | 72.9 % | 0.9819 |
| Innovus b6 | total C | 41,688 | +2.10 | 4.60 | **19.59** | 22.2 % | 0.9985 |
| Innovus b6 | total R | 41,688 | +1.34 | 1.46 | 4.98 | 4.2 % | 0.9853 |
| Innovus b6 | ground C | 41,688 | +5.92 | 16.05 | 53.76 | 67.4 % | 0.9837 |
| OpenROAD | total C | 37,897 | -2.33 | 3.57 | **12.68** | 9.9 % | 0.9993 |
| OpenROAD | total R | 37,897 | +1.60 | 1.66 | 3.08 | 3.9 % | 0.9915 |
| OpenROAD | ground C | 37,897 | +3.76 | 11.58 | 48.02 | 55.6 % | 0.9904 |

Design totals (all nets, Quantus / StarRC): C 0.963 (ICC2), 1.019 (Innovus), 0.986 (OpenROAD); R 0.983, 0.954, 0.971; coupling C 1.055, 1.010, 0.961.

### min and max corners

| Arm | Corner | Total C median % | Total C p95 \|err\| % | Outside 10 % | Total R median % | Total R p95 \|err\| % | Ground C median % | Design C / R ratio |
|---|---|---:|---:|---:|---:|---:|---:|---|
| ICC2 b6 | min | -3.11 | 9.39 | 4.0 % | +2.71 | 5.89 | -16.42 | 0.961 / 0.981 |
| ICC2 b6 | max | -3.13 | 9.96 | 4.9 % | +0.81 | 1.26 | -16.72 | 0.962 / 0.987 |
| Innovus b6 | min | +2.02 | **19.13** | 20.9 % | +2.05 | 7.53 | +6.11 | 1.015 / 0.951 |
| Innovus b6 | max | +1.69 | **19.19** | 22.0 % | +0.78 | 4.10 | +5.72 | 1.014 / 0.962 |
| OpenROAD | min | -2.23 | **12.03** | 8.7 % | +2.93 | 7.07 | +3.96 | 0.986 / 0.967 |
| OpenROAD | max | -2.39 | **13.16** | 10.7 % | +0.80 | 1.54 | +3.50 | 0.985 / 0.978 |

The corner dependence is small: total-C medians move by at most 0.5 point between nom, min and max. Total R is the only quantity with a corner trend (median +2.7..+2.9 % at min, +0.8 % at max,
against +1.3..+1.6 % at nom), probably because the min/max resistivity and via-resistance scaling is realised differently by the ICT (Quantus) and the ITF/TCAD tables (StarRC) (inferred, not isolated). All nine cases pass the median gate on total C and total R;
the total-C tail beyond +-10 % at p95 (Innovus about 19 %, OpenROAD 12..13 %) is the same at every corner, so it is a structural per-net difference, not a corner-scaling error. Full table: `signoff/quantus/reports/quantus_vs_starrc.md`.

Reading against the plan's gate (beyond +-10 % is *indicative*):
- **Total C and total R pass on the median for all three arms** (median |error| 1.5 to 4.6 %). Total R is tight everywhere (p95 under 5 %).
- **Total C has a tail beyond +-10 %** at p95 for Innovus b6 (19.6 %) and OpenROAD (12.7 %); ICC2 b6 is just inside (9.75 %). Flagged `tail_beyond_10pct` in the JSON. Median-gate verdict: within gate; tail: indicative.
- **Ground C alone disagrees by 12 to 19 % (median) and 45 to 54 % (p95).** Total C agrees much better, so the two tools split ground and coupling differently
  (StarRC `COUPLE_TO_GROUND: NO` against Quantus' treatment of shapes with no net, fill and the 0.1 fF coupling filter). The ICC2 arm shows it most (design ground C 0.81, coupling 1.055).
  This is a convention difference, not evidence that either tool is wrong. It matters to anything that lumps coupling to ground, such as PrimeTime's default read (the judge).
- Net-name matching: 8, 330 and 95 StarRC nets have no Quantus counterpart (ICC2, Innovus, OpenROAD); Quantus has none that StarRC lacks.

## 4. PrimeTime sensitivity: Quantus SPEF instead of StarRC SPEF (nom_tt, base SDC, same netlist)

Run with `PT_SET=quantus PT_STARRC_DIR=pnr/commercial/signoff/quantus/runs PT_NO_MARKER=1 scripts/run_one.sh <arm> nom tt 1` (the judge scripts, unchanged apart from the marker switch in `arms.sh`).
Annotation gate: 0 unannotated pin-to-pin nets in all three runs.

| Arm | Setup WNS ns (StarRC / Quantus) | Hold WNS ns | Hold violators | Power mW (PrimePower) |
|---|---|---|---|---|
| ICC2 b6 | 3.314 / 3.379 (+0.066) | -1.230 / -1.187 | 556 / 547 | 70.8 / 70.3 |
| Innovus b6 | 2.455 / 2.486 (+0.031) | -1.929 / -1.901 | 455 / 429 | 76.2 / 76.4 |
| OpenROAD | 3.172 / 3.190 (+0.018) | -0.319 / -0.316 | 51 / 42 | 93.1 / 93.1 |

Setup WNS moves by +18 to +66 ps, hold WNS by +2 to +43 ps, power by at most 0.7 %. **The ranking of the arms and every pass/fail verdict are unchanged**
(the base-SDC hold failures are the known I/O-latency artefact of that SDC, see `pt_judge_summary.md`). The sensitivity is small next to the arms' differences.
PrimeTime took 8 min on the first ICC2 read of the Quantus SPEF (cold cache) and 27 to 30 s on the others (StarRC SPEFs: 19 to 162 s).

## 5. Gotchas found (also in `memory/pd/knowledge.md`)

1. `Techgen -simulation_FS_off` never writes `rcxfs.dat`; the unified flow's last step needs it. Use `-cell` + `-migrate -rcgen`.
2. Quantus cell-level flow rejects both a bare `RCGEN` and the partial unified file (`EXTGRMP-354`).
3. `process_technology -technology_directory` is LVS-only (`EXTQRCXOPT-266`); cell level needs `-technology_library_file <cds.lib-style file>` (`DEFINE <name> <dir>`) plus `-technology_name`.
4. `extraction_setup -technology_lef_map_file` maps tech LEFs to DEFs, not layers (it produced `Cpp-99: absolute path to "li1" could not be resolved`). Layer names go through `-technology_layer_map <lef> <ict> ...`. LEF `nwell`/`pwell` are reported unmapped and ignored.
5. A `$(...)` that starts a background sampler hangs unless the sampler redirects stdout.
6. Techgen `-cell` progress is not linear: 36 % in 75 min, then 3 % in the next 40 min.
7. The ICT keeps the conductor named `li1`; the `li1` to `met0` rename (`mk_ict_li1m1.py`) is only needed for Innovus `generateCapTbl` and was not needed for Quantus.

## 6. Not closed

- The nom Techgen figure is not a single fresh end-to-end run (section 1); min and max are. The fresh nom re-run (39 % done) is resumable but was not completed, since the min/max runs show it would take about 3.3 h and the nom `RCGEN` already used is from the same ICT.
- Agreement is between two extractors reading one authored stack. There is still no calibration to silicon or a foundry deck.
- The total-C tail (p95 above 10 % for Innovus b6 and OpenROAD) is reported, not diagnosed per net.
- PrimeTime sensitivity was run at nom_tt only, as planned.
