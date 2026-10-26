# Conformal LEC of the post-route Innovus netlist, Sky130 `rv32i_cpu_top` (B4e: b5c current, B4d: b5b superseded)

## B4e: `b5c_innovus_s2` (CURRENT Innovus deliverable)

**Verdict: EQUIVALENT, both compares, with and without the diodes; all four negative controls are caught.** Same tool, method and settings as the b5b section below
(Conformal 24.10-p100, `lec -nogui -xl`, 2 threads, `safe_run.sh` 6 GB cap, flat compares, no `fv_map`, no Genus implementation info, no constraints/waivers).
Revised netlist: `pnr/commercial/impl/innovus/runs/b5c_innovus_s2/out/rv32i_cpu_top.nl.v` (flat, 1 module, 6.77 MB, no PG, no physical-only cells).
Goldens as before: (a) RTL, same 28 SV files + defines incl. `SRAM_SKY130`; (b) Genus final netlist `syn/genus/runs/b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v`.

### Results (measured from `lec.log`; 0 non-equivalent / 0 aborted / 0 unknown / 0 uncompared in every EQUIVALENT run)
| Run (`runs/<tag>`, copies in `signoff/lec/conformal/reports/<tag>/`) | Golden | Revised | EQ points | Unmapped | Wall (load-dependent), RSS |
|---|---|---|---|---|---|
| `b4e_innovus_vs_rtl` **(a)** | RTL | b5c netlist | 5,597 = 379 PO + 5,208 DFF + 10 SRAM BBOX (5,791 counting merged points) | golden 947 DFF unreachable; revised 262 diode BBOX unreachable; 0 not-mapped | 69 s, 361 MB |
| `b4e_innovus_vs_genus` **(b)** | Genus netlist | b5c netlist | 5,597 (same mix) | revised 262 diode BBOX unreachable; 0 golden | 14 s, 271 MB |
| `b4e_innovus_nodiode_vs_rtl` | RTL | b5c, 262 `diode_2` stripped | 5,597 (5,791) | revised **0**; golden 947 DFF unreachable | 44 s, 376 MB |
| `b4e_innovus_nodiode_vs_genus` | Genus netlist | stripped copy | 5,597 | **0 / 0** | 16 s, 257 MB |
Peak RSS 376 MB. Timings are longer than b5b (38/8 s) only because PT, Magic and Netgen were running concurrently on the host.
The flop count is again exactly 5,208 (all compare points): the reroute added/removed no register. Names are stable (`\u_core/fwd_b_ex1c_r_reg` etc.).

### What changed vs b5b (measured on the netlists)
| | b5b_innovus | b5c_innovus_s2 |
|---|---|---|
| std-cell instances | 32,557 | 34,209 |
| buffer-class cells (`buf*`, `bufbuf*`, `bufinv*`) | 5,694 | 7,258 |
| `clkbuf_*` / `CTS_*` nets | 1,751 / 171 | 2,161 / 167 |
| flops | 5,208 | 5,208 |
| `diode_2` total | 271 (115 PORTDIODE + 156 DIODE_N) | **262 (105 PORTDIODE + 157 DIODE_N)** |
The diode count is re-derived, not assumed: `scripts/strip_diodes.py` now derives it from the file (and asserts every instance has the exact `diode_2 NAME ( .DIODE(net) );` form); optional argv[3] asserts a number.
Per-instance list of the 262 unreachable revised BBOX: `reports/b4e_innovus_vs_genus/unmapped_unreachable_points.txt`.

### Unmapped points, by class (same classes as b5b)
- **Revised: 262 `diode_2`** = black boxes with no output in the Liberty, "unreachable: all paths to outputs are blocked", no golden counterpart, cannot affect any compare point. Not waived: the stripped copy repeats both compares with **0 unmapped** and the same EQ counts, both forms reported.
- **Golden (RTL): 947 DFF unreachable + 81 merged by LEC + 388 constant-0**, identical to B4b/B4d (a Genus/RTL property, unchanged by P&R). Explained in `lec_genus_conformal.md`.
- Compare (b) has no golden-only points.

### Negative controls (REQUIRED): 4 of 4 caught, each mutant against both goldens
Mutants of the b5c netlist via `scripts/mk_mutant_innovus.py`, now anchored on instance NAMES with the connected nets read from the file (gate `g419910` and the flops kept their names; its A1 net changed `FE_OFN18145_n_265` -> `n_265`; the same script still reproduces the b5b mutants byte-identically). Diffs: `reports/b4e_mutant_*.diff.txt`.
| Mutant | vs RTL | vs Genus netlist |
|---|---|---|
| `fwdb_inv`: inverter on D (`\u_core/n_13109`) of `\u_core/fwd_b_ex1c_r_reg` | **NON-EQUIVALENT**, 1 failing point `fwd_b_ex1c_r_reg` (its merged twin `fwd_store_ex1c_r_reg` is listed with it); 5,790 EQ | **NON-EQUIVALENT**, 1 failing point `fwd_b_ex1c_r_reg`; 5,596 EQ |
| `swap`: A1 and B1 swapped on `a211o_1 \u_core/g419910` (drives D of `ex1a_ex1b_reg_q_reg[alu_result][5]`) | **NON-EQUIVALENT**, 1 failing point `alu_result[5]`; 5,790 EQ | **NON-EQUIVALENT**, 1 failing point `alu_result[5]`; 5,596 EQ |
`make lec-innovus-negctl` fails the recipe if any mutant is equivalent; it passed.

### Reproduce (Makefile is parameterised; b5b and b5c both stay reproducible)
```
make -C pnr/commercial/signoff/lec/conformal lec-genus                                          # B4b prerequisite (mapping file for (a))
make -C pnr/commercial/signoff/lec/conformal lec-innovus-all INNTAG=b5c_innovus_s2 STEP=b4e   # b5c: 4 compares + negctl, tags b4e_*
make -C pnr/commercial/signoff/lec/conformal lec-innovus-all                                   # b5b (defaults INNTAG=b5b_innovus STEP=b4d), tags b4d_*
```
Individual targets: `lec-innovus-rtl`, `lec-innovus-genus`, `lec-innovus-rtl-nodiode`, `lec-innovus-genus-nodiode`, `lec-innovus-negctl` (all honour `INNTAG`/`STEP`; pass `TAG=` for the first two).
Caveats as b5b: logical netlist only (PG/physical cells are LVS's job); rerun after any ECO; single tt library view; LEC says netlist == RTL, not that the RTL is right.

---

# B4d: `b5b_innovus` (SUPERSEDED deliverable; text kept as recorded)

**Verdict: EQUIVALENT, both compares, and all four negative controls are caught.** Conformal LEC 24.10-p100 (`lec -nogui -xl`), 2 threads, under `safe_run.sh` (6 GB cap), with the extraction queue running.
Revised netlist: `pnr/commercial/impl/innovus/runs/b5b_innovus/out/rv32i_cpu_top.nl.v` (flat, 1 module, 180,281 lines, no PG, no physical-only cells).
Method = B4b (`lec_genus_conformal.md`), flat compares with no Genus `fv_map` and no Genus implementation information. Nothing waived: no `add_pin_constraints`, `add_instance_constraints`,
`add_ignore_outputs`, user black boxes or gate/wire edits (verification report sections 2 and 3: all "no"/0; the one flagged non-standard option in (a) is the Genus-written `set_undriven_signal 0 -golden`, inert as the RTL has no undriven nets; "Black box due to undefined cells: no").

### Results (measured, from each run's `lec.log`; 0 non-equivalent, 0 aborted, 0 unknown, 0 uncompared in every EQUIVALENT run)
| Run (`runs/<tag>`, text copies in `signoff/lec/conformal/reports/<tag>/`) | Golden | Revised | EQ compare points | Unmapped | Wall, RSS |
|---|---|---|---|---|---|
| `b4d_innovus_vs_rtl` **(a)** | RTL (28 SV files, `SRAM_SKY130` + same 5 defines as B4b) | Innovus netlist | 5,597 = 379 PO + 5,208 DFF + 10 BBOX (5,791 counting merged/equivalence points) | golden 947 DFF unreachable; revised 271 diode BBOX unreachable; 0 "not-mapped" | 38 s, 372 MB |
| `b4d_innovus_vs_genus` **(b)** | Genus final netlist `b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v` | Innovus netlist | 5,597 = 379 PO + 5,208 DFF + 10 BBOX | revised 271 diode BBOX unreachable; 0 golden unmapped | 8 s, 268 MB |
| `b4d_innovus_nodiode_vs_rtl` | RTL | Innovus netlist, 271 `diode_2` stripped | 5,597 (5,791) | revised **0**; golden 947 DFF unreachable | 38 s, 372 MB |
| `b4d_innovus_nodiode_vs_genus` | Genus netlist | stripped copy | 5,597 | **0 / 0** | 8 s, 267 MB |
| `b4d_innovus_vs_rtl_nomap` (ablation) | RTL | Innovus netlist, **no mapping file at all** | 5,597 (5,791) | same as (a) | 36 s, 368 MB |
Compare-point mix is identical to B4b (RTL vs Genus): the netlist has 5,208 flops and every one is a compare point, so post-route added/removed **no register** (CTS, hold/setup repair and sizing are combinational/buffer only).
Run (a) uses the Genus-composed RTL->Genus-netlist **name** pairs from B4b (`MAPFILE`, pairing only: a wrong pair can only cause a mismatch); the ablation with no mapping file gives the same result, so the mapping file is not load-bearing here.
Flatten options as B4b direct run: `-seq_constant -seq_constant_x_to 0 -hier_seq_merge -seq_merge -balanced_modeling`; naming rules for RTL golden only; Liberty hd tt + patched SRAM Liberty.

### What post-route changed (measured on the netlists)
| | Genus | Innovus |
|---|---|---|
| std-cell instances | 26,337 | 32,557 (incl. 271 diodes) |
| buffer-class cells (`buf*`,`bufbuf*`,`bufinv*`) | 228 | 5,694 |
| `clkbuf_*` | 119 | 1,751 (171 `CTS_*` nets) |
| flops | 5,208 | 5,208 (names kept, e.g. `\u_core/fwd_b_ex1c_r_reg`; sizes/types changed by optimisation, e.g. `dfbbn_2` -> `dfbbn_1`, more `dfxtp_1`) |
| `diode_2` | 0 | **271** |
The 271 is not the 115 in the task note: 115 are `PORTDIODE_*` on primary-input fanouts (`attachDiode`) and **156 are `DIODE_N` antenna-repair diodes** on internal/output nets (106 top-level + 50 under `u_core/`). All 271 have the form `diode_2 NAME ( .DIODE(net) );`.

### Unmapped points, by class
- **Revised, 271 `diode_2` (BBOX, "unreachable: all paths to outputs are blocked").** In the Liberty a diode has one input pin and no function/output, so Conformal models each as a black box (the verification report shows "Total black box modules referenced in Revised = 2": the SRAM and `diode_2`). No golden counterpart and no path to any output, so they cannot influence a compare point. Same behaviour as Formality in B4c. To make "unmatched = 0" literally true without a waiver, `scripts/strip_diodes.py` writes a copy (original never edited; asserts exactly 271 instances all of the exact `diode_2` / `.DIODE` form) and the compares were repeated: **revised unmapped = 0, EQUIVALENT, same 5,597/5,791 EQ points**, for both golden designs. Both forms are reported. Per-instance list: `reports/b4d_innovus_vs_genus/unmapped_unreachable_points.txt`.
- **Golden (RTL), 947 DFF unreachable + 81 merged by LEC (6,236 RTL flop bits = 5,208 + 81 + 947).** Identical profile to B4b (`lec_genus_conformal.md`, "Unmapped points explained"): 388 constant-0 flops that LEC finds itself, 81 duplicate flops merged by LEC, and 947 flops with no path to any PO/SRAM pin (dead pipeline-struct fields, unused address/tag bits, MBIST `rec_*` and collar fail flags, `mcountinhibit_q` upper bits, unconsumed `maint_done_q`). The profile did not move with post-route, as expected: these are RTL-vs-Genus facts that Innovus inherited. Classification by group + spot RTL reads, not a per-bit proof (the tool's "unreachable" count is the measured fact).
- Compare (b) has no golden-only points at all: Genus and Innovus netlists have the same 5,208 flops with the same names.
- 607 "undriven pins" in the Genus golden netlist (b) are treated by LEC as free inputs (same as B4b); the flat Innovus netlist has none. All points are EQ, so they do not matter.

### Negative controls (REQUIRED): 4 of 4 caught
Mutants of the Innovus netlist (`scripts/mk_mutant_innovus.py`, mirrors B4c `mk_mutant_icc2.py`, re-anchored on Innovus names; diffs in `reports/mutant_inn_*.diff.txt`), each checked against **both** golden designs, all four runs show Compare Results `FAIL:NONEQ`:
| Mutant | Edit | vs RTL | vs Genus netlist |
|---|---|---|---|
| `fwdb_inv` | inverter on the D pin (`\u_core/n_13109`) of flop `\u_core/fwd_b_ex1c_r_reg` | **NON-EQUIVALENT**, 1 failing point `fwd_b_ex1c_r_reg` (5,790 EQ; RTL-side the merged twin `fwd_store_ex1c_r_reg` is listed with it) | **NON-EQUIVALENT**, 1 failing point `/u_core/fwd_b_ex1c_r_reg` (5,596 EQ) |
| `swap` | `a211o_1 \u_core/g419910` = (A1&A2)\|B1\|C1, pins A1 and B1 swapped; it drives the D net of `ex1a_ex1b_reg_q_reg[alu_result][5]` | **NON-EQUIVALENT**, 1 failing point `ex1a_ex1b_reg_q_reg[alu_result][5]` (5,790 EQ) | **NON-EQUIVALENT**, 1 failing point `alu_result[5]` (5,596 EQ) |
Each mutant leaves the rest passing, so a single-gate defect is localised to its flop. `make lec-innovus-negctl` fails the recipe if any mutant is judged equivalent; it passed. The mutants carry the 271 diodes, as the real netlist does (diodes are not a variable in the controls).

### Reproduce
```
make -C pnr/commercial/signoff/lec/conformal lec-genus                         # B4b prerequisite: writes the name-pair mapping file used by (a)
make -C pnr/commercial/signoff/lec/conformal lec-innovus-rtl TAG=b4d_innovus_vs_rtl       # (a)
make -C pnr/commercial/signoff/lec/conformal lec-innovus-genus TAG=b4d_innovus_vs_genus   # (b)
make -C pnr/commercial/signoff/lec/conformal lec-innovus-rtl-nodiode lec-innovus-genus-nodiode   # 0-unmatched variants
make -C pnr/commercial/signoff/lec/conformal lec-innovus-rtl INNMAP= TAG=b4d_innovus_vs_rtl_nomap  # ablation, no mapping file
make -C pnr/commercial/signoff/lec/conformal lec-innovus-negctl                # 2 mutants x 2 goldens, each must be NON-EQUIVALENT
```
Files: `pnr/commercial/signoff/lec/conformal/{Makefile, scripts/{mk_innovus_do.py,lec_innovus_rtl.do,lec_innovus_genus.do,strip_diodes.py,mk_mutant_innovus.py}}` (do-files generated from the B4b `lec_genus_direct.do`, each change commented in `mk_innovus_do.py`);
`runs/` gitignored; `reports/b4d_*/` text copies (3.0 MB total with B4b). Tools ran inside `runs/<tag>/`, nothing written to the repo root.

### Caveats
- Equivalence is of the logical netlist (`saveNetlist`). The PG netlist (`.pg.pnl.v`) and physical cells (taps, fill) were not LEC'd; they have no logic and are covered by LVS, not LEC. Whether the GDS matches this netlist is Netgen LVS's job.
- ECOs or edits after this Innovus run are not covered: rerun `lec-innovus-*` after any change. Gate names (`g419910`) change per run; flop names are stable; re-anchor the mutants.
- Single tt library view (logic equivalence is corner independent). Constant-0 flops rely on `-seq_constant_x_to 0`, same caveat as B4a/B4b. LEC says netlist == RTL, not that the RTL is correct.
