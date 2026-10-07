# Makefile for SoC cocotb tests (Phase 5 / M3–M9)
# Component unit tests (M3–M6) + SoC boot test (M9).

TOPLEVEL_LANG ?= verilog
SIM ?= verilator

# Absolute paths so the Makefile works whether invoked from sim/ or here.
SOC_DIR  := $(shell pwd)
PROJ_ROOT := $(abspath $(SOC_DIR)/../../..)
RTL      := $(PROJ_ROOT)/rtl
TB       := $(PROJ_ROOT)/tb/cocotb
SIM_DIR  := $(PROJ_ROOT)/sim

# Bead claude_verilog_test-f97: base directory for the per-target sim_build dirs.
# Defaults to `.` so an unset environment behaves exactly as before (CI unchanged).
# Point it at scratch when the root filesystem is tight, e.g.
#   make SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc soc_all
# The 26 per-target dirs are ~190 MB each (~5 GB total) and EVERY one of them is
# invalidated by any RTL edit, so a full soc_all rebuild needs several GB at once.
# When that space is not there the run dies part-way and reports
#   ERROR: results.xml was not written by the simulation!
# AFTER the per-suite PASS lines -- an ENOSPC that does not look like one.
# Same idea as the AMS cosim flow's SIM_BUILD routing (CLAUDE.md, PHASE7 plan).
SIM_BUILD_ROOT ?= .
ifeq ($(strip $(SIM_BUILD_ROOT)),)
  $(error SIM_BUILD_ROOT is empty -- refusing to build or clean at the filesystem root)
endif

# GH #216 / bead nkj7: where `make soc_coverage` collects per-simulation coverage .dat files, the
# merged.dat and the report.  Absolute, because every sub-make and every simulator process runs
# from this directory but a relative path would silently follow a future `-C`.
COV_DIR ?= $(SIM_BUILD_ROOT)/coverage
override COV_DIR := $(abspath $(COV_DIR))

# Bead claude_verilog_test-f97: pre-flight free-space gate.  A full soc_all
# rebuild writes ~5 GB of Verilator objects; running out mid-flight surfaces as
# a post-PASS `results.xml was not written` error that reads like flaky infra.
# Fail here instead, naming the real cause.  Override the floor if you know the
# build is incremental: make SIM_BUILD_MIN_FREE_MB=500 soc_all
SIM_BUILD_MIN_FREE_MB ?= 6000

# NOTE: the check-space RECIPE lives at the bottom of this file, after the
# cocotb `include`.  Any target defined before that include becomes make's
# default goal, and the per-suite recipes re-invoke `$(MAKE) MODULE=... ` with
# NO explicit target -- so a target up here silently replaces the cocotb `sim`
# goal and every suite runs the check instead of the test, exiting 0 having
# tested nothing.  Only the variables may live up here.

# bfm/ lives in tb/cocotb (TB); slave model lives in this directory.
export PYTHONPATH := $(TB):$(SOC_DIR):$(PYTHONPATH)

# GH #104 Sky130 SoC Stage-2 — sram_controller.sv backing-store selection for
# the standalone `sram_controller` unit-test target only (mirrors the
# SRAM_TARGET convention in sim/Makefile). PLL_SOURCES/SOC_BOOT_SOURCES below
# instantiate soc_top, which also has a cache-macro `ifdef SRAM_SKY130`
# selection (rv32i_dcache.sv/rv32i_icache.sv) not wired to a SRAM_TARGET
# switch in *this* Makefile today — enabling SRAM_TARGET=sky130 here only
# affects the isolated sram_controller DUT (no cache in its source list).
# For a full soc_top elaboration under SRAM_SKY130, use
# `make -C sim lint_soc_sky130` (sim/Makefile swaps both the cache and
# sram_controller macros together).
#   make sram_controller                      # flat array (existing 7/7 suite)
#   make sram_controller SRAM_TARGET=sky130   # sky130_sram_4kbyte_1rw1r_32x1024_8
SRAM_TARGET ?= freepdk45
ifeq ($(SRAM_TARGET),sky130)
    SRAM_CTRL_SIM_MODEL := $(SIM_DIR)/sky130_sram_4kbyte_1rw1r_32x1024_8.sv
    COMPILE_ARGS += +define+SRAM_SKY130
else
    SRAM_CTRL_SIM_MODEL :=
endif

# Per-DUT source lists.  The default build is the crossbar (preserves prior
# `make` behaviour); the register_bank / axil_interconnect targets override
# VERILOG_SOURCES + MODULE + TOPLEVEL on the recursive make.
XBAR_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(RTL)/soc/axi4_crossbar.sv \
	$(SOC_DIR)/tb_axi4_crossbar.sv

REGBANK_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(SOC_DIR)/tb_axi_lite_register_bank.sv

AXIL_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_periph_map_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/soc/axi_lite_interconnect.sv \
	$(SOC_DIR)/tb_axi_lite_interconnect.sv

# Bead claude_verilog_test-8riq: the real ring -> axil_to_apb -> apb_interconnect -> apb4_register_bank
# chain with scripted AXI-Lite / APB slaves (stalls + error responses), see tb_axil_apb_fabric.sv.
AXIL_APB_FABRIC_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_interconnect.sv \
	$(RTL)/soc/axil_to_apb.sv \
	$(RTL)/soc/apb_interconnect.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(SOC_DIR)/tb_axil_apb_fabric.sv

SRAM_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(SRAM_CTRL_SIM_MODEL) \
	$(RTL)/soc/sram_controller.sv

# Bead ej6j: standalone AXI4-fabric bridge / ROM unit suites (the DUT is the toplevel, like sram_controller).
A2L_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi4_to_axilite.sv

L2A_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axilite_to_axi4.sv

BOOTROM_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(RTL)/soc/boot_rom.sv

DMA_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/periph/dma_engine.sv

TIMER_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/timer.sv

IRQ_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/interrupt_controller.sv

UART_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/uart_controller.sv

SPI_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/cdc/cdc_2ff_sync.sv \
	$(RTL)/periph/spi_controller.sv

# APB migration PR-1: apb4_register_bank unit-test sources.
# Standalone: axi_pkg (for DW/SW constants) + DUT + TB wrapper.
APB4_REG_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(SOC_DIR)/tb_apb4_register_bank.sv

# APB migration PR-1: axil_to_apb bridge unit-test sources.
# Full AXI→APB path: axi_pkg + bridge + register bank + TB wrapper.
AXIL_TO_APB_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/axil_to_apb.sv \
	$(SOC_DIR)/tb_axil_to_apb.sv

# APB migration PR-7: pll_axil_regs deleted — PLL_REGS_SOURCES now points at
# pll_apb_regs (APB4 slave).  The pll_regs target and pll_regs_lint below are
# redirected to the PR-6 pll_apb_regs target (same functional coverage).
# PLL_REGS_SOURCES kept as an alias so any external callers still compile;
# the canonical source list is PLL_APB_REGS_SOURCES.
PLL_REGS_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/pll/pll_apb_regs.sv \
	$(SOC_DIR)/tb_pll_apb_regs.sv

# APB migration PR-6: standalone pll_apb_regs unit-test sources.
# Minimal: apb4_register_bank (no axi_pkg needed) + pll_apb_regs + standalone TB.
# BFM drives APB4 ports directly; no bus-bridge or full SoC required.
PLL_APB_REGS_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/pll/pll_apb_regs.sv \
	$(SOC_DIR)/tb_pll_apb_regs.sv

# GH #101: standalone pmu unit-test sources.
# Minimal: apb4_register_bank (no axi_pkg needed) + pmu + standalone TB.
# BFM drives APB4 ports directly; no bus-bridge or full SoC required.
PMU_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/pmu.sv \
	$(SOC_DIR)/tb_pmu.sv

# Phase 6a (bead claude_verilog_test-ckc): standalone gpio_controller unit-test sources.
# apb4_register_bank (register file) + cdc_2ff_sync (N_PINS independent single-bit input
# synchronisers, one per pin -- see gpio_controller.sv header) + gpio_controller + standalone TB.
GPIO_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/cdc/cdc_2ff_sync.sv \
	$(RTL)/periph/gpio_controller.sv \
	$(SOC_DIR)/tb_gpio.sv

# Phase 6a-2 (bead claude_verilog_test-f7vs.6): standalone pwm_controller unit-test sources.
# apb4_register_bank (register file) + pwm_controller + standalone TB. Unlike GPIO_SOURCES above,
# there is no cdc_2ff_sync here -- PWM has no async input pins at all (push-pull pwm_o only, no
# oe, no CDC -- docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-2 -- PWM"). pwm_controller.sv does not
# exist yet as of this line's authorship (strict TDD, step 2 of Sec.9's workflow); the pwm/
# pwm_lint targets below are expected to fail to elaborate until it does.
PWM_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/pwm_controller.sv \
	$(SOC_DIR)/tb_pwm.sv

# Phase 6a-3 (bead claude_verilog_test-f7vs.7): standalone watchdog_timer unit-test sources.
# apb4_register_bank (register file) + watchdog_timer + standalone TB. Like PWM there is no
# cdc_2ff_sync here -- the WDT has no async input pins (clk/rst_n/APB4 only; irq_o and
# wdt_rst_req_o are outputs), so no CDC in this module -- docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7
# "6a-3 -- WDT". watchdog_timer.sv does not exist yet as of this line's authorship (strict TDD,
# step 2 of Sec.9's workflow); the wdt/wdt_lint targets below are expected to fail to elaborate
# until it does.
WDT_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/watchdog_timer.sv \
	$(SOC_DIR)/tb_wdt.sv

# Phase 6a-4 (bead claude_verilog_test-f7vs.8): standalone trng unit-test sources.
# apb4_register_bank (register file) + trng + its DEFAULT (LFSR) entropy sub-module + standalone
# TB. trng.sv selects its entropy source with `ifdef TRNG_RO_SKY130 INSIDE the module; this target
# does NOT define that macro, so trng_lfsr_entropy.sv is the arm under test and
# trng_ro_sky130.sv is deliberately absent (it is a Sky130-only analog stub, exempted in
# tools/verif/check_periph_filelists.py's EXEMPT map -- never add it to a file list). No
# cdc_2ff_sync here: the LFSR arm has no asynchronous input (clk/rst_n/APB4 only; irq_o is an
# output) -- docs/PHASE6_IP_EXPANSION_PLAN.md Sec.7 "6a-4 -- TRNG". trng.sv and
# trng_lfsr_entropy.sv do not exist yet as of this line's authorship (strict TDD, step 2 of
# Sec.9's workflow); the trng/trng_lint targets below are expected to fail to elaborate until they
# do.
TRNG_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/trng_lfsr_entropy.sv \
	$(RTL)/periph/trng.sv \
	$(SOC_DIR)/tb_trng.sv

# Phase 6a-5 (bead claude_verilog_test-f7vs.9): standalone i2c_controller unit-test sources.
# apb4_register_bank (register file) + cdc_2ff_sync (i2c_controller instantiates one per pin,
# like gpio_controller) + i2c_bit_engine (protocol core) + i2c_controller + standalone TB. The bus (wired-AND of master, slave and
# pull-up) is modelled by tb/cocotb/bfm/i2c_slave.py, NOT by any RTL file in this list.
# test_i2c.py also re-lints this exact list with `-GCLKDIV_MIN=2` to prove the DUT's elaboration
# guard refuses an unsafe prescaler minimum.
I2C_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/cdc/cdc_2ff_sync.sv \
	$(RTL)/periph/i2c_bit_engine.sv \
	$(RTL)/periph/i2c_controller.sv \
	$(SOC_DIR)/tb_i2c.sv

# Phase 6b (bead claude_verilog_test-f7vs.10): standalone crypto_accel unit-test sources.
# apb4_register_bank (register file; crypto_accel's DOUT / DIGEST / IV3 / STATUS / IRQ_STAT are
# hardware-written bank words, so the bank IS the result storage) + the two sub-cores
# (aes128_core, sha256_core -- listed BEFORE the wrapper that instantiates them, same ordering
# convention as trng_lfsr_entropy before trng and i2c_bit_engine before i2c_controller) +
# crypto_accel + the standalone TB. tb_crypto.sv instantiates FOUR crypto_accel configurations
# side by side (default, SBOX_PARALLEL=4, EN_AES=0, EN_SHA=0) so one simulation build reaches both
# generate arms and both fold factors; test_crypto.py also re-lints this exact list (read back
# through tools/verif/check_source_closure.py's parser, not hand-copied) with -G overrides to
# prove the elaboration guards refuse an illegal SBOX_PARALLEL / ADDR_W / EN_AES=EN_SHA=0.
# NO cdc/cdc_2ff_sync.sv here, deliberately and unlike gpio / i2c: crypto_accel has NO
# asynchronous input at all (clk / rst_n / APB4 in, irq_o out), so there is nothing to
# synchronise, and no SDC set_false_path applies either -- the crypto_accel header says so
# explicitly. Do not "add it for safety": an unused module in the list is dead weight that would
# also hide a genuinely missing one. The three RTL files did not exist when this list was written
# (strict TDD): crypto / crypto_lint are expected to fail to elaborate until the RTL lands.
CRYPTO_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/aes128_core.sv \
	$(RTL)/periph/sha256_core.sv \
	$(RTL)/periph/crypto_accel.sv \
	$(SOC_DIR)/tb_crypto.sv

# Phase 6c (bead claude_verilog_test-f7vs.11): standalone npu_top unit-test sources.
# apb4_register_bank (register file; npu_top's STATUS / AOUT / IRQ_STAT / WADDR are hardware-written
# bank words, so the bank IS the storage -- same pattern as crypto_accel) + the three npu RTL files
# (npu_weight_mem and npu_mac_array listed BEFORE the npu_top that instantiates them, the same
# sub-modules-first convention as CRYPTO_SOURCES) + the standalone TB. tb_npu.sv instantiates TWO
# npu_top configurations side by side (defaults, and EN_NPU=0) so one simulation build reaches both
# generate arms; test_npu.py also re-lints this exact list (read back through
# tools/verif/check_source_closure.py's parser, not hand-copied) with a -G override to prove the
# WEIGHT_WORDS elaboration guard refuses anything but 1024.
# The weight memory is a hard-macro wrapper with a 3-way ifdef (plan Sec.7 "Weight-SRAM
# instantiation"): the SIMULATION build defines neither SRAM_SKY130 nor SRAM_ASAP7 and so takes the
# FreePDK45 `else` arm, which instantiates 4 banks of sram_1rw_256x32_freepdk45 -- that behavioural
# model lives in sim/sram_1rw_256x32_verilator.v (same file SRAM_SIM_MODEL / the SoC lists use) and
# MUST be in this list or Verilator reports a missing module. rv32i_clock_gate is listed because the
# ASAP7 arm instantiates it per bank (en = !csb0); under the default define set that arm is not
# elaborated, so the file is dead weight at sim time but keeps the list a faithful superset of every
# arm and costs nothing (an `ifdef`-pruned module is never an unused-module lint warning).
# NO cdc/cdc_2ff_sync.sv, deliberately: npu_top has NO asynchronous input (clk / rst_n / APB4 in,
# irq_o out), so there is nothing to synchronise -- do not "add it for safety". The three rtl/npu
# files did not exist when this list was written (strict TDD): npu / npu_lint are expected to fail
# to elaborate until the RTL lands. rtl/npu/ must not be created by the verification step because
# tools/verif/check_periph_filelists.py already scans it and would demand five file-list entries.
NPU_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/mem/rv32i_clock_gate.sv \
	$(PROJ_ROOT)/sim/sram_1rw_256x32_verilator.v \
	$(RTL)/npu/npu_weight_mem.sv \
	$(RTL)/npu/npu_mac_array.sv \
	$(RTL)/npu/npu_top.sv \
	$(SOC_DIR)/tb_npu.sv

# Phase 6 groundwork (bead claude_verilog_test-f7vs.4): standalone apb_interconnect
# unit-test sources. apb_interconnect is a single, self-contained combinational module --
# no other RTL package or CDC primitive needed.
APB_INTERCONNECT_SOURCES = \
	$(RTL)/soc/apb_interconnect.sv \
	$(SOC_DIR)/tb_apb_interconnect.sv

# GH #91: standalone async_axi_fifo (dual-clock AXI4 CDC bridge) unit-test
# sources. axi_pkg (bus geometry defaults) + the 3 cdc/ primitives +
# async_axi_fifo + standalone TB wrapper. No bus-bridge or full SoC required.
ASYNC_AXI_FIFO_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/cdc/cdc_2ff_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/cdc/cdc_gray_fifo.sv \
	$(RTL)/soc/async_axi_fifo.sv \
	$(SOC_DIR)/tb_async_axi_fifo.sv

# GH #93: standalone apb_cdc_bridge (APB4 4-phase RZ-handshake CDC bridge --
# converted from 2-phase NRZ toggle by bead claude_verilog_test-rfz,
# 2026-08-12, see rtl/soc/apb_cdc_bridge.sv header) unit-test sources.
# apb_cdc_bridge.sv only depends on the 2 cdc/ reset/sync primitives (no
# axi_pkg, no cdc_gray_fifo -- it crosses single-bit req/ack levels, not
# gray-coded multi-bit pointers) + standalone TB wrapper. No bus-bridge or
# full SoC required.
APB_CDC_BRIDGE_SOURCES = \
	$(RTL)/soc/cdc/cdc_2ff_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/apb_cdc_bridge.sv \
	$(SOC_DIR)/tb_apb_cdc_bridge.sv

# Bead claude_verilog_test-07n: standalone cdc_reset_sync DFT scan-bypass
# mux (scanmode_i / scan_rst_ni) directed unit test. cdc_reset_sync alone +
# standalone TB wrapper -- no cdc_2ff_sync/cdc_gray_fifo dependency, this is
# a single-primitive test, not a CDC bridge test.
CDC_RESET_SYNC_SCAN_SOURCES = \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(SOC_DIR)/tb_cdc_reset_sync_scan.sv

# Full SoC top-level sources for the boot test (M9).
# Order: packages first, leaf RTL, adapters, then soc_top + tb wrapper.
SRAM_SIM_MODEL ?= $(PROJ_ROOT)/sim/sram_1rw_256x32_verilator.v
GPU_SRAM_SIM   ?= $(PROJ_ROOT)/sim/sram_1rw_128x32_asap7.v

# Phase 7 M-c: PLL verification sources.
# Uses tb_soc_pll.sv (exposes pll_locked_o) instead of tb_soc_top.sv.
# PLL_IMPL="STUB" (default in pll_clkgen.sv) keeps this runnable under
# pure Verilator — no real-number model support required.
# pll_rnm.sv is intentionally excluded: the generate/if prunes it in STUB mode.
PLL_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(RTL)/soc/soc_periph_map_pkg.sv \
	$(SRAM_SIM_MODEL) \
	$(RTL)/cpu/core/rv32i_pipeline_pkg.sv \
	$(RTL)/mem/rv32i_cache_pkg.sv \
	$(RTL)/cpu/core/rv32i_alu.sv \
	$(RTL)/cpu/core/rv32i_imm_gen.sv \
	$(RTL)/cpu/core/rv32i_regfile.sv \
	$(RTL)/cpu/core/rv32i_decode.sv \
	$(RTL)/cpu/core/rv32i_branch_comp.sv \
	$(RTL)/cpu/core/rv32i_hazard_unit.sv \
	$(RTL)/cpu/core/rv32i_forwarding_unit.sv \
	$(RTL)/cpu/core/rv32i_csr_file.sv \
	$(RTL)/cpu/core/rv32i_interrupt_ctrl.sv \
	$(RTL)/mem/rv32i_icache.sv \
	$(RTL)/mem/rv32i_dcache.sv \
	$(RTL)/mem/rv32i_cache_arbiter.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_if.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_id.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex1b.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex1c.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex2.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(RTL)/cpu/core/rv32i_core.sv \
	$(RTL)/cpu/rv32i_cpu_top.sv \
	$(RTL)/gpu/gpu_pkg.sv \
	$(GPU_SRAM_SIM) \
	$(RTL)/gpu/vector_register_file.sv \
	$(RTL)/gpu/vector_alu.sv \
	$(RTL)/gpu/gpu_compute_unit.sv \
	$(RTL)/gpu/warp_scheduler.sv \
	$(RTL)/gpu/gpu_command_queue.sv \
	$(RTL)/gpu/gpu_memory_unit.sv \
	$(RTL)/gpu/memory_coalescer.sv \
	$(RTL)/gpu/shared_memory.sv \
	$(RTL)/gpu/gpu_top.sv \
	$(RTL)/periph/uart_controller.sv \
	$(RTL)/periph/spi_controller.sv \
	$(RTL)/periph/timer.sv \
	$(RTL)/periph/interrupt_controller.sv \
	$(RTL)/periph/gpio_controller.sv \
	$(RTL)/periph/pwm_controller.sv \
	$(RTL)/periph/watchdog_timer.sv \
	$(RTL)/periph/trng_lfsr_entropy.sv \
	$(RTL)/periph/trng.sv \
	$(RTL)/periph/i2c_bit_engine.sv \
	$(RTL)/periph/i2c_controller.sv \
	$(RTL)/periph/aes128_core.sv \
	$(RTL)/periph/sha256_core.sv \
	$(RTL)/periph/crypto_accel.sv \
	$(RTL)/npu/npu_mac_array.sv \
	$(RTL)/npu/npu_weight_mem.sv \
	$(RTL)/npu/npu_top.sv \
	$(RTL)/periph/dma_engine.sv \
	$(RTL)/soc/axi4_crossbar.sv \
	$(RTL)/soc/axi_lite_interconnect.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/soc/sram_controller.sv \
	$(RTL)/soc/boot_rom.sv \
	$(RTL)/soc/axi4_to_axilite.sv \
	$(RTL)/soc/axilite_to_axi4.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/axil_to_apb.sv \
	$(RTL)/soc/apb_interconnect.sv \
	$(RTL)/soc/soc_bus.sv \
	$(RTL)/soc/pll/pll_clkgen_stub.sv \
	$(RTL)/soc/pll/pll_apb_regs.sv \
	$(RTL)/soc/pll/pll_clkgen.sv \
	$(RTL)/soc/pll/pll_subsystem.sv \
	$(RTL)/soc/cdc/cdc_2ff_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/cdc/cdc_gray_fifo.sv \
	$(RTL)/soc/async_axi_fifo.sv \
	$(RTL)/soc/apb_cdc_bridge.sv \
	$(RTL)/soc/pmu.sv \
	$(RTL)/soc/soc_top.sv \
	$(SOC_DIR)/tb_soc_pll.sv

SOC_BOOT_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(RTL)/soc/soc_periph_map_pkg.sv \
	$(SRAM_SIM_MODEL) \
	$(RTL)/cpu/core/rv32i_pipeline_pkg.sv \
	$(RTL)/mem/rv32i_cache_pkg.sv \
	$(RTL)/cpu/core/rv32i_alu.sv \
	$(RTL)/cpu/core/rv32i_imm_gen.sv \
	$(RTL)/cpu/core/rv32i_regfile.sv \
	$(RTL)/cpu/core/rv32i_decode.sv \
	$(RTL)/cpu/core/rv32i_branch_comp.sv \
	$(RTL)/cpu/core/rv32i_hazard_unit.sv \
	$(RTL)/cpu/core/rv32i_forwarding_unit.sv \
	$(RTL)/cpu/core/rv32i_csr_file.sv \
	$(RTL)/cpu/core/rv32i_interrupt_ctrl.sv \
	$(RTL)/mem/rv32i_icache.sv \
	$(RTL)/mem/rv32i_dcache.sv \
	$(RTL)/mem/rv32i_cache_arbiter.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_if.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_id.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex1b.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex1c.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex2.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(RTL)/cpu/core/rv32i_core.sv \
	$(RTL)/cpu/rv32i_cpu_top.sv \
	$(RTL)/gpu/gpu_pkg.sv \
	$(GPU_SRAM_SIM) \
	$(RTL)/gpu/vector_register_file.sv \
	$(RTL)/gpu/vector_alu.sv \
	$(RTL)/gpu/gpu_compute_unit.sv \
	$(RTL)/gpu/warp_scheduler.sv \
	$(RTL)/gpu/gpu_command_queue.sv \
	$(RTL)/gpu/gpu_memory_unit.sv \
	$(RTL)/gpu/memory_coalescer.sv \
	$(RTL)/gpu/shared_memory.sv \
	$(RTL)/gpu/gpu_top.sv \
	$(RTL)/periph/uart_controller.sv \
	$(RTL)/periph/spi_controller.sv \
	$(RTL)/periph/timer.sv \
	$(RTL)/periph/interrupt_controller.sv \
	$(RTL)/periph/gpio_controller.sv \
	$(RTL)/periph/pwm_controller.sv \
	$(RTL)/periph/watchdog_timer.sv \
	$(RTL)/periph/trng_lfsr_entropy.sv \
	$(RTL)/periph/trng.sv \
	$(RTL)/periph/i2c_bit_engine.sv \
	$(RTL)/periph/i2c_controller.sv \
	$(RTL)/periph/aes128_core.sv \
	$(RTL)/periph/sha256_core.sv \
	$(RTL)/periph/crypto_accel.sv \
	$(RTL)/npu/npu_mac_array.sv \
	$(RTL)/npu/npu_weight_mem.sv \
	$(RTL)/npu/npu_top.sv \
	$(RTL)/periph/dma_engine.sv \
	$(RTL)/soc/axi4_crossbar.sv \
	$(RTL)/soc/axi_lite_interconnect.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/soc/sram_controller.sv \
	$(RTL)/soc/boot_rom.sv \
	$(RTL)/soc/axi4_to_axilite.sv \
	$(RTL)/soc/axilite_to_axi4.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/axil_to_apb.sv \
	$(RTL)/soc/apb_interconnect.sv \
	$(RTL)/soc/soc_bus.sv \
	$(RTL)/soc/pll/pll_clkgen_stub.sv \
	$(RTL)/soc/pll/pll_apb_regs.sv \
	$(RTL)/soc/pll/pll_clkgen.sv \
	$(RTL)/soc/pll/pll_subsystem.sv \
	$(RTL)/soc/cdc/cdc_2ff_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/cdc/cdc_gray_fifo.sv \
	$(RTL)/soc/async_axi_fifo.sv \
	$(RTL)/soc/apb_cdc_bridge.sv \
	$(RTL)/soc/pmu.sv \
	$(RTL)/soc/soc_top.sv \
	$(SOC_DIR)/tb_soc_top.sv

VERILOG_SOURCES = $(XBAR_SOURCES)

ifeq ($(SIM),verilator)
	COMPILE_ARGS += -Wno-fatal
	COMPILE_ARGS += -Wno-WIDTH
	COMPILE_ARGS += -Wno-CASEINCOMPLETE
	COMPILE_ARGS += -Wno-TIMESCALEMOD
	COMPILE_ARGS += -Wno-UNOPTFLAT
	# bead claude_verilog_test-rvs: gates rtl/soc/cdc/cdc_2ff_sync.sv's
	# optional simulation-only randomised-delay CDC injector (RAND_CDC_DELAY_EN,
	# default OFF at every instantiation site — this define alone changes
	# nothing observable). Never defined for sim/Makefile's lint_soc or the
	# tools/cdc/ sv2v+yosys CDC-gate flow, so the synthesis/lint/CDC-gate
	# paths stay bit-identical; only actual cocotb simulation runs (this
	# Makefile) can see the injector at all, and only instances that
	# explicitly override RAND_CDC_DELAY_EN=1 activate it.
	COMPILE_ARGS += +define+SIMULATION
	COMPILE_ARGS += --timescale 1ns/1ps
	COMPILE_ARGS += --public-flat-rw
	COMPILE_ARGS += --no-timing
# GH #216 / bead nkj7: opt-in line + toggle coverage.  `make soc_coverage` (below) runs the whole
# soc_all_ci regression with COVERAGE=1; nothing here changes an ordinary (uninstrumented) run.
#  * The flags go in COMPILE_ARGS, not EXTRA_ARGS: most targets pass EXTRA_ARGS= on the command
#    line, which would override a makefile-level `+=`; none pass COMPILE_ARGS=.
#  * COV_SFX is appended to EVERY SIM_BUILD (the generic one and the hardcoded per-variant ones),
#    so an instrumented build can never reuse an uninstrumented Vtop (or vice versa) -- the same
#    stale-Vtop false-pass class as PR #142.
#  * Each simulation writes its own .dat through the runtime plusarg +verilator+coverage+file+,
#    which cocotb 1.9.2's verilator.cpp honours when it calls VerilatedCov::write().  The name
#    carries MODULE as well as SIM_BUILD because soc_integration_batch shares one SIM_BUILD
#    across four MODULEs.
#  * --coverage-max-width 256 keeps wide datapath arrays (the DMA's 8192-bit linebuf, SRAM model
#    arrays) out of toggle coverage, where they would only add noise and memory.
ifdef COVERAGE
	COV_SFX := _cov
	# Verilator will not create the directory itself; make a direct `make gpio COVERAGE=1` work too.
	COV_MKDIR := $(shell mkdir -p $(COV_DIR))
	COMPILE_ARGS += --coverage-line --coverage-toggle --coverage-max-width 256
	override PLUSARGS += +verilator+coverage+file+$(COV_DIR)/$(notdir $(SIM_BUILD))__$(MODULE).dat
endif
	# Override PYTHON3: nix verilator hardcodes nix Python 3.11 but PYTHONHOME=/usr
	# points to Python 3.10 stdlib — mismatch crashes verilator_includer.
	#
	# SIM_PYTHON3 is overridable because the right answer is environment-specific.
	# Locally /usr/bin/python3 IS the interpreter cocotb runs on, so it is the
	# default. On a GitHub runner, actions/setup-python puts a hostedtoolcache
	# interpreter on PATH and points PYTHONHOME/LD_LIBRARY_PATH at it, while
	# /usr/bin/python3 is Ubuntu's own (different minor version) — verilator_includer
	# then loads the wrong stdlib and dies with
	#   Fatal Python error: init_fs_encoding: failed to get the Python codec of the
	#   filesystem encoding / ModuleNotFoundError: No module named 'encodings'
	# CI therefore passes SIM_PYTHON3=$(command -v python3) so the compile-time
	# interpreter matches the one cocotb itself runs on.
	SIM_PYTHON3 ?= /usr/bin/python3
	BUILD_ARGS += PYTHON3=$(SIM_PYTHON3)
	# Override CXX/LINK: nix verilator generates clang++ commands but only g++
	# is available outside nix's clang environment.  cxx_shim.sh wraps g++ and
	# strips clang-only flags.
	BUILD_ARGS += CXX=$(SIM_DIR)/cxx_shim.sh
	BUILD_ARGS += LINK=$(SIM_DIR)/cxx_shim.sh
	# -O0 compile: Vtop__Syms.cpp (809 KB, thousands of scope initialisers) takes
	# 30+ min at default -Os on this host via cxx_shim; -O0 reduces it to seconds.
	# Functional regression only — short integration test runtime overhead is negligible.
	BUILD_ARGS += OPT_FAST=-O0
	BUILD_ARGS += OPT_SLOW=-O0
# Bead claude_verilog_test-7je: give every target its OWN build dir.
# Verilator always names the binary Vtop regardless of TOPLEVEL, so a single
# shared sim_build/ meant `make timer` straight after `make async_axi_fifo`
# silently reused the previous suite's Vtop and died with
#   VPI: Couldn't find root handle timer / Toplevel instances: timer != tb_async_axi_fifo
# BUILD_ARGS is recursively expanded (only ever `+=`, never `:=`), so `$@`
# resolves at recipe time to the target being built.  soc_all's per-suite
# `rm -rf sim_build` and the per-target `$(MAKE) clean` calls that used to
# paper over this are removed -- the dirs no longer collide.
# The build dir must also distinguish BUILD VARIANTS of the same target, not
# just different targets. soc_all runs `sram_controller` twice -- once default,
# once SRAM_TARGET=sky130 -- and that switch changes the source list
# (SRAM_CTRL_SIM_MODEL), a define (SRAM_SKY130) and a parameter
# (MEM_WORDS 4096 -> 1024). Same $@, so without the suffix below both land in
# sim_build_sram_controller and the second run silently REUSES the first's
# Vtop: measured MEM_WORDS=0x1000 and zero sky130 references in the binary
# while the suite still reported 11/11 PASS. That is a false pass, strictly
# worse than the VPI crash this bead started from, and it is only invisible
# because TOPLEVEL happens to match. (Caught in review of PR #142.)
BUILD_ARGS += SIM_BUILD=$(SIM_BUILD_ROOT)/sim_build_$@$(if $(filter-out freepdk45,$(SRAM_TARGET)),_$(SRAM_TARGET))$(COV_SFX)
ifneq ($(wildcard /nix/store),)
	# Nix environment: nix ld.so cannot find system libs when cocotb dlopen's
	# libpython3.10.so.1.0.  Create a compat dir with symlinks to system libs.
	NIX_COMPAT_DIR := /tmp/cocotb_nix_compat
	# `ldconfig` inside `nix develop` resolves to the nix-store glibc binary, whose
	# ld.so.cache is empty/unreadable — the probe then returns nothing and the compat
	# dir is silently left empty.  Prefer the system /sbin/ldconfig, and fall back to
	# a direct lookup in the usual multiarch dirs if that is unavailable too.
	#
	# libssl/libcrypto (bead npz): cocotb.regression installs pytest's assertion
	# rewrite hook, which imports anyio -> ssl -> libssl.so.3.  Without these two
	# the hook raises ImportError and every run prints an ERROR + ~30-line
	# traceback before the tests (which are unaffected) proceed with assertion
	# rewriting silently disabled.  Note the failure is inside the SIMULATOR
	# process, not the shell: plain `nix develop --command python3 -c 'import ssl'`
	# succeeds, which is why this looked like a nix-shell problem and was not.
	SIM_CMD_PREFIX := mkdir -p $(NIX_COMPAT_DIR) && \
	  for _lib in libexpat.so.1 libz.so.1 libbz2.so.1.0 liblzma.so.5 libffi.so.8 \
	              libssl.so.3 libcrypto.so.3; do \
	    _src=$$(PATH=/sbin:/usr/sbin:$$PATH ldconfig -p 2>/dev/null | grep "^	$$_lib " | awk '{print $$NF}' | head -1); \
	    if [ -z "$$_src" ]; then \
	      for _d in /usr/lib/x86_64-linux-gnu /lib/x86_64-linux-gnu /usr/lib64 /usr/lib; do \
	        if [ -e "$$_d/$$_lib" ]; then _src="$$_d/$$_lib"; break; fi; \
	      done; \
	    fi; \
	    [ -n "$$_src" ] && ln -sf "$$_src" $(NIX_COMPAT_DIR)/$$_lib 2>/dev/null || true; \
	  done && \
	  export LD_LIBRARY_PATH=$(NIX_COMPAT_DIR):$${LD_LIBRARY_PATH} &&
endif
endif

MODULE   ?= test_crossbar
TOPLEVEL ?= tb_axi4_crossbar

# Suppress reduced-log noise to keep output readable.
export COCOTB_REDUCED_LOG_FMT=1

include $(shell cocotb-config --makefiles)/Makefile.sim

# Bead p6t8 -- make a failing cocotb suite actually fail the make.
#
# cocotb 1.9.2's own makefile cannot propagate a test failure as an exit code.  Its
# Makefile.inc (cocotb/share/makefiles/Makefile.inc:88-90) says so in as many words:
#     # Check that the COCOTB_RESULTS_FILE was created, since we can't set an exit code
#     # from cocotb.
#     define check_for_results_file
#         @test -f $(COCOTB_RESULTS_FILE) || (echo "ERROR: ... was not written ..." && exit 1)
#     endef
# It asserts the file EXISTS, never that it holds no failures, and `$(call
# check_for_results_file)` is the last line of the $(COCOTB_RESULTS_FILE) recipe in every
# simulator makefile (Makefile.verilator:76 for us).  Measured: a forced failure gave
# TESTS=9 PASS=0 FAIL=8, a results.xml with 8 <failure> elements, and sub-make exit 0.
#
# The fix is a redefinition HERE, after the include above.  Make expands recipe lines when
# the rule RUNS, not when the file is parsed, so a definition that appears later in the
# makefile still reaches every target, every simulator and every build point, with no edit
# to the ~35 recipes below.  The macro runs at the end of each build point's own recipe, so
# build points overwriting a shared results.xml does not matter: each is checked before the
# next one starts.
#
# This is what makes the `set -e` in the multi-build-point recipes (register_bank,
# apb4_register_bank, the apb_interconnect sweep) FUNCTION -- until now a failing point was
# masked by a later passing one and only the CI PASS_FLOOR log-grep noticed, indirectly.
#
# The verdict comes from tools/verif/check_cocotb_results.py, which reuses
# tools/eda/summarize.py's tested parser (failure / error / no-passing-test / unparsable
# all count as not clean), deliberately not a grep for "<failure".  The original existence
# check is kept so a missing file still gets cocotb's own message first.
# `check-exit-propagation` below is the self-test that proves this stays wired.
define check_for_results_file
    @test -f $(COCOTB_RESULTS_FILE) || (echo "ERROR: $(COCOTB_RESULTS_FILE) was not written by the simulation!" >&2 && exit 1)
    @$(or $(SIM_PYTHON3),python3) $(PROJ_ROOT)/tools/verif/check_cocotb_results.py $(COCOTB_RESULTS_FILE) || (echo "ERROR: cocotb recorded failures (bead p6t8: cocotb itself cannot set an exit code)" >&2 && exit 1)
endef

.PHONY: axi4_to_axilite axilite_to_axi4 boot_rom crossbar register_bank axil_interconnect axil_apb_fabric axil_apb_fabric_lint sram_controller dma dma_lint timer timer_lint irq irq_lint uart uart_lint spi spi_lint soc_boot soc_periph soc_coherency soc_cpu_gpu soc_stress soc_pll soc_pll_lint soc_all soc_all_ci verilator_lint soc_boot_lint l2_bench l2_bench_lint apb4_register_bank apb4_register_bank_lint axil_to_apb axil_to_apb_lint pmu pmu_lint async_axi_fifo async_axi_fifo_lint soc_multiclock soc_multiclock_reset soc_pll_multiclock apb_cdc_bridge apb_cdc_bridge_lint soc_pmu_multiclock soc_integration cdc_reset_sync_scan cdc_reset_sync_scan_lint gpio gpio_lint soc_gpio gpio_driver apb_interconnect apb_interconnect_lint pwm pwm_lint soc_pwm wdt wdt_lint soc_wdt trng trng_lint soc_trng i2c i2c_lint soc_i2c crypto crypto_lint soc_crypto npu npu_lint soc_npu check-exit-propagation
crossbar:
	$(MAKE) MODULE=test_crossbar,test_crossbar_errors TOPLEVEL=tb_axi4_crossbar \
		$(BUILD_ARGS)

# Two build points (bead r5hu): the default ADDR_W=12, and ADDR_W=5 where WORDW=3 and
# N_REGS(8) == 2**WORDW -- the case a truncating `WORDW'(N_REGS)` cast wraps to 0.  ADDR_W is an
# elaboration parameter, so the second point is its own Verilator build in its OWN SIM_BUILD
# (reusing one dir across parameter values is the stale-Vtop hazard; test_register_bank.py also
# checks the elaborated address-bus width against REGBANK_ADDR_W).  $(BUILD_ARGS) is kept for
# the nix CXX shim / -O0 flags; its SIM_BUILD is overridden by the later, explicit one (the last
# command-line assignment wins).  `set -e` + trailing `\` so either point failing aborts the target.
register_bank:
	@set -e; \
	echo "=== register_bank: ADDR_W=12 (default) ==="; \
	REGBANK_ADDR_W=12 \
	$(MAKE) MODULE=test_register_bank TOPLEVEL=tb_axi_lite_register_bank \
		VERILOG_SOURCES="$(REGBANK_SOURCES)" \
		$(BUILD_ARGS); \
	echo "=== register_bank: ADDR_W=5 (N_REGS == 2**WORDW) ==="; \
	REGBANK_ADDR_W=5 \
	$(MAKE) MODULE=test_register_bank TOPLEVEL=tb_axi_lite_register_bank \
		VERILOG_SOURCES="$(REGBANK_SOURCES)" \
		EXTRA_ARGS="-GADDR_W=5" \
		$(BUILD_ARGS) \
		SIM_BUILD=$(SIM_BUILD_ROOT)/sim_build_register_bank_aw5$(COV_SFX) \
		sim

axil_interconnect:
	$(MAKE) MODULE=test_axil_interconnect TOPLEVEL=tb_axi_lite_interconnect \
		VERILOG_SOURCES="$(AXIL_SOURCES)" \
		$(BUILD_ARGS)

# Bead 8riq: fabric chain with stalls / SLVERR / DECERR.  -Wno-SYNCASYNCNET kept for consistency
# with the other SoC-level targets; the wrapper has no async paths of its own.
axil_apb_fabric_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_axil_apb_fabric $(AXIL_APB_FABRIC_SOURCES)

axil_apb_fabric: axil_apb_fabric_lint
	$(MAKE) MODULE=test_axil_apb_fabric TOPLEVEL=tb_axil_apb_fabric \
		VERILOG_SOURCES="$(AXIL_APB_FABRIC_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

verilator_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		$(if $(filter sky130,$(SRAM_TARGET)),+define+SRAM_SKY130 -GMEM_WORDS=1024) \
		--top-module sram_controller $(SRAM_SOURCES)

# GH #104 verification finding: sram_controller's MEM_WORDS parameter
# defaults to 4096 (16 KB flat-array window); the sky130_sram_4kbyte macro is
# hardwired to 1024 words (10-bit addr0/addr1). Without overriding MEM_WORDS
# here, SRAM_SKY130 elaborates with a 12-bit word_index() truncated onto the
# macro's 10-bit address ports (WIDTHTRUNC) -- a silent address-aliasing bug
# in the *test build*, not caught by the RTL's own MEM_WORDS!=1024 check
# (that check is a runtime `initial $error`, which neither Verilator
# `--lint-only` nor a live cocotb run treats as fatal). -GMEM_WORDS=1024
# matches the macro geometry the RTL comment (sram_controller.sv line ~52)
# already documents as mandatory under SRAM_SKY130.
sram_controller: verilator_lint
	$(MAKE) MODULE=test_sram_controller TOPLEVEL=sram_controller \
		VERILOG_SOURCES="$(SRAM_SOURCES)" \
		EXTRA_ARGS="$(if $(filter sky130,$(SRAM_TARGET)),-GMEM_WORDS=1024)" \
		$(BUILD_ARGS)

# Bead ej6j.  boot_rom runs as two build points: the default (empty MEM_INIT_FILE -> zero-fill arm)
# and one with MEM_INIT_FILE set to a hex image (the $$readmemh arm no other suite takes -- they all
# backdoor-load).  The parameter is an elaboration parameter, so the second point is its own
# Verilator build in its OWN SIM_BUILD (the stale-Vtop hazard documented above).
axi4_to_axilite:
	$(MAKE) MODULE=test_axi4_to_axilite TOPLEVEL=axi4_to_axilite \
		VERILOG_SOURCES="$(A2L_SOURCES)" \
		$(BUILD_ARGS)

axilite_to_axi4:
	$(MAKE) MODULE=test_axilite_to_axi4 TOPLEVEL=axilite_to_axi4 \
		VERILOG_SOURCES="$(L2A_SOURCES)" \
		$(BUILD_ARGS)

boot_rom:
	@set -e; \
	echo "=== boot_rom: MEM_INIT_FILE empty (default) ==="; \
	$(MAKE) MODULE=test_boot_rom TOPLEVEL=boot_rom \
		VERILOG_SOURCES="$(BOOTROM_SOURCES)" \
		$(BUILD_ARGS); \
	echo "=== boot_rom: MEM_INIT_FILE=boot_rom_init.hex ==="; \
	$(MAKE) MODULE=test_boot_rom_init TOPLEVEL=boot_rom \
		VERILOG_SOURCES="$(BOOTROM_SOURCES)" \
		EXTRA_ARGS='-GMEM_INIT_FILE=\"$(SOC_DIR)/boot_rom_init.hex\"' \
		$(BUILD_ARGS) \
		SIM_BUILD=$(SIM_BUILD_ROOT)/sim_build_boot_rom_init$(COV_SFX) \
		sim

dma_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module dma_engine $(DMA_SOURCES)

dma: dma_lint
	$(MAKE) MODULE=test_dma TOPLEVEL=dma_engine \
		VERILOG_SOURCES="$(DMA_SOURCES)" \
		$(BUILD_ARGS)

timer_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module timer $(TIMER_SOURCES)

timer: timer_lint
	$(MAKE) MODULE=test_timer TOPLEVEL=timer \
		VERILOG_SOURCES="$(TIMER_SOURCES)" \
		$(BUILD_ARGS)

irq_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module interrupt_controller $(IRQ_SOURCES)

irq: irq_lint
	$(MAKE) MODULE=test_irq_ctrl TOPLEVEL=interrupt_controller \
		VERILOG_SOURCES="$(IRQ_SOURCES)" \
		$(BUILD_ARGS)

uart_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module uart_controller $(UART_SOURCES)

uart: uart_lint
	$(MAKE) MODULE=test_uart TOPLEVEL=uart_controller \
		VERILOG_SOURCES="$(UART_SOURCES)" \
		$(BUILD_ARGS)

# -Wno-SYNCASYNCNET: spi_controller's own flops are synchronous-reset while the
# cdc_2ff_sync on spi_miso_i (bead a2g) asserts reset asynchronously, so rst_n
# reaches both styles.  With spi_controller as the lint ROOT there is no logic
# between the port and the two usages, so Verilator flags the mix; the same
# rst_n / cdc_2ff_sync pattern raises nothing at soc_top scope.  Every SoC-level
# target in this file already carries this flag for the same reason.
spi_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module spi_controller $(SPI_SOURCES)

spi: spi_lint
	$(MAKE) MODULE=test_spi TOPLEVEL=spi_controller \
		VERILOG_SOURCES="$(SPI_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# APB migration PR-1: apb4_register_bank lint + sim.
apb4_register_bank_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_apb4_register_bank $(APB4_REG_SOURCES)

# Two build points (bead r5hu); same scheme as register_bank above.  The ADDR_W=5 point is the
# POSITIVE CONTROL for the axi_lite_register_bank truncating-cast defect: this module already
# zero-extends the address (GH #87), so its boundary test must pass.
apb4_register_bank: apb4_register_bank_lint
	@set -e; \
	echo "=== apb4_register_bank: ADDR_W=12 (default) ==="; \
	REGBANK_ADDR_W=12 \
	$(MAKE) MODULE=test_apb4_register_bank TOPLEVEL=tb_apb4_register_bank \
		VERILOG_SOURCES="$(APB4_REG_SOURCES)" \
		$(BUILD_ARGS); \
	echo "=== apb4_register_bank: ADDR_W=5 (N_REGS == 2**WORDW) ==="; \
	REGBANK_ADDR_W=5 \
	$(MAKE) MODULE=test_apb4_register_bank TOPLEVEL=tb_apb4_register_bank \
		VERILOG_SOURCES="$(APB4_REG_SOURCES)" \
		EXTRA_ARGS="-GADDR_W=5" \
		$(BUILD_ARGS) \
		SIM_BUILD=$(SIM_BUILD_ROOT)/sim_build_apb4_register_bank_aw5$(COV_SFX) \
		sim

# APB migration PR-1: axil_to_apb bridge lint + sim.
# clean first: bridge TB uses the same Vtop binary name as other targets.
axil_to_apb_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_axil_to_apb $(AXIL_TO_APB_SOURCES)

axil_to_apb: axil_to_apb_lint
	$(MAKE) MODULE=test_axil_to_apb TOPLEVEL=tb_axil_to_apb \
		VERILOG_SOURCES="$(AXIL_TO_APB_SOURCES)" \
		$(BUILD_ARGS)

# Phase 7 M-c: PLL lint gates.
# soc_pll_lint: lints tb_soc_pll (full SoC, used by test_pll_lock).
# pll_regs_lint: APB migration PR-7 — pll_axil_regs deleted; redirected to
#   lint tb_pll_apb_regs (APB4 slave, same functional coverage as original).
soc_pll_lint:
	verilator --lint-only -Wall -Wno-fatal -Wno-IMPORTSTAR \
		-Wno-UNUSEDSIGNAL -Wno-UNOPTFLAT -Wno-SYNCASYNCNET \
		-Wno-DECLFILENAME -Wno-UNUSEDPARAM -Wno-BLKSEQ \
		-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		--top-module tb_soc_pll \
		$(PLL_SOURCES)

pll_regs_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_pll_apb_regs \
		$(PLL_APB_REGS_SOURCES)

# Phase 7 M-c / APB migration PR-7: SoC PLL simulation targets.
# test_pll_lock (3 tests): uses full SoC tb_soc_pll — verifies PLL lock
#   signal propagation and pll_locked_o port.
# pll_regs: APB migration PR-7 — pll_axil_regs deleted; pll_regs is now an
#   alias for pll_apb_regs (4 tests, tb_pll_apb_regs, APB4 slave).
#   The original test_pll_regs (AXI-Lite) is superseded by test_pll_apb_regs.
pll_regs: pll_regs_lint
	$(MAKE) pll_apb_regs

# APB migration PR-6: pll_apb_regs lint + sim.
# lint only: apb4_register_bank + pll_apb_regs + standalone TB wrapper.
pll_apb_regs_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_pll_apb_regs \
		$(PLL_APB_REGS_SOURCES)

pll_apb_regs: pll_apb_regs_lint
	$(MAKE) MODULE=test_pll_apb_regs TOPLEVEL=tb_pll_apb_regs \
		VERILOG_SOURCES="$(PLL_APB_REGS_SOURCES)" \
		$(BUILD_ARGS)

# GH #101: pmu lint + sim.
# lint only: apb4_register_bank + pmu + standalone TB wrapper.
pmu_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_pmu \
		$(PMU_SOURCES)

pmu: pmu_lint
	$(MAKE) MODULE=test_pmu TOPLEVEL=tb_pmu \
		VERILOG_SOURCES="$(PMU_SOURCES)" \
		$(BUILD_ARGS)

# Phase 6a (bead claude_verilog_test-ckc): gpio_controller lint + sim.
# lint only: apb4_register_bank + cdc_2ff_sync + gpio_controller + standalone TB wrapper.
# -Wno-SYNCASYNCNET: same rationale as spi_lint above -- cdc_2ff_sync's own flops are
# asynchronous-reset while gpio_controller's are synchronous-reset, and both are flopped off the
# same rst_n at this lint ROOT (gpio_controller instantiates cdc_2ff_sync directly).
gpio_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_gpio \
		$(GPIO_SOURCES)

gpio: gpio_lint
	$(MAKE) MODULE=test_gpio TOPLEVEL=tb_gpio \
		VERILOG_SOURCES="$(GPIO_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6a-2 (bead claude_verilog_test-f7vs.6): pwm_controller lint + sim.
# lint only: apb4_register_bank + pwm_controller + standalone TB wrapper.
# -Wno-SYNCASYNCNET: matches the gpio targets' convention above, for consistency with the rest of
# this file's per-target EXTRA_ARGS, even though PWM has no cdc_2ff_sync / async input of its own.
pwm_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_pwm \
		$(PWM_SOURCES)

pwm: pwm_lint
	$(MAKE) MODULE=test_pwm TOPLEVEL=tb_pwm \
		VERILOG_SOURCES="$(PWM_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6a-3 (bead claude_verilog_test-f7vs.7): watchdog_timer lint + sim.
# lint only: apb4_register_bank + watchdog_timer + standalone TB wrapper.
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm targets above.
wdt_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_wdt \
		$(WDT_SOURCES)

wdt: wdt_lint
	$(MAKE) MODULE=test_wdt TOPLEVEL=tb_wdt \
		VERILOG_SOURCES="$(WDT_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6a-4 (bead claude_verilog_test-f7vs.8): trng lint + sim.
# lint only: apb4_register_bank + trng_lfsr_entropy + trng + standalone TB wrapper.
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm/wdt targets above.
trng_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_trng \
		$(TRNG_SOURCES)

trng: trng_lint
	$(MAKE) MODULE=test_trng TOPLEVEL=tb_trng \
		VERILOG_SOURCES="$(TRNG_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6a-5 (bead claude_verilog_test-f7vs.9): i2c_controller lint + sim (L1 protocol suite).
# lint only: apb4_register_bank + cdc_2ff_sync + i2c_controller + standalone TB wrapper.
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm/wdt/trng targets above (the
# async pad inputs feed cdc_2ff_sync flops).
i2c_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_i2c \
		$(I2C_SOURCES)

i2c: i2c_lint
	$(MAKE) MODULE=test_i2c TOPLEVEL=tb_i2c \
		VERILOG_SOURCES="$(I2C_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6b (bead claude_verilog_test-f7vs.10): crypto_accel lint + sim (L1 AES / SHA suite).
# lint only: apb4_register_bank + aes128_core + sha256_core + crypto_accel + standalone TB wrapper
# (which holds all four configurations, so this lint also covers EN_AES=0 / EN_SHA=0 /
# SBOX_PARALLEL=4). Contract: 0 errors, 0 warnings.
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm/wdt/trng/i2c targets above, kept
# for consistency although crypto_accel has no asynchronous input to trip it.
crypto_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_crypto \
		$(CRYPTO_SOURCES)

crypto: crypto_lint
	$(MAKE) MODULE=test_crypto TOPLEVEL=tb_crypto \
		VERILOG_SOURCES="$(CRYPTO_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6c (bead claude_verilog_test-f7vs.11): npu_top lint + sim (L1 INT8 NPU suite).
# lint only: apb4_register_bank + the weight-SRAM behavioural model + the three npu RTL files +
# standalone TB wrapper (which holds both configurations, so this lint also covers EN_NPU=0).
# Contract: 0 errors, 0 warnings.  Default define set => the FreePDK45 SRAM arm (see NPU_SOURCES).
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm/wdt/trng/i2c/crypto targets above,
# kept for consistency although npu_top has no asynchronous input to trip it.
# -Wno-DECLFILENAME: sim/sram_1rw_256x32_verilator.v defines module sram_1rw_256x32_freepdk45, so
# `-Wall` reports DECLFILENAME on a file this target does not own (measured, Verilator 5.048);
# soc_boot_lint disables it for the same file. Every npu RTL file is named after its module, so
# nothing of ours is hidden by it. test_npu.py's single-instance lint passes the same flag.
# RED until the RTL lands: with rtl/npu/ absent both targets stop at "Cannot find file".
npu_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET -Wno-DECLFILENAME \
		--top-module tb_npu \
		$(NPU_SOURCES)

npu: npu_lint
	$(MAKE) MODULE=test_npu TOPLEVEL=tb_npu \
		VERILOG_SOURCES="$(NPU_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6 groundwork (bead claude_verilog_test-f7vs.4): apb_interconnect lint + sim.
# lint only: apb_interconnect + standalone TB wrapper, at the wrapper's default N_SLAVES.
# -Wno-SYNCASYNCNET: matches the gpio/spi targets' convention above, even though this DUT has
# no clock/reset of its own to trip it -- kept for consistency with the rest of this file's
# per-target EXTRA_ARGS.
apb_interconnect_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_apb_interconnect \
		$(APB_INTERCONNECT_SOURCES)

# apb_interconnect is a real N_SLAVES sweep, not a single build+run like every other target in
# this file: N_SLAVES is a SystemVerilog elaboration-time parameter (it changes SEL_W/IDXW and
# the generated decode-window array sizes -- see tb_apb_interconnect.sv), so Verilator must
# re-elaborate the whole design once per value; a single cocotb process cannot change it at
# runtime. Each point gets ITS OWN SIM_BUILD directory -- reusing one across different N_SLAVES
# values is exactly the stale-Verilator-cache / corrupt-Vtop hazard this phase's groundwork
# (bead f7vs.3) exists to avoid (docs/PHASE6_IP_EXPANSION_PLAN.md Sec.10 "Operational hazards").
# test_apb_interconnect.py reads back which N_SLAVES / OVERLAP_TEST this build used via the
# APB_IC_N_SLAVES / APB_IC_OVERLAP environment variables set below, so the same test module
# runs unmodified at every sweep point plus the dedicated first-match-wins overlap build.
# `set -e` (in a single multi-line shell recipe, note the trailing `\` continuations) so a
# failure at any sweep point aborts the target with a non-zero exit instead of being masked by
# a later point's success.
apb_interconnect: apb_interconnect_lint
	@set -e; \
	for n in 1 2 7 8 9 13 14 15 16 17; do \
		echo "=== apb_interconnect sweep: N_SLAVES=$$n ==="; \
		APB_IC_N_SLAVES=$$n APB_IC_OVERLAP=0 \
		$(MAKE) MODULE=test_apb_interconnect TOPLEVEL=tb_apb_interconnect \
			VERILOG_SOURCES="$(APB_INTERCONNECT_SOURCES)" \
			EXTRA_ARGS="-Wno-SYNCASYNCNET -GN_SLAVES=$$n" \
			SIM_BUILD=$(SIM_BUILD_ROOT)/sim_build_apb_interconnect_n$${n}$(COV_SFX) \
			sim; \
	done; \
	echo "=== apb_interconnect overlap test: N_SLAVES=2 OVERLAP_TEST=1 ==="; \
	APB_IC_N_SLAVES=2 APB_IC_OVERLAP=1 \
	$(MAKE) MODULE=test_apb_interconnect TOPLEVEL=tb_apb_interconnect \
		VERILOG_SOURCES="$(APB_INTERCONNECT_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET -GN_SLAVES=2 -GOVERLAP_TEST=1" \
		SIM_BUILD=$(SIM_BUILD_ROOT)/sim_build_apb_interconnect_overlap$(COV_SFX) \
		sim

# GH #91: async_axi_fifo lint + sim.
# lint only: axi_pkg + 3 cdc/ primitives + async_axi_fifo + standalone TB wrapper.
async_axi_fifo_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_async_axi_fifo \
		$(ASYNC_AXI_FIFO_SOURCES)

async_axi_fifo: async_axi_fifo_lint
	$(MAKE) MODULE=test_async_axi_fifo TOPLEVEL=tb_async_axi_fifo \
		VERILOG_SOURCES="$(ASYNC_AXI_FIFO_SOURCES)" \
		$(BUILD_ARGS)

# GH #93: apb_cdc_bridge lint + sim.
# lint only: 2 cdc/ primitives + apb_cdc_bridge + standalone TB wrapper.
apb_cdc_bridge_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_apb_cdc_bridge \
		$(APB_CDC_BRIDGE_SOURCES)

apb_cdc_bridge: apb_cdc_bridge_lint
	$(MAKE) MODULE=test_apb_cdc_bridge TOPLEVEL=tb_apb_cdc_bridge \
		VERILOG_SOURCES="$(APB_CDC_BRIDGE_SOURCES)" \
		$(BUILD_ARGS)

# Bead claude_verilog_test-07n: cdc_reset_sync DFT scan-bypass lint + sim.
# lint only: cdc_reset_sync + standalone TB wrapper.
cdc_reset_sync_scan_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_cdc_reset_sync_scan \
		$(CDC_RESET_SYNC_SCAN_SOURCES)

cdc_reset_sync_scan: cdc_reset_sync_scan_lint
	$(MAKE) MODULE=test_cdc_reset_sync_scan TOPLEVEL=tb_cdc_reset_sync_scan \
		VERILOG_SOURCES="$(CDC_RESET_SYNC_SCAN_SOURCES)" \
		$(BUILD_ARGS)

soc_pll: soc_pll_lint
	$(MAKE) MODULE=test_pll_lock TOPLEVEL=tb_soc_pll \
		VERILOG_SOURCES="$(PLL_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) pll_apb_regs

# GH #93 multiclock APB_PLL2 / apb_cdc_bridge exercise (bonus item 4 of the
# GH #93 multiclock verification task — see test_soc_multiclock_pll2.py's
# module docstring for why this is a separate DUT/target from
# soc_multiclock). Reuses pll2_fw/pll2_decode.hex — no new firmware.
#
soc_pll_multiclock: soc_pll_lint
	$(MAKE) MODULE=test_soc_multiclock_pll2 TOPLEVEL=tb_soc_pll \
		VERILOG_SOURCES="$(PLL_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

soc_boot_lint:
	verilator --lint-only -Wall -Wno-fatal -Wno-IMPORTSTAR \
		-Wno-UNUSEDSIGNAL -Wno-UNOPTFLAT -Wno-SYNCASYNCNET \
		-Wno-DECLFILENAME -Wno-UNUSEDPARAM -Wno-BLKSEQ \
		-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		--top-module tb_soc_top \
		$(SOC_BOOT_SOURCES)

# M9 SoC boot test — 3 tests: PC scoreboard, SRAM sentinels, 100/100 stability.
# fr_null_20260603_052800_00 (CPU RESET_PC) fixed by rtl-design-orchestrator 2026-06-03.
soc_boot: soc_boot_lint
	$(MAKE) MODULE=test_boot TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M9 SoC DMA + peripheral loopback test — self-checking firmware drives DMA
# mem->mem + UART/SPI internal loopback via CPU MMIO; scoreboards PASS_PC/FAIL_PC.
soc_periph: soc_boot_lint
	$(MAKE) MODULE=test_periph_loopback TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Diagnostic boot test — dumps fetch-path signals for 300 cycles.
.PHONY: soc_boot_diag
soc_boot_diag:
	$(MAKE) MODULE=test_boot_diag TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET"

# M9 software-managed coherency test — CPU flush+GPU launch+CPU inval end-to-end.
# Verifies CSRW 0x7C0 (dcache_flush) and CSRW 0x7C1 (dcache_inval) under real
# GPU kernel execution (bead claude_verilog_test-777).
# Firmware: coherency_fw/coherency_fw.hex (generated by gen_coherency_hex.py).
# Tests: test_coherency_pass (positive), test_coherency_no_flush (negative),
#        test_coherency_no_inval (negative/warn if dst lines cold).
soc_coherency: soc_boot_lint
	$(MAKE) MODULE=test_soc_coherency TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M9 CPU-GPU interrupt integration test (bead claude_verilog_test-ov2).
# IRQ-driven counterpart to soc_coherency: CPU enables GPU IRQ via
# interrupt_controller (IRQ_MASK bit 4), launches kernel, waits in a bounded
# spin loop until the ISR fires (mtvec trap → ISR clears IRQ + sets flag +
# MRET), then reads corrected dst words and verifies src+1.
# Tests: test_cpu_gpu_irq_pass (positive), test_cpu_gpu_irq_no_irq_enable (negative).
soc_cpu_gpu: soc_boot_lint
	$(MAKE) MODULE=test_cpu_gpu_irq TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level GPIO test (bead claude_verilog_test-8qn4 item 1). Exercises
# gpio_controller (APB slave 7, 0x2000_A000) through the real fabric path —
# CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
# axil_to_apb -> apb_interconnect -- for the first time (test_gpio/tb_gpio.sv
# drives the APB4 face directly). gpio_controller.sv is already part of
# SOC_BOOT_SOURCES (no new source-list variable needed) and tb_soc_top.sv
# already lints clean with the new gpio_out_o/gpio_oe_o/gpio_in_i ports, so
# this reuses soc_boot_lint as its hard prerequisite exactly like
# soc_periph/soc_coherency/soc_cpu_gpu above.
# Tests: output path (GPIO_DIR/GPIO_DATA_OUT reach gpio_oe_o/gpio_out_o),
# input path (gpio_in_i -> GPIO_DATA_IN, respecting the 3-clock-edge sync
# latency), and the GPIO -> interrupt_controller[5] -> CPU MEIP interrupt
# path end to end (CPU actually takes the trap; GPIO_IRQ_CLR deasserts it).
soc_gpio: soc_boot_lint
	$(MAKE) MODULE=test_soc_gpio TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level PWM test (bead claude_verilog_test-f7vs.6 item 5). Exercises
# pwm_controller (APB slave 8, 0x2000_B000) through the real fabric path —
# CPU -> axi4_crossbar -> axi4_to_axilite -> axi_lite_interconnect ->
# axil_to_apb -> apb_interconnect -- for the first time (test_pwm/tb_pwm.sv
# drives the APB4 face directly). pwm_controller.sv is already part of
# SOC_BOOT_SOURCES (no new source-list variable needed) and tb_soc_top.sv
# already lints clean with the existing pwm_o port, so this reuses
# soc_boot_lint as its hard prerequisite exactly like soc_gpio above.
# Tests: boundary toggle (pwm_o free-runs at the configured period/duty once
# channel 0 is enabled — no cocotb stimulus needed, unlike soc_gpio) and the
# PWM -> interrupt_controller[6] -> CPU MEIP interrupt path end to end (CPU
# actually takes the trap; PWM_IRQ_CLR + PWM_IRQ_EN=0 deassert it).
soc_pwm: soc_boot_lint
	$(MAKE) MODULE=test_soc_pwm TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level WDT test (bead claude_verilog_test-f7vs.7 step 5). Exercises watchdog_timer
# (APB slave 9, 0x2000_C000) through the real fabric path — CPU -> axi4_crossbar ->
# axi4_to_axilite -> axi_lite_interconnect -> axil_to_apb -> apb_interconnect -- for the first
# time (test_wdt/tb_wdt.sv drives the APB4 face directly), plus the two things that only exist
# inside soc_top: the WDT -> interrupt_controller[7] -> CPU MEIP interrupt path, and the
# bite -> CPU-domain reset path (u_cpu_wdt_rst_sync). Two tests / two hand-assembled images
# (wdt_fw/gen_wdt_hex.py, no cross toolchain — CI-safe): feed-then-starve with RST_EN=0 (bark
# trap, bite trap, wdt_rst_req_o at the boundary, cpu_domain_rst_n never falls), and RST_EN=1
# (bite resets the CPU domain only). watchdog_timer.sv is already in SOC_BOOT_SOURCES and
# tb_soc_top.sv already lints clean with wdt_rst_req_o, so this reuses soc_boot_lint exactly
# like soc_pwm above.
soc_wdt: soc_boot_lint
	$(MAKE) MODULE=test_soc_wdt TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level TRNG test (bead claude_verilog_test-f7vs.8 step 5). Exercises trng (APB slave 10,
# 0x2000_D000) through the real fabric path — CPU -> axi4_crossbar -> axi4_to_axilite ->
# axi_lite_interconnect -> axil_to_apb -> apb_interconnect -- for the first time (test_trng/
# tb_trng.sv drives the APB4 face directly), plus the trng -> interrupt_controller[8] -> CPU MEIP
# interrupt path. One test / one hand-assembled image (trng_fw/gen_trng_hex.py, no cross
# toolchain — CI-safe): polled phase with the popped words checked value-exact against
# tb/models/trng_lfsr_model.py and TRNG_STATUS[3] (INSECURE) read back, then an interrupt-driven
# phase. trng.sv + trng_lfsr_entropy.sv are already in SOC_BOOT_SOURCES and tb_soc_top.sv is
# unchanged (TRNG adds no top-level pins), so this reuses soc_boot_lint exactly like soc_wdt above.
soc_trng: soc_boot_lint
	$(MAKE) MODULE=test_soc_trng TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level I2C FABRIC test (bead claude_verilog_test-f7vs.9). Exercises i2c_controller (APB slave
# 11, 0x2000_E000) through the real fabric path -- CPU -> axi4_crossbar -> axi4_to_axilite ->
# axi_lite_interconnect -> axil_to_apb -> apb_interconnect -- plus the i2c -> interrupt_controller
# [9] -> CPU MEIP interrupt path. Deliberately CHEAP: it uses the DUT's internal loopback
# (I2C_CTRL[1], the SPI_CTRL[4] precedent) so no bus BFM and no protocol traffic runs at
# CLK_PERIOD_NS=2; full protocol coverage is the L1 `i2c` suite. One test / one hand-assembled
# image (i2c_fw/gen_i2c_hex.py, no cross toolchain -- CI-safe). i2c_controller.sv is already in
# SOC_BOOT_SOURCES and tb_soc_top.sv already exposes the i2c_* pins, so this reuses soc_boot_lint
# exactly like soc_trng/soc_gpio/soc_wdt above.
soc_i2c: soc_boot_lint
	$(MAKE) MODULE=test_soc_i2c TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level CRYPTO FABRIC test (bead claude_verilog_test-f7vs.10). Exercises crypto_accel (APB slave
# 12, 0x2000_F000) through the real fabric path -- CPU -> axi4_crossbar -> axi4_to_axilite ->
# axi_lite_interconnect -> axil_to_apb -> apb_interconnect -- plus the crypto -> interrupt_controller
# [10] -> CPU MEIP interrupt path. Deliberately CHEAP: a few FIPS-197 / FIPS 180-4 known answers read
# back over the bus; every behaviour of the peripheral itself is the L1 `crypto` suite. One test / one
# hand-assembled image (crypto_fw/gen_crypto_hex.py, no cross toolchain -- CI-safe). crypto_accel.sv,
# aes128_core.sv and sha256_core.sv are already in SOC_BOOT_SOURCES and tb_soc_top.sv needs no new
# ports (crypto has no pins), so this reuses soc_boot_lint exactly like soc_i2c/soc_trng above.
soc_crypto: soc_boot_lint
	$(MAKE) MODULE=test_soc_crypto TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level NPU FABRIC test (bead claude_verilog_test-f7vs.11). Exercises npu_top (APB slave 13,
# 0x2001_0000) through the real fabric path -- CPU -> axi4_crossbar -> axi4_to_axilite ->
# axi_lite_interconnect -> axil_to_apb -> apb_interconnect -- plus the npu -> interrupt_controller
# [11] -> CPU MEIP interrupt path. Deliberately CHEAP: three small INT8 inferences (polled, interrupt
# driven with ReLU, illegal START) read back over the bus; every behaviour of the peripheral itself
# is the L1 `npu` suite. One test / one hand-assembled image (npu_fw/gen_npu_hex.py, no cross
# toolchain -- CI-safe). npu_top.sv / npu_mac_array.sv / npu_weight_mem.sv are already in
# SOC_BOOT_SOURCES and tb_soc_top.sv needs no new ports (the NPU has no pins), so this reuses
# soc_boot_lint exactly like soc_crypto above.
soc_npu: soc_boot_lint
	$(MAKE) MODULE=test_soc_npu TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# GPIO DRIVER test (bead claude_verilog_test-8qn4 item 2). Unlike soc_gpio
# above (hand-assembled gpio_fw firmware proving the RTL through the
# fabric), this suite proves sw/drivers/gpio.h -- the first GPIO driver
# layer in this repo -- by RUNNING a normal compiled C program
# (sw/bench/gpio_demo.c) built through the existing sw/bench toolchain.
# gpio_controller.sv is already part of SOC_BOOT_SOURCES and tb_soc_top.sv
# already exposes gpio_out_o/gpio_oe_o/gpio_in_i (see soc_gpio's own
# comment), so this reuses soc_boot_lint as its hard lint prerequisite
# exactly like soc_gpio/soc_periph/soc_coherency/soc_cpu_gpu do -- no
# separate gpio_driver_lint alias, for the same reason none of those four
# have one either (one shared tb_soc_top lint gate for the whole family).
# SRAM_MEM_WORDS=65536 override matches l2_bench: gpio_demo.c links via the
# shared sw/bench/rv32i.ld, whose stack top (0x41C00) assumes that window.
# Firmware is pre-built by
#   nix develop ~/Downloads/Github/claude_verilog_test#bench --command make -C sw/bench
# this target consumes sw/bench/build/gpio_demo.{hex,sym,dis} -- it does NOT
# rebuild the C code (same contract as l2_bench).
# ── gpio_driver is IN soc_all but NOT IN soc_all_ci (bead 8qn4 item 2) ────────
# It consumes sw/bench/build/{trampoline,gpio_demo}.{hex,sym}, produced by the
# riscv32-none-elf cross toolchain into the GITIGNORED sw/bench/build/. CI has no
# cross-toolchain step, so those files cannot exist there and the suite dies in
# _parse_hex() with a FileNotFoundError traceback -- exactly what failed on
# PR #195. Hence: in soc_all (the full local gate), out of soc_all_ci.
#
# l2_bench depends on the same sw/bench hexes but is in NEITHER target, on
# purpose: it is a benchmark/characterisation harness built for the M10 L2
# decision (TESTCASE-limited, SRAM_MEM_WORDS=65536), not a pass/fail regression.
#
# RTL-level GPIO coverage is unaffected either way: soc_gpio is in soc_all_ci
# because its firmware (tb/cocotb/soc/gpio_fw/gpio_fw.hex) is generated by a
# pure-Python assembler, is committed, and needs no external toolchain.
gpio_driver: soc_boot_lint
	@test -f $(PROJ_ROOT)/sw/bench/build/gpio_demo.hex -a \
	      -f $(PROJ_ROOT)/sw/bench/build/trampoline.hex || { \
		echo "ERROR: sw/bench/build/{gpio_demo,trampoline}.hex missing."; \
		echo "       This target needs the riscv32 cross toolchain. Build first:"; \
		echo "         nix develop $(PROJ_ROOT)#bench --command make -C sw/bench"; \
		exit 1; }
	$(MAKE) MODULE=test_gpio_driver TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET \
		  -GSRAM_MEM_WORDS=65536" \
		$(BUILD_ARGS)

# GH #93 multiclock SoC CDC exercise (bead: feat/cpu-domain-cdc-gh93 verif task).
# Drives clk_i (fabric) / cpu_clk_i (CPU) at a genuinely asynchronous 7 ns /
# 3 ns ratio (see test_soc_multiclock.py's module docstring for the full
# rationale) to prove the CPU<->fabric CDC (async_axi_fifo + the
# ext_irq/timer_irq/pmu_cpu_* cdc_2ff_sync synchronisers in soc_top.sv) works
# when the two domains are not clock-aligned, reusing boot_fw/boot.hex,
# periph_fw/periph_loopback.hex, and cpu_gpu_irq_fw/cpu_gpu_irq_fw.hex — no
# new firmware. Reuses SOC_BOOT_SOURCES + soc_boot_lint (same DUT/lint gate
# as soc_boot/soc_periph/soc_cpu_gpu).
#
# In soc_all (see the soc_all comment block) since 2026-08-02, once both
# bugs it found were fixed. Runnable standalone too: `rtk make soc_multiclock`.
soc_multiclock: soc_boot_lint
	$(MAKE) MODULE=test_soc_multiclock TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# GH #95 (Group A, directed-test half): SoC-level reset-asymmetry class --
# hold one physical domain's reset input low for an extended, deliberate
# window (well beyond ordinary PLL-lock skew) while the other domain is
# fully released and free-running, offering real traffic through
# u_cpu_axi_cdc. See test_soc_multiclock_reset.py's module docstring for the
# full rationale (regression coverage for fr_57f49b7f9b29 / fr_280f3ac18c66's
# shared bug-class signature, at full-SoC scale). Reuses boot_fw/boot.hex --
# no new firmware. Same DUT/source list/lint gate as soc_multiclock.
soc_multiclock_reset: soc_boot_lint
	$(MAKE) MODULE=test_soc_multiclock_reset TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# GH #95 (Group C): PMU-driven live CPU-domain power-cycle at a divergent
# clock ratio (bead claude_verilog_test-2k8) -- see test_soc_pmu_multiclock.py's
# module docstring for the full rationale (firmware programs the DMA to write
# PMU CTRL=CPU_OFF on the CPU's own behalf; the power-up trigger is supplied
# by the testbench itself, since the CPU cannot write its own wake register
# once gated). Firmware: pmu_cycle_fw/pmu_cycle.hex (generated by
# gen_pmu_cycle_hex.py) -- new firmware, not reused from another suite. Same
# DUT/source list/lint gate as soc_multiclock.
soc_pmu_multiclock: soc_boot_lint
	$(MAKE) MODULE=test_soc_pmu_multiclock TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level integration gaps from the GH #216 coverage run (bead claude_verilog_test-oez2): the
# peripheral IRQ lines + CPU traps (timer/UART/SPI/DMA), the SPI MISO input against a testbench
# slave, both PLLs' divider registers through the fabric, GPU isolation via a PMU power cycle,
# and the external APB debug master (halt/GPR/step, RO-register PSLVERR, and the apb_cdc_bridge
# force-complete PSLVERR with the destination in reset). Six tests, ONE Vtop build. Firmware:
# integ_fw/gen_integ_hex.py (three images, hand-assembled, no cross toolchain -- CI-safe).
# Same DUT/source list/lint gate as soc_pmu_multiclock.
soc_integration: soc_boot_lint
	$(MAKE) MODULE=test_soc_integration TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M9 SoC stress + benchmark test (bead claude_verilog_test-pgf).
# Self-checking firmware runs STRESS_ITER=10 outer loops exercising CPU burst,
# DMA, GPU kernel, UART/SPI loopback, and timer in each loop (≥1M sim cycles).
# Waveform tracing is DISABLED (EXTRA_ARGS="") — tracing 1M+ cycles would
# generate a multi-GB VCD dump.  Keep this target OUT of soc_all because
# runtime is long (>5 min); run explicitly with `make soc_stress`.
soc_stress: soc_boot_lint
	/usr/bin/python3 $(SOC_DIR)/stress_fw/gen_stress_hex.py
	$(MAKE) MODULE=test_soc_stress TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M10 L2-cache decision benchmark (bead claude_verilog_test-e4f).
# Loads bare-metal C benchmarks (hello / sweep / matmul) onto the full SoC
# with SRAM_MEM_WORDS=65536 (256 KB window) and reads perf-counter scratch
# slots after EBREAK to compute I$/D$-miss rates.
# Firmware is pre-built by `nix develop .#bench --command make -C sw/bench`;
# this target consumes the build/ outputs — it does NOT rebuild the C code.
# EXTRA_ARGS: no --trace (miss-rate runs can be long; VCD is wasteful here).
# Excluded from soc_all (long runtime; separate measurement tool).
l2_bench_lint:
	verilator --lint-only -Wall -Wno-fatal -Wno-IMPORTSTAR \
		-Wno-UNUSEDSIGNAL -Wno-UNOPTFLAT -Wno-SYNCASYNCNET \
		-Wno-DECLFILENAME -Wno-UNUSEDPARAM -Wno-BLKSEQ \
		-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		--top-module tb_soc_top \
		$(SOC_BOOT_SOURCES)

l2_bench: l2_bench_lint
	$(MAKE) MODULE=test_l2_bench TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET \
		  -GSRAM_MEM_WORDS=65536" \
		TESTCASE=test_hello_sanity,test_sweep_l2_bench \
		$(BUILD_ARGS)

# Run every SoC test: M3–M6 component suites + M9 boot + M9 periph + M9 coherency +
# M9 cpu_gpu + Phase 7 M-c PLL (lock + regs) + GH #101 PMU + GH #91 async_axi_fifo.
# Bead claude_verilog_test-7je: each suite now builds into its own
# sim_build_<target>/ (see BUILD_ARGS above), so no per-suite purge is needed
# here.  Use `make distclean` to sweep every build dir.
# NOTE: soc_stress and l2_bench are intentionally excluded from soc_all (long runtime).
# soc_multiclock / soc_pll_multiclock (GH #93) joined soc_all on 2026-08-02.
#   Both blocking bugs they found (soc_top.sv CPU clock-gate/sync-reset race,
#   commit 4398c2e; cdc_gray_fifo wr_ready_o reset-release-skew accept-and-drop,
#   commit 7a9f9d4 — see test_soc_multiclock.py's BLOCKER NOTE #1/#2 for the
#   full root-cause trail) are fixed, and both suites pass. Runtime measured at
#   ~95s combined (soc_multiclock ~93s dominated by test_multiclock_periph_loopback's
#   UART/SPI bit-banging at the 7ns/3ns ratio; soc_pll_multiclock <1s) — comparable
#   to soc_boot's own 100-attempt stability gate already in this list, so kept in.
# ── soc_all vs soc_all_ci ─────────────────────────────────────────────────────
# soc_all_ci  — every suite that needs NOTHING beyond this repo + the nix sim
#               devshell. This is what CI runs, and what PASS_FLOOR is measured
#               against.
# soc_all     — soc_all_ci PLUS suites that additionally need the riscv32-none-elf
#               cross toolchain to have produced sw/bench/build/*.hex. Run this
#               locally as the final verification step before pushing; it is the
#               real "everything" gate.
#
# The split exists because CI has no cross-toolchain step, so a toolchain-
# dependent suite in the CI target dies in _parse_hex() with a FileNotFoundError
# (this is exactly what failed on PR #195). Prior to this split the only way to
# keep CI green was to drop such suites from soc_all altogether, which silently
# shrank the "run everything" target — the reason for naming the CI subset
# explicitly instead.
#
# Build the firmware first if you are running the full soc_all:
#   nix develop <repo>#bench --command make -C sw/bench
soc_all: soc_all_ci
	$(MAKE) gpio_driver

soc_all_ci: check-space
	$(MAKE) crossbar
	$(MAKE) register_bank
	$(MAKE) axil_interconnect
	$(MAKE) axil_apb_fabric
	$(MAKE) sram_controller
	$(MAKE) sram_controller SRAM_TARGET=sky130
	$(MAKE) axi4_to_axilite
	$(MAKE) axilite_to_axi4
	$(MAKE) boot_rom
	$(MAKE) dma
	$(MAKE) irq
	$(MAKE) timer
	$(MAKE) uart
	$(MAKE) spi
	$(MAKE) apb4_register_bank
	$(MAKE) axil_to_apb
	$(MAKE) pmu
	$(MAKE) gpio
	$(MAKE) pwm
	$(MAKE) wdt
	$(MAKE) trng
	$(MAKE) i2c
	$(MAKE) crypto
	$(MAKE) npu
	$(MAKE) apb_interconnect
	$(MAKE) async_axi_fifo
	$(MAKE) apb_cdc_bridge
	$(MAKE) cdc_reset_sync_scan
	$(MAKE) soc_boot
	$(MAKE) soc_periph
	$(MAKE) soc_coherency
	$(MAKE) soc_cpu_gpu
	$(MAKE) soc_gpio
	$(MAKE) soc_pwm
	$(MAKE) soc_wdt
	$(MAKE) soc_trng
	$(MAKE) soc_i2c
	$(MAKE) soc_crypto
	$(MAKE) soc_npu
	$(MAKE) soc_pll
	$(MAKE) soc_multiclock
	$(MAKE) soc_multiclock_reset
	$(MAKE) soc_pll_multiclock
	$(MAKE) soc_pmu_multiclock
	$(MAKE) soc_integration

# soc_integration_batch — compile tb_soc_top ONCE and run the four soc_top integration
# suites back-to-back without a clean between MODULE changes.
# Saves ~3 full compilations (~90 min at -j2) vs running soc_boot/periph/coherency/cpu_gpu
# individually. Safe because all four share identical VERILOG_SOURCES, TOPLEVEL, EXTRA_ARGS,
# and BUILD_ARGS; only the MODULE (Python test) differs. cocotb's dependency check sees the
# Vtop binary is current and skips recompilation for suites 2-4.
# Requires the same SIM_BUILD for all four invocations (set via env or command line).
.PHONY: soc_integration_batch
soc_integration_batch: soc_boot_lint
	$(MAKE) MODULE=test_boot TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_periph_loopback TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_soc_coherency TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_cpu_gpu_irq TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Bead claude_verilog_test-7je: cocotb's own `clean` only removes $(SIM_BUILD),
# which is now per-target, so it cannot sweep the others.
# Bead claude_verilog_test-f97: sweep $(SIM_BUILD_ROOT), not the CWD.  With the
# dirs relocated, a CWD-relative `rm -rf sim_build_*` deleted only the local
# symlinks and orphaned the real ~1.8 GB on the scratch filesystem.
.PHONY: distclean clean-sim-builds
distclean: clean-sim-builds

clean-sim-builds:
	rm -rf $(SIM_BUILD_ROOT)/sim_build $(SIM_BUILD_ROOT)/sim_build_*
	@# Also clear any stale in-tree dirs/symlinks left by an earlier SIM_BUILD_ROOT.
	rm -rf ./sim_build ./sim_build_*

# Bead p6t8 self-test: prove a genuinely failing cocotb suite now makes make exit non-zero.
# Deliberately NOT in soc_all / soc_all_ci -- it fails a suite on purpose.  The failure needs
# no edit to any committed test: test_register_bank.py's stale-Vtop guard (_setup) asserts
# the elaborated address-bus width equals REGBANK_ADDR_W, so elaborating -GADDR_W=5 while
# claiming REGBANK_ADDR_W=12 makes every test fail.  Own SIM_BUILD (the stale-Vtop hazard
# applies to reuse of a dir across parameter values).  The sub-make is expected to fail;
# exit 0 from it means the check_for_results_file redefinition has stopped working.
.PHONY: check-exit-propagation
check-exit-propagation:
	@echo "=== check-exit-propagation: a deliberately failing suite MUST make make exit non-zero ==="; \
	if REGBANK_ADDR_W=12 $(MAKE) MODULE=test_register_bank TOPLEVEL=tb_axi_lite_register_bank \
		VERILOG_SOURCES="$(REGBANK_SOURCES)" \
		EXTRA_ARGS="-GADDR_W=5" \
		$(BUILD_ARGS) \
		SIM_BUILD=$(SIM_BUILD_ROOT)/sim_build_check_exit_propagation \
		sim; then \
		echo "check-exit-propagation: FAIL -- a failing cocotb suite exited 0 (bead p6t8 regressed)" >&2; \
		exit 1; \
	fi; \
	echo "check-exit-propagation: PASS -- the failing suite exited non-zero"

.PHONY: check-space
check-space:
	@mkdir -p $(SIM_BUILD_ROOT)
	@free_mb=$$(df -Pm $(SIM_BUILD_ROOT) | awk 'NR==2 {print $$4}'); \
	if [ "$$free_mb" -lt "$(SIM_BUILD_MIN_FREE_MB)" ]; then \
	  echo "ERROR: only $${free_mb} MB free on the filesystem holding SIM_BUILD_ROOT=$(SIM_BUILD_ROOT)"; \
	  echo "       a full rebuild of every sim_build dir needs >= $(SIM_BUILD_MIN_FREE_MB) MB."; \
	  echo "       Point SIM_BUILD_ROOT at a bigger filesystem, e.g."; \
	  echo "         make SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc $(MAKECMDGOALS)"; \
	  echo "       or reclaim space with: make clean-sim-builds"; \
	  echo "       (override the floor with SIM_BUILD_MIN_FREE_MB=<n> if the build is incremental)"; \
	  exit 1; \
	fi; \
	echo "check-space: $${free_mb} MB free at $(SIM_BUILD_ROOT) (floor $(SIM_BUILD_MIN_FREE_MB) MB) -- OK"

# GH #216 / bead nkj7: whole-SoC line + toggle coverage.  Runs the ENTIRE soc_all_ci regression
# with COVERAGE=1 (instrumented Vtop in its own sim_build_*_cov dirs, one .dat per simulation in
# $(COV_DIR)), merges them, and renders a per-module report.  Deliberately NOT a prerequisite of
# soc_all_ci / soc_all: an instrumented -O0 build is much slower and is run nightly / on demand
# (.github/workflows/soc_coverage.yml), never per PR.  Defined down here for the same reason as
# check-space: a target above the cocotb include would become the default goal.
#   make SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc_cov soc_coverage
# Outputs in $(COV_DIR): <build>__<module>.dat (per simulation), merged.dat,
# coverage_report.md, coverage_report.json.  The target fails if the regression fails or if no
# coverage data was produced (a vacuous "report" would otherwise look like a clean one).
.PHONY: soc_coverage
soc_coverage:
	@mkdir -p $(COV_DIR)
	rm -f $(COV_DIR)/*.dat $(COV_DIR)/coverage_report.md $(COV_DIR)/coverage_report.json
	$(MAKE) soc_all_ci COVERAGE=1
	@ls $(COV_DIR)/*.dat >/dev/null 2>&1 || { echo "ERROR: soc_coverage: no .dat written to $(COV_DIR) -- coverage was not collected" >&2; exit 1; }
	verilator_coverage --write $(COV_DIR)/merged.dat $(COV_DIR)/*.dat
	$(or $(SIM_PYTHON3),python3) $(PROJ_ROOT)/tools/verif/coverage_report.py \
		--dat $(COV_DIR)/merged.dat --root $(PROJ_ROOT) \
		--waivers $(PROJ_ROOT)/tools/verif/coverage_waivers.txt \
		--out-md $(COV_DIR)/coverage_report.md --out-json $(COV_DIR)/coverage_report.json
