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

SRAM_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/soc_addr_map_pkg.sv \
	$(SRAM_CTRL_SIM_MODEL) \
	$(RTL)/soc/sram_controller.sv

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
	COMPILE_ARGS += --timescale 1ns/1ps
	COMPILE_ARGS += --public-flat-rw
	COMPILE_ARGS += --no-timing
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
BUILD_ARGS += SIM_BUILD=sim_build_$@$(if $(filter-out freepdk45,$(SRAM_TARGET)),_$(SRAM_TARGET))
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

.PHONY: crossbar register_bank axil_interconnect sram_controller dma dma_lint timer timer_lint irq irq_lint uart uart_lint spi spi_lint soc_boot soc_periph soc_coherency soc_cpu_gpu soc_stress soc_pll soc_pll_lint soc_all verilator_lint soc_boot_lint l2_bench l2_bench_lint apb4_register_bank apb4_register_bank_lint axil_to_apb axil_to_apb_lint pmu pmu_lint async_axi_fifo async_axi_fifo_lint soc_multiclock soc_multiclock_reset soc_pll_multiclock apb_cdc_bridge apb_cdc_bridge_lint soc_pmu_multiclock cdc_reset_sync_scan cdc_reset_sync_scan_lint
crossbar:
	$(MAKE) MODULE=test_crossbar TOPLEVEL=tb_axi4_crossbar \
		$(BUILD_ARGS)

register_bank:
	$(MAKE) MODULE=test_register_bank TOPLEVEL=tb_axi_lite_register_bank \
		VERILOG_SOURCES="$(REGBANK_SOURCES)" \
		$(BUILD_ARGS)

axil_interconnect:
	$(MAKE) MODULE=test_axil_interconnect TOPLEVEL=tb_axi_lite_interconnect \
		VERILOG_SOURCES="$(AXIL_SOURCES)" \
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

spi_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module spi_controller $(SPI_SOURCES)

spi: spi_lint
	$(MAKE) MODULE=test_spi TOPLEVEL=spi_controller \
		VERILOG_SOURCES="$(SPI_SOURCES)" \
		$(BUILD_ARGS)

# APB migration PR-1: apb4_register_bank lint + sim.
apb4_register_bank_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		--top-module tb_apb4_register_bank $(APB4_REG_SOURCES)

apb4_register_bank: apb4_register_bank_lint
	$(MAKE) MODULE=test_apb4_register_bank TOPLEVEL=tb_apb4_register_bank \
		VERILOG_SOURCES="$(APB4_REG_SOURCES)" \
		$(BUILD_ARGS)

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
soc_all:
	$(MAKE) crossbar
	$(MAKE) register_bank
	$(MAKE) axil_interconnect
	$(MAKE) sram_controller
	$(MAKE) sram_controller SRAM_TARGET=sky130
	$(MAKE) dma
	$(MAKE) irq
	$(MAKE) timer
	$(MAKE) uart
	$(MAKE) spi
	$(MAKE) apb4_register_bank
	$(MAKE) axil_to_apb
	$(MAKE) pmu
	$(MAKE) async_axi_fifo
	$(MAKE) apb_cdc_bridge
	$(MAKE) cdc_reset_sync_scan
	$(MAKE) soc_boot
	$(MAKE) soc_periph
	$(MAKE) soc_coherency
	$(MAKE) soc_cpu_gpu
	$(MAKE) soc_pll
	$(MAKE) soc_multiclock
	$(MAKE) soc_multiclock_reset
	$(MAKE) soc_pll_multiclock
	$(MAKE) soc_pmu_multiclock

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
.PHONY: distclean
distclean:
	rm -rf sim_build sim_build_*
