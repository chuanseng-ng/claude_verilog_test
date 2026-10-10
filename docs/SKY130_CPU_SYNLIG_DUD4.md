# Sky130 CPU macro netlist vs RTL differential (bead `dud4`)

Date 2026-10-10. Question: is the Sky130 `rv32i_cpu_top` hard macro netlist (built with
`USE_SYNLIG: true`) functionally corrupt, the way `u99`/`ma7` showed for ASAP7? Test only: no PD run,
no config change, no re-harden. Statements are tagged MEASURED, INFERRED or HYPOTHESIS.

## Verdict

**CORRUPT, and the cause is localised to the Synlig frontend.** The committed Sky130 CPU macro netlist
computes wrong results. Synlig elaborates two port connections of the hazard unit as undefined; a
synthesis of the same pinned RTL through sv2v is functionally identical to RTL on every program tried, and a
Synlig synthesis of the same RTL reproduces the committed netlist's failure signature. The mechanism is
**hazard/forwarding compare against undefined `rs1`/`rs2`**, not the regfile read mux that `ma7`/`u99` blame.

## Root cause (MEASURED unless marked)

`rv32i_core.sv` connects the hazard unit as
`.if_id_rs1_addr(if_id_reg.instruction[19:15])`, `.if_id_rs2_addr(if_id_reg.instruction[24:20])`
(lines 432/433 at `5c49ddf`; 436/437 on main). Synlig/Surelog logs during `Yosys.Synthesis` and JsonHeader:

```
rv32i_core.sv:432: Warning: Range select [639:608] out of bounds on signal `\if_id_reg': Setting all 32 result bits to undef.
rv32i_core.sv:433: Warning: Range select [799:768] out of bounds on signal `\if_id_reg': Setting all 32 result bits to undef.
```

The raw RTLIL straight from Synlig has `connect \if_id_rs1_addr 5'x` and `connect \if_id_rs2_addr 5'x`
(`localise/raw_synlig.il`, lines 22700-22701). A part-select of a packed-struct field inside a port
connection is what triggers it. sv2v elaborates the same lines correctly. With the compare address undefined,
every `rd_addr == if_id_rs?_addr` in `rv32i_hazard_unit` (pre-decoded forwarding selects, load-use detect) is a
don't-care, so Yosys merges the B-side registered selects into the A-side ones.

Flop census (post-synthesis, pinned RTL `5c49ddf`): Synlig 4,829 `dfxtp` with **0** `fwd_b_*` flops; sv2v 4,834
with 5 (`fwd_b_sel_r` x3, `fwd_b_ex1c_r`, `fwd_b_ex1b2_r`). The committed post-PnR netlist has **4,829** `dfxtp`
and no `fwd_b_*` nets, i.e. exactly the Synlig count. `Removed N multiplexer ports` counts are identical in both
arms (`OPT_MUXTREE` is not the difference). Source of these numbers: `/nobackup/claude_sim_build/dud4/synth/NOTES.md`
(PD-agent synthesis-only experiment; commands, hashes and tool versions there: LibreLane 2.4.13, Yosys 0.46,
Surelog 1.82, sv2v 0.0.13.1).

## Simulation result: three netlists, same testbench, same programs (MEASURED)

RTL arm: RTL at `5c49ddf` (+`SRAM_SKY130`). Gate arms: synthesis-only netlists (`Yosys.Synthesis` output, same PDK,
config, library, strategy per pair; single variable = frontend), PDK functional cell models, project SRAM model.
Programs: `trivial`, `ma7_straight` (u99), `ma7_branch`, `sweepA/B/C` (31-register sweeps). Comparison:
commit stream, AXI writes, 32 debug GPR reads and a per-cycle trace of every output port.

| gate netlist (pinned RTL `5c49ddf`) | result vs RTL |
|---|---|
| committed post-PnR netlist (`995c487`) | x4 = `0x30`, BEQ x2,x3 not taken, sweeps trap at the first MMIO store (earlier section of this PR) |
| `pinned/synlig` synth netlist | **5 of 6 programs diverge** with the same signature: `ma7_straight` x4 = `0x30` (RTL `0x0c`); `ma7_branch` first commit divergence #5 (pc 0x14 instead of 0x20, BEQ not taken); sweeps A/B/C diverge at commit #69 (first MMIO store, pc 0x114 -> restart at pc 0). `trivial` identical. Port matrix: 96 of 124 exercised cells FAIL |
| `pinned/sv2v` synth netlist | **IDENTICAL to RTL on all 6 programs**, cycle-exact on every output port, all 32 debug reads. Port matrix: **124 of 124 cells PASS** (x1..x31 x {rs1, rs2, both, debug}) |
| `wa/synlig` (main RTL + scratch workaround: the two selects routed through a full-width wire) | see "Main-RTL pair" below |

So: the fault exists at synthesis output (P&R, CTS, resizer and ECO are exonerated for this signature), the fault
comes from the frontend, and the sv2v netlist of the same RTL is functionally correct for what was tested.

Ruled out as harness effects (MEASURED): initial state/X (random-reset runs, two seeds, identical to zero-init per
arm); Verilator scheduling (original `ma7` yosys-`sim` harness also gives `0x30` and the not-taken branch on the
committed netlist, and `0xc` on the pinned sv2v synth netlist); SRAM model and latency (same file, both arms); RTL
commit (pinned; the RTL arm matches the by-construction expectation 116/116 stores and final GPRs); cell models
(`trivial` is cycle-exact identical on every netlist).

### Harness problem found and fixed on the way (MEASURED)

On the first attempt the synthesis-output netlists produced no commits at all in Verilator, for **both** frontends.
Cause: the PDK `sky130_fd_sc_hd__conb_1` model uses `pullup`/`pulldown` primitives; where the Yosys netlist drives
output ports/nets straight from tie cells, Verilator resolves them as pulled tri-states, warns `Circular
combinational logic ... __out__strong__out` and returns 0 for `HI`, so the CPU never starts. Fix: `CONB_FIX=1` in
`build_arm.sh` swaps the cell type for a plain `HI=1, LO=0` module (`conb_model.v`). The yosys-`sim` Liberty run is
unaffected and independently gave the same answers. The committed post-PnR netlist was not affected (its ties go through
`assign` nets).

## Corrected mechanism

* MEASURED (committed netlist, `ma7_straight` probes): regfile read data into ID/EX equals RTL in every cycle except
  the final `SW x4`; stored values are wrong from `x2` on (`0x0c` instead of `0x07` at cycle 26); the registered
  forwarding-select flops assert in a rolling pattern (cycles 25-31) where RTL asserts once.
* INFERRED from the arithmetic and the root cause: with `if_id_rs1/rs2` undefined the forwarding selects depend on
  the producer alone, so each ALU operand is the previous instruction's result (`7+5`, `12+12`, `24+24`), including
  for `x0`. That also explains why the sweeps trap at the first store: the address operand is forwarded garbage.
* The debug read mux is faithful (storage == debug read for all 32 registers). The regfile read mux is **not** the
  fault; it passes the full 31-register x port matrix on the sv2v netlist, and the Synlig netlist's regfile read
  results are not what fails.

## Why nothing caught it

* Port-connection fault *between* modules: per-module Synlig-vs-sv2v SAT equivalence (hazard, forwarding, ALU, branch
  comparator, decode, immediate generator: all equivalent in isolation; `equiv_all_comb.sh`) cannot see it because the
  broken wires are the instance's port connection inside `rv32i_core`, outside every isolated module.
* It is a logged **Warning** that no step gates on. `Checker.YosysSynthChecks`, lint (Verilator on the sources),
  unmapped-cell, NetlistAssign and inferred-latch checks all pass (`synthesis__check_error__count` 0 in every arm).
* Netgen LVS compares layout to the same wrong netlist; STA and P&R are happy with a smaller, wrong design (Synlig
  netlist is 333-957 cells smaller).
* The earlier `OPT_MUXTREE` hypothesis fits the symptom only by coincidence (identical removal counts in both arms).

## Consequences

* The Sky130 SoC consumes the wrong CPU macro (`pnr/sky130/soc/config.json` MACROS). Every Sky130 SoC result that depends
  on CPU behaviour at gate level rests on it; RTL-level cocotb results are unaffected.
* ASAP7 (INFERRED, untested): the ASAP7 CPU config is also `USE_SYNLIG:true` on RTL with the same two lines, and
  its `u99`/`ma7` signature (x4 = `0x30`, BEQ not taken) is identical to the one reproduced here by the Synlig netlist.
  So the ASAP7 failure is very likely this defect, and the `u99`/`ma7` "regfile read-mux OPT_MUXTREE" diagnosis is
  in doubt. Not verified by building or simulating any ASAP7 netlist here.
* Remedies (owner's decision, both need a re-harden): switch the Sky130 CPU config to sv2v (as the SoC and, since `ma7`,
  ASAP7 already are) and/or rewrite the two part-selects through a full-width wire; gate on the Synlig `Range select ...
  out of bounds` / `undef` warning.
* Surelog shared-cache caveat (MEASURED, from the synthesis run): the Makefile runs LibreLane with cwd = the librelane
  checkout, so Surelog's `slpp_all` cache is shared across every project and worktree; one run logged source paths from
  an older worktree whose `rv32i_core.sv`, `rv32i_hazard_unit.sv` and `rv32i_forwarding_unit.sv` differ. The resulting
  netlist was byte-identical to the clean-cwd run, so no stale content leaked in that instance, but it is a latent hazard
  and cannot be excluded for the committed netlist (its run directory is gone).

## Negative control, on a clean baseline (MEASURED)

Baseline = `pinned/sv2v` netlist (IDENTICAL to RTL on all 6 programs). Fault (scratch copy, `inject_fault.py tie1`):
data input A1 tied to 0 on the 63 first-level read-mux cells that select x1 among x0..x3 in every read tree
(`find_x1_read_cells.py`). Detected in **4 of 6 programs** (`ma7_branch`, `sweepA`, `sweepB`, `sweepC`; first AXI write
divergence: expected `0x91b7584a`, got `0x00001000`). Not detected in `trivial` and `ma7_straight` (neither reads x1
through a settled read-mux path that matters there: `x1` is consumed via forwarding or only through the debug path).
So the differential detects a regfile read-path fault when the program reads settled registers, which the sweeps do.
Earlier controls against the faulty committed netlist were weak (an S0/S1 swap was invisible because x1 and x2 share
bit 0).

MAIN_PAIR_PLACEHOLDER

## Not done / limits

* Whole-CPU formal equivalence between netlists and RTL; ASAP7 netlist simulation; the sv2v netlist was shown
  correct only for the programs above (all 31 registers on both ID ports, plus both ma7 programs), not exhaustively.
* The committed netlist's own run log is gone, so "built by Synlig" for that exact file is inferred from its
  signature (4,829 flops, no `fwd_b_*`) plus the config, not read from a log.
* `rv32i_core.sv` line-number mapping is per RTL version (432/433 pinned, 436/437 main).

## Reproduce

`gen_all_progs.sh`, `build_arm.sh rtl|gate` (`CONB_FIX=1` for Yosys synthesis-output netlists; `RTL_ROOT=` selects
the RTL tree), `run_arm.sh`, `compare_arms.py diff`, `port_matrix.py`, `run_and_compare.sh`, `run_yosys_gate_check.sh`,
`inject_fault.py`, `find_x1_read_cells.py`, `equiv_all_comb.sh`; probes `build_probe_arms.sh`, `run_probe.sh`,
`decode_trace.py`. Scratch under `/nobackup/claude_sim_build/dud4`. Netlists are not committed.
