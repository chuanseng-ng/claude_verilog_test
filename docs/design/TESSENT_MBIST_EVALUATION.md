# Siemens Tessent MemoryBIST vs the in-house MBIST (parallel evaluation)

Branch `feat/tessent-mbist`, flow in `dft/tessent/mbist/`. Epic `j41m` (DFT), follows `docs/design/DFT_ARCHITECTURE.md`
section 16 (the in-house MBIST). **Nothing under `rtl/`, `pnr/` or `tb/` was changed and the in-house MBIST is
untouched**: the Tessent hardware is generated into a separate netlist (`dft/tessent/mbist/build/`, gitignored).
The decision between the two is the user's; section 9 is a recommendation only.

Labels as in the architecture document: **[M]** measured (command or file named), **[R]** read from a source file,
**[A]** assumed or inferred (reasoning given).

Tools: Tessent Shell 2025.4 (licence checkout verified with a smoke run), VCS Y-2026.03, yosys 0.64+345 (the repo pins
0.62; see 6.4), sv2v 0.0.13.1 behind the RHEL8 glibc wrapper.

## 1. What was built

| Item | File |
|---|---|
| Memory description (TCD) for `sky130_sram_4kbyte_1rw1r_32x1024_8` | `dft/tessent/mbist/lib/sky130_sram_4kbyte_1rw1r_32x1024_8.tcd_memory` (+ `.v_interface`, the interface-only Verilog view) |
| Evaluation top: the unmodified `sram_controller` and `npu_weight_mem`, one clock, in-house `mb_*` inputs tied inactive | `dft/tessent/mbist/rtl/mbist_eval_top.sv` |
| Dofiles: generate (DRC + DftSpecification), insert (hardware, ICL, patterns), sim (VCS) | `dft/tessent/mbist/dofiles/` |
| Makefile: `mbist-generate`, `mbist-insert`, `mbist-sim`, `mbist-area`, `mbist-evidence`, `all`, `clean` | `dft/tessent/mbist/Makefile` |
| Fault-injecting memory wrapper (reuses `tb/cocotb/soc/sram_fi_core.sv`, plusargs set the fault) | `dft/tessent/mbist/tb/sky130_sram_fi_tess.sv` |
| Fault campaign (same fault universe as the in-house golden model) and area scripts | `scripts/fi_campaign.py`, `scripts/area.sh`, `scripts/area_breakdown.py` |
| Small committed results | `dft/tessent/mbist/evidence/` |

Flow, as run [M] (`make clean && make mbist-generate mbist-insert mbist-sim` from scratch reproduced the numbers below):

1. `sv2v` of the same SoC sources the Sky130 flow uses, with `--define=SRAM_SKY130 --define=__pnr__` (and **not**
   `USE_SKY130_CLKCELLS`: those hand-instantiated clock cells are a black box to Tessent; see 7).
2. Tessent `set_context dft -rtl`, `tcd_memory` library, `read_verilog`, `add_clocks clk -period 25ns`,
   `check_design_rules` (clean), `create_dft_specification`, `process_dft_specification`, `extract_icl`,
   `create_patterns_specification`.
3. `run_testbench_simulations -simulator vcs` on Tessent's own generated testbenches, against the project's behavioural
   model `sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv`, then against the fault-injecting model.
4. yosys `synth; dfflibmap; abc -liberty sky130_fd_sc_hd__tt_025C_1v80` on the Tessent-inserted design and on the
   in-house blocks, the method of section 16.9 of the architecture document.

## 2. Memory library: what is in the TCD and what was assumed

Authored from the macro's Liberty (`pnr/sky130/soc/macro/*_TT_1p8V_25C.lib`), the OpenRAM model beside it, and the
project's simulation model. **Assumptions** (also in the file header):

| # | Assumption | Basis | Risk |
|---|---|---|---|
| A1 | Both ports are synchronous, read latency one clock, no output register (`DataOutStage None`, `OperationSet sync`). The macro captures inputs at the rising edge and reads at the following falling edge, so data is valid half a clock later and sampled at the next rising edge. | [R] `sim/sky130_sram_4kbyte_1rw1r_32x1024_8.sv` header; Liberty `timing_type : falling_edge` on `dout0/dout1` | The half-cycle internal timing is invisible at the pins in RTL simulation. Tessent's at-speed timing assumptions for the real macro (SDC/MinHold) are **not validated**. |
| A2 | `csb0/csb1/web0` active low, `wmask0` active high, one bit per 8-bit lane (`GroupWriteEnable`, `BitGrouping 8`) | [R] Liberty, model | none |
| A3 | Port 1 is read only (`LogicalPorts 1R1RW`: **`[nR][nW][nRW]` order**, `1RW 1R` and `1RW1R` are rejected) | [R] Liberty | none |
| A4 | No transparent/bypass mode (`TransparentMode None`); the macro is a black box in scan mode, as in the in-house flow | `DFT_ARCHITECTURE.md` 6.3 | A Tessent ATPG flow around the macro would want a bypass; not evaluated. |
| A5 | The physical row/column map is **not known** (OpenRAM scrambles it; LEF/Liberty do not say). The address map is a logical split `Row[7:0] = Address[9:2]`, `Column[1:0] = Address[1:0]`, chosen because Tessent **silently forces `BitGrouping` to the word size (32)** on a memory with no column address bits, which would drop the byte-lane write-mask test. | Tessent note at TCD read | All neighbourhood algorithms (checkerboard, the SMarchCHKB family) work in logical space only, the same limit as the in-house `CKBD` (architecture 16.3). A physical map would need the OpenRAM scrambler documentation. |
| A6 | `MinHold 1`, `MilliWattsPerMegaHertz 0.3` (the latter is only a power-budget input; Tessent reports `power_mw 24.00` for the run) | placeholder | Power number is not measured; do not use it. |

## 3. Comparison, Tessent vs in-house

Both test the two SoC-level 4 KB macros of `soc_top` in parallel from one controller on `core_clk` (25 ns, 40 MHz).

| Aspect | In-house (`mbist_ctrl` + `mem_collar`, TAP opcodes 6/7) | Tessent MemoryBIST 2025.4 (generated) |
|---|---|---|
| Algorithms available in the evaluated build | March C- (`MARCH_CM`), retention (`RETENTION`), both (`MARCH_CM_RET`), checkerboard + March C- (`CKBD`), byte-lane (`LANE`), `FULL`; six data backgrounds, optional sweep; selected at run time through `MBIST_CTRL` [R] | Library of 22 algorithms in the install (`lib/tools/etv/membistipg_algos/*.algo`): LVMarchCMinus, LVMarchX/Y/LA, LVCheckerboard1X1/4X4, LVGal*, LVWalkingPat, LVRowBar/ColumnBar, LVAddress/DataInterconnect, LVBitSurroundDisturb, LVMasest, ReadOnly, SMarch, SMarchCHKB, SMarchCHKBci/cil/vcd. The run evaluated 6 (LVMarchCMinus, SMarch, SMarchCHKB, SMarchCHKBci, SMarchCHKBcil, LVCheckerboard1X1), all selectable at run time (controller type *Programmable*, "HardProgrammable" in the generation log) [M] |
| March C- | yes | yes (`LVMARCHCMINUS`); detection on the 105-fault universe identical to the in-house `MARCH_CM` (97/105 per memory, 5.1) |
| Retention | `RETENTION`/`MARCH_CM_RET`, programmable pause 0 to 4.18 M cycles | **No retention algorithm in the library**; a `ParallelRetentionTest` pattern (`parallel_retention_time`, run mode `hw_default`) pauses between write and read. Detection of a 5000-clock decay with an 8000-clock pause demonstrated (5.3). User-defined retention would be a soft algorithm with the delay counter [A: not built] |
| Checkerboard | logical-space `CKBD` | `LVCHECKERBOARD1X1`; `SMarchCHKB*` family (names match the user's `smarchchkd`) |
| User-defined algorithm | ROM row in `mbist_ctrl` (RTL change) | Soft algorithm instructions (`soft_instruction_count`, `AlgorithmResourceOptions`) or a custom `.algo` file [R, syntax]; **not exercised** |
| Fault classes (measured, 5.2) | SAF, TF, AF (none/alias/multi), CFin/CFid/CFst inter-word, intra-word coupling with `FULL`, write-mask lane (only `LANE`/`FULL`), port-1 stuck, retention | SAF, TF, AF, CFin/CFid/CFst inter-word 100 % with every March-class algorithm, intra-word coupling 75 to 100 % depending on algorithm, port-1 stuck, retention; **write-mask lane stuck-at-1 not detected by any library algorithm** (8/16, 5.2) |
| Test time, March C-, both macros in parallel (cycles, 25 ns) | **10,259** (0.26 ms) | **24,768** (0.62 ms): the controller makes one pass per logical port ("Test Port" table in the generation log: port A, then port B); the 1R port of the NPU weight memory is tied off inside `npu_weight_mem` and the pass is wasted there [M] |
| Test time, other algorithms (cycles) | `RETENTION` 4,106 + 2 pauses; `MARCH_CM_RET` 14,364 + 2 pauses; `CKBD` 14,367; `LANE` 17,418; `FULL` 46,147 + 2 pauses; x6 with background sweep [R formula pinned by `test_cycle_counts_pin_the_sequencing`] | SMarchCHKBcil **90,164** (default); SMarchCHKBci about 73.8 k; SMarchCHKB about 57.5 k; SMarch about 45.2 k; LVCheckerboard1X1 about 16.6 k (VCS time minus about 52 us IJTAG setup); retention pattern about 15.8 k + 8 k pause [M, see 5.1] |
| Area, sky130_fd_sc_hd, same flow (um2) | **29,733** landed (controller 13,061; two collars 1,191; TCK->core crossing 3,761; status return 3,503; TAP delta 8,217) | **25,850** (full, 6 algorithms) / **23,750** (March C- only) / **27,050** (full with the Tessent-inserted TAP); details 6 |
| Access / integration | Custom private TAP opcodes 6/7 (`MBIST_CTRL` 29 b, `MBIST_STATUS` 140 b), control word crosses TCK to `core_clk` through a depth-2 `cdc_gray_fifo`; tester software is plain register writes and polling | IJTAG (IEEE 1687): eight raw ports `ijtag_{tck,reset,ce,se,ue,sel,si,so}` on a SIB network, or a Tessent-inserted 1149.1 TAP (`-host_scan_interface_type tap`: `tck tms tdi tdo trst tdo_en`, +1.2 k um2). Patterns, ICL and PDL come out of the tool. Not connectable to the existing `jtag_tap` without a new IR opcode and an ICL for it (7.2) |
| Repair / BIRA | none (pass/fail record), by design: the OpenRAM macros have no spare rows or columns | MemoryBisr, BIRA and fuse-map options exist (`RepairOptions`, `MemoryBisr`), **not applicable to these macros** (no redundancy) and not exercised |
| Diagnosis | one first-failure record per run: address, element, slot, background, port, 32-bit XOR mask; per-memory sticky go/no-go | per-memory go (`compare_memory_go`) and per-comparator go-id, stop-on-error with 12-bit counter, failure-count limit, bitmap/ATE diagnosis flows (`CharacterizationDebugOptions`); the bitmap tooling was **not run** |
| Effort and maintenance | RTL (`mbist_ctrl` 598 lines, collar, crossing, status, TAP changes), golden model and fault suites already written and running in CI; open source toolchain only; CPU-macro cache collars still to do (16.7) | TCD about 100 lines + three dofiles; the 11.5 k-line controller is regenerated, not maintained; **needs a Tessent MemoryBIST licence** (features `mtmemorybist_c` etc. present on this host, absent in CI); one TCD per macro (the 1 KB cache macro would need another); algorithm library maintained by the vendor |

## 4. Rules, violations and warnings triaged

| # | Tool message | Cause | Resolution |
|---|---|---|---|
| 1 | `Unrecognized syntax ('1RW1R'). Correct syntax: [<int>R][<int>W][<int>RW]` | Port-type order in `LogicalPorts` | `LogicalPorts : 1R1RW;` |
| 2 | Note: "memory has no column address bits ... BitGrouping changed to 32" | TCD declared all address bits as row bits | Logical split `Row[7:0]/Column[1:0]` (assumption A5) so `BitGrouping 8` is kept |
| 3 | `DFT_C1-1` memory clock not properly sourced, tracing stops at `u_pll_sub/u_stub/out_clk_o` (then at `u_pll_sub/u_ref_cm/.../muxinst/Z`) on `soc_top` | See section 7. First the clock path contains the black-box `sky130_fd_sc_hd__mux2_4` (`USE_SKY130_CLKCELLS`); with that define removed it stops at the behavioural `dft_clk_mux` | Evaluation top `mbist_eval_top` with one `clk` port |
| 4 | Duplicate `sky130_sram_4kbyte_1rw1r_32x1024_8` in simulation (sv2v carries the blackbox stub into the design file) | Stub module and simulation model have the same name | Stub removed from the sv2v input list; Tessent reads `lib/*.v_interface` with `-interface_only -exclude_from_file_dictionary` |
| 5 | `Warning [PPHW01]` x5 in the controller generation log: `NumberOfDataRegisterBits` not specified (32 bits assumed); `DataPolarityEnable:ON is ignored since the physical data map does not exist` for LVMARCHCMINUS and LVCHECKERBOARD1X1 (x2); group write enable port "will be enabled" by operation set SYNC (x2, one per memory) | Consequence of A5 (no physical map) and of the 1RW+1R TCD | Accepted. The data-polarity warning means the two LV algorithms run without the physical-neighbour data inversion: logical-space only |
| 6 | `Warning: Rule FN1 violation occurs 3770 times`, `Rule FP13 ... 71 times` at `extract_icl` after insertion | Netlist-sanity rules re-evaluated on the generated RTL; `check_design_rules` on the input design reports none | **Not triaged to root cause**; non-blocking (ICL extraction, patterns and VCS simulation all pass). Needs a look at the rule text before any production use |
| 7 | Default patterns use `reduced_address_count : on` (simulated in 65 us) | Tessent's generated simulation patterns shorten the address range | Own patterns specification with the option off for every algorithm (`dofiles/mbist_sim.do`) so the fault campaign runs the full 1024 addresses |
| 8 | `Error: Unrecognized argument '-pattern_id'` for `process_patterns_specification` | Argument exists only on `run_testbench_simulations` | Fixed in `dofiles/mbist_sim.do` |
| 9 | yosys: `$finish executed` while reading the sv2v output | `$fatal` elaboration checks of `sram_controller` at its default `MEM_WORDS=4096` | `read_verilog -defer` (as the repo's synthesis gate does) |

## 5. Simulation and fault-injection results [M]

### 5.1 Fault-free simulation on VCS

Tessent-generated testbenches, the project's behavioural SRAM model, full address count, per-memory go compare:

| Pattern (algorithm) | Result | Simulated time (incl. about 52 us IJTAG setup) |
|---|---|---|
| ICLNetwork (IJTAG network verify) | pass, 0 miscompares | 10 us |
| LVMARCHCMINUS | pass, 0 miscompares | 671.7 us |
| SMARCH | pass | 1182.0 us |
| SMARCHCHKB | pass | 1488.8 us |
| SMARCHCHKBCI | pass | 1897.0 us |
| SMARCHCHKBCIL | pass | 2302.2 us |
| LVCHECKERBOARD1X1 | pass | 467.1 us |
| Retention (200 us pause) | pass | 647.1 us |

`unscheduled 0 queued 0 running 0 pass 8 fail 0`. The same eight patterns also pass against the fault-injecting model
with all faults off (`pass 8 fail 0`); the in-house suite proves that model equal to the real simulation model
(`test_fi_model_equals_real_model`). The default signoff patterns of `make mbist-insert` (reduced address count) also
pass, 3 of 3.

### 5.2 Fault injection

The in-house fault catalogue (`tb/cocotb/soc/mbist_golden.py::catalogue(10)`: 105 faults at AW=10) was injected into
**each** memory (`sr` = `sram_controller` macro, `wm` = NPU weight memory) through the fault-injecting model, plus two
read-port-1 stuck-at faults on `sr` (the weight memory ties port 1 off). 1,272 simulations, all from one compiled
`simv` per pattern; a fault is **detected** if the testbench reports more than zero miscompares (the fault-free run
reports zero, checked first). Counts below are pooled over both memories (212 = 2 x 105 + 2).

| Fault class | LVMARCHCMINUS | SMARCH | SMARCHCHKB | SMARCHCHKBCI | SMARCHCHKBCIL | LVCHECKERBOARD1X1 |
|---|---|---|---|---|---|---|
| AFalias | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 4/6 |
| AFmulti | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 4/6 |
| AFnone | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 | 6/6 |
| CFid | 40/40 | 40/40 | 40/40 | 40/40 | 40/40 | 8/40 |
| CFid (intra-word) | 4/8 | 4/8 | 6/8 | 6/8 | 6/8 | 0/8 |
| CFin | 20/20 | 20/20 | 20/20 | 20/20 | 20/20 | 8/20 |
| CFin (intra-word) | 4/4 | 4/4 | 4/4 | 4/4 | 4/4 | 0/4 |
| CFst | 40/40 | 40/40 | 40/40 | 40/40 | 40/40 | 20/40 |
| CFst (intra-word) | 4/8 | 4/8 | 8/8 | 8/8 | 8/8 | 4/8 |
| P1STUCK | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 | 2/2 |
| SAF | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 |
| TF | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 | 28/28 |
| WMASK | 8/16 | 8/16 | 8/16 | 8/16 | 8/16 | 8/16 |
| **all** | **196/212** | **196/212** | **202/212** | **202/212** | **202/212** | **120/212** |

| Fault class | MARCH_CM | CKBD | LANE | FULL |
|---|---|---|---|---|
| AFalias | 3/3 | 3/3 | 3/3 | 3/3 |
| AFmulti | 3/3 | 3/3 | 3/3 | 3/3 |
| AFnone | 3/3 | 3/3 | 3/3 | 3/3 |
| CFid | 20/20 | 20/20 | 5/20 | 20/20 |
| CFid (intra-word) | 2/4 | 2/4 | 2/4 | 4/4 |
| CFin | 10/10 | 10/10 | 5/10 | 10/10 |
| CFin (intra-word) | 2/2 | 2/2 | 2/2 | 2/2 |
| CFst | 20/20 | 20/20 | 15/20 | 20/20 |
| CFst (intra-word) | 2/4 | 2/4 | 2/4 | 4/4 |
| SAF | 14/14 | 14/14 | 14/14 | 14/14 |
| TF | 14/14 | 14/14 | 14/14 | 14/14 |
| WMASK | 4/8 | 4/8 | 8/8 | 8/8 |
| **all** | **97/105** | **97/105** | **76/105** | **105/105** |

The in-house columns are the **golden-model prediction** for the same faults (the repo's fault-injection suites assert
that the RTL reproduces the golden model exactly, `test_mbist_ctrl.py`), not a new RTL simulation.

Readings:

* Tessent `LVMARCHCMINUS` and the in-house `MARCH_CM` detect the same faults: 97 of 105 per memory. Both miss the same
  classes: half the intra-word coupling cases and the write-mask faults that a full-word March cannot see.
* The SMarchCHKB family adds intra-word coupling (up to 100 of 105 per memory) and `LVCHECKERBOARD1X1` alone is weak
  (120/212), as expected of a checkerboard without a March.
* **Write-mask lane faults:** every Tessent library algorithm leaves the stuck-at-1 mask-lane cases undetected (8/16).
  The in-house `LANE`/`FULL` algorithms detect all 8 per memory. This is the one fault class where the in-house
  algorithm set is stronger, and it is a property of the library algorithms plus the `group_write_enable_control :
  always_on` default [A: a system-controlled mask (`group_write_enable_control : system`) with a soft algorithm might
  close it; not tried].
* In-house `FULL` (all of the above with a background sweep) detects 105/105. No Tessent algorithm run reached 105/105.

### 5.3 Retention

| Case | `RETENTION` pattern (200 us = 8,000-clock pause) | LVMARCHCMINUS (no pause) |
|---|---|---|
| Cell decays after 5,000 clocks (longer than the longest write-to-read gap of a pause-free March, about 2,100 clocks, shorter than the pause) | **detected** on both memories | not detected |
| Cell decays after 200,000 clocks (longer than the pause) | not detected (pause too short, as it must be) | not detected |

So the pause is meaningful in both directions. The in-house test has the same property (its programmable pause is
also pinned by the repo's fault-injection suite).

## 6. Area

### 6.1 Method [M]

`scripts/area.sh`: yosys `synth -top; dfflibmap -liberty L; abc -liberty L; opt_clean -purge; stat -liberty L` with
`L = sky130_fd_sc_hd__tt_025C_1v80.lib`, no timing-driven sizing, hierarchy kept (`read_verilog -defer`). In-house blocks
are synthesised alone with the parameters of `soc_mbist` (`N_MEM=2, AW=10, P1_MASK=2'b01`). The Tessent number is
the **difference** between the whole evaluation top after insertion and before (`mbist_eval_top`, memory macro as
black box), so it includes the memory interfaces, comparators, controller, BAP and SIBs.

### 6.2 Results (um2)

| Block | In-house | Tessent full | Tessent min | Tessent + TAP |
|---|---|---|---|---|
| Baseline (`sram_controller` + `npu_weight_mem` + in-house collars) | 7,073 | 7,073 | 7,073 | 7,073 |
| Same design after insertion | n/a | 32,923 | 30,823 | 34,139 |
| **Inserted MBIST delta** | see below | **25,850** | **23,750** | **27,066** |
| Controller (sequencer, address/data generators, FSM) | `mbist_ctrl` 13,061 (243 flops) | about 14,380 | about 12,260 | about 14,380 |
| Memory interfaces + comparators + status | 2 collars 1,191 (656 + 536) | about 8,090 | about 8,090 | about 8,090 |
| Access (TAP delta / BAP + SIBs / Tessent TAP) | TAP delta 8,217 [recorded, 16.9, not re-measured] | about 2,180 (BAP 1,549 + SIB 628) | about 2,180 | about 3,380 (+1,200 TAP) |
| CDC (TCK to core, status return) | crossing 3,761 + status 3,503 | not separately present [A] | | |
| **Total** | **29,733** | **25,850** | **23,750** | **27,066** |

Notes: (a) the Tessent breakdown is the sum of per-module areas and accounts for about 96 % of the delta, the rest is
not attributed to a module [A: multiply-instantiated small cells]; (b) ten `$_DLATCH_N_` in the Tessent clock-gate
cells are not mapped by this flow (about 150 um2 missing); (c) "min" is `AdvancedOptions/algorithm LVMARCHCMINUS` with
no extra algorithms, the controller is still reported *Programmable* and Tessent still lists a second library algorithm
in its log, so "min" is not a hard-wired single-algorithm controller [M: `evidence/generation/min_c1.generation_log`];
(d) the in-house `mbist_ctrl` re-measured here is 13,061 against 13,314 recorded in 16.9 (yosys 0.64 against 0.62,
`mem_collar` 656/536 against 653/513); (e) all numbers are before the real flow's buffering and upsizing.

The two are comparable in size. Tessent is 13 % smaller than the in-house total with six algorithms selectable and
per-memory go/no-go, 20 % smaller in the March-C- only configuration, and 9 % smaller with its own 1149.1 TAP. The
in-house figure also pays for a TCK-to-core crossing and a 140-bit status mirror that the Tessent IJTAG
interface does not have in this form [A: how Tessent's BAP crosses from `ijtag_tck` to the BIST clock was not studied;
its generated `posedge_synchronizer_reset` cells show it has synchronisers].

## 7. Integration findings

### 7.1 `soc_top` as the Tessent target

Insertion into `soc_top` itself failed at `check_design_rules` with `DFT_C1-1`: the memory clock `core_clk` reaches the
macros through `dft_clk_mux`, whose select is `dft_scan_mode`, an OR of the primary input `scan_mode_i` and TAP
flops of `dft_ctrl`. Tessent can only constrain **primary inputs** (`add_input_constraints` rejects internal nets:
`'dft_scan_mode' is not a primary input`), so it cannot prove the mux transparent. Tried: `add_input_constraints
scan_mode_i -c0`, additionally declaring `scan_clk_i` as a clock, a pseudo primary input at `u_pll_sub/ref_clk_o`:
none removed the error [M, run interactively; logs not kept]. With `USE_SKY130_CLKCELLS` the trace first stops at the
black-box library mux. That the cause is the non-constant select is inferred from the message and the three failed
workarounds [A]. Practical consequence: running Tessent on the full SoC needs either an RTL/constraint change
(a static test-mode input for that mux) or an internal-pin clock declaration, which would move the clock root for
simulation. This evaluation therefore uses `mbist_eval_top`, which holds the two real SRAM users with one clock.

### 7.2 Access to the existing TAP

The in-house `jtag_tap` has no IJTAG instruction. Hosting Tessent's SIB network behind it needs (a) an additional IR
opcode (the existing numbering is frozen by decision Q-OP, so this is additive, not a renumbering) selecting a
1687 host data register, (b) an ICL for `jtag_tap` so Tessent can retarget patterns, and (c) a decision on the second
`dft_ctrl`/TCK clock crossing. None of this was built. The two options evaluated instead: raw IJTAG ports (8 pins, a
sibling of the TAP) and Tessent's own TAP (6 pins, +1.2 k um2), which would duplicate the project's TAP.

## 8. Not done, and limits

* Gate-level simulation, SDC for the generated hardware, timing of the controller and at-speed behaviour of the real macro: not run.
* Tessent on `soc_top`, on the 1 KB CPU-macro cache SRAMs, and combination with the in-house collar left in place: not run.
* The `smarchchkd` request: the library contains `SMarchCHKB`, `SMarchCHKBci`, `SMarchCHKBcil` and `SMarchCHKBvcd`; the
  element sequences are licensed content in the install and are neither copied nor reproduced here. `SMarchCHKBvcd` was not generated.
* Physical row/column mapping unknown (A5), so no claim about physical-neighbour coverage in either flow.
* Fault models are the functional ones of `sram_fi_core.sv`; no analogue/resistive defects.
* Parallel jobs: the fault campaign ran two `simv` processes at a time; Tessent ran with `set_multiprocessing_options -processors 2`.

## 9. Recommendation (the decision is the user's)

1. **Keep the in-house MBIST for the Sky130 SoC.** It already meets the section 16 requirements, is verified by golden
   models and fault suites that run in open-source CI, detects every fault of the shared catalogue (105/105 with `FULL`)
   including write-mask lane faults that no Tessent library algorithm detected, tests both ports in one pass (about 2.4
   times fewer cycles for March C-), and needs no licence.
2. **Do not replace it with Tessent on this evidence.** Tessent's area is only 13 to 20 % lower, it has no retention
   algorithm in the library, its access network does not plug into the existing TAP without RTL changes, and it cannot be
   run on `soc_top` as is (7.1).
3. **Where Tessent would earn its place:** (a) if the project ever moves to a memory with redundancy and needs
   BIRA/BISR, (b) if an ATE flow needs standard ICL/PDL retargeting, STIL/WGL patterns and the bitmap/diagnosis tooling,
   (c) if a vendor-qualified algorithm set (SMarchCHKB family) is a customer requirement. For (c) the cheapest route is
   adding the Tessent flow in `dft/tessent/mbist/` as a **cross-check** in a licensed environment: the fault
   campaign script and the TCD are ready, and it already shows the algorithm sets agree on the common faults.
4. **Cheap follow-ups either way:** try `group_write_enable_control : system` to see whether Tessent can close the
   write-mask gap; build the physical address map if OpenRAM documents the scrambler; and note that a Tessent
   controller needs a per-macro TCD, so the CPU-macro 1 KB cache SRAM (not covered here) would need a second one.

## 10. Reproducing

```
cd dft/tessent/mbist
# host overrides (not committed): host/env.mk  (SV2V := <sv2v wrapper>)   host/env.sh  (YOSYS, SV2V, SKY130_LIB)
source ../../../tools/eda/sim_env.sh            # VCS licence/env
make mbist-generate mbist-insert mbist-sim mbist-area mbist-evidence
```
Licence: `MGLS_LICENSE_FILE=27017@eda.ic`. Runtime on this host: generate + insert about 2 min, simulation about 2 min,
fault campaign about 10 min, area about 3 min.
