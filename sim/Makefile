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
# The Sky130 SRAM simulation model must precede any RTL that instantiates it.
SRAM_SIM_MODEL := $(SIM_DIR)/sky130_sram_1kbyte_1rw1r_32x256_8.sv

VERILOG_SOURCES := \
	$(SRAM_SIM_MODEL) \
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
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(RTL_DIR)/cpu/core/rv32i_core.sv \
	$(RTL_DIR)/cpu/rv32i_cpu_top.sv

# Cache-only sources (for cache unit tests with a single cache DUT)
CACHE_SOURCES := \
	$(SRAM_SIM_MODEL) \
	$(RTL_DIR)/mem/rv32i_cache_pkg.sv \
	$(RTL_DIR)/mem/rv32i_icache.sv \
	$(RTL_DIR)/mem/rv32i_dcache.sv \
	$(RTL_DIR)/mem/rv32i_cache_arbiter.sv

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
	# Override PYTHON3 so the nix-verilator's verilated.mk uses the system
	# Python instead of the nix Python 3.11 (which conflicts with PYTHONHOME=/usr).
	BUILD_ARGS += PYTHON3=$(shell which python3)
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

# Use distclean to avoid conflict with cocotb's clean
# Note: 'clean' target is only defined when cocotb Makefile is included
distclean:
	@echo "Cleaning simulation artifacts..."
	@$(MAKE) clean 2>/dev/null || true
	@rm -rf obj_dir 2>/dev/null || true
	@rm -rf __pycache__ 2>/dev/null || true
	@rm -rf sim_build 2>/dev/null || true
	@rm -f dump.vcd 2>/dev/null || true
	@rm -f results.xml 2>/dev/null || true
	@rm -f *.log 2>/dev/null || true
