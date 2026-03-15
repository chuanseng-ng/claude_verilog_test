#================================================================
# LibreLane Flow — Makefile
# Design: rv32i_cpu_top (Phase 3: RV32I CPU + L1 I-Cache + L1 D-Cache)
# PDK: sky130A / sky130_fd_sc_hd
# Frequency: 75 MHz (13.333 ns period)
#================================================================

#----------------------------------------------------------------
# Configuration
#----------------------------------------------------------------

DESIGN_NAME := rv32i_cpu_top
CONFIG_FILE := $(abspath config.json)

# LibreLane run directory (created by the flow)
RUN_DIR := runs

# LibreLane nix-shell directory
# LibreLane is invoked inside the nix-shell from this repo clone.
# Override with: make run LIBRELANE_NIXDIR=/other/path
LIBRELANE_NIXDIR ?= $(HOME)/Downloads/Github/librelane

# Internal: run a command inside the LibreLane nix-shell.
# Usage: $(NIX_RUN) "librelane <args>"
NIX_RUN = cd $(LIBRELANE_NIXDIR) && nix-shell --run

# PDK root — LibreLane reads this via the PDK_ROOT env var.
# LibreLane/volare defaults to ~/.volare; override if installed elsewhere.
PDK_ROOT ?= $(HOME)/.volare

export PDK_ROOT

#----------------------------------------------------------------
# Phony Targets
#----------------------------------------------------------------

.PHONY: all run run-skip-lint synth clean results help check_env

#----------------------------------------------------------------
# Default Target
#----------------------------------------------------------------

all: run

#----------------------------------------------------------------
# Environment Check
#----------------------------------------------------------------

check_env:
	@echo "Checking LibreLane nix-shell environment..."
	@if [ ! -d "$(LIBRELANE_NIXDIR)" ]; then \
		echo "ERROR: LibreLane repo not found at $(LIBRELANE_NIXDIR)"; \
		echo "       Clone with: git clone https://github.com/efabless/librelane $(LIBRELANE_NIXDIR)"; \
		exit 1; \
	fi
	@if [ ! -f "$(LIBRELANE_NIXDIR)/shell.nix" ]; then \
		echo "ERROR: shell.nix not found in $(LIBRELANE_NIXDIR)"; \
		exit 1; \
	fi
	@echo "  LibreLane nix dir : $(LIBRELANE_NIXDIR)"
	@echo "  PDK_ROOT          : $(PDK_ROOT)"
	@if [ ! -d "$(PDK_ROOT)/sky130A" ]; then \
		echo "  WARNING: PDK not found at $(PDK_ROOT)/sky130A"; \
		echo "           LibreLane will attempt to fetch it automatically via volare."; \
	else \
		echo "  Sky130A           : found"; \
	fi
	@echo "  Config            : $(CONFIG_FILE)"
	@echo "Environment check complete."

#----------------------------------------------------------------
# Full Flow Run
#----------------------------------------------------------------

run: check_env
	@echo "=========================================="
	@echo "Running LibreLane flow — $(DESIGN_NAME)"
	@echo "Config : $(CONFIG_FILE)"
	@echo "PDK_ROOT: $(PDK_ROOT)"
	@echo "nix-shell: $(LIBRELANE_NIXDIR)"
	@echo "=========================================="
	$(NIX_RUN) "PDK_ROOT=$(PDK_ROOT) librelane $(CONFIG_FILE)"
	@echo "=========================================="
	@echo "LibreLane flow complete."
	@echo "Results in: $(RUN_DIR)/"
	@echo "=========================================="
	@$(MAKE) results

#----------------------------------------------------------------
# Full Flow Run — skip Verilator lint (workaround for Yosys 0.46 native SV
# frontend incompatibility with $unit-scope package imports)
# Starts from the Yosys JSON header step, bypassing steps 01-04.
#----------------------------------------------------------------

run-skip-lint: check_env
	@echo "=========================================="
	@echo "Running LibreLane flow (skip lint) — $(DESIGN_NAME)"
	@echo "Config : $(CONFIG_FILE)"
	@echo "PDK_ROOT: $(PDK_ROOT)"
	@echo "nix-shell: $(LIBRELANE_NIXDIR)"
	@echo "=========================================="
	$(NIX_RUN) "PDK_ROOT=$(PDK_ROOT) librelane $(CONFIG_FILE) --from yosys.JsonHeader"
	@echo "=========================================="
	@echo "LibreLane flow complete."
	@echo "Results in: $(RUN_DIR)/"
	@echo "=========================================="
	@$(MAKE) results

#----------------------------------------------------------------
# Synthesis Only
# LibreLane does not natively support running a single step via
# the config file in the same way as the standalone OpenROAD flow.
# The recommended approach is to use the --last-step flag to stop
# early, or to use the Python API.
#----------------------------------------------------------------

synth: check_env
	@echo "=========================================="
	@echo "Running LibreLane synthesis only"
	@echo "=========================================="
	$(NIX_RUN) "PDK_ROOT=$(PDK_ROOT) librelane $(CONFIG_FILE) --last-step yosys.Synthesis"
	@echo "Synthesis complete."
	@$(MAKE) _report_synth

_report_synth:
	@LATEST=$$(ls -td $(RUN_DIR)/RUN_* 2>/dev/null | head -1); \
	if [ -n "$$LATEST" ]; then \
		echo "Latest run: $$LATEST"; \
		find $$LATEST -name "*.stat.rpt" -exec echo "--- {} ---" \; -exec cat {} \; 2>/dev/null | head -60; \
	fi

#----------------------------------------------------------------
# Results Summary
# Parse the most recent run directory and display key metrics.
#----------------------------------------------------------------

results:
	@LATEST=$$(ls -td $(RUN_DIR)/RUN_* 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "No completed runs found in $(RUN_DIR)/"; \
		exit 0; \
	fi; \
	echo "=========================================="; \
	echo "Results from: $$LATEST"; \
	echo "=========================================="; \
	echo ""; \
	echo "--- Area ---"; \
	find $$LATEST -name "*area*" -name "*.rpt" | xargs grep -h "Design area\|Chip area" 2>/dev/null | head -5; \
	echo ""; \
	echo "--- Timing (WNS/TNS) ---"; \
	find $$LATEST -name "*timing*" -o -name "*sta*" | xargs grep -h "wns\|tns\|slack" 2>/dev/null | grep -v "^#" | head -10; \
	echo ""; \
	echo "--- Power ---"; \
	find $$LATEST -name "*power*" | xargs grep -h "Total\|Internal\|Switching\|Leakage" 2>/dev/null | head -8; \
	echo ""; \
	echo "--- DRC ---"; \
	find $$LATEST -name "*drc*" | xargs grep -h "violation\|Total" 2>/dev/null | head -5; \
	echo ""; \
	echo "Full reports: $$LATEST/"

#----------------------------------------------------------------
# Clean
#----------------------------------------------------------------

clean:
	@echo "Removing LibreLane run outputs..."
	rm -rf $(RUN_DIR)
	@echo "Clean complete."

#----------------------------------------------------------------
# Help
#----------------------------------------------------------------

help:
	@echo "LibreLane Flow — Available Targets"
	@echo "==================================="
	@echo ""
	@echo "  run         Run the complete LibreLane flow (default)"
	@echo "  synth       Run synthesis only (stops after Yosys)"
	@echo "  results     Show key metrics from the latest completed run"
	@echo "  clean       Remove all run outputs"
	@echo "  check_env   Verify LibreLane and PDK are available"
	@echo "  help        Show this message"
	@echo ""
	@echo "Configuration:"
	@echo "  DESIGN_NAME      = $(DESIGN_NAME)"
	@echo "  CONFIG_FILE      = $(CONFIG_FILE)"
	@echo "  PDK_ROOT         = $(PDK_ROOT)"
	@echo "  LIBRELANE_NIXDIR = $(LIBRELANE_NIXDIR)"
	@echo ""
	@echo "Environment overrides:"
	@echo "  make run PDK_ROOT=/path/to/pdk"
	@echo "  make run LIBRELANE_NIXDIR=/other/librelane/clone"
	@echo ""

#----------------------------------------------------------------
# End of Makefile
#----------------------------------------------------------------
