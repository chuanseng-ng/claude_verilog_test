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
or an unmapped-APB stimulus injected below the ring; **Decided 2026-10-07 (user): waive, do not change the map** -- `apb_m_pslverr` is now waived in
`soc_bus` with this map-based justification (W1 closed). Validated against PR #226's CI coverage data: the waiver matches,
no waiver is stale, and `apb_m_pslverr` no longer appears as uncovered.

Non-vacuity: the known gaps show up in the raw (pre-waiver) report: `timer_irq` never toggles, `i2c_scl_o` /
`i2c_sda_o` never toggle, and the DMA early-RLAST branch is not in the uncovered list (covered since bead
`wdmo`, PR #217).

**Re-measured 2026-10-08 after bead `oez2`** (SoC-level integration suite `soc_integration`, 6 tests, one Vtop).
Measurement level: **whole-SoC (`tb_soc_top`), directed firmware + testbench tests**, no unit-level stimulus. Basis
(not a full local `soc_coverage` run, which is too heavy for the 15 GB host): the `soc-coverage` artifact of the
scheduled CI run 37755024842 on `main` (merged `soc_all_ci` data) merged with this branch's instrumented
`soc_integration` run (`make soc_integration COVERAGE=1`, 6/6 PASS) and rendered with the unchanged
`tools/verif/coverage_report.py`; points are identified by module/file/line/column/object so the union is exact. The
CI `soc_coverage` run on the PR supersedes these numbers. One new category-b waiver
(`soc_top` `cpu_debug_{rs1,rs2,branch_taken,state}`, 138 points: `rv32i_core.sv:951-956` ties the CPU's legacy debug
taps to constants), no stale waiver.

| Module | Line before | Line after | Toggle before | Toggle after |
| :----- | ----------: | ---------: | ------------: | -----------: |
| soc_top | 75.9 (22/29) | **100.0 (29/29)** | 37.4 (1828/4890) | 50.4 (2401/4760) |
| pll_subsystem | - | - | 15.3 (30/196) | **71.4 (140/196)** |
| pll_apb_regs | - | - | 19.7 (114/578) | 26.0 (150/578) |
| pll_clkgen | - | - | 40.0 (8/20) | **100.0 (20/20)** |
| interrupt_controller | 100.0 (5/5) | 100.0 (5/5) | 50.2 (331/660) | 51.7 (341/660) |
| pmu | 100.0 (31/31) | 100.0 (31/31) | 36.6 (231/632) | 38.1 (241/632) |
| timer | 100.0 (22/22) | 100.0 (22/22) | 38.7 (361/934) | 42.0 (392/934) |
| **Triaged total** | 98.9 (1652/1670) | **99.3 (1659/1670)** | 65.5 (39082/59648) | 67.2 (40081/59656) |

Formerly uncovered `soc_top` points now hit (all behaviourally checked, not just toggled):
- `soc_top.sv` L1450-L1456 (GPU isolation clamps, 7 `cond_then` arms): PMU GPU power cycle with `gpu_irq_o == gpu_irq_raw & !gpu_iso_en`
  asserted on every cycle and the clamp seen acting (`raw=1, out=0, iso=1`) in the iso-before-reset window; sequence order
  `ret_save < iso_en < clk gate < reset` down and the reverse up checked from the testbench.
- `pmu_gpu_iso_en`, `pmu_gpu_ret_save`, `pmu_gpu_ret_restore`, `timer_irq` (+`_cpu_sync`), `uart_irq`, `spi_irq`, `dma_irq`:
  the CPU takes the trap for each (ISR committed, `mcause` 0x8000_0007 for the timer's direct MTIP and 0x8000_000B for the three
  routed through `interrupt_controller`, pending bit logged, source nets sampled at trap entry and after the handler).
- `spi_miso_i`: non-loopback SPI against a testbench slave; firmware reads back 0xA6, the slave checks MOSI 0x3C and CS framing.
- Debug path `apb_{psel,penable,pwrite,paddr,pwdata}_i`, `dbg_bridge_m_*`, and
  **`apb_pslverr_o`, `dbg_bridge_m_pslverr`** (un-waived by GH #222 W2): PSLVERR on a write to each RO CSR debug register
  (`rv32i_cpu_top.sv:64,330`) and the `apb_cdc_bridge` force-complete PSLVERR with the destination (CPU-domain) in reset,
  both before the request and with the reset asserted 1-6 cycles into it.
- `pll_m_pwdata`/`pll2_m_pwdata`/`paddr` and `pll_subsystem`/`pll_apb_regs` divider fields: both PLLs' CONTROL written
  through the fabric (read back, locked flag re-checked), `pll_fb_div`/`pll_post_div` of each instance checked after every
  write and the other instance proven untouched. `pll_clkgen_stub` is a pass-through by design, so the "output" observed is
  the divider ports at `pll_clkgen` plus the lock flag, not a frequency change.

Still open in this bead's scope: `i2c_*_oe_o` (pad drive, bead `pnfw`), ROM write channel `bus_rom_aw*/w*/b*` (bead `ej6j`,
unit level), `uart_rx_i` (bead `rqvo`), `pll_m_prdata`/`pready` partial points. `interrupt_controller` and `pmu` toggle
gains are small because their uncovered points are register-bank data/address bits, not integration paths.

**Finding (no RTL change made).** The GPU's flops are async-reset, so the PMU's domain reset clears all GPU state (the
level-held irq latch, `irq_enable`, `done`) even though the clock is gated first. `pmu.sv`'s header and
`docs/POWER_DOMAIN_EVALUATION.md` claim state survives an off/on cycle "by construction" because reset only asserts under a
gated clock; that holds for the synchronous-reset CPU but not for the GPU. `test_soc_gpu_isolation_via_pmu` asserts the
actual (state-lost) behaviour and a successful relaunch; tracked as a documentation/model-fidelity bead (the physical
behaviour of a power-gated domain with no retention cells is state loss anyway).

## Results

Basis (re-measured 2026-10-09, bead `7ovx`): ONE full local `make soc_coverage` on branch `test/register-walk-7ovx` (59 simulation runs, 597 passed / 0 failed / 17 skipped by the CI log-grep formula, 59 `.dat` files merged), rendered with the unchanged `tools/verif/coverage_report.py` and the waiver file after the 7ovx drift fix (below). The tables are therefore a single consistent measurement; the earlier per-bead dagger rows (unit-only `dma_engine`, `uart_controller`, `spi_controller`) are superseded by it. The PR's own CI `soc_coverage` run supersedes these numbers.

### Triaged trees (after 60 waivers: 48 line and 950 toggle points removed from the denominator)

| Module | Tree | Line % | Line hit/total | Toggle % | Toggle hit/total | Waived (line/toggle) |
| :----- | :--- | -----: | -------------: | -------: | ---------------: | -------------------: |
| npu_mac_array | rtl/npu | 100.0 | 8/8 | 100.0 | 1568/1568 | 0/0 |
| npu_top | rtl/npu | 100.0 | 55/55 | 87.4 | 2618/2994 | 0/2 |
| npu_weight_mem | rtl/npu | 100.0 | 12/12 | 100.0 | 530/530 | 0/0 |
| aes128_core | rtl/periph | 100.0 | 281/281 | 100.0 | 2348/2348 | 1/0 |
| crypto_accel | rtl/periph | 100.0 | 48/48 | 97.5 | 3349/3434 | 1/2 |
| dma_engine | rtl/periph | 100.0 | 67/67 | 38.5 | 911/2368 | 2/52 |
| gpio_controller | rtl/periph | 100.0 | 11/11 | 78.1 | 1667/2134 | 0/2 |
| i2c_bit_engine | rtl/periph | 100.0 | 113/113 | 91.4 | 448/490 | 1/0 |
| i2c_controller | rtl/periph | 97.6 | 83/85 | 91.0 | 1146/1260 | 1/6 |
| interrupt_controller | rtl/periph | 100.0 | 5/5 | 52.6 | 347/660 | 0/2 |
| pwm_controller | rtl/periph | 100.0 | 15/15 | 47.5 | 772/1626 | 0/2 |
| sha256_core | rtl/periph | 100.0 | 84/84 | 100.0 | 2268/2268 | 2/0 |
| spi_controller | rtl/periph | 100.0 | 53/53 | 45.6 | 603/1322 | 1/2 |
| timer | rtl/periph | 100.0 | 22/22 | 50.3 | 470/934 | 0/2 |
| trng | rtl/periph | 100.0 | 39/39 | 59.6 | 1215/2040 | 0/2 |
| trng_lfsr_entropy | rtl/periph | 100.0 | 18/18 | 100.0 | 396/396 | 0/0 |
| uart_controller | rtl/periph | 100.0 | 112/112 | 52.1 | 633/1216 | 3/2 |
| watchdog_timer | rtl/periph | 100.0 | 23/23 | 46.1 | 795/1724 | 0/2 |
| apb4_register_bank | rtl/soc | 100.0 | 23/23 | 79.6 | 1491/1874 | 0/2 |
| apb_cdc_bridge | rtl/soc | 100.0 | 47/47 | 99.9 | 713/714 | 2/2 |
| apb_interconnect | rtl/soc | 100.0 | 10/10 | 76.5 | 1578/2064 | 0/0 |
| async_axi_fifo | rtl/soc | - | 0/0 | 82.1 | 1123/1368 | 0/2 |
| axi4_crossbar | rtl/soc | 100.0 | 124/124 | 59.3 | 2522/4252 | 6/0 |
| axi4_to_axilite | rtl/soc | 100.0 | 42/42 | 81.2 | 820/1010 | 5/12 |
| axi_lite_interconnect | rtl/soc | 100.0 | 60/60 | 71.4 | 1085/1520 | 2/0 |
| axi_lite_register_bank | rtl/soc | 100.0 | 45/45 | 63.4 | 1256/1982 | 2/8 |
| axil_to_apb | rtl/soc | 100.0 | 43/43 | 90.7 | 660/728 | 1/12 |
| axilite_to_axi4 | rtl/soc | 100.0 | 10/10 | 66.8 | 250/374 | 0/218 |
| boot_rom | rtl/soc | 100.0 | 29/29 | 80.7 | 421/522 | 2/4 |
| cdc_2ff_sync | rtl/soc | 100.0 | 5/5 | 100.0 | 44/44 | 0/0 |
| cdc_gray_fifo | rtl/soc | 100.0 | 15/15 | 69.1 | 445/644 | 0/0 |
| cdc_reset_sync | rtl/soc | 100.0 | 8/8 | 100.0 | 16/16 | 0/0 |
| pll_apb_regs | rtl/soc | - | 0/0 | 26.0 | 150/578 | 0/2 |
| pll_clkgen | rtl/soc | - | 0/0 | 100.0 | 20/20 | 0/0 |
| pll_clkgen_stub | rtl/soc | 100.0 | 5/5 | 100.0 | 32/32 | 0/0 |
| pll_subsystem | rtl/soc | - | 0/0 | 71.4 | 140/196 | 0/2 |
| pmu | rtl/soc | 100.0 | 31/31 | 38.1 | 241/632 | 3/2 |
| soc_addr_map_pkg | rtl/soc | - | 0/0 | - | 0/0 | 4/0 |
| soc_bus | rtl/soc | - | 0/0 | 46.3 | 2538/5480 | 0/102 |
| soc_periph_map_pkg | rtl/soc | - | 0/0 | - | 0/0 | 4/0 |
| soc_top | rtl/soc | 100.0 | 29/29 | 53.3 | 2536/4760 | 0/440 |
| sram_controller | rtl/soc | 100.0 | 92/92 | 76.2 | 1169/1534 | 5/64 |
| **Total (42 modules)** | | **99.9** | 1667/1669 | **69.3** | 41334/59656 | |


A dash means the module has no point of that kind (`soc_bus`, the `pll_*` wrappers and `async_axi_fifo` are
wiring or have no procedural line points; the two address-map packages are fully waived).

### Informational trees (no triage, no waivers)

These numbers come only from the SoC regression. The CPU, caches and GPU have their own dedicated suites
(`sim/Makefile`, `tb/cocotb/cpu`, `tb/cocotb/gpu`) that are not part of this run, so low figures here do not
indicate a verification hole in those blocks. **The combined report below (bead `1eyv`) adds those suites; read
its numbers, not this table's, for `rtl/cpu`, `rtl/mem` and `rtl/gpu`.**

| Module | Tree | Line % | Line hit/total | Toggle % | Toggle hit/total | Waived (line/toggle) |
| :----- | :--- | -----: | -------------: | -------: | ---------------: | -------------------: |
| rv32i_alu | rtl/cpu | 61.5 | 8/13 | 99.3 | 278/280 | 0/0 |
| rv32i_branch_comp | rtl/cpu | 57.1 | 4/7 | 98.5 | 134/136 | 0/0 |
| rv32i_core | rtl/cpu | 88.6 | 31/35 | 56.5 | 2878/5094 | 0/0 |
| rv32i_cpu_top | rtl/cpu | 84.4 | 81/96 | 46.0 | 923/2006 | 0/0 |
| rv32i_csr_file | rtl/cpu | 47.4 | 45/95 | 29.6 | 480/1624 | 0/0 |
| rv32i_decode | rtl/cpu | 42.3 | 33/78 | 88.8 | 190/214 | 0/0 |
| rv32i_forwarding_unit | rtl/cpu | 100.0 | 45/45 | 72.5 | 1240/1710 | 0/0 |
| rv32i_hazard_unit | rtl/cpu | 94.9 | 37/39 | 98.1 | 202/206 | 0/0 |
| rv32i_imm_gen | rtl/cpu | 87.5 | 7/8 | 99.3 | 133/134 | 0/0 |
| rv32i_interrupt_ctrl | rtl/cpu | 100.0 | 3/3 | 32.1 | 27/84 | 0/0 |
| rv32i_pipeline_ex | rtl/cpu | 83.3 | 10/12 | 77.1 | 969/1256 | 0/0 |
| rv32i_pipeline_ex1b | rtl/cpu | 83.3 | 5/6 | 28.7 | 58/202 | 0/0 |
| rv32i_pipeline_ex1c | rtl/cpu | 71.4 | 15/21 | 78.9 | 30/38 | 0/0 |
| rv32i_pipeline_ex2 | rtl/cpu | 100.0 | 4/4 | 75.0 | 6/8 | 0/0 |
| rv32i_pipeline_id | rtl/cpu | 91.7 | 11/12 | 86.1 | 835/970 | 0/0 |
| rv32i_pipeline_if | rtl/cpu | 100.0 | 20/20 | 52.8 | 355/672 | 0/0 |
| rv32i_pipeline_mem | rtl/cpu | 61.4 | 27/44 | 58.5 | 636/1088 | 0/0 |
| rv32i_pipeline_wb | rtl/cpu | 100.0 | 5/5 | 72.4 | 504/696 | 0/0 |
| rv32i_regfile | rtl/cpu | 100.0 | 18/18 | 99.5 | 376/378 | 0/0 |
| gpu_command_queue | rtl/gpu | 100.0 | 7/7 | 8.3 | 72/870 | 0/0 |
| gpu_compute_unit | rtl/gpu | 73.1 | 49/67 | 25.9 | 1699/6560 | 0/0 |
| gpu_memory_unit | rtl/gpu | 100.0 | 5/5 | 20.0 | 474/2374 | 0/0 |
| gpu_top | rtl/gpu | 61.6 | 61/99 | 21.3 | 989/4644 | 0/0 |
| memory_coalescer | rtl/gpu | 90.0 | 36/40 | 19.0 | 652/3434 | 0/0 |
| shared_memory | rtl/gpu | 72.4 | 21/29 | 8.0 | 276/3452 | 0/0 |
| vector_alu | rtl/gpu | 33.3 | 7/21 | 27.6 | 894/3242 | 0/0 |
| vector_register_file | rtl/gpu | 100.0 | 7/7 | 29.6 | 490/1654 | 0/0 |
| warp_scheduler | rtl/gpu | 88.9 | 24/27 | 22.7 | 298/1310 | 0/0 |
| rv32i_cache_arbiter | rtl/mem | 96.3 | 26/27 | 65.8 | 578/878 | 0/0 |
| rv32i_clock_gate | rtl/mem | 100.0 | 3/3 | 100.0 | 8/8 | 0/0 |
| rv32i_dcache | rtl/mem | 93.6 | 160/171 | 67.8 | 2582/3810 | 0/0 |
| rv32i_icache | rtl/mem | 94.7 | 72/76 | 62.1 | 1735/2792 | 0/0 |
| **Total (32 modules)** | | **77.8** | 887/1140 | **40.5** | 21001/51824 | |

## Combined report: SoC + CPU / cache / GPU suites (bead `1eyv`, 2026-10-10)

The informational rows above reflect only what the `soc_*` suites incidentally hit. The CPU, Phase 3 cache and
Phase 4 GPU suites were never part of this report (the nightly `rtl-coverage` job measured only the CPU modules,
and its `make coverage` kept just the last simulation's `sim/coverage.dat`; GPU had no coverage wiring at all).
This section merges them in.

### Method

1. **Same toolchain, same flags.** `sim/Makefile` now takes `COVERAGE=1` exactly like the SoC Makefile:
   `--coverage-line --coverage-toggle --coverage-max-width 256` in `COMPILE_ARGS`, a `_cov` suffix on every
   `SIM_BUILD` (idempotent, because cocotb exports `SIM_BUILD` and a sub-make would otherwise append twice;
   instrumented and plain `Vtop` can never be reused for each other), and one `<build>__<module>.dat` per
   simulation through `+verilator+coverage+file+`. It replaces the blanket `--coverage` and the
   every-simulation-overwrites-`sim/coverage.dat` behaviour. `SIM_PYTHON3` is now overridable (CI needs it).
2. **`make -C sim coverage_cpu_gpu`** runs the 9 CPU modules + Phase 3 cache suites (`make test`) and `gpu_all`
   (unit, kernels, handoff, random smoke) instrumented, and merges them into `cpu_gpu_merged.dat`. The existing
   `make coverage` (nightly `rtl-coverage`, `sim/coverage_merged.dat` artifact) is kept, now also with per-simulation
   `.dat` files instead of losing the Phase 3 ones.
3. **Merge at the report level, not with `verilator_coverage --write`.**
   `tools/verif/coverage_report.py --dat soc/merged.dat --dat cpu_gpu_merged.dat` concatenates the inputs and
   aggregates them like instances of one run. The report already identified a point as
   (module, file, kind, line, column, object, source lines) with the hierarchy dropped and "hit if any hit", so a
   point of `rtl/cpu/...` measured by both flows is one point, hit if either hit it, with nothing new to
   reconcile. A raw `verilator_coverage --write` would instead need identical absolute paths *and* hierarchy keys
   to fold points, and the two flows differ in both: the SoC `.dat` records `tb_soc_top.u_soc.u_cpu...`, the CPU
   one `Vtop.rv32i_cpu_top...`, and the files carry whatever checkout root the run used (a developer worktree
   such as `.claude/worktrees/agent-xxx/`, `/home/runner/work/...` on CI, `../rtl/...` from `sim/`).
4. **Path normalisation** (new): a path under `--root` is made repo-relative; any other path is anchored on its
   `rtl/<soc|periph|npu|cpu|mem|gpu>/` component. Before, a `.dat` from another checkout (including every CI
   artifact opened locally) silently dropped all RTL as "outside root".
5. **No vacuous merge** (new): an input contributing zero reportable RTL points is an error naming the input;
   modules measured by more than one input have their point sets compared and listed under *Cross-input
   point-set consistency*, flagged `SUSPECT` below 80 % overlap (a union of two disagreeing sets would double the
   denominator and under-report), and the CLI warns on stderr. The union is never shrunk to the overlap and hits
   are never credited across non-matching points.
6. **Versions.** The nightly `rtl-coverage` job builds Verilator **5.036** from source; `soc_coverage` uses the
   flake-pinned nix **5.048**. Point keys are not guaranteed to match across them (not verifiable here: only 5.048
   is installed). So the combined CI run does *not* consume the `rtl-coverage-report` artifact: it runs
   `coverage_cpu_gpu` on the same nix Verilator inside `soc_coverage.yml`. Measured: with both inputs on 5.048,
   **every module measured by both flows has an identical point set** (consistency section empty), which is the
   check that the merge is exact rather than assumed. Cost: about 14 min and 1.5 GB for the CPU/cache/GPU
   half (29 `TESTS=` blocks, 207 tests, 0 failed), against 85 min for the SoC half.

SoC input: the 2026-10-09 `bead 7ovx` full `soc_coverage` run (597 passed by the CI formula, 0 failed), reused
rather than re-run. `git diff 745574e HEAD -- rtl` is empty, so the RTL it measured is exactly this tree's, and the
tests are the `soc_all_ci` set at `394db87`. Its `.dat` records another worktree's absolute paths, which is
itself the path-normalisation case. Triaged-tree numbers from this combined run are identical to the SoC-only
run (the CPU/GPU suites add nothing to `rtl/soc|periph|npu`): 42 modules, line 1667/1669, toggle 41334/59656.

```bash
nix develop --command make -C tb/cocotb/soc soc_coverage SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc_cov
nix develop --command make -C sim coverage_cpu_gpu SIM_BUILD_ROOT=/nobackup/claude_sim_build/cov_cpu_gpu
python3 tools/verif/coverage_report.py \
    --dat /nobackup/claude_sim_build/soc_cov/coverage/merged.dat \
    --dat /nobackup/claude_sim_build/cov_cpu_gpu/coverage/cpu_gpu_merged.dat \
    --waivers tools/verif/coverage_waivers.txt --out-md combined.md --out-json combined.json
# or in one go:  make -C sim coverage_combined SOC_DAT=<soc merged.dat> SIM_BUILD_ROOT=...
```

### Informational trees, before (SoC suites only) / after (combined)

Line % and toggle %, no waivers. "Before" is the 2026-10-09 SoC-only run (the earlier figures quoted in bead
`1eyv`, `rv32i_decode` 34.6 %, `rv32i_csr_file` 43.2 %, `rv32i_cpu_top` 44.8 %, `vector_alu` 33.3 %, were from
the first nkj7 run before the `soc_integration` and register-walk suites raised them; `vector_alu` is unchanged).

| Module | Tree | Line % SoC only | Line % combined | Line hit/total | Toggle % SoC only | Toggle % combined | Toggle hit/total |
| :----- | :--- | --------------: | --------------: | -------------: | ----------------: | ----------------: | ---------------: |
| rv32i_alu | rtl/cpu | 61.5 | 100.0 | 13/13 | 99.3 | 100.0 | 280/280 |
| rv32i_branch_comp | rtl/cpu | 57.1 | 100.0 | 7/7 | 98.5 | 100.0 | 136/136 |
| rv32i_core | rtl/cpu | 88.6 | 100.0 | 35/35 | 56.5 | 70.1 | 3572/5094 |
| rv32i_cpu_top | rtl/cpu | 84.4 | 96.9 | 93/96 | 46.0 | 54.7 | 1097/2006 |
| rv32i_csr_file | rtl/cpu | 47.4 | 70.5 | 67/95 | 29.6 | 39.0 | 634/1624 |
| rv32i_decode | rtl/cpu | 42.3 | 94.9 | 74/78 | 88.8 | 99.1 | 212/214 |
| rv32i_forwarding_unit | rtl/cpu | 100.0 | 100.0 | 45/45 | 72.5 | 87.1 | 1490/1710 |
| rv32i_hazard_unit | rtl/cpu | 94.9 | 97.4 | 38/39 | 98.1 | 99.0 | 204/206 |
| rv32i_imm_gen | rtl/cpu | 87.5 | 100.0 | 8/8 | 99.2 | 100.0 | 134/134 |
| rv32i_interrupt_ctrl | rtl/cpu | 100.0 | 100.0 | 3/3 | 32.1 | 32.1 | 27/84 |
| rv32i_pipeline_ex | rtl/cpu | 83.3 | 100.0 | 12/12 | 77.2 | 87.2 | 1095/1256 |
| rv32i_pipeline_ex1b | rtl/cpu | 83.3 | 83.3 | 5/6 | 28.7 | 50.5 | 102/202 |
| rv32i_pipeline_ex1c | rtl/cpu | 71.4 | 95.2 | 20/21 | 79.0 | 100.0 | 38/38 |
| rv32i_pipeline_ex2 | rtl/cpu | 100.0 | 100.0 | 4/4 | 75.0 | 100.0 | 8/8 |
| rv32i_pipeline_id | rtl/cpu | 91.7 | 100.0 | 12/12 | 86.1 | 99.0 | 960/970 |
| rv32i_pipeline_if | rtl/cpu | 100.0 | 100.0 | 20/20 | 52.8 | 83.3 | 560/672 |
| rv32i_pipeline_mem | rtl/cpu | 61.4 | 88.6 | 39/44 | 58.5 | 68.9 | 750/1088 |
| rv32i_pipeline_wb | rtl/cpu | 100.0 | 100.0 | 5/5 | 72.4 | 85.3 | 594/696 |
| rv32i_regfile | rtl/cpu | 100.0 | 100.0 | 18/18 | 99.5 | 99.5 | 376/378 |
| gpu_command_queue | rtl/gpu | 100.0 | 100.0 | 7/7 | 8.3 | 43.9 | 382/870 |
| gpu_compute_unit | rtl/gpu | 73.1 | 95.5 | 64/67 | 25.9 | 86.0 | 5643/6560 |
| gpu_memory_unit | rtl/gpu | 100.0 | 100.0 | 5/5 | 20.0 | 95.9 | 2276/2374 |
| gpu_top | rtl/gpu | 61.6 | 86.9 | 86/99 | 21.3 | 76.8 | 3569/4644 |
| memory_coalescer | rtl/gpu | 90.0 | 97.5 | 39/40 | 19.0 | 88.0 | 3021/3434 |
| shared_memory | rtl/gpu | 72.4 | 100.0 | 29/29 | 8.0 | 74.8 | 2582/3452 |
| vector_alu | rtl/gpu | 33.3 | 90.5 | 19/21 | 27.6 | 99.4 | 3222/3242 |
| vector_register_file | rtl/gpu | 100.0 | 100.0 | 7/7 | 29.6 | 98.8 | 1634/1654 |
| warp_scheduler | rtl/gpu | 88.9 | 100.0 | 27/27 | 22.8 | 40.1 | 526/1310 |
| rv32i_cache_arbiter | rtl/mem | 96.3 | 96.3 | 26/27 | 65.8 | 75.4 | 662/878 |
| rv32i_clock_gate | rtl/mem | 100.0 | 100.0 | 3/3 | 100.0 | 100.0 | 8/8 |
| rv32i_dcache | rtl/mem | 93.6 | 96.5 | 165/171 | 67.8 | 68.8 | 2620/3810 |
| rv32i_icache | rtl/mem | 94.7 | 94.7 | 72/76 | 62.1 | 93.7 | 2617/2792 |

Per tree (sum over modules, no waivers):

| Tree | Line, SoC only | Line, combined | Toggle, SoC only | Toggle, combined | Modules < 95 % line, before to after |
| :--- | -------------: | -------------: | ---------------: | ---------------: | -----------------------------------: |
| rtl/cpu (19) | 72.9 % (409/561) | **92.3 %** (518/561) | 61.1 % | **73.0 %** (12269/16796) | 13 to 4 |
| rtl/mem (4) | 94.2 % (261/277) | **96.0 %** (266/277) | 65.5 % | **78.9 %** (5907/7488) | 2 to 1 |
| rtl/gpu (9) | 71.9 % (217/302) | **93.7 %** (283/302) | 21.2 % | **83.0 %** (22855/27540) | 6 to 2 |

What the combined numbers say that the SoC-only ones hid: the large "gaps" in `rv32i_decode`, `rv32i_alu`,
`vector_alu`, `shared_memory` and the GPU toggle figures were just missing suites. What they now show as genuine,
unwaived gaps (bead `a5ze` tracks the triage): `rv32i_csr_file` (70.5 % line, 39.0 % toggle), `rv32i_pipeline_mem` (88.6 %),
`rv32i_pipeline_ex1b` (83.3 %, unchanged by every suite), `gpu_top` (86.9 %), `vector_alu` (90.5 %),
`warp_scheduler` (40.1 % toggle), `rv32i_interrupt_ctrl` (32.1 % toggle, no suite moves it) and
`gpu_command_queue` (43.9 % toggle). Not yet triaged: some may be unreachable by design and need waivers, none are
assumed to be.

### CI and recommendation

`.github/workflows/soc_coverage.yml` now runs `make -C sim coverage_cpu_gpu` on the same nix Verilator after the SoC
run (`continue-on-error`), renders the combined report, appends it to the job summary and uploads it as the
separate artifact `rtl-combined-coverage`. The existing `soc-coverage` artifact, per-flow report, `PASS_FLOOR`
and gate are untouched, and the nightly `rtl-coverage` job in `random_tests.yml` is unchanged. Everything stays
non-gating; `rtl/cpu|mem|gpu` stay **informational** in the report (the recorded user decision: triage covers
`rtl/soc|periph|npu` only; this change does not alter it).

**Recommendation (not applied): triage `rtl/cpu`, `rtl/mem` and `rtl/gpu` for line coverage, still not gating.**
The reason the user's decision was sound, that the numbers were an artifact of unrelated suites, no longer
holds: the combined figures (92.3 / 96.0 / 93.7 % line) are real and only 7 of 32 modules sit below 95 %, a
list short enough to work through the way the triaged trees were (test-gap bead or category-`b` waiver per
point). Toggle should stay out of any triage for these trees for now: the CPU's wide CSR/address/data buses
dominate it exactly as in the triaged trees. Promote only once the three nightly flows run together on the
same Verilator for a few cycles, so a `SUSPECT` consistency row would show up before anyone triages against it.

## 7ovx register-walk re-measurement (2026-10-09)

Bead `7ovx` (GH #216 follow-up). Most of the remaining toggle gap on the register-bank peripherals and the fabric was upper
data/address bits that never saw both edges, because tests wrote small values to a few low offsets. New reusable helper
`tb/cocotb/soc/reg_walk.py` + documented maps `reg_maps.py` (transcribed from the module headers and `MEMORY_MAP.md`, NOT read
back from the RTL's `RESET_VAL`/`WMASK`) + CPU-firmware generator `soc_reg_fw.py`.

**What a walk checks (behaviour, not just toggles).** Per register: idle/reset value; walking ones (32), walking zeros (32),
`0xFFFFFFFF`/`0`/`0xA5A5A5A5`/`0x5A5A5A5A`, each read back against `(model & ~wmask) | (written & wmask)` so every RO / reserved /
WO-reads-0 bit is proven to stay put; per-lane `pstrb` writes and `pstrb=0`; PSLVERR never; restore to reset; a second pass that
every register still holds its idle value after all the others were written (cross-talk); unmapped words read 0 and writes to
them disturb nothing (catches a snoop decoding too few address bits). Side-effect bits are removed from the driven pattern
(`Reg.drive`) rather than the register dropped: WDT `CTRL.enable`, TRNG `CTRL.enable`, PMU `CTRL[1:0]` power-mode request,
CRYPTO/NPU `CTRL.START`. Skipped registers print their reason: `UART_TX`, `SPI_TX`, `I2C_TX_DATA`, `NPU_AIN` (FIFO push),
`CRYPTO_KEY0-3`, `CRYPTO_DIN0-3`, `NPU_WDATA` (apertures), `I2C_CMD`, `WDT_FEED` (commands). W1C/W1P are checked
semantically by `check_w1c` and dedicated tests (below), because they need a pending bit created first.

**Applied at unit level** (a `test_register_walk` added to each existing suite, so no new Vtop build): timer, uart, spi,
interrupt_controller (N_SOURCES=5), gpio, pwm, wdt, trng, pmu, pll_apb_regs, i2c, crypto, npu = 13 tests. Plus 5 semantic tests:
GPIO edge-sticky W1C of all 32 pins one at a time and level-mode `GPIO_IRQ_CLR` is a no-op; PWM W1C of 4 wrap bits; WDT W1C of
bark and bite; NPU `CTRL.START` is W1P (reads 0) and the illegal start's `done`/`cfg_rejected` clear through IRQ_CLR[0]/[1]; CRYPTO
the same for `done`. `check_w1c` additionally proves a 0, a non-wired bit and a bit with its byte strobe low clear nothing.

**Applied at SoC level** (`test_soc_register_walk` in `test_soc_integration.py`, same Vtop as the other six): generated RV32I firmware
(no committed binary) walks 160 table entries - 104 registers across 14 peripheral windows (6 32-bit registers get the full set
and SB byte stores through every lane, the rest the short set) plus 56 unmapped words in the windows - through
CPU -> crossbar -> `axi4_to_axilite` -> `axi_lite_interconnect` -> `axil_to_apb` -> `apb_interconnect` (-> `apb_cdc_bridge` for
both PLLs). 104 927 cycles, 74 s. Result is read back independently over the debug APB (x30 = failing checks, x26-x29 = first
failure: address, written, read, expected). SoC-level exclusions on top of the unit ones: `IRQ_STATUS`/`IRQ_PENDING_MASKED` are
live (they mirror other peripherals' IRQ lines that the walk itself moves).

**Result: no RTL/doc register-map mismatch found** - every walk passed on the first run against the transcribed maps. That is a
finding only because the checks are non-vacuous (mutants below); no bead for a map bug was needed.

**Measured delta** (before = scheduled CI run 37910784827 on `main`, 2026-10-09 09:21; after = this branch's full local run;
rows shown only where toggle points changed; toggle hit/total):

| Module | Toggle before | Toggle after | Delta (points) |
| :----- | ------------: | -----------: | -------------: |
| gpio_controller | 52.0 (1110/2134) | **78.1** (1667/2134) | +557 |
| pwm_controller | 41.5 (674/1626) | 47.5 (772/1626) | +98 |
| timer | 42.0 (392/934) | 50.3 (470/934) | +78 |
| apb4_register_bank | 75.7 (1419/1874) | 79.6 (1491/1874) | +72 |
| soc_top | 50.4 (2401/4760) | 53.3 (2536/4760) | +135 |
| axi4_crossbar | 58.5 (2486/4252) | 59.3 (2522/4252) | +36 |
| soc_bus | 45.6 (2497/5480) | 46.3 (2538/5480) | +41 |
| i2c_bit_engine | 88.6 (434/490) | 91.4 (448/490) | +14 |
| watchdog_timer | 45.7 (787/1724) | 46.1 (795/1724) | +8 |
| interrupt_controller | 51.7 (341/660) | 52.6 (347/660) | +6 |
| spi_controller | 45.2 (597/1322) | 45.6 (603/1322) | +6 |
| async_axi_fifo / axi4_to_axilite / cdc_gray_fifo / boot_rom / uart_controller | | | +4 / +4 / +4 / +2 / +3 |
| **Triaged total** | 67.5 (40266/59656) | **69.3** (41334/59656) | **+1068** |

Line coverage is unchanged by the walk, except the informational CPU modules gain from the new instruction mix (SB/XORI/BNE
loops): `rv32i_pipeline_mem` 20/44 -> 27/44, `rv32i_decode` 27/78 -> 33/78, `rv32i_pipeline_ex1c` 11/21 -> 15/21.

**Why the gain is smaller than the issue's "worst pools" suggest - what is left is structural, not a missing walk.** For every
register-bank peripheral the surviving uncovered points are `hw_wdata_i` / `hw_wen_i` (the bank's HARDWARE-write port: for RW
registers it is tied to `regs_o`, for status registers it only carries the few real status bits), `regs_o` / `regs` bits that
belong to reserved, WO-snoop or RO-constant fields, `pready` (constant 1, zero wait states), `paddr[1:0]` (the banks ignore the byte
offset; a word-aligned master never toggles it, 4 points per module) and `prdata` bits above the implemented field width. A
software register walk cannot reach these. They need either waivers with the bank-structure justification (candidate bead) or the
unaligned-address probe. `soc_bus`/`soc_top`/`axi4_crossbar` residue is dominated by the upper address bits (`m_awaddr` 57/256,
`m_araddr` 67/256: the 32-bit address never leaves 0x0..0x2001_0FFF), the 128-bit D-cache write-back/refill data lanes
(`m_wdata` 120/256) and the unmapped ROM write channel (`bus_rom_aw*`/`w*`, bead `ej6j`), none of which are on the AXI-Lite -> APB path.

**Waiver drift fixed in passing (file `tools/verif/coverage_waivers.txt`, no waiver added or loosened).** Three FSM-`default:` waivers
had gone stale because later RTL edits shifted their lines, which made the report show the default arm as an uncovered line and
two stale-waiver warnings: `uart_controller` `L591` -> `L602` (bead `rqvo`), `pmu` `L262` -> `L275` and `L294|365` -> `L307|378`
(bead `4a7i` header edit, including the `pmu.sv:` line references in the justification text), `axi_lite_interconnect` `L328` -> `L335`.
Each target was re-read in the RTL and is still the `default:` arm it was waived as. After the fix: 0 stale waivers, line
99.9 % (1667/1669 - the two left are `i2c_controller` L617/L645, bead `pnfw`), 0 modules below the 95 % line floor.

**Non-vacuity (hand mutants, RTL reverted, `git diff --stat rtl/` empty).** Each killed by the named test:

| Mutant | Killed by |
| :----- | :-------- |
| `timer` CTRL WMASK `0x7` -> `0x3` (RW bit made RO) | `test_timer.test_register_walk` (35 mismatches) |
| `pwm_controller` `PWM_IRQ_STAT` made SW-writable | `test_pwm.test_register_walk` (45) |
| `pll_apb_regs` CONTROL WMASK `0x3F0` -> `0x3F1` (GH #89 self-brick path re-opened) | `test_pll_apb_regs.test_register_walk` (40) |
| `apb4_register_bank` `strb_expand` ORs lane 0 into every lane | `test_timer.test_register_walk` (4) |
| `crypto_accel` reserved word 28 SW-writable | `test_crypto.test_register_walk` (36) |
| `gpio_controller` W1C clear mask forced to 0 (W1C broken) | `test_gpio.test_register_w1c_semantics` (32) |
| `npu_top` CTRL WMASK `0x9` -> `0xD` (START stored, not W1P) | `test_npu.test_register_w1p_w1c_semantics` |
| `crypto_accel` CTRL WMASK `0x1B` -> `0x1F` (START stored) | `test_crypto.test_register_w1p_w1c_semantics` |
| `npu_top` `IRQ_CLR[1]` wired to `pwdata[0]` | `test_npu.test_register_w1p_w1c_semantics` |
| `axil_to_apb` `pwdata` bit 31 dropped | `test_soc_integration.test_soc_register_walk` (48 failing checks, first `timer.TMR_COMPARE` wrote `0x80000000` read `0`) |
| `axi4_to_axilite` `wstrb` lane 2 dropped | `test_soc_register_walk` (168 failing checks, first `timer.TMR_COMPARE`) |

Note the walk alone does NOT catch a stored W1P bit (the bit is never driven, by design), which is why the W1P/W1C semantic tests exist.

## ej6j AXI4-fabric re-measurement (2026-10-07)

Bead `ej6j` added directed suites: `test_crossbar_errors.py` (+7, run by `make crossbar`), `test_axi4_to_axilite.py` (10),
`test_axilite_to_axi4.py` (7), `test_boot_rom.py` (7) + `test_boot_rom_init.py` (2, a second build with `MEM_INIT_FILE`), one
`sram_controller` WRAP test (+1 per build) and two `async_axi_fifo` error-response tests, all on a new cycle-accurate BFM
(`axi4_fabric_bfm.py`). **No RTL bug was found.**

Scope of the numbers below: an instrumented run of ONLY these unit suites merged on their own
(`COVERAGE=1`, 6 `.dat`), not the full `soc_coverage` merge -- the SoC-level suites contribute nothing to these points, so the
ej6j-listed points are directly comparable; the module totals in the main table above are NOT yet re-measured (full run pending).

| Module | ej6j point (before: uncovered) | After (unit suites only) |
| :----- | :----------------------------- | :----------------------- |
| `axi4_crossbar` | L439, L478, L479, L515, L517; `dr_len`/`dr_cnt`/`slv_bresp`/`slv_rresp`/`s_rresp` never toggle | **0 uncovered lines (124/124 after waivers); no never-toggling signal** |
| `axi4_to_axilite` | L182, L205, L214, L288, L291; 13 never-toggling (`w_rem_q`, `r_rem_q`, `m_axil_bresp/rresp`, `w_resp_q`, ...) | L182/205/214/288/291 hit; **no never-toggling signal**; L150/152/155 waived (Verilator function-arm counter limitation, see waivers) |
| `axilite_to_axi4` | L131, L149, L152 (skid hold); `ar_hold_q`/`ar_addr_q`/`m_axi_rresp` never toggle | **10/10 lines**, no never-toggling signal |
| `boot_rom` | L107, L141-L157 (whole write path), L205; 19 never-toggling write-path signals | **29/29 lines**; `s_rresp` waived (constant OKAY) |
| `sram_controller` | L175/L178 (`last_addr`) | still shown uncovered by the instrument although INCR, FIXED and the range check run -- waived as the same function-arm counter limitation; WRAP rejection now tested |
| `async_axi_fifo` | `s_rresp_o` never non-OKAY | toggles; SLVERR/DECERR cross the CDC per beat (both clock ratios) |

Non-vacuity: 17 single-fault mutants (response accumulator, address increment, early B, skid-buffer capture/clear, ROM write
response/corruption/rlast, crossbar DECERR rlast/W-sink/R-advance, steered slave responses, WRAP check, FIFO bresp/rresp) were
each killed by the new suites. Kills were real test failures, not build errors.

**Not yet measured**: the full `make soc_coverage` / `soc_all_ci` (a Sky130 `librelane` run was active on the host, which this
15 GB machine cannot share with a SoC simulation). CI `PASS_FLOOR` was raised 477 -> 514 as a *derived* figure (477 + the 37
tests above); re-measure and tighten it on the next full run.

## GH #222 waiver audit (bead `kp61`, 2026-10-08)

Audit of the #220 waiver file against the RTL. Everything below was verified against the PR #226 CI data
(`merged.dat`, run 37539378647) with the fixed report; no waiver is stale.

| Item | Change |
| :--- | :----- |
| **T1** report line labels | `coverage_report.py` labelled a line point with the first line of Verilator's `S` span; inside a generate loop that is the `for` header (`pmu` points `l=294`/`l=365` came out as `L277`). Now labelled with the point's own `l` key; a gap whose span starts on another line shows it (`L294 (span 277,294)`). Branch arms are labelled by their own `l` too: Verilator writes an `else` arm with the `if` line (`l=152`, `S=155`), so it is now `L152 else`, not `L155 else`. Three new pytest cases with a generate-loop fixture (RED before, GREEN after); the two existing fixture tests moved to the `l` convention. Triaged-tree gap labels were otherwise unchanged by the fix; only informational CPU/GPU labels shifted (e.g. `rv32i_dcache` `L756 else` -> `L743 else`). |
| **W1** `soc_bus apb_m_pslverr` | already on this PR: waived, map-based justification (user decision 2026-10-07). |
| **W2** `soc_top` pslverr | `apb_pslverr_o` and `dbg_bridge_m_pslverr` removed from the waiver (reachable: CPU debug pslverr on writes to RO debug regs `rv32i_cpu_top.sv:64,330`; `apb_cdc_bridge` force-completes with pslverr when the destination is in reset, `apb_cdc_bridge.sv:214-230`). Kept: `apb_pslverr`, `pll_m_pslverr`, `pll2_m_pslverr` (bank-backed). The two are now uncovered test gaps tracked in bead `oez2` (+4 toggle points). |
| **W3** `pmu` | `^L(262\|277)` became two entries. L262 is the `default:` of `case (pmu_mode_req)`, a software-written 2-bit CTRL field whose 4 labels enumerate every value: reworded as exhaustive-enumeration dead default, not an FSM recovery arm. `^L(294\|365)` are the real per-domain generate-case recovery arms (verified against raw `l=` keys: both 0 in every instance). |
| **W4** `apb_cdc_bridge scanmode_i` | reference fixed: the ties are `soc_top.sv` `SCAN_MODE_TIE_OFF` at the instantiations (645, 705, 1019, 1246, 2074, 2180) and `tb_apb_cdc_bridge.sv:76`; `apb_cdc_bridge.sv:301` is only a comment. |
| **W5** AxPROT | Decision: test, not waiver, for the interconnect. New `test_axprot_routed_to_selected_slave_only` in `test_axil_interconnect.py` drives non-zero AWPROT/ARPROT (5 values x 3 slaves, write and read, plus an unmapped address) and checks the value arrives unchanged at the selected slave and never on another lane (`axi_lite_interconnect.sv:159,287`). Non-vacuity: dropping `_s_awprot[wsel]` and mis-routing `_s_arprot` to lane 0 are each caught (one failing assertion each); RTL reverted. The `axi_lite_interconnect` AxPROT waiver (48 points) is removed, and so is the `axi_lite_register_bank` one: its AxPROT ports (declared, never read) now toggle through the same test (12 points hit), so the waiver would have been stale. Kept, reworded ("at SoC level the only AXI-Lite master, `axi4_to_axilite`, ties AxPROT to 0, `axi4_to_axilite.sv:132,245`"): `axil_to_apb`, `dma_engine`, `soc_top`, `soc_bus`, `axi4_to_axilite`. |
| **W6** decode helpers | `decode_slave()` / `decode_axil_slave()` are kept uncalled reference helpers (`grep -rn` over `rtl tb sim tools sw`: only their definitions; docs cite them). No RTL deleted. Waivers reworded as "dead by intent", noting that under the #216 taxonomy this is closer to (c) dead code kept on purpose than to (b). |
| **ej6j function-arm waivers** | Claim checked and found **only partly true**. Raw `merged.dat`: `worse_resp` entry block L149 = 77 hits while the L150 elsif and both L152 arm points are 0; `last_addr` L175 if/else both 0. But arms of other functions are counted (`axi4_crossbar` `decode` L142, `axi_lite_interconnect` `decode` L95, `rv32i_csr_file` `apply_csr_op` L260). A 4-input micro-repro (Verilator 5.048, `tools/verif/repro/verilator_return_arm.sv`) isolates it: an if/else-if/else chain of `return` statements in a function reads 0 on every arm although called with all inputs, while the same chain assigning the function name counts. So the waivers are kept as a **tool limitation scoped to `return` arms** (the only two functions in the tree with that shape), reworded, and narrowed to `^L(150\|152)` (the report no longer produces an `L155`) and `^L175`. |

Cross-check of the open coverage-gap beads against the fixed labels: every line cited in `05wf` (uart L191/192/520/535/544/572,
spi L187/188), `bq2o` (dma L393/546/576/596) and `oez2` (`soc_top` L1450-L1456) is still the correct source line (re-read against
the RTL); no correction needed.

### 05wf re-measurement: `uart_controller` / `spi_controller` (unit level, 2026-10-08)

† rows in the table above. Measured with `make uart spi COVERAGE=1` (the two unit suites only, merged `.dat`,
`tools/verif/coverage_report.py` with the unchanged waiver file; no waiver added or removed). The unit-only
baseline before the new tests reproduced the full-SoC figures exactly on line coverage (uart 106/112, spi 51/53),
so the SoC-level numbers will be at least these; the full `soc_coverage` run supersedes them.

| Module | Line before | Line after | Toggle before (unit) | Toggle after (unit) |
| :----- | ----------: | ---------: | -------------------: | ------------------: |
| uart_controller | 94.6 % (106/112) | **100.0 % (112/112)** | 519/1216 (42.7 %) | 602/1216 (49.5 %) |
| spi_controller | 96.2 % (51/53) | **100.0 % (53/53)** | 461/1322 (34.9 %) | 561/1322 (42.4 %) |

Points closed: uart L191/L192 (lanes 2/3), L520/L544/L572 `else` (os_tick low in RX_START/DATA/STOP, slow-baud
runs at D = 1/3/4), L535 `cond_then` (false-start rejection); spi L187/L188 (lanes 2/3); `uart_controller.rx_full` and
`spi_controller.tx_full` now toggle (and `spi sclk_div_cnt_q` upper bits via `CLK_DIV = 0x8000`). Nothing waived
and no RTL change; remaining waivers on these two modules are the FSM `default:` arms and `pslverr` tie-off.
Tests added (13): uart 9 (`byte_lane_2_3_priority`, `rw_reg_partial_strobe`, `rx_fifo_full_drop_wrap`,
`tx_fifo_full_drop_drain`, `rx_false_start_rejected`, `stop_bit_glitch_no_framing_error`, `slow_baud_tx_timing`,
`slow_baud_rx_raw_and_framing`, `slow_baud_loopback`); spi 4 (`byte_lane_2_3_priority`, `rw_reg_partial_strobe`,
`tx_fifo_full_drop_drain`, `clk_div_wide_first_edge`). Behaviours pinned: lowest-asserted-`pstrb`-lane priority,
drop-newest FIFO semantics at depth 4 (flags, order, pointer wrap, IRQ), `tx_en`/`enable` gating, exact
`16*(D+1)`-clock bit windows on the TX pin, START majority-vote (single-clock glitch anywhere tolerated, majority-high
START rejected), STOP-bit vote tolerance. Hand mutants (14 + 3 re-runs): all killed except one provably equivalent
(`bit_tick` at phase 14 instead of 15 only shifts the phase, not the period). Residual toggle gaps are datapath/address
bits of the APB bus and register banks (`paddr`, `pwdata`, `prdata`, `regs_o`, `hw_wdata_i`), not control signals.

### Adjusted totals, before / after (triaged trees, PR #226 data)

| State | Line | Toggle |
| :---- | ---: | -----: |
| Before (HEAD of PR #230 with W1, old report script) | 98.74 % (1649/1670) | 64.99 % (38816/59730) |
| After waivers only (no new test) | 98.74 % (1649/1670) | **64.92 %** (38816/59794) |
| After waivers + AxPROT test (final) | 98.74 % (1649/1670) | 65.04 % (38891/59794) |

The honest effect of the waiver changes alone is a small drop in adjusted toggle coverage (64 points move back into the denominator:
48 `axi_lite_interconnect` AxPROT, 12 `axi_lite_register_bank` AxPROT, 4 `soc_top` debug-path pslverr); the new test recovers 75 hit points
(`axi_lite_interconnect` 1020 -> 1083, `axi_lite_register_bank` 1212 -> 1224). Line coverage is unchanged because the `pmu` waiver was retargeted,
not removed. Waiver file: 57 entries (23 line, 34 toggle), down from 58. Not run locally: the full `soc_all_ci`
/ `soc_coverage` (another agent's SoC simulation was active on this 15 GB host); PR CI covers it. `PASS_FLOOR` 545 -> 546.

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
| (b) waiver | `pslverr` tie-off on 15 APB modules and its soc_top/soc_bus fan-out; `AxPROT` on modules that ignore it (the interconnect's routing is tested, GH #222 W5); constant DMA IDs; `*_unused` nets; `scanmode_i`; I2C `i2c_scl_o`/`i2c_sda_o` (dead open-drain outputs); `axilite_to_axi4` write channel tie-offs | constants by design |
| (a) bead `ej6j` (**tests added 2026-10-07, see "ej6j AXI4-fabric re-measurement" below; full-run table above not yet re-measured**) | AXI4 fabric: crossbar decode-error bursts, `axi4_to_axilite` bursts/errors, `axilite_to_axi4` AR skid, `boot_rom` write path, `sram_controller` WRAP, `async_axi_fifo` error response | |
| (a) bead `8riq` -> **closed for the unit-level fabric** (2026-10-07, PR for `test/axil-apb-coverage-8riq`) | `axi_lite_interconnect` / `axi_lite_register_bank` / `axil_to_apb` / `apb_interconnect` are now **100 % line** (were 95.0 / 93.3 / 95.3 / 100 %). New suite `axil_apb_fabric` (14 tests: ring AW/W/AR stalls, B/R stalls, SLVERR/DECERR end to end, APB wait states, unclaimed APB slot -> SLVERR) plus register-bank, bridge and `apb_interconnect` additions. **Still open, now tracked separately:** SoC-level `soc_bus`/`soc_top` response signals (`periph_axil_*resp`, `axil_gpu/dma_*resp`, `mem_*resp`, `m_*resp`) need CPU firmware to reach an unmapped ring address, and `apb_m_pslverr` is unreachable through the current map (see below). RTL bug found: bead `3xtv` (phantom second DECERR read beat), pinned by an `expect_fail` guard | |
| (a) bead `bq2o` -> **closed at unit level** (2026-10-08, PR `test/dma-coverage-bq2o`; unit-measured, CI re-measure pending) | `dma_engine` is **100 % line (67/67 after waivers)**, was 91.2 % (62/68) at unit level with the pre-PR 10-test `test_dma` (raw 98.5 %, 67/68, before the L393 waiver). 8 new tests: burst clamp 255/256/257/293 words, AR / AW / W / B stalls (`arready`/`awready` low for 9/11 edges, `wready` low 3 edges per beat, B delayed 8 cycles), all channels stalled over a 4 KB-split + 256-clamp plan, write SLVERR and DECERR (second burst), stale `err_on_read` clear, descriptor queue full with silent drop. Beyond the bead's lines, **L584 (S_W `wready` stall) and L594 (S_B bvalid wait) were also uncovered** and are now hit. **L393 is waived (b), not tested**: it is dead (`beats_raw` is already clamped by `min2(.., MAX_BURST_BEATS)`), so the bead's "saturation never taken" was a misreading; the real clamp (min2) is tested and a `MAX-1` mutant is killed. `m_bresp` and `q_full` now toggle; `s_axil_bresp`/`s_axil_rresp` (8 points) are waived: tied OKAY in `axi_lite_register_bank`. Unit-level toggle 28.8 -> 37.5 % (the rest is datapath address/data bits and constant `m_arburst`/`m_*size`). Non-vacuity: 9 hand mutants of `dma_engine.sv` each killed (RTL reverted, `git diff --stat rtl/` empty): clamp MAX-1 (5 tests fail), DECERR ignored on B, stale `err_on_read` not cleared, queue-full guard removed, `arready` / `wready` / `awready` / `bvalid` ignored, `last_resp_q` not captured on B. No RTL bug found. | |
| (a) bead `05wf` -> **closed at unit level** (2026-10-08, branch `test/uart-spi-coverage-05wf`) | `uart_controller` / `spi_controller`: byte lanes 2/3, FIFO full, RX false-start, os_tick gaps — see "05wf re-measurement" below. SoC-level numbers in the table are marked † and are unit-suite figures until the next full `soc_coverage` run | |
| (a) bead `oez2` -> **closed** (2026-10-08, PR #236, see "Re-measured 2026-10-08 after bead `oez2`" above) | `soc_top`: `timer_irq`/`uart_irq`/`spi_irq`/`dma_irq`, GPU isolation, debug APB, PLL programming, SPI MISO | |
| (a) bead `pnfw` (existing) | I2C: slave-mode bit-counter arms L617/L645, SoC-level pad drive | notes appended |
| (a) bead `2k8` (existing) | GPU-domain PMU path (`pmu_gpu_iso_en` etc.) | note appended |

Waiver summary: 59 entries (24 line, 35 toggle; +2 for bead `bq2o`: `dma_engine` L393 dead saturate, `s_axil_bresp`/`s_axil_rresp` tied OKAY; GH #222 audit above), all category `b`, all with a justification
and a file:line reference. The report flags a waiver that matches no uncovered point as stale, and the unit
tests pin that a waiver can only remove an uncovered point from the denominator (raw % stays visible).

Not waived on purpose, left as visible gaps: every non-tie-off never-toggling signal (error responses,
IRQ lines, debug port, PLL registers, ROM write channel). They are listed under the (a) beads above.

## Gate decision

**Informational for now** (user decision, 2026-10-05): `soc_coverage` and its CI job never fail on a coverage
percentage; they fail only if the regression itself fails, the instrumented pass count drops below the
`PASS_FLOOR` (see `.github/workflows/cocotb.yml`, 574 as of 2026-10-09, bead `oez2`), or no coverage data is produced. Revisit once the (a) beads above land. Candidate floors
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
