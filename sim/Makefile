# Makefile for RV32I CPU cocotb simulation
# Uses Verilator by default
#
# NOTE: For simulation tests, run this Makefile in WSL:
#   From Windows: wsl bash -c "cd \$(wslpath '\$(pwd)') && make test"
#   From WSL: make test
#
# For lint check, can run from Windows or WSL:
#   make lint

# Ensure ~/.local/bin is in PATH for cocotb-config
export PATH := $(HOME)/.local/bin:$(PATH)

# Paths
PROJ_ROOT := $(shell cd .. && pwd)
RTL_DIR := $(PROJ_ROOT)/rtl
TB_DIR := $(PROJ_ROOT)/tb
SIM_DIR := $(PROJ_ROOT)/sim

# DUT configuration
DUT := rv32i_cpu_top
TOPLEVEL := $(DUT)

# Default test module (can be overridden on command line)
MODULE ?= tb.cocotb.cpu.test_smoke

# All available test modules
TEST_MODULES := \
	tb.cocotb.cpu.test_smoke \
	tb.cocotb.cpu.test_c_programs \
	tb.cocotb.cpu.test_axi_protocol \
	tb.cocotb.cpu.test_debug_if \
	tb.cocotb.cpu.test_isa_uvm \
	tb.cocotb.cpu.test_fault_injection \
	tb.cocotb.cpu.test_pipeline_hazards \
	tb.cocotb.cpu.test_interrupts

# RTL source files (Phase 3: 5-stage pipeline + I-cache + D-cache)
# Packages must appear first so Verilator can resolve them.
#
# SRAM model selection — mirrors the `ifdef SRAM_SKY130 switch in cache RTL:
#   SRAM_TARGET=freepdk45 (default): OpenRAM FreePDK45 model, no define needed
#   SRAM_TARGET=sky130             : Sky130 behavioral model, adds +define+SRAM_SKY130
#
# Examples:
#   make lint                          # FreePDK45 (default)
#   make lint SRAM_TARGET=sky130       # Sky130
#   make test SRAM_TARGET=sky130       # run full suite against sky130 SRAM
SRAM_TARGET ?= freepdk45

ifeq ($(SRAM_TARGET),sky130)
    SRAM_SIM_MODEL := $(SIM_DIR)/sky130_sram_1kbyte_1rw1r_32x256_8.sv
    COMPILE_ARGS   += +define+SRAM_SKY130
else
    SRAM_SIM_MODEL := $(SIM_DIR)/sram_1rw_256x32_verilator.v
endif

VERILOG_SOURCES := \
	$(SRAM_SIM_MODEL) \
	$(RTL_DIR)/soc/axi_pkg.sv \
	$(RTL_DIR)/cpu/core/rv32i_pipeline_pkg.sv \
	$(RTL_DIR)/mem/rv32i_cache_pkg.sv \
	$(RTL_DIR)/cpu/core/rv32i_alu.sv \
	$(RTL_DIR)/cpu/core/rv32i_imm_gen.sv \
	$(RTL_DIR)/cpu/core/rv32i_regfile.sv \
	$(RTL_DIR)/cpu/core/rv32i_decode.sv \
	$(RTL_DIR)/cpu/core/rv32i_branch_comp.sv \
	$(RTL_DIR)/cpu/core/rv32i_hazard_unit.sv \
	$(RTL_DIR)/cpu/core/rv32i_forwarding_unit.sv \
	$(RTL_DIR)/cpu/core/rv32i_csr_file.sv \
	$(RTL_DIR)/cpu/core/rv32i_interrupt_ctrl.sv \
	$(RTL_DIR)/mem/rv32i_icache.sv \
	$(RTL_DIR)/mem/rv32i_dcache.sv \
	$(RTL_DIR)/mem/rv32i_cache_arbiter.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_if.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_id.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex1b.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex1c.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex2.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(RTL_DIR)/cpu/core/rv32i_core.sv \
	$(RTL_DIR)/cpu/rv32i_cpu_top.sv

# Cache-only sources (for cache unit tests with a single cache DUT)
# axi_pkg.sv must appear first: rv32i_icache.sv and rv32i_dcache.sv both
# `import axi_pkg::*` for burst constants (AXI_LEN_LINE, AXI_SIZE_4B, etc.)
# added in Phase 5 M2 burst upgrade.
CACHE_SOURCES := \
	$(SRAM_SIM_MODEL) \
	$(RTL_DIR)/soc/axi_pkg.sv \
	$(RTL_DIR)/mem/rv32i_cache_pkg.sv \
	$(RTL_DIR)/mem/rv32i_icache.sv \
	$(RTL_DIR)/mem/rv32i_dcache.sv \
	$(RTL_DIR)/mem/rv32i_cache_arbiter.sv

# GPU sources — package first, then leaf modules, then integration top
# Unit tests that target a single GPU module use a subset of these.
GPU_PKG := $(RTL_DIR)/gpu/gpu_pkg.sv
# Behavioral sim model for the GPU shared-memory SRAM banks (synthesis/P&R use
# the pnr/asap7 blackbox stub + LEF/Liberty instead).
GPU_SRAM_SIM := $(SIM_DIR)/sram_1rw_128x32_asap7.v
GPU_SOURCES := \
	$(GPU_PKG) \
	$(GPU_SRAM_SIM) \
	$(RTL_DIR)/gpu/vector_register_file.sv \
	$(RTL_DIR)/gpu/vector_alu.sv \
	$(RTL_DIR)/gpu/gpu_compute_unit.sv \
	$(RTL_DIR)/gpu/warp_scheduler.sv \
	$(RTL_DIR)/gpu/gpu_command_queue.sv \
	$(RTL_DIR)/gpu/gpu_memory_unit.sv \
	$(RTL_DIR)/gpu/memory_coalescer.sv \
	$(RTL_DIR)/gpu/shared_memory.sv \
	$(RTL_DIR)/gpu/gpu_top.sv

# Simulator selection (default: verilator)
SIM ?= verilator

# Verilator-specific flags
ifeq ($(SIM),verilator)
	EXTRA_ARGS += --trace --trace-structs
	COMPILE_ARGS += -Wno-fatal
	COMPILE_ARGS += -Wno-WIDTH
	COMPILE_ARGS += -Wno-CASEINCOMPLETE
	COMPILE_ARGS += -Wno-TIMESCALEMOD
	COMPILE_ARGS += --timescale 1ns/1ps
	COMPILE_ARGS += --public-flat-rw
	COMPILE_ARGS += --no-timing
	COMPILE_ARGS += -I$(RTL_DIR)/cpu/core
	COMPILE_ARGS += -I$(RTL_DIR)/mem
	COMPILE_ARGS += -I$(RTL_DIR)/gpu
	# Override PYTHON3 so the nix-verilator's verilated.mk uses the system Python 3.10
	# (/usr/bin/python3) instead of the nix-devshell Python 3.11. Inside nix-shell,
	# `which python3` resolves to nix Python 3.11, but PYTHONHOME=/usr is set in the
	# outer environment pointing to Python 3.10 stdlib; the mismatch crashes
	# verilator_includer. Hardcoding /usr/bin/python3 guarantees the version matches.
	BUILD_ARGS += PYTHON3=/usr/bin/python3
	# Override CXX/LINK: nix verilator generates Vtop.mk with CXX=clang++ but
	# only g++ is available on this host outside nix's clang environment.
	# cxx_shim.sh (in this directory) wraps g++ and strips clang-only flags
	# (-fbracket-depth, -Qunused-arguments, -fcf-protection, -Wno-non-pod-varargs,
	#  -Wno-overloaded-virtual, -Wno-parentheses-equality, -Wno-c++11-narrowing,
	#  -Wno-constant-logical-operand, -Wno-tautological-*) and drops -include-pch
	# (Vtop.cpp has explicit #include "Vtop__pch.h" so normal include suffices).
	BUILD_ARGS += CXX=$(SIM_DIR)/cxx_shim.sh
	BUILD_ARGS += LINK=$(SIM_DIR)/cxx_shim.sh
ifneq ($(wildcard /nix/store),)
	# Nix environment only: the nix ld.so can't find system libs (expat, zlib,
	# etc.) when cocotb dlopen's libpython3.10.so.1.0 (not in its trusted dirs).
	# Fix: create a compat dir with symlinks to the required system libs and
	# export LD_LIBRARY_PATH before exec'ing Vtop so all cocotb env vars
	# (COCOTB_TEST_MODULES etc.) that the cocotb Makefile sets as shell-variable
	# assignments are still visible to the simulator subprocess.
	NIX_COMPAT_DIR := /tmp/cocotb_nix_compat
	SIM_CMD_PREFIX := mkdir -p $(NIX_COMPAT_DIR) && \
	  for _lib in libexpat.so.1 libz.so.1 libbz2.so.1.0 liblzma.so.5 libffi.so.8; do \
	    _src=$$(ldconfig -p 2>/dev/null | grep "^	$$_lib " | awk '{print $$NF}' | head -1); \
	    [ -n "$$_src" ] && ln -sf "$$_src" $(NIX_COMPAT_DIR)/$$_lib 2>/dev/null || true; \
	  done && \
	  export LD_LIBRARY_PATH=$(NIX_COMPAT_DIR):$${LD_LIBRARY_PATH} &&
endif
ifdef COVERAGE
	COMPILE_ARGS += --coverage
	EXTRA_ARGS   += --coverage
endif
endif

# Questa-specific flags
ifeq ($(SIM),questa)
	COMPILE_ARGS += -timescale=1ns/1ps
	EXTRA_ARGS += -voptargs=+acc
endif

# Python path
export PYTHONPATH := $(PROJ_ROOT):$(PYTHONPATH)

# Cocotb configuration
export COCOTB_REDUCED_LOG_FMT=1

# ============================================================================
# Standalone Targets (work without cocotb)
# ============================================================================

.PHONY: help lint distclean

help:
	@echo "RV32I CPU Simulation Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  make test         - Run all cocotb tests (requires WSL)"
	@echo "  make sim          - Run single test module (requires WSL)"
	@echo "  make waves        - Open waveform viewer (gtkwave)"
	@echo "  make lint         - Run Verilator lint check"
	@echo "  make axi          - Run AXI protocol tests only"
	@echo "  make debug        - Run APB3 debug interface tests only"
	@echo "  make hazards      - Run Phase 2 pipeline hazard tests only"
	@echo "  make interrupts   - Run Phase 2 interrupt and CSR tests only"
	@echo "  make icache       - Run Phase 3 I-cache unit tests"
	@echo "  make dcache       - Run Phase 3 D-cache unit tests"
	@echo "  make cache_integration - Run Phase 3 CPU+cache integration tests"
	@echo "  make phase3_all   - Run all Phase 3 cache tests"
	@echo "  make gpu_regfile  - Run Phase 4 vector_register_file unit tests"
	@echo "  make gpu_alu      - Run Phase 4 vector_alu unit tests"
	@echo "  make gpu_diverge  - Run Phase 4 gpu_compute_unit divergence tests"
	@echo "  make gpu_sched    - Run Phase 4 warp_scheduler unit tests"
	@echo "  make gpu_cmdq     - Run Phase 4 gpu_command_queue unit tests"
	@echo "  make gpu_coalescer - Run Phase 4 memory_coalescer unit tests"
	@echo "  make gpu_shmem    - Run Phase 4 shared_memory unit tests"
	@echo "  make gpu_unit     - Run all Phase 4 GPU unit tests"
	@echo "  make gpu_kernels  - Run all Phase 4 GPU kernel tests"
	@echo "  make gpu_handoff  - Run Phase 4 CPU-GPU handoff integration test"
	@echo "  make gpu_all      - Run all Phase 4 GPU tests"
	@echo "  make coverage     - Run all tests with Verilator coverage + generate reports"
	@echo "  make distclean    - Clean simulation artifacts"
	@echo "  make help         - Show this help"
	@echo ""
	@echo "Variables:"
	@echo "  SIM=<simulator>       - Select simulator (verilator, questa, icarus)"
	@echo "  MODULE=<module>       - Select specific test module for 'make sim'"
	@echo ""
	@echo "Available test modules:"
	@echo "  $(TEST_MODULES)"
	@echo ""
	@echo "Examples (from WSL):"
	@echo "  make lint"
	@echo "  make test"
	@echo "  make sim MODULE=tb.cocotb.cpu.test_smoke"
	@echo "  make test SIM=questa"
	@echo ""
	@echo "Examples (from Windows - run from sim/ directory):"
	@echo "  wsl bash -c \"cd \$$(wslpath '\$$(pwd)') && make test\""
	@echo "  wsl bash -c \"cd \$$(wslpath '\$$(pwd)') && make sim MODULE=tb.cocotb.cpu.test_smoke\""
	@echo ""
	@echo "Note: Simulation tests must be run in WSL environment"

lint:
	@echo "Running Verilator lint check..."
	@command -v verilator >/dev/null 2>&1 || { echo "ERROR: Verilator not found. Install with: sudo apt-get install verilator, or run from WSL"; exit 1; }
	@verilator --lint-only -Wall -Wno-fatal \
		--top-module $(DUT) \
		-I$(RTL_DIR)/cpu/core \
		-I$(RTL_DIR)/mem \
		-I$(RTL_DIR)/soc \
		-Wno-IMPORTSTAR \
		-Wno-UNUSEDSIGNAL \
		-Wno-UNOPTFLAT \
		$(VERILOG_SOURCES) 2>&1

# ============================================================================
# Cocotb Targets (require cocotb installation in WSL)
# ============================================================================

# Only include cocotb makefiles if we're actually running a simulation target
# This prevents errors when running 'make help' or 'make lint' from Windows
ifneq ($(filter test sim regression results.xml,$(MAKECMDGOALS)),)
    # Check if cocotb-config exists (check PATH and common install locations)
    COCOTB_CONFIG := $(shell which cocotb-config 2>/dev/null)

    ifeq ($(COCOTB_CONFIG),)
        COCOTB_CONFIG := $(shell test -f $(HOME)/.local/bin/cocotb-config && echo $(HOME)/.local/bin/cocotb-config)
    endif

    ifeq ($(COCOTB_CONFIG),)
        $(error cocotb not found. Please run this in WSL with cocotb installed: pip install cocotb)
    endif

    # Include cocotb makefiles
    include $(shell $(COCOTB_CONFIG) --makefiles)/Makefile.sim
endif

.PHONY: all test waves

all: test

test:
	@echo "Running all cocotb tests with $(SIM)..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	@failed_tests=""; \
	for module in $(TEST_MODULES); do \
		echo "========================================"; \
		echo "Running test: $$module"; \
		echo "========================================"; \
		if ! $(MAKE) sim MODULE=$$module; then \
			failed_tests="$$failed_tests $$module"; \
		fi; \
		slug=$$(echo $$module | tr '.' '_'); \
		cp -f $(SIM_DIR)/coverage.dat \
		       $(SIM_DIR)/coverage_$${slug}.dat 2>/dev/null || true; \
		echo ""; \
	done; \
	echo "========================================"; \
	echo "Running Phase 3 cache test suites..."; \
	echo "========================================"; \
	if ! $(MAKE) phase3_all; then \
		failed_tests="$$failed_tests phase3_all"; \
	fi; \
	echo ""; \
	if [ -n "$$failed_tests" ]; then \
		echo "========================================"; \
		echo "FAILED TESTS:$$failed_tests"; \
		echo "========================================"; \
		exit 1; \
	else \
		echo "========================================"; \
		echo "ALL TESTS PASSED!"; \
		echo "========================================"; \
	fi

waves:
	@echo "Opening waveform viewer..."
	@if [ -f "dump.vcd" ]; then \
		gtkwave dump.vcd 2>/dev/null || echo "gtkwave not found. Install with: sudo apt-get install gtkwave"; \
	else \
		echo "No waveform file found. Run 'make test' first."; \
	fi

# Convenience target for AXI protocol tests only
.PHONY: axi
axi:
	@echo "Running AXI protocol tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim MODULE=tb.cocotb.cpu.test_axi_protocol

# Convenience target for APB3 debug interface tests
.PHONY: debug
debug:
	@echo "Running APB3 debug interface tests (single-step, BP0, BP1, GPR write, PC write)..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim MODULE=tb.cocotb.cpu.test_debug_if

# Convenience target for Phase 2 pipeline hazard tests
.PHONY: hazards
hazards:
	@echo "Running Phase 2 pipeline hazard tests (RAW forwarding, load-use, branches)..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim MODULE=tb.cocotb.cpu.test_pipeline_hazards

# Convenience target for Phase 2 interrupt / CSR tests
.PHONY: interrupts
interrupts:
	@echo "Running Phase 2 interrupt and CSR instruction tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim MODULE=tb.cocotb.cpu.test_interrupts

# Run all tests with Verilator coverage instrumentation and generate reports
.PHONY: coverage
coverage:
	@echo "Running all tests with coverage instrumentation..."
	@mkdir -p $(PROJ_ROOT)/reports
	@rm -f $(SIM_DIR)/coverage_*.dat $(SIM_DIR)/coverage_merged.dat
	@$(MAKE) test COVERAGE=1
	@echo "Merging coverage data from all test modules..."
	@verilator_coverage --write $(SIM_DIR)/coverage_merged.dat \
		$(SIM_DIR)/coverage_*.dat 2>/dev/null || true
	@echo "Generating Verilator coverage report..."
	@verilator_coverage $(SIM_DIR)/coverage_merged.dat \
		--annotate $(PROJ_ROOT)/reports/coverage_annotated 2>/dev/null || \
		echo "Note: verilator_coverage not available or no coverage data found"
	@echo "Coverage report: reports/coverage_annotated/"

# ============================================================================
# Random / Stress UVM Targets (used by CI)
# ============================================================================

.PHONY: random_uvm random_uvm_smoke stress_uvm stress_uvm_smoke

random_uvm:
	@echo "Running pyuvm random instruction tests..."
	$(MAKE) sim MODULE=tb.cocotb.cpu.test_random_uvm

random_uvm_smoke:
	@echo "Running pyuvm random instruction tests (SMOKE: 10 seeds × 50 instructions)..."
	RANDOM_TEST_SMOKE=1 $(MAKE) sim MODULE=tb.cocotb.cpu.test_random_uvm

stress_uvm:
	@echo "Running pyuvm stress tests (4 profiles: ALU, Jump, Shift, Immediate)..."
	$(MAKE) sim MODULE=tb.cocotb.cpu.test_stress_uvm

stress_uvm_smoke:
	@echo "Running pyuvm stress tests (SMOKE: 10 seeds × 100 instr per profile)..."
	STRESS_TEST_SMOKE=1 $(MAKE) sim MODULE=tb.cocotb.cpu.test_stress_uvm

# ============================================================================
# Phase 3 Cache Test Targets
# ============================================================================

# I-Cache unit tests (DUT = rv32i_icache)
.PHONY: icache
icache:
	@echo "Running I-Cache unit tests (hit, miss, conflict, FENCE.I)..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.mem.test_icache \
		TOPLEVEL=rv32i_icache \
		VERILOG_SOURCES="$(CACHE_SOURCES)" \
		SIM_BUILD=sim_build_icache

# D-Cache unit tests (DUT = rv32i_dcache)
.PHONY: dcache
dcache:
	@echo "Running D-Cache unit tests (read/write hit/miss, dirty eviction, strobes)..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.mem.test_dcache \
		TOPLEVEL=rv32i_dcache \
		VERILOG_SOURCES="$(CACHE_SOURCES)" \
		SIM_BUILD=sim_build_dcache

# CPU + cache integration tests (DUT = rv32i_cpu_top)
.PHONY: cache_integration
cache_integration:
	@echo "Running CPU + cache integration tests (locality, FENCE.I, load-after-store)..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim MODULE=tb.cocotb.cpu.test_cache_integration

# Phase 5 SoC tests (delegates to tb/cocotb/soc/Makefile)
.PHONY: soc_all
soc_all:
	@echo "Running Phase 5 SoC tests (crossbar + register bank + AXI-Lite interconnect)..."
	$(MAKE) -C ../tb/cocotb/soc clean && $(MAKE) -C ../tb/cocotb/soc crossbar
	$(MAKE) -C ../tb/cocotb/soc clean && $(MAKE) -C ../tb/cocotb/soc register_bank
	$(MAKE) -C ../tb/cocotb/soc clean && $(MAKE) -C ../tb/cocotb/soc axil_interconnect

# Run all Phase 3 tests
.PHONY: phase3_all
phase3_all:
	@echo "Running all Phase 3 cache tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	@failed_tests=""; \
	for target in icache dcache cache_integration; do \
		echo "========================================"; \
		echo "Running target: $$target"; \
		echo "========================================"; \
		if ! $(MAKE) $$target; then \
			failed_tests="$$failed_tests $$target"; \
		fi; \
		echo ""; \
	done; \
	if [ -n "$$failed_tests" ]; then \
		echo "========================================"; \
		echo "FAILED PHASE 3 TARGETS:$$failed_tests"; \
		echo "========================================"; \
		exit 1; \
	else \
		echo "========================================"; \
		echo "ALL PHASE 3 TESTS PASSED!"; \
		echo "========================================"; \
	fi

# ============================================================================
# Phase 4 GPU Test Targets
# ============================================================================

# vector_register_file unit tests
.PHONY: gpu_regfile
gpu_regfile:
	@echo "Running Phase 4 vector_register_file unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_vector_regfile \
		TOPLEVEL=vector_register_file \
		VERILOG_SOURCES="$(GPU_PKG) $(RTL_DIR)/gpu/vector_register_file.sv" \
		SIM_BUILD=sim_build_gpu_regfile

# vector_alu unit tests
.PHONY: gpu_alu
gpu_alu:
	@echo "Running Phase 4 vector_alu unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_vector_alu \
		TOPLEVEL=vector_alu \
		VERILOG_SOURCES="$(GPU_PKG) $(RTL_DIR)/gpu/vector_alu.sv" \
		SIM_BUILD=sim_build_gpu_alu

# gpu_compute_unit unit tests (divergence)
.PHONY: gpu_diverge
gpu_diverge:
	@echo "Running Phase 4 gpu_compute_unit divergence unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_divergence \
		TOPLEVEL=gpu_compute_unit \
		VERILOG_SOURCES="$(GPU_PKG) $(RTL_DIR)/gpu/vector_register_file.sv $(RTL_DIR)/gpu/vector_alu.sv $(RTL_DIR)/gpu/gpu_compute_unit.sv" \
		SIM_BUILD=sim_build_gpu_diverge

# warp_scheduler unit tests
.PHONY: gpu_sched
gpu_sched:
	@echo "Running Phase 4 warp_scheduler unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_warp_scheduler \
		TOPLEVEL=warp_scheduler \
		VERILOG_SOURCES="$(GPU_PKG) $(RTL_DIR)/gpu/warp_scheduler.sv" \
		SIM_BUILD=sim_build_gpu_sched

# gpu_command_queue unit tests
.PHONY: gpu_cmdq
gpu_cmdq:
	@echo "Running Phase 4 gpu_command_queue unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_command_queue \
		TOPLEVEL=gpu_command_queue \
		VERILOG_SOURCES="$(GPU_PKG) $(RTL_DIR)/gpu/gpu_command_queue.sv" \
		SIM_BUILD=sim_build_gpu_cmdq

# memory_coalescer unit tests
.PHONY: gpu_coalescer
gpu_coalescer:
	@echo "Running Phase 4 memory_coalescer unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_memory_coalescer \
		TOPLEVEL=memory_coalescer \
		VERILOG_SOURCES="$(GPU_PKG) $(RTL_DIR)/gpu/memory_coalescer.sv" \
		SIM_BUILD=sim_build_gpu_coalescer

# gpu_memory_unit unit tests (AXI master wrapper around memory_coalescer)
.PHONY: gpu_memunit
gpu_memunit:
	@echo "Running Phase 4 gpu_memory_unit unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_memory_unit \
		TOPLEVEL=gpu_memory_unit \
		VERILOG_SOURCES="$(GPU_PKG) $(RTL_DIR)/gpu/memory_coalescer.sv $(RTL_DIR)/gpu/gpu_memory_unit.sv" \
		SIM_BUILD=sim_build_gpu_memunit

# gpu_top smoke tests (register bank + FSM)
.PHONY: gpu_top_smoke
gpu_top_smoke:
	@echo "Running Phase 4 gpu_top smoke tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_gpu_top \
		TOPLEVEL=gpu_top \
		VERILOG_SOURCES="$(GPU_SOURCES)" \
		SIM_BUILD=sim_build_gpu_top

# shared_memory unit tests
.PHONY: gpu_shmem
gpu_shmem:
	@echo "Running Phase 4 shared_memory unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_shared_memory \
		TOPLEVEL=shared_memory \
		VERILOG_SOURCES="$(GPU_PKG) $(GPU_SRAM_SIM) $(RTL_DIR)/gpu/shared_memory.sv" \
		SIM_BUILD=sim_build_gpu_shmem

# All Phase 4 unit tests (leaf modules + compute pipeline)
.PHONY: gpu_unit
gpu_unit:
	@echo "Running all Phase 4 GPU unit tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	@failed_tests=""; \
	for target in gpu_regfile gpu_alu gpu_diverge gpu_sched gpu_cmdq gpu_coalescer gpu_memunit gpu_shmem gpu_top_smoke; do \
		echo "========================================"; \
		echo "Running target: $$target"; \
		echo "========================================"; \
		rm -f results.xml; \
		if ! $(MAKE) $$target || [ ! -f results.xml ] || grep -q '<failure\|<error' results.xml; then \
			failed_tests="$$failed_tests $$target"; \
		fi; \
		echo ""; \
	done; \
	if [ -n "$$failed_tests" ]; then \
		echo "========================================"; \
		echo "FAILED GPU UNIT TESTS:$$failed_tests"; \
		echo "========================================"; \
		exit 1; \
	else \
		echo "========================================"; \
		echo "ALL GPU UNIT TESTS PASSED!"; \
		echo "========================================"; \
	fi

# All Phase 4 kernel-level tests (full DUT = gpu_top)
.PHONY: gpu_kernels
gpu_kernels:
	@echo "Running all Phase 4 GPU kernel tests..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	@failed_tests=""; \
	for module in \
		tb.cocotb.gpu.kernels.kernel_vector_add \
		tb.cocotb.gpu.kernels.kernel_dot_product \
		tb.cocotb.gpu.kernels.kernel_divergence_basic \
		tb.cocotb.gpu.kernels.kernel_memory_coalesce \
		tb.cocotb.gpu.kernels.kernel_shared_mem_pingpong \
		tb.cocotb.gpu.kernels.kernel_sync; do \
		echo "========================================"; \
		echo "Running kernel: $$module"; \
		echo "========================================"; \
		rm -f results.xml; \
		if ! $(MAKE) sim MODULE=$$module TOPLEVEL=gpu_top VERILOG_SOURCES="$(GPU_SOURCES)" SIM_BUILD=sim_build_gpu_top || [ ! -f results.xml ] || grep -q '<failure\|<error' results.xml; then \
			failed_tests="$$failed_tests $$module"; \
		fi; \
		echo ""; \
	done; \
	if [ -n "$$failed_tests" ]; then \
		echo "========================================"; \
		echo "FAILED GPU KERNEL TESTS:$$failed_tests"; \
		echo "========================================"; \
		exit 1; \
	else \
		echo "========================================"; \
		echo "ALL GPU KERNEL TESTS PASSED!"; \
		echo "========================================"; \
	fi

# Random-kernel regression (RTL vs GpuRefModel). EXTRA_ARGS="" disables Verilator
# --trace for this long run so it does not generate a multi-GB dump.vcd.
# Configure via RANDOM_KERNELS / RANDOM_KERNELS_SMOKE / RANDOM_KERNELS_SEED env.
.PHONY: gpu_random
gpu_random:
	@echo "Running Phase 4 random-kernel regression (RTL vs reference model)..."
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_random_kernels \
		TOPLEVEL=gpu_top \
		VERILOG_SOURCES="$(GPU_SOURCES)" \
		SIM_BUILD=sim_build_gpu_random \
		EXTRA_ARGS=""

# CPU-GPU handoff integration test
.PHONY: gpu_handoff
gpu_handoff:
	@echo "Running Phase 4 CPU-GPU handoff integration test..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	$(MAKE) sim \
		MODULE=tb.cocotb.gpu.test_cpu_gpu_handoff \
		TOPLEVEL=gpu_top \
		VERILOG_SOURCES="$(GPU_SOURCES)" \
		SIM_BUILD=sim_build_gpu_handoff

# All Phase 4 tests: unit + kernels + handoff
.PHONY: gpu_all
gpu_all:
	@echo "Running all Phase 4 GPU tests (unit + kernels + handoff)..."
	@echo "Note: This should be run in WSL environment"
	@echo ""
	@failed_tests=""; \
	for target in gpu_unit gpu_kernels gpu_handoff; do \
		echo "========================================"; \
		echo "Running target: $$target"; \
		echo "========================================"; \
		rm -f results.xml; \
		if ! $(MAKE) $$target || { [ "$$target" = "gpu_handoff" ] && { [ ! -f results.xml ] || grep -q '<failure\|<error' results.xml; }; }; then \
			failed_tests="$$failed_tests $$target"; \
		fi; \
		echo ""; \
	done; \
	if [ -n "$$failed_tests" ]; then \
		echo "========================================"; \
		echo "FAILED PHASE 4 TARGETS:$$failed_tests"; \
		echo "========================================"; \
		exit 1; \
	else \
		echo "========================================"; \
		echo "ALL PHASE 4 GPU TESTS PASSED!"; \
		echo "========================================"; \
	fi

# Use distclean to avoid conflict with cocotb's clean
# Note: 'clean' target is only defined when cocotb Makefile is included
distclean:
	@echo "Cleaning simulation artifacts..."
	@$(MAKE) clean 2>/dev/null || true
	@rm -rf obj_dir 2>/dev/null || true
	@rm -rf __pycache__ 2>/dev/null || true
	@rm -rf sim_build sim_build_icache sim_build_dcache 2>/dev/null || true
	@rm -rf sim_build_gpu_regfile sim_build_gpu_alu sim_build_gpu_diverge 2>/dev/null || true
	@rm -rf sim_build_gpu_sched sim_build_gpu_cmdq sim_build_gpu_coalescer 2>/dev/null || true
	@rm -rf sim_build_gpu_memunit sim_build_gpu_shmem sim_build_gpu_top sim_build_gpu_handoff 2>/dev/null || true
	@rm -f dump.vcd 2>/dev/null || true
	@rm -f results.xml 2>/dev/null || true
	@rm -f *.log 2>/dev/null || true
