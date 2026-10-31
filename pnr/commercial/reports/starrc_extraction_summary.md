# StarRC neutral-judge extraction, Sky130 `rv32i_cpu_top` (step B1 part 2b + B6a)

Scope: PD `extraction` stage only. StarRC X-2025.06-SP1 (`StarXtract`) reads each arm's routed DEF and writes one SPEF
per corner (nom/min/max) for the separate STA agent. No STA, P&R or other stage was run. Everything ran through
`pnr/commercial/pdk/sky130/scripts/safe_run.sh` (load/memory gate, process-group kill), 2 cores, one extraction at a time.

**Status**: OpenROAD and ICC2 arms done (6 SPEFs). **Innovus: PENDING (b5c reroute)**: `impl/innovus/runs/b5c_innovus/out/rv32i_cpu_top.def`
did not exist when this ended (empty `out/`). One command extracts it once the DEF is complete: `make -C pnr/commercial/signoff/starrc innovus`.
The old b5b Innovus DEF was smoke-extracted once before the coordinator's scope change; those runs were moved to
`runs/_superseded_b5b/` and are not used anywhere below.
**Quantus: skipped.** `pdk/sky130/build/qrc/nom` has no `qrcTechFile` yet (Techgen nom still running, `-restart -multi_cpu 2`, left alone).

**Every number here rests on an authored, uncalibrated ITF** (`pdk_enablement_sky130.md`), not a foundry StarRC deck.

## 1. Files

| Item | Path |
|---|---|
| Command-file generator (the template) | `pnr/commercial/signoff/starrc/scripts/gen_cmd.sh` |
| One extraction under safe_run | `scripts/run_starrc.sh <arm> <corner>` (time + peak RSS to `runs/<arm>_<corner>/time.txt`) |
| DEF per arm | `scripts/arms.sh` |
| Supplementary LEF for ICC2's via names | `scripts/icc2_via_names.lef`, from `scripts/gen_icc2_via_lef.py` |
| SPEF parser / correlation / stats | `scripts/spef_stats.py`, `scripts/correlate.py`, `scripts/collect_stats.py` |
| Makefile | `pnr/commercial/signoff/starrc/Makefile` (`smoke`, `corr-extract`, `judge` = OpenROAD+ICC2, `innovus`, `corr`, `stats`) |
| Judge SPEFs (gitignored) | `pnr/commercial/signoff/starrc/runs/<arm>_<corner>/rv32i_cpu_top.<corner>.spef` for arm in `openroad`, `icc2` (Innovus pending) |
| Committable reports | `pnr/commercial/signoff/starrc/reports/` (`correlation_{nom,min,max}.md`, `correlation_icc2native_nom.md`, `per_arm.md`) |

## 2. StarRC command file (identical for every arm and corner)

Only the DEF, the nxtgrd/tech-LEF corner and the output paths change. Generated for icc2/nom:

```
BLOCK: rv32i_cpu_top
TCAD_GRD_FILE: pnr/commercial/pdk/sky130/build/nxtgrd/<corner>/sky130A_<corner>.nxtgrd
MAPPING_FILE: runs/<arm>_<corner>/sky130.map
LEF_FILE: $SKY130_HD_TLEF[_MIN|_MAX]            (sky130_fd_sc_hd__{nom,min,max}.tlef)
LEF_FILE: sky130_fd_sc_hd.lef
LEF_FILE: sky130_ef_sc_hd.lef                   (decap_12 filler cells in the OpenROAD DEF)
LEF_FILE: sky130_sram_1kbyte_1rw1r_32x256_8.lef (macros: pin geometry only, no OBS/internal extraction)
LEF_FILE: scripts/icc2_via_names.lef
TOP_DEF_FILE: <routed DEF of the arm>
STAR_DIRECTORY: runs/<arm>_<corner>/star
EXTRACTION: RC
COUPLE_TO_GROUND: NO                            (coupling caps kept, for SI later)
REDUCTION: NO_EXTRA_LOOPS
OPERATING_TEMPERATURE: 25                       (same for all corners; the ITF carries no temperature coefficients)
NETS: *
POWER_EXTRACT: NO                               (signal nets only)
NETLIST_FORMAT: SPEF
NETLIST_FILE: runs/<arm>_<corner>/rv32i_cpu_top.<corner>.spef
SHORTS_LIMIT: 1000000                           (default 1000 truncates the short report)
NUM_CORES: 2
```

SRAM macros are black boxes: StarRC takes the macro as a LEF cell, and its pin shapes connect the net wiring; nothing inside the macro is
extracted and `PIN_CAP NONE` (no cell pin capacitance in either tool's SPEF, so comparisons are like for like).

**Mapping file** (`runs/*/sky130.map`; `starrc_layer.map` minus its `#` comment lines):

```
conducting_layers
li1 li1
met1 met1
met2 met2
met3 met3
met4 met4
met5 met5
via_layers
mcon mcon
via via1
via2 via2
via3 via3
via4 via4
```

Smoke-test findings on layers and connectivity (OpenROAD DEF, nom): the mapping parses; unmapped LEF layers are only `nwell`, `pwell`, `licon`
(SX-2086; `licon` "has no VIA connection", SX-2076), none used by routing, so ignored. 0 open nets, 0 shorts, 0 errors. Net count
42,291 = DEF `NETS`. The 87 zero-C nets are empty nets (no routing, no pins that touch wires).

## 3. Correlation gate: StarRC vs OpenRCX, OpenROAD DEF

Both tools read the same DEF. OpenRCX SPEFs are the ones the OpenROAD flow wrote (`pnr/commercial/runs/openroad/rv32i_cpu_top.{min,nom,max}.spef`).
Ratio = StarRC / OpenRCX per net, population = nets in both with OpenRCX total C > 1 fF. Total C = ground + coupling, as in both SPEF headers.

| Corner | Nets | C median | C p5 | C p95 | C r (lin / log-log) | C outside +-10 % | R median | R p5 / p95 | R r (lin) | Total design C, StarRC vs OpenRCX | Label |
|---|---|---|---|---|---|---|---|---|---|---|---|
| nom | 34,081 | **1.135** | 0.963 | 1.406 | 0.9957 / 0.9987 | 21,872 (64.2 %) | 0.976 | 0.963 / 1.037 | 0.9564 | 1023.4 vs 995.0 pF (x1.029) | **INDICATIVE** (median outside +-10 %) |
| min | 32,713 | **1.006** | 0.847 | 1.228 | 0.9948 / 0.9986 | 11,610 (35.5 %) | 0.958 | 0.924 / 1.051 | 0.9518 | 810.5 vs 888.0 pF (x0.913) | median passes the gate; see note |
| max | 35,277 | **1.256** | 1.066 | 1.569 | 0.9968 / 0.9986 | 32,062 (90.9 %) | 0.987 | 0.981 / 1.023 | 0.9726 | 1241.5 vs 1080.1 pF (x1.149) | **INDICATIVE** (median outside +-10 %) |

Further columns (full tables in `signoff/starrc/reports/correlation_<corner>.md`):

| Corner | Ground C median | Coupling C StarRC vs OpenRCX | Coupling share of total C (StarRC / OpenRCX) | Sum R ratio |
|---|---|---|---|---|
| nom | 1.524 | 173.9 vs 273.0 pF (x0.637) | 0.340 / 0.549 | 1.021 |
| min | 1.406 | 134.2 vs 247.1 pF (x0.543) | 0.331 / 0.556 | 1.020 |
| max | 1.550 | 215.5 vs 280.0 pF (x0.770) | 0.347 / 0.518 | 1.017 |

Reading (measured, then inferred):
- Per-net shape agrees very well (r about 0.995 for total C); resistance agrees within a few percent at all corners (median 0.96 to 0.99). Resistance is not the issue.
- Total C is high by 13 % (nom) and 26 % (max) in the median, and about right at min. Design totals are x1.03 / x0.91 / x1.15. The corner spread of the authored ITF (uniform dielectric multiplier 0.79 / 1.21)
  is wider than OpenRCX's (min to max: StarRC 810 to 1242 pF, x1.53; OpenRCX 888 to 1080 pF, x1.22). That is the ITF as authored, a documented design choice, not tuned here.
- Ground/coupling split differs a lot: StarRC puts about 34 % of C into coupling where OpenRCX has about 55 %. INFERRED (not tested): the authored dielectric stack and the 1-D calibration (RMS 1.9 % against Magic area caps only) do not
  constrain lateral coupling and fringe. Any later SI/crosstalk result from these SPEFs is therefore the weakest part.
- The min corner passes the stated median test only by cancellation; 35 % of its nets are outside +-10 % and p5 is 0.85. Treat all three corners as indicative in practice; only nom and max carry the formal label.
- **Rule applied**: nom and max are labelled **INDICATIVE** in every downstream result. No ITF tuning was done.

Reference check, not the gate: StarRC on the ICC2 DEF vs ICC2's own native SPEF (nominal TLU+, derived from the same ITF; no coupling in that SPEF): total C median 1.008, r 0.9997, design 829.8 vs 833.4 pF; R median 0.985
(`reports/correlation_icc2native_nom.md`). So StarRC and ICC2 agree with each other on the authored ITF. The disagreement above is ITF versus OpenRCX's own deck, not a tool problem.

## 4. Per-arm extraction table (StarRC settings identical)

| Arm | Corner | Nets in DEF | Nets in SPEF | Zero-C nets | Open nets | Shorts | Total C (pF) | Ground C | Coupling C | Sum R (Mohm) | Wall | Peak RSS |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| OpenROAD | nom | 42,291 | 42,291 | 87 | 0 | 0 | 1023.4 | 675.6 | 173.9 | 7.77 | 2:29 | 0.56 GB |
| OpenROAD | min | 42,291 | 42,291 | 87 | 0 | 0 | 810.5 | 542.1 | 134.2 | 4.61 | 2:20 | 0.56 GB |
| OpenROAD | max | 42,291 | 42,291 | 87 | 0 | 0 | 1241.5 | 810.4 | 215.5 | 14.48 | 2:20 | 0.56 GB |
| ICC2 | nom | 35,149 | 35,149 | 0 | 0 | 0 | 829.8 | 501.2 | 164.3 | 5.07 | 2:05 | 0.56 GB |
| ICC2 | min | 35,149 | 35,149 | 0 | 0 | 0 | 657.2 | 406.2 | 125.5 | 2.93 | 2:05 | 0.56 GB |
| ICC2 | max | 35,149 | 35,149 | 0 | 0 | 0 | 1006.6 | 595.7 | 205.5 | 9.58 | 2:05 | 0.56 GB |
| Innovus (b5c) | nom/min/max | | | | | | | | | | | **PENDING** |

Peak RSS is `/usr/bin/time -v` (parent plus waited children, 2 cores). Opens: `report_opens NETID1 : 0` in every run. Shorts: `star/shorts_all.sum` empty in every run.
Every SPEF ends in `*END`, rc 0, `.starrc_complete` present. C is in the SPEF D_NET sense: ground + coupling, no pin caps. Net counts differ between arms because the netlists differ (fill, tie and buffer nets), not because of extraction loss.
Do not compare total C across arms as a PPA metric: the DEFs have different cells, wire lengths and fill.

## 5. Caveats

1. **Authored ITF, indicative.** No foundry StarRC deck exists for Sky130. The stack comes from the SkyWater figure plus Magic area caps, fit with a 1-D plate model; lateral coupling, fringe, temperature coefficients, etch bias and density effects are absent.
   The correlation above is the first check against anything independent, and it fails the gate at nom and max.
2. **One temperature (25 C) for all corners** (no tempco in the stack), so ss 100 C / ff -40 C resistance is not temperature-scaled. The three corners differ only by the nxtgrd (R from the tech LEF per corner, C by a uniform dielectric multiplier).
3. **Innovus arm absent**: only the b5c reroute is to be extracted. Its earlier b5b DEF had 1,579 routing shorts; if b5c still shows any, StarRC lists them in `star/shorts_all.sum` and flags the affected nets as unreliable (SX-0955). In the b5b smoke run StarRC reported 1000+ shorts and 0 opens, so shorts show up in the log.
4. **SRAM black boxes**: macros contribute pin shapes only. `LEF_USE_OBS` was left at the StarRC default and its effect was not tested, so whether macro OBS shapes act as coupling neighbours is unverified. Net C near the ten SRAMs may be low (inference).
5. **ICC2 DEF via names**: ICC2 writes its ContactCode names (`mcon_cc`, `via_cc`, `via2_cc`, `via3_cc`, `via4_cc`) into the DEF routing; the PDK LEF has no such vias, so the first ICC2 run reported 33,375 of 35,149 nets open (SX-2064).
   The supplementary LEF `scripts/icc2_via_names.lef` defines them with the `.tf` ContactCode geometry; with it, 0 opens. The same LEF is in every arm's command file. The DEF-internal array vias (`via_cc_1_9`, ...) are self-defined and needed nothing.
6. **Reduction and loops**: `REDUCTION: NO_EXTRA_LOOPS` keeps the full RC network. Total R is the sum of all resistors, which for nets with loops (power-like or mesh) is not the driver-to-sink resistance; fine as a like-for-like statistic, not as a path R.
7. **Single-corner runs** (SX-3552 warns): the three corners were run separately, not as simultaneous multi-corner. Runtime was not a problem (2 min).
8. **Antenna, EM and IR are not in this stage.** Quantus (Cadence) extraction was not run (no `qrcTechFile`).

## 6. Tool gotchas (for the agent suite)

| Symptom | Cause / fix |
|---|---|
| `ERROR: Unknown command (option) name ... Line: DEF_FILE` (SX-0271) | DEF flow keyword is `TOP_DEF_FILE`, not `DEF_FILE`. A list of valid names is obtainable with `strings -n4 .../linux64_starrc/bin/StarXtract | grep '^[A-Z_]*$'`; the man pages under `doc/starrc/man/catn/SX` are message texts, not keywords. |
| `ERROR: Absolute path ... is not permitted for star_cmd option SUMMARY_FILE` (SX-3978) | Drop the option (summary lands in `<BLOCK>.star_sum`) or give a relative name. |
| `ERROR: Section has not been described Line: # tech-LEF layer name ...` (SX-1907) | The mapping file has **no comment syntax**: a `#` line is parsed as a section name. Strip comments (`grep -v '^#'`). Task `Layers_part1` fails with SX-0255. |
| `ERROR: The definition of cell 'sky130_ef_sc_hd__decap_12' ... is not found` x161,973 (SX-2144) | The OpenROAD DEF uses the `sky130_ef_sc_hd` library; add `sky130_ef_sc_hd.lef` as a `LEF_FILE`. |
| `WARNING: VIA 'mcon_cc' undefined` (SX-2064) and ~95 % open nets | Tool-specific via names in the DEF (see caveat 5): supply a LEF with those VIAs. |
| `Number of shorts exceeds SHORTS_LIMIT: 1000` (SX-3062) | Default truncates the short report; set `SHORTS_LIMIT`. |
| Opens / shorts counts | No simple summary line: opens are `report_opens NETID1 : N` in `star/summary/.ReportOpens.messages`; shorts are lines in `star/shorts_all.sum`; EX-414 "found open net(s)" appears in the log when N > 0. |
| `make` deletes intermediates | Use `.SECONDARY:` (already in the Makefile). |
| Shell | `bash -c 'source tools/eda/pd_env.sh'`; the login shell is csh. A command line with `=====` fails in the tool shell; quote it. |
| Host reset | A 12 h host shutdown killed everything mid-queue. Completeness check per run: `star/.starrc_complete`, `rc=0` in `time.txt`, SPEF ends in `*END`. All six were complete. |

## 7. Open items

1. Innovus b5c: run `make -C pnr/commercial/signoff/starrc innovus` once `b5c_innovus/out/rv32i_cpu_top.def` is complete (about 2 min per corner), then `make stats` and add the rows. If Innovus's DEF names vias or layers that the LEF lacks, expect SX-2064/SX-2144 again and a large open count; fix with a supplementary LEF as for ICC2, not by editing the DEF.
2. Quantus correlation once Techgen produces `qrcTechFile` (not started; not touched).
3. ITF tuning (coupling/fringe, corner spread) was explicitly not done; the correlation numbers above are the baseline for it.
4. The nom and max SPEFs carry the **INDICATIVE** label into STA.

---

# B1c: ITF calibration to OpenRCX (2026-10-26 to 10-28)  [IN PROGRESS: updated after each milestone]

**Status (updated 2026-10-31)**: nom, min and max done (tuned stack, new settings; the max nxtgrd finished 2026-10-28 20:08). The ICC2 and Innovus rows below are the SUPERSEDED b5a / b5d extractions, kept as history; the current ones are b5e / b5g in section B7 at the end of this file.
"Calibrated to OpenRCX" means calibrated to the OpenRCX `rules.openrcx.sky130A.*.calibre` decks (the ones the OpenROAD flow runs), **not correlated to silicon**.

## Findings that changed the plan

1. **The coupling-share gap was a StarRC setting, not the stack.** StarRC lumps any coupling below 3 % of the net's total C (`rel_cap_threshold 0.03`, `abs 3e-15 F`) into ground. OpenRCX only grounds couplings below 0.1 fF absolute. Same nxtgrd, only `COUPLING_ABS_THRESHOLD: 0.1`, `COUPLING_REL_THRESHOLD: 0`: design coupling share 0.340 to 0.548 (OpenRCX 0.549), per-net median share diff -16.4 to -2.7 points. Total C is unchanged by thresholds.
2. **The excess total C is a per-pin term, not the stack.** Regression over nets with C < 50 fF: `C_StarRC = 1.007 * C_OpenRCX + 0.219 fF * n_pins - 0.007` (default settings). StarRC extracts cell pin shapes, cell OBS and vias that OpenRCX does not. Ratio vs net size: C < 1 fF ratio 1.5 to 2.0; C > 50 fF ratio 0.995 to 1.04. With `LEF_USE_OBS: NO` (pins only, which is what the task asks for the SRAM macros and is applied to std cells too): `0.977 * C_OpenRCX + 0.161 fF/pin`, design total 988.0 vs 995.0 pF (x0.993).
3. **The old corner spread was derived from the wrong file and the wrong column.** `corner_scale.py` read the 4th column of `rules.openrcx.sky130A.*.spef_extractor` as capacitance. That column is resistance per length (Rsq/(2w)), and that deck is not the one the OpenROAD flow uses (it uses `.calibre`; the `.spef_extractor` deck is flat, coupling column 0). The 0.7919/1.2131 multipliers were the sheet-R corner ratios.
4. **The nominal stack needs no change.** On wire-dominated nets (C > 20 fF) StarRC/OpenRCX total C is 0.995 to 1.07, coupling share within 1 to 2 points. The nominal ITF/ICT are byte-identical to the untuned ones, so the running Techgen nom job stays valid.
5. **OpenRCX's own tables are not a physical target.** On isolated wires OpenRCX gives 87 to 95 aF/um (foundry LEF edge-cap constants), a 2-D field solve of the published stack with no other layers present gives 40 to 64, StarRC 67 to 75 (it sees the pin squares and end effects). Adjacent-track patterns agree within about 6 % (met1..met4 `T_*_1_1`), sparse environments are 15 to 25 % low in StarRC (`pattern_check_nom.md`). Physically plausible knobs cannot close that (below), and design-level totals agree anyway because crossings dominate.

## Knobs

| Knob | Original | Final | Why |
|---|---|---|---|
| ER corner multiplier, min | 0.7919 | **0.9133** | OpenRCX design total min/nom = 0.8925 (888.0/995.0 pF), divided by StarRC nom wire slope K_NOM = 0.9772 |
| ER corner multiplier, max | 1.2131 | **1.1109** | OpenRCX max/nom = 1.0856 (1080.1/995.0 pF), same K_NOM |
| nominal dielectric ER (all slabs) | per `gen_stack.py` SLABS/FIT | unchanged | wire-proportional slope 0.977 to 1.007 vs OpenRCX; changing it would invalidate the running nom Techgen |
| metal thickness, etch bias, conformal liner | FIG values, none, none | unchanged | sensitivity below: no plausible value fixes the isolated-wire gap without breaking the dense-wire match |
| StarRC `COUPLING_ABS_THRESHOLD` / `COUPLING_REL_THRESHOLD` | defaults 0.003 fF / 0.03 | 0.1 fF / 0 | OpenRCX's grounding rule (setting, not ITF) |
| StarRC `LEF_USE_OBS` | default (OBS used) | NO | pins-only extraction, as for the SRAM macros |

cap2d sensitivity (`scripts/tune/sensitivity.py`, 2-D numpy surrogate validated within 1 to 11 % of StarRC on the same patterns), change in Ctot for met1..met4 dense / isolated wires: all ER x1.05: +5 % / +5 %; lateral-slab ER x1.10: +8 to +10 % / +4 to +7 %; sub-slab ER x1.10: +0 to +2 % / +2 to +6 %; metal thickness x1.05: +3 % / +0.5 %; 20 nm etch bias: +3 to +9 % / +1 %; 25 nm K=7.3 liner: +5 to +13 % / +1 to +2 %. The isolated-wire gap to OpenRCX is 20 to 30 %.

Single sources: `pnr/commercial/pdk/sky130/scripts/corner_scale.py` (values) is loaded by `gen_stack.py`, which writes ITF and ICT, so they stay consistent.

## Before / after (OpenROAD DEF, StarRC vs OpenRCX, nets with C > 1 fF)

| Corner | | C median | C p5 / p95 | C outside +-10 % | R median | per-net coupling-share median (OpenRCX / StarRC, diff) | Design C StarRC vs OpenRCX |
|---|---|---|---|---|---|---|---|
| nom | before | 1.135 | 0.963 / 1.406 | 64.2 % | 0.976 | 0.540 / 0.376 (-16.4 pts) | 1023.4 vs 995.0 (x1.029) |
| nom | **after** | **1.078** | 0.937 / 1.348 | 45.3 % | 0.976 | 0.540 / 0.571 (+3.0 pts) | 988.0 vs 995.0 (x0.993) |
| min | before | 1.006 | 0.847 / 1.228 | 35.5 % | 0.958 | 0.555 / 0.369 (-18.5 pts) | 810.5 vs 888.0 (x0.913) |
| min | **after** | **1.104** | 0.946 / 1.361 | 53.8 % | 0.958 | 0.555 / 0.570 (+1.5 pts) | 902.4 vs 888.0 (x1.016) |
| max | before | 1.256 | 1.066 / 1.569 | 90.9 % | 0.987 | 0.505 / 0.381 (-12.4 pts) | 1241.5 vs 1080.1 (x1.149) |
| max | **after** | **1.091** | 0.954 / 1.376 | 48.4 % | 0.987 | 0.505 / 0.571 (+6.5 pts) | 1097.6 vs 1080.1 (x1.016) |

Wire-proportional slope (`pinfit.py`, nets C < 50 fF): nom 0.977, min 1.003 (before: 0.895 at min with the old +-21 % multipliers, 1.119 at max).

Acceptance status (target: C median +-5 %, coupling-share median +-5 points, R +-5 %, spread close to OpenRCX):
- coupling share: met at nom and min (+3.0, +1.5 points).
- R: met (median 0.958 to 0.987; unchanged by the tuning, RPSQ is explicit in the ITF).
- C median: NOT met (nom 1.078, min 1.104). The remainder is the 0.16 fF per pin that StarRC extracts and OpenRCX does not; matching it by lowering ER would put the wire-dominated nets about 10 % low. Not forced.
- spread: StarRC design min/nom 0.913 vs OpenRCX 0.8925 (the multiplier was calibrated on the wire slope; calibrating on the design total would give 0.8988 / 1.0933, a second grdgenxo regeneration that was not spent).

## ICC2-native agreement

The ICC2 TLU+ comes from the same ITF. The nominal ITF is unchanged, so the nom TLU+ is unchanged. StarRC on the ICC2 DEF vs ICC2's native nominal SPEF: total C median 0.987 (was 1.008; the 2 % shift is `LEF_USE_OBS: NO`), r 0.9996, design 819.9 vs 833.4 pF (was 829.8). min/max TLU+ regenerated with the new multipliers (`gzip -t` OK, header `TLUPlus_ver 18`; grdgenxo's TLU+ step exits rc=1 after "Done (GRD-0062)", the known exit crash). ICC2 has no native min/max SPEF to compare with.

## Files

Tuned ITF/ICT: `pnr/commercial/pdk/sky130/build/tech/{itf,ict}/sky130A_<c>.{itf,ict}`; untuned kept as `sky130A_<c>.untuned.{itf,ict}`. nom is byte-identical; min and max differ. nxtgrd: `build/nxtgrd/{nom,min,max}/` (untuned min/max in `min.untuned`, `max.untuned`). Superseded SPEFs: `signoff/starrc/runs/_superseded_untuned/`. Tools and tables: `pdk/sky130/scripts/tune/` (`gen_patterns.py`, `cap2d.py`, `patterns2d.py`, `validate.py`, `sensitivity.py`, `def_stats.py`, `pinfit.py`), `signoff/starrc/reports/{correlation_*.md,untuned/,pattern_check_nom.md}`.

## Per-arm table, tuned stack + new settings (max pending; Innovus = b5c_innovus_s2)

| arm | corner | DEF nets | SPEF D_NETs | zero-C nets | opens | total C (pF) | gnd C (pF) | coupling C (pF) | sum R (Mohm) | wall | peak RSS (GB) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| openroad | nom | 42291 | 42291 | 87 | 0 | 988.0 | 399.6 | 294.2 | 7.77 | 2:24.36 | 0.49 |
| openroad | min | 42291 | 42291 | 87 | 0 | 902.4 | 365.3 | 268.5 | 4.61 | 3:00.59 | 0.49 |
| icc2 | nom | 35149 | 35149 | 0 | 0 | 819.9 | 306.2 | 256.9 | 5.07 | 2:11.97 | 0.53 |
| icc2 | min | 35149 | 35149 | 0 | 0 | 748.8 | 279.7 | 234.6 | 2.93 | 1:52.10 | 0.53 |
| innovus | nom | 35047 | 35047 | 322 | 0 | 984.0 | 429.2 | 277.4 | 6.26 | 2:24.21 | 0.36 |
| innovus | min | 35047 | 35047 | 322 | 0 | 898.7 | 392.2 | 253.3 | 4.14 | 3:32.44 | 0.36 |

Innovus: 0 opens, 3 residual shorted net pairs (met3/met4) in `star/shorts_all.sum`, so the capacitance of those 6 nets is unreliable (SX-0955). Innovus uses the PDK via names (M1M2_PR, L1M1_PR ...), so no supplementary via LEF was needed. The 322 zero-C Innovus nets are probably nets without routed wiring (not checked). Opens and shorts are read as described in section 6.

## Remaining (automated)

`signoff/starrc/scripts/finish_max.sh` (started 2026-10-28 18:48, setsid) waits for `build/nxtgrd/max/sky130A_max.nxtgrd`, then extracts max for openroad, icc2, innovus one at a time, rebuilds `reports/correlation_*.md`, `reports/per_arm.md`, `reports/pinfit_max.txt`; progress in `reports/finish_max.status`. If the host dies again: re-run `build/nxtgrd/max` via `pnr/commercial/pdk/sky130/scripts/run_grdgenxo.sh max` (move any partial `sky130A_max/` aside first), then `signoff/starrc/scripts/finish_max.sh`. For a b5d Innovus DEF: change `innovus)` in `scripts/arms.sh` (and the path in `collect_stats.py`), move `runs/innovus_*` aside, `make innovus`.


---

# B7: ICC2 b5e and Innovus b5g re-extraction (2026-10-31)

StarRC X-2025.06-SP1, tuned nxtgrds (nom, min, max), identical settings for every arm (`gen_cmd.sh`: `COUPLING_ABS_THRESHOLD 0.1`, `COUPLING_REL_THRESHOLD 0`, `LEF_USE_OBS NO`, `TOP_DEF_FILE`, `NUM_CORES 2`), one extraction at a time under `safe_run.sh`.
**"Calibrated to OpenRCX" means calibrated to the OpenRCX decks the OpenROAD flow runs, not correlated to silicon.** `scripts/arms.sh` and `scripts/collect_stats.py` now point at `impl/icc2/runs/b5e_icc2/out/rv32i_cpu_top.def` and `impl/innovus/runs/b5g_innovus/out/rv32i_cpu_top.def`.
The previous extractions are kept (not deleted) as `runs/_superseded_b5a/icc2_b5a_{nom,min,max}` and `runs/_superseded_b5d/innovus_b5d_{nom,min,max}`.

| arm | corner | DEF nets | SPEF D_NETs | zero-C nets | opens | total C (pF) | gnd C (pF) | coupling C (pF) | sum R (Mohm) | wall | peak RSS (GB) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| icc2 b5e | nom | 35096 | 35096 | 0 | 0 | 828.7 | 309.2 | 259.7 | 4.88 | 3:54.60 | 0.53 |
| icc2 b5e | min | 35096 | 35096 | 0 | 0 | 756.8 | 282.5 | 237.2 | 2.80 | 2:52.98 | 0.53 |
| icc2 b5e | max | 35096 | 35096 | 0 | 0 | 920.5 | 343.3 | 288.6 | 9.34 | 3:13.98 | 0.53 |
| innovus b5g | nom | 35893 | 35893 | 322 | 0 | 974.0 | 428.7 | 272.7 | 6.26 | 2:51.28 | 0.37 |
| innovus b5g | min | 35893 | 35893 | 322 | 0 | 889.6 | 391.7 | 249.0 | 4.13 | 12:21.48 (load-gate waits) | 0.37 |
| innovus b5g | max | 35893 | 35893 | 322 | 0 | 1082.0 | 476.0 | 303.0 | 10.38 | 3:21.57 | 0.37 |
| openroad (unchanged), max now done | max | 42291 | 42291 | 87 | 0 | 1097.6 | 443.7 | 326.9 | 14.48 | 7:43.88 | 0.49 |

Previous vintages for reference (tuned stack): ICC2 b5a nom/min total C 819.9 / 748.8 pF (superseded; max run is in `_superseded_b5a`); Innovus b5d nom 984.0, min 898.7 (earlier row of the B1c table above).

Completeness (read from the run directories, not from make): all six runs have `star/.starrc_complete`, `rc=0` in `time.txt`, SPEF ending `*END`, no `^ERROR` in `starrc.log`, `report_opens NETID1 : 0`, no SX-2064 (ICC2 via names resolved by `icc2_via_names.lef`; Innovus uses the PDK via names) and no SX-2144.

**Shorts (physical caveat that the extraction inherits):**
- **ICC2 b5e: 1 met1 short pair**, identical in nom, min and max: nets `u_core/ex1c_comb[158]` and `u_core/ex1c_ex1b_reg_q[124]`, layer met1, BBox (1918.13, 882.91) to (1918.27, 883.05) um (3 lines in `star/shorts_all.sum`; SX-0955 raised once per run). This is the known remaining DRC short of the b5e layout; StarRC finds it independently of ICC2. **The extraction of these two nets includes the short, so their R and C are unreliable and the two nets are electrically merged in the SPEF**; every other net is unaffected. b5a had no short.
- **Innovus b5g: no shorts** (no `shorts_all.sum`, no SX-0955). The b5d extraction had 3 shorted pairs in the earlier b5c_s2 vintage; those are gone.
- Innovus b5g also carries 4 antenna violations on 3 clock-tree nets and 232 ECO `buf_8` repeaters on the `axi_rdata_i` inputs. Neither is an extraction issue, but both are in the netlist the SPEFs belong to.
- The 322 zero-C Innovus nets are unchanged from b5d (probably nets without routed wiring; not checked).

**Correlation.** OpenROAD StarRC vs OpenRCX is unchanged by this step (same DEF, same decks): max corner is now measured, `reports/correlation_max.md`: C median 1.091, p5/p95 0.954/1.376, r 0.9977, 48.4 % outside +-10 %, coupling-share diff +6.5 points, R median 0.987, design 1097.6 vs 1080.1 pF (x1.016); wire-proportional slope 0.9949 (`reports/pinfit_max.txt`). Nom and min figures are in the B1c table above. The tuned stack is therefore still INDICATIVE at nom and max by the stated C-median criterion (+-5 % not met, 1.078 / 1.091).
StarRC vs the ICC2-native SPEF (nominal TLU+, no coupling), new b5e layout, nom: **total C median 0.987, p5/p95 0.911/1.102, r 0.9997, design 828.7 vs 842.0 pF (x0.984); R median 0.985, design x0.984** (`reports/correlation_icc2native_b5e_nom.md`). Same agreement as on b5a (0.987, r 0.9996), so the ICC2 arm's extraction is as consistent with its own tool as before. (Ground C and coupling-share rows of that report are not comparable: the native SPEF has no coupling.) No Innovus native comparison was run.
