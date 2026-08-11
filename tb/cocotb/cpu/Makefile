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

# Python path: repo root must be on PYTHONPATH for `from tb.xxx import` to work
export PYTHONPATH := $(PWD)/../../..:$(PYTHONPATH)

# Runtime library path: nix-built Vtop binary needs system libexpat, libz, libffi
# when it dlopen's system Python (libpython3.10).  Only these three libs are added
# (not the full system lib directory) to avoid glibc version conflicts.
# Set USE_VERILATOR_EXTRALIBS=1 to enable; opt-in avoids failures on systems
# where these paths don't exist or have different SONAME versions.
_EXTRALIBS := /tmp/verilator_extralibs
export LD_LIBRARY_PATH := $(_EXTRALIBS):$(LD_LIBRARY_PATH)
ifneq ($(USE_VERILATOR_EXTRALIBS),)
$(shell mkdir -p $(_EXTRALIBS) \
  && ([ -e /usr/lib/x86_64-linux-gnu/libexpat.so.1 ] && ln -sf /usr/lib/x86_64-linux-gnu/libexpat.so.1 $(_EXTRALIBS)/libexpat.so.1 || true) \
  && ([ -e /lib/x86_64-linux-gnu/libz.so.1 ] && ln -sf /lib/x86_64-linux-gnu/libz.so.1 $(_EXTRALIBS)/libz.so.1 || true) \
  && ([ -e /lib/x86_64-linux-gnu/libffi.so.8 ] && ln -sf /lib/x86_64-linux-gnu/libffi.so.8 $(_EXTRALIBS)/libffi.so.8 || true))
endif

# RTL source files (packages must come first)
# Kept in sync with pnr/asap7/cpu/config.json's VERILOG_FILES import order —
# see tools/verif/check_source_closure.py, which verifies this list closes
# over every `import <pkg>::*` used by the files it lists (bead claude_verilog_test-50t).
VERILOG_SOURCES += $(PWD)/../../../rtl/soc/axi_pkg.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/soc/soc_addr_map_pkg.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_pipeline_pkg.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/mem/rv32i_cache_pkg.sv
# rv32i_clock_gate.sv: instantiated by rv32i_icache.sv/rv32i_dcache.sv (tag/data bank clock gating)
VERILOG_SOURCES += $(PWD)/../../../rtl/mem/rv32i_clock_gate.sv
# Phase 3: Verilator-compatible SRAM behavioral model
# (sram_1rw_256x32_verilator.v avoids mixed blocking/non-blocking and negedge
#  triggers that Verilator cannot handle in the original OpenRAM model)
VERILOG_SOURCES += $(PWD)/../../../sim/sram_1rw_256x32_verilator.v
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/rv32i_cpu_top.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_core.sv
# rv32i_control.sv is Phase 1 only — rv32i_core.sv (Phase 2+) does not instantiate it
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_decode.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_alu.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_regfile.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_imm_gen.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_branch_comp.sv
# Pipeline stage modules (IF / ID / EX / EX1b / EX1c / EX2 / MEM / WB).
# EX1b/EX1c/EX2 are the EX-stage retiming split (Run 14+, ASAP7 sign-off) —
# the pre-retiming TB list only had IF/ID/EX/MEM/WB and predates this.
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/pipeline/rv32i_pipeline_if.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/pipeline/rv32i_pipeline_id.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/pipeline/rv32i_pipeline_ex.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/pipeline/rv32i_pipeline_ex1b.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/pipeline/rv32i_pipeline_ex1c.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/pipeline/rv32i_pipeline_ex2.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/pipeline/rv32i_pipeline_wb.sv
# Hazard detection, forwarding, CSR, and interrupt control units
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_hazard_unit.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_forwarding_unit.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_csr_file.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/cpu/core/rv32i_interrupt_ctrl.sv
# NOTE: rv32i_axi_arbiter.sv (Phase 1 AXI4-Lite IF-vs-MEM arbiter) intentionally
# dropped — dead since Phase 2's cache_arbiter took over; nothing in the current
# hierarchy instantiates it (confirmed via grep + absent from pnr/asap7/cpu/config.json).
# Phase 3: Cache RTL (I-cache, D-cache, cache arbiter)
VERILOG_SOURCES += $(PWD)/../../../rtl/mem/rv32i_icache.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/mem/rv32i_dcache.sv
VERILOG_SOURCES += $(PWD)/../../../rtl/mem/rv32i_cache_arbiter.sv

# Testbench settings (can override MODULE on command line)
TOPLEVEL = rv32i_cpu_top
MODULE ?= test_smoke_uvm

# Verilator-specific flags
ifeq ($(SIM), verilator)
    EXTRA_ARGS += --trace --trace-structs
    COMPILE_ARGS += -Wno-WIDTH -Wno-UNUSED -Wno-BLKSEQ -Wno-UNOPTFLAT --no-timing
    COMPILE_ARGS += -CFLAGS "-std=c++14"
endif

# Icarus Verilog settings
ifeq ($(SIM), icarus)
    COMPILE_ARGS += -g2012
endif

# Include cocotb makefiles
include $(shell cocotb-config --makefiles)/Makefile.sim

# Convenience targets for different test suites
.PHONY: smoke basic random isa ebreak debug all_tests usage info distclean
.PHONY: smoke_uvm random_uvm random_uvm_smoke random_uvm_waves isa_uvm all_uvm
.PHONY: stress_uvm stress_uvm_smoke stress_alu stress_jump stress_shift stress_immediate
.PHONY: directed_random_uvm directed_alu directed_immediate directed_rtype
.PHONY: pipeline_hazards interrupts axi_protocol fault_injection phase2_all

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

debug:
	@echo "Running APB3 debug interface tests (5 tests: single-step, BP0, BP1, GPR write, PC write)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_debug_if

# ── Phase 2 Verification Targets ──────────────────────────────────────────────
pipeline_hazards:
	@echo "Running pipeline hazard tests (Groups 2-3: RAW, load-use, control hazards)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_pipeline_hazards

interrupts:
	@echo "Running interrupt and CSR tests (Groups 4-5: timer/ext IRQ, MRET, CSR insns)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_interrupts

axi_protocol:
	# Covers Phase 1 protocol regression AND Phase 2 arbiter (IF vs MEM) contention tests.
	@echo "Running AXI protocol + arbiter tests (Phase 1 compliance + Phase 2 IF/MEM arbiter)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_axi_protocol

fault_injection:
	@echo "Running fault injection tests (misaligned access, illegal instruction traps)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_fault_injection

phase2_all:
	@echo "========================================="
	@echo "Running Phase 2 Comprehensive Test Suite"
	@echo "========================================="
	@failed=0; \
	echo ""; \
	echo "[1/7] Running pyuvm smoke tests..."; \
	if $(MAKE) smoke_uvm; then \
		echo "✓ smoke_uvm PASSED"; \
	else \
		echo "✗ smoke_uvm FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[2/7] Running ISA compliance tests..."; \
	if $(MAKE) isa_uvm; then \
		echo "✓ isa_uvm PASSED"; \
	else \
		echo "✗ isa_uvm FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[3/7] Running pipeline hazard tests (Groups 2-3)..."; \
	if $(MAKE) pipeline_hazards; then \
		echo "✓ pipeline_hazards PASSED"; \
	else \
		echo "✗ pipeline_hazards FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[4/7] Running interrupt and CSR tests (Groups 4-5)..."; \
	if $(MAKE) interrupts; then \
		echo "✓ interrupts PASSED"; \
	else \
		echo "✗ interrupts FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[5/7] Running APB3 debug interface tests (Group 6)..."; \
	if $(MAKE) debug; then \
		echo "✓ debug PASSED"; \
	else \
		echo "✗ debug FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[6/7] Running AXI protocol + arbiter tests (Group 7)..."; \
	if $(MAKE) axi_protocol; then \
		echo "✓ axi_protocol PASSED"; \
	else \
		echo "✗ axi_protocol FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[7/7] Running fault injection tests..."; \
	if $(MAKE) fault_injection; then \
		echo "✓ fault_injection PASSED"; \
	else \
		echo "✗ fault_injection FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "========================================="; \
	if [ $$failed -eq 0 ]; then \
		echo "OVERALL RESULT: ✓ ALL PHASE 2 SUITES PASSED"; \
		echo "========================================="; \
		exit 0; \
	else \
		echo "OVERALL RESULT: ✗ $$failed PHASE 2 SUITE(S) FAILED"; \
		echo "========================================="; \
		exit 1; \
	fi

# pyuvm test targets (Phase F+)
smoke_uvm:
	@echo "Running pyuvm smoke tests (4 tests)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_smoke_uvm

random_uvm:
	@echo "Running pyuvm random instruction tests..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_random_uvm

random_uvm_smoke:
	@echo "Running pyuvm random instruction tests (SMOKE TEST: 10 seeds × 50 instructions)..."
	export RANDOM_TEST_SMOKE=1 && export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_random_uvm

random_uvm_waves:
	@echo "Running pyuvm random instruction tests with waveform capture enabled..."
	@echo "Note: Waveforms are saved automatically for failed seeds to results/waveforms/"
	export ENABLE_WAVEFORMS=1 && export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_random_uvm

isa_uvm:
	@echo "Running pyuvm ISA compliance tests (54 tests, 37 RV32I instructions)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_isa_uvm

stress_uvm:
	@echo "Running pyuvm stress tests (4 profiles: ALU, Jump, Shift, Immediate)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_stress_uvm

stress_uvm_smoke:
	@echo "Running pyuvm stress tests (SMOKE TEST: 10 seeds × 100 instr per profile)..."
	export STRESS_TEST_SMOKE=1 && export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_stress_uvm

stress_alu:
	@echo "Running ALU-intensive stress test (90% ALU operations)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_stress_uvm TESTCASE=test_stress_alu_intensive

stress_jump:
	@echo "Running jump-heavy stress test (40% jump instructions)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_stress_uvm TESTCASE=test_stress_jump_heavy

stress_shift:
	@echo "Running shift-intensive stress test..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_stress_uvm TESTCASE=test_stress_shift_intensive

stress_immediate:
	@echo "Running immediate-heavy stress test..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_stress_uvm TESTCASE=test_stress_immediate_heavy

directed_random_uvm:
	@echo "Running pyuvm directed random tests (3 scenarios: ALU-focused, immediate-heavy, R-type dominant)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_directed_random_uvm

directed_alu:
	@echo "Running directed random ALU-focused test (70% ALU operations)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_directed_random_uvm TESTCASE=test_directed_alu_focused

directed_immediate:
	@echo "Running directed random immediate-heavy test (80% I-type + upper immediate)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_directed_random_uvm TESTCASE=test_directed_immediate_heavy

directed_rtype:
	@echo "Running directed random R-type dominant test (90% R-type)..."
	export PYTHONPATH=$$PYTHONPATH:$(PWD)/../../.. && $(MAKE) MODULE=test_directed_random_uvm TESTCASE=test_directed_rtype_dominant

all_uvm:
	@echo "========================================="
	@echo "Running All pyuvm Test Suites"
	@echo "========================================="
	@failed=0; \
	echo ""; \
	echo "[1/3] Running pyuvm smoke tests..."; \
	if $(MAKE) smoke_uvm; then \
		echo "✓ pyuvm smoke tests PASSED"; \
	else \
		echo "✗ pyuvm smoke tests FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[2/3] Running pyuvm ISA compliance tests..."; \
	if $(MAKE) isa_uvm; then \
		echo "✓ pyuvm ISA tests PASSED"; \
	else \
		echo "✗ pyuvm ISA tests FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "[3/3] Running pyuvm random tests..."; \
	if $(MAKE) random_uvm; then \
		echo "✓ pyuvm random tests PASSED"; \
	else \
		echo "✗ pyuvm random tests FAILED"; \
		failed=$$((failed + 1)); \
	fi; \
	echo ""; \
	echo "========================================="; \
	if [ $$failed -eq 0 ]; then \
		echo "OVERALL RESULT: ✓ ALL PYUVM TESTS PASSED"; \
		echo "========================================="; \
		exit 0; \
	else \
		echo "OVERALL RESULT: ✗ $$failed PYUVM TEST SUITE(S) FAILED"; \
		echo "========================================="; \
		exit 1; \
	fi

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
	@echo "  make              - Run default tests (pyuvm smoke tests)"
	@echo ""
	@echo "Recommended pyuvm targets:"
	@echo "  make smoke_uvm         - Run pyuvm smoke tests (4 tests)"
	@echo "  make isa_uvm           - Run pyuvm ISA compliance tests (54 tests, 37 instructions)"
	@echo "  make random_uvm        - Run pyuvm random instruction tests (default: 100 seeds × 100 instr)"
	@echo "  make random_uvm_smoke  - Run pyuvm random smoke test (10 seeds × 50 instr, ~10s)"
	@echo "  make random_uvm_waves  - Run pyuvm random tests with waveform capture enabled"
	@echo "  make stress_uvm        - Run pyuvm stress tests (4 profiles: ALU/Jump/Shift/Immediate)"
	@echo "  make stress_uvm_smoke  - Run pyuvm stress smoke test (10 seeds × 100 instr per profile)"
	@echo "  make directed_random_uvm - Run pyuvm directed random tests (3 scenarios with custom distributions)"
	@echo "  make all_uvm           - Run all pyuvm test suites (smoke + ISA + random)"
	@echo ""
	@echo "Individual stress test profiles:"
	@echo "  make stress_alu        - ALU-intensive test (90% ALU operations)"
	@echo "  make stress_jump       - Jump-heavy test (40% jump instructions)"
	@echo "  make stress_shift      - Shift-intensive test (heavy shift operations)"
	@echo "  make stress_immediate  - Immediate-heavy test (tests immediate generation)"
	@echo ""
	@echo "Individual directed random test scenarios:"
	@echo "  make directed_alu      - ALU-focused test (70% ALU operations, balanced coverage)"
	@echo "  make directed_immediate - Immediate-heavy test (80% I-type + upper immediate)"
	@echo "  make directed_rtype    - R-type dominant test (90% R-type instructions)"
	@echo ""
	@echo "Debug interface tests:"
	@echo "  make debug        - Run APB3 debug interface tests (5 tests)"
	@echo ""
	@echo "Phase 2 comprehensive verification:"
	@echo "  make pipeline_hazards  - Groups 2-3: data hazards + control hazards"
	@echo "  make interrupts        - Groups 4-5: interrupts + CSR instructions"
	@echo "  make axi_protocol      - Phase 1 regression + Phase 2 arbiter tests"
	@echo "  make fault_injection   - Exception/trap path tests"
	@echo "  make phase2_all        - All Phase 2 suites (smoke + ISA + hazards + IRQ + debug + AXI + faults)"
	@echo ""
	@echo "Legacy targets (DEPRECATED - use pyuvm instead):"
	@echo "  make smoke        - Run legacy smoke tests"
	@echo "  make basic        - Run legacy basic CPU tests"
	@echo "  make random       - Run legacy random tests (10,000 instructions)"
	@echo "  make isa          - Run legacy ISA compliance tests (37 instructions)"
	@echo "  make ebreak       - Run EBREAK halt test"
	@echo "  make all_tests    - Run all legacy test suites"
	@echo ""
	@echo "Utility targets:"
	@echo "  make clean        - Remove simulation artifacts"
	@echo "  make distclean    - Deep clean (remove all generated files)"
	@echo "  make usage        - Show this usage message"
	@echo "  make info         - Show this usage message (alias)"
	@echo ""
	@echo "Override options:"
	@echo "  make MODULE=test_name   - Run specific test module"
	@echo "  make SIM=icarus         - Use different simulator (verilator, icarus)"
	@echo ""
	@echo "Random test environment variables:"
	@echo "  RANDOM_TEST_SEEDS=N     - Number of seeds (default: 100)"
	@echo "  RANDOM_TEST_INSTRS=N    - Instructions per seed (default: 100)"
	@echo "  RANDOM_TEST_SMOKE=1     - Use smoke test config (10 seeds × 50 instr)"
	@echo ""
	@echo "Stress test environment variables:"
	@echo "  STRESS_TEST_SEEDS=N     - Number of seeds per profile (default: 100)"
	@echo "  STRESS_TEST_INSTRS=N    - Instructions per seed (default: 500)"
	@echo "  STRESS_TEST_SMOKE=1     - Use smoke test config (10 seeds × 100 instr)"
	@echo ""
	@echo "Examples:"
	@echo "  make smoke_uvm                              # Quick smoke test (4 tests)"
	@echo "  make random_uvm_smoke                       # Quick random test (10 seeds)"
	@echo "  make random_uvm                             # Full random test (100 seeds)"
	@echo "  RANDOM_TEST_SEEDS=1000 make random_uvm      # Extended test (1000 seeds)"
	@echo "  make random_uvm_waves                       # Random test with waveform capture"
	@echo "  make stress_uvm_smoke                       # Quick stress test (all profiles)"
	@echo "  make stress_alu                             # ALU-intensive stress test"
	@echo "  STRESS_TEST_SEEDS=200 make stress_jump      # Jump stress with 200 seeds"
	@echo "  make MODULE=test_smoke_uvm                  # Explicitly specify module"
	@echo "  make SIM=icarus smoke_uvm                   # Use Icarus Verilog"
	@echo ""
	@echo "Test modules available:"
	@echo "  pyuvm tests (RECOMMENDED):"
	@echo "    test_smoke_uvm            - pyuvm smoke tests (4 tests)"
	@echo "    test_isa_uvm              - pyuvm ISA compliance tests (54 tests, 37 instructions)"
	@echo "    test_random_uvm           - pyuvm random tests (multi-seed)"
	@echo "    test_stress_uvm           - pyuvm stress tests (biased instruction distributions)"
	@echo "    test_directed_random_uvm  - pyuvm directed random tests (custom distributions)"
	@echo "    test_ebreak               - EBREAK halt detection test"
	@echo "    test_debug_if             - APB3 debug interface tests (5 tests)"
	@echo "    test_pipeline_hazards     - Phase 2 data + control hazard tests"
	@echo "    test_interrupts           - Phase 2 interrupt + CSR instruction tests"
	@echo "    test_axi_protocol         - AXI protocol compliance + Phase 2 arbiter tests"
	@echo "    test_fault_injection      - Phase 2 fault injection + exception tests"
	@echo ""
	@echo "  Legacy cocotb tests (DEPRECATED - in legacy/ directory):"
	@echo "    legacy/test_smoke                - Basic functionality tests (6 tests)"
	@echo "    legacy/test_isa_compliance       - ISA compliance tests (37 instructions)"
	@echo "    legacy/test_random_instructions  - Random instruction tests (10,000 instr)"
	@echo ""
	@echo "Prerequisites:"
	@echo "  - Verilator or Icarus Verilog installed"
	@echo "  - cocotb Python package installed"

# Custom clean target to avoid conflicts with cocotb's clean
distclean: clean
	@rm -rf __pycache__ 2>/dev/null || true
	@rm -f *.vcd *.fst 2>/dev/null || true
	@echo "Deep clean complete"
