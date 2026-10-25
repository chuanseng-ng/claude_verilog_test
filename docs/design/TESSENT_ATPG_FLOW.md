# Tessent scan insertion + ATPG evaluation flow (Sky130 SoC fabric)

DFT Stage 2 evaluation with Siemens Tessent Shell 2025.4 (epic `j41m`; beads `j41m.8` scan insertion and `j41m.5` scan-mode SDC are the real
Stage 2 deliverables, this flow is the evaluation of them). Code: `dft/tessent/atpg/`. **Evaluation only: nothing here is back-annotated into
PD, no RTL is modified, and the architecture decisions of `DFT_ARCHITECTURE.md` (test ports, `scan_mode`/`scan_en`, reset and clock muxes,
`dft_clk_switch`, N4 TAP flops on no chain, CPU macro as a black box, crypto key mask and wipe) are followed, not re-decided.**

Labels: **[M]** measured (file named), **[R]** read from source, **[A]** assumed/inferred.

## 1. How to run

```sh
cd dft/tessent/atpg
make all YOSYS=<yosys> SV2V=<sv2v>        # synth, scan, atpg (stuck-at)
make atpg-trans                            # transition-delay (LOC), 26 min
BUILD=$PWD/build sh scripts/vcs_sim.sh build/patterns/soc_stuck_serial.v $PWD/build/vcs_stuck   # VCS pattern check
make clean
```

Targets: `synth` (sv2v netlist -> sky130_fd_sc_hd gate netlist, yosys), `cells` (Liberty -> Tessent cell library), `scan` (insertion + scan DRC +
DRC triage), `atpg` (stuck-at), `atpg-trans`, `all`, `clean`. Everything is generated into `dft/tessent/atpg/build/` (gitignored);
small summary reports are committed in `dft/tessent/atpg/reports/`.

Host requirements: `tessent` on PATH with `MGLS_LICENSE_FILE`, `yosys` >= 0.62, `sv2v`, VCS for the pattern check. **The Sky130 PDK is not
installed on the evaluation host**, so `scripts/fetch_lib.sh` downloads `sky130_fd_sc_hd__tt_025C_1v80.lib` from the OpenROAD-flow-scripts sky130hd
platform (sha256 pinned in the script). This is the same Liberty the OpenROAD/LibreLane flows read, but it was NOT taken from this repo's PD runs.
Tessent is started with `< /dev/null` and `-replace` (see section 8).

## 2. Flow and decisions

| Step | What | Decision / reason |
|---|---|---|
| sv2v | `make -C pnr sky130-soc-sv2v` regenerated from current `main` (60 files, `__pnr__ SRAM_SKY130 USE_SKY130_CLKCELLS`) | A committed synthesised netlist exists only in untracked PD run directories; none matches current RTL (TAP, MBIST, clock cells are newer). Regenerated, not reused. |
| synth | yosys 0.64, `synth -flatten`, `dfflibmap`/`abc` against the tt Liberty, latch techmap, `hilomap` (`scripts/synth.ys.in`) | CPU macro and the two SRAM macros stay black boxes. **Not the PD netlist**: yosys picks `edfxtp_1` (enable flop) for 10,174 flops where the LibreLane recipe produced `dfxtp` + mux. Area/flop counts therefore differ from the PD runs. 17m44s, 1.1 GB [M `reports/runtime.txt`]. |
| fix-up | `scripts/fixup_gate.py`: delete the six `scan_out_o[5:0]` placeholder ties, rename the `$paramod` CPU macro | 14.4 contract step (a), done on the generated netlist (RTL untouched). |
| cell library | `lib2v.py` (Liberty -> zero-delay Verilog models) -> LibComp -> `.atpglib` -> `write_cell_library` + `read_liberty` -> `.tcelllib` with a curated `dft_cell_selection` | See section 3. |
| scan | `set_context dft -scan -no_rtl`, `add_scan_mode soc_scan -chain_count 6 -single_clock_domain_chains on -lockup_cell_type latch` bound to the existing `scan_in_i[5:0]`/`scan_out_o[5:0]`, `insert_test_logic` | 6 fabric chains per DFT_ARCHITECTURE section 8 (5 `clk_i` + 1 `cpu_clk_i`); chains 6,7 belong to the CPU macro and are not stitched here. In test mode every flop is on `scan_clk_i` (clock muxes), so the tool sees one domain and balances by length, not by domain. |
| constraints | `scan_mode_i`=1; `clk_i cpu_clk_i tck_i tdi_i trst_ni`=0; `tms_i rst_n_i cpu_rst_n_i`=1; clocks `scan_clk_i` (off 0) and `scan_rst_ni` (off 1); scan enable `scan_en_i` | TAP held in reset (`trst_ni`=0) so the pin leg of `dft_ctrl` is the only scan control. **Deviation**: the SE net is the port `scan_en_i`, not the internal `dft_scan_en` (`soc_top.sv:360-382`); they are equal with the TAP idle. TAP-serial scan is therefore not exercised. |
| ATPG | `set_context patterns -scan`, `import_scan_mode`, stuck-at then transition (`set_pattern_type -sequential 2`, LOC) | Single thread (`add_processors -number` not accepted, section 8). |

## 3. Cell library (Liberty import) [M]

`read_liberty` alone does **not** give Tessent a usable library: it only attaches attributes (scan pins, `test_cell`, clock-gating) to models that must
come from `read_verilog` or `read_cell_library`, and `read_cell_library` wants `.atpglib`/`.tcelllib`, not Verilog. Pipeline (`make cells`):

1. `scripts/lib2v.py`: Liberty `function`/`ff`/`latch`/`statetable` -> plain Verilog-2001 models. 415 of 428 cells modelled. **Not modelled (13):**
   `ebufn_{1,2,4,8}`, `einvn_{0,1,2,4,8}`, `einvp_{1,2,4,8}` (three-state; the SoC has none, `reports/lib2v_report.txt`). Bare buffers are emitted as `buf`
   gates, because `assign X = A` becomes a `_wire` primitive that Tessent will not accept as a buffer.
2. `libcomp` -> `sky130_hd.atpglib`: 415 models, **0 errors**, `lcVerify` "ALL PASSED for all patterns" (415 models) [M `build/libcomp/libcomp.log`].
   Note this checks the atpglib against *my generated Verilog*, not against vendor models (none available on this host).
3. `read_liberty` warnings (kept, not fixed): `dlclkp_*`/`sdlclkp_*` lack `clock_gate_test_pin`, so Tessent will not use them as test-logic clock gaters
   (the SoC clock gate is hand-instantiated and already has `SCE`); the 13 tristate cells have no match; `probe*`, `lpflow_*` buffers fail the buffer check and
   lose the attribute (unused).
4. `scripts/mk_tcelllib.py` replaces the auto-created `dft_cell_selection` (which picks `lpflow_*` low-power cells and `_4` drive strengths) with a curated
   `sky130hd` selection (`buf_2`, `inv_2`, `mux2_2`, `dlxtn_1` lockup latch, `sdf*` scan cells, ...). Scan equivalents for every flop in the netlist exist in the
   Liberty (`dfxtp_1`->`sdfxtp_1`, `dfrtp_1`->`sdfrtp_1`, `dfstp_*`->`sdfstp_*`, `edfxtp_1`->`sedfxtp_1`).

## 4. Results [M]

### 4.1 Scan insertion and DRC

6 chains of 3044, 3044, 3044, 3044, 3044, 3043 cells (**18,263 scan cells**, max imbalance 1 cell; the doc's section 8 proposal was ~3,511 for 5 fabric chains) via existing
`scan_in_i[5:0]`/`scan_out_o[5:0]`, 0 top-level ports added, 12 instances added (the tool reports 6 retiming elements; the other 6 are not itemised), flush test passes in
the ATPG-time DRC (`Chain = soc_scan_chain* successfully traced`). ScanDEF written (`build/soc_top.scanorder`, `write_scan_order`). 1m50s, 1.17 GB.
The test procedure file is inside the STIL (`soc_stuck.stil` Procedures block).

| Rule | Count | Handling | Triage (by Q-net RTL hierarchy, `reports/drc_triage.txt`) |
|---|---|---|---|
| S1 unstable non-scan cells when clocks off | 417 | demoted to warning | 243 `u_dft_ctrl.u_tap`, 122 `u_mbist.u_stsync_core`, 29 `mbist_ctl`, 8 `u_mbist.u_xing_core`, 4 `u_clk_sw`, rest single TAP outputs. **All TAP/MBIST TCK-domain flops: decision N4 (TAP flops on no chain).** |
| S2 clock capture ability | 471 | demoted to warning | same set (+64 `u_mbist.u_xing_core`): these flops are clocked by `tck_i`, held 0. Not a fix: the tool otherwise refuses to leave setup mode. |
| D5 non-scan memory element | 483 | warning | 415 TIE-0 (TAP flops held by `trst_ni`), 6 TIE-1, 56 INIT-X, 6 TLA (transparent latches). Same blocks. |
| C4 clock may be affected by captured data | 731 | note | all on `scan_rst_ni`: the reset cone contains flops (`pll_locked_o`, `cpu_pll_locked_o`, CDC reset-sync flops). Mux selects are constant in test mode, so likely structural pessimism; **not proven**, section 7. |
| S7 / E5 | 13 / 308 | note | S7: scannable cells tied to constants (reset-synchroniser stages, `u_crypto.scan_s1_q`). E5: X propagation from black boxes. |
| Any rule with `error` handling after demotion | 0 | | |

No S1/S2 violator is outside the declared TAP/MBIST-TCK set, so no exclusion was made to clear a report. Nothing needed an RTL change to proceed.

### 4.2 Coverage and patterns

| Fault model | Faults | Test coverage | Fault coverage | ATPG effectiveness | Patterns | CPU / wall |
|---|---|---|---|---|---|---|
| Stuck-at | 661,690 | **94.17 %** | 93.25 % | 99.99 % | **1,574** | 292 s / 4m55s, 1.18 GB |
| Transition (LOC, 2 pulses) | 608,006 | **81.28 %** | 80.42 % | 99.31 % | **2,567** (2,564 clock-sequential) | 1,587 s / 26m29s, 1.22 GB |

Targets in the DFT skill are 99 % SAF / 95 % transition; **neither is met**, and the project's own goal (`DFT_ARCHITECTURE` 2.1) is 99 % test / 98 % fault. The shortfall is
explained, not reclassified (section 4.3). Reports: `reports/stuck_statistics.rpt`, `reports/trans_statistics.rpt`. Shift time at 6 x 3,044:
1,574 x 3,045 = 4.8 M cycles (0.19 s at 25 MHz); transition 7.8 M cycles [A, arithmetic].

### 4.3 Where the stuck-at coverage goes (5.83 % not detected)

| Class (faults, % of 661,690) | Cause | Attribution (`reports/stuck_fault_triage.txt`, representative faults) |
|---|---|---|
| AU.BB black boxes, 6,915 (1.05 %) | CPU macro and 2 SRAM macros are X sources/sinks; no shadow logic exists (DFT_ARCHITECTURE 6.3 shadow flops are not built) | `u_cpu_axi_cdc` 3,097 (the CPU AXI boundary), `u_sram` 460, `u_npu` 395, CPU-facing glue |
| AU.PC pin constraints, 14,707 (2.22 %) | logic dead under the test-mode constants | `u_crypto` 2,598 (the `key_q`/`rk_q` AND masks, `~scan_mode`: by design), `u_mbist` 419, `u_dft_ctrl` 304, functional mux legs of the clock/reset muxes |
| AU.TC tied cells, 8,407 (1.27 %) | TAP/MBIST-TCK flops held in reset make their cones constant | `u_dft_ctrl` 3,101, `u_mbist` 852 (N4) |
| AU unclassified, 7,318 (1.11 %) | not broken down by the tool | `u_crypto` 1,155, `u_npu` 438, `u_mbist` 362, I2C/TRNG/SPI/PWM/GPIO 100-270 each (CDC synchroniser cones, constant-reset flops) |
| RE redundant 6,474 (0.98 %), PU 950, SEQ 280, UO 88 (ATPG abort) | | `u_mbist` 168 SEQ |

The 477 TAP/MBIST flops off the chains are N4 by decision (about 2.6 % of the sequential cells); they account for most of AU.TC and part of AU.PC [A, by attribution, not by an A/B run]. Crypto key-mask loss (2,598 representative faults, plus the key-fanout cones) is the quantified cost of decision 3.

**Transition**: 81.28 % with 89,242 unclassified AU (14.7 %) is not interpretable as a sign-off number. There are no timing exceptions, no OCC, no SDC, the CDC
crossings are not masked, and launch-on-capture uses the single ATE clock `scan_clk_i`. It shows the flow works and the order of magnitude; section 9 lists what a
real transition run needs.

## 5. Pattern verification (VCS) [M]

`scripts/vcs_sim.sh`: VCS Y-2026.03, the scan-inserted netlist `soc_top_scan.v`, the generated zero-delay cell models, X-output stand-ins for the black boxes
(`mk_sim_stubs.py`), and the Tessent serial testbench (chain test + **20 sampled patterns of 1,574**, `-sample 20`).

| Run | Result |
|---|---|
| good netlist | `Begin chain test` / `End chain test` / **`No error between simulated and expected patterns`** (2.80 ms simulated, 2m34s, 153 MB) |
| negative control: one mid-file scan link `.SCD()` tied to `1'b0` | **`Error between simulated and expected patterns`** (detected) |

NOT RUN: the full 1,574-pattern set, the transition patterns, parallel-mode patterns, and any simulation against vendor Sky130 cell models (the cell models are
derived from the same Liberty the ATPG used, so a Liberty misreading would be common-mode). The negative control proves the check can fail; it does not prove coverage.

## 6. Runtime and memory [M `reports/runtime.txt`]

yosys 17m44s / 1.10 GB; cell library < 3 min; scan insertion + DRC 1m50s / 1.17 GB; stuck-at ATPG 4m55s / 1.18 GB; transition ATPG 26m29s / 1.22 GB; VCS compile ~1 min,
run 2m34s / 153 MB. Host: 8 cores shared with a SpyGlass job; Tessent ran single-threaded.

## 7. Testability findings (proposals; no RTL changed)

| # | Finding | Where | Proposal |
|---|---|---|---|
| 1 | `scan_out_o[5:0]` placeholder tie must be deleted before insertion | `rtl/soc/soc_top.sv:421` | Stage 2 insertion step (this flow deletes it in the netlist) |
| 2 | SE is the internal TAP-or-pin net, not the raw port | `rtl/soc/soc_top.sv:360-382` | bind SE to `dft_scan_en` in real Stage 2; TAP-serial ATPG mode is untested here |
| 3 | 477-483 TAP/MBIST-TCK flops on no chain (N4) | `rtl/soc/dft/jtag_tap.sv`, `mbist_xing.sv`, `mbist_status_sync.sv` | accepted; they plausibly cost about 1.5 pp of stuck-at coverage together with their cones [A: AU.TC 1.27 % + part of AU.PC, not isolated by a separate run]. A separate TAP scan mode would recover it (N4 option) |
| 4 | 731 C4 notes: `scan_rst_ni` reset cones contain flops | `rtl/soc/pll/pll_subsystem.sv:121-127`, `pll_clkgen_stub.sv:52-57` (`locked_q`), `cdc_reset_sync.sv` | check with the Tessent C4 report that the muxes with constant select block the flop legs; if not, reset-pin faults need `scan_rst_ni` pulses the tool will not generate |
| 5 | Crypto mask makes the key cone untestable by design | `rtl/periph/crypto_accel.sv:491`, `rtl/periph/aes128_core.sv:461` | accepted (decision 3); quantified here: 2,598 AU.PC representative faults |
| 6 | CPU AXI boundary, SRAM pins: no shadow/bypass logic | `rtl/soc/soc_top.sv` (`u_cpu`, `u_sram`, `u_npu`) | the section 6.3 shadow flops are the biggest recoverable block (AU.BB 1.05 % plus their downstream cones) |
| 7 | Latches without a scan equivalent: `dlxtn_1` in the clock gate and `dft_clk_switch` enables, 6 transparent latches (TLA) | `rtl/mem/rv32i_clock_gate.sv:75`, `rtl/soc/dft/dft_clk_switch.sv` | none needed (clock-gate/test-clock internals); recorded |

## 8. Notes on tooling (for the next person)

- `tessent -shell -dofile x.tcl` **hangs in interactive mode after any aborted dofile**; always pass `< /dev/null`. `-logfile` is not overwritten without `-replace`
  (a stale log looks like a result).
- Start-up is 15 s on an idle host and was up to 9 minutes on a loaded one.
- The `-scan` legacy commands (`add_scan_groups`, `add_scan_chains`, `run`) exist but `insert_test_logic` in `set_context dft -scan` did nothing with them
  ("No test logic was inserted"). The working flow is the modern one: `-no_rtl -design_id gate`, `.tcelllib` with a `dft_cell_selection`, `add_scan_mode`, `analyze_scan_chains`,
  `insert_test_logic`, `write_design -tsdb`, then `set_context patterns -scan` + `read_design` + `import_scan_mode` (`/home/EDA/mentor/tessent2025/tessent_2025.4/share/UsageExamples/`
  `tessent_example_flat_flow_v2025.4.tgz` is the reference). `write_design -tsdb` fails if the TSDB exists: the Makefile removes it.
- `add_processors -number N` is rejected in 2025.4 (one thread was used); `set_multiprocessing_options -multithreading on` is accepted.
- The auto-generated `dft_cell_selection` is unusable for Sky130 (low-power cells); a buffer, inverter, mux and lockup latch are mandatory or insertion aborts.
- `set_drc_handling S1 warning` / `S2 warning` is required to leave setup mode with unscanned TCK-domain flops.
- `pgrep`-style waiting and `sleep` loops are blocked in agent sessions; use run-in-background and completion notifications.

## 9. Gap list toward real Stage 2

1. **PD back-annotation**: the scan netlist is not placed. Needs the ScanDEF into ODB (the OpenROAD DFT stage in `tools/dft/` used a different stitcher), scan re-ordering, a buffer tree for the
   18 k-sink SE net (Tessent connects `scan_en_i` straight to every scan cell [A: not measured]), hold repair on 18 k Q->SI links (`GRT_RESIZER_HOLD_SLACK_MARGIN` 0.3 ns), and the
   `sdf*`/`sedfxtp` cells allowed by the flow's `DONT_USE_CELLS` (unverified).
2. **Netlist realism**: re-run on the LibreLane synthesis netlist (it uses `dfxtp`+mux, not `edfxtp`) and on the PDK-installed Liberty and vendor Verilog models.
3. **Scan-mode SDC** (`j41m.5`): shift (`scan_clk_i`, `scan_en_i`=1) and capture (`scan_en_i`=0, LOC pulses) constraints; the functional SDC pins `scan_mode_i`=0.
4. **CPU macro wrapper** (`j41m.4`): the 4,880-flop macro is a black box here. Its scan chains (indices 6,7), SRAM collars and shadow logic must exist and be modelled (a Tessent core
   description/`add_core_instance` with the macro's chain info, or the macro netlist flattened in) before an SoC coverage number means anything.
5. **SRAM shadow/bypass** (DFT_ARCHITECTURE 6.3) and **TAP-serial** mode (SE = `dft_scan_en`).
6. **At-speed**: OCC/clock controller or ATE bursts, timing-aware transition ATPG with SDC/STA exceptions, CDC masking, `en_latch`/`dft_clk_switch` handling, the Q-META tester contract
   (`scan_clk_i` low across IR loads).
7. **Crypto wipe protocol** (`j41m.6` limit, 14.10 item 5): three capture-type edges after `scan_mode` rises; Tessent test setup does not know this. The first patterns here shift immediately.
8. **Compression** (TestKompress/EDT) was not attempted (not cheap on this netlist; flat 6 x 3,044 is already modest). `mttestkompress_c` is licensed.
9. Convert the patterns for an ATE/JTAG path (SVF/STIL via TAP) and run full-set and parallel-mode simulation.
10. Resolve the 731 C4 notes (finding 4) and the Tessent "unclassified AU" (14.7 % of transition faults).

`tools/dft/check_scan_clk_rst.py` / `make -C pnr dft-scan-check` were not affected: no RTL, netlist generator or Makefile under `pnr/` was changed.
