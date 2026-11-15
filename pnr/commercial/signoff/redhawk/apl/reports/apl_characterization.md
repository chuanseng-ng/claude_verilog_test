# APL characterisation of the Sky130 decap cells and the 12 most-used std cells (step 8, 2026-11-15)

**Scope (user decision 2026-11-08, "Partial + justify rest").** Ansys APL (`apldi`, RedHawk 2025 R2.2, internal NSPICE) for the 6 decap cells that occur in the final-arm DEFs and the 12 functional std cells with the highest pooled instance count over ICC2 b9, Innovus b11 and OpenROAD B2. All other cells keep the RedHawk defaults derived from the Liberty. Corner: TT, 25 C, 1.8 V, mismatch off (the Liberty and the RedHawk tech are the same nominal corner).

## 1. Cell set (`reports/cell_selection.tsv`, `reports/apl_coverage.tsv`)
Pooled functional instances 127,766 (DEF COMPONENTS, fill/tap/decap/diode/conb excluded). Top 12 = 59,381 instances = 46.5 %:
`dfxtp_1 buf_2 dlygate4sd3_1 nand2_1 dfxtp_2 inv_2 clkbuf_1 a22o_1 nor2_1 o21ai_1 clkbuf_4 buf_4`.
Share of each arm's non-SRAM leaf cells and of its PrimePower power (variant B) inside the set:

| arm | leaf cells | in set | instance share | total mW (non-SRAM) | in set mW | power share |
|---|---|---|---|---|---|---|
| ICC2 b9 / b12 | 40,334 | 21,317 | 52.9 % | 40.34 | 22.99 | 57.0 % |
| Innovus b11 | 45,184 | 20,124 | 44.5 % | 45.57 | 20.20 | 44.3 % |
| OpenROAD B2 | 42,578 | 17,940 | 42.1 % | 64.03 | 21.51 | 33.6 % |

Decap cells characterised: `sky130_fd_sc_hd__decap_3/4/6/8/12` and `sky130_ef_sc_hd__decap_12`. The 10 SRAM macros (about 41 % of ICC2 power) are NOT characterised (no APL for memories without `sim2iprof`/ACE); they stay lumped constant sinks.

## 2. Method and what had to be done to make it run
- **Models.** The open_pdks models are ngspice-style. `scripts/mk_hspice_models.py` writes `models/sky130_tt_hspice.lib` (`.lib TT`) with only syntactic conversions: `{expr}` to `'expr'`; `.param` defaults inside `.subckt` moved onto the `.subckt` line; the `.option scale=1u` unit scaling written out on the model-owning MOS instance (HSPICE did not scale W through the subckt parameter); `AGAUSS(..)*MC_MM_SWITCH` with `MC_MM_SWITCH=0` replaced by 0. Sanity: HSPICE X-2025.06 inverter transient gives the expected levels. `scripts/mk_cell_netlist.py` extracts the cell subckts and resolves `u`-suffixed numbers (`1e+06u` is 1.0 in ngspice but 1e6 in HSPICE).
- **APL configuration** (`scripts/run_apl_all.sh`): design-independent run mode, one `DESIGN_CORNER`, no `LEF_FILES` (with the LEF/Liberty the VPB/VNB pins become separate supply domains and APL refuses them as alias pins, measured), `VDD_PIN_NAME VPWR`, `GND_PIN_NAME VGND`, `DECAP_VDD_PIN {VPWR 1.8 VPB 1.8}`, a cell-level `pgarc` custom lib restricting the arc to VPWR-VGND.
- **ef decap fix** (`scripts/run_apl_ef_fix.sh`): `sky130_ef_sc_hd__decap_12` is not in the hd Liberty/LEF, so APL did not know its VPB/VNB pins and left the bulk nodes floating: first result 10.2 nF and 43 mA leakage (kept as `ef_decap12_bad.cdev`, discarded). A `CUSTOM_LIBS_FILE` declaring the 4 P/G pins gives 57.2 / 69.1 fF, consistent with the identical-device hd decap_12.
- **Runs** (2 threads, `licensed_lock.sh` + `safe_run.sh`, `/usr/bin/time -v`): decap `-p` 6 cells 1:05 wall, peak RSS 416 MB; library-cell `-c` 12 cells 2:28, 416 MB; switching current 12 cells 15:37 wall (APLDI CPU 2,178 s), 420 MB; ef fix 0:23, 415 MB. Nearly all of the 1 to 3 min for the small steps is the Liberty parse and pre-check of the 414-cell library.
- **Checks.** `aplchk` on `CURRENT` and `CAP`: no failures, one warning (toggle count 2 against SPICE toggle 4 for `buf_2`). RedHawk import: 0 P/G pin mismatches (`apache.refCell.mismatchAplCdev/Current`), all decap cells found.

## 3. Results and the two caveats they carry (`reports/apl_cdev_summary.tsv`, `reports/hspice_decap_check.tsv`)
Intrinsic capacitance of the decap cells (VPWR pin / VGND pin, fF) against an independent HSPICE small-signal check (1 MHz, VPWR driven, VPB tied to VPWR) and the earlier spice W/L estimate:

| cell | HSPICE AC | APL VPWR | APL VGND | W/L estimate |
|---|---|---|---|---|
| decap_4 | 11.8 | 27.8 | 26.2 | 12.6 |
| decap_8 | 31.7 | 73.3 | 70.0 | 34.6 |
| decap_12 | 51.7 | 55.1 | 67.7 | 56.6 |

1. **APL decap capacitance is not confirmed by the independent check.** For decap_4 and decap_8 APL is 2.3 to 2.4 times the HSPICE AC capacitance and above the gate-area limit of the cell (Cox 8.4 fF/um2 x gate area gives 12.6 and 34.6 fF); for decap_12 it is 1.07 times. The sequence over the cell sizes is not monotonic (decap_8 above decap_12). The cause was not isolated (INFERRED: APL derives the value from a charge/transient state, and the BSIM4 capacitance parameters are binned by L). How RedHawk combines the per-pin `esc` values was not verified either. The RedHawk run with the W/L-estimated decap (section 5) brackets the effect.
2. **ESR of the decap cells is 1 ohm (a floor) on VPWR and VGND, 10 to 12 ohm on the well pins.** The AC analysis printed divide-by-zero warnings (imaginary impedance 0). The sky130 BSIM4 cards have `acnqsmod=0`, `trnqsmod=0`, `rgatemod=0`, so the model has no channel/gate resistance in the capacitance path and APL cannot extract a physical ESR. The estimate used before (1,956 ohm for decap_4) came from L/W channel resistance; the truth for silicon is not in the models. Treat the APL decap as an optimistic limit in ESR.
Std cells: intrinsic C and ESR look physical (dfxtp_1: 28 fF on VPWR, ESR 612 ohm; inv_2: 7.1 fF, 25 ohm).

## 4. Package model (ASSUMED)
Not from any package. The simple-package example of the RedHawk manual (ch. 12) applied to every one of the 72 supply connections (one per met5 stripe end): pad R 0.01 ohm C 0.5 pF; wirebond/bump R 0.245 ohm L 1,420 pH C 5 pF; package R 0.001 ohm L 10 pH C 10 pF, identical for VDD and VSS. RedHawk reports the applied loop: wirebond 0.245 ohm and 1,420 pH per pin, package 0.001 ohm and 10 pH. In a parent SoC the macro would be overlaid by the SoC grid and this impedance would not exist at the macro boundary; it is in the dynamic numbers as an ASSUMED stress, and it dominates the worst-instance change against the b6-era runs (the b6 feed was ideal).

## 5. Reproduce
`python3.11 -I scripts/select_cells.py; scripts/run_apl_all.sh; scripts/run_apl_ef_fix.sh; python3.11 -I scripts/summarize_apl.py; python3.11 -I scripts/coverage.py` (in `apl/`), then in `redhawk/`: `scripts/prep_arm.sh <arm>`, `python3.11 -I scripts/gen_rh_inputs_apl.py <arm>`, `scripts/chain_apl_all.sh <arm...>`, `scripts/chain_apl.sh dynamic-estdecap <arm...>`, `collect_static.py` / `collect_dynamic.py <arm> rh-apl-<mode>`, `scripts/publish_reports.py`, `scripts/tables_apl.py`.
