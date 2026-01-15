##############################################################################
# CoCoTB Makefile for RV32I CPU Testing
# Supports: Verilator, ModelSim/Questa, Vivado (Xsim)
##############################################################################

# Simulator selection (default: verilator)
# Use: make SIM=verilator|modelsim|xsim
SIM ?= verilator

# Test module selection
# Use: make MODULE=tests.test_rv32i_basic
MODULE ?= tests.test_rv32i_basic

# Toplevel RTL module
TOPLEVEL = rv32i_cpu_top

# Toplevel language
TOPLEVEL_LANG = verilog

# Project paths
RTL_DIR = ../../rtl
TB_DIR = ../../tb
SIM_DIR = ../../sim

# RTL source files
VERILOG_SOURCES += $(RTL_DIR)/pkg/rv32i_pkg.sv
VERILOG_SOURCES += $(RTL_DIR)/pkg/axi4lite_pkg.sv
VERILOG_SOURCES += $(RTL_DIR)/core/rv32i_alu.sv
VERILOG_SOURCES += $(RTL_DIR)/core/rv32i_regfile.sv
VERILOG_SOURCES += $(RTL_DIR)/core/rv32i_imm_gen.sv
VERILOG_SOURCES += $(RTL_DIR)/core/rv32i_decode.sv
VERILOG_SOURCES += $(RTL_DIR)/core/rv32i_control.sv
VERILOG_SOURCES += $(RTL_DIR)/core/rv32i_core.sv
VERILOG_SOURCES += $(RTL_DIR)/interfaces/axi4lite_master.sv
VERILOG_SOURCES += $(RTL_DIR)/interfaces/apb3_slave.sv
VERILOG_SOURCES += $(RTL_DIR)/debug/rv32i_debug.sv
VERILOG_SOURCES += $(RTL_DIR)/rv32i_cpu_top.sv

# Include directories
VERILOG_INCLUDE_DIRS += $(RTL_DIR)/pkg

# Python search path
export PYTHONPATH := $(PWD)/lib:$(PYTHONPATH)

##############################################################################
# Simulator-specific settings
##############################################################################

# Verilator settings
ifeq ($(SIM),verilator)
    COMPILE_ARGS += --trace
    COMPILE_ARGS += --trace-structs
    COMPILE_ARGS += --trace-max-array 1024
    COMPILE_ARGS += -Wno-fatal
    COMPILE_ARGS += -Wno-WIDTHTRUNC
    COMPILE_ARGS += -Wno-WIDTHEXPAND
    COMPILE_ARGS += -Wno-CASEINCOMPLETE
    COMPILE_ARGS += --timing
endif

# ModelSim/Questa settings
ifeq ($(SIM),modelsim)
    COMPILE_ARGS += +acc
    COMPILE_ARGS += -permissive
    EXTRA_ARGS += -voptargs="+acc"
    SIM_ARGS += -voptargs="+acc"
endif

# Vivado Xsim settings
ifeq ($(SIM),xsim)
    COMPILE_ARGS += --incr
    COMPILE_ARGS += --relax
endif

##############################################################################
# Waveform settings
##############################################################################

# Enable waveforms with WAVES=1
WAVES ?= 0

ifeq ($(WAVES),1)
    ifeq ($(SIM),verilator)
        EXTRA_ARGS += --trace-fst
    endif
    ifeq ($(SIM),modelsim)
        SIM_ARGS += -do "log -r /*; run -all"
    endif
    ifeq ($(SIM),xsim)
        SIM_ARGS += -log xsim.log -wdb xsim.wdb
    endif
endif

##############################################################################
# Test targets
##############################################################################

# Default target - run all basic tests
.PHONY: all
all: test_basic

# Run all basic tests
.PHONY: test_basic
test_basic:
	$(MAKE) sim MODULE=tests.test_rv32i_basic

# Run all debug tests
.PHONY: test_debug
test_debug:
	$(MAKE) sim MODULE=tests.test_rv32i_debug

# Run specific tests
.PHONY: test_simple_add
test_simple_add:
	$(MAKE) sim MODULE=tests.test_rv32i_basic TESTCASE=test_simple_add

.PHONY: test_load_store
test_load_store:
	$(MAKE) sim MODULE=tests.test_rv32i_basic TESTCASE=test_load_store

.PHONY: test_branch
test_branch:
	$(MAKE) sim MODULE=tests.test_rv32i_basic TESTCASE=test_branch

.PHONY: test_reset
test_reset:
	$(MAKE) sim MODULE=tests.test_rv32i_basic TESTCASE=test_reset

.PHONY: test_halt_resume
test_halt_resume:
	$(MAKE) sim MODULE=tests.test_rv32i_debug TESTCASE=test_halt_resume

.PHONY: test_single_step
test_single_step:
	$(MAKE) sim MODULE=tests.test_rv32i_debug TESTCASE=test_single_step

.PHONY: test_register_access
test_register_access:
	$(MAKE) sim MODULE=tests.test_rv32i_debug TESTCASE=test_register_access

.PHONY: test_pc_access
test_pc_access:
	$(MAKE) sim MODULE=tests.test_rv32i_debug TESTCASE=test_pc_access

.PHONY: test_breakpoint
test_breakpoint:
	$(MAKE) sim MODULE=tests.test_rv32i_debug TESTCASE=test_breakpoint

.PHONY: test_full_debug
test_full_debug:
	$(MAKE) sim MODULE=tests.test_rv32i_debug TESTCASE=test_full_debug_sequence

# Run all tests (regression)
.PHONY: regression
regression:
	$(MAKE) test_basic
	$(MAKE) test_debug

# Alias for regression (CI convention)
.PHONY: test
test: regression

##############################################################################
# Utility targets
##############################################################################

# Clean build artifacts
.PHONY: clean
clean:
	@rm -rf sim_build
	@rm -rf __pycache__
	@rm -rf tests/__pycache__
	@rm -rf lib/__pycache__
	@rm -rf lib/*/__pycache__
	@rm -rf .pytest_cache
	@rm -f results.xml
	@rm -f dump.vcd dump.fst
	@rm -f *.log

# View waveforms
.PHONY: waves
waves:
	@if [ -f dump.fst ]; then \
		gtkwave dump.fst; \
	elif [ -f dump.vcd ]; then \
		gtkwave dump.vcd; \
	else \
		echo "No waveform file found. Run with WAVES=1"; \
	fi

# Install Python dependencies
.PHONY: install
install:
	pip install -r requirements.txt

# Help
.PHONY: help
help:
	@echo "CoCoTB Makefile for RV32I CPU Testing"
	@echo ""
	@echo "Simulator Selection:"
	@echo "  SIM=verilator    - Use Verilator (default)"
	@echo "  SIM=modelsim     - Use ModelSim/Questa"
	@echo "  SIM=xsim         - Use Vivado Xsim"
	@echo ""
	@echo "Test Targets:"
	@echo "  make all             - Run all basic tests"
	@echo "  make test_basic      - Run basic functionality tests"
	@echo "  make test_debug      - Run debug interface tests"
	@echo "  make test_simple_add - Run simple_add test"
	@echo "  make test_load_store - Run load/store test"
	@echo "  make test_branch     - Run branch test"
	@echo "  make regression      - Run all tests"
	@echo ""
	@echo "Waveform Options:"
	@echo "  WAVES=1          - Enable waveform dumping"
	@echo "  make waves       - View waveforms with GTKWave"
	@echo ""
	@echo "Utility:"
	@echo "  make clean       - Clean build artifacts"
	@echo "  make install     - Install Python dependencies"
	@echo "  make help        - Show this help"
	@echo ""
	@echo "Examples:"
	@echo "  make SIM=verilator WAVES=1"
	@echo "  make SIM=modelsim test_debug"
	@echo "  make SIM=xsim regression"

##############################################################################
# Include cocotb makefiles
##############################################################################

include $(shell cocotb-config --makefiles)/Makefile.sim
