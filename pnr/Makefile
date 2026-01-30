#================================================================
# OpenROAD Physical Design Flow - Makefile
# Target: Phase 1 RV32I Single-Cycle CPU
#================================================================

#----------------------------------------------------------------
# Configuration
#----------------------------------------------------------------

# Design parameters
export TOP_MODULE   ?= rv32i_cpu_top
export CLOCK_PERIOD ?= 10.0
export CLOCK_PORT   ?= clk

# PDK selection (sky130 or asap7)
export PDK          ?= sky130

# Directories
export RTL_DIR      := ../rtl
export TB_DIR       := ../tb
export DOCS_DIR     := ../docs
export CONFIG_DIR   := config
export SCRIPTS_DIR  := scripts
export CONSTR_DIR   := constraints
export LOGS_DIR     := logs
export REPORTS_DIR  := reports
export RESULTS_DIR  := results
export WORK_DIR     := work

# Tools
YOSYS       := yosys
OPENROAD    := openroad
STA         := sta
KLAYOUT     := klayout
VERILATOR   := verilator

# Constraint files
SDC_FILE    := $(CONSTR_DIR)/phase1_cpu.sdc
UPF_FILE    := $(CONSTR_DIR)/phase1_cpu.upf

# Output files
NETLIST     := $(RESULTS_DIR)/$(TOP_MODULE).v
DEF_FILE    := $(RESULTS_DIR)/$(TOP_MODULE).def
SPEF_FILE   := $(RESULTS_DIR)/$(TOP_MODULE).spef
SDF_FILE    := $(RESULTS_DIR)/$(TOP_MODULE).sdf
GDS_FILE    := $(RESULTS_DIR)/$(TOP_MODULE).gds

#----------------------------------------------------------------
# Phony Targets
#----------------------------------------------------------------

.PHONY: all clean help
.PHONY: synth floorplan place cts route parasitics sta power verify gls
.PHONY: report_timing report_power report_area

#----------------------------------------------------------------
# Default Target
#----------------------------------------------------------------

all: synth floorplan place cts route parasitics sta power
	@echo "=========================================="
	@echo "Physical design flow complete!"
	@echo "=========================================="
	@$(MAKE) report_summary

#----------------------------------------------------------------
# Help Target
#----------------------------------------------------------------

help:
	@echo "OpenROAD Physical Design Flow - Available Targets"
	@echo "=================================================="
	@echo ""
	@echo "Main Flow Targets:"
	@echo "  all          - Run complete flow (synth through power)"
	@echo "  synth        - Run RTL synthesis (Yosys)"
	@echo "  floorplan    - Run floorplanning (OpenROAD)"
	@echo "  place        - Run placement (OpenROAD)"
	@echo "  cts          - Run clock tree synthesis (OpenROAD)"
	@echo "  route        - Run routing (OpenROAD)"
	@echo "  parasitics   - Extract parasitics (OpenRCX)"
	@echo "  sta          - Run static timing analysis (OpenSTA)"
	@echo "  power        - Run power analysis (OpenROAD)"
	@echo "  verify       - Run physical verification (KLayout)"
	@echo "  gls          - Run gate-level simulation (Verilator)"
	@echo ""
	@echo "Report Targets:"
	@echo "  report_timing  - Show timing summary"
	@echo "  report_power   - Show power summary"
	@echo "  report_area    - Show area summary"
	@echo "  report_summary - Show all summaries"
	@echo ""
	@echo "Utility Targets:"
	@echo "  clean        - Remove all generated files"
	@echo "  help         - Show this help message"
	@echo ""
	@echo "Configuration:"
	@echo "  TOP_MODULE   = $(TOP_MODULE)"
	@echo "  CLOCK_PERIOD = $(CLOCK_PERIOD) ns"
	@echo "  PDK          = $(PDK)"
	@echo ""

#----------------------------------------------------------------
# Stage 1: Synthesis
#----------------------------------------------------------------

synth: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Running RTL Synthesis (Yosys)"
	@echo "=========================================="
	$(YOSYS) -c $(SCRIPTS_DIR)/01_synth.tcl | tee $(LOGS_DIR)/synth.log
	@echo "Synthesis complete. Check $(LOGS_DIR)/synth.log"

#----------------------------------------------------------------
# Stage 2: Floorplan
#----------------------------------------------------------------

floorplan: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Running Floorplanning (OpenROAD)"
	@echo "=========================================="
	$(OPENROAD) -no_init -exit $(SCRIPTS_DIR)/02_floorplan.tcl | tee $(LOGS_DIR)/floorplan.log
	@echo "Floorplan complete. Check $(LOGS_DIR)/floorplan.log"

#----------------------------------------------------------------
# Stage 3: Placement
#----------------------------------------------------------------

place: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Running Placement (OpenROAD)"
	@echo "=========================================="
	$(OPENROAD) -no_init -exit $(SCRIPTS_DIR)/03_place.tcl | tee $(LOGS_DIR)/place.log
	@echo "Placement complete. Check $(LOGS_DIR)/place.log"

#----------------------------------------------------------------
# Stage 4: Clock Tree Synthesis
#----------------------------------------------------------------

cts: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Running Clock Tree Synthesis (OpenROAD)"
	@echo "=========================================="
	$(OPENROAD) -no_init -exit $(SCRIPTS_DIR)/04_cts.tcl | tee $(LOGS_DIR)/cts.log
	@echo "CTS complete. Check $(LOGS_DIR)/cts.log"

#----------------------------------------------------------------
# Stage 5: Routing
#----------------------------------------------------------------

route: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Running Routing (OpenROAD)"
	@echo "=========================================="
	$(OPENROAD) -no_init -exit $(SCRIPTS_DIR)/05_route.tcl | tee $(LOGS_DIR)/route.log
	@echo "Routing complete. Check $(LOGS_DIR)/route.log"

#----------------------------------------------------------------
# Stage 6: Parasitic Extraction
#----------------------------------------------------------------

parasitics: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Extracting Parasitics (OpenRCX)"
	@echo "=========================================="
	$(OPENROAD) -no_init -exit $(SCRIPTS_DIR)/06_parasitics.tcl | tee $(LOGS_DIR)/parasitics.log
	@echo "Parasitic extraction complete. Check $(LOGS_DIR)/parasitics.log"

#----------------------------------------------------------------
# Stage 7: Static Timing Analysis
#----------------------------------------------------------------

sta: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Running Static Timing Analysis (OpenSTA)"
	@echo "=========================================="
	$(STA) $(SCRIPTS_DIR)/07_sta.tcl | tee $(LOGS_DIR)/sta.log
	@echo "STA complete. Check $(LOGS_DIR)/sta.log"

#----------------------------------------------------------------
# Stage 8: Power Analysis
#----------------------------------------------------------------

power: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Running Power Analysis (OpenROAD)"
	@echo "=========================================="
	$(OPENROAD) -no_init -exit $(SCRIPTS_DIR)/08_power.tcl | tee $(LOGS_DIR)/power.log
	@echo "Power analysis complete. Check $(LOGS_DIR)/power.log"

#----------------------------------------------------------------
# Stage 9: Physical Verification
#----------------------------------------------------------------

verify: $(LOGS_DIR) $(RESULTS_DIR) $(REPORTS_DIR)
	@echo "=========================================="
	@echo "Running Physical Verification (KLayout)"
	@echo "=========================================="
	@echo "TODO: Implement KLayout DRC/LVS scripts"
	@echo "Physical verification placeholder"

#----------------------------------------------------------------
# Stage 10: Gate-Level Simulation
#----------------------------------------------------------------

gls: $(LOGS_DIR) $(RESULTS_DIR)
	@echo "=========================================="
	@echo "Running Gate-Level Simulation"
	@echo "=========================================="
	@echo "TODO: Integrate with ../sim Makefile"
	@echo "Gate-level simulation placeholder"

#----------------------------------------------------------------
# Report Targets
#----------------------------------------------------------------

report_timing:
	@echo "=========================================="
	@echo "Timing Report Summary"
	@echo "=========================================="
	@if [ -f $(REPORTS_DIR)/timing_setup.rpt ]; then \
		grep -A 5 "slack" $(REPORTS_DIR)/timing_setup.rpt | head -20; \
	else \
		echo "No timing report found. Run 'make sta' first."; \
	fi

report_power:
	@echo "=========================================="
	@echo "Power Report Summary"
	@echo "=========================================="
	@if [ -f $(REPORTS_DIR)/power.rpt ]; then \
		grep -A 10 "Total Power" $(REPORTS_DIR)/power.rpt; \
	else \
		echo "No power report found. Run 'make power' first."; \
	fi

report_area:
	@echo "=========================================="
	@echo "Area Report Summary"
	@echo "=========================================="
	@if [ -f $(REPORTS_DIR)/synth_area.rpt ]; then \
		grep "Chip area" $(REPORTS_DIR)/synth_area.rpt; \
	else \
		echo "No area report found. Run 'make synth' first."; \
	fi

report_summary: report_area report_timing report_power
	@echo "=========================================="
	@echo "Flow Summary Complete"
	@echo "=========================================="

#----------------------------------------------------------------
# Directory Creation
#----------------------------------------------------------------

$(LOGS_DIR):
	@mkdir -p $(LOGS_DIR)

$(REPORTS_DIR):
	@mkdir -p $(REPORTS_DIR)

$(RESULTS_DIR):
	@mkdir -p $(RESULTS_DIR)

$(WORK_DIR):
	@mkdir -p $(WORK_DIR)

#----------------------------------------------------------------
# Clean Target
#----------------------------------------------------------------

clean:
	@echo "Cleaning generated files..."
	rm -rf $(WORK_DIR) $(LOGS_DIR) $(REPORTS_DIR) $(RESULTS_DIR)
	@echo "Clean complete."

#----------------------------------------------------------------
# End of Makefile
#----------------------------------------------------------------
