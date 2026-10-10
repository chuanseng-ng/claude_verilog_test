# Sky130 CPU macro netlist vs RTL differential (bead `dud4`)

Date 2026-10-10. Question: is the Sky130 `rv32i_cpu_top` hard macro netlist (built with
`USE_SYNLIG: true`) functionally corrupt, the way `u99`/`ma7` showed for ASAP7?
Scope: test only. No PD run, no config change, no re-harden.

## Verdict

**CORRUPT (netlist != RTL), high confidence. Attribution to the Synlig frontend specifically: NOT established.**

The committed Sky130 CPU macro netlist computes wrong architectural results. On the exact
`u99` program it leaves `x4 = 0x30` where RTL gives `0x0c` (the same value `u99` saw on ASAP7),
and on the exact `ma7` branch program it evaluates `BEQ x2,x3` (9==9) as NOT TAKEN (same as
ASAP7). Three independent confirmations: Verilator + PDK functional cell models, yosys `sim` +
Liberty cell models (a second, race-free simulator), and (for the RTL side) agreement with the
Python reference model. The mechanism is **not** the regfile read mux that `ma7` blames; see
"Mechanism". That also puts the `ma7`/`u99` diagnosis in question.

## Netlist provenance (MEASURED)

* `pnr/sky130/cpu/macro/rv32i_cpu_top.nl.v.gz`, sha256
  `d905d526e8b8093e556f77571c6ec259a2603341b23b15ebd89915ba2c5cea49`, 669,682 lines (gunzipped).
  This is the file the Sky130 SoC consumes (`pnr/sky130/soc/config.json` MACROS entry
  `../cpu/macro/...`); there is no other CPU netlist on disk.
* Committed in `995c487` (2026-07-27): "Adopt RUN_2026-07-27_05-52-19 ... Netlist taken from the final
  (post-fill-insertion) step". Parent chain: `74d3064`, `5c49ddf`.
* Source RTL: `rtl/cpu`, `rtl/mem`, `rtl/soc` last changed in `9f15ebe` (2026-07-25), before the run
  started. The RTL arm uses the tree at `5c49ddf` (`git archive`). `rv32i_regfile.sv` is unchanged
  between `5c49ddf` and HEAD; HEAD differs in 15 other `rtl/cpu|mem` files (e.g. `999e44a` registered APB
  outputs), which is why the pinned tree was used.
* **Synlig as the frontend is NOT proven from a log.** The run directory is gone
  (`/nobackup/sky130_cpu_runs` is empty), so no resolved config or synthesis log exists. The only
  evidence is `pnr/sky130/cpu/config.json` at `5c49ddf`/`995c487`: `USE_SYNLIG: true`,
  `SYNLIG_DEFER: false` (identical at HEAD). Treat "built by Synlig" as configuration evidence only.
* Cells: 4,829 `dfxtp` flops, 10 `sky130_sram_1kbyte_1rw1r_32x256_8` macros (I$/D$ tag+data), no
  latches, no clock gates.

## Method (MEASURED)

`tools/verif/gls/sky130/` (reproduce with `gen_all_progs.sh`, `build_arm.sh rtl|gate`, `run_arm.sh`,
`compare_arms.py diff`). One testbench (`tb_sky130_cpu_check.sv`), unmodified, drives both arms;
only the sources differ.

* Gate arm: netlist + `sky130_fd_sc_hd` PDK functional Verilog models (`-DFUNCTIONAL`, UDP-based,
  `UNIT_DELAY` empty) + `sim/sky130_sram_1kbyte_1rw1r_32x256_8.sv`. Verilator 5.048 handled the PDK
  UDP models directly; nothing else was substituted.
* RTL arm: pinned RTL, `+define+SRAM_SKY130`, same SRAM model, Verilator.
* Bench: ROM + burst AXI read BFM, AXI write slave (MMIO stores bypass the D$ and show at the
  boundary), APB master that halts the core and reads GPR x0..x31 through the debug port. Race
  discipline: outputs snapshotted 1 ns before each posedge, bench state advances by NBA.
* Comparison: commit stream, AXI writes, 32 debug GPR reads, and a per-cycle trace of every macro output
  port (cycle-exact).
* Programs: `ma7_straight` (u99), `ma7_branch` (ma7 step 1), `trivial` (ADDI x1,5 ; park),
  `sweepA/B/C` (31-register sweep, three base/dest choices; expected stores computed by construction).

## Results (MEASURED)

| program | RTL arm | gate vs RTL |
|---|---|---|
| trivial | matches model | **IDENTICAL**, all 74 commits, every cycle of the boundary trace, all 32 GPR reads |
| ma7_straight | x4 = 0x0c | commit stream and AXI identical; **x2/x3/x4 = 0x0c/0x18/0x30** (RTL 0x07/0x0c/0x0c) |
| ma7_branch | BEQ taken, parks 0x28 | **BEQ NOT taken**, retires 0x14, 0x18 (WRONG path) |
| sweepA/B/C | 116/116 stores and final GPRs match expectation | **diverge at the first MMIO store** (cycle 348): gate raises `trap_taken` cause 6 (store address misaligned), `awaddr`=0 instead of `0x20000110`, restarts at pc 0 |

Ruled out as harness causes (MEASURED):

* Initialisation/X: both arms re-run with `+verilator+rand+reset+2`, seeds 11 and 22: each arm identical to its
  own zero-init run on all 6 programs; gate-vs-RTL divergence unchanged. (The regfile is synchronously
  reset in RTL and the netlist has no un-reset state that the programs read.)
* Simulator race / UDP scheduling: the original `ma7` yosys-`sim` harness, unmodified, on the same netlist
  with Liberty cell models gives `apb_prdata_captured = 0x30` for the u99 program and the same
  NOT-TAKEN `BEQ` trace (`run_yosys_gate_check.sh`).
* SRAM model: same file, same read latency, both arms; `trivial` (which exercises I$ refill and the APB
  path) is cycle-exact identical.
* RTL commit mismatch: RTL pinned to the source commit; RTL arm independently matches the by-construction
  expectation for all three sweeps and the published ma7 RTL results.
* Cell models / power pins: functional models without power pins; `trivial` identical end to end.

First diverging observation, `ma7_straight` (MEASURED, probe build): regfile storage `x2` is written
`0x0c` at cycle 26 (RTL `0x07`); `x3` `0x18` at 29 (RTL `0x0c`); `x4` `0x30` at 32 (RTL `0x0c`). The
debug-port read returned exactly the storage contents for all 32 registers (storage == debug read), so the
debug read mux is faithful here; the **stored values are wrong**.

## Mechanism (partly MEASURED, partly INFERRED)

* MEASURED: ID/EX `rs1_data`/`rs2_data` (the regfile read results registered into ID/EX) are identical to RTL in
  every cycle of `ma7_straight` except the final `SW x4`, where the gate's read returns its (already wrong)
  storage `0x30`. Reads of recently written registers are stale in both arms and corrected by forwarding.
* MEASURED: the registered forwarding-select flops (`fwd_a_ex1c_r`, `fwd_a_ex1b2_r`, `fwd_a_sel_r`) assert in
  a rolling pattern over cycles 25..31 in the gate, whereas RTL asserts a single forward (cycle 26).
* INFERRED from the arithmetic: `0x0c = 7+5`, `0x18 = 12+12`, `0x30 = 24+24` i.e. each ALU operand is the
  previous instruction's result instead of the architected operand, including for `rs=x0`. That is a
  forwarding-select (hazard-unit pre-decode) fault, **not** a regfile read-mux fault.
* This contradicts the `ma7` mechanism for Sky130. The ASAP7 results (same `0x30`, same wrong branch)
  are consistent with the same forwarding fault and `u99`'s "debug read mux" attribution may have mistaken
  wrong STORED values for a wrong read. **HYPOTHESIS for ASAP7, not tested here.**
* MEASURED, negative: Synlig-elaborated + `librelane_opt(nodffe,nosdff)x5` versions of `rv32i_hazard_unit`,
  `rv32i_forwarding_unit`, `rv32i_alu`, `rv32i_branch_comp`, `rv32i_decode`, `rv32i_imm_gen` are
  **formally equivalent** to the sv2v/`read_verilog` versions (`miter` + SAT, `equiv_all_comb.sh`; vacuity
  of the miter not separately checked). `rv32i_regfile` alone: identical coarse-cell census and identical
  `OPT_MUXTREE` removals (14 ports) under Synlig and sv2v. So the fault is NOT visible when these modules are
  elaborated in isolation.
* MEASURED, unexplained: Synlig-elaborated whole CPU after proc/flatten/opt (stop before techmap/abc), simulated
  with the ma7 harness in yosys, returns `apb_prdata_captured = xxxxxxxx` (X) for the u99 program, while the
  sv2v-elaborated equivalent returns the correct `0x0c` (`frontend_sim_check.sh`). Not root-caused (could be
  an X-propagation artefact of the Synlig RTLIL); it is a Synlig-vs-sv2v difference at the pre-techmap stage,
  but not the same symptom as the netlist.

## Negative control

MEASURED, weak. Two attempts, both on a scratch copy (`inject_fault.py`; original untouched), compared
gate-with-fault against the unfaulted gate arm:

1. Swap S0/S1 on the two bit-0 first-level read `mux4` cells for x0..x3 (`_35893_`, `_36552_`):
   **not detected** in any program. Cause: the swap exchanges index 1 and 2, and x1=5, x2=7 share bit 0, so
   it was invisible by construction. Recorded as an uninformative control, not as evidence.
2. Tie input A1 (index-1 data) of the same two cells to 0: **detected in 1 of 6 programs** (`sweepC`): first
   trace divergence at cycle 348, the same store the unfaulted gate traps on; with the fault the gate arm
   executes `SW` at pc 0x114 (RTL-like) instead of trapping. The other five programs were unaffected
   (`trivial`, `ma7_*`, `sweepA/B`: IDENTICAL to the unfaulted gate), so those cells are not on those
   programs' observed paths.

So the harness does detect a netlist change, but the control is low-sensitivity and was not run on a clean
baseline (none exists). An unexpected side observation, **uninterpreted**: perturbing a regfile read-tree
cell changed the failure of `sweepC` at the very cycle where it first diverges. That means the `sweep` failure
(store-address path via ID read of the base register) may involve the regfile read path after all, unlike
`ma7_straight`. Not resolved here.

## What was NOT done

* No sv2v-built (or otherwise non-Synlig) CPU netlist through the same flow was produced or simulated, so
  **the fault is not attributed to Synlig**. The failure could equally come from a later flow step (ABC with
  `DELAY 3`, resizer/repair, ECO). This is the single experiment that settles attribution (below).
* The 31-register x port matrix was not obtained: all three sweeps trap at their first MMIO store, so no
  per-register read-port verdict exists. The regfile read mux is NOT shown clean or corrupt in general; the
  evidence is limited to `x4` on the rs2 port and debug-port reads of all 32 registers in `ma7_straight`.
* Forwarding-select internals were probed only for the A side and only on `ma7_straight`.
* Whole-CPU formal equivalence (gate netlist vs RTL) not attempted. Run dir / synthesis log for provenance
  unavailable. ASAP7 not re-examined.

## Next experiment (one)

Synthesise `rv32i_cpu_top` with the committed Sky130 config but `USE_SYNLIG:false` (sv2v frontend), synthesis
step only, and run `tools/verif/gls/sky130/` (`build_arm.sh gate <that netlist>`, `run_arm.sh`,
`compare_arms.py diff`). If it matches RTL, the frontend is the cause; if it diverges identically, the fault is
downstream of the frontend (and `ma7`'s remedy would not fix it). Needs the user's go-ahead (fresh synthesis).

## Reproduce

`gen_all_progs.sh <progs>`; `build_arm.sh rtl <dir>`; `build_arm.sh gate <dir> [netlist]`;
`run_arm.sh <armdir> <progs>`; `compare_arms.py diff <rtl_run> <gate_run>`; `rand_init_check.sh`;
`run_yosys_gate_check.sh`; probes: `build_probe_arms.sh`, `run_probe.sh`, `decode_trace.py`;
`equiv_all_comb.sh`; `frontend_sim_check.sh`; `inject_fault.py`. Scratch under
`/nobackup/claude_sim_build/dud4`. Netlists are not committed.
