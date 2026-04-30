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
# LibreLane configuration
#----------------------------------------------------------------

# LibreLane repo (nix-shell entry point)
LIBRELANE_DIR       ?= $(HOME)/Downloads/Github/librelane

# PDK root for manual-pdk flows (nangate45, asap7)
MANUAL_PDK_ROOT     ?= $(HOME)/pdk

# LibreLane config directories
LIBRELANE_SKY130_DIR    := librelane
LIBRELANE_NANGATE45_DIR := freepdk45
LIBRELANE_ASAP7_DIR     := asap7

# Number of threads for detailed routing
DRT_THREADS         ?= 4

#----------------------------------------------------------------
# Phony Targets
#----------------------------------------------------------------

.PHONY: all clean help lint
.PHONY: synth floorplan place cts route parasitics sta power verify gls
.PHONY: report_timing report_power report_area
.PHONY: docker-pull docker-check docker-pdk docker-run docker-synth docker-results
.PHONY: librelane-sky130 librelane-nangate45 librelane-asap7
.PHONY: librelane-sky130-results librelane-nangate45-results librelane-asap7-results

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
	@echo "LibreLane Targets (nix-shell, recommended):"
	@echo "  librelane-sky130      - Run full LibreLane flow on Sky130 (pnr/librelane/)"
	@echo "  librelane-nangate45   - Run full LibreLane flow on FreePDK45/nangate45 (pnr/freepdk45/)"
	@echo "  librelane-asap7       - Run full LibreLane flow on ASAP7 (pnr/asap7/)"
	@echo "  librelane-sky130-results    - Show metrics from latest Sky130 LibreLane run"
	@echo "  librelane-nangate45-results - Show metrics from latest nangate45 LibreLane run"
	@echo "  librelane-asap7-results     - Show metrics from latest ASAP7 LibreLane run"
	@echo ""
	@echo "  LIBRELANE_DIR     = $(LIBRELANE_DIR)"
	@echo "  MANUAL_PDK_ROOT   = $(MANUAL_PDK_ROOT)"
	@echo "  DRT_THREADS       = $(DRT_THREADS)"
	@echo ""
	@echo "OpenLane 1 Docker Targets:"
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
	@echo "  lint         - Verilator lint/compile check (nix-shell, no simulator needed)"
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
# Verilator Lint / Compile Check
# Runs via nix-shell (matches cocotb simulation environment).
# Uses sim/sram_1rw_256x32_verilator.v behavioral stub for SRAM macros.
#----------------------------------------------------------------

# RTL sources in compile order (packages first, top last)
RTL_SOURCES := \
	$(RTL_DIR)/cpu/core/rv32i_pipeline_pkg.sv \
	$(RTL_DIR)/mem/rv32i_cache_pkg.sv \
	../sim/sram_1rw_256x32_verilator.v \
	$(RTL_DIR)/cpu/rv32i_cpu_top.sv \
	$(RTL_DIR)/cpu/core/rv32i_core.sv \
	$(RTL_DIR)/cpu/core/rv32i_decode.sv \
	$(RTL_DIR)/cpu/core/rv32i_alu.sv \
	$(RTL_DIR)/cpu/core/rv32i_regfile.sv \
	$(RTL_DIR)/cpu/core/rv32i_imm_gen.sv \
	$(RTL_DIR)/cpu/core/rv32i_branch_comp.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_if.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_id.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(RTL_DIR)/cpu/core/rv32i_hazard_unit.sv \
	$(RTL_DIR)/cpu/core/rv32i_forwarding_unit.sv \
	$(RTL_DIR)/cpu/core/rv32i_csr_file.sv \
	$(RTL_DIR)/cpu/core/rv32i_interrupt_ctrl.sv \
	$(RTL_DIR)/cpu/rv32i_axi_arbiter.sv \
	$(RTL_DIR)/mem/rv32i_icache.sv \
	$(RTL_DIR)/mem/rv32i_dcache.sv \
	$(RTL_DIR)/mem/rv32i_cache_arbiter.sv

VERILATOR_LINT_FLAGS := --lint-only -sv \
	-Wno-WIDTH -Wno-UNUSED -Wno-BLKSEQ -Wno-UNOPTFLAT --no-timing \
	--top-module $(TOP_MODULE)

lint:
	@echo "=========================================="
	@echo "Running Verilator lint/compile check"
	@echo "  Top: $(TOP_MODULE)"
	@echo "=========================================="
	nix-shell -p verilator --run \
		"verilator $(VERILATOR_LINT_FLAGS) $(RTL_SOURCES)"
	@echo "Lint PASSED."

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
# LibreLane Flow Targets
# Runs LibreLane via nix-shell from LIBRELANE_DIR.
# Sky130 uses the volare-managed PDK (no --manual-pdk).
# nangate45 and ASAP7 use a manually structured PDK under MANUAL_PDK_ROOT.
#----------------------------------------------------------------

# Helper macro: pretty-print latest run directory for a given config dir
define librelane_results
	@LATEST=$$(ls -td $(1)/runs/RUN_* 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "No completed LibreLane runs found in pnr/$(1)/runs/"; \
		exit 0; \
	fi; \
	echo "=========================================="; \
	echo "Results from: $$LATEST"; \
	echo "=========================================="; \
	echo ""; \
	echo "--- Area ---"; \
	find $$LATEST -name "*.json" | xargs grep -h '"design_area"\|"wire_length"' 2>/dev/null | head -5; \
	echo ""; \
	echo "--- Timing (WNS/TNS) ---"; \
	find $$LATEST \( -name "*timing*" -o -name "*sta*" \) -name "*.rpt" \
		| xargs grep -h "wns\|tns\|slack" 2>/dev/null | grep -v "^#" | head -10; \
	echo ""; \
	echo "--- Power ---"; \
	find $$LATEST -name "*power*" -name "*.rpt" \
		| xargs grep -h "Total\|Internal\|Switching\|Leakage" 2>/dev/null | head -8; \
	echo ""; \
	echo "Full results: $$LATEST/"
endef

# Sky130: LibreLane uses volare PDK (PDK_ROOT auto-detected, no --manual-pdk)
librelane-sky130:
	@echo "=========================================="
	@echo "Running LibreLane flow — Sky130 HD"
	@echo "  Config : pnr/$(LIBRELANE_SKY130_DIR)/config.json"
	@echo "  Tool   : $(LIBRELANE_DIR)"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_SKY130_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_SKY130_DIR)/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"python3 -m librelane \
		 $(abspath $(LIBRELANE_SKY130_DIR))/config.json"

librelane-sky130-results:
	$(call librelane_results,$(LIBRELANE_SKY130_DIR))

# nangate45 / FreePDK45: uses manually structured PDK under MANUAL_PDK_ROOT
librelane-nangate45:
	@echo "=========================================="
	@echo "Running LibreLane flow — nangate45 / FreePDK45"
	@echo "  Config   : pnr/$(LIBRELANE_NANGATE45_DIR)/config.json"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Tool     : $(LIBRELANE_DIR)"
	@echo "  Skipping : Odb.HeuristicDiodeInsertion OpenROAD.RepairAntennas"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_NANGATE45_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_NANGATE45_DIR)/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --skip Checker.LintTimingConstructs \
		 --skip Odb.HeuristicDiodeInsertion \
		 --skip OpenROAD.RepairAntennas \
		 --skip Odb.ReportDisconnectedPins \
		 --skip Checker.DisconnectedPins \
		 --skip Magic.SpiceExtraction \
		 --skip Checker.IllegalOverlap \
		 --skip Odb.CheckDesignAntennaProperties \
		 --skip Checker.LVS \
		 $(abspath $(LIBRELANE_NANGATE45_DIR))/config.json"

librelane-nangate45-results:
	$(call librelane_results,$(LIBRELANE_NANGATE45_DIR))

# ASAP7: uses manually structured PDK under MANUAL_PDK_ROOT
# Config directory pnr/asap7/ must exist with a valid config.json.
librelane-asap7:
	@echo "=========================================="
	@echo "Running LibreLane flow — ASAP7"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_DIR)/config.json"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Tool     : $(LIBRELANE_DIR)"
	@echo "  Skipping : Odb.HeuristicDiodeInsertion OpenROAD.RepairAntennas"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_DIR)/config.json not found."; \
		echo "       Create pnr/asap7/ with a LibreLane config.json to use this target."; \
		exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --skip Checker.LintTimingConstructs \
		 --skip Odb.HeuristicDiodeInsertion \
		 --skip Odb.DiodesOnPorts \
		 --skip OpenROAD.RepairAntennas \
		 --skip Odb.ReportDisconnectedPins \
		 --skip Checker.DisconnectedPins \
		 --skip Magic.SpiceExtraction \
		 --skip Checker.IllegalOverlap \
		 --skip Odb.CheckDesignAntennaProperties \
		 --skip Checker.LVS \
		 --skip OpenROAD.CheckAntennas \
		 --skip OpenROAD.CheckAntennas-1 \
		 --skip Magic.StreamOut \
		 --skip KLayout.StreamOut \
		 --skip Magic.WriteLEF \
		 --skip Checker.SetupViolations \
		 --skip Checker.HoldViolations \
		 --skip Checker.MaxSlewViolations \
		 --skip Checker.MaxCapViolations \
		 $(abspath $(LIBRELANE_ASAP7_DIR))/config.json"

librelane-asap7-results:
	$(call librelane_results,$(LIBRELANE_ASAP7_DIR))

#----------------------------------------------------------------
# Clean Target
#----------------------------------------------------------------

clean:
	@echo "Cleaning generated files..."
	rm -rf $(WORK_DIR) $(LOGS_DIR) $(REPORTS_DIR) $(RESULTS_DIR) \
		openlane/runs openlane1/runs \
		$(LIBRELANE_SKY130_DIR)/runs \
		$(LIBRELANE_NANGATE45_DIR)/runs \
		$(LIBRELANE_ASAP7_DIR)/runs
	@echo "Clean complete."

#----------------------------------------------------------------
# End of Makefile
#----------------------------------------------------------------
