#================================================================
# OpenROAD Physical Design Flow - Makefile
# Target: Phase 3 RV32I CPU + L1 I-Cache + L1 D-Cache
# PDK: Sky130 HD (sky130_fd_sc_hd)
# Frequency: 75 MHz (13.333 ns period)
#================================================================

#----------------------------------------------------------------
# Configuration
#----------------------------------------------------------------

# Design parameters
export TOP_MODULE   ?= rv32i_cpu_top
export CLOCK_PERIOD ?= 13.333
export CLOCK_PORT   ?= clk_i

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

#----------------------------------------------------------------
# OpenLane 1 Docker configuration
#----------------------------------------------------------------

# Docker command — auto-detects snap install; override with DOCKER_CMD=sudo docker if needed
DOCKER_CMD          ?= $(shell command -v docker 2>/dev/null || echo /snap/bin/docker)

# OpenLane 1 image
OPENLANE_IMAGE      ?= efabless/openlane:master

# OpenLane 1 design directory (contains config.json in OL1 format)
OPENLANE1_DIR       := openlane1

# PDK root — mounted into the container at /root/.volare
# volare installs PDKs here by default; override with PDK_ROOT=/other/path
PDK_ROOT            ?= $(HOME)/.volare

# PDK version pinned to OL1 1.1.1 default (bdc9412b)
OL1_PDK_VERSION     ?= bdc9412b3e468c102d01b7cf6337be06ec6e9c9a

# Absolute path to the project root (parent of pnr/)
PROJECT_ROOT        := $(abspath ..)

# Constraint files
SDC_FILE    := $(CONSTR_DIR)/phase3_cache.sdc
UPF_FILE    := $(CONSTR_DIR)/phase3_cache.upf

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
.PHONY: docker-pull docker-check docker-pdk docker-run docker-synth docker-results

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
	@echo "OpenLane 1 Docker Targets (recommended):"
	@echo "  docker-pull    - Pull the OpenLane 1 Docker image"
	@echo "  docker-check   - Verify Docker is ready"
	@echo "  docker-pdk     - Download Sky130A PDK via volare (run once, ~1 GB)"
	@echo "  docker-run     - Run full flow via OpenLane 1 Docker"
	@echo "  docker-synth   - Run synthesis only via Docker"
	@echo "  docker-results - Show metrics from latest Docker run"
	@echo ""
	@echo "Raw OpenROAD Flow Targets (requires tools on PATH):"
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
	@echo "  TOP_MODULE      = $(TOP_MODULE)"
	@echo "  CLOCK_PERIOD    = $(CLOCK_PERIOD) ns"
	@echo "  PDK             = $(PDK)"
	@echo "  OPENLANE_IMAGE  = $(OPENLANE_IMAGE)"
	@echo "  OPENLANE1_DIR   = $(OPENLANE1_DIR)"
	@echo "  PDK_ROOT        = $(PDK_ROOT)"
	@echo "  DOCKER_CMD      = $(DOCKER_CMD)"
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
# OpenLane 1 Docker Targets
#----------------------------------------------------------------

# Pull the OpenLane 1 Docker image
docker-pull:
	@echo "=========================================="
	@echo "Pulling OpenLane 1 Docker image"
	@echo "  Image: $(OPENLANE_IMAGE)"
	@echo "=========================================="
	$(DOCKER_CMD) pull $(OPENLANE_IMAGE)
	@echo "Pull complete."

# Verify Docker is running and the image is available
docker-check:
	@$(DOCKER_CMD) info >/dev/null 2>&1 || \
		(echo "ERROR: Docker daemon not running or not accessible."; \
		 echo ""; \
		 echo "  Fix socket permissions (snap Docker):"; \
		 echo "    sudo chown root:docker /var/run/docker.sock"; \
		 echo ""; \
		 echo "  Or start the daemon:"; \
		 echo "    sudo systemctl start docker"; \
		 echo "    newgrp docker"; \
		 exit 1)
	@$(DOCKER_CMD) image inspect $(OPENLANE_IMAGE) >/dev/null 2>&1 || \
		(echo "ERROR: Image $(OPENLANE_IMAGE) not found locally."; \
		 echo "       Run: make docker-pull"; \
		 exit 1)
	@echo "Docker environment OK."
	@echo "  Image    : $(OPENLANE_IMAGE)"
	@echo "  Design   : $(OPENLANE1_DIR)"
	@echo "  PDK_ROOT : $(PDK_ROOT)"
	@echo "  Mount    : $(PROJECT_ROOT) -> /work"

# Download Sky130A PDK into PDK_ROOT via volare (run once, ~1 GB)
docker-pdk: docker-check
	@echo "=========================================="
	@echo "Downloading Sky130A PDK via volare"
	@echo "  Version : $(OL1_PDK_VERSION)"
	@echo "  Target  : $(PDK_ROOT)/sky130A"
	@echo "=========================================="
	@mkdir -p $(PDK_ROOT)
	$(DOCKER_CMD) run --rm \
		-v $(PDK_ROOT):/root/.volare \
		$(OPENLANE_IMAGE) \
		bash -c "volare enable --pdk sky130 $(OL1_PDK_VERSION)"
	@echo "PDK download complete: $(PDK_ROOT)/sky130A"

# Run the full OpenLane 1 flow via Docker
docker-run: docker-check
	@echo "=========================================="
	@echo "Running OpenLane 1 flow (Docker)"
	@echo "  Design   : $(OPENLANE1_DIR)/config.json"
	@echo "  Image    : $(OPENLANE_IMAGE)"
	@echo "  PDK_ROOT : $(PDK_ROOT)"
	@echo "=========================================="
	@if [ ! -d "$(PDK_ROOT)/sky130A" ]; then \
		echo "WARNING: PDK not found at $(PDK_ROOT)/sky130A"; \
		echo "         Run 'make docker-pdk' first to download it (~1 GB)."; \
		exit 1; \
	fi
	$(DOCKER_CMD) run --rm \
		-v $(PROJECT_ROOT):/work \
		-v $(PDK_ROOT):/root/.volare \
		$(OPENLANE_IMAGE) \
		bash -c "PDK_ROOT=/root/.volare \
		         flow.tcl \
		         -design /work/pnr/$(OPENLANE1_DIR) \
		         -run_path /work/pnr/$(OPENLANE1_DIR)/runs"
	@echo "=========================================="
	@echo "OpenLane 1 flow complete."
	@echo "Results in: pnr/$(OPENLANE1_DIR)/runs/"
	@echo "=========================================="
	@$(MAKE) docker-results

# Run synthesis only — OL1 1.1.1 removed -from/-to step selection;
# this target runs the full flow but is kept as an alias for docker-run.
docker-synth: docker-run

# Show key metrics from the latest Docker flow run
docker-results:
	@LATEST=$$(ls -td $(OPENLANE1_DIR)/runs/RUN_* 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "No completed OpenLane runs found in pnr/$(OPENLANE1_DIR)/runs/"; \
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
	find $$LATEST \( -name "*timing*" -o -name "*sta*" \) | xargs grep -h "wns\|tns\|slack" 2>/dev/null | grep -v "^#" | head -10; \
	echo ""; \
	echo "--- Power ---"; \
	find $$LATEST -name "*power*" | xargs grep -h "Total\|Internal\|Switching\|Leakage" 2>/dev/null | head -8; \
	echo ""; \
	echo "--- Final summary ---"; \
	find $$LATEST -name "final_summary*" | xargs cat 2>/dev/null | head -30; \
	echo ""; \
	echo "Full reports: $$LATEST/"

#----------------------------------------------------------------
# Clean Target
#----------------------------------------------------------------

clean:
	@echo "Cleaning generated files..."
	rm -rf $(WORK_DIR) $(LOGS_DIR) $(REPORTS_DIR) $(RESULTS_DIR) openlane/runs openlane1/runs
	@echo "Clean complete."

#----------------------------------------------------------------
# End of Makefile
#----------------------------------------------------------------
