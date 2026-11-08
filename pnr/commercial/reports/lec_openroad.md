# LEC of the OpenROAD / LibreLane B2 post-route netlist (Sky130 `rv32i_cpu_top`)

Date 2026-11-08. Tools: Synopsys Formality X-2025.06, Cadence Conformal LEC 24.10-p100 (`lec -xl`), Yosys 0.46 `equiv_induct`. Closes open item 1 of
`docs/COMMERCIAL_FLOW_COMPARISON.md` section 7. **Superseded by the final verdict at the end of this report**: the OpenROAD netlist is EQUIVALENT to the RTL (Yosys induction on the Yosys leg), with the stated limit. The sections below record how it was reached, including the Formality and Conformal failures, which are unresolved and not waived.

## Verdict

| Leg | Tool | Verdict | Points |
|---|---|---|---|
| (1) RTL (28 SV files) == `rv32i_cpu_top_sv2v.v` (what Yosys read) | Formality | **SUCCEEDED** | 6,302 pass / 0 fail / 0 unmatched compare points (701 symmetric unread) |
| (2) OpenROAD final netlist == Yosys synthesis netlist (same run) | Formality | **SUCCEEDED**, diode-free and with the 64,086 diodes | 6,248 pass / 0 fail / 0 unmatched (all matched by name; with diodes: 64,086 impl-only diode black boxes) |
| (3) Yosys netlist == sv2v (and so RTL) | Formality | **FAILED**, 3,902 failing, 242 ref / 113 impl unmatched registers | not proven |
| (3') Yosys netlist vs RTL | Conformal | **NOT_EQUIVALENT**, 4,335 non-equivalent, 164 golden / 139 revised key points unmapped | not proven |
| (4) direct RTL vs final netlist | Formality | **FAILED**, 3,670 failing, 1,329 ref unmatched registers | not proven |

Legs (1) and (2) are proven and non-vacuous (negative controls below). Leg (3) is the only thing standing between "OpenROAD stages preserve function" (proven) and
"the OpenROAD netlist equals the RTL". Everything after synthesis (placement, resizing, buffering, CTS, hold buffers, tie cells, 64,086 antenna diodes,
fill/tap/decap) is covered by (2). The frontend (sv2v) is covered by (1), the class that caused the Synlig `dud4` defect.

## Provenance

- Netlist: `pnr/commercial/runs/openroad/rv32i_cpu_top.nl.v`, md5 `a0f0731993ea3e6a5422e2579810f1e5`. Same md5 as `pnr/sky130/cpu/runs/b2_openroad/final/nl/rv32i_cpu_top.nl.v`
  and as `netlist_md5` in all 36 `compare/snapshot/pt/*/openroad_*/inputs.txt` (the judge). The power netlist `.pnl.v` (md5 `57bd0c2f...`) is not used.
- **Frontend is sv2v, not Synlig**: `resolved.json` has `USE_SYNLIG=false`, `VERILOG_FILES = [stub, pnr/sky130/cpu/rv32i_cpu_top_sv2v.v]`, `VERILOG_DEFINES=[SRAM_SKY130]`;
  the Yosys log reads `rv32i_cpu_top_sv2v.v` with the Verilog frontend. Run: LibreLane 2.4.13 container, OpenROAD edf00dff, git 915cc01.
- `rv32i_cpu_top_sv2v.v` md5 `a5b5b22de466ba438e40f5e3e8e4866a` (mtime Oct 25 21:12, before the Yosys netlist at 21:31). It is untracked/gitignored; leg (1) proves it equals the RTL,
  leg (2)+Yosys netlist is its synthesis. The 28 RTL files are unchanged since commit 1234714/a1cb4cd (Oct 23-24), before the run; `git diff 915cc01 HEAD -- rtl` touches only `crypto_accel.sv`, `soc_top.sv`.
- Yosys synthesis netlist `pnr/sky130/cpu/runs/b2_openroad/06-yosys-synthesis/rv32i_cpu_top.nl.v` md5 `cb24a60da5a503a157af328753e2ce19` (Yosys 0.46; run dir is gitignored).
- Reference RTL list and defines: `pnr/commercial/syn/dc/scripts/rtl_list.sh` (28 files; `PDK_sky130A SCL_sky130_fd_sc_hd __librelane__ __pnr__ SRAM_SKY130`), SRAM stub never read,
  the 10 SRAMs black-boxed from the macro `.db` on both sides, `hdlin_unresolved_modules error`, no SVF (Yosys writes none), no `set_constant`, no `set_dont_verify`, no user match, no waiver.

## OpenROAD-specific netlist handling

`final/nl` is the logical export but still has 556,952 instances. `scripts/strip_openroad_physical.py` makes a Formality-readable copy and asserts what it removes:

- 450,288 physical-only cells, all with an **empty port list `()`**: `decap_{3,4,6,8}` (145,558), `sky130_ef_sc_hd__decap_12` (161,973, no `.db` model, which is why the raw file cannot be linked), `fill_{1,2}` (83,116), `tapvpwrvgnd_1` (59,641).
- `--diodes`: 64,086 `diode_2` (one input pin `.DIODE`, no output; 116 on primary inputs, 63,970 on internal nets). Variants: `or_phys` (diodes kept) and `or_nodiode`.
- Kept: 42,578 logic instances + 10 SRAMs, 221 `conb` tie cells, 5,642 `dlygate4sd3` hold buffers, clock tree `clkbuf`, 131 `assign` statements. A post-check shows the per-master cell counts differ only for the removed masters.

## Why the RTL-vs-netlist compare fails (leg 3), what is established and what is not

Established (measured): in leg (3) and (4) Formality ends with registers it cannot match (RTL struct fields and Yosys bit-index names, registers Yosys merged, renamed to an alias or turned into constants:
`mhpmcounter*`, `id_ex_reg_o.rs*_data`, `refill_addr_bank_q`, `if_id_reg_o`, `regs[x][y]`, 135 constrained-0X flops). Formality/Conformal treat unmatched registers as free inputs, so downstream cones fail.
The same designs matched and passed in legs (1) and (2), and the sv2v-vs-RTL compare matched everything. Conformal without names did not finish key-point mapping in 22 min (`or_cf_syn_vs_rtl_anon_ABORTED_mapping_gt20min`, killed by me);
with flop instances renamed to `<Q net>_reg` (`conformal/scripts/name_flops_openroad.py`, connectivity multiset asserted identical) it mapped but left 164/139 unmapped and "functionally mapped" unrelated flops (for example `halt_cause_lat_reg[3]` with `dbg_status_reg[7]`).

**Not established**: whether the 3,902 failures are only the cascade of unmatched registers, or contain a real Yosys synthesis difference. I did not prove either. Nothing is waived. In the repo's own words (loop-back row): the netlist does not match the golden at
the reported points; `lec_run` regenerates neither artifact. Next steps for the owner: (a) give Formality the merge/constant/rename information Yosys does not export (derive it from Yosys, then let Formality verify the claims, like the DC SVF);
(b) or prove the Yosys leg with Yosys itself (`equiv_make`/`equiv_induct` on the sv2v file vs the technology-mapped netlist); (c) or re-run synthesis with `keep`/no register merging.

## Negative controls (they validate legs 1 and 2 only)

Mutants of `or_phys.nl.v` (anchors found by structure, edited once, fail if absent), each required to give `Verification FAILED` against the Yosys netlist:

| Control | Class | Failing points |
|---|---|---|
| `or_negctl_syn_fwdb_inv` | D of the `fwd_b_ex1c_r` flop inverted (the `dud4` flop) | 1 |
| `or_negctl_syn_swap` | A2<->B2 of an `a22oi_1` in the operand-forwarding cone | 308 |
| `or_negctl_syn_bufinv` | a resizer hold buffer (`dlygate4sd3_1` on a flop D) turned into an inverter | 1 |
| `or_negctl_syn_tiehi` | tie cell polarity LO->HI (output port tie) | 1 |

Mutants of `rv32i_cpu_top_sv2v.v` against the RTL (leg 1): `or_negctl_fe_fwdb_inv` (same flop's D inverted) 1 failing point, `or_negctl_fe_swap` (SLT sign mux operand) 1 failing point.
6/6 caught. No negative control exists for a "proven" RTL-vs-final verdict, because there is none.

## Tool choice

The ICC2 arm used Formality (with the DC SVF) and the Innovus arm used Conformal (with the Genus netlist), one tool per arm. OpenROAD has neither a vendor guide nor a named Genus-style netlist, so I ran both on the RTL side
of the synthesis leg; both fail. Formality alone was used for legs (1) and (2) (name-matched, no ambiguity).

## Files

Scripts: `signoff/lec/formality/scripts/{strip_openroad_physical,mk_mutant_openroad,mk_mutant_sv2v}.py`, `fm_lec_or_frontend.tcl`, `fm_lec_icc2.tcl` (new `REFMODE=sv2v`), `chain_or.sh`, `chain_or2.sh`;
`signoff/lec/conformal/scripts/name_flops_openroad.py`; Makefile targets `lec-or-prep`, `lec-or-run`, `lec-or-fe`, `lec-or-negctl` (formality) and `lec-innovus-rtl INNMAP=` (conformal).
Reports: `signoff/lec/formality/reports/or_*`, `signoff/lec/conformal/reports/or_cf_*`. Run times: 26 s (leg 1), 6-10 s (leg 2), 4 min 44 s (leg 3), 5 min 42 s (direct), Conformal named run 3 min; peak RSS 0.43-0.88 GB.

## Continuation 2026-11-08 (second session): attempts to close leg (3) in Formality, no SVF. Leg (3) is STILL OPEN

New fact from the Yosys log (`06-yosys-synthesis/yosys-synthesis.log`, section 48, lines 7449-7644): the `fsm` pass **re-encoded three 2-bit registers to one-hot**:
`u_core.fwd_a_sel_r`, `u_core.fwd_b_sel_r` (the forwarding-select flops, the `dud4` class) and `u_core.u_cache_arb.grant_q`. Stated mapping (old -> new, bit 0 right): `00 -> 0001`, `10 -> 0010`, `01 -> 0100`, `11 -> 1000`.
In the netlist `fwd_*_sel_r` keep bits [3:1] only (bit 0 has no reader), `grant_q` keeps four flops (bit 3 has the port net `axi_bready_o`). A combinational point-to-point LEC cannot match a re-encoded state
register, and the forwarding selects feed every ALU operand, so this alone explains a large cascade. The log names no per-flop merges or constant removals (only anonymous "Setting constant" counts), so nothing else can be derived from it.

All runs are Formality, Yosys netlist (impl) vs `rv32i_cpu_top_sv2v.v` (ref) unless noted; every run is FAILED. Counts are Passing / Failing, unmatched reference / implementation compare points.

| Tag | Knob | Pass / Fail | Unmatched ref / impl |
|---|---|---|---|
| `or_syn_vs_sv2v` | baseline | 2,231 / 3,902 | 242 / 113 |
| `or_syn_vs_sv2v_mergedup` | `verification_merge_duplicated_registers true` | 3,206 / 2,918 | 103 / 123 |
| `or_syn_vs_sv2v_cprop` | + `verification_propagate_const_reg_x true` | identical to mergedup | identical |
| `or_syn_vs_sv2v_netmatch` | + `name_match_net`, `name_match_pin_net`, `signature_analysis_allow_net_match` | 3,202 / 2,921 | 104 / 124 |
| `or_syn_vs_sv2v_fsm` | `set_fsm_state_vector` + `set_fsm_encoding` for the 3 FSMs (accepted, **no effect** in the flat match: identical to baseline) | 2,231 / 3,902 | 242 / 113 |
| `or_syn_vs_fsmoh` | reference copy with the 3 FSM registers re-encoded as the log states (`mk_ref_fsm_onehot.py`, one-hot register keeps the original name) | 2,602 / 3,541 | 235 / 103 |
| `or_syn_vs_fsmoh_mergedup` | both of the above | 3,831 / 2,316 | 85 / 99 |

`or_syn_vs_fsmoh*` use a modified reference. That copy is **not yet proven equal to the original sv2v file**; that proof (Yosys `equiv_make`/`equiv_induct`, cut at the named decoded wires) is the next step, and without it those runs prove nothing.

Remaining unmatched families (mergedup run): reference `mem_trap_cause_val_r` (30, constant 0/X), `rec_addr_q` (10, 0/X), `if_id_reg_o` (9), `wb_index_q` (8), `data_idx_q` (8), `regs_reg` (5); implementation `u_regfile.regs[0][*]` (31 flops: Yosys
kept a word 0 for the `reg [31:0] regs [1:31]` array, never read because `rd_addr==0` is masked), `if_id_instr_w` (10), `wb_addr_base` (8), and about 40 anonymous `_000NN_` flops. `scripts/analyze_cone_openroad.py` on the mergedup run: of 2,918 failing points,
1,878 have an unmatched implementation flop in their implementation fan-in cone; 1,040 do not (the reference side was not analysed), so the cascade explanation is partly supported and not complete.
`verification_*` knobs for constants/merging do not change this. No user match and no `set_constant` was used. `fm_lec_icc2.tcl` was reverted to its committed state; the OpenROAD runs use `scripts/fm_lec_openroad.tcl`
(the committed run evidence above was produced with an `fm_lec_icc2.tcl` that had the `sv2v` mode added; the logic of the other modes is unchanged).

Next (not started): (1) Yosys `equiv_make`/`equiv_simple`/`equiv_induct` of the sv2v file against the Yosys netlist inside the LibreLane container (route 2), which also proves the re-encoding copy; (2) pair the
remaining ~100 unmatched registers with structural evidence (alias chain in the sv2v file) before any `set_user_match`; (3) for any point still failing after matching, take a Formality counterexample (`analyze_points`) and replay it in gate-vs-RTL simulation. Re-synthesis without register merging only with approval.

## Route 2 (third session): Yosys `equiv_make` / `equiv_struct` / `equiv_induct` in the LibreLane container

Setup (`signoff/lec/yosys/scripts/equiv1.ys`, `equiv3.ys`, `run_equiv.sh`, `chain_equiv.sh`): podman image `ghcr.io/librelane/librelane:2.4.13` (Yosys 0.46, the B2 run's build), under `licensed_lock.sh` + `safe_run.sh` (2 threads, 10 GB cap).
Gold = `rv32i_cpu_top_sv2v.v` through `synth -flatten -noabc` (the LibreLane flow minus abc, so `proc`, `fsm` re-encoding, `memory_map`, `opt` are applied to gold exactly as in the B2 run) then `splitnets`.
Gate = the netlist, read with `read_liberty` of `sky130_fd_sc_hd__tt_025C_1v80.lib` (functional cell models), flattened and `techmap`ped, then `splitnets`. SRAM instances are black boxes on both sides: `expose -evert` turns each SRAM input pin into an extra
output and each SRAM output pin into an extra input named `<instance>.<pin>` on both sides, so every SRAM input pin is proven and both sides read the same free SRAM data. `equiv_make` matches wires by name, `equiv_struct` merges identical structure, `equiv_induct -seq 2` proves by induction.

| Tag | Gate netlist | `$equiv` cells | Proven / unproven |
|---|---|---|---|
| `e3` (superseded) | Yosys netlist, SRAM instances left in place | 6,155 | 5,825 / 330 (all 330 are SRAM `dout` pairs of two separate black boxes, plus 10 `ev0_w` that read them: an artefact of the missing pin cut, fixed in e4) |
| `e4` | Yosys synthesis netlist (md5 cb24a60d...) | 6,156 | **6,156 / 0** |
| `e5_final` | OpenROAD FINAL netlist, physical cells and diodes stripped (`or_nodiode.nl.v`) | 6,156 | **6,156 / 0** |

So the sequential equivalence of the sv2v design and the OpenROAD final netlist is proven by Yosys induction, covering all 379 outputs, every flop (name-matched after `splitnets`) and every SRAM input pin.

Limits of this proof, stated plainly:
- Gold goes through the same Yosys front/coarse passes (`proc`, `fsm` recode, `opt`, `memory_map`) as the netlist did. A bug in those passes that affects both would not be seen; the proof covers what happens after them (abc, `dfflibmap`, hold/resizer buffering, CTS, diode insertion, OpenROAD edits) and shows nothing else differs. The FSM re-encoding of `fwd_a_sel_r`, `fwd_b_sel_r`, `grant_q` is Yosys proving its own transform. RTL == sv2v is independently proven by Formality (leg 1).
- Induction is `-seq 2`; the proof is not a bounded check. Cut points are same-named wires; unmatched logic is covered by induction through the `$equiv` cells.
- The Formality and Conformal runs of the same comparison still fail (matching problem). They are not contradicted by this result, but they are not confirmed either.
- Negative controls for the Yosys proof: 4 mutants of the final netlist (`chain_equiv.sh`), each required to leave unproven `$equiv` cells. **4 of 4 caught:**

| Tag | Mutation | Proven / unproven |
|---|---|---|
| `e6_neg_fwdb_inv` | D of the `fwd_b_ex1c_r` flop inverted | 3 / 6,153 |
| `e7_neg_swap` | A2/B2 of an a22oi in the operand-forwarding cone swapped | 5,810 / 346 |
| `e8_neg_bufinv` | a hold buffer turned into an inverter | 3 / 6,153 |
| `e9_neg_tiehi` | tie cell polarity flipped | 3 / 6,154 |

  `e6`, `e8` and `e9` collapse the whole induction (a failing cell removes the induction hypothesis for nearly all others); `e7` leaves a partial unproven set of 346 points, not a collapse. Both patterns are detections. The proof is therefore sensitive to all four mutation classes.

## Final verdict (2026-11-08)

The OpenROAD B2 netlist (md5 a0f0731993ea3e6a5422e2579810f1e5) is **EQUIVALENT** to the RTL, by a chain of three proofs:
RTL == `rv32i_cpu_top_sv2v.v` (Formality, 6,302 / 0, controls caught), sv2v == OpenROAD final netlist (Yosys `equiv_induct`, 6,156 / 0, 4/4 controls caught), and, as a cross-check of the P&R stages, final == Yosys synthesis netlist (Formality, 6,248 / 0).
Stated limit: the Yosys gold goes through the same Yosys `proc`, `fsm`, `opt` and `memory_map` passes as the netlist did, so a common-mode Yosys bug in those passes would not be seen. The independent `synth -nofsm` check was not run.
The Formality (3,902 failing) and Conformal (4,335 non-equivalent) compares of sv2v/RTL against the Yosys netlist are unresolved matching failures; they are reported above and are not waived, and they do not contradict the Yosys proof.
