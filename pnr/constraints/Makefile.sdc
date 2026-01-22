#================================================================
# SDC Constraint Verification Makefile
# Include this in main Makefile or use standalone
#================================================================

#----------------------------------------------------------------
# SDC File Selection
#----------------------------------------------------------------

# Default to enhanced SDC for pre-CTS stages
SDC_PRE_CTS  := constraints/phase1_cpu_enhanced.sdc
SDC_POST_CTS := constraints/phase1_cpu_post_cts.sdc
SDC_BASELINE := constraints/phase1_cpu.sdc

# Auto-select SDC file based on flow stage
# Override with: make synth SDC_FILE=constraints/phase1_cpu_enhanced.sdc
ifeq ($(MAKECMDGOALS),cts)
    SDC_FILE ?= $(SDC_POST_CTS)
else ifeq ($(MAKECMDGOALS),route)
    SDC_FILE ?= $(SDC_POST_CTS)
else ifeq ($(MAKECMDGOALS),sta)
    SDC_FILE ?= $(SDC_POST_CTS)
else
    SDC_FILE ?= $(SDC_PRE_CTS)
endif

#----------------------------------------------------------------
# SDC Verification Targets
#----------------------------------------------------------------

.PHONY: check_sdc sdc_info help_sdc list_sdc

# Check SDC constraint coverage
check_sdc:
	@echo "=========================================="
	@echo "Checking SDC Constraints"
	@echo "SDC File: $(SDC_FILE)"
	@echo "=========================================="
	@if [ ! -f $(SDC_FILE) ]; then \
		echo "ERROR: SDC file not found: $(SDC_FILE)"; \
		exit 1; \
	fi
	@echo "Running constraint verification..."
	@$(STA) -no_splash -exit constraints/check_constraints.tcl | tee logs/sdc_check.log
	@echo "Results saved to: logs/sdc_check.log"

# Display SDC file information
sdc_info:
	@echo "=========================================="
	@echo "SDC File Information"
	@echo "=========================================="
	@echo ""
	@echo "Current SDC File: $(SDC_FILE)"
	@echo ""
	@echo "Available SDC Files:"
	@echo "  $(SDC_BASELINE) - Original baseline constraints"
	@echo "  $(SDC_PRE_CTS)  - Enhanced (recommended for pre-CTS)"
	@echo "  $(SDC_POST_CTS) - Post-CTS with tighter uncertainty"
	@echo ""
	@echo "Constraint Summary:"
	@echo "  Clock Period:    10.0 ns (100 MHz)"
	@echo "  AXI I/O Delay:   max=2.0ns, min=0.5ns"
	@echo "  APB I/O Delay:   max=3.0ns, min=1.0ns"
	@echo "  Total Ports:     ~40 (18 inputs, 20 outputs)"
	@echo ""
	@if [ -f $(SDC_FILE) ]; then \
		echo "Current SDC File Contents:"; \
		echo "----------------------------------------"; \
		grep -E "^create_clock|^set_clock_uncertainty|^set_input_delay|^set_output_delay|^set_false_path" $(SDC_FILE) | head -20; \
		echo "..."; \
		echo ""; \
		echo "Total lines: $$(wc -l < $(SDC_FILE))"; \
	fi

# List all constraint-related files
list_sdc:
	@echo "=========================================="
	@echo "SDC Constraint Files"
	@echo "=========================================="
	@ls -lh constraints/*.sdc 2>/dev/null || echo "No SDC files found"
	@echo ""
	@echo "Documentation Files:"
	@ls -lh constraints/*.md 2>/dev/null || echo "No documentation found"
	@echo ""
	@echo "Verification Scripts:"
	@ls -lh constraints/*.tcl 2>/dev/null || echo "No TCL scripts found"

# SDC-specific help
help_sdc:
	@echo "=========================================="
	@echo "SDC Constraint Targets"
	@echo "=========================================="
	@echo ""
	@echo "Verification Targets:"
	@echo "  make check_sdc        - Verify all ports are constrained"
	@echo "  make sdc_info         - Display SDC file information"
	@echo "  make list_sdc         - List all SDC-related files"
	@echo ""
	@echo "SDC File Selection:"
	@echo "  make synth            - Uses: $(SDC_PRE_CTS)"
	@echo "  make cts              - Uses: $(SDC_POST_CTS)"
	@echo "  make sta              - Uses: $(SDC_POST_CTS)"
	@echo ""
	@echo "Manual Override:"
	@echo "  make synth SDC_FILE=constraints/phase1_cpu.sdc"
	@echo ""
	@echo "Available SDC Files:"
	@echo "  $(SDC_BASELINE) - Baseline"
	@echo "  $(SDC_PRE_CTS)  - Enhanced (recommended)"
	@echo "  $(SDC_POST_CTS) - Post-CTS"
	@echo ""
	@echo "Documentation:"
	@echo "  constraints/README_SDC.md        - Full documentation"
	@echo "  constraints/QUICK_REFERENCE.md   - Quick lookup"
	@echo "  constraints/SDC_FILES_SUMMARY.md - File overview"
	@echo ""

#----------------------------------------------------------------
# SDC Validation Checks
#----------------------------------------------------------------

# Pre-flight check before synthesis
validate_sdc_pre_synth:
	@echo "Validating SDC file for synthesis..."
	@if [ ! -f $(SDC_FILE) ]; then \
		echo "ERROR: SDC file not found: $(SDC_FILE)"; \
		exit 1; \
	fi
	@echo "SDC file found: $(SDC_FILE)"
	@echo "Checking for required constraints..."
	@grep -q "create_clock" $(SDC_FILE) || (echo "ERROR: No clock definition found"; exit 1)
	@grep -q "set_input_delay" $(SDC_FILE) || (echo "WARNING: No input delays found"; exit 0)
	@grep -q "set_output_delay" $(SDC_FILE) || (echo "WARNING: No output delays found"; exit 0)
	@echo "SDC validation passed"

# Post-CTS SDC check
validate_sdc_post_cts:
	@echo "Validating post-CTS SDC file..."
	@if [ ! -f $(SDC_POST_CTS) ]; then \
		echo "ERROR: Post-CTS SDC file not found: $(SDC_POST_CTS)"; \
		exit 1; \
	fi
	@echo "Checking for post-CTS specific constraints..."
	@grep -q "set_clock_uncertainty.*-setup" $(SDC_POST_CTS) || \
		(echo "WARNING: Post-CTS should have separate setup/hold uncertainty"; exit 0)
	@echo "Post-CTS SDC validation passed"

#----------------------------------------------------------------
# Integration with Main Flow
#----------------------------------------------------------------

# Hook into main synthesis target (if including in main Makefile)
.PHONY: synth_with_sdc
synth_with_sdc: validate_sdc_pre_synth
	@echo "Running synthesis with SDC: $(SDC_FILE)"
	# Main synthesis commands would go here

# Hook into CTS target
.PHONY: cts_with_sdc
cts_with_sdc: validate_sdc_post_cts
	@echo "Running CTS with post-CTS SDC: $(SDC_POST_CTS)"
	# Main CTS commands would go here

#----------------------------------------------------------------
# Quick Timing Analysis
#----------------------------------------------------------------

# Quick timing check (requires OpenSTA)
quick_sta:
	@echo "=========================================="
	@echo "Quick Static Timing Analysis"
	@echo "=========================================="
	@if [ ! -f $(NETLIST) ]; then \
		echo "ERROR: Netlist not found. Run 'make synth' first."; \
		exit 1; \
	fi
	@echo "Netlist: $(NETLIST)"
	@echo "SDC:     $(SDC_FILE)"
	@echo ""
	@echo "read_liberty $$PDK_LIBERTY" > $(WORK_DIR)/quick_sta.tcl
	@echo "read_verilog $(NETLIST)" >> $(WORK_DIR)/quick_sta.tcl
	@echo "link_design $(TOP_MODULE)" >> $(WORK_DIR)/quick_sta.tcl
	@echo "read_sdc $(SDC_FILE)" >> $(WORK_DIR)/quick_sta.tcl
	@echo "report_checks -path_delay max -format full_clock" >> $(WORK_DIR)/quick_sta.tcl
	@echo "report_checks -path_delay min -format full_clock" >> $(WORK_DIR)/quick_sta.tcl
	@echo "report_wns" >> $(WORK_DIR)/quick_sta.tcl
	@echo "report_tns" >> $(WORK_DIR)/quick_sta.tcl
	@$(STA) -no_splash -exit $(WORK_DIR)/quick_sta.tcl | tee logs/quick_sta.log
	@echo ""
	@echo "Results saved to: logs/quick_sta.log"

#----------------------------------------------------------------
# Usage Examples
#----------------------------------------------------------------

# Example: Full flow with SDC checking
.PHONY: flow_with_checks
flow_with_checks: check_sdc synth cts sta
	@echo "Flow complete with SDC verification"

#----------------------------------------------------------------
# End of SDC Makefile
#----------------------------------------------------------------
