# SoC line + toggle coverage report (GH #216)

Bead `nkj7`. Measured 2026-10-06 on branch `feat/soc-coverage-216`. `VERIFICATION_PLAN.md:362` sets a
>95 % RTL line-coverage exit criterion; until now only the 9 CPU cocotb modules (`sim/Makefile coverage`)
were instrumented. This report covers the whole `tb/cocotb/soc` regression (`soc_all_ci`).

## Method

- `COVERAGE=1` in `tb/cocotb/soc/Makefile` adds `--coverage-line --coverage-toggle --coverage-max-width 256`
  to `COMPILE_ARGS` (not `EXTRA_ARGS`: most targets override that on the command line). Every `SIM_BUILD`
  gets a `_cov` suffix, so an instrumented build can never reuse an uninstrumented `Vtop` (the PR #142
  stale-`Vtop` false-pass class). Each simulation writes its own `<build>__<module>.dat` through the runtime
  plusarg `+verilator+coverage+file+` (honoured by cocotb 1.9.2's `verilator.cpp`).
  `--coverage-max-width 256` keeps the DMA's 8192-bit `linebuf` and the SRAM model arrays out of toggle coverage.
- `make soc_coverage` runs the whole `soc_all_ci` instrumented, merges all `.dat` files with
  `verilator_coverage --write`, and renders the tables below with `tools/verif/coverage_report.py`.
  It is not part of `soc_all_ci` / `soc_all`; CI runs it nightly (`.github/workflows/soc_coverage.yml`).
- Line % = `v_line` + `v_branch` points; toggle % = `v_toggle` points (per bit, per direction, as Verilator
  counts them). A point is the same point in every instance and testbench and is hit if any instance hit it;
  `<module>__<params>` specialisations fold into the base module.
- Triaged trees: `rtl/soc`, `rtl/periph`, `rtl/npu`. Informational: `rtl/cpu`, `rtl/mem`, `rtl/gpu`.
  Excluded: `tb/`, `sim/`, behavioural SRAM models.

Exact run command (15 GB host, `SIM_BUILD_ROOT` on the big disk, never concurrent with another soc sim):

```bash
nix develop --command make -C tb/cocotb/soc soc_coverage SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc_cov
# outputs: $SIM_BUILD_ROOT/coverage/{merged.dat,coverage_report.md,coverage_report.json}
```

Measured run: 53 suites, **480 passed, 0 failed, 16 skipped** (the same 480/0/16 as the uninstrumented
regression), 53 per-simulation `.dat` files merged, wall time about 85 min (5 095 s) with a cold build,
5.9 GB of build output. Nix Verilator 5.048 handled `--coverage` without the bead `hg2` crash: the Makefile
already passes `PYTHON3=$(SIM_PYTHON3)`, and `verilator_coverage` from the same nix profile merges fine, so
no source-built Verilator is needed.

**Re-measured 2026-10-07 after bead `8riq`** (same command, `SIM_BUILD_ROOT` from clean, all other RTL
unchanged): 54 suites (+ the new `axil_apb_fabric`), **511 passed by the CI log-grep formula, 0 failed, 17
skipped** (512 `PASS` rows in the `TESTS=` blocks: the extra one is the `expect_fail` guard
`test_ring_unmapped_read_single_beat`, which cocotb reports as a pass but the CI grep does not count; +31 =
14 fabric + 6 register_bank + 2 axil_to_apb + 10 apb_interconnect sweep points, minus that 1, reconciling exactly against the
prior 480). 55 `.dat` files merged. The tables below are this run.

Before / after for the touched modules (line % hit/total, toggle % hit/total):

| Module | Line before | Line after | Toggle before | Toggle after |
| :----- | ----------: | ---------: | ------------: | -----------: |
| axi_lite_interconnect | 95.0 (57/60) | **100.0 (60/60)** | 58.6 (863/1472) | 69.3 (1020/1472) |
| axi_lite_register_bank | 93.3 (42/45) | **100.0 (45/45)** | 48.3 (956/1978) | 61.5 (1212/1970) |
| axil_to_apb | 95.3 (41/43) | **100.0 (43/43)** | 76.4 (556/728) | 90.7 (660/728) |
| apb_interconnect | 100.0 (10/10) | 100.0 (10/10) | 46.0 (950/2064) | 76.5 (1578/2064) |
| apb4_register_bank | 100.0 (23/23) | 100.0 (23/23) | 75.3 (1411/1874) | 75.7 (1419/1874) |

The formerly uncovered points now hit: `axi_lite_interconnect` L206 (W_AW stall), L207 (W_DATA stall), L326
(R_AR stall); `axi_lite_register_bank` L156/L158 (`w_now` low: W captured before AW) and L205 (`RD_RESP` with
`rready` low); `axil_to_apb` L175/L176/L177 (ACCESS wait state, `S_WRESP`/`S_RRESP` held by a stalled master).
`s_axil_bresp`/`rresp` of the ring now leave OKAY end to end (EXOKAY/SLVERR/DECERR from a slave; DECERR from
the ring's own decode; SLVERR from `axil_to_apb` for a slave `pslverr` and for `apb_interconnect`'s
unclaimed-slot `pslverr_o`). `apb_interconnect` `pwdata_o`/`pstrb_o`/`pwrite_o`/`penable_o`/`paddr_o` are
now driven and checked on every slave copy. The two `axi_lite_register_bank` response ports are waived (tied to
OKAY by design, one new category-b waiver); the rest of the toggle gain is real stimulus.

**Waiver correction (partially addresses GH #222, W1).** The `soc_bus` waiver
`^(apb_pslverr|apb_m_pslverr)[\[:]` was too wide: `apb_m_pslverr` is `apb_interconnect`'s `pslverr_o`, which
is 1 on an unmapped APB access, so it is not a hard-wired constant. It is narrowed to `^apb_pslverr[\[:]` and
`apb_m_pslverr` (2 points) now shows as a never-toggling signal in `soc_bus`. It still does not toggle in the
full regression, and the reason is the memory map, not a missing test: the only hole in the APB window
(`0x2000_5000-0x2000_5FFF`) is claimed by the DMA slot of the AXI-Lite ring (last match wins in
`axi_lite_interconnect`), so no ring access can ever reach an unclaimed APB offset in the integrated SoC, and every APB slave ties
`pslverr` to 0. The same `apb_interconnect` -> `axil_to_apb` -> SLVERR path is covered in `axil_apb_fabric`,
which instantiates the real modules with a hole in the APB window. Making `soc_bus.apb_m_pslverr` toggle would need either a map change
or an unmapped-APB stimulus injected below the ring; that decision is left open.

Non-vacuity: the known gaps show up in the raw (pre-waiver) report: `timer_irq` never toggles, `i2c_scl_o` /
`i2c_sda_o` never toggle, and the DMA early-RLAST branch is not in the uncovered list (covered since bead
`wdmo`, PR #217).

## Results

### Triaged trees (after 54 waivers: 42 line and 878 toggle points removed from the denominator)

Totals: line **97.0 %** (1624/1675), toggle **62.7 %**
(37456/59728), 6 of 42 modules below the
95 % line floor. Before waivers the line total was 94.6 % (1624/1717) and 10 modules were below the floor.

| Module | Tree | Line % | Line hit/total | Toggle % | Toggle hit/total | Waived (line/toggle) |
| :----- | :--- | -----: | -------------: | -------: | ---------------: | -------------------: |
| npu_mac_array | rtl/npu | 100.0 | 8/8 | 100.0 | 1568/1568 | 0/0 |
| npu_top | rtl/npu | 100.0 | 55/55 | 87.4 | 2618/2994 | 0/2 |
| npu_weight_mem | rtl/npu | 100.0 | 12/12 | 100.0 | 530/530 | 0/0 |
| aes128_core | rtl/periph | 100.0 | 281/281 | 100.0 | 2348/2348 | 1/0 |
| crypto_accel | rtl/periph | 100.0 | 48/48 | 97.5 | 3349/3434 | 1/2 |
| dma_engine | rtl/periph | 94.1 | 64/68 | 31.6 | 752/2376 | 1/44 |
| gpio_controller | rtl/periph | 100.0 | 11/11 | 51.2 | 1092/2134 | 0/2 |
| i2c_bit_engine | rtl/periph | 100.0 | 113/113 | 88.6 | 434/490 | 1/0 |
| i2c_controller | rtl/periph | 97.6 | 83/85 | 91.0 | 1146/1260 | 1/6 |
| interrupt_controller | rtl/periph | 100.0 | 5/5 | 50.2 | 331/660 | 0/2 |
| pwm_controller | rtl/periph | 100.0 | 15/15 | 40.5 | 658/1626 | 0/2 |
| sha256_core | rtl/periph | 100.0 | 84/84 | 100.0 | 2268/2268 | 2/0 |
| spi_controller | rtl/periph | 96.2 | 51/53 | 35.9 | 475/1322 | 1/2 |
| timer | rtl/periph | 100.0 | 22/22 | 38.7 | 361/934 | 0/2 |
| trng | rtl/periph | 100.0 | 39/39 | 59.6 | 1215/2040 | 0/2 |
| trng_lfsr_entropy | rtl/periph | 100.0 | 18/18 | 100.0 | 396/396 | 0/0 |
| uart_controller | rtl/periph | 94.6 | 106/112 | 43.3 | 527/1216 | 3/2 |
| watchdog_timer | rtl/periph | 100.0 | 23/23 | 44.7 | 771/1724 | 0/2 |
| apb4_register_bank | rtl/soc | 100.0 | 23/23 | 75.7 | 1419/1874 | 0/2 |
| apb_cdc_bridge | rtl/soc | 100.0 | 47/47 | 98.7 | 705/714 | 2/2 |
| apb_interconnect | rtl/soc | 100.0 | 10/10 | 76.5 | 1578/2064 | 0/0 |
| async_axi_fifo | rtl/soc | - | 0/0 | 72.1 | 987/1368 | 0/2 |
| axi4_crossbar | rtl/soc | 96.0 | 119/124 | 43.2 | 1836/4252 | 6/0 |
| axi4_to_axilite | rtl/soc | 82.2 | 37/45 | 61.0 | 616/1010 | 2/12 |
| axi_lite_interconnect | rtl/soc | 100.0 | 60/60 | 69.3 | 1020/1472 | 2/48 |
| axi_lite_register_bank | rtl/soc | 100.0 | 45/45 | 61.5 | 1212/1970 | 2/20 |
| axil_to_apb | rtl/soc | 100.0 | 43/43 | 90.7 | 660/728 | 1/12 |
| axilite_to_axi4 | rtl/soc | 60.0 | 6/10 | 41.0 | 150/366 | 0/226 |
| boot_rom | rtl/soc | 62.1 | 18/29 | 27.8 | 146/526 | 2/0 |
| cdc_2ff_sync | rtl/soc | 100.0 | 5/5 | 100.0 | 44/44 | 0/0 |
| cdc_gray_fifo | rtl/soc | 100.0 | 15/15 | 65.4 | 421/644 | 0/0 |
| cdc_reset_sync | rtl/soc | 100.0 | 8/8 | 100.0 | 16/16 | 0/0 |
| pll_apb_regs | rtl/soc | - | 0/0 | 19.7 | 114/578 | 0/2 |
| pll_clkgen | rtl/soc | - | 0/0 | 40.0 | 8/20 | 0/0 |
| pll_clkgen_stub | rtl/soc | 100.0 | 5/5 | 62.5 | 20/32 | 0/0 |
| pll_subsystem | rtl/soc | - | 0/0 | 15.3 | 30/196 | 0/2 |
| pmu | rtl/soc | 100.0 | 31/31 | 36.6 | 231/632 | 3/2 |
| soc_addr_map_pkg | rtl/soc | - | 0/0 | - | 0/0 | 4/0 |
| soc_bus | rtl/soc | - | 0/0 | 44.5 | 2439/5482 | 0/100 |
| soc_periph_map_pkg | rtl/soc | - | 0/0 | - | 0/0 | 4/0 |
| soc_top | rtl/soc | 75.9 | 22/29 | 37.4 | 1828/4886 | 0/314 |
| sram_controller | rtl/soc | 97.9 | 92/94 | 74.1 | 1137/1534 | 3/64 |
| **Total (42 modules)** | | **97.0** | 1624/1675 | **62.7** | 37456/59728 | |

A dash means the module has no point of that kind (`soc_bus`, the `pll_*` wrappers and `async_axi_fifo` are
wiring or have no procedural line points; the two address-map packages are fully waived).

### Informational trees (no triage, no waivers)

These numbers come only from the SoC regression. The CPU, caches and GPU have their own dedicated suites
(`sim/Makefile`, `tb/cocotb/cpu`, `tb/cocotb/gpu`) that are not part of this run, so low figures here do not
describe those blocks' real coverage.

| Module | Tree | Line % | Line hit/total | Toggle % | Toggle hit/total | Waived (line/toggle) |
| :----- | :--- | -----: | -------------: | -------: | ---------------: | -------------------: |
| rv32i_alu | rtl/cpu | 53.8 | 7/13 | 98.6 | 276/280 | 0/0 |
| rv32i_branch_comp | rtl/cpu | 57.1 | 4/7 | 98.5 | 134/136 | 0/0 |
| rv32i_core | rtl/cpu | 88.6 | 31/35 | 51.5 | 2625/5094 | 0/0 |
| rv32i_cpu_top | rtl/cpu | 44.8 | 43/96 | 23.7 | 475/2006 | 0/0 |
| rv32i_csr_file | rtl/cpu | 43.2 | 41/95 | 26.7 | 433/1624 | 0/0 |
| rv32i_decode | rtl/cpu | 34.6 | 27/78 | 83.6 | 179/214 | 0/0 |
| rv32i_forwarding_unit | rtl/cpu | 95.6 | 43/45 | 69.4 | 1186/1710 | 0/0 |
| rv32i_hazard_unit | rtl/cpu | 89.7 | 35/39 | 95.1 | 196/206 | 0/0 |
| rv32i_imm_gen | rtl/cpu | 87.5 | 7/8 | 98.5 | 132/134 | 0/0 |
| rv32i_interrupt_ctrl | rtl/cpu | 100.0 | 3/3 | 22.6 | 19/84 | 0/0 |
| rv32i_pipeline_ex | rtl/cpu | 83.3 | 10/12 | 74.8 | 940/1256 | 0/0 |
| rv32i_pipeline_ex1b | rtl/cpu | 83.3 | 5/6 | 27.7 | 56/202 | 0/0 |
| rv32i_pipeline_ex1c | rtl/cpu | 52.4 | 11/21 | 68.4 | 26/38 | 0/0 |
| rv32i_pipeline_ex2 | rtl/cpu | 100.0 | 4/4 | 75.0 | 6/8 | 0/0 |
| rv32i_pipeline_id | rtl/cpu | 91.7 | 11/12 | 84.0 | 815/970 | 0/0 |
| rv32i_pipeline_if | rtl/cpu | 90.0 | 18/20 | 51.2 | 344/672 | 0/0 |
| rv32i_pipeline_mem | rtl/cpu | 45.5 | 20/44 | 57.4 | 624/1088 | 0/0 |
| rv32i_pipeline_wb | rtl/cpu | 100.0 | 5/5 | 70.4 | 490/696 | 0/0 |
| rv32i_regfile | rtl/cpu | 88.9 | 16/18 | 60.3 | 228/378 | 0/0 |
| gpu_command_queue | rtl/gpu | 100.0 | 7/7 | 8.3 | 72/870 | 0/0 |
| gpu_compute_unit | rtl/gpu | 73.1 | 49/67 | 24.7 | 1621/6560 | 0/0 |
| gpu_memory_unit | rtl/gpu | 100.0 | 5/5 | 17.6 | 418/2374 | 0/0 |
| gpu_top | rtl/gpu | 61.6 | 61/99 | 20.0 | 931/4644 | 0/0 |
| memory_coalescer | rtl/gpu | 90.0 | 36/40 | 16.8 | 578/3434 | 0/0 |
| shared_memory | rtl/gpu | 72.4 | 21/29 | 7.5 | 258/3452 | 0/0 |
| vector_alu | rtl/gpu | 33.3 | 7/21 | 26.2 | 850/3242 | 0/0 |
| vector_register_file | rtl/gpu | 100.0 | 7/7 | 28.3 | 468/1654 | 0/0 |
| warp_scheduler | rtl/gpu | 88.9 | 24/27 | 22.7 | 298/1310 | 0/0 |
| rv32i_cache_arbiter | rtl/mem | 96.3 | 26/27 | 63.9 | 561/878 | 0/0 |
| rv32i_clock_gate | rtl/mem | 100.0 | 3/3 | 100.0 | 8/8 | 0/0 |
| rv32i_dcache | rtl/mem | 93.6 | 160/171 | 62.0 | 2364/3810 | 0/0 |
| rv32i_icache | rtl/mem | 94.7 | 72/76 | 61.1 | 1705/2792 | 0/0 |
| **Total (32 modules)** | | **71.8** | 819/1140 | **37.3** | 19316/51824 | |

## Triage

Every uncovered line/branch point in the triaged trees, and every never-toggling control signal on a port,
was classified (the full per-module list is in `coverage_report.md` / `.json`):

- **(a) test gap** -> bead. **(b) unreachable by design** -> waiver in `tools/verif/coverage_waivers.txt`
  with a justification (no pragma edits to RTL). **(c) real bug** -> none found.

| Class | Items | Where |
| :---- | :---- | :---- |
| (c) bug | none | no uncovered point was dead logic that should not be |
| (b) waiver | FSM / `case` `default:` recovery arms (34 line points: 32 FSM arms across dma, i2c, spi, uart, crypto, apb_cdc_bridge, crossbar, axi4_to_axilite, axi-lite blocks, axil_to_apb, boot_rom, pmu, sram_controller, sha256, plus the 2 dead `sbox()` / `sha_k()` defaults) | state registers only hold named encodings in simulation |
| (b) waiver | unused reference decode helpers in `soc_addr_map_pkg` / `soc_periph_map_pkg` (8 line points) | no caller in RTL or tb |
| (b) waiver | `pslverr` tie-off on 15 APB modules and its soc_top/soc_bus fan-out; `AxPROT` (not decoded anywhere); constant DMA IDs; `*_unused` nets; `scanmode_i`; I2C `i2c_scl_o`/`i2c_sda_o` (dead open-drain outputs); `axilite_to_axi4` write channel tie-offs | constants by design |
| (a) bead `ej6j` | AXI4 fabric: crossbar decode-error bursts, `axi4_to_axilite` bursts/errors (78.7 % raw, the weakest triaged bridge), `axilite_to_axi4` AR skid, `boot_rom` write path (58 % raw), `sram_controller` FIXED/WRAP, `async_axi_fifo` error response | |
| (a) bead `8riq` -> **closed for the unit-level fabric** (2026-10-07, PR for `test/axil-apb-coverage-8riq`) | `axi_lite_interconnect` / `axi_lite_register_bank` / `axil_to_apb` / `apb_interconnect` are now **100 % line** (were 95.0 / 93.3 / 95.3 / 100 %). New suite `axil_apb_fabric` (14 tests: ring AW/W/AR stalls, B/R stalls, SLVERR/DECERR end to end, APB wait states, unclaimed APB slot -> SLVERR) plus register-bank, bridge and `apb_interconnect` additions. **Still open, now tracked separately:** SoC-level `soc_bus`/`soc_top` response signals (`periph_axil_*resp`, `axil_gpu/dma_*resp`, `mem_*resp`, `m_*resp`) need CPU firmware to reach an unmapped ring address, and `apb_m_pslverr` is unreachable through the current map (see below). RTL bug found: bead `3xtv` (phantom second DECERR read beat), pinned by an `expect_fail` guard | |
| (a) bead `bq2o` | `dma_engine`: max-burst saturation, AR/AW stall, write-response error, queue full | |
| (a) bead `05wf` | `uart_controller` / `spi_controller`: byte lanes 2/3, FIFO full, RX false-start, os_tick gaps | |
| (a) bead `oez2` | `soc_top`: `timer_irq`/`uart_irq`/`spi_irq`/`dma_irq`, GPU isolation, debug APB, PLL programming, SPI MISO | |
| (a) bead `pnfw` (existing) | I2C: slave-mode bit-counter arms L617/L645, SoC-level pad drive | notes appended |
| (a) bead `2k8` (existing) | GPU-domain PMU path (`pmu_gpu_iso_en` etc.) | note appended |

Waiver summary: 54 entries (20 line, 34 toggle), all category `b`, all with a justification
and a file:line reference. The report flags a waiver that matches no uncovered point as stale, and the unit
tests pin that a waiver can only remove an uncovered point from the denominator (raw % stays visible).

Not waived on purpose, left as visible gaps: every non-tie-off never-toggling signal (error responses,
IRQ lines, debug port, PLL registers, ROM write channel). They are listed under the (a) beads above.

## Gate decision

**Informational for now** (user decision, 2026-10-05): `soc_coverage` and its CI job never fail on a coverage
percentage; they fail only if the regression itself fails, the instrumented pass count drops below the
`PASS_FLOOR` (see `.github/workflows/cocotb.yml`, 508 as of 2026-10-07), or no coverage data is produced. Revisit once the (a) beads above land. Candidate floors
for that revisit:

- **Line**: 95 % per module in the triaged trees (the `VERIFICATION_PLAN.md:362` criterion), after waivers.
  Today 6 modules fail it, all explained by the (a) beads (`axi4_to_axilite`,
  `axilite_to_axi4`, `boot_rom`, `soc_top`, `uart_controller`, `dma_engine`).
- **Toggle**: a floor on control signals only (valids, readys, enables, IRQs, FSM state), never on datapath
  arrays. Raw toggle % is a poor gate (62.7 % overall) because wide data/address buses and per-bit directions
  dominate; the useful signal is the never-toggling list, which should be empty or waived.
- **No toggle gating of datapath arrays** (DMA `linebuf`, SRAM models, register-bank storage).

## Reproducing

```bash
python3 -m pytest tb/tests/test_coverage_report.py          # report-script tests
nix develop --command make -C tb/cocotb/soc soc_coverage SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc_cov
python3 tools/verif/coverage_report.py --dat <merged.dat> --waivers tools/verif/coverage_waivers.txt \
    --out-md report.md --out-json report.json              # re-render without re-simulating
```
