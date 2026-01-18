# Makefile for CPU cocotb testbench
# This will be used in Phase 1+ when RTL exists

# Simulator selection
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# RTL source files (will be created in Phase 1)
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/rv32i_cpu_top.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_core.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_control.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_decode.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_alu.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_regfile.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_imm_gen.sv

# Testbench settings
TOPLEVEL = rv32i_cpu_top
MODULE = test_cpu_basic

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

# Custom clean target to avoid conflicts with cocotb's clean
distclean: clean
	@rm -rf __pycache__ 2>/dev/null || true
	@rm -f *.vcd *.fst 2>/dev/null || true
	@echo "Deep clean complete"

.PHONY: distclean
