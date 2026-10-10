# ASAP7 CPU macro netlist vs RTL differential (beads `ma7` / `u99` / `dud4`)

Date 2026-10-10. Question: is the ASAP7 `rv32i_cpu_top` miscompile proven in `u99`/`ma7`
(`DBG_GPR[4]` = `0x30` instead of `0x0c`; `BEQ x2,x3` with 9 == 9 not taken) the same defect that `dud4`
root-caused on Sky130 (Synlig elaborates two hazard-unit port connections as `5'x`), or does ASAP7 have a second
cause (ma7's "`OPT_MUXTREE` mis-elaborates the runtime-indexed regfile read mux")? Test only: no PD run, no config
change, no macro view touched. Statements are tagged MEASURED or INFERRED.

## Verdict

**ma7 = dud4 (same defect), for the programs and netlists covered.** The two netlists that carry the two
`5'x` hazard-unit connections (the committed macro and a fresh Synlig synthesis of main RTL) reproduce the u99/ma7
failure exactly, in two independent simulators. The two netlists that do not (Synlig with the two part-selects
routed through a named wire; and the sv2v frontend) are identical to RTL on all 6 programs and pass all 124 cells of
the 31-register x (rs1, rs2, both, debug) matrix. **No second cause was found and the ma7 regfile read-mux /
`OPT_MUXTREE` hypothesis is not supported**: the regfile read path is correct in both clean netlists, and
`OPT_MUXTREE` removal counts and the regfile `$mem` structure are identical across all three synthesised arms
(PD agent's `NOTES.md`).

What this does NOT establish: formal equivalence (6 programs, not exhaustive); that the committed macro is bit-identical
in behaviour to arm S on programs not run; the GPU macro; anything about P&R-introduced faults beyond "the
committed post-P&R netlist behaves like the synthesis-only Synlig netlist on all 6 programs".

## Provenance (MEASURED)

Netlists from the PD agent's synthesis-only experiment, `/nobackup/claude_sim_build/dud4/asap7/` (method, configs,
census in its `NOTES.md`). sha256 re-verified before use:

| arm | netlist | frontend | sha256 |
|---|---|---|---|
| committed | gunzip of `pnr/asap7/soc/macro/rv32i_cpu_top.nl.v.gz` (post-P&R, built at RTL `999e44a`) | Synlig (config `USE_SYNLIG:true`; "built by Synlig" is inferred from its flop count 4863 and no `fwd_b_*`, its run log is gone) | `a416d23f038065433eafa81553e85b9d599892dc9e6da64ca632563b6d1da0b2` |
| S | Synlig synthesis, unmodified main RTL | Synlig | `a2abef9c8f5d024bc512a8bb09ab5fdcb39ed86c9b14d01e03b72b22b5efe046` |
| W | Synlig + the two hazard-unit part-selects routed through a named full-width wire | Synlig | `505b939796da1977ec8ab5243008b4eea66ed4f0175b2471fe9e7fb6d20d3eee` |
| V | sv2v frontend | sv2v | `c2d7f3f37d7d08bece3fd0f8517eef4b682a19af9ee0268353d19a92f6216e24` |

Flop counts (PD agent): committed 4863, S 4863, W 4868, V 4868 (`fwd_b_*` bank present only in W and V).

RTL arms (this test): **main (CPU RTL identical to `5eb5f63`)** for S/W/V; **`999e44a`** (the commit the committed macro was
built at, GH #96 run 23) for the committed macro. The two RTL arms were compared with each other: IDENTICAL on all 6
programs, cycle-exact on every output port, so the committed-vs-main RTL cleanups (declare-before-use,
`default_nettype`, empty blocks; hazard-unit lines and regfile unchanged) do not change observable behaviour and the
choice of RTL reference does not matter for the verdicts below (committed vs `999e44a` and vs main give the same
result, MEASURED).

Committed-netlist physical cells: it instantiates `DECAPx1/2/4/6/10`, `FILLER`, `FILLERxp5`, `TAPCELL` (40,359 lines).
None has a port connection (the netlist has no power pins), so they were **removed** with `asap7/strip_physical.sh`
(function-neutral by construction; stub modules would be equivalent). Every other cell type is covered (checked per
netlist) by the Liberty-derived combinational models plus `asap7_seq_cell_models.v`; the 10 SRAM macros use
`asap7_sram_1rw_256x32_model.v`. The RTL arm uses the same SRAM and ICG models (`SRAM_ASAP7`, `USE_ICG_CELL`).

## Method

* **Simulator 1: yosys 0.62 `sim`**, the original u99/ma7 harness unmodified (`run_cpu_macro_check.sh`,
  `run_cpu_macro_check_branch.sh`, `tb_cpu_macro_check.v`; Liberty `read_liberty -ignore_miss_func` models). Programs:
  `ma7_straight` (u99) and `ma7_branch` (ma7 step 1). `DBG_GPR[4]` is the testbench's captured APB read, the commit
  stream comes from the VCD. Wrapper: `asap7/run_yosys_gate.sh`.
* **Simulator 2: Verilator 5.048**, cycle-exact. One testbench (`asap7/tb_asap7_cpu_check.sv`, derived from the dud4
  `tb_sky130_cpu_check.sv`) for both arms; gate arm = netlist + Liberty-derived cell models (`asap7/gen_cell_lib.sh`),
  RTL arm = RTL tree with the same SRAM/ICG models. All 6 programs of the dud4 set (`trivial`, `ma7_straight`,
  `ma7_branch`, `sweepA/B/C`); compared: commit stream, AXI writes, 32 debug GPR reads and a per-cycle trace of every
  output port (`sky130/compare_arms.py diff`), plus the 31-register port matrix (`sky130/port_matrix.py`).
* Every yosys/Verilator job ran under `systemd-run --user --scope -p MemoryMax=5G -p MemorySwapMax=0`.

### Harness fix found on the way (MEASURED)

The dud4 TB's APB sequencer never completes on main-vintage RTL (0 debug reads, TIMEOUT even in the RTL arm). Cause: the
TB drove APB inputs with non-blocking assignments at the clock edge; under Verilator `--timing` a TB process resumed by
a posedge runs before the DUT's clocked logic of the same edge, so the DUT already saw the new inputs at that edge and the
registered `pready` came one cycle earlier than the sequencer expected. `tb_asap7_cpu_check.sv` drives APB inputs 1 ns
after the edge with blocking assignments; then all 32 debug reads work on the RTL arms (`trivial`: `x1 = 5`, rest 0)
and the port matrix and debug-GPR comparison are available for main-vintage RTL (they were not in the dud4 main-RTL
pair). The other TB inputs (AXI responders) still use NBAs at the edge; they are identical in both arms and were
unaffected (cycle-exact agreement of the clean arms).

## Result 1: the two ma7 programs, yosys `sim` (original harness), four netlists (MEASURED)

| netlist | `ma7_straight`: `DBG_GPR[4]` (RTL `0x0c`) | `ma7_branch`: `BEQ x2,x3` (x2 = x3 = 9, must be TAKEN) | `ma7_branch`: `DBG_GPR[4]` (RTL `0x0e`) |
|---|---|---|---|
| committed (post-P&R) | **`0x30`** FAIL | **not taken**, retires WRONG marker `0x14`, parks at `0x18` FAIL | **`0x2e`** FAIL |
| S (Synlig, main RTL) | **`0x30`** FAIL | **not taken**, parks at `0x18` FAIL | **`0x2e`** FAIL |
| W (Synlig + workaround) | `0x0c` PASS | taken, retires `0x20`,`0x24`, parks at PASS `0x28` | `0x0e` PASS |
| V (sv2v) | `0x0c` PASS | taken, parks at `0x28` | `0x0e` PASS |

Commit streams: committed and S identical (73 commit edges); W and V identical (70).

## Result 2: six programs, Verilator, cycle-exact vs RTL (MEASURED)

"IDENTICAL" = commit stream, AXI writes, 32 debug GPR reads and the per-cycle trace of every output port all equal.

| gate netlist (RTL ref) | trivial | ma7_straight | ma7_branch | sweepA | sweepB | sweepC | port matrix (124 cells) |
|---|---|---|---|---|---|---|---|
| committed (`999e44a`) | IDENT | DIVERGES | DIVERGES | DIVERGES | DIVERGES | DIVERGES | 96 FAIL |
| S (main) | IDENT | DIVERGES | DIVERGES | DIVERGES | DIVERGES | DIVERGES | 96 FAIL |
| W (main) | IDENT | IDENT | IDENT | IDENT | IDENT | IDENT | **124 / 124 PASS** |
| V (main) | IDENT | IDENT | IDENT | IDENT | IDENT | IDENT | **124 / 124 PASS** |

(committed vs main RTL gives the same divergences as vs `999e44a`; `rtl_999` vs `rtl_main` is IDENTICAL on all 6.)
Failing-arm signatures, identical on committed and S: `ma7_straight` x2/x3/x4 = `0x0c/0x18/0x30` (RTL `0x07/0x0c/0x0c`);
`ma7_branch` first commit divergence #5 (BEQ not taken, pc `0x14` instead of `0x20`); sweeps A/B/C all diverge at commit #69
(first MMIO store at pc `0x114`, restart at pc 0, 1392 commits and 0 AXI writes against 916 commits and 116 writes).
This is the Sky130 dud4 signature, number for number.

Caveat on the failing matrix: on S and committed the sweeps derail at the first store, so the 96 FAIL cells are
"the program never reached the store", not 96 independently faulty register read cells. The clean verdict on the regfile
read path comes from W and V (124/124). The debug-read column passes for 28 of 31 registers on S (x2, x30 and one more fail), i.e. most of the
registers hold the expected final value; the failing ones are those written by wrong results.

## Controls (MEASURED unless marked)

* **(a) positive:** `trivial` is IDENTICAL on all four netlists and both simulators agree on `ma7_straight`/`ma7_branch`
  verdicts on all four (yosys `sim` and Verilator give the same `x4` and the same branch outcome).
* **(b) the gate arm really executes:** 74 / 96 / 196 commits on trivial / straight / branch, PCs advance through the
  expected sequences, the clean arms retire 916 commits and perform 116 AXI stores in each sweep; no stuck-in-reset
  and no X (all debug reads defined).
* **(c) negative (fault injection into arm V, clean baseline IDENTICAL):** stuck-at-0 on the sinks of a single net,
  `asap7/inject_stuck.py`. `u_core.mem_wb_reg[160]` (INFERRED from the struct packing: instruction bit 21): detected in **5 of 6** programs (all but `trivial`);
  `u_core.mem_wb_reg[150]` (INFERRED: instruction bit 11 = `rd[4]`): detected in **4 of 6** (`ma7_branch`, `sweepA/B/C`; not
  `trivial`, nor `ma7_straight`, which only writes x1..x4 so `rd[4]` is always 0 and the stuck-at is invisible). **Limitation:** only nets that keep a name
  after ASAP7 mapping can be targeted (`mem_wb_reg` pc/instruction bits); the regfile storage, read mux and hazard-compare
  nets are anonymous, so no fault could be injected *into the regfile read mux* as the Sky130 control did. The injected
  faults are on the commit-observation path. The sensitivity of the differential to a datapath fault is instead shown by
  arms S and committed, which are real datapath faults and are detected in 5 of 6 programs.
* **(d) X / initialisation:** random power-up state (`+verilator+rand+reset+2`, seeds 7 and 23) on the RTL arms and all four
  gate arms: every arm is IDENTICAL to its own zero-initialised run on all 6 programs, and gate-vs-RTL verdicts are unchanged
  (W, V: 6/6 identical; S, committed: 1/6, only `trivial`). The yosys runs use `-zinit`. INFERRED: that the randomisation
  actually changed the initial state was not independently checked (same mechanism as the dud4 control).

## First divergence and mechanism

MEASURED (per-cycle boundary trace, `asap7/first_divergence.py`), arm S vs RTL main:

* `ma7_straight`: the commit stream and every output port are identical for the whole run; the first differing port value
  is the debug read of x2 (cycle 439, `prdata` `0x7` vs `0xc`). Same on committed vs `999e44a`. I.e. the instruction
  stream is fetched and retired correctly and only the *data* computed is wrong.
* `ma7_branch`: first differing port cycle is 39, `debug_pc_src` / `debug_take_branch_jump` asserted in RTL (BEQ taken) and
  not in S; the commit stream diverges at commit #5.

Arithmetic mechanism (the failing values are reproduced exactly; INFERRED internals, MEASURED values). Model: with the
forwarding selects independent of the consumer's `rs1`/`rs2`, each ALU operand is the *previous instruction's result*.

| program | instr | model | S / committed (debug read) |
|---|---|---|---|
| straight | `ADDI x1,x0,5` | 0+5 = 5 | x1 = 5 (RTL 5) |
| straight | `ADDI x2,x0,7` | prev(5)+7 = **12** | x2 = `0x0c` (RTL 7) |
| straight | `ADD x3,x1,x2` | 12+12 = **24** | x3 = `0x18` (RTL 12) |
| straight | `ADD x4,x3,x0` | 24+24 = **48** | x4 = `0x30` (RTL 12) |
| branch | `ADDI x2,x0,9` | prev(5)+9 = **14** | x2 = `0x0e` (RTL 9) |
| branch | `ADDI x3,x0,9` | 14+9 = **23** | x3 = `0x17` (RTL 9) |
| branch | `ADD x4,x1,x2` | 23+23 = **46** | x4 = `0x2e` (RTL 14) |

The BEQ then compares stored x2 = 14 with stored x3 = 23 and is not taken: the ma7 "corruption reaches the execute
datapath" observation is real, but it is wrong *data produced by forwarding*, not a bad regfile read (INFERRED that the BEQ
reads those stored values).

Causal isolation (MEASURED): arm W differs from arm S in exactly the two hazard-unit port-connection lines
(`rv32i_core.sv:436-437`), same Synlig frontend, same flow, same config; W is IDENTICAL to RTL and S is not. Arm V (a
different frontend, which elaborates those lines correctly: no `5'x`) is also identical. Synthesis evidence (PD agent,
MEASURED): Synlig logs `Range select [639:608] / [799:768] out of bounds on signal \if_id_reg ... undef`, the raw RTLIL has
`connect \if_id_rs1_addr 5'x`, the S/committed netlists have 4863 flops and no `fwd_b_*` bank while W/V have 4868.

Not done: direct observation of the forwarding-select flops. In the ASAP7 netlists the flops are anonymous (the hierarchy
and `fwd_*`/`id_ex_reg`/regfile storage names are lost in ABC/DFFHQN mapping), so the Sky130-style probes of the
select flops and regfile storage are not available. The mechanism rests on the arithmetic reproduction above and the W/S
isolation, not on a waveform of the select flops.

## Consequences

* The ASAP7 CPU macro views (`pnr/asap7/soc/macro/rv32i_cpu_top.*`) are functionally wrong for the reason Sky130's are (MEASURED
  on the netlist; the LEF/Liberty views are derived from the same netlist). The config switch to `USE_SYNLIG:false` (sv2v)
  from `ma7` fixes it, as does an RTL change that routes the two part-selects through a full-width wire (arm W).
* **Option for the blocked `lxv`/`ma7` sv2v re-harden (not a decision):** if the RTL fix (PR #259) is merged, a Synlig
  build is a second route to a correct ASAP7 CPU macro (arm W is the evidence, at synthesis level; place-and-route of a
  W-style netlist was not run). The Synlig route would also avoid the sv2v-specific routing regression recorded in `lxv`
  only if that regression is frontend-dependent, which this test does not show (`e69`'s 2,045 violations came from the Synlig-era
  macro; the 108,716 from sv2v builds).
* The same `struct.member[a:b]` in a port connection pattern may exist elsewhere (the GPU's `warp_scheduler.sv:152` was
  flagged in `ma7`); only the `rv32i_core` cone was checked for the Synlig `out of bounds` warning (PD agent), the GPU was not
  simulated.
* No step gates on Synlig's `Range select ... undef` warning (see `docs/SKY130_CPU_SYNLIG_DUD4.md`).

## Not done

Formal equivalence of S/W/V vs RTL; waveform-level view of the forwarding-select flops (anonymous after mapping); a
fault injected into the regfile read mux itself; P&R of an arm-W netlist; the GPU macro; programs beyond the 6 (no
loads, no CSR, no interrupts, no cache-miss-heavy streams beyond what the sweeps do); yosys `sim` runs of the sweeps (the
sweeps ran in Verilator only).

## Reproduce

Scratch: `/nobackup/claude_sim_build/dud4/asap7_sim/`. `asap7/gen_cell_lib.sh <out.v>` (cell models),
`asap7/strip_physical.sh` (committed netlist), `asap7/build_arm.sh rtl|gate` (Verilator; `RTL_ROOT=` selects the RTL tree,
`CELLLIB=` the cell models), `sky130/gen_all_progs.sh`, `sky130/run_arm.sh`, `sky130/compare_arms.py diff`,
`sky130/port_matrix.py`, `asap7/run_yosys_gate.sh`, `asap7/first_divergence.py`, `asap7/inject_stuck.py`.
Netlists are not committed.
