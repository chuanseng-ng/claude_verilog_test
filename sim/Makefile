# Verilator Makefile for RV32I CPU

# Verilator flags
VERILATOR = verilator
VERILATOR_FLAGS = --cc --exe --build -Wall --trace --timing
VERILATOR_FLAGS += -Wno-WIDTHEXPAND -Wno-WIDTHTRUNC -Wno-UNUSEDSIGNAL
VERILATOR_FLAGS += -Wno-CASEINCOMPLETE -Wno-UNOPTFLAT

# Include paths
INCLUDE_PATHS = -I../rtl/pkg -I../rtl/core -I../rtl/interfaces -I../rtl/debug -I../rtl -I../tb -I../tb/tests

# Source files
PKG_FILES = \
	../rtl/pkg/rv32i_pkg.sv \
	../rtl/pkg/axi4lite_pkg.sv

CORE_FILES = \
	../rtl/core/rv32i_alu.sv \
	../rtl/core/rv32i_regfile.sv \
	../rtl/core/rv32i_imm_gen.sv \
	../rtl/core/rv32i_decode.sv \
	../rtl/core/rv32i_control.sv \
	../rtl/core/rv32i_core.sv

INTERFACE_FILES = \
	../rtl/interfaces/axi4lite_master.sv \
	../rtl/interfaces/apb3_slave.sv

DEBUG_FILES = \
	../rtl/debug/rv32i_debug.sv

TOP_FILE = ../rtl/rv32i_cpu_top.sv

TB_FILES = \
	../tb/axi4lite_mem.sv \
	../tb/apb3_master.sv \
	../tb/tb_rv32i_cpu_top.sv

RTL_FILES = $(PKG_FILES) $(CORE_FILES) $(INTERFACE_FILES) $(DEBUG_FILES) $(TOP_FILE)

# Output directory
OBJ_DIR = obj_dir

# Targets
.PHONY: all clean clean-claude clean-all sim test_alu test_regfile help

all: sim

# Main simulation (top-level testbench)
sim: $(RTL_FILES) $(TB_FILES) main.cpp
	$(VERILATOR) $(VERILATOR_FLAGS) $(INCLUDE_PATHS) \
		--top-module tb_rv32i_cpu_top \
		$(RTL_FILES) $(TB_FILES) main.cpp \
		-o Vtb_rv32i_cpu_top
	@echo "Build complete. Run with: ./$(OBJ_DIR)/Vtb_rv32i_cpu_top"

# ALU unit test
test_alu: $(PKG_FILES) ../rtl/core/rv32i_alu.sv ../tb/tests/test_alu.sv main_unit.cpp
	$(VERILATOR) $(VERILATOR_FLAGS) $(INCLUDE_PATHS) \
		--top-module test_alu \
		$(PKG_FILES) ../rtl/core/rv32i_alu.sv ../tb/tests/test_alu.sv main_unit.cpp \
		-o Vtest_alu
	./$(OBJ_DIR)/Vtest_alu

# Register file unit test
test_regfile: $(PKG_FILES) ../rtl/core/rv32i_regfile.sv ../tb/tests/test_regfile.sv main_unit.cpp
	$(VERILATOR) $(VERILATOR_FLAGS) $(INCLUDE_PATHS) \
		--top-module test_regfile \
		$(PKG_FILES) ../rtl/core/rv32i_regfile.sv ../tb/tests/test_regfile.sv main_unit.cpp \
		-o Vtest_regfile
	./$(OBJ_DIR)/Vtest_regfile

# Run all unit tests
unit_tests: test_alu test_regfile
	@echo "All unit tests completed"

# Run full simulation
run: sim
	./$(OBJ_DIR)/Vtb_rv32i_cpu_top

# View waveforms
waves: run
	gtkwave waveform.vcd &

# Clean build artifacts
clean:
	rm -rf $(OBJ_DIR)
	rm -f waveform.vcd
	rm -f *.log

# Clean Claude Code temporary files
clean-claude:
	rm -f ../tmpclaude-*
	rm -f tmpclaude-*
	@echo "Claude temporary files cleaned"

# Clean everything (build artifacts + Claude temp files)
clean-all: clean clean-claude
	@echo "All artifacts cleaned"

# Help
help:
	@echo "RV32I CPU Verilator Build System"
	@echo ""
	@echo "Targets:"
	@echo "  all          - Build main simulation (default)"
	@echo "  sim          - Build main testbench simulation"
	@echo "  run          - Build and run main simulation"
	@echo "  test_alu     - Build and run ALU unit test"
	@echo "  test_regfile - Build and run register file unit test"
	@echo "  unit_tests   - Run all unit tests"
	@echo "  waves        - Run simulation and open GTKWave"
	@echo "  clean        - Remove build artifacts"
	@echo "  clean-claude - Remove Claude Code temporary files"
	@echo "  clean-all    - Remove all artifacts (build + Claude temp)"
	@echo "  help         - Show this help message"
