# Makefile for SoC cocotb tests (Phase 5 / M3–M9)
# Component unit tests (M3–M6) + SoC boot test (M9).
# Doc: tm:suite:soc-makefile, cr:suite:soc-makefile

TOPLEVEL_LANG ?= verilog
SIM ?= verilator

# Absolute paths so the Makefile works whether invoked from sim/ or here.
SOC_DIR  := $(shell pwd)
PROJ_ROOT := $(abspath $(SOC_DIR)/../../..)
RTL      := $(PROJ_ROOT)/rtl
TB       := $(PROJ_ROOT)/tb/cocotb
SIM_DIR  := $(PROJ_ROOT)/sim

# Base directory for the per-target sim_build dirs. It defaults to `.`, so with the variable unset the
# sim_build dirs stay in the current directory. Point it at scratch when the root filesystem is tight:
#   make SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc soc_all
# An RTL edit invalidates every dir that compiles the edited file; after an edit to a shared package a full soc_all
# rebuild needs several GB at once. When that space is missing, the run fails after the per-suite PASS lines with
# "ERROR: results.xml was not written by the simulation!". That message means a full disk, not a test fault.
SIM_BUILD_ROOT ?= .
ifeq ($(strip $(SIM_BUILD_ROOT)),)
  $(error SIM_BUILD_ROOT is empty -- refusing to build or clean at the filesystem root)
endif

# Where `make soc_coverage` collects the per-simulation coverage .dat files, merged.dat and the report.
# Absolute, because every sub-make and simulator process runs from this directory, but a relative path
# would silently follow a future `-C`.
COV_DIR ?= $(SIM_BUILD_ROOT)/coverage
override COV_DIR := $(abspath $(COV_DIR))

# Pre-flight free-space gate. A full soc_all rebuild writes several GB of Verilator objects, and running out
# of space mid-flight shows up as a "results.xml was not written" error after the PASS lines.
# The check-space target fails first and names the real cause. Override the floor if the build is
# incremental: make SIM_BUILD_MIN_FREE_MB=500 soc_all
SIM_BUILD_MIN_FREE_MB ?= 6000

# NOTE: the check-space RECIPE lives at the bottom of this file, after the
# cocotb `include`.  Any target defined before that include becomes make's
# default goal, and the per-suite recipes re-invoke `$(MAKE) MODULE=... ` with
# NO explicit target -- so a target up here silently replaces the cocotb `sim`
# goal and every suite runs the check instead of the test, exiting 0 having
# tested nothing.  Only the variables may live up here.

# bfm/ lives in tb/cocotb (TB); slave model lives in this directory.
export PYTHONPATH := $(TB):$(SOC_DIR):$(PYTHONPATH)

# Backing store for the standalone sram_controller target (same SRAM_TARGET convention as sim/Makefile).
# SRAM_TARGET=sky130 adds +define+SRAM_SKY130 to COMPILE_ARGS of EVERY target in this make: pass it only with sram_controller.
# The cache, CPU and NPU RTL also select sky130 macros on that define, and PLL_SOURCES, SOC_BOOT_SOURCES, NPU_SOURCES lack them.
# For a full soc_top elaboration under SRAM_SKY130, use `make -C sim lint_soc_sky130`.
#   make sram_controller                      # flat array
#   make sram_controller SRAM_TARGET=sky130   # sky130_sram_4kbyte_1rw1r_32x1024_8
SRAM_TARGET ?= freepdk45
ifeq ($(SRAM_TARGET),sky130)
    SRAM_CTRL_SIM_MODEL := $(SIM_DIR)/sky130_sram_4kbyte_1rw1r_32x1024_8.sv $(RTL)/soc/dft/mem_collar.sv
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

# The real ring -> axil_to_apb -> apb_interconnect -> apb4_register_bank
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

# Standalone AXI4-fabric bridge / ROM unit suites (the DUT is the toplevel, like sram_controller).
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
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/periph/interrupt_controller.sv

UART_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/periph/uart_controller.sv

SPI_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/periph/spi_controller.sv

# APB migration: apb4_register_bank unit-test sources.
# Standalone: axi_pkg (for DW/SW constants) + DUT + TB wrapper.
APB4_REG_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(SOC_DIR)/tb_apb4_register_bank.sv

# APB migration: axil_to_apb bridge unit-test sources.
# Full AXI→APB path: axi_pkg + bridge + register bank + TB wrapper.
AXIL_TO_APB_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/axil_to_apb.sv \
	$(SOC_DIR)/tb_axil_to_apb.sv

# APB migration: pll_axil_regs deleted — PLL_REGS_SOURCES now points at
# pll_apb_regs (APB4 slave).  The pll_regs target and pll_regs_lint below are
# redirected to the pll_apb_regs target (same functional coverage).
# PLL_REGS_SOURCES kept as an alias so any external callers still compile;
# the canonical source list is PLL_APB_REGS_SOURCES.
PLL_REGS_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/pll/pll_apb_regs.sv \
	$(SOC_DIR)/tb_pll_apb_regs.sv

# APB migration: standalone pll_apb_regs unit-test sources.
# Minimal: apb4_register_bank (no axi_pkg needed) + pll_apb_regs + standalone TB.
# BFM drives APB4 ports directly; no bus-bridge or full SoC required.
PLL_APB_REGS_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/pll/pll_apb_regs.sv \
	$(SOC_DIR)/tb_pll_apb_regs.sv

# Standalone pmu unit-test sources.
# Minimal: apb4_register_bank (no axi_pkg needed) + pmu + standalone TB.
# BFM drives APB4 ports directly; no bus-bridge or full SoC required.
PMU_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/pmu.sv \
	$(SOC_DIR)/tb_pmu.sv

# Phase 6a: standalone gpio_controller unit-test sources.
# apb4_register_bank (register file) + cdc_sync (N_PINS independent single-bit input
# synchronisers, one per pin -- see gpio_controller.sv header) + gpio_controller + standalone TB.
GPIO_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/periph/gpio_controller.sv \
	$(SOC_DIR)/tb_gpio.sv

# Phase 6a-2: standalone pwm_controller unit-test sources.
# apb4_register_bank (register file) + pwm_controller + standalone TB. Unlike GPIO_SOURCES above, there is no
# cdc_sync here: PWM has no async input pins (push-pull pwm_o only, no oe, no CDC). Doc: ds:ch:phase6-ip-expansion-plan:6a-2-pwm-rtlperiphpwm-controllersv
PWM_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/pwm_controller.sv \
	$(SOC_DIR)/tb_pwm.sv

# Phase 6a-3: standalone watchdog_timer unit-test sources.
# apb4_register_bank (register file) + watchdog_timer + standalone TB. Like PWM there is no cdc_sync here:
# the WDT has no async input pins (clk/rst_n/APB4 only; irq_o and wdt_rst_req_o are outputs).
# Doc: ds:ch:phase6-ip-expansion-plan:6a-3-wdt-rtlperiphwatchdog-timersv
WDT_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/watchdog_timer.sv \
	$(SOC_DIR)/tb_wdt.sv

# Phase 6a-4: standalone trng unit-test sources: apb4_register_bank + trng + its DEFAULT (LFSR) entropy
# sub-module + standalone TB. trng.sv selects its entropy source with `ifdef TRNG_RO_SKY130 INSIDE the module.
# This target does NOT define that macro, so trng_lfsr_entropy.sv is the arm under test and trng_ro_sky130.sv
# is deliberately absent: it is a Sky130-only analog stub, exempt in tools/verif/check_periph_filelists.py
# (EXEMPT map). Never add it to a file list. No cdc_sync: the LFSR arm has no asynchronous input.
# Doc: ds:ch:phase6-ip-expansion-plan:6a-4-trng-rtlperiphtrngsv
TRNG_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/trng_lfsr_entropy.sv \
	$(RTL)/periph/trng.sv \
	$(SOC_DIR)/tb_trng.sv

# Phase 6a-5: standalone i2c_controller unit-test sources.
# apb4_register_bank (register file) + cdc_sync (i2c_controller instantiates one per pin,
# like gpio_controller) + i2c_bit_engine (protocol core) + i2c_controller + standalone TB. The bus (wired-AND of master, slave and
# pull-up) is modelled by tb/cocotb/bfm/i2c_slave.py, NOT by any RTL file in this list.
# test_i2c.py also re-lints this exact list with `-GCLKDIV_MIN=2` to prove the DUT's elaboration
# guard refuses an unsafe prescaler minimum.
I2C_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/periph/i2c_bit_engine.sv \
	$(RTL)/periph/i2c_controller.sv \
	$(SOC_DIR)/tb_i2c.sv

# Phase 6b: standalone crypto_accel unit-test sources. apb4_register_bank (its DOUT / DIGEST / IV3 / STATUS / IRQ_STAT
# words are hardware-written bank words) + aes128_core and sha256_core, listed BEFORE the wrapper that instantiates them.
# tb_crypto.sv has FOUR crypto_accel configurations (default, SBOX_PARALLEL=4, EN_AES=0, EN_SHA=0). test_crypto.py re-lints
# this exact list (read back through tools/verif/check_source_closure.py's parser) with -G overrides.
# NO cdc_sync.sv, unlike gpio / i2c: crypto_accel has no asynchronous input, so no synchroniser and no SDC false path apply.
# Do not add it for safety: an unused module in the list is dead weight and hides a genuinely missing one.
CRYPTO_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/periph/aes128_core.sv \
	$(RTL)/periph/sha256_core.sv \
	$(RTL)/periph/crypto_accel.sv \
	$(SOC_DIR)/tb_crypto.sv

# Phase 6c: standalone npu_top unit-test sources. The register bank holds the hardware-written words, so it is the storage.
# npu_weight_mem and npu_mac_array come BEFORE npu_top. tb_npu.sv has two npu_top configurations (defaults, EN_NPU=0).
# test_npu.py re-lints this exact list (read back through tools/verif/check_source_closure.py's parser) with a -G override.
# The weight memory has a 3-way ifdef. A simulation build defines neither SRAM_SKY130 nor SRAM_ASAP7, so it takes the FreePDK45
# arm, and sim/sram_1rw_256x32_verilator.v MUST be in this list or Verilator reports a missing module. rv32i_clock_gate is for
# the ASAP7 arm: unused at sim time, but it keeps the list a superset of every arm. No cdc_sync: npu_top has no asynchronous input.
NPU_SOURCES = \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/mem/rv32i_clock_gate.sv \
	$(PROJ_ROOT)/sim/sram_1rw_256x32_verilator.v \
	$(RTL)/npu/npu_weight_mem.sv \
	$(RTL)/npu/npu_mac_array.sv \
	$(RTL)/npu/npu_top.sv \
	$(SOC_DIR)/tb_npu.sv

# Phase 6 groundwork: standalone apb_interconnect
# unit-test sources. apb_interconnect is a single, self-contained combinational module --
# no other RTL package or CDC primitive needed.
APB_INTERCONNECT_SOURCES = \
	$(RTL)/soc/apb_interconnect.sv \
	$(SOC_DIR)/tb_apb_interconnect.sv

# Standalone async_axi_fifo (dual-clock AXI4 CDC bridge) unit-test
# sources. axi_pkg (bus geometry defaults) + the 3 cdc/ primitives +
# async_axi_fifo + standalone TB wrapper. No bus-bridge or full SoC required.
ASYNC_AXI_FIFO_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/cdc/cdc_gray_fifo.sv \
	$(RTL)/soc/async_axi_fifo.sv \
	$(SOC_DIR)/tb_async_axi_fifo.sv

# Standalone apb_cdc_bridge (APB4 4-phase RZ-handshake CDC bridge) unit-test sources. It depends only on the 2 cdc/
# reset/sync primitives (no axi_pkg, no cdc_gray_fifo: it crosses single-bit req/ack levels, not gray-coded multi-bit
# pointers) + standalone TB wrapper. No bus-bridge or full SoC required.
APB_CDC_BRIDGE_SOURCES = \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/apb_cdc_bridge.sv \
	$(SOC_DIR)/tb_apb_cdc_bridge.sv

# cdc_sync RESET_VAL directed unit test.
# The primitive alone + standalone TB wrapper.
CDC_SYNC_SOURCES = \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(SOC_DIR)/tb_cdc_sync.sv

# Standalone cdc_gray_fifo (DEPTH=2 variant + DEPTH=4 control)
# unit-test sources. CDC_GRAY_FIFO_RTL is overridable so the mutation campaign can point the very
# same suite at a mutated copy of the primitive: make CDC_GRAY_FIFO_RTL=/path/mutant.sv cdc_gray_fifo
CDC_GRAY_FIFO_RTL ?= $(RTL)/soc/cdc/cdc_gray_fifo.sv
CDC_GRAY_FIFO_SOURCES = \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(CDC_GRAY_FIFO_RTL) \
	$(SOC_DIR)/tb_cdc_gray_fifo.sv

# Standalone cdc_reset_sync DFT scan-bypass
# mux (scanmode_i / scan_rst_ni) directed unit test. cdc_reset_sync alone +
# standalone TB wrapper -- no cdc_sync/cdc_gray_fifo dependency, this is
# a single-primitive test, not a CDC bridge test.
CDC_RESET_SYNC_SCAN_SOURCES = \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(SOC_DIR)/tb_cdc_reset_sync_scan.sv

# DFT Stage 1a: rv32i_clock_gate test-enable unit test.
# The gate alone + standalone wrapper; no other RTL needed.
CLOCK_GATE_SCAN_SOURCES = \
	$(RTL)/mem/rv32i_clock_gate.sv \
	$(SOC_DIR)/tb_clock_gate_scan.sv

# tb_dft_muxes instantiates exactly three DUT modules: dft_clk_mux, dft_rst_mux and dft_ctrl_ports (see tb_dft_muxes.sv). None of
# them instantiates another module or imports a package, so these are the only RTL files this suite needs. jtag_tap, dft_clk_switch,
# dft_ctrl, the CDC primitives and rv32i_clock_gate have their own suites (JTAG_TAP_SOURCES, DFT_CLK_SWITCH_SOURCES, ...).
DFT_MUXES_SOURCES = \
	$(RTL)/soc/dft/dft_clk_mux.sv \
	$(RTL)/soc/dft/dft_rst_mux.sv \
	$(RTL)/soc/dft/dft_ctrl_ports.sv \
	$(SOC_DIR)/tb_dft_muxes.sv

# DFT Stage 1b: the JTAG TAP alone. cdc_reset_sync is the TAP's
# TRST_N release synchroniser (the only dependency).
JTAG_TAP_SOURCES = \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/dft/jtag_tap.sv \
	$(SOC_DIR)/tb_jtag_tap.sv

# DFT Stage 4: MBIST controller + collar + fault-injecting SRAM models.
MBIST_CTRL_SOURCES = \
	$(RTL)/soc/dft/mbist_ctrl.sv \
	$(RTL)/soc/dft/mem_collar.sv \
	$(SOC_DIR)/sram_fi_core.sv \
	$(SOC_DIR)/tb_mbist_domain.sv

# TAP-driven end to end: dft_ctrl + soc_mbist (core + CPU domain) + controllers + FI memories.
MBIST_TAP_SOURCES = \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/cdc/cdc_gray_fifo.sv \
	$(RTL)/mem/rv32i_clock_gate.sv \
	$(RTL)/soc/dft/dft_ctrl_ports.sv \
	$(RTL)/soc/dft/jtag_tap.sv \
	$(RTL)/soc/dft/dft_clk_switch.sv \
	$(RTL)/soc/dft/dft_rst_mux.sv \
	$(RTL)/soc/dft/dft_ctrl.sv \
	$(RTL)/soc/dft/mbist_ctrl.sv \
	$(RTL)/soc/dft/mbist_xing.sv \
	$(RTL)/soc/dft/mbist_ctl_hold.sv \
	$(RTL)/soc/dft/mbist_status_sync.sv \
	$(RTL)/soc/dft/mem_collar.sv \
	$(RTL)/soc/dft/soc_mbist.sv \
	$(SOC_DIR)/sram_fi_core.sv \
	$(SOC_DIR)/tb_mbist_tap.sv

# SoC-level integration on the REAL wrappers: sram_controller + npu_top with +define+SRAM_SKY130 against the
# fault-injecting stand-in that takes the real macro's module name.
MBIST_SOC_SLICE_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(RTL)/soc/apb4_register_bank.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/cdc/cdc_gray_fifo.sv \
	$(RTL)/mem/rv32i_clock_gate.sv \
	$(RTL)/soc/dft/dft_ctrl_ports.sv \
	$(RTL)/soc/dft/jtag_tap.sv \
	$(RTL)/soc/dft/dft_clk_switch.sv \
	$(RTL)/soc/dft/dft_rst_mux.sv \
	$(RTL)/soc/dft/dft_ctrl.sv \
	$(RTL)/soc/dft/mbist_ctrl.sv \
	$(RTL)/soc/dft/mbist_xing.sv \
	$(RTL)/soc/dft/mbist_ctl_hold.sv \
	$(RTL)/soc/dft/mbist_status_sync.sv \
	$(RTL)/soc/dft/mem_collar.sv \
	$(RTL)/soc/dft/soc_mbist.sv \
	$(RTL)/soc/sram_controller.sv \
	$(RTL)/npu/npu_mac_array.sv \
	$(RTL)/npu/npu_weight_mem.sv \
	$(RTL)/npu/npu_top.sv \
	$(SOC_DIR)/sram_fi_core.sv \
	$(SOC_DIR)/sky130_sram_fi_wrappers.sv \
	$(SOC_DIR)/tb_mbist_soc_slice.sv

# FI model with no fault armed vs the REAL 4 KB simulation model.
MBIST_FI_EQUIV_SOURCES = \
	$(SIM_DIR)/sky130_sram_4kbyte_1rw1r_32x1024_8.sv \
	$(SOC_DIR)/sram_fi_core.sv \
	$(SOC_DIR)/tb_sram_fi_equiv.sv

# The REAL rv32i_cpu_top (+define+SRAM_SKY130, ten collars and the in-macro MBIST
# controller) behind dft_ctrl + soc_mbist, against fault-injecting stand-ins carrying the 1 KB macro's name.
MBIST_CPU_MACRO_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(RTL)/cpu/core/rv32i_pipeline_pkg.sv \
	$(RTL)/mem/rv32i_cache_pkg.sv \
	$(RTL)/cpu/core/rv32i_alu.sv \
	$(RTL)/cpu/core/rv32i_branch_comp.sv \
	$(RTL)/cpu/core/rv32i_imm_gen.sv \
	$(RTL)/cpu/core/rv32i_regfile.sv \
	$(RTL)/cpu/core/rv32i_decode.sv \
	$(RTL)/cpu/core/rv32i_forwarding_unit.sv \
	$(RTL)/cpu/core/rv32i_hazard_unit.sv \
	$(RTL)/cpu/core/rv32i_interrupt_ctrl.sv \
	$(RTL)/cpu/core/rv32i_csr_file.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_if.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_id.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex1c.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex1b.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_ex2.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(RTL)/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(RTL)/mem/rv32i_icache.sv \
	$(RTL)/mem/rv32i_dcache.sv \
	$(RTL)/mem/rv32i_cache_arbiter.sv \
	$(RTL)/cpu/core/rv32i_core.sv \
	$(RTL)/cpu/rv32i_cpu_top.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/cdc/cdc_gray_fifo.sv \
	$(RTL)/mem/rv32i_clock_gate.sv \
	$(RTL)/soc/dft/dft_ctrl_ports.sv \
	$(RTL)/soc/dft/jtag_tap.sv \
	$(RTL)/soc/dft/dft_clk_switch.sv \
	$(RTL)/soc/dft/dft_rst_mux.sv \
	$(RTL)/soc/dft/dft_ctrl.sv \
	$(RTL)/soc/dft/mbist_ctrl.sv \
	$(RTL)/soc/dft/mbist_xing.sv \
	$(RTL)/soc/dft/mbist_ctl_hold.sv \
	$(RTL)/soc/dft/mbist_status_sync.sv \
	$(RTL)/soc/dft/mem_collar.sv \
	$(RTL)/soc/dft/soc_mbist.sv \
	$(SOC_DIR)/sram_fi_core.sv \
	$(SOC_DIR)/sky130_sram_fi_wrappers.sv \
	$(SOC_DIR)/tb_mbist_cpu_macro.sv

# 1 KB macro: FI model with no fault armed vs the REAL 1 KB simulation model.
MBIST_FI_EQUIV_1K_SOURCES = \
	$(SIM_DIR)/sky130_sram_1kbyte_1rw1r_32x256_8.sv \
	$(SOC_DIR)/sram_fi_core.sv \
	$(SOC_DIR)/tb_sram_fi_equiv_1k.sv

# dft_ctrl = jtag_tap + the unchanged 1a pin leg + the TCK
# scan-clock gate (rv32i_clock_gate) + the combiner; the wrapper also instantiates the 1a
# dft_ctrl_ports as the golden reference.
DFT_CTRL_SOURCES = \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/mem/rv32i_clock_gate.sv \
	$(RTL)/soc/dft/dft_ctrl_ports.sv \
	$(RTL)/soc/dft/jtag_tap.sv \
	$(RTL)/soc/dft/dft_clk_switch.sv \
	$(RTL)/soc/dft/dft_ctrl.sv \
	$(SOC_DIR)/tb_dft_ctrl.sv

# The glitch-free test-clock switch alone.  tb_dft_clk_switch gates
# a raw TCK with rv32i_clock_gate to make the A clock (as dft_ctrl does) and carries a PLAIN_MUX
# parameter that swaps the switch for `sel ? a : b` (the RED negative control, target
# dft_clk_switch_plainmux).
DFT_CLK_SWITCH_SOURCES = \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/mem/rv32i_clock_gate.sv \
	$(RTL)/soc/dft/dft_clk_switch.sv \
	$(SOC_DIR)/tb_dft_clk_switch.sv

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
	$(RTL)/soc/dft/dft_clk_mux.sv \
	$(RTL)/soc/dft/dft_rst_mux.sv \
	$(RTL)/soc/dft/dft_ctrl_ports.sv \
	$(RTL)/soc/dft/jtag_tap.sv \
	$(RTL)/soc/dft/dft_clk_switch.sv \
	$(RTL)/soc/dft/dft_ctrl.sv \
	$(RTL)/soc/dft/mbist_ctrl.sv \
	$(RTL)/soc/dft/mbist_xing.sv \
	$(RTL)/soc/dft/mbist_ctl_hold.sv \
	$(RTL)/soc/dft/mbist_status_sync.sv \
	$(RTL)/soc/dft/mem_collar.sv \
	$(RTL)/soc/dft/soc_mbist.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
	$(RTL)/soc/cdc/cdc_reset_sync.sv \
	$(RTL)/soc/cdc/cdc_gray_fifo.sv \
	$(RTL)/soc/async_axi_fifo.sv \
	$(RTL)/soc/apb_cdc_bridge.sv \
	$(RTL)/soc/pmu.sv \
	$(RTL)/soc/soc_top.sv \
	$(SOC_DIR)/tb_soc_pll.sv

# Full SoC top-level sources for the boot test (M9).
# Order: packages first, leaf RTL, adapters, then soc_top + tb wrapper.
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
	$(RTL)/soc/dft/dft_clk_mux.sv \
	$(RTL)/soc/dft/dft_rst_mux.sv \
	$(RTL)/soc/dft/dft_ctrl_ports.sv \
	$(RTL)/soc/dft/jtag_tap.sv \
	$(RTL)/soc/dft/dft_clk_switch.sv \
	$(RTL)/soc/dft/dft_ctrl.sv \
	$(RTL)/soc/dft/mbist_ctrl.sv \
	$(RTL)/soc/dft/mbist_xing.sv \
	$(RTL)/soc/dft/mbist_ctl_hold.sv \
	$(RTL)/soc/dft/mbist_status_sync.sv \
	$(RTL)/soc/dft/mem_collar.sv \
	$(RTL)/soc/dft/soc_mbist.sv \
	$(RTL)/soc/cdc/cdc_sync.sv \
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
	# bead claude_verilog_test-rvs: gates rtl/soc/cdc/cdc_sync.sv's
	# optional simulation-only randomised-delay CDC injector (RAND_CDC_DELAY_EN,
	# default OFF at every instantiation site — this define alone changes
	# nothing observable). Never defined for sim/Makefile's lint_soc or the
	# tools/cdc/ sv2v+yosys CDC-gate flow, so the synthesis/lint/CDC-gate
	# paths stay bit-identical; only actual cocotb simulation runs (this
	# Makefile) can see the injector at all, and only instances that
	# explicitly override RAND_CDC_DELAY_EN=1 activate it.
	COMPILE_ARGS += +define+SIMULATION
	# bead hlrm (FPGA Stage 0): `make FPGA=1 soc_all_ci` elaborates the `FPGA arms (rtl/fpga block-RAM-inferable
	# memories). `-y rtl/fpga` lets Verilator resolve fpga_sram_1rw / fpga_sdp_ram_be by module name, so no source
	# list changes; COMPILE_ARGS is part of the content-keyed SIM_BUILD name, so FPGA and non-FPGA builds can
	# never share a directory. Off by default; nothing changes unless FPGA=1 is passed.
	ifeq ($(FPGA),1)
	COMPILE_ARGS += +define+FPGA -y $(PROJ_ROOT)/rtl/fpga
	# bead hlrm.2: the FPGA clock-gate arm (rv32i_clock_gate `FPGA_BUFGCE) instantiates the Xilinx BUFGCE primitive;
	# the simulation stub lives in rtl/fpga/sim/ (kept out of rtl/fpga/ so no Vivado file list can pick it up).
	COMPILE_ARGS += +define+FPGA_BUFGCE -y $(PROJ_ROOT)/rtl/fpga/sim
	endif
	COMPILE_ARGS += --timescale 1ns/1ps
	COMPILE_ARGS += --public-flat-rw
	COMPILE_ARGS += --no-timing
# Opt-in line + toggle coverage: `make soc_coverage` (below) runs the whole soc_all_ci regression with COVERAGE=1.
#  * The flags go in COMPILE_ARGS, not EXTRA_ARGS: most targets pass EXTRA_ARGS= on the command line, which
#    would override a makefile-level `+=`; none pass COMPILE_ARGS=.
#  * COV_SFX is appended to EVERY SIM_BUILD, so an instrumented build never reuses an uninstrumented Vtop.
#  * Each simulation writes its own .dat through the plusarg +verilator+coverage+file+. The name carries MODULE too,
#    because soc_integration_batch shares one SIM_BUILD across four MODULEs. --coverage-max-width 256 keeps wide arrays out of toggle coverage.
ifdef COVERAGE
	COV_SFX := _cov
	# Verilator will not create the directory itself; make a direct `make gpio COVERAGE=1` work too.
	COV_MKDIR := $(shell mkdir -p $(COV_DIR))
	COMPILE_ARGS += --coverage-line --coverage-toggle --coverage-max-width 256
	# (the +verilator+coverage+file+ plusarg is added further down, after SIM_BUILD is defined)
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
# SIM_BUILD = $(SIM_BUILD_ROOT)/sim_build_<TOPLEVEL>_<key>[_cov]: one dir per distinct compiled model. <key> is a sha256 prefix of
# SIM_KEY_MATERIAL (tools, TOPLEVEL, ordered VERILOG_SOURCES, COMPILE_ARGS, EXTRA_ARGS, BUILD_ARGS minus -j, build-time env).
# Stale-Vtop hazard: Verilator always names the binary Vtop, so a compile-time input missing from the key lets a second model reuse
# the first model's Vtop and still PASS. Add every new compile-time define, parameter or env var to SIM_KEY_MATERIAL, and pass no
# SIM_BUILD= from a recipe (check-exit-propagation alone does, on purpose). MODULE, TESTCASE, PLUSARGS, SIM_ARGS stay out of the key.
# Do not hash source content (each RTL edit would leave a new large dir). Check a key: `make print-sim-build ...`, tb/tests/test_sim_build_key.py.
ifndef SIM_KEY_TOOLS
  export SIM_KEY_TOOLS := $(shell printf '%s|%s|%s|%s' "$$(verilator --version 2>&1)" "$$(g++ --version 2>&1 | head -n1)" "$$(cocotb-config --version 2>&1)" "$$(sha256sum < $(SIM_DIR)/cxx_shim.sh | cut -c1-16)")
endif
# Only a simulation sub-make (MODULE given on the command line / env, as every recipe does) gets a
# keyed directory; a bare `make` keeps cocotb's default ./sim_build exactly as before.
ifneq ($(filter command line environment override,$(origin MODULE)),)
  SIM_KEY_MATERIAL := $(strip \
    tools=$(SIM_KEY_TOOLS) \
    top=$(TOPLEVEL) \
    sources=$(VERILOG_SOURCES) \
    compile=$(COMPILE_ARGS) \
    extra=$(EXTRA_ARGS) \
    build=$(filter-out -j%,$(BUILD_ARGS)) \
    env=$(VERILATOR_TRACE),$(VERILATOR_SIM_DEBUG),$(VERILOG_INCLUDE_DIRS),$(COCOTB_HDL_TIMEUNIT),$(COCOTB_HDL_TIMEPRECISION),$(CXXFLAGS),$(CPPFLAGS),$(LDFLAGS),$(OBJCACHE))
  SIM_BUILD_KEY := $(shell printf '%s' '$(subst ','\'',$(SIM_KEY_MATERIAL))' | sha256sum | cut -c1-16)
  SIM_BUILD := $(SIM_BUILD_ROOT)/sim_build_$(TOPLEVEL)_$(SIM_BUILD_KEY)$(COV_SFX)
endif
ifdef COVERAGE
	# Each simulation writes its own .dat through the runtime plusarg (see the COVERAGE block).
	# MODULE is in the name because suites that share a build directory share SIM_BUILD.
	override PLUSARGS += +verilator+coverage+file+$(COV_DIR)/$(notdir $(SIM_BUILD))__$(MODULE)$(if $(TESTCASE),__tc$(shell printf '%s' '$(TESTCASE)' | sha256sum | cut -c1-8)).dat
endif
# Parallel C++ compile of the Verilated model.  Unset by default (a developer host
# keeps whatever -j its own MAKEFLAGS gives); CI sets it to the runner's core count.  Applies to
# the Vtop.mk build only, never to the order the suites run in, and is excluded from the key.
SIM_BUILD_JOBS ?=
ifneq ($(strip $(SIM_BUILD_JOBS)),)
	BUILD_ARGS += -j$(SIM_BUILD_JOBS)
endif
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

# Commercial simulators (SIM=vcs | SIM=xcelium): tb/cocotb/common/sim_portability.mk translates the
# Verilator-flavoured EXTRA_ARGS/COMPILE_ARGS (-G<P>=, -I, -D, -W*, --trace ...) into each tool's
# own form, gives every build its own SIM_BUILD and turns the `*_lint` prerequisites into no-ops.
# It is inert for SIM=verilator, which is the only simulator CI runs.  `+define+SIMULATION` is set
# in the verilator block above, so it is passed on here for the other simulators.
SIM_PORT_KEYED_BUILD := 1
SIM_PORT_DEFINES := SIMULATION
ifneq ($(SIM),verilator)
  ifeq ($(FPGA),1)
    $(error FPGA=1 is only wired for SIM=verilator (the -y rtl/fpga library lookup is not translated for $(SIM)))
  endif
endif
include $(TB)/common/sim_portability.mk

include $(shell cocotb-config --makefiles)/Makefile.sim

# Make a failing cocotb suite fail the make. cocotb 1.9.2's check_for_results_file only tests that the results file EXISTS,
# never that it holds no failures, so a red suite exited 0. This redefinition goes AFTER the include and reaches every target and
# simulator, because make expands recipe lines when the rule runs. It makes the `set -e` in the multi-build-point recipes
# (register_bank, apb4_register_bank, boot_rom, mbist_ctrl, the apb_interconnect sweep) take effect. The verdict comes from tools/verif/check_cocotb_results.py,
# which reuses tools/eda/summarize.py's parser, not from a grep for "<failure". The existence check stays first, so a missing
# file still gets cocotb's own message. `check-exit-propagation` below is the self-test that proves this stays wired.
define check_for_results_file
    @test -f $(COCOTB_RESULTS_FILE) || (echo "ERROR: $(COCOTB_RESULTS_FILE) was not written by the simulation!" >&2 && exit 1)
    @$(or $(SIM_PYTHON3),python3) $(PROJ_ROOT)/tools/verif/check_cocotb_results.py $(COCOTB_RESULTS_FILE) || (echo "ERROR: cocotb recorded failures (bead p6t8: cocotb itself cannot set an exit code)" >&2 && exit 1)
endef

.PHONY: axi4_to_axilite axilite_to_axi4 boot_rom crossbar register_bank axil_interconnect axil_apb_fabric axil_apb_fabric_lint sram_controller dma dma_lint timer timer_lint irq irq_lint uart uart_lint spi spi_lint soc_boot soc_periph soc_coherency soc_cpu_gpu soc_stress soc_pll soc_pll_lint soc_all soc_all_ci verilator_lint soc_boot_lint l2_bench l2_bench_lint apb4_register_bank apb4_register_bank_lint axil_to_apb axil_to_apb_lint pmu pmu_lint pmu_guard_neg async_axi_fifo async_axi_fifo_lint soc_multiclock soc_multiclock_reset soc_pll_multiclock soc_dft_scan soc_scan_en_gate apb_cdc_bridge apb_cdc_bridge_lint soc_pmu_multiclock soc_integration cdc_reset_sync_scan cdc_reset_sync_scan_lint cdc_sync cdc_sync_lint cdc_sync_stages1_neg cdc_gray_fifo cdc_gray_fifo_sim cdc_gray_fifo_lint cdc_gray_fifo_depth_guard_neg periph_sync_stages clock_gate_scan clock_gate_scan_lint dft_muxes dft_muxes_lint jtag_tap jtag_tap_lint mbist_ctrl mbist_ctrl_lint mbist_tap mbist_tap_lint mbist_soc_slice mbist_soc_slice_lint mbist_fi_equiv mbist_fi_equiv_lint mbist_fi_equiv_1k mbist_fi_equiv_1k_lint mbist_cpu_macro mbist_cpu_macro_lint dft_clk_switch dft_clk_switch_lint dft_clk_switch_plainmux dft_ctrl dft_ctrl_lint soc_jtag gpio gpio_lint soc_gpio gpio_driver apb_interconnect apb_interconnect_lint pwm pwm_lint soc_pwm wdt wdt_lint soc_wdt trng trng_lint soc_trng i2c i2c_lint soc_i2c crypto crypto_lint soc_crypto npu npu_lint soc_npu check-exit-propagation soc_uart_boot soc_pmu_iso_ack
crossbar:
	$(MAKE) MODULE=test_crossbar,test_crossbar_errors TOPLEVEL=tb_axi4_crossbar \
		$(BUILD_ARGS)

# Two build points: the default ADDR_W=12, and ADDR_W=5 where WORDW=3 and N_REGS(8) == 2**WORDW, the case a truncating
# `WORDW'(N_REGS)` cast wraps to 0. ADDR_W is an elaboration parameter, so each point is its own Verilator build, and the
# differing EXTRA_ARGS put the points in separate SIM_BUILD dirs. test_register_bank.py also checks the elaborated address-bus
# width against REGBANK_ADDR_W. $(BUILD_ARGS) carries the nix CXX shim and -O0 flags. `set -e` and the trailing `\` make
# a failure at either point abort the target.
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
		sim

axil_interconnect:
	$(MAKE) MODULE=test_axil_interconnect TOPLEVEL=tb_axi_lite_interconnect \
		VERILOG_SOURCES="$(AXIL_SOURCES)" \
		$(BUILD_ARGS)

# Fabric chain with stalls / SLVERR / DECERR.  -Wno-SYNCASYNCNET kept for consistency
# with the other SoC-level targets; the wrapper has no async paths of its own.
axil_apb_fabric_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_axil_apb_fabric $(AXIL_APB_FABRIC_SOURCES)

axil_apb_fabric: $(call sp_lint,axil_apb_fabric_lint)
	$(MAKE) MODULE=test_axil_apb_fabric TOPLEVEL=tb_axil_apb_fabric \
		VERILOG_SOURCES="$(AXIL_APB_FABRIC_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

verilator_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		$(if $(filter sky130,$(SRAM_TARGET)),+define+SRAM_SKY130 -GMEM_WORDS=1024) \
		--top-module sram_controller $(SRAM_SOURCES)

# sram_controller's MEM_WORDS defaults to 4096, but the sky130_sram_4kbyte macro is hardwired to 1024 words (10-bit addr0/addr1).
# Without -GMEM_WORDS=1024 under SRAM_SKY130, a 12-bit word_index() is truncated onto the macro's 10-bit address ports
# (WIDTHTRUNC): a silent address alias in the test build. The RTL's own MEM_WORDS != 1024 check is a runtime `initial $error`,
# which neither Verilator `--lint-only` nor a cocotb run treats as fatal. -GMEM_WORDS=1024 matches the macro geometry that
# sram_controller.sv documents as mandatory under SRAM_SKY130.
sram_controller: $(call sp_lint,verilator_lint)
	$(MAKE) MODULE=test_sram_controller TOPLEVEL=sram_controller \
		VERILOG_SOURCES="$(SRAM_SOURCES)" \
		EXTRA_ARGS="$(if $(filter sky130,$(SRAM_TARGET)),-GMEM_WORDS=1024)" \
		$(BUILD_ARGS)

axi4_to_axilite:
	$(MAKE) MODULE=test_axi4_to_axilite TOPLEVEL=axi4_to_axilite \
		VERILOG_SOURCES="$(A2L_SOURCES)" \
		$(BUILD_ARGS)

axilite_to_axi4:
	$(MAKE) MODULE=test_axilite_to_axi4 TOPLEVEL=axilite_to_axi4 \
		VERILOG_SOURCES="$(L2A_SOURCES)" \
		$(BUILD_ARGS)

# boot_rom runs as two build points: the default (empty MEM_INIT_FILE -> zero-fill arm)
# and one with MEM_INIT_FILE set to a hex image (the $$readmemh arm no other suite takes -- they all
# backdoor-load).  The parameter is an elaboration parameter, so the second point is its own
# Verilator build, and the different EXTRA_ARGS give it its own SIM_BUILD (see the stale-Vtop hazard at SIM_BUILD).
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
		sim

dma_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module dma_engine $(DMA_SOURCES)

dma: $(call sp_lint,dma_lint)
	$(MAKE) MODULE=test_dma TOPLEVEL=dma_engine \
		VERILOG_SOURCES="$(DMA_SOURCES)" \
		$(BUILD_ARGS)

timer_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module timer $(TIMER_SOURCES)

timer: $(call sp_lint,timer_lint)
	$(MAKE) MODULE=test_timer TOPLEVEL=timer \
		VERILOG_SOURCES="$(TIMER_SOURCES)" \
		$(BUILD_ARGS)

# -Wno-SYNCASYNCNET (irq_lint, uart_lint): the peripheral's own flops are
# synchronous-reset while the cdc_sync instances assert reset
# asynchronously, so rst_n reaches both styles; same rationale as spi_lint.
irq_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module interrupt_controller $(IRQ_SOURCES)

irq: $(call sp_lint,irq_lint)
	$(MAKE) MODULE=test_irq_ctrl TOPLEVEL=interrupt_controller \
		VERILOG_SOURCES="$(IRQ_SOURCES)" \
		$(BUILD_ARGS)

uart_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module uart_controller $(UART_SOURCES)

uart: $(call sp_lint,uart_lint)
	$(MAKE) MODULE=test_uart TOPLEVEL=uart_controller \
		VERILOG_SOURCES="$(UART_SOURCES)" \
		$(BUILD_ARGS)

# -Wno-SYNCASYNCNET: spi_controller's own flops are synchronous-reset while the
# cdc_sync on spi_miso_i asserts reset asynchronously, so rst_n
# reaches both styles.  With spi_controller as the lint ROOT there is no logic
# between the port and the two usages, so Verilator flags the mix; the same
# rst_n / cdc_sync pattern raises nothing at soc_top scope.  Every SoC-level
# target in this file already carries this flag for the same reason.
spi_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module spi_controller $(SPI_SOURCES)

spi: $(call sp_lint,spi_lint)
	$(MAKE) MODULE=test_spi TOPLEVEL=spi_controller \
		VERILOG_SOURCES="$(SPI_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# APB migration: apb4_register_bank lint + sim.
apb4_register_bank_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_apb4_register_bank $(APB4_REG_SOURCES)

# Two build points; same scheme as register_bank above.  The ADDR_W=5 point is the
# POSITIVE CONTROL for the axi_lite_register_bank truncating-cast defect: this module already
# zero-extends the address, so its boundary test must pass.
apb4_register_bank: $(call sp_lint,apb4_register_bank_lint)
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
		sim

# APB migration: axil_to_apb bridge lint + sim.
axil_to_apb_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_axil_to_apb $(AXIL_TO_APB_SOURCES)

axil_to_apb: $(call sp_lint,axil_to_apb_lint)
	$(MAKE) MODULE=test_axil_to_apb TOPLEVEL=tb_axil_to_apb \
		VERILOG_SOURCES="$(AXIL_TO_APB_SOURCES)" \
		$(BUILD_ARGS)

# Phase 7 M-c: PLL lint gates.
# soc_pll_lint: lints tb_soc_pll (full SoC, used by test_pll_lock).
# pll_regs_lint: APB migration — pll_axil_regs deleted; redirected to
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

# Phase 7 M-c / APB migration: SoC PLL simulation targets.
# pll_regs is an alias for pll_apb_regs (tb_pll_apb_regs, APB4 slave); pll_axil_regs and its AXI-Lite test are deleted.
pll_regs: $(call sp_lint,pll_regs_lint)
	$(MAKE) pll_apb_regs

# APB migration: pll_apb_regs lint + sim.
# lint only: apb4_register_bank + pll_apb_regs + standalone TB wrapper.
pll_apb_regs_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_pll_apb_regs \
		$(PLL_APB_REGS_SOURCES)

pll_apb_regs: $(call sp_lint,pll_apb_regs_lint)
	$(MAKE) MODULE=test_pll_apb_regs TOPLEVEL=tb_pll_apb_regs \
		VERILOG_SOURCES="$(PLL_APB_REGS_SOURCES)" \
		$(BUILD_ARGS)

# pmu lint + sim.
# lint only: apb4_register_bank + pmu + standalone TB wrapper.
pmu_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_pmu \
		$(PMU_SOURCES)

# Negative control: an ADDR_W that cannot hold four register words, or an ISO_ACK_TIMEOUT that cannot be
# told from "no wait", must fail elaboration through the generate-scope $fatal and name the guard.
pmu_guard_neg:
	@for a in 0 1 2 3; do \
		out=$$(verilator --lint-only -Wall -Wno-IMPORTSTAR -GADDR_W=$$a \
			--top-module pmu $(RTL)/soc/apb4_register_bank.sv $(RTL)/soc/pmu.sv 2>&1); rc=$$?; \
		if [ $$rc -eq 0 ]; then \
			echo "FAIL: ADDR_W=$$a elaborated cleanly"; exit 1; \
		elif echo "$$out" | grep -q "pmu: ADDR_W ($$a) must be >= 4"; then \
			echo "PASS: ADDR_W=$$a rejected by pmu elaboration guard"; \
		else \
			echo "FAIL: ADDR_W=$$a failed for the wrong reason"; echo "$$out"; exit 1; \
		fi; \
	done
	@for t in 0 1; do \
		out=$$(verilator --lint-only -Wall -Wno-IMPORTSTAR -GISO_ACK_TIMEOUT=$$t \
			--top-module pmu $(RTL)/soc/apb4_register_bank.sv $(RTL)/soc/pmu.sv 2>&1); rc=$$?; \
		if [ $$rc -eq 0 ]; then \
			echo "FAIL: ISO_ACK_TIMEOUT=$$t elaborated cleanly"; exit 1; \
		elif echo "$$out" | grep -q "pmu: ISO_ACK_TIMEOUT ($$t) must be >= 2"; then \
			echo "PASS: ISO_ACK_TIMEOUT=$$t rejected by pmu elaboration guard"; \
		else \
			echo "FAIL: ISO_ACK_TIMEOUT=$$t failed for the wrong reason"; echo "$$out"; exit 1; \
		fi; \
	done

pmu: $(call sp_lint,pmu_lint pmu_guard_neg)
	$(MAKE) MODULE=test_pmu TOPLEVEL=tb_pmu \
		VERILOG_SOURCES="$(PMU_SOURCES)" \
		$(BUILD_ARGS)

# Phase 6a: gpio_controller lint + sim.
# lint only: apb4_register_bank + cdc_sync + gpio_controller + standalone TB wrapper.
# -Wno-SYNCASYNCNET: same rationale as spi_lint above -- cdc_sync's own flops are
# asynchronous-reset while gpio_controller's are synchronous-reset, and both are flopped off the
# same rst_n at this lint ROOT (gpio_controller instantiates cdc_sync directly).
gpio_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_gpio \
		$(GPIO_SOURCES)

gpio: $(call sp_lint,gpio_lint)
	$(MAKE) MODULE=test_gpio TOPLEVEL=tb_gpio \
		VERILOG_SOURCES="$(GPIO_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6a-2: pwm_controller lint + sim.
# lint only: apb4_register_bank + pwm_controller + standalone TB wrapper.
# -Wno-SYNCASYNCNET: matches the gpio targets' convention above, for consistency with the rest of
# this file's per-target EXTRA_ARGS, even though PWM has no cdc_sync / async input of its own.
pwm_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_pwm \
		$(PWM_SOURCES)

pwm: $(call sp_lint,pwm_lint)
	$(MAKE) MODULE=test_pwm TOPLEVEL=tb_pwm \
		VERILOG_SOURCES="$(PWM_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6a-3: watchdog_timer lint + sim.
# lint only: apb4_register_bank + watchdog_timer + standalone TB wrapper.
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm targets above.
wdt_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_wdt \
		$(WDT_SOURCES)

wdt: $(call sp_lint,wdt_lint)
	$(MAKE) MODULE=test_wdt TOPLEVEL=tb_wdt \
		VERILOG_SOURCES="$(WDT_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6a-4: trng lint + sim.
# lint only: apb4_register_bank + trng_lfsr_entropy + trng + standalone TB wrapper.
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm/wdt targets above.
trng_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_trng \
		$(TRNG_SOURCES)

trng: $(call sp_lint,trng_lint)
	$(MAKE) MODULE=test_trng TOPLEVEL=tb_trng \
		VERILOG_SOURCES="$(TRNG_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6a-5: i2c_controller lint + sim (L1 protocol suite).
# lint only: apb4_register_bank + cdc_sync + i2c_controller + standalone TB wrapper.
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm/wdt/trng targets above (the
# async pad inputs feed cdc_sync flops).
i2c_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_i2c \
		$(I2C_SOURCES)

i2c: $(call sp_lint,i2c_lint)
	$(MAKE) MODULE=test_i2c TOPLEVEL=tb_i2c \
		VERILOG_SOURCES="$(I2C_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6b: crypto_accel lint + sim (L1 AES / SHA suite).
# lint only: apb4_register_bank + aes128_core + sha256_core + crypto_accel + standalone TB wrapper
# (which holds all four configurations, so this lint also covers EN_AES=0 / EN_SHA=0 /
# SBOX_PARALLEL=4). Contract: 0 errors, 0 warnings.
# -Wno-SYNCASYNCNET: same per-target convention as the gpio/pwm/wdt/trng/i2c targets above, kept
# for consistency although crypto_accel has no asynchronous input to trip it.
crypto_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_crypto \
		$(CRYPTO_SOURCES)

crypto: $(call sp_lint,crypto_lint)
	$(MAKE) MODULE=test_crypto TOPLEVEL=tb_crypto \
		VERILOG_SOURCES="$(CRYPTO_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6c: npu_top lint + sim (L1 INT8 NPU suite). Lint: NPU_SOURCES (both configurations, so it also covers EN_NPU=0).
# Contract: 0 errors, 0 warnings.
# -Wno-SYNCASYNCNET: same per-target convention as the other peripheral targets, kept for consistency.
# -Wno-DECLFILENAME: sim/sram_1rw_256x32_verilator.v defines module sram_1rw_256x32_freepdk45, so `-Wall` reports it on a
# file this target does not own. soc_boot_lint disables it for the same file, and test_npu.py's lint passes the flag too.
# Every npu RTL file is named after its module, so the flag hides nothing of ours.
npu_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET -Wno-DECLFILENAME \
		--top-module tb_npu \
		$(NPU_SOURCES)

npu: $(call sp_lint,npu_lint)
	$(MAKE) MODULE=test_npu TOPLEVEL=tb_npu \
		VERILOG_SOURCES="$(NPU_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Phase 6 groundwork: apb_interconnect lint + sim.
# lint only: apb_interconnect + standalone TB wrapper, at the wrapper's default N_SLAVES.
# -Wno-SYNCASYNCNET: matches the gpio/spi targets' convention above, even though this DUT has
# no clock/reset of its own to trip it -- kept for consistency with the rest of this file's
# per-target EXTRA_ARGS.
apb_interconnect_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-SYNCASYNCNET \
		--top-module tb_apb_interconnect \
		$(APB_INTERCONNECT_SOURCES)

# apb_interconnect is a real N_SLAVES sweep: N_SLAVES is an elaboration-time parameter (it changes SEL_W/IDXW and the decode-window
# array sizes, see tb_apb_interconnect.sv), so Verilator re-elaborates once per value. Each point hashes to its OWN SIM_BUILD:
# reusing one dir across N_SLAVES values is the stale-Vtop hazard (see the SIM_BUILD block; Doc: ds:ch:phase6-ip-expansion-plan:operational-hazards). test_apb_interconnect.py
# reads N_SLAVES and OVERLAP_TEST back from APB_IC_N_SLAVES / APB_IC_OVERLAP, set below, so one test module runs at every sweep
# point plus the first-match-wins overlap build. `set -e` in one multi-line recipe (note the trailing `\`) makes a failing point
# abort the target.
apb_interconnect: $(call sp_lint,apb_interconnect_lint)
	@set -e; \
	for n in 1 2 7 8 9 13 14 15 16 17; do \
		echo "=== apb_interconnect sweep: N_SLAVES=$$n ==="; \
		APB_IC_N_SLAVES=$$n APB_IC_OVERLAP=0 \
		$(MAKE) MODULE=test_apb_interconnect TOPLEVEL=tb_apb_interconnect \
			VERILOG_SOURCES="$(APB_INTERCONNECT_SOURCES)" \
			EXTRA_ARGS="-Wno-SYNCASYNCNET -GN_SLAVES=$$n +define+TB_N_SLAVES=$$n" \
			$(BUILD_ARGS) \
			sim; \
	done; \
	echo "=== apb_interconnect overlap test: N_SLAVES=2 OVERLAP_TEST=1 ==="; \
	APB_IC_N_SLAVES=2 APB_IC_OVERLAP=1 \
	$(MAKE) MODULE=test_apb_interconnect TOPLEVEL=tb_apb_interconnect \
		VERILOG_SOURCES="$(APB_INTERCONNECT_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET -GN_SLAVES=2 -GOVERLAP_TEST=1 +define+TB_N_SLAVES=2 +define+TB_OVERLAP_TEST=1" \
		$(BUILD_ARGS) \
		sim

# async_axi_fifo lint + sim.
# lint only: axi_pkg + 3 cdc/ primitives + async_axi_fifo + standalone TB wrapper.
async_axi_fifo_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_async_axi_fifo \
		$(ASYNC_AXI_FIFO_SOURCES)

async_axi_fifo: $(call sp_lint,async_axi_fifo_lint)
	$(MAKE) MODULE=test_async_axi_fifo TOPLEVEL=tb_async_axi_fifo \
		VERILOG_SOURCES="$(ASYNC_AXI_FIFO_SOURCES)" \
		$(BUILD_ARGS)

# apb_cdc_bridge lint + sim.
# lint only: 2 cdc/ primitives + apb_cdc_bridge + standalone TB wrapper.
apb_cdc_bridge_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_apb_cdc_bridge \
		$(APB_CDC_BRIDGE_SOURCES)

apb_cdc_bridge: $(call sp_lint,apb_cdc_bridge_lint)
	$(MAKE) MODULE=test_apb_cdc_bridge TOPLEVEL=tb_apb_cdc_bridge \
		VERILOG_SOURCES="$(APB_CDC_BRIDGE_SOURCES)" \
		$(BUILD_ARGS)

# cdc_sync RESET_VAL lint + sim.
cdc_sync_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_cdc_sync \
		$(CDC_SYNC_SOURCES)

# Negative control: STAGES < 2 must fail elaboration (the generate-scope
# $fatal in the primitive). Verilator is run on the bare primitive with
# STAGES overridden to 1; the step passes only if it fails AND names the guard.
cdc_sync_stages1_neg:
	@out=$$(verilator --lint-only -Wall -Wno-IMPORTSTAR -GSTAGES=1 \
		--top-module cdc_sync $(RTL)/soc/cdc/cdc_sync.sv 2>&1); rc=$$?; \
	if [ $$rc -eq 0 ]; then \
		echo "FAIL: STAGES=1 elaborated cleanly"; exit 1; \
	elif echo "$$out" | grep -q "STAGES (1) must be >= 2"; then \
		echo "PASS: STAGES=1 rejected by cdc_sync elaboration guard"; \
	else \
		echo "FAIL: STAGES=1 failed for the wrong reason"; echo "$$out"; exit 1; \
	fi

cdc_sync: $(call sp_lint,cdc_sync_lint cdc_sync_stages1_neg)
	$(MAKE) MODULE=test_cdc_sync TOPLEVEL=tb_cdc_sync \
		VERILOG_SOURCES="$(CDC_SYNC_SOURCES)" \
		$(BUILD_ARGS)

# cdc_gray_fifo DEPTH=2 lint + sim.
# Lint of the wrapper (both depths) plus the bare primitive at every legal depth, so the depth-2
# generate branch and the unchanged DEPTH>=4 branch are each elaborated under -Wall.
cdc_gray_fifo_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_cdc_gray_fifo \
		$(CDC_GRAY_FIFO_SOURCES)
	@for d in 2 4 8 16; do \
		verilator --lint-only -Wall -Wno-IMPORTSTAR -GDEPTH=$$d \
			--top-module cdc_gray_fifo $(RTL)/soc/cdc/cdc_sync.sv $(CDC_GRAY_FIFO_RTL) \
			|| { echo "FAIL: cdc_gray_fifo DEPTH=$$d lint"; exit 1; }; \
		echo "PASS: cdc_gray_fifo DEPTH=$$d lint clean"; \
	done

# Negative control: illegal depths must fail elaboration through the generate-scope $fatal, and
# must name the guard (not die for an unrelated reason).
cdc_gray_fifo_depth_guard_neg:
	@for d in 0 1 3 6 12; do \
		out=$$(verilator --lint-only -Wall -Wno-IMPORTSTAR -GDEPTH=$$d \
			--top-module cdc_gray_fifo $(RTL)/soc/cdc/cdc_sync.sv $(CDC_GRAY_FIFO_RTL) 2>&1); rc=$$?; \
		if [ $$rc -eq 0 ]; then \
			echo "FAIL: DEPTH=$$d elaborated cleanly"; exit 1; \
		elif echo "$$out" | grep -q "DEPTH ($$d) must be a power of two and >= 2"; then \
			echo "PASS: DEPTH=$$d rejected by cdc_gray_fifo elaboration guard"; \
		else \
			echo "FAIL: DEPTH=$$d failed for the wrong reason"; echo "$$out"; exit 1; \
		fi; \
	done

# cdc_gray_fifo_sim is the simulation alone (no lint / guard steps): the mutation campaign
# (tools/verif/mutate_cdc_gray_fifo.py) uses it so a mutant is killed by the suite's behavioural
# checks, not merely by lint.
cdc_gray_fifo_sim:
	$(MAKE) MODULE=test_cdc_gray_fifo TOPLEVEL=tb_cdc_gray_fifo \
		VERILOG_SOURCES="$(CDC_GRAY_FIFO_SOURCES)" \
		$(BUILD_ARGS)

cdc_gray_fifo: $(call sp_lint,cdc_gray_fifo_lint cdc_gray_fifo_depth_guard_neg)
	$(MAKE) cdc_gray_fifo_sim

# SYNC_STAGES pass-through of the four peripherals that own an
# input synchroniser. One cheap latency test per family at SYNC_STAGES=3 (the default depth 2 is
# covered by each peripheral's own suite). -GSYNC_STAGES is part of the sim_build key, so each
# variant gets its own directory. Lint of each DUT already runs in its own <name>_lint target.
periph_sync_stages: $(call sp_lint,uart_lint irq_lint spi_lint gpio_lint)
	$(MAKE) MODULE=test_periph_sync_stages TOPLEVEL=uart_controller \
		VERILOG_SOURCES="$(UART_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET -GSYNC_STAGES=3" \
		SYNC_PERIPH=uart_controller EXPECT_STAGES=3 \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_periph_sync_stages TOPLEVEL=interrupt_controller \
		VERILOG_SOURCES="$(IRQ_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET -GSYNC_STAGES=3" \
		SYNC_PERIPH=interrupt_controller EXPECT_STAGES=3 \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_periph_sync_stages TOPLEVEL=spi_controller \
		VERILOG_SOURCES="$(SPI_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET -GSYNC_STAGES=3" \
		SYNC_PERIPH=spi_controller EXPECT_STAGES=3 \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_periph_sync_stages TOPLEVEL=tb_gpio \
		VERILOG_SOURCES="$(GPIO_SOURCES)" \
		EXTRA_ARGS="-Wno-SYNCASYNCNET -GSYNC_STAGES=3" \
		SYNC_PERIPH=tb_gpio EXPECT_STAGES=3 \
		$(BUILD_ARGS)

# cdc_reset_sync DFT scan-bypass lint + sim.
# lint only: cdc_reset_sync + standalone TB wrapper.
cdc_reset_sync_scan_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_cdc_reset_sync_scan \
		$(CDC_RESET_SYNC_SCAN_SOURCES)

cdc_reset_sync_scan: $(call sp_lint,cdc_reset_sync_scan_lint)
	$(MAKE) MODULE=test_cdc_reset_sync_scan TOPLEVEL=tb_cdc_reset_sync_scan \
		VERILOG_SOURCES="$(CDC_RESET_SYNC_SCAN_SOURCES)" \
		$(BUILD_ARGS)

# rv32i_clock_gate test_en (scan) lint + sim.
# The gate carries its own lint_off pragmas for the behavioural latch, so the
# plain -Wall lint below must stay clean.
clock_gate_scan_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_clock_gate_scan \
		$(CLOCK_GATE_SCAN_SOURCES)

dft_muxes_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_dft_muxes \
		$(DFT_MUXES_SOURCES)

dft_muxes: $(call sp_lint,dft_muxes_lint)
	$(MAKE) MODULE=test_dft_muxes TOPLEVEL=tb_dft_muxes \
		VERILOG_SOURCES="$(DFT_MUXES_SOURCES)" \
		$(BUILD_ARGS)

# DFT Stage 1b: JTAG TAP unit suite, dft_ctrl suite.
# Every unit test is generated once per (TCK period, system-clock period) pair, see test_jtag_tap.py.
jtag_tap_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_jtag_tap \
		$(JTAG_TAP_SOURCES)

jtag_tap: $(call sp_lint,jtag_tap_lint)
	$(MAKE) MODULE=test_jtag_tap TOPLEVEL=tb_jtag_tap \
		VERILOG_SOURCES="$(JTAG_TAP_SOURCES)" \
		$(BUILD_ARGS)

mbist_ctrl_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR --top-module tb_mbist_domain $(MBIST_CTRL_SOURCES)
	verilator --lint-only -Wall -Wno-IMPORTSTAR -GN_MEM=10 -GAW=8 -GP1_MASK=0 --top-module tb_mbist_domain $(MBIST_CTRL_SOURCES)
	verilator --lint-only -Wall -Wno-IMPORTSTAR -GN_MEM=2 -GAW=10 -GP1_MASK=1 --top-module tb_mbist_domain $(MBIST_CTRL_SOURCES)
	verilator --lint-only -Wall -Wno-IMPORTSTAR -GN_MEM=10 -GAW=8 -GP1_MASK=0 -GLOCAL_CMP=1 --top-module tb_mbist_domain $(MBIST_CTRL_SOURCES)
	verilator --lint-only -Wall -Wno-IMPORTSTAR -GN_MEM=4 -GAW=6 -GP1_MASK="4'b0101" -GLOCAL_CMP=1 --top-module tb_mbist_domain $(MBIST_CTRL_SOURCES)

# Three build points (each hashes to its own SIM_BUILD): small (every algorithm x every fault class), soc
# (two 1024-word macros, port 1 on memory 0) and cpu (ten 256-word cache SRAMs); small and cpu are built a
# second time with LOCAL_CMP = 1 (collar-local compare).
mbist_ctrl: $(call sp_lint,mbist_ctrl_lint)
	@set -e; for cfg in "small 4 6 5 0" "soc 2 10 1 0" "cpu 10 8 0 0" "small 4 6 5 1" "cpu 10 8 0 1"; do set -- $$cfg; \
	  echo "=== mbist_ctrl: $$1 (N_MEM=$$2 AW=$$3 P1_MASK=$$4 LOCAL_CMP=$$5) ==="; \
	  MBIST_CFG=$$1 MBIST_LOCAL=$$5 $(MAKE) MODULE=test_mbist_ctrl TOPLEVEL=tb_mbist_domain \
		VERILOG_SOURCES="$(MBIST_CTRL_SOURCES)" \
		EXTRA_ARGS="-GN_MEM=$$2 -GAW=$$3 -GP1_MASK=$$4 -GLOCAL_CMP=$$5" \
		$(BUILD_ARGS); \
	done

mbist_tap_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR --top-module tb_mbist_tap $(MBIST_TAP_SOURCES)

mbist_tap: $(call sp_lint,mbist_tap_lint)
	$(MAKE) MODULE=test_mbist_tap TOPLEVEL=tb_mbist_tap \
		VERILOG_SOURCES="$(MBIST_TAP_SOURCES)" \
		$(BUILD_ARGS)

mbist_soc_slice_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR +define+SRAM_SKY130 --top-module tb_mbist_soc_slice $(MBIST_SOC_SLICE_SOURCES)

mbist_soc_slice: $(call sp_lint,mbist_soc_slice_lint)
	$(MAKE) MODULE=test_mbist_soc_slice TOPLEVEL=tb_mbist_soc_slice \
		VERILOG_SOURCES="$(MBIST_SOC_SLICE_SOURCES)" \
		EXTRA_ARGS="+define+SRAM_SKY130" \
		$(BUILD_ARGS)

mbist_fi_equiv_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-DECLFILENAME --top-module tb_sram_fi_equiv $(MBIST_FI_EQUIV_SOURCES)

mbist_fi_equiv: $(call sp_lint,mbist_fi_equiv_lint)
	$(MAKE) MODULE=test_sram_fi_equiv TOPLEVEL=tb_sram_fi_equiv \
		VERILOG_SOURCES="$(MBIST_FI_EQUIV_SOURCES)" \
		$(BUILD_ARGS)

mbist_fi_equiv_1k_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-DECLFILENAME --top-module tb_sram_fi_equiv_1k $(MBIST_FI_EQUIV_1K_SOURCES)

mbist_fi_equiv_1k: mbist_fi_equiv_1k_lint
	$(MAKE) MODULE=test_sram_fi_equiv TOPLEVEL=tb_sram_fi_equiv_1k \
		VERILOG_SOURCES="$(MBIST_FI_EQUIV_1K_SOURCES)" \
		$(BUILD_ARGS)

mbist_cpu_macro_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR -Wno-DECLFILENAME -Wno-UNUSEDSIGNAL -Wno-UNUSEDPARAM -Wno-PINCONNECTEMPTY \
		+define+SRAM_SKY130 --top-module tb_mbist_cpu_macro $(MBIST_CPU_MACRO_SOURCES)

mbist_cpu_macro: $(call sp_lint,mbist_cpu_macro_lint)
	$(MAKE) MODULE=test_mbist_cpu_macro TOPLEVEL=tb_mbist_cpu_macro \
		VERILOG_SOURCES="$(MBIST_CPU_MACRO_SOURCES)" \
		EXTRA_ARGS="+define+SRAM_SKY130" \
		$(BUILD_ARGS)

dft_clk_switch_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_dft_clk_switch \
		$(DFT_CLK_SWITCH_SOURCES)

dft_clk_switch: $(call sp_lint,dft_clk_switch_lint)
	$(MAKE) MODULE=test_dft_clk_switch TOPLEVEL=tb_dft_clk_switch \
		VERILOG_SOURCES="$(DFT_CLK_SWITCH_SOURCES)" \
		$(BUILD_ARGS)

# RED negative control, deliberately NOT in soc_all / soc_all_ci: the SAME suite against
# `assign clk_o = sel_a_i ? clk_a_i : clk_b_i` (the plain mux Q-CLK replaced).  It is EXPECTED TO
# FAIL (runts, immediate switch with no handshake); a pass would mean the suite cannot tell the
# glitch-free switch from a plain mux.  Run:  make dft_clk_switch_plainmux  (exit status non-zero).
dft_clk_switch_plainmux: $(call sp_lint,dft_clk_switch_lint)
	$(MAKE) MODULE=test_dft_clk_switch TOPLEVEL=tb_dft_clk_switch \
		VERILOG_SOURCES="$(DFT_CLK_SWITCH_SOURCES)" \
		EXTRA_ARGS="-GPLAIN_MUX=1" \
		$(BUILD_ARGS)

dft_ctrl_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_dft_ctrl \
		$(DFT_CTRL_SOURCES)

dft_ctrl: $(call sp_lint,dft_ctrl_lint)
	$(MAKE) MODULE=test_dft_ctrl TOPLEVEL=tb_dft_ctrl \
		VERILOG_SOURCES="$(DFT_CTRL_SOURCES)" \
		$(BUILD_ARGS)

clock_gate_scan: $(call sp_lint,clock_gate_scan_lint)
	$(MAKE) MODULE=test_clock_gate_scan TOPLEVEL=tb_clock_gate_scan \
		VERILOG_SOURCES="$(CLOCK_GATE_SCAN_SOURCES)" \
		$(BUILD_ARGS)

# soc_pll runs test_pll_lock on the full SoC (tb_soc_pll, which exposes pll_locked_o), then pll_apb_regs.
soc_pll: $(call sp_lint,soc_pll_lint)
	$(MAKE) MODULE=test_pll_lock TOPLEVEL=tb_soc_pll \
		VERILOG_SOURCES="$(PLL_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) pll_apb_regs

# Multiclock APB_PLL2 / apb_cdc_bridge exercise on tb_soc_pll. test_soc_multiclock_pll2.py's module docstring says why
# it is a separate target from soc_multiclock. Reuses pll2_fw/pll2_decode.hex (no new firmware).
soc_pll_multiclock: $(call sp_lint,soc_pll_lint)
	$(MAKE) MODULE=test_soc_multiclock_pll2 TOPLEVEL=tb_soc_pll \
		VERILOG_SOURCES="$(PLL_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# DFT Stage 1a: soc_top test-access ports, via tb_soc_pll
# (which exposes pll_locked_o / cpu_pll_locked_o). Same sources/flags as soc_pll_multiclock.
soc_dft_scan: $(call sp_lint,soc_pll_lint)
	$(MAKE) MODULE=test_soc_dft_scan TOPLEVEL=tb_soc_pll \
		VERILOG_SOURCES="$(PLL_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# The scan_en gate (dft_scan_en = request & crypto wipe done), pin
# and TAP-serial, on the same wrapper and flags as soc_dft_scan.
soc_scan_en_gate: $(call sp_lint,soc_pll_lint)
	$(MAKE) MODULE=test_soc_scan_en_gate TOPLEVEL=tb_soc_pll \
		VERILOG_SOURCES="$(PLL_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# DFT Stage 1b: soc_top driven through the JTAG TAP (tb_soc_pll
# carries tck_i/tms_i/tdi_i/trst_ni/tdo_o/tdo_oe_o). Same sources/flags as soc_dft_scan.
soc_jtag: $(call sp_lint,soc_pll_lint)
	$(MAKE) MODULE=test_soc_jtag TOPLEVEL=tb_soc_pll \
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
soc_boot: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_boot TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M9 SoC DMA + peripheral loopback test — self-checking firmware drives DMA
# mem->mem + UART/SPI internal loopback via CPU MMIO; scoreboards PASS_PC/FAIL_PC.
soc_periph: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_periph_loopback TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Diagnostic boot test — dumps fetch-path signals for 300 cycles.
.PHONY: soc_boot_diag
soc_boot_diag:
	$(MAKE) MODULE=test_boot_diag TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET"

# M9 software-managed coherency test — CPU flush+GPU launch+CPU inval end-to-end.
# Verifies CSRW 0x7C0 (dcache_flush) and CSRW 0x7C1 (dcache_inval) under real
# GPU kernel execution.
# Firmware: coherency_fw/coherency_fw.hex (generated by gen_coherency_hex.py).
# Tests: test_coherency_pass (positive), test_coherency_no_flush (negative),
#        test_coherency_no_inval (negative/warn if dst lines cold).
soc_coherency: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_coherency TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M9 CPU-GPU interrupt integration test.
# IRQ-driven counterpart to soc_coherency: CPU enables GPU IRQ via
# interrupt_controller (IRQ_MASK bit 4), launches kernel, waits in a bounded
# spin loop until the ISR fires (mtvec trap → ISR clears IRQ + sets flag +
# MRET), then reads corrected dst words and verifies src+1.
# Tests: test_cpu_gpu_irq_pass (positive), test_cpu_gpu_irq_no_irq_enable (negative).
soc_cpu_gpu: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_cpu_gpu_irq TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level GPIO test. Exercises gpio_controller (APB slave 7, 0x2000_A000) through the real fabric path: CPU -> axi4_crossbar ->
# axi4_to_axilite -> axi_lite_interconnect -> axil_to_apb -> apb_interconnect. test_gpio/tb_gpio.sv drives the APB4 face directly.
# gpio_controller.sv is already in SOC_BOOT_SOURCES, so this reuses soc_boot_lint as its hard prerequisite, like soc_periph,
# soc_coherency and soc_cpu_gpu. Tests: output path, input path (3-clock-edge sync latency) and the GPIO ->
# interrupt_controller[5] -> CPU MEIP interrupt path end to end (the CPU takes the trap; GPIO_IRQ_CLR deasserts it).
soc_gpio: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_gpio TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# UART boot-ROM bootloader: the real bootloader image from sw/bootloader/prebuilt/
# is backdoor-loaded into boot_rom and driven over uart_rx_i by a bit-level UART model.
# Rebuild the images (needs the nix #bench toolchain):  make -C sw/bootloader prebuilt
soc_uart_boot: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_uart_boot TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level PWM test. Exercises pwm_controller (APB slave 8, 0x2000_B000) through the same fabric path as soc_gpio;
# test_pwm/tb_pwm.sv drives the APB4 face directly. pwm_controller.sv is already in SOC_BOOT_SOURCES, so this reuses
# soc_boot_lint as its hard prerequisite, like soc_gpio. Tests: boundary toggle (pwm_o free-runs at the configured
# period and duty once channel 0 is enabled, so no cocotb stimulus is needed) and the PWM -> interrupt_controller[6] ->
# CPU MEIP interrupt path end to end (PWM_IRQ_CLR + PWM_IRQ_EN=0 deassert it).
soc_pwm: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_pwm TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level WDT test. Exercises watchdog_timer (APB slave 9, 0x2000_C000) through the same fabric path as soc_gpio, plus what exists
# only inside soc_top: the WDT -> interrupt_controller[7] -> CPU MEIP path and the bite -> CPU-domain reset path
# (u_cpu_wdt_rst_sync). Three tests on two hand-assembled images (wdt_fw/gen_wdt_hex.py, no cross toolchain, CI-safe): feed-then-starve
# with RST_EN=0 (bark trap, bite trap, wdt_rst_req_o at the boundary, cpu_domain_rst_n never falls), RST_EN=1 (bite resets the
# CPU domain only), and recovery after an external reset. It reuses soc_boot_lint, like soc_pwm.
soc_wdt: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_wdt TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level TRNG test. Exercises trng (APB slave 10, 0x2000_D000) through the same fabric path as soc_gpio, plus the
# trng -> interrupt_controller[8] -> CPU MEIP path. One test, one hand-assembled image (trng_fw/gen_trng_hex.py, no cross
# toolchain, CI-safe): a polled phase with the popped words checked value-exact against tb/models/trng_lfsr_model.py and
# TRNG_STATUS[3] (INSECURE) read back, then an interrupt-driven phase. trng.sv and trng_lfsr_entropy.sv are in SOC_BOOT_SOURCES
# and TRNG adds no top-level pins, so this reuses soc_boot_lint, like soc_wdt.
soc_trng: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_trng TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level I2C test. Exercises i2c_controller (APB slave 11, 0x2000_E000) through the same fabric path as soc_gpio.
# Two tests, two hand-assembled images (i2c_fw/gen_i2c_hex.py, no cross toolchain, CI-safe): test_soc_i2c uses the internal
# loopback (I2C_CTRL[1]) and the i2c -> interrupt_controller[9] -> CPU MEIP path; test_soc_i2c_real_pads drives the real pads
# against tb/cocotb/bfm/i2c_slave.py. Full protocol coverage is the L1 `i2c` suite. i2c_controller.sv is in SOC_BOOT_SOURCES
# and tb_soc_top.sv exposes the i2c_* pins, so this reuses soc_boot_lint.
soc_i2c: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_i2c TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level crypto fabric test. Exercises crypto_accel (APB slave 12, 0x2000_F000) through the same fabric path as soc_gpio, plus the
# crypto -> interrupt_controller[10] -> CPU MEIP path. Deliberately cheap: a few FIPS-197 / FIPS 180-4 known answers read back over
# the bus. The behaviour of the peripheral itself is the L1 `crypto` suite. One test, one hand-assembled image
# (crypto_fw/gen_crypto_hex.py, no cross toolchain, CI-safe). The crypto RTL is in SOC_BOOT_SOURCES and crypto has no pins,
# so this reuses soc_boot_lint.
soc_crypto: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_crypto TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level NPU fabric test. Exercises npu_top (APB slave 13, 0x2001_0000) through the same fabric path as soc_gpio, plus the
# npu -> interrupt_controller[11] -> CPU MEIP path. Deliberately cheap: three small INT8 inferences (polled, interrupt driven
# with ReLU, illegal START) read back over the bus. The behaviour of the peripheral itself is the L1 `npu` suite. One test, one
# hand-assembled image (npu_fw/gen_npu_hex.py, no cross toolchain, CI-safe). The NPU RTL is in SOC_BOOT_SOURCES and the NPU has
# no pins, so this reuses soc_boot_lint.
soc_npu: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_npu TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# GPIO driver test: proves sw/drivers/gpio.h by RUNNING a compiled C program (sw/bench/gpio_demo.c) on the SoC. soc_gpio proves
# the RTL with committed firmware instead. This target reuses soc_boot_lint (no separate gpio_driver_lint) and passes
# SRAM_MEM_WORDS=65536 like l2_bench: gpio_demo.c links via sw/bench/rv32i.ld, whose stack top (0x41C00) assumes that window.
# It consumes sw/bench/build/{trampoline,gpio_demo}.{hex,sym} and does NOT rebuild them:
#   nix develop <repo>#bench --command make -C sw/bench
# In soc_all, NOT in soc_all_ci: CI has no riscv32 cross-toolchain step and sw/bench/build is gitignored. l2_bench is in neither.
gpio_driver: $(call sp_lint,soc_boot_lint)
	@test -f $(PROJ_ROOT)/sw/bench/build/gpio_demo.hex -a \
	      -f $(PROJ_ROOT)/sw/bench/build/trampoline.hex || { \
		echo "ERROR: sw/bench/build/{gpio_demo,trampoline}.hex missing."; \
		echo "       This target needs the riscv32 cross toolchain. Build first:"; \
		echo "         nix develop $(PROJ_ROOT)#bench --command make -C sw/bench"; \
		exit 1; }
	$(MAKE) MODULE=test_gpio_driver TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET \
		  -GSRAM_MEM_WORDS=65536" \
		$(BUILD_ARGS)

# Multiclock SoC CDC exercise. Drives clk_i (fabric) and cpu_clk_i (CPU) at a genuinely asynchronous ratio (see
# test_soc_multiclock.py's module docstring) to prove the CPU<->fabric CDC (async_axi_fifo and the ext_irq / timer_irq /
# pmu_cpu_* cdc_sync synchronisers in soc_top.sv) works when the domains are not clock-aligned. Reuses boot_fw/boot.hex,
# periph_fw/periph_loopback.hex and cpu_gpu_irq_fw/cpu_gpu_irq_fw.hex (no new firmware), the SOC_BOOT_SOURCES list and
# soc_boot_lint. It is in soc_all_ci and also runs standalone.
soc_multiclock: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_multiclock TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level reset-asymmetry class: hold one physical domain's reset input low for an extended, deliberate window (well beyond
# ordinary PLL-lock skew) while the other domain is released and free-running, offering real traffic through u_cpu_axi_cdc.
# See test_soc_multiclock_reset.py's module docstring for the rationale. Reuses boot_fw/boot.hex (no new firmware).
# Same DUT, source list and lint gate as soc_multiclock.
soc_multiclock_reset: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_multiclock_reset TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# PMU-driven live CPU-domain power-cycle at a divergent clock ratio; see test_soc_pmu_multiclock.py's module docstring (firmware
# programs the DMA to write PMU CTRL=CPU_OFF on the CPU's behalf, and the testbench supplies the power-up trigger, because the
# CPU cannot write its own wake register once gated). Firmware: pmu_cycle_fw/pmu_cycle.hex (generated by gen_pmu_cycle_hex.py),
# new for this suite. Same DUT, source list and lint gate as soc_multiclock.
soc_pmu_multiclock: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_pmu_multiclock TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# PMU / soc_top isolation-before-reset ordering (iso-ack handshake) at CPU clocks 3x and 8x
# SLOWER than the fabric (the ratios where the old 2-flop clamp lost the race to the async PMU reset),
# 1:1 and faster; the stale-ack guard on back-to-back power cycles; a dead CPU clock (the handshake
# must time out, not hang the PMU); and the ISO_GPU clamps incl. m_axil_if_rready.  Power
# cycles are driven by a backdoor write of PMU CTRL, so no firmware.  Same DUT/source list/lint gate
# as soc_pmu_multiclock.
soc_pmu_iso_ack: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_pmu_iso_ack TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# SoC-level integration gaps: the peripheral IRQ lines + CPU traps (timer/UART/SPI/DMA), the SPI MISO input against a testbench
# slave, both PLLs' divider registers through the fabric, GPU isolation via a PMU power cycle, and the external APB debug master
# (halt/GPR/step, RO-register PSLVERR, and the apb_cdc_bridge force-complete PSLVERR with the destination in reset), plus register,
# DMA and GPU walks. Firmware: integ_fw/gen_integ_hex.py (hand-assembled, no cross toolchain -- CI-safe).
# Same DUT/source list/lint gate as soc_pmu_multiclock.
soc_integration: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_soc_integration TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M9 SoC stress + benchmark test. Self-checking firmware (stress_fw/gen_stress_hex.py, run first) does STRESS_ITER outer loops of
# CPU burst, DMA, GPU kernel, UART/SPI loopback and timer work.
# Do not add --trace or WAVES=1: a trace of this run fills the disk. Keep this target out of soc_all and soc_all_ci because
# it runs long; run it with `make soc_stress`.
soc_stress: $(call sp_lint,soc_boot_lint)
	/usr/bin/python3 $(SOC_DIR)/stress_fw/gen_stress_hex.py
	$(MAKE) MODULE=test_soc_stress TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M10 L2-cache decision benchmark. Loads bare-metal C benchmarks (hello / sweep / matmul) onto the full SoC with
# SRAM_MEM_WORDS=65536 (256 KB window) and reads perf-counter scratch slots after EBREAK to compute I$/D$-miss rates.
# Firmware is pre-built by `nix develop .#bench --command make -C sw/bench`; this target consumes the build/ outputs
# and does NOT rebuild the C code. No --trace: miss-rate runs can be long and a VCD is wasteful here.
# Not in soc_all or soc_all_ci: it is a benchmark, not a pass/fail regression, and it needs the cross-built sw/bench/build hexes.
l2_bench_lint:
	verilator --lint-only -Wall -Wno-fatal -Wno-IMPORTSTAR \
		-Wno-UNUSEDSIGNAL -Wno-UNOPTFLAT -Wno-SYNCASYNCNET \
		-Wno-DECLFILENAME -Wno-UNUSEDPARAM -Wno-BLKSEQ \
		-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		--top-module tb_soc_top \
		$(SOC_BOOT_SOURCES)

l2_bench: $(call sp_lint,l2_bench_lint)
	$(MAKE) MODULE=test_l2_bench TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET \
		  -GSRAM_MEM_WORDS=65536" \
		TESTCASE=test_hello_sanity,test_sweep_l2_bench \
		$(BUILD_ARGS)

# soc_all = soc_all_ci + gpio_driver. soc_all_ci is every suite that needs nothing beyond this repo and the
# nix sim devshell. CI runs it, and PASS_FLOOR is measured against it. gpio_driver also needs the riscv32-none-elf cross toolchain
# to have built sw/bench/build/*.hex (nix develop <repo>#bench --command make -C sw/bench), so run soc_all locally as the final gate
# before a push. Keep a toolchain-dependent suite out of soc_all_ci: CI has no cross-toolchain step, and such a suite dies in
# _parse_hex() with a FileNotFoundError. soc_stress and l2_bench are in neither target (long runtime). Builds go into
# content-keyed sim_build dirs, so no per-suite purge is needed. Use `make distclean` to sweep every build dir.
soc_all: soc_all_ci
	$(MAKE) gpio_driver

# The ordered list of `soc_all_ci` sub-make invocations lives in ONE variable. An entry is the sub-make's arguments joined with ':'
# (`sram_controller:SRAM_TARGET=sky130` is `$(MAKE) sram_controller SRAM_TARGET=sky130`). It feeds soc_all_ci (every entry, in order),
# soc_ci_shard (a subset, same relative order) and print-soc-ci-suites (one entry per line, for tools/verif/soc_shards.py and the CI
# union check). Add a new CI suite HERE, once: the sharded workflows pick it up. Put no comment line inside the variable block,
# because soc_shards.py parses its raw text.
SOC_CI_SUITES := \
    crossbar \
    register_bank \
    axil_interconnect \
    axil_apb_fabric \
    sram_controller \
    sram_controller:SRAM_TARGET=sky130 \
    axi4_to_axilite \
    axilite_to_axi4 \
    boot_rom \
    dma \
    irq \
    timer \
    uart \
    spi \
    apb4_register_bank \
    axil_to_apb \
    pmu \
    gpio \
    pwm \
    wdt \
    trng \
    i2c \
    crypto \
    npu \
    apb_interconnect \
    async_axi_fifo \
    apb_cdc_bridge \
    cdc_reset_sync_scan \
    cdc_sync \
    cdc_gray_fifo \
    periph_sync_stages \
    clock_gate_scan \
    dft_muxes \
    jtag_tap \
    dft_clk_switch \
    dft_ctrl \
    mbist_fi_equiv \
    mbist_fi_equiv_1k \
    mbist_ctrl \
    mbist_tap \
    mbist_soc_slice \
    mbist_cpu_macro \
    soc_boot \
    soc_periph \
    soc_coherency \
    soc_cpu_gpu \
    soc_gpio \
    soc_pwm \
    soc_wdt \
    soc_trng \
    soc_i2c \
    soc_crypto \
    soc_npu \
    soc_uart_boot \
    soc_pll \
    soc_multiclock \
    soc_multiclock_reset \
    soc_pll_multiclock \
    soc_dft_scan \
    soc_scan_en_gate \
    soc_jtag \
    soc_pmu_multiclock \
    soc_pmu_iso_ack \
    soc_integration

# Suites whose ONE module is too heavy for a single shard are run as several TESTCASE slices when
# sharded (never by soc_all_ci, which runs the whole module).  `suite=slice|slice|...`, a slice is
# a comma-separated list of the module's cocotb test names.  soc_uart_boot is the one split suite; its slices are balanced on the
# run times in tools/verif/soc_shard_weights.json.
# Every @cocotb.test of the module must appear in exactly one slice: tb/tests/test_soc_shards.py
# checks that against the test file, so a new test cannot silently fall out of the sharded run.
SOC_CI_SPLITS := \
    soc_uart_boot=test_load_verify_jump_and_run|test_load_verify_8n1_back_to_back|test_bad_crc_is_nakked_and_memory_untouched,test_refusals_nak_with_the_right_code,test_banner_and_info_default_115200_at_50mhz|test_table_sum_is_independent,test_banner_and_info_sim_divisor,test_oversized_length_nak_then_resync,test_truncated_frame_times_out_and_recovers,test_line_noise_before_sof_is_ignored,test_autoboot_runs_preloaded_image,test_autoboot_refuses_empty_sram_and_stays_serviceable

define soc_nl


endef
# `$(call soc_run_suites,<entries>)` expands to one recipe line per entry, each exactly the line
# soc_all_ci used to spell out by hand.
soc_run_suites = $(foreach s,$(1),+$(MAKE) $(subst :, ,$(s))$(soc_nl))

soc_all_ci: check-space
	$(call soc_run_suites,$(SOC_CI_SUITES))

.PHONY: print-soc-ci-suites
print-soc-ci-suites:
	@$(foreach s,$(SOC_CI_SUITES),echo '$(s)';)

# Run a subset of the soc_all_ci list (a CI shard). Select it explicitly,
#   make soc_ci_shard SUITES="crossbar soc_boot sram_controller:SRAM_TARGET=sky130"
# or by index, using the balanced assignment of tools/verif/soc_shards.py (weights: tools/verif/soc_shard_weights.json):
#   make soc_ci_shard SHARD=1 NSHARDS=5
# Each entry that ran to completion is appended to $(SOC_SUITES_RAN) (default $(SIM_BUILD_ROOT)/suites_ran.txt). The CI merge job
# compares that file with print-soc-ci-suites. A failing suite stops the shard (the results check above makes a red suite exit non-zero).
SHARD ?=
NSHARDS ?=
SOC_SUITES_RAN ?= $(SIM_BUILD_ROOT)/suites_ran.txt
# Cost model for SHARD=/NSHARDS=.  Empty = the script's default, the INSTRUMENTED
# (COVERAGE=1) timings of soc_coverage.yml.  The plain cocotb.yml shards pass the uninstrumented
# file (tools/verif/soc_shard_weights_plain.json), because instrumented and plain runs scale
# differently per suite and a balance tuned for one is poor for the other.
SOC_SHARD_WEIGHTS ?=
ifneq ($(strip $(SHARD)),)
  ifeq ($(strip $(NSHARDS)),)
    $(error SHARD=$(SHARD) needs NSHARDS=<n>)
  endif
  SUITES = $(shell $(or $(SIM_PYTHON3),python3) $(PROJ_ROOT)/tools/verif/soc_shards.py $(if $(strip $(SOC_SHARD_WEIGHTS)),--weights $(SOC_SHARD_WEIGHTS)) select --shard $(SHARD) --nshards $(NSHARDS) --suites "$(SOC_CI_SUITES)" --splits "$(SOC_CI_SPLITS)")
endif
.PHONY: soc_ci_shard
soc_ci_shard: check-space
	@test -n "$(strip $(SUITES))" || { echo "ERROR: soc_ci_shard: set SUITES=\"...\" or SHARD=<k> NSHARDS=<n>" >&2; exit 1; }
	@mkdir -p $(dir $(SOC_SUITES_RAN)) && : > $(SOC_SUITES_RAN)
	$(foreach s,$(SUITES),+$(MAKE) $(subst :, ,$(s)) && echo '$(s)' >> $(SOC_SUITES_RAN)$(soc_nl))

# The instrumented half of `soc_coverage` for ONE shard: run the shard's suites with
# COVERAGE=1 and leave the per-simulation .dat files in $(COV_DIR).  No merge and no report here;
# the sharded workflow's final job merges every shard's .dat and renders the report once.
.PHONY: soc_coverage_shard
soc_coverage_shard:
	@mkdir -p $(COV_DIR)
	rm -f $(COV_DIR)/*.dat
	$(MAKE) soc_ci_shard COVERAGE=1
	@ls $(COV_DIR)/*.dat >/dev/null 2>&1 || { echo "ERROR: soc_coverage_shard: no .dat written to $(COV_DIR) -- coverage was not collected" >&2; exit 1; }

# soc_integration_batch: run the four tb_soc_top suites (test_boot, test_periph_loopback, test_soc_coherency, test_cpu_gpu_irq) in one
# command. They pass the same TOPLEVEL, VERILOG_SOURCES, EXTRA_ARGS and BUILD_ARGS, so they hash to one SIM_BUILD and cocotb builds
# Vtop once. soc_boot, soc_periph, soc_coherency and soc_cpu_gpu run one by one share that same build dir.
.PHONY: soc_integration_batch
soc_integration_batch: $(call sp_lint,soc_boot_lint)
	$(MAKE) MODULE=test_boot TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_periph_loopback TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_soc_coherency TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) MODULE=test_cpu_gpu_irq TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/soc/cdc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# cocotb's own `clean` removes only $(SIM_BUILD), one keyed dir, so it cannot sweep the others.
# Sweep $(SIM_BUILD_ROOT), not the CWD. With the dirs relocated, a CWD-relative `rm -rf sim_build_*` deletes only the local
# symlinks and orphans the real dirs on the scratch filesystem.
.PHONY: distclean clean-sim-builds
distclean: clean-sim-builds

clean-sim-builds:
	rm -rf $(SIM_BUILD_ROOT)/sim_build $(SIM_BUILD_ROOT)/sim_build_*
	@# Also clear any stale in-tree dirs/symlinks left by an earlier SIM_BUILD_ROOT.
	rm -rf ./sim_build ./sim_build_*

# Self-test: a genuinely failing cocotb suite must make make exit non-zero. NOT in soc_all / soc_all_ci: it fails a suite on purpose.
# No committed test needs an edit: the stale-Vtop guard in test_register_bank.py (_setup) asserts that the elaborated address-bus
# width equals REGBANK_ADDR_W, so elaborating -GADDR_W=5 while claiming REGBANK_ADDR_W=12 fails every test. The sub-make has its own
# SIM_BUILD and is expected to fail. Exit 0 from it means the check_for_results_file redefinition has stopped working.
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

# Print the build directory (and, with SIM_KEY_VERBOSE=1, the exact key material) the
# sub-make for the given variables would use, without building anything.  Used by
# tb/tests/test_sim_build_key.py; handy when asking "why did this target rebuild / not share?":
#   make print-sim-build MODULE=m TOPLEVEL=tb_soc_top VERILOG_SOURCES="..." EXTRA_ARGS="..." $(BUILD_ARGS)
.PHONY: print-sim-build
print-sim-build:
	@echo "$(SIM_BUILD)"
ifdef SIM_KEY_VERBOSE
	@echo "key-material: $(SIM_KEY_MATERIAL)"
endif

# Self-test: a failing suite that REUSES another suite's build directory must still make make exit non-zero. The same register_bank
# DUT runs twice with the same compile-time inputs and a different runtime-only environment (REGBANK_ADDR_W is read by the Python
# test, never by Verilator): 12 matches the elaborated ADDR_W=12 and passes, 7 does not and fails the stale-Vtop guard in
# test_register_bank._setup. A pass proves that REGBANK_ADDR_W is runtime-only (the second run hashes to the SAME directory), that the
# second run did NOT rebuild (no verilator invocation in its output), and that the sharing does not mask its failure.
# NOT in soc_all / soc_all_ci: it fails a suite on purpose.
.PHONY: check-shared-build-failure
check-shared-build-failure:
	@echo "=== check-shared-build-failure: a failing suite in a SHARED build dir MUST fail make ==="; \
	set -e; \
	REGBANK_ADDR_W=12 $(MAKE) MODULE=test_register_bank TOPLEVEL=tb_axi_lite_register_bank \
		VERILOG_SOURCES="$(REGBANK_SOURCES)" $(BUILD_ARGS) sim; \
	out=$$(REGBANK_ADDR_W=7 $(MAKE) MODULE=test_register_bank TOPLEVEL=tb_axi_lite_register_bank \
		VERILOG_SOURCES="$(REGBANK_SOURCES)" $(BUILD_ARGS) sim 2>&1) && rc=0 || rc=$$?; \
	echo "$$out" | tail -n 5; \
	if [ "$$rc" -eq 0 ]; then \
		echo "check-shared-build-failure: FAIL -- a failing suite in a shared build dir exited 0" >&2; exit 1; \
	fi; \
	if echo "$$out" | grep -q -- '-Mdir'; then \
		echo "check-shared-build-failure: FAIL -- the second run REBUILT, so the directory was not shared" >&2; exit 1; \
	fi; \
	echo "check-shared-build-failure: PASS -- shared build reused (no rebuild) and the failing suite exited $$rc"

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

# Whole-SoC line + toggle coverage: runs the ENTIRE soc_all_ci regression with COVERAGE=1 (instrumented Vtop in its own
# sim_build_*_cov dirs, one .dat per simulation in $(COV_DIR)), merges them and renders a per-module report. NOT a prerequisite of
# soc_all_ci / soc_all: an instrumented -O0 build is much slower. soc_coverage.yml runs the sharded form (soc_coverage_shard) nightly and on a PR that edits this Makefile.
# Defined down here for the same reason as check-space: a target above the cocotb include would become the default goal.
#   make SIM_BUILD_ROOT=/nobackup/claude_sim_build/soc_cov soc_coverage
# Outputs in $(COV_DIR): per-simulation .dat files, merged.dat, coverage_report.md and .json. It fails if no .dat was produced, so an empty report cannot pass.
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

# Commercial-simulator coverage, VCS only (Xcelium's imc is not installed, and sim_portability.mk refuses COVERAGE=1 for SIM=xcelium).
# Runs the SAME soc_all_ci job list as the uninstrumented VCS regression (tools/eda/regress_specs.py soc, read from
# `make print-soc-ci-suites`, never a fork) with COVERAGE=1 at bounded parallelism (VCS_COV_JOBS; vcs_coverage.py refuses more than 3 because of host memory), merges every
# simv.vdb with ONE urg call (-flex_merge modules) and writes the report under $(VCS_COV_ROOT)/report/soc.
# Fails if a chain fails or urg reports no scores. Needs `source tools/eda/sim_env.sh` in the calling shell.
#   make SIM=vcs soc_coverage_vcs     (SIM=vcs only so this Makefile parses without a verilator binary)
VCS_COV_ROOT ?= $(PROJ_ROOT)/sim_build_cov
VCS_COV_JOBS ?= 3
.PHONY: soc_coverage_vcs
soc_coverage_vcs:
	python3 $(PROJ_ROOT)/tools/eda/vcs_coverage.py run --area soc --root $(VCS_COV_ROOT) --out $(VCS_COV_ROOT)/report --jobs $(VCS_COV_JOBS)
