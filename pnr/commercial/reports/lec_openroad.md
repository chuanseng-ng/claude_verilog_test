# LEC of the OpenROAD / LibreLane B2 post-route netlist (Sky130 `rv32i_cpu_top`)

Date 2026-11-08. Tools: Synopsys Formality X-2025.06, Cadence Conformal LEC 24.10-p100 (`lec -xl`). Closes **part** of open item 1 of
`docs/COMMERCIAL_FLOW_COMPARISON.md` section 7. **The OpenROAD netlist is NOT proven equivalent to the RTL.** One leg (Yosys synthesis) is unproven
because both tools fail on it; the failure is not root-caused. This is an escalation, not a waiver.

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
