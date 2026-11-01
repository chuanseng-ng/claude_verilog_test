# DC-NXT syn v2 (MCMM), Sky130 `rv32i_cpu_top`: synthesis + Formality LEC (steps B3c, B4f)

**Comparison run, no target.** v2 = the v1 DC arm (`dc_synth_summary.md`) re-synthesised with **four scenarios**: setup `ss` + `tt`, hold `ff` + `tt`.
Why only DC: the Step 1 probe (`synth_ss_probe_step1.md`) confirmed the tt-only/area-recovery weakness for DC (v1 -10.46 ns at nom_ss, zero-wire, vs Yosys -1.92) and
**refuted it for Genus** (v1 +0.61 ns at ss), so the Genus v2 run was **not** made (script prepared, untested).
v1 outputs are untouched; v2 lives in `syn/dc/runs/b3c_dc_mcmm/` (gitignored), committed report copies in `syn/dc/reports_v2/`.
Reproduce: `make -C pnr/commercial/syn/dc dc-synth-v2` (script `scripts/dc_synth_v2.tcl`, run under `licensed_lock.sh` + `safe_run.sh`, 2 cores, 6 GB cap).

## What changed vs v1 (and what did not)
Changed (script diff = libraries, NDM ref libs, parasitics, constraints block, reports):
- `target_library`/`link_library`: tt, ss, ff `sky130_fd_sc_hd` `.db` + the SRAM `.db`; NDM ref libs `sky130_hd_{tt,ss,ff}.ndm` + phys + SRAM NDM (all exist in `pdk/sky130/build/ndm`).
- Scenarios (mapping identical to `pdk/sky130/scripts/mmmc.tcl`): `setup_ss` = ss_100C_1v60 + **max** TLU+, `setup_tt` = tt_025C_1v80 + **nom** TLU+ (setup only), `hold_ff` = ff_n40C_1v95 + **min** TLU+, `hold_tt` = tt + nom (hold only).
  The SDC is `read_sdc`'d once per scenario, unchanged (md5 `3c69635042a9d65cb87e71a9db713e4e`, `syn/dc/reports_v2/sdc.md5`). In both hold scenarios `set_fix_hold [get_clocks clk_i]` (DC repairs hold only when asked).
- Reports per scenario; `write_sdc` per scenario.

Unchanged: the same 28 RTL files (the task text says 26; the list is `make -C pnr sky130-cpu-sv2v-inputs`, as in v1) and 5 defines incl. `SRAM_SKY130`, native SV, SRAM `.db` hard macro + `dont_touch` (10 of 10), `dont_use.tcl`, the floorplan
(`mk_fp_def.py` die/rows/pins + `macro_placement.cfg` macros, 10 placed), met1..met4 routing layers, `compile_ultra -spg` at default effort/auto-ungroup, SVF, `change_names`.

Caveats, all measured:
- **The SRAM lib is TT 1.8 V 25 C only in every scenario (bead `o1i`).** The ss and ff scenarios time the 10 SRAMs with a TT model. The SRAM-limited paths (icache/dcache `*_dout_r` flops, `tag_dout_r`) are therefore not ss-pessimistic in this run.
- TLU+: nom file unchanged since v1 (`nxtgrd/nom/sky130A_nom.tluplus`, 25 Oct); min/max are the files now in `nxtgrd/{min,max}` (26/28 Oct, tuned-ITF generation). v1 used nom for both min and max. Not correlated against OpenRCX or StarRC for synthesis purposes.
- `PSYN-100` x12 ("Layer li1..met5 missing resistance/capacitance") appear at `extract_physical_constraints`; in v2 the TLU+ is set per scenario after the floorplan block whereas v1 set it before. The compile then ran with all four scenarios' TLU+ passing `check_tlu_plus_files`; the
  messages did not stop the flow, but the floorplan step ran without RC in v2. Not investigated further.
- Carried over from v1, not new: `floorplan.rpt` says "pins fixed: 0 of 503" in both runs (v1 report has the same line), so the DC arm's pin placement is not "fixed" in either.
- Host contended (loadavg 9 to 16 from the PD agents): `COMPILE_RESULT` 1,391 s in-script vs 219 s in v1; DC's own "Overall Compile Wall Clock Time" 333.6 s vs 177.3 s. Peak RSS 1.55 GB (v1 1.38 GB). Runtimes are not comparable.

## DC-reported timing (its own SPG/TLU+ wire estimates, ideal clock)
| Scenario | v1 (tt only) | v2 |
|---|---|---|
| setup_ss | not analysed | **0.00 ns** (worst path `u_core_u_csr_mhpmcounter4_q_reg_0_` to `_31_`, 33 levels, 12.51 ns) |
| setup_tt | 0.00 ns | **+2.35 ns** (worst path is SRAM-limited: `u_core_u_icache_gen_data_sram_3__...clk0` to `icache_data_dout_r_reg_3__31_`) |
| hold_ff | not analysed | worst -0.01 ns, **22 hold violations, TNS -0.12 ns** (`u_mbist_ctrl_tg_addr_q_reg_*` shift chain; no delay cells inserted: 0 `dly*` cells) |
| hold_tt | +0.12 ns | 0 violations |
So with the ss scenario in the loop DC met 0 ps at ss and left 2.35 ns at tt; v1 met 0 ps at tt and was -10.5 ns at ss (zero-wire PT, below).

## Neutral PT check (same probe as Step 1: ideal clock, no parasitics, shared SDC, SRAM TT-only)
| Netlist | cells | nom_tt WNS | nom_ss WNS | nom_ss TNS / violators | ss gap vs Yosys |
|---|---:|---:|---:|---:|---:|
| Yosys/ABC (DELAY 3) | 30,369 | +4.759 | -1.919 | -130.1 / 152 | 0 |
| DC v1 | 32,881 | +1.715 | -10.457 | -957.4 / 303 | -8.54 |
| **DC v2 (MCMM)** | 35,644 | **+5.325** | **+1.163** | **0 / 0** | **+3.08** |
| Genus v1 (reference) | 26,347 | +5.498 | +0.606 | 0 / 0 | +2.52 |
DC v2 gains **+11.62 ns** at ss over v1 (and +3.61 ns at tt). Worst v2 ss path: `u_core_fwd_b_sel_r_reg_0_` to `ex1a_ex1b_reg_q_reg_alu_result__0_` (12.35 ns arrival incl. 1.0 ns source latency); the 32-bit ripple `fa` chain is gone.
Same zero-wire caveat as Step 1: this is intrinsic netlist speed, not a closure prediction. Raw: `syn/ss_probe/reports/step2_dc_v2_probe_metrics.tsv`, `step2_worst_dc_v2_ss.txt`.

## QoR v2 vs v1 (DC `report_qor`, scenario-independent area)
| Metric | v1 | v2 | delta |
|---|---:|---:|---:|
| Leaf cells incl. 10 SRAM | 32,881 | 35,644 | +2,763 (+8.4 %) |
| Std-cell area, um2 | 259,850 (comb 152,847 + seq 107,003) | 286,078 (comb 178,796 + seq 107,282) | **+26,228 (+10.1 %)** |
| Flops (excl. SRAM) | 5,284 | 5,284 | 0 (same 18 `dfrtn_1`; `dfxtp_1/_2/_4`: 4,812/229/225 to 4,531/539/196) |
| Buf+inv cells / area um2 | 7,734 / 29,590 | 8,490 / 37,048 | +756 / +7,458 |
| Full adders `fa*` / half adders `ha*` | 60 / 6 | 6 / 58 | ripple full-adder chains replaced |
| Delay (`dly*`) cells | 0 | 0 | hold fixing inserted none |
| Max-tran / max-cap / max-fanout violating nets (DC estimate) | 4,754 / 1,094 / 97 | 6,970 / 541 / 72 | long-wire effect, left to P&R as in v1 |
| FWD_B flops present | 4 | 4 | |
| 138 `OPT-1206` constant-register removals | 138 | 138 | same set size |
| Power (vectorless, no clock tree) | 47.8 mW | 47.7 mW | |
The ss timing is bought with about 10 % more std-cell area (+26,228 um2); the SRAM macros (1,907,125 um2) are unchanged, so the total cell area moves by +1.2 % (2,193,204 vs 2,166,975 um2).

## Formality LEC, RTL == DC v2 netlist (B4f)
`make -C pnr/commercial/signoff/lec/formality lec-dc-v2 lec-dc-v2-negctl lec-dc-v2-svfprobe` (new targets, tags `b4a2_*`; `fm_lec.tcl` unchanged; Formality X-2025.06, v2 SVF, `licensed_lock.sh` + `safe_run.sh`, 2 cores, 46 s and 0.58 GB for the main run).
| Run | Verdict | Detail |
|---|---|---|
| `b4a2_dc_v2_vs_rtl` RTL vs DC v2 netlist | **Verification SUCCEEDED** | 6,233 passing, 0 failing, 0 aborted, 0 unverified, **0 unmatched compare points** (889 unread points, both sides, as expected for the unloaded debug/constant logic) |
| negative control 1: `fwdb_inv` (inverter on D of `u_core_fwd_b_ex1c_r_reg`) | FAILED = detected | 1 failing point, 6,232 passing |
| negative control 2: `swap` (A2<->B2 of `a22oi_1 U10974`, forwarding-mux cone) | FAILED = detected | 1 failing point, 6,232 passing |
| negative control 3: RTL mutant M2 (`fwd_store_sel_r <= ~fwd_b_sel_pre_w`, falsifies the SVF merge claim) | FAILED = detected | 32 failing points (Formality did not trust the SVF merge claim) |
| negative control 4: RTL mutant M3 (`flush_ex_mem = 1'b1`, falsifies the SVF constant claim) | FAILED = detected | 1,112 failing points (SVF constant claim rejected and checked) |
**4/4 negative controls caught; the EQUIVALENT verdict counts.** The v2 netlist is flat (`u_core_*`), so the v1 mutator's anchors (`U1801`, `N1438`-with-`rv32i_core_00000000`) did not apply: `scripts/mk_mutant_v2.py` finds its anchors and fails if absent
(fwdb_inv anchored on the one flop named `*fwd_b_ex1c_r_reg`; swap on the first `a22oi_1` with one input on an `ex1b_ex2_reg_q` bus and one on `ex1c_comb`, with A1!=B1 and A2!=B2 so the function changes).
No Conformal run: there is no Genus v2 netlist.
Not shown by LEC: that the RTL is right, or the SRAM behaviour (black box both sides); the SVF-guided constant registers are verified, not trusted (probe M3).

## Recommendation for re-implementation (b6): see the hand-off report
Files: `scripts/dc_synth_v2.tcl`, `Makefile` targets `dc-synth-v2` / `genus-synth-v2`, `reports_v2/`, `signoff/lec/formality/{Makefile,scripts/mk_mutant_v2.py}`.
