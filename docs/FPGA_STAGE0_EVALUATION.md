# FPGA Stage 0 evaluation (bead `hlrm`, GH #245, PR #279)

Feasibility only: open tools, **no board, no vendor toolchain, no place-and-route, no timing, no hardware.**
Everything below is either *measured* (tool output quoted, source named) or *inferred* (marked). Nothing here is a
decision; the open human decisions are collected in section 9.

## 1. Method

1. **One define, `FPGA`**, selects block-RAM-inferable memories at every macro / flat-array site (section 3). With `FPGA`
   undefined the design is unchanged (section 4).
2. **File list** = the cocotb `PLL_SOURCES` list parsed out of `tb/cocotb/soc/Makefile` (cannot drift from what the
   regression elaborates) + `rtl/mem/rv32i_clock_gate.sv` (that list never names it: Verilator finds it through `-I`, sv2v has
   no `-I` and would silently blackbox it) + `rtl/fpga/*.sv`. `tools/fpga/stage0_filelist.sh`.
3. **No-GPU** = `rtl/gpu/*` replaced by `pnr/sky130/soc/gpu_top_tieoff.sv`, the *same* synthesisable tie-off the Sky130 SoC
   flow uses (`pnr/Makefile` `SKY130_SOC_SV_FILES`). No new exclusion mechanism. Note the Sky130 flow also blackboxes the CPU
   as a hard macro; **here the CPU stays real**, so "no-GPU" is CPU + peripherals + CRYPTO + NPU + DMA + SRAM.
4. **Synthesis**: sv2v (`--define=FPGA --define=__pnr__`) -> yosys `read_verilog`, `hierarchy -check -top soc_top`,
   `synth_xilinx -family xc7 -flatten -noiopad` or `synth_ecp5 -flatten -noiopad`, `stat`, `write_json`.
   `ulimit -v` 10 GB, one job at a time, outputs under `/nobackup/fpga_stage0/synth` (not in the repo).
   `tools/fpga/stage0_synth.sh`. `-noiopad`: no IOBUF/IBUF insertion, so port buffers are not in the counts.
5. **Resource + depth numbers** come from the yosys JSON via `tools/fpga/stage0_report.py`.
6. `__pnr__` is the define every synthesis flow in this repo already uses; it zero-initialises `boot_rom` (see section 7).

### Tool versions and where they came from

| Tool | Version | Source | In the project flake? |
|---|---|---|---|
| sv2v | 0.0.13.1 | `/nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1` (hard-coded in `pnr/Makefile` `SV2V ?=`) | **No.** Not in any `flake.nix` devShell. |
| yosys | 0.62 (git 7326bb7) | `/nix/store/f1q0w7rd0a4ny4hqvfxlhs4cmariidcy-yosys-0.62` (found in the nix store; presumably pulled in by the LibreLane environment: inference) | **No.** |
| Verilator | 5.048 | project flake `default` devShell | Yes |
| nextpnr (any), prjtrellis, prjxray, openFPGALoader | - | **absent** (searched `/nix/store`) | No |

Nothing was installed. The shared external LibreLane install was not edited. **A flake change is needed before Stage 1**:
today yosys and sv2v are reachable only by absolute store path. A small `fpga` devShell (yosys, sv2v, nextpnr-ecp5 +
prjtrellis, openFPGALoader) would make this reproducible; it is *not* done in this PR (decision 9.6).

## 2. Results

### 2.1 Resource table (measured: yosys 0.62 `stat` / JSON, `-flatten`, no P&R)

| | Xilinx 7-series, no-GPU | Xilinx 7-series, with GPU | ECP5, no-GPU | ECP5, with GPU |
|---|---|---|---|---|
| LUT (logic) | 38,554 (LUT1-6) | 62,353 | 34,172 (LUT4) | 67,427 (LUT4) |
| + LUT-RAM | 46 RAM32M (~184 LUT sites) | 46 RAM32M + 704 RAM64M + 1024 RAM128X1S (~5,048 LUT sites) | 68 TRELLIS_DPR16X4 | 2,116 TRELLIS_DPR16X4 |
| FF | 14,079 | 19,665 | 14,349 | 18,911 |
| Latch cells | 4 (LDCE) | 5 (LDCE) | see 2.4 | see 2.4 |
| Block RAM | 15 RAMB18 + 1 RAMB36 (= 9 RAMB36-eq) | same | 17 DP16KD (18 Kb) | 49 DP16KD |
| DSP | 19 DSP48E1 | 44 DSP48E1 | 19 MULT18X18D | 45 MULT18X18D |
| Carry | 852 CARRY4 | 1,194 CARRY4 | 1,731 CCU2C (2 bit each) | 2,372 CCU2C |
| Wide-mux | 3,271 MUXF7 / 872 MUXF8 | 4,472 / 941 | 6,220 PFUMX / 1,407 L6MUX21 | 9,505 / 512 |
| yosys wall / peak RSS | 5:38 / 2.0 GB | 8:36 / 2.1 GB | 3:05 / 1.6 GB | 9:42 / 2.1 GB |

Caveats on the table: yosys/ABC LUT counts are typically 10-30 % *worse* than Vivado/Quartus (**inference**, not measured
here); LUT-RAM sites are my conversion from primitive counts (RAM32M = 4 sites, RAM64M = 4, RAM128X1S = 2); ECP5 DPR16X4
costs roughly 2-3 slices each (**inference**, from memory of the ECP5 docs). Latch cells and unmapped logic are in the totals as
yosys reported them.

### 2.2 Which memories inferred block RAM (measured: `mapping memory ...` lines in the logs)

| Memory | Bits | Xilinx 7 | ECP5 |
|---|---|---|---|
| I-cache tag + 4 data banks (5 x 256x32) | 5 x 8 Kb | 5 x BRAM SDP (RAMB18) | 5 x PDPW16KD |
| D-cache tag + 4 data banks (5 x 256x32) | 5 x 8 Kb | 5 x BRAM SDP | 5 x PDPW16KD |
| `sram_controller` main SRAM (1024x32, byte-write) | 32 Kb | 1 x BRAM TDP (RAMB36) | 1 x DP16KD pair (2 x 18 Kb) |
| NPU weight memory (4 x 256x32) | 4 x 8 Kb | 4 x BRAM SDP | 4 x PDPW16KD |
| DMA `linebuf` (not an FPGA arm; inferred from the existing RTL) | small | BRAM SDP (RAMB18) | PDPW16KD |
| DMA `q_mem`, 5 x CDC FIFO `mem_q` | small | LUT-RAM | DPR16X4 (LUT-RAM) |
| GPU shared memory: 32 banks x 128x32 (16 KB total) | 32 x 4 Kb | **LUT-RAM, 32 x RAM128X1S-based (about 5 K LUT sites)** | **BRAM (32 x PDPW16KD)** |
| GPU vector register file `rf` (8 lanes) | 8 x ... | LUT-RAM | LUT-RAM |
| CPU register file | 31 x 32 x 3 read ports | flops/LUT logic (not mapped as `mapping memory`) | same |

**Finding:** the vendor mappers disagree on the same RTL for the GPU shared memory (7-series chose LUT-RAM, ECP5 chose BRAM),
and 7-series LUT-RAM there costs ~5 K LUT sites. Forcing `(* ram_style = "block" *)` in `fpga_sram_1rw` for the 128-deep case
would move 7-series to 32 RAMB18. I did **not** do this (it is a sizing/portability choice, section 9.3).
`proc_rom` turned 31 (no-GPU) / 33 (GPU) constant-`case` memories (AES/SHA S-boxes and constants) into logic; none became
block RAM.

### 2.3 Blackboxes / undefined modules

`hierarchy -check -top soc_top` passed in all four jobs and the log greps for blackbox / undefined / missing are empty
(measured). The earlier hazard is real though: before `rv32i_clock_gate.sv` was added to the list explicitly, Verilator
lint reported `MODMISSING` for it (3 instances) and sv2v would have silently blackboxed it. With IOBUF stripped
(`-noiopad`) and no vendor primitives instantiated in RTL, nothing else is left undefined.

### 2.4 Latches (measured: `Latch inferred` lines)

Six `proc_dlatch` inferences, identical in all four jobs: `rv32i_clock_gate.en_latch` (the ICG latch),
`dft_clk_switch.en_a_q` / `en_b_q` (intentional: glitch-free clock switch), and three `sv2v_autoblock_N.w` temporaries in
`rv32i_dcache` / `rv32i_icache`. The final cell count is 4 LDCE (no-GPU) / 5 LDCE (GPU) on 7-series, which matches the
three `rv32i_clock_gate` instances (`u_cpu_cg`, `u_gpu_cg`, `u_tck_cg`) + the two switch latches with the GPU gate
removed by the tie-off; the three `autoblock.w` latches do not appear to survive as cells (**UNVERIFIED**: I did not trace
them past `proc`). They exist in the shared RTL, not in the `FPGA` arms.

### 2.5 fmax: NOT MEASURED (ECP5 lower bound measured later)

> A post-route ECP5 lower bound now exists: CPU-only, LFE5U-85F-6, nextpnr 0.11.1, about 48-52 MHz (CPU domain) and
> 47-55 MHz (fabric domain) over 3 seeds; see [`FPGA_BOARD_SELECTION.md`](FPGA_BOARD_SELECTION.md) §5. Still no Xilinx timing.

There is **no nextpnr**, no Vivado, no Quartus. yosys has no placement or routing. What exists is a *depth proxy*: the
longest combinational path in LUT-level equivalents (LUT = 1, MUXF = 0.5, CARRY4 = 0.25; cut at FF/latch/BRAM/DSP/ports),
from the mapped JSON:

| | Depth (LUT-eq) | Bracket (depth x ns/level + overhead) | Assumption |
|---|---|---|---|
| 7-series, no-GPU | 20.5 | 58 .. 99 MHz | 0.45-0.80 ns/level + 0.9 ns |
| 7-series, GPU | 20.5 | 58 .. 99 MHz | same |
| ECP5, no-GPU | 19.0 | 38 .. 61 MHz | 0.80-1.30 ns/level + 1.3 ns |
| ECP5, GPU | 23.5 | 31 .. 50 MHz | same |

Limits: the ns/level figures are my assumptions, not device data; it ignores fan-out and routing congestion (this design has
large flat fan-outs, e.g. the ASIC work's 836-fanout counter-enable cone); it treats all clocks together (two clock ports,
`clk_i` and `cpu_clk_i`); the ECP5 runs cut 4 / 6 combinational loops (clock-gate / clock-mux latch paths) so the path may
be understated there. **Treat "tens of MHz" as the order of magnitude and nothing more.** An ASIC target of 1282 MHz (CPU) /
571 MHz (fabric) implies a prototype scale factor of roughly 10-40x; all later measurements must be labelled with it.

## 3. The FPGA arms (what was written, by whom, what each infers)

Written directly by the fpga-orchestrator (not sub-delegated to the rtl-design orchestrator); lint and checker below.

| Site | Arm | Infers |
|---|---|---|
| `rtl/fpga/fpga_sram_1rw.sv` (new) | stand-in for every 32-bit 1RW macro; ports = the macro/sim contract; dout holds on write and when `csb0` is high (identical to `sim/sram_1rw_256x32_verilator.v`, the model the regression uses) | single-port block RAM, sync read, no reset, one address |
| `rtl/fpga/fpga_sdp_ram_be.sv` (new) | byte-enabled simple-dual-port, registered read, read-first on a same-address collision | block RAM SDP/TDP with byte write |
| `rv32i_icache.sv`, `rv32i_dcache.sv` | `` `elsif FPGA `` arm for tag and data (`fpga_sram_1rw #(.AW(8))`) | BRAM |
| `npu_weight_mem.sv` | `` `elsif FPGA `` in the banked arm: 4 x `fpga_sram_1rw`; the shared 4:1 mux and 2-cycle read-latency normalisation are untouched | BRAM |
| `gpu/shared_memory.sv` | `` `ifdef FPGA `` around the bank instance (`AW(7)`) | LUT-RAM (7-series) / BRAM (ECP5), see 2.2 |
| `soc/sram_controller.sv` | the existing `SRAM_SKY130` two-port FSM (single write port, dedicated registered-read port, 2-entry skid buffer, **no flat array**) is reused through a file-local macro `SRAM_CTRL_2P` (defined iff `SRAM_SKY130` or `FPGA`; undefined at end of file); `FPGA` instantiates `fpga_sdp_ram_be` instead of the OpenRAM macro | BRAM (RAMB36 TDP), instead of the 32,768-flop + 1024:1 mux flat array |
| `rv32i_clock_gate.sv` | **NO ARM** (section 6) | - |

Why registered-read is timing-compatible: the Sky130 macro launches `dout1` on the negedge after the address edge and the
FSM samples it at the next posedge; a registered-output block RAM presents the same word over the same cycle, so
`rd_pend_q` is high exactly when the data is fresh. A same-cycle read+write of the same address is a race in the Sky130 arm
too; the FPGA arm returns the old word.

No arm contains an `initial`, a vendor primitive, an array reset, or a runtime-indexed mux of flops. The `ma7` defect class
(`OPT_MUXTREE` on runtime-indexed muxes) is a Synlig issue; this flow uses sv2v + yosys, and the coarse-grain check was not
re-run for the new files (nothing in them selects a flop array by a runtime index; reasoning, not a tool run).

## 4. Non-FPGA identity proof

`tools/fpga/stage0_sv2v_identity.sh` runs sv2v over the full SoC (with GPU and with the tie-off; file list identical on both
trees, `rtl/fpga` deliberately excluded) under the five non-FPGA define sets: none (cocotb default), `SIMULATION`,
`__pnr__`, `__pnr__ + SRAM_SKY130` (Sky130 SoC flow), `USE_ICG_CELL + __pnr__ + SRAM_ASAP7` (ASAP7 SoC flow), on a pristine
`git archive origin/main` export and on this branch, and compares with `cmp -s`.

Result (measured): **10 of 10 outputs byte-identical after one normalisation.** sv2v embeds `<absolute path>:<line>:<col>` in
every elaboration-time `$fatal` message; that is a diagnostic source location, it differs between two checkouts of the same RTL
and shifts when a file gains lines above a `$fatal` (`sram_controller.sv` gained 10). The script strips exactly that token
(`Fatal [..] <path>:L:C ` -> `Fatal [..] `) and nothing else before comparing. Before normalisation all 10 differed by those
lines only (first run: 72 diff lines in `nogpu_sky130`, all `$display("Fatal ...` lines).

| output | sha256 prefix (normalised) |
|---|---|
| gpu_sim / gpu_simulation / gpu_pnr / gpu_sky130 / gpu_asap7 | 76abbdb2... / bed3b4d2... / aaf5e54e... / 50ae3bdd... / d23ab691... |
| nogpu_sim / nogpu_simulation / nogpu_pnr / nogpu_sky130 / nogpu_asap7 | 4ac613f2... / 1361d449... / e064e71c... / d7f0bcd2... / 60f174dc... |

Verilator `-Wall` lint of full `soc_top` (`-Wno-IMPORTSTAR -Wno-UNUSEDSIGNAL -Wno-UNOPTFLAT -Wno-SYNCASYNCNET`), measured:
FPGA gpu 0 errors / 3 warnings, FPGA no-GPU 0 / 4, default gpu 0 / 4, default no-GPU 0 / 5; none of the warnings is in a file
this change touched (`rv32i_cache_pkg` unused parameters, `DECLFILENAME` on the tie-off). `check_struct_member_select.py`: exit 0.

## 5. Regression with the FPGA define

Command: `nix develop --command make -i -C tb/cocotb/soc FPGA=1 SIM_BUILD_ROOT=/nobackup/fpga_stage0/regr soc_all_ci`
(separate, content-keyed SIM_BUILD root; `FPGA=1` adds `+define+FPGA -y rtl/fpga`, a new opt-in hook in
`tb/cocotb/soc/Makefile`). `-i` because `soc_all_ci` is a chain of `$(MAKE)` lines and stops at the first failing suite; the
first, un-`-i` run aborted at `soc_boot` after 700 passed / 1 failed.

| Run | Passed | Failed | Notes |
|---|---|---|---|
| `soc_all_ci`, `FPGA=1`, no test edits (measured, CI-style grep `cocotb.regression .* passed$`), **before the helper** | **742** | **20** | 72 suite summaries; main is 762 |
| Diagnostic re-run of the 15 suites that contain the 20 failures, TB handle path temporarily changed (edit reverted, never committed) | 31 | **0** | the 20 pass; 742 + 20 = **762** = main |
| `soc_all_ci`, `FPGA=1`, **with the `sram_backdoor.sram_mem` helper (PR #282)**, same command, `SIM_BUILD_ROOT=/nobackup/fpga_helper/regr` (measured, CI grep) | **762** | **0** | 72 suite summaries, 17 skipped, 0 `contains no object named` lines, make exit 0; 2026-10-14 18:12 to 19:46 (cold build) |
| Default build, same commit, CI `cocotb soc_all` job (PR #282, run 38554821410) | **762** | **0** | log line `cocotb: 762 passed, 0 failed`; floors untouched |

**Resolved by `tb/cocotb/soc/sram_backdoor.py` (PR #282).** `sram_mem(dut)` tries `dut.u_soc.u_sram.mem`, then
`dut.u_soc.u_sram.u_fpga_mem.mem`, and raises `SramBackdoorError` naming every path tried if neither resolves; all 31 backdoor
sites in 18 SoC suites go through it (pure test refactor, no assertion or RTL change; `tb/tests/test_sram_backdoor.py` pins
each path and the error). The `SRAM_SKY130` macro arm (`u_sram.u_sram_macro`) is deliberately **not** served: no SoC-level
cocotb build defines `SRAM_SKY130`, so a path for it could not be verified, and the macro's read/write timing differs from the
flat array; the helper fails loudly there. The statement below describes the failure as it was before the helper.

**Root cause of all 20 failures (one cause, measured):** every one is `AttributeError: u_sram contains no object named mem`
(20 of 20 tracebacks, `grep -c`). These tests backdoor-read / backdoor-load the SoC SRAM through the hierarchical handle
`dut.u_soc.u_sram.mem` (about 20 sites across `test_boot`, `test_periph_loopback`, `test_soc_coherency`, `test_cpu_gpu_irq`,
`test_soc_gpio/pwm/wdt/trng/i2c/crypto/npu`, the multiclock and PMU suites). In the `FPGA` arm (and equally in the
`SRAM_SKY130` arm) the array is not in `sram_controller`; it is `u_sram.u_fpga_mem.mem`. It is a testbench
hierarchy dependency, not a functional RTL difference: with the path pointed at `u_fpga_mem.mem` all 20 pass. It also means
those 20 tests are the ones that prove the `sram_controller` FPGA arm end to end through the SoC; that evidence now exists from
the unmodified-RTL regression with the helper (762/762 above), not only from the diagnostic re-run. The `sram_controller` unit suite (AXI-only) and the boot
PC scoreboard / 100-boot stability passed unmodified under `FPGA=1`.

**CI job: NOT added (user decision 2026-10-14: "path helper, no CI job"), floors untouched** (`PASS_FLOOR` 759 / `CPU_PASS_FLOOR`
unchanged). The `FPGA=1` regression is a local-only check. Cost: ~35 min warm (measured: 06:57 to 07:24 for the cached `-i`
rerun), 94 min for the cold helper run above on this 15 GB host. The testbench blocker that kept it red is removed by the helper.

## 6. Clock gating: no arm written (decision needed)

`rv32i_clock_gate` is a latch + AND on the clock. Synthesised as-is (the numbers above assume this unchanged behavioural
gate): one `LDCE` per instance, and the AND output drives flop clocks from fabric, not from a clock buffer. Vivado/nextpnr
accept this only with warnings; the gated net is not a global clock, so skew and hold are untrustworthy. It gates `core_clk`
into `u_cpu`/`u_gpu` (PMU) and the DFT TCK path. **More than one reasonable option exists, so nothing was committed:**

| Option | What it is | Cost / risk |
|---|---|---|
| A. Vendor primitive per family | `BUFGCE` (Xilinx) / `DCCA` (ECP5) in the arm | Correct and glitch-free, but two vendor-specific arms; unknown-module lint stubs; cannot be exercised by Verilator |
| B. Clock enable | Remove gating; add a CE to every flop in the CPU/GPU domains | Closest to FPGA practice, but touches every flop (not a `rv32i_clock_gate`-only edit) and changes the verified RTL broadly |
| C. Pass-through | `gclk = clk`; the PMU still sequences reset/isolation/enables | One-line arm, no primitive; but the CPU/GPU keep toggling while "gated", so PMU power-down tests no longer prove the gate; functional behaviour under PMU sequencing is then only reset+isolation |
| D. Keep the latch+AND | Let the tool insert a BUFG on the fabric output | Zero RTL change; tool-dependent, timing unsupported, one more CDC-style hazard |

Recommendation (not implemented): **C for Stage 1 bring-up** (nothing to debug in the gate; PMU register interface still
works), and **A** only if a Stage 3 power-sequencing test needs real gating.

## 7. What does not map to an FPGA (or maps only conditionally)

| Item | Result |
|---|---|
| PLL (`pll_clkgen_stub`, `pll_subsystem`) | Stub is a pure reference pass-through; synthesises to wires. A real prototype needs MMCM/PLLE2 (7-series) or EHXPLLL (ECP5) at the top, not written. `pll_apb_regs` just becomes registers with no effect. |
| DFT (`jtag_tap`, `dft_clk_switch`, `dft_clk_mux`, `dft_rst_mux`, TCK ICG) | Synthesises (latch + mux clock paths, see 2.4) but is dead weight on a prototype; the intentional-latch clock switch maps to LDCE and creates fabric clock muxes the tools will warn about. Options: tie scan/test off and accept, or strip under `FPGA` (not done). |
| CDC primitives (`cdc_sync`, `cdc_reset_sync`, `cdc_gray_fifo`, `async_axi_fifo`, `apb_cdc_bridge`) | Map: 2-FF chains become FDRE/FDCE, gray FIFO storage becomes LUT-RAM with an async read. **Not** done: `ASYNC_REG` attributes and the `set_max_delay -datapath_only` constraints (the #94 SDC is Tcl-validated only and is Synopsys-style, not XDC/LPF). Without them a vendor tool will time the crossings as synchronous. |
| Pad-less GPIO / I2C triplets (`*_o`, `*_oe_o`, `*_i`) | No `inout` in the RTL. `-noiopad` leaves 292 port bits unbuffered. A top-level wrapper with `IOBUF`/`TRELLIS_IO` is needed at Stage 1; not written. |
| `boot_rom` | **Numbers understate it.** Under `__pnr__` it is zero-initialised (1024 words, 4 KB), so yosys folds it to constants. A real prototype loads firmware: `MEM_INIT_FILE`/`initial` becomes BRAM init, about 1 RAMB36 (7-series). Not in the counts. |
| 2 clock domains (`clk_i` 571 MHz class, `cpu_clk_i` 1282 MHz class on ASIC) | Both exist as ports. Two outputs of **one** MMCM are phase-related, so they would not exercise the async crossing the ASIC has; see 9.4. |
| ASAP7/Sky130 hard macros | None remain: every macro site has an `FPGA` arm or is behavioural. |

## 8. Device-class sizing (INFERENCE from vendor datasheet figures as I remember them; verify before buying)

Target utilisation from the skill defaults: LUT <= 70 %, BRAM <= 80 %, DSP <= 80 %. yosys LUT counts are pessimistic against
vendor tools, so these margins are conservative.

| Device (example board) | LUT | BRAM | DSP | no-GPU | with GPU |
|---|---|---|---|---|---|
| XC7A35T / 50T (Arty A7-35/50) | 20.8 K / 32.6 K | 50 / 75 RAMB36 | 90 / 120 | **No** | **No** |
| XC7A75T | 47.2 K | 105 | 180 | Fits, ~82 % LUT: no margin | No |
| XC7A100T (Arty A7-100, Nexys A7) | 63.4 K | 135 | 240 | **Fits, ~61 % LUT** | No (~106 % with LUT-RAM) |
| XC7A200T | 134.6 K | 365 | 740 | Fits (~29 %) | **Fits, ~50 %** |
| XC7K325T (Genesys 2, KC705) | 203.8 K | 445 | 840 | Fits (~19 %) | Fits (~33 %) |
| ECP5 LFE5U-25F | 24 K | 56 DP16KD | 28 | **No** | **No** |
| ECP5 LFE5U-45F | 43.8 K LUT4 | 108 | 72 | Fits, ~78 % LUT: no margin | **No** |
| ECP5 LFE5U-85F (ULX3S, Versa, OrangeCrab 85) | 83.6 K | 208 | 156 | **Fits, ~41 %** | Marginal: 67.4 K LUT4 + LUT-RAM (~8-13 K sites) is ~90-95 %, above the 70 % target |

BRAM and DSP are not the limit anywhere: 9 RAMB36-eq of 105+ (7-series), 17 / 49 DP16KD (ECP5), 19-45 multipliers.
The GPU is LUT-bound, and 7-series mapped its 16 KB shared memory to LUT-RAM (~5 K sites) where BRAM would be nearly free.

## 9. Board options and go / no-go (options for the user, not a decision)

> **Superseded for board choice by [`FPGA_BOARD_SELECTION.md`](FPGA_BOARD_SELECTION.md)** (2026-10-14): growth-adjusted sizing,
> Singapore price/stock, recommendation (Nexys Video, XC7A200T), second-clock add-on and fmax tool availability.

| Option | Fits | Toolchain | Note |
|---|---|---|---|
| 1. ECP5-85F board (ULX3S / Versa) | no-GPU with margin | Fully open: yosys + nextpnr-ecp5 + prjtrellis + openFPGALoader (nextpnr/prjtrellis not on host: flake change) | Only option that needs no vendor tool; GPU does not fit with margin |
| 2. Artix-7 100T board (Arty A7-100T / Nexys A7-100T) | no-GPU with margin | Vivado (free WebPACK covers this part); nextpnr-xilinx is experimental | Cheapest vendor-backed path; GPU does not fit |
| 3. Artix-7 200T / Kintex-7 325T (Genesys 2, KC705) | both builds | Vivado | Only way to prototype CPU + GPU together without shrinking the GPU |

Go / no-go as options: **no-GPU prototype: GO on option 1 or 2** (measured fit by resource count; fmax and routing unproven).
**With-GPU prototype: NO-GO on options 1 and 2 as-is**; it needs either option 3, or a smaller GPU, or moving the GPU shared
memory to BRAM and re-measuring (7-series: removes ~5 K LUT sites, still ~62 K LUT, ~98 % of an A7-100T, so still no).

### Open human decisions

1. **Board / vendor family** (options above).
2. **GPU does not fit** on the cheap boards: choose option 3, shrink the GPU (lane count, 16 KB shared memory), or ship the CPU-only prototype first.
3. **GPU shared memory style on FPGA** (`ram_style` BRAM vs LUT-RAM; vendor mappers disagree).
4. **Clock-gating strategy** (section 6; recommendation C then A).
5. **Dual-oscillator CDC plan** for later stages: two independent oscillators/PLLs (needed for the async-crossing soak and the 7 ns / 3 ns coprime ratio the ASIC regression used) vs one MMCM with two outputs (phase-related, does not stress the CDC). Also the XDC/LPF translation of the #94 SDC and `ASYNC_REG`.
6. **Flake change** for yosys/sv2v/nextpnr/openFPGALoader (an `fpga` devShell) vs keeping absolute store paths.
7. **CI job for the FPGA-define regression**: proposal in section 5; not added.
8. Whether to strip DFT / TAP on the prototype and who owns the top-level IO wrapper and `boot_rom` image.

## 10. What was NOT verified

No place-and-route, no timing (fmax **not measured**), no bitstream, no hardware, no vendor-tool synthesis (so Vivado/Quartus LUT counts will differ),
no gate-level or post-synthesis simulation of the yosys netlist, no metastability/CDC behaviour on FPGA, no power. The `boot_rom`
content and IO buffers are outside the counts. Device sizing is inference. The `ecp5` jobs initially aborted in yosys's cosmetic
`autoname` step (`std::bad_alloc` under the 10 GB cap, peak RSS ~8.8 GB); the final runs use `synth_ecp5 -run :check` (every
mapping pass runs; only `autoname` / `hierarchy -check` / `stat` of the `check` label are skipped, and `stat` + `blackbox
=A:whitebox` are run explicitly). The 7-series runs used the full `synth_xilinx` script.
