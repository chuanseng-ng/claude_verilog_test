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
.PHONY: smoke basic random isa ebreak all_tests usage info distclean

smoke:
	@echo "Running smoke tests..."
	$(MAKE) MODULE=test_smoke

basic:
	@echo "Running basic CPU tests (smoke tests)..."
	$(MAKE) MODULE=test_smoke

random:
	@echo "Running random instruction tests (10,000 instructions)..."
	$(MAKE) MODULE=test_random_instructions

isa:
	@echo "Running ISA compliance tests (37 RV32I instructions)..."
	$(MAKE) MODULE=test_isa_compliance

ebreak:
	@echo "Running EBREAK halt test..."
	$(MAKE) MODULE=test_ebreak

all_tests:
	@echo "========================================="
	@echo "Running All Test Suites"
	@echo "========================================="
	@failed=0; \
	echo ""; \
	echo "[1/3] Running smoke tests..."; \
	if $(MAKE) smoke; then \
		echo "✓ Smoke tests PASSED"; \
	else \
		echo "✗ Smoke tests FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[2/3] Running ISA compliance tests..."; \
	if $(MAKE) isa; then \
		echo "✓ ISA tests PASSED"; \
	else \
		echo "✗ ISA tests FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[3/3] Running random instruction tests..."; \
	if $(MAKE) random; then \
		echo "✓ Random tests PASSED"; \
	else \
		echo "✗ Random tests FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "========================================="; \
	if [ $$failed -eq 0 ]; then \
		echo "OVERALL RESULT: ✓ ALL TESTS PASSED"; \
		echo "========================================="; \
		exit 0; \
	else \
		echo "OVERALL RESULT: ✗ $$failed TEST SUITE(S) FAILED"; \
		echo "========================================="; \
		exit 1; \
	fi

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
	@echo "  make random       - Run random instruction tests (10,000 instructions)"
	@echo "  make isa          - Run ISA compliance tests (37 RV32I instructions)"
	@echo "  make ebreak       - Run EBREAK halt test"
	@echo "  make all_tests    - Run all test suites (smoke + isa + random)"
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
	@echo "  make random             # Run 10,000 random instructions"
	@echo "  make MODULE=test_smoke  # Explicitly specify module"
	@echo "  make SIM=icarus smoke   # Use Icarus Verilog"
	@echo ""
	@echo "Test modules available:"
	@echo "  test_smoke                - Basic functionality tests (6 smoke tests)"
	@echo "  test_isa_compliance       - ISA compliance tests (37 RV32I instructions)"
	@echo "  test_random_instructions  - Random instruction tests (10,000 instructions)"
	@echo "  test_ebreak               - EBREAK halt detection test"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - Verilator or Icarus Verilog installed"
	@echo "  - cocotb Python package installed"

# Custom clean target to avoid conflicts with cocotb's clean
distclean: clean
	@rm -rf __pycache__ 2>/dev/null || true
	@rm -f *.vcd *.fst 2>/dev/null || true
	@echo "Deep clean complete"
