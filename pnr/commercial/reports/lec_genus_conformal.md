# Conformal LEC, RTL == Genus netlist, Sky130 `rv32i_cpu_top` (step B4b)

**Verdict: EQUIVALENT, with negative controls detected (all four).** Conformal LEC 24.10-p100 (`lec -nogui -xl`), Genus 23.14-s090_1 netlist
`pnr/commercial/syn/genus/runs/b3b_genus_tt_r2/out/rv32i_cpu_top.nl.v`. Three independent compares agree, 0 non-equivalent / 0 aborted / 0 unknown / 0 uncompared in each.
This mirrors B4a (`lec_dc_formality.md`). It says RTL == netlist only; it says nothing about the RTL being right (that is the dud4 gate-vs-RTL simulation work).

## Results (measured, from `lec.log` of each run)
| Run (tag under `runs/`) | What it compares | Compare points | Result |
|---|---|---|---|
| `b4b_genus_vs_rtl` leg 1 | Genus `fv_map` vs final netlist, flat, Genus implementation info | 5,597 = 379 PO + 5,208 DFF + 10 BBOX | **EQUIVALENT**, 0 unmapped |
| `b4b_genus_vs_rtl` leg 2 | RTL vs `fv_map`, Genus' hierarchical `run_hier_compare` (4 module pairs) | ex1c 78 PO, decode 42 PO, core 349 PO + 4,522 DFF + 12 BBOX, top 379 PO + 686 DFF + 1 BBOX | **EQUIVALENT**, 4/4 modules EQ, Compare Results PASS |
| `b4b_flat_rtl_vs_fvmap` | RTL vs `fv_map`, FLAT (no module-boundary constraints) | 5,597 (379 PO + 5,208 DFF + 10 BBOX) | **EQUIVALENT** |
| `b4b_direct_rtl_vs_final` | RTL vs FINAL netlist, FLAT, **no Genus implementation information** | 5,597 (379 PO + 5,208 DFF + 10 BBOX), 5,791 EQ counting merged/equivalence points | **EQUIVALENT** (this is the headline: RTL -> final netlist directly) |

Run cost (`/usr/bin/time`, 2 threads, safe_run 6 GB cap): main two-leg 118 s wall, peak RSS 399 MB; flat 40 s / 336 MB; direct 50 s / 380 MB; negative controls 32-50 s / 335-385 MB.
Netlist flop count 5,208 (Genus) equals the DFF compare-point count: every implementation flop, including the `dfxbp`, `sdfxtp` and negedge `dfrtn_1`/`dfbbn_2` cells, is a verified compare point.
Library cells were modelled from the sky130 hd tt Liberty (`read_library -liberty`); the verification report shows "Black box due to undefined cells: no".

## Black boxes
Only the SRAM `sky130_sram_1kbyte_1rw1r_32x256_8` (module-level count 1 in each design, **10 instances**), `add_notranslate_modules -library -both` with the patched SRAM Liberty.
All 10 BBOX are compare points and EQ (their input pins are checked; outputs are free on both sides). `set_undefined_cell black_box` is in the Genus do-file but nothing else became a black box.
(The "HIER: rv32i_decode / rv32i_pipeline_ex1c / rv32i_core_RESET_PC0" black boxes seen in the leg-2 log are the hierarchical-compare mechanism, each module is compared in its own pass.)

## Settings (what was run, and what was changed)
The Genus-written `out/lec_rv32i_cpu_top.do` could not run as-is. Genus outputs were not edited: `scripts/mk_do.py` derives `scripts/lec_genus.do` and asserts each substitution.
| Change | Why |
|---|---|
| `lec -xl` (Makefile) | `analyze_extended_mapping` in the do-file needs a Conformal_Ultra licence; plain `lec` aborts there (measured: "This feature requires a Conformal_Ultra license") |
| `LEC_VERSION=24.10-p100` | the do-file parses it (needs >= 19.10-p100 for the RTL-names flow; 21.10 steps are enabled) |
| S1 log path -> `$LEC_RUN/lec.log` | do not write into the Genus run dir |
| S2 final netlist -> `$IMPL` | same file runs the real netlist and the mutants |
| S3 `-threads 1,4` -> `1,2` | host rule (VMware guest hard-locks under full vCPU load) |
| S4 greppable `B4B_LEG1_VERDICT:` marker | negative controls need a machine-readable verdict; Genus' own `error` on non-PASS leg 1 is kept (leg 2 does not run on a non-equivalent leg 1) |
Kept exactly as Genus wrote them: `set_mapping_method -sensitive`, genus naming style and `%s_reg` register rule, `-const_port_extend`, `set_undriven_signal 0 -golden`, `set_flatten_model -seq_constant -seq_constant_x_to 0 -hier_seq_merge` (+ `-balanced_modeling` in leg 2),
the 28 RTL files and the `-define PDK_sky130A SCL_sky130_fd_sc_hd __librelane__ __pnr__ SRAM_SKY130 SYNTHESIS` set, mapping files.
**NOT used:** `add_pin_constraints`, `add_instance_constraints`, `add_ignore_outputs`, user black boxes, `set_dont_verify`-style waivers, any "Change gate/wire" edits (verification report sections 2 and 3 show all "no"/0).
Non-standard option flagged by the report (count 1): "Floating signals tied to Z: no" = Genus' `set_undriven_signal 0 -golden`; the golden RTL has no undriven nets in the log, so it is inert here (inference from the log: the only undriven warnings are on the Revised side).
The hierarchical leg 2 applies module-boundary constants/equivalences it extracts itself (`-constraint`); the **flat** and **direct** runs have none, and they agree, so these did not mask anything.
Variants (`scripts/mk_flat.py`, `scripts/mk_direct.py`): flat = Genus' leg-2 setup with `run_hier_compare` replaced by one flat compare; direct = additionally `read_implementation_information`/`set_verification_information`
removed (Genus' constants, merges, unreachable-flop claims, boundary optimisations are not used), revised = final netlist, `-seq_merge` added, mapping file = Genus' composed RTL->final **name-only** pairs (a wrong pair can only cause a mismatch).
The direct run needs the composed mapping file that leg 1 writes (`analyze_extended_mapping`, XL licence), so run `lec-genus` first.

## Unmapped / unreachable points explained
Golden (RTL) flop bits: **6,236** = 5,208 compared + 81 merged + 947 unreachable (direct run; 6,749 key points = 124 PI + 379 PO + 10 BBOX + 6,236 DFF).
Implementation side: **0 unmapped** in every run (all 5,208 netlist flops map to an RTL flop, all 379 POs and 124 PIs map).
- **Constants (measured).** 388 RTL flops are constant 0. Genus' info supplied 221; Conformal's own analysis agrees on all 221 and finds 167 more (`sequential_constant.json`: 0 inconsistencies; all LEC constants are 0). The direct run, which gets no Genus info, finds the same 388 itself ("(F18) Converted 388 DFF/DLAT(s) in (G) to ZERO/ONE"). They are never loaded with a non-zero value in the RTL itself: upper bits of `trap_cause`/`irq_cause`/`dec_trap_cause`/`mem_trap_cause_val_r` (cause codes are small), `mtvec[1:0]`, `mcountinhibit_q` upper 27 bits (CSR read masks `& 32'h3D`), `refill_addr_bank_q[3:0]` and `tag_din_q[31:20]` (hard-wired 0 in the RTL assignment), `mem_size[2]`, `mem_trap_target_r[1:0]`, `u_mbist_ctrl rec_addr/rec_port` upper bits, the `g_cmp.fail1_q/_n_q` comparator flags of the 10 collars (MBIST compare never enabled in this macro) and `cancel_wait_r_q` (RTL comment "legacy, unused in burst"). Also constant in the RTL: `ex1a_ex1b_reg_q.{dec_trap_valid,dec_do_redirect,dec_mret,dec_is_irq,dec_fence_i,dec_dbg_halt,flush_ex_mem}` (those decode fields come from `ex1c` combinationally instead).
- **Merged (measured).** 81 RTL flops are duplicates of another flop, merged by Conformal itself (77 + 4, "Merged ... DFF/DLAT(s)") in the direct run; Genus' own table lists 144 members in 108 groups (LEC picks a different representative in 108, not a conflict: 0 inconsistencies reported for constants, and the merged points compare EQ: 58 merged + 136 equivalence-class points in the direct run).
- **Unreachable (measured count, classification by group).** 947 (direct) / 922 (flat vs fv_map) / 886 in the hierarchical leg: "all paths to outputs are blocked", i.e. no path to any PO or SRAM pin, so they cannot influence a compare point. Groups (`reports/b4b_direct_rtl_vs_final/unreachable_groups.txt`): dead pipeline-struct fields that are carried through the stages but never read (e.g. `*_reg.csr_wdata`, `*.csr_addr`, `*.pc_target`, `*.mtvec`, `*.mret_pc`, `*.irq_cause`, `*.immediate`, `*.fwd_store`, `*.pre_wdata_aligned`, `*.dec_redirect_target`: the CSR file takes `csr_wdata_ex` straight from EX, `rv32i_core.sv:228,609,743`); `refill_addr_bank_q` bits [31:12] (only [11:4] feed the SRAM address, `rv32i_icache.sv:570`; 96 = 4 banks x 24) and `refill_line_addr_q`/`tag_dout_r`/`tag_din_q` unused bits; `maint_done_q` in the D-cache (output `dc_maint_done` is an unconsumed net, `rv32i_core.sv:345-349`); MBIST `rec_*` upper bits and collar fail flags; 27 `mcountinhibit_q` bits. This classification is from names plus spot RTL reads, it is not a per-bit proof; the tool's "unreachable" itself is the measured fact.
- **Nothing suspicious found for equivalence:** every unmapped item is golden-only, constant-0 or output-blocked, and every output/SRAM pin/flop that is reachable is EQ. A defect of the Synlig struct-select kind (a register deleted because a select elaborated to `x`) would show up as a non-equivalent PO or flop, which is exactly what the negative controls below prove the flow detects.
- RTL-owner observation (not a LEC finding): the constant-0 `ex1a_ex1b_reg_q` decode fields and the many dead struct fields above are real RTL dead state; they are harmless but are the reason 947 flops are unreachable.
- Caveat on constants (same as B4a): "constant 0" uses `-seq_constant_x_to 0`; registers without reset are X until the first clock in silicon, harmless because they feed only constant/unreachable consumers.
- 607 "undriven pins in Revised" (RTL2.13): LEC converts them to free inputs ("Converted 607 internal output port(s) to inout"). Free values can only make equivalence harder, and all points are EQ, so they do not matter; I did not enumerate them individually (my ad-hoc netlist parse mostly found `UNCONNECTED*` nets of unloaded output pins, inference).

## Negative controls (REQUIRED): all four detected
Mutants of the FINAL netlist (`scripts/mk_mutant.py`, re-anchored to Genus names; diffs in `reports/mutant_*.diff.txt`), each run through leg 1 (fv_map vs mutant) and through the direct RTL-vs-mutant compare.
| Mutant | Edit | Two-leg, leg 1 | Direct (RTL vs mutant) |
|---|---|---|---|
| `fwdb_inv` | inverter on the D pin of `fwd_b_ex1c_r_reg` (dud4 forwarding-select flop class) | **NON-EQUIVALENT**, 1 failing point `u_core/fwd_b_ex1c_r_reg` | **NON-EQUIVALENT**, 1 failing point, same flop |
| `swap` | `and3b_1 g371542` pins A_N and C swapped (operand-B forwarding select decode, `fwd_b_sel_r[1:0]`) | **NON-EQUIVALENT**, 65 failing DFFs (`ex1a_ex1b_reg_q_reg[alu_result][*]` ...) | **NON-EQUIVALENT**, 65 failing DFFs |
`make lec-genus-negctl` fails the recipe if any mutant is judged equivalent; it passed.

## Reproduce
```
make -C pnr/commercial/signoff/lec/conformal lec-genus          # Genus two-leg flow, EQUIVALENT, ~2 min
make -C pnr/commercial/signoff/lec/conformal lec-genus-flat     # flat RTL vs fv_map
make -C pnr/commercial/signoff/lec/conformal lec-genus-direct   # RTL vs final netlist, no Genus info (needs lec-genus first for the mapping file)
make -C pnr/commercial/signoff/lec/conformal lec-genus-negctl   # 4 mutant runs, must all be NON-EQUIVALENT
```
Files: `pnr/commercial/signoff/lec/conformal/{Makefile,scripts/{mk_do.py,mk_flat.py,mk_direct.py,mk_mutant.py,flat_tail.tcl,lec_genus*.do}}` (+ `reports/<tag>/lec_log.txt` and friends, text copies; `runs/` is gitignored via `pnr/commercial/.gitignore`).
All tools ran inside `runs/<tag>/`, nothing written to the repo root. Genus run dir untouched (`fv/` is copied into each run dir).

## For the post-route Innovus-netlist LEC
- Same flow shape: use the direct do-file (`mk_direct.py` pattern) with `IMPL=<innovus netlist>`; Genus' `fv_map` legs do not apply because Innovus does not write them. A cheaper cross-check is Genus final netlist (golden) vs Innovus netlist (revised) netlist-to-netlist.
- Name mapping: `MAPFILE` is the Genus-composed RTL->final name pairs; Innovus keeps flop names (`u_core/fwd_b_ex1c_r_reg`, `fwd_b_sel_r_reg[*]`) but may rename escaped/bus bits, so check `report_unmapped_points -notmapped` (must be 0 on the revised side) and fall back to LEC name-based plus function-based mapping where it is not.
- Netlist export: no PG pins, physical-only cells (tap/fill/decap/diode) must be known library cells or excluded in the export, else they become undefined-cell black boxes (the report's "Black box due to undefined cells" must stay "no"). CTS buffers/inverters and hold buffers are combinational and fine; any new flop or clock gate is a LEC mismatch to explain. SRAM stays the only black box (10 instances).
- Re-anchor the mutants: flop `fwd_b_ex1c_r_reg` is stable, gate names (`g371542`, net `n_13445`) are not.
- Keep `-xl`, `LEC_VERSION`, <= 2 threads, safe_run.sh, and keep the 388 constants / 81 merges / unreachable counts as the reference profile: a large change in them after P&R is a reason to look.
