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
