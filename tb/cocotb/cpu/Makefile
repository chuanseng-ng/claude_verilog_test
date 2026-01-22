# Makefile for CPU cocotb testbench
# Cocotb tests must be run via 'make', NOT via 'pytest'
#
# Usage:
#   make                    - Run default test (smoke tests)
#   make MODULE=test_smoke  - Run smoke tests
#   make usage              - Show available targets

# Simulator selection
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# RTL source files
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/rv32i_cpu_top.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_core.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_control.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_decode.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_alu.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_regfile.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_imm_gen.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_branch_comp.sv

# Testbench settings (can override MODULE on command line)
TOPLEVEL = rv32i_cpu_top
MODULE ?= test_smoke

# Verilator-specific flags
ifeq ($(SIM), verilator)
    EXTRA_ARGS += --trace --trace-structs
    COMPILE_ARGS += -Wno-WIDTH -Wno-UNUSED -Wno-BLKSEQ
    COMPILE_ARGS += -CFLAGS "-std=c++14"
endif

# Icarus Verilog settings
ifeq ($(SIM), icarus)
    COMPILE_ARGS += -g2012
endif

# Include cocotb makefiles
include $(shell cocotb-config --makefiles)/Makefile.sim

# Convenience targets for different test suites
.PHONY: smoke basic all_tests usage info distclean

smoke:
	@echo "Running smoke tests..."
	$(MAKE) MODULE=test_smoke

basic:
	@echo "Running basic CPU tests..."
	$(MAKE) MODULE=test_cpu_basic

all_tests: smoke basic

# Usage/help target (renamed from 'help' to avoid conflict with cocotb's help)
usage info:
	@echo "RV32I CPU Cocotb Test Makefile"
	@echo ""
	@echo "IMPORTANT: These are cocotb tests (NOT pytest tests)"
	@echo "           Run via 'make', not 'pytest'"
	@echo ""
	@echo "Available targets:"
	@echo "  make              - Run default tests (smoke)"
	@echo "  make smoke        - Run smoke tests (quick validation)"
	@echo "  make basic        - Run basic CPU tests"
	@echo "  make all_tests    - Run all test suites"
	@echo "  make clean        - Remove simulation artifacts"
	@echo "  make distclean    - Deep clean (remove all generated files)"
	@echo "  make usage        - Show this usage message"
	@echo "  make info         - Show this usage message (alias)"
	@echo ""
	@echo "Override options:"
	@echo "  make MODULE=test_name   - Run specific test module"
	@echo "  make SIM=icarus         - Use different simulator (verilator, icarus)"
	@echo ""
	@echo "Examples:"
	@echo "  make smoke              # Quick smoke test"
	@echo "  make MODULE=test_smoke  # Explicitly specify module"
	@echo "  make SIM=icarus smoke   # Use Icarus Verilog"
	@echo ""
	@echo "Test modules available:"
	@echo "  test_smoke       - Basic functionality tests"
	@echo "  test_cpu_basic   - CPU instruction tests"
	@echo "  test_c_programs  - Compiled C program tests"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - Verilator or Icarus Verilog installed"
	@echo "  - cocotb Python package installed"

# Custom clean target to avoid conflicts with cocotb's clean
distclean: clean
	@rm -rf __pycache__ 2>/dev/null || true
	@rm -f *.vcd *.fst 2>/dev/null || true
	@echo "Deep clean complete"
