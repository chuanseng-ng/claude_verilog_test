# Formality LEC of the post-route ICC2 netlist, Sky130 `rv32i_cpu_top` (step B4c)

**Verdict: EQUIVALENT, both compares.** The ICC2 post-route netlist (`impl/icc2/runs/b5a_icc2/out/rv32i_cpu_top.nl.v`, md5 `e9150655...`, flat, no PG,
no physical-only cells) is equivalent to (a) the RTL and (b) the DC-NXT netlist. 6,233 passing / 0 failing / 0 aborted / 0 unverified in every
successful run. Negative controls on the ICC2 netlist fail as required. Formality X-2025.06, 2 cores, under `safe_run.sh` (6 GB cap), Innovus running concurrently.
Method and rules identical to B4a (`lec_dc_formality.md`): no `set_constant`, no `set_dont_verify_point`, no user matches, no waivers.

## Results
| Run (`runs/<tag>`, copies in `signoff/lec/formality/reports/<tag>/`) | Reference | SVF | Verdict | Pass / Fail / Abort / Unverif | Unmatched (ref/impl) | Wall, RSS |
|---|---|---|---|---|---|---|
| `b4c_icc2_vs_dc` **(b)** | DC netlist | none | **SUCCEEDED** | 6,233 / 0 / 0 / 0 | 0 / 115 | 14 s, 497 MB |
| `b4c_icc2_vs_rtl_svf` **(a)** | RTL (28 files, 5 defines) | DC SVF, 1,177/1,177 accepted | **SUCCEEDED** | 6,233 / 0 / 0 / 0 | 0 / 115 | 32 s, 575 MB |
| `b4c_icc2_vs_rtl_nosvf` | RTL | none | FAILED (explained below) | 3,821 / 2,412 / 0 / 0 | 143 / 115 | 38 s, 609 MB |
| `b4c_icc2nodiode_vs_dc` | DC netlist | none | **SUCCEEDED** | 6,233 / 0 / 0 / 0 | **0 / 0** | 8 s |
| `b4c_icc2nodiode_vs_rtl_svf` | RTL | DC SVF | **SUCCEEDED** | 6,233 / 0 / 0 / 0 | **0 / 0** | 30 s |

Compare-point mix (all four SUCCEEDED runs): 5,284 DFF + 379 port + 570 black-box input pins. 5,284 DFF is the same count as DC, so ICC2 added/removed no register
(its CTS/optimisation/hold cells are combinational/buffers only). The 18 `dfrtn_1` negedge flops and the `fwd_b_*` flops are verified points.

### (a) Is the DC SVF usable for this hop? Yes.
All 1,177 guidance commands are accepted on the ICC2 netlist, 0 rejected, same table as B4a. Reason: ICC2 started from the DC netlist and kept DC's flat names
(`\u_core/...` escaped names with literal `/`, same flop names), and the registers DC removed (138 constants, 5 merged duplicates) are absent in both netlists; the
SVF's reference-side guidance is what bridges them to the RTL. Formality matches the ICC2 flat names to the RTL hierarchy by name (6,233 by name, 0 by signature/topology).
Without the SVF the result is exactly the B4a no-SVF result (3,821 pass / 2,412 fail, the same 143 unmatched reference registers = 136 `Constrained 0X` + 7 DFFs
(2 `flush_ex_mem`, 5 merged duplicates)): the failures are fan-out of those unmatched registers, so the SVF is needed for RTL-vs-anything-derived-from-DC and
the failure is not new in ICC2. The B4a probes (falsified merge and constant claims both fail; Formality rejects the invalid `reg_constant`s) show the SVF guidance is
checked, not blindly trusted; they were not rerun here as the SVF and reference are unchanged.

### (b) DC netlist vs ICC2 netlist, no SVF
Netlist-to-netlist, no guidance: SUCCEEDED in 14 s with all 6,233 points matched by name (the DC hierarchy is flattened by Formality and the ICC2 escaped names
`\u_core/x` match DC's `u_core/x`). This is the strongest check on what ICC2 changed (assign elimination, optimisation/CTS/hold buffers, resizing, port diodes) and does
not depend on the SVF.

## The 115 port diodes (the only "unmatched" objects)
ICC2 inserted 115 `sky130_fd_sc_hd__diode_2` (`PORTDIODE__*`, one on every primary input except `clk_i`). In the `.db` the diode is a tech macro with one input pin
(`DIODE`) and no function/output, so Formality models each as a black box: 115 BBox + 115 BBPin appear as **unmatched implementation points** (`0(115)`), have no
reference counterpart and cannot be compared. They do not affect any compare point (a cell without an output cannot influence anything). To keep the sign-off count
"unmatched = 0" literally true without a waiver, `scripts/strip_diodes.py` writes a copy in the run dir with those 115 instances removed (asserts: exactly 115,
each of form `diode_2 N ( .DIODE ( net ) ) ;`, every net a primary input) and the compare was repeated: **0 unmatched, SUCCEEDED** for both references (`b4c_icc2nodiode_*`).
Both forms are reported; the ICC2 file is never edited in place.

## Netlist handling
- `supply1 VPWR ;` / `supply0 VGND ;` (lines 28849-50) are declarations with no connections (grep: the only two occurrences). Formality read the file as-is, no
  error, no change to results; so no preprocessing was applied. The file is not edited.
- Black boxes: the 10 `sky130_sram_1kbyte_1rw1r_32x256_8` macros from the `.db` on both sides (instances `\u_core/u_icache_gen_data_sram_N__u_data_sram`, `\u_core/u_dcache/...`), matched by name;
  570 input-pin compare points pass. Nothing else is a black box except the diodes above.
- Settings = B4a (2 cores, `hdlin_unresolved_modules error`, failing-point limit 0, `read_db -technology_library`, implementation `.db` read after the reference top is set).
  For `REFMODE=dc` the std-cell and SRAM `.db` are read into the reference container before the DC netlist.
- FM-399 "222 undriven nets" are in the reference (DC) submodules `rv32i_core_00000000`/`rv32i_dcache` (same as B4a); the flat ICC2 netlist has 0 undriven nets (`222 (0)` in (b)).

## Negative control (required): 4 of 4 detected, one failing point each
Mutants of the ICC2 netlist (`scripts/mk_mutant_icc2.py`, re-anchored on ICC2 names): `fwdb_inv` = inverter on the D pin of `\u_core/fwd_b_ex1c_r_reg` (D net `ZBUF_2_561`);
`swap` = pins A1/C1 exchanged on `o221ai_1 \u_core/U2793`, which drives the D net of `ex1a_ex1b_reg_q_reg_alu_result__5_` (ALU cone).
| Mutant | vs DC netlist | vs RTL (+SVF) |
|---|---|---|
| `fwdb_inv` | FAILED, 1 point: `u_core/fwd_b_ex1c_r_reg` | FAILED, 1 point (same flop) |
| `swap` | FAILED, 1 point: `ex1a_ex1b_reg_q_reg_alu_result[5]` | FAILED, 1 point |
Each mutant leaves 6,232 passing, so the unmutated remainder still verifies and a single-gate defect is localised. The negctl target errors out if any mutant is judged equivalent.

## Caveats
- Equivalence is of the logical netlist (`write_verilog -exclude {pg_netlist physical_only_cells}`). The PG netlist (`.pg.nl.v`, 8.4 MB) and `.full.pnl.v` (taps/endcaps/fill, for LVS) were
  not LEC'd; physical-only cells have no logic and are covered by LVS, not LEC. Whether the GDS matches this netlist is Netgen LVS's job (not run on the ICC2 GDS yet).
- Single tt library view; logic equivalence is corner independent. Eco/post-route edits after `06_finish` are not covered: rerun `lec-icc2-*` after any change.
- LEC says netlist == RTL, not that the RTL is correct.

## Reproduce
```
make -C pnr/commercial/signoff/lec/formality lec-icc2-rtl lec-icc2-dc     # (a) with DC SVF, (b) vs DC netlist
make -C pnr/commercial/signoff/lec/formality lec-icc2-rtl-nosvf           # ablation (expected FAIL)
make -C pnr/commercial/signoff/lec/formality lec-icc2-nodiode             # 0-unmatched variant (needs the diode strip)
make -C pnr/commercial/signoff/lec/formality lec-icc2-negctl              # 4 mutant runs, each must FAIL
```
(`TAG=` selects the run dir; default tag is `b4a_dc_vs_rtl`, so pass `TAG=b4c_icc2_vs_dc` etc. when running targets individually.)
Files: `scripts/{fm_lec_icc2.tcl,mk_mutant_icc2.py,strip_diodes.py}`, `Makefile` (committed); `runs/` gitignored; `reports/b4c_*/` text copies.
