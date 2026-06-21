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
	$(RTL)/soc/sram_controller.sv

DMA_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/periph/dma_engine.sv

TIMER_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/periph/timer.sv

IRQ_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/periph/interrupt_controller.sv

UART_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/periph/uart_controller.sv

SPI_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/periph/spi_controller.sv

# Phase 7 M-c: standalone pll_axil_regs unit-test sources.
# Minimal: axi_pkg + axi_lite_register_bank (dependency) + pll_axil_regs + standalone TB.
# Does NOT include the full SoC — the BFM drives s_axil_* top-level ports directly.
PLL_REGS_SOURCES = \
	$(RTL)/soc/axi_pkg.sv \
	$(RTL)/soc/axi_lite_register_bank.sv \
	$(RTL)/soc/pll/pll_axil_regs.sv \
	$(SOC_DIR)/tb_pll_axil_regs.sv

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
	$(RTL)/soc/pll/pll_clkgen_stub.sv \
	$(RTL)/soc/pll/pll_axil_regs.sv \
	$(RTL)/soc/pll/pll_clkgen.sv \
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
	$(RTL)/soc/pll/pll_clkgen_stub.sv \
	$(RTL)/soc/pll/pll_axil_regs.sv \
	$(RTL)/soc/pll/pll_clkgen.sv \
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
	BUILD_ARGS += PYTHON3=/usr/bin/python3
	# Override CXX/LINK: nix verilator generates clang++ commands but only g++
	# is available outside nix's clang environment.  cxx_shim.sh wraps g++ and
	# strips clang-only flags.
	BUILD_ARGS += CXX=$(SIM_DIR)/cxx_shim.sh
	BUILD_ARGS += LINK=$(SIM_DIR)/cxx_shim.sh
ifneq ($(wildcard /nix/store),)
	# Nix environment: nix ld.so cannot find system libs when cocotb dlopen's
	# libpython3.10.so.1.0.  Create a compat dir with symlinks to system libs.
	NIX_COMPAT_DIR := /tmp/cocotb_nix_compat
	SIM_CMD_PREFIX := mkdir -p $(NIX_COMPAT_DIR) && \
	  for _lib in libexpat.so.1 libz.so.1 libbz2.so.1.0 liblzma.so.5 libffi.so.8; do \
	    _src=$$(ldconfig -p 2>/dev/null | grep "^	$$_lib " | awk '{print $$NF}' | head -1); \
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

.PHONY: crossbar register_bank axil_interconnect sram_controller dma dma_lint timer timer_lint irq irq_lint uart uart_lint spi spi_lint soc_boot soc_periph soc_coherency soc_cpu_gpu soc_stress soc_pll soc_pll_lint soc_all verilator_lint soc_boot_lint l2_bench l2_bench_lint conflict_bench_1way conflict_bench_2way
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
		--top-module sram_controller $(SRAM_SOURCES)

sram_controller: verilator_lint
	$(MAKE) MODULE=test_sram_controller TOPLEVEL=sram_controller \
		VERILOG_SOURCES="$(SRAM_SOURCES)" \
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

# Phase 7 M-c: PLL lint gates.
# soc_pll_lint: lints tb_soc_pll (full SoC, used by test_pll_lock).
# pll_regs_lint: lints tb_pll_axil_regs (standalone, used by test_pll_regs).
soc_pll_lint:
	verilator --lint-only -Wall -Wno-fatal -Wno-IMPORTSTAR \
		-Wno-UNUSEDSIGNAL -Wno-UNOPTFLAT -Wno-SYNCASYNCNET \
		-Wno-DECLFILENAME -Wno-UNUSEDPARAM -Wno-BLKSEQ \
		-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		--top-module tb_soc_pll \
		$(PLL_SOURCES)

pll_regs_lint:
	verilator --lint-only -Wall -Wno-IMPORTSTAR \
		-I$(RTL)/soc \
		--top-module tb_pll_axil_regs \
		$(PLL_REGS_SOURCES)

# Phase 7 M-c: SoC PLL simulation targets.
# test_pll_lock (3 tests): uses full SoC tb_soc_pll — verifies PLL lock
#   signal propagation and pll_locked_o port.
# test_pll_regs (4 tests): uses standalone tb_pll_axil_regs — exercises the
#   pll_axil_regs register interface directly.  Separated from test_pll_lock
#   because the original approach (BFM on periph_axil_* in the full SoC) had
#   a structural conflict: periph_axil_arvalid is continuously driven by
#   axi4_to_axilite assigns and cannot be force-driven by cocotb value-writes
#   in Verilator.  The standalone TB exposes true input ports the BFM owns.
# clean first: stale Vtop from any prior target causes VPI root handle mismatch.
pll_regs: pll_regs_lint
	$(MAKE) clean
	$(MAKE) MODULE=test_pll_regs TOPLEVEL=tb_pll_axil_regs \
		VERILOG_SOURCES="$(PLL_REGS_SOURCES)" \
		$(BUILD_ARGS)

soc_pll: soc_pll_lint pll_regs_lint
	$(MAKE) clean
	$(MAKE) MODULE=test_pll_lock TOPLEVEL=tb_soc_pll \
		VERILOG_SOURCES="$(PLL_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)
	$(MAKE) pll_regs

soc_boot_lint:
	verilator --lint-only -Wall -Wno-fatal -Wno-IMPORTSTAR \
		-Wno-UNUSEDSIGNAL -Wno-UNOPTFLAT -Wno-SYNCASYNCNET \
		-Wno-DECLFILENAME -Wno-UNUSEDPARAM -Wno-BLKSEQ \
		-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		--top-module tb_soc_top \
		$(SOC_BOOT_SOURCES)

# M9 SoC boot test — 3 tests: PC scoreboard, SRAM sentinels, 100/100 stability.
# fr_null_20260603_052800_00 (CPU RESET_PC) fixed by rtl-design-orchestrator 2026-06-03.
# clean first: sim_build/Vtop is always named Vtop regardless of TOPLEVEL, so a
# stale binary from any prior target (e.g. spi_controller) will cause VPI root
# handle mismatch ("tb_soc_top != spi_controller").
soc_boot: soc_boot_lint
	$(MAKE) clean
	$(MAKE) MODULE=test_boot TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# M9 SoC DMA + peripheral loopback test — self-checking firmware drives DMA
# mem->mem + UART/SPI internal loopback via CPU MMIO; scoreboards PASS_PC/FAIL_PC.
# Reuses the full-SoC source list + boot lint. clean first (stale Vtop guard).
soc_periph: soc_boot_lint
	$(MAKE) clean
	$(MAKE) MODULE=test_periph_loopback TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET" \
		$(BUILD_ARGS)

# Diagnostic boot test — dumps fetch-path signals for 300 cycles.
.PHONY: soc_boot_diag
soc_boot_diag:
	$(MAKE) clean
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
	$(MAKE) clean
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
	$(MAKE) clean
	$(MAKE) MODULE=test_cpu_gpu_irq TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
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
	$(MAKE) clean
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
	$(MAKE) clean
	$(MAKE) MODULE=test_l2_bench TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET \
		  -GSRAM_MEM_WORDS=65536" \
		TESTCASE=test_hello_sanity,test_sweep_l2_bench \
		$(BUILD_ARGS)

# M10c conflict-stress benchmark (bead claude_verilog_test-u7f).
# Two separate targets — one per DCACHE_WAYS value.  Each does make clean first so
# the Verilator binary is rebuilt with the correct DCACHE_WAYS in rv32i_cache_pkg.sv.
# DCACHE_WAYS_EXPECTED is passed to the Python test so _detect_dcache_ways() can
# fall back to it if the localparam is not public in the elaborated DUT.
# The firmware binary (conflict.hex) is the same for both WAYS; it uses a 4096 B
# stride which maps to the same cache set regardless of WAYS.
# Do NOT pass --trace: conflict runs are fast but VCD is wasteful here.
conflict_bench_1way: l2_bench_lint
	$(MAKE) clean
	$(MAKE) MODULE=test_l2_bench TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET \
		  -GSRAM_MEM_WORDS=65536" \
		TESTCASE=test_conflict_l2_bench \
		DCACHE_WAYS_EXPECTED=1 \
		$(BUILD_ARGS)

conflict_bench_2way: l2_bench_lint
	$(MAKE) clean
	$(MAKE) MODULE=test_l2_bench TOPLEVEL=tb_soc_top \
		VERILOG_SOURCES="$(SOC_BOOT_SOURCES)" \
		EXTRA_ARGS="-I$(RTL)/cpu/core -I$(RTL)/mem -I$(RTL)/soc -I$(RTL)/gpu \
		  -Wno-SYNCASYNCNET \
		  -GSRAM_MEM_WORDS=65536" \
		TESTCASE=test_conflict_l2_bench \
		DCACHE_WAYS_EXPECTED=2 \
		$(BUILD_ARGS)

.PHONY: conflict_bench_1way conflict_bench_2way

# Run every SoC test: M3–M6 component suites + M9 boot + M9 periph + M9 coherency +
# M9 cpu_gpu + Phase 7 M-c PLL (lock + regs).
# Use rm -rf sim_build (not $(MAKE) clean) for each suite so that stale or
# partially-written files from a prior build — including large PCH .gch files
# that $(MAKE) clean sometimes leaves behind — are reliably purged.
# NOTE: soc_stress and l2_bench are intentionally excluded from soc_all (long runtime).
soc_all:
	rm -rf sim_build && $(MAKE) crossbar
	rm -rf sim_build && $(MAKE) register_bank
	rm -rf sim_build && $(MAKE) axil_interconnect
	rm -rf sim_build && $(MAKE) sram_controller
	rm -rf sim_build && $(MAKE) dma
	rm -rf sim_build && $(MAKE) irq
	rm -rf sim_build && $(MAKE) timer
	rm -rf sim_build && $(MAKE) uart
	rm -rf sim_build && $(MAKE) spi
	rm -rf sim_build && $(MAKE) soc_boot
	rm -rf sim_build && $(MAKE) soc_periph
	rm -rf sim_build && $(MAKE) soc_coherency
	rm -rf sim_build && $(MAKE) soc_cpu_gpu
	rm -rf sim_build && $(MAKE) soc_pll
