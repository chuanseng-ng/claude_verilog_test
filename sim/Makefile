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
	tb.cocotb.cpu.test_c_programs

# RTL source files
VERILOG_SOURCES := \
	$(RTL_DIR)/cpu/core/rv32i_alu.sv \
	$(RTL_DIR)/cpu/core/rv32i_imm_gen.sv \
	$(RTL_DIR)/cpu/core/rv32i_regfile.sv \
	$(RTL_DIR)/cpu/core/rv32i_decode.sv \
	$(RTL_DIR)/cpu/core/rv32i_branch_comp.sv \
	$(RTL_DIR)/cpu/core/rv32i_control.sv \
	$(RTL_DIR)/cpu/core/rv32i_core.sv \
	$(RTL_DIR)/cpu/rv32i_cpu_top.sv

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

.PHONY: help lint clean-basic

help:
	@echo "RV32I CPU Simulation Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  make test         - Run all cocotb tests (requires WSL)"
	@echo "  make sim          - Run single test module (requires WSL)"
	@echo "  make waves        - Open waveform viewer (gtkwave)"
	@echo "  make lint         - Run Verilator lint check"
	@echo "  make clean        - Clean simulation artifacts"
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
	@verilator --lint-only -Wall \
		--top-module $(DUT) \
		$(VERILOG_SOURCES) 2>&1 || echo "Verilator not found. Install with: sudo apt-get install verilator, or run from WSL"

clean-basic:
	@echo "Cleaning simulation artifacts..."
	@rm -rf obj_dir 2>/dev/null || true
	@rm -rf __pycache__ 2>/dev/null || true
	@rm -rf sim_build 2>/dev/null || true
	@rm -f dump.vcd 2>/dev/null || true
	@rm -f results.xml 2>/dev/null || true
	@rm -f *.log 2>/dev/null || true

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
		echo ""; \
	done; \
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

# Override clean to use our basic clean
clean: clean-basic
