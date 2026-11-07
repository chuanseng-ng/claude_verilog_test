# Formality LEC, RTL == DC-NXT netlist, Sky130 `rv32i_cpu_top` (step B4a)

**Verdict: EQUIVALENT (Verification SUCCEEDED), with the SVF.** 6,233 passing / 0 failing / 0 aborted / 0 unverified compare points,
0 unmatched points. The negative controls fail as required (below), so the verdict counts.
Git base `223296b`, branch `feat/commercial-pd-sky130`. Formality X-2025.06, `set_host_options -max_cores 2`, under `safe_run.sh` (6 GB cap).

## Inputs
| | |
|---|---|
| Reference | the 28 native SV files + 5 defines of `make -C pnr sky130-cpu-sv2v-inputs` (via `pnr/commercial/syn/dc/scripts/rtl_list.sh`), `read_sverilog`; SRAM stub not read |
| Implementation | `pnr/commercial/syn/dc/runs/b3a_dc_tt/out/rv32i_cpu_top.nl.v` (md5 `698e56f0...`, 3 modules, 131 assigns) |
| Guidance | `.../out/rv32i_cpu_top.svf` (md5 `0740dd79...`), loaded with `set_svf` before any read |
| Libraries | impl: `sky130_fd_sc_hd__tt_025C_1v80.db` + SRAM `.db`; ref: SRAM `.db` (`read_db -technology_library`) |

## Results (main run `runs/b4a_dc_vs_rtl`)
| Compare points | BBPin | Port | DFF | LAT | Loop/BBNet/Cut | Total |
|---|---|---|---|---|---|---|
| Passing | 570 | 379 | 5,284 | 0 | 0 | **6,233** |
| Failing / aborted / unverified | 0 | 0 | 0 | 0 | 0 | **0** |

- Matching: 6,233 by name, 0 by signature, 0 by topology, 436 primary-input/black-box-output matches, **0 unmatched**.
  889 reference "unread points" are signals with no fanout (e.g. `_unused_*` suppressors, unused debug outputs): they cannot influence a compare point.
- DFF 5,284 equals DC's flop count, so every implementation flop (incl. the 18 `dfrtn_1` negedge async-reset flops and the 4 `fwd_b_*` flops) is a verified compare point.
- **Black boxes:** 10 of 10 `sky130_sram_1kbyte_1rw1r_32x256_8` instances, a Technology Macro cell (`m`) from the `.db` on both sides, matched by (flattened) instance
  name (`u_icache_gen_data_sram_0__u_data_sram` etc. resolved by the SVF `change_names`/`instance_map`). Their 570 input pins are compare points
  (BBPin, all equivalent); outputs are free primary inputs on both sides. No other black boxes, no unresolved modules (`hdlin_unresolved_modules error`).
- **SVF:** 1,177 guidance commands, 1,177 accepted, 0 rejected (ungroup 35, change_names 85, constant 718, reg_constant 138, inv_push 18,
  merge 10, reg_merging 5, instance_map 28, uniquify 2, other housekeeping). Note from Formality: no `guide_hier_map` in the SVF (DC `hdlin_enable_hier_map`
  not set); harmless here (no rejections, no aborts).
- Runtime/memory: 32.5 s wall, peak RSS 569 MB (match + verify, 2 cores). Reports: `pnr/commercial/signoff/lec/formality/reports/`.
- DFT: `scan_mode_i`, `scan_en_i`, `scan_in_i`, `mbist_*` are ordinary primary inputs, free on both sides, so the equivalence holds for all values;
  no DFT constants were needed. The RTL is not scan-inserted (`scan_out_o` is tied 0, `scan_en`/`scan_in` unread by design, `rv32i_cpu_top.sv` ~l.137-148).
  No clock gate exists in the Sky130 macro. Equivalence therefore covers functional AND test-mode logic as written.

## Settings (every one has a reason in `scripts/fm_lec.tcl`)
- `set_host_options -max_cores 2`: host rule (VMware guest hard-locks under full vCPU load).
- `set_svf <DC svf>` before reads: DC auto-ungroups, renames (`change_names`), removes 138 constant regs, merges duplicate regs, pushes 18 inversions; Formality cannot
  discover those unaided (see ablation).
- `hdlin_unresolved_modules error` (the default, kept explicitly): a missing RTL file must not silently become a black box.
- `verification_failing_point_limit 0`: report all failing points, not 20.
- `read_db -technology_library` of the SRAM `.db` in both containers: the 10 macros are the same cell on both sides. Order matters: the implementation `.db`
  files are read after the reference top is set (otherwise FM-236 and unlinked library cells, FE-LINK-2: measured).
- NOT used: no `set_constant`, no `set_dont_verify_point`, no `set_user_match`, no `verification_set_undriven_signals`, no waivers.

## Is the SVF masking anything? (ablation and probes)
1. **No-SVF run** (`b4a_dc_vs_rtl_nosvf`): FAILS (3,821 pass / 2,412 fail). 143 reference registers are unmatched: 136 that Formality itself classifies as
   `Constrained 0X` (never loaded with a non-zero value: upper bits of `mem_trap_cause_val_r`, `*_trap_cause`, `irq_cause`, `mtvec[1:0]`, icache `tag_din[31:20]`,
   `mem_size[2]`, `u_mbist_ctrl/rec_*`), and 7 DFFs (2x `flush_ex_mem` pipeline copies, and 5 duplicates merged by DC: `fwd_store_sel_r[1:0]`, `fwd_store_ex1c_r`,
   `fwd_store_ex1b2_r`, `mem_trap_redirect_r`). The failing points are fan-out of those unmatched registers, the expected consequence, not independent bugs.
   The 138 SVF `reg_constant` entries are exactly this set (all value 0).
2. **Probe M2 (merge claim)**: RTL copy with `fwd_store_sel_r <= ~fwd_b_sel_pre_w` (`rv32i_core.sv:535`) while the SVF still says it is merged with `fwd_b_sel_r`:
   Formality FAILS (32 failing points, at the store-forwarding consumers). The merge guidance is not blindly trusted.
3. **Probe M3 (constant claim)**: RTL copy with `ex1a_ex1b_nop.flush_ex_mem = 1'b1` (`rv32i_pipeline_pkg.sv:335`): Formality REJECTS the 2 SVF `reg_constant`
   entries for `flush_ex_mem` (136 accepted / 2 rejected) and FAILS (1,112 failing points). The constant guidance is checked against the RTL, not blindly applied.
   (For the real RTL the invariant holds: every branch of the hazard unit that sets `flush_ex_mem` also flushes `ex1a_ex1b`/`ex1c_ex1b`, which reload the NOP, whose
   field is 0.)

## Negative control (REQUIRED): both mutants detected
| Mutant (`scripts/mk_mutant.py`) | Edit | Result |
|---|---|---|
| `fwdb_inv` | inverter inserted on the D pin of flop `fwd_b_ex1c_r_reg` (the dud4 forwarding-select flop class) | **FAILED**, 1 failing point: `u_core/fwd_b_ex1c_r_reg` (6,232 pass) |
| `swap` | A2/B2 data inputs swapped on `a22oi_1 U1801` in the operand-B forwarding mux cone | **FAILED**, 33 failing points: `ex1a_ex1b_reg_q_reg_alu_result[*]` etc. (6,200 pass) |

## Observations and residual caveats
- The 222 nets Formality calls "undriven" in the implementation (FM-399) are all outputs of the submodules `rv32i_core_00000000` / `rv32i_dcache`
  (constant AXI low bits/len, unused debug outputs); none is in `rv32i_cpu_top`, which carries them as `assign` feed-throughs from a tie net, and all 379 top
  ports compare equal. I did not separately prove that no logic reads one of those submodule nets (inference: the parent's connections are unloaded
  `SYNOPSYS_UNCONNECTED_*` nets).
- This LEC says RTL == netlist. It says nothing about the RTL being right (functional proof against the golden model is the sim/gate-level work of dud4) nor
  about the SRAM macro behaviour (black box on both sides; its input pins are checked, its outputs are free).
- The 136 never-loaded registers: equivalence assumes they are 0 (no register in silicon is X after the first clock; some have no reset, so they are
  indeterminate until the first clock edge; harmless since they feed only constant-0 consumers).
- Single corner: logic equivalence is corner independent; the netlist is the tt-mapped DC output only.

## For the post-route LEC (ICC2 netlist), later step
- Same reference. Implementation = ICC2 `write_verilog` netlist (with PG pins stripped or `-no_physical_only_cells`; filler/tap/decap and antenna diodes need
  `set_black_box`-free handling: they are library cells with no function in the `.db`, so include `sky130_fd_sc_hd__{tap,fill,decap,diode}` or the NDM-derived verilog).
- Chain the SVFs: ICC2 writes its own SVF/`set_svf` additions (CTS clock tree buffers/ICGs, hold buffers, scan-free). Formality takes several: `set_svf {dc.svf icc2.svf}`
  (order of tool flow). The DC netlist is NOT a valid reference to compare against unless the same SVF chain is applied; compare ICC2 vs RTL with both SVFs, or ICC2 vs DC netlist
  (netlist-to-netlist, no SVF needed for the second hop, much cheaper) as the cross-check.
- Expect `_BAR` ports and ungrouped names to persist; the SRAM instance names are already flat in the DC netlist (`u_icache_gen_data_sram_N__u_data_sram`), ICC2 keeps them.
- Reuse `fm_lec.tcl` with `IMPL=<icc2 netlist> SVF=<svf>`; the `lec-dc-negctl` mutator anchors on DC instance names (`U1801`, `fwd_b_ex1c_r_reg`) and must be re-anchored (the flop name
  `fwd_b_ex1c_r_reg` is stable, `U1801` is not).

## Reproduce
```
make -C pnr/commercial/signoff/lec/formality lec-dc            # EQUIVALENT, ~35 s
make -C pnr/commercial/signoff/lec/formality lec-dc-negctl     # both mutants must FAIL (the target errors otherwise)
make -C pnr/commercial/signoff/lec/formality lec-dc-svfprobe   # RTL-side probes of the SVF merge/constant guidance
make -C pnr/commercial/signoff/lec/formality lec-dc-nosvf      # ablation (expected FAIL)
```
Files: `pnr/commercial/signoff/lec/formality/{Makefile,scripts/fm_lec.tcl,scripts/mk_mutant.py}` (committed), `runs/` (gitignored), `reports/<tag>/` (txt copies).
