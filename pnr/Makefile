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
LIBRELANE_SKY130_DIR     := librelane
LIBRELANE_SKY130_CPU_DIR := sky130/cpu
LIBRELANE_SKY130_SOC_DIR := sky130/soc
LIBRELANE_NANGATE45_DIR  := freepdk45
# shared PDK resources (stubs, lib, pdn)
LIBRELANE_ASAP7_ROOT    := asap7
# CPU design directory
LIBRELANE_ASAP7_DIR     := asap7/cpu
# GPU design directory
LIBRELANE_ASAP7_GPU_DIR := asap7/gpu
# SoC top-level design directory (Phase 5 M11)
LIBRELANE_ASAP7_SOC_DIR := asap7/soc
# New designs: copy pnr/asap7/template/ as a starting point

# Maximum number of ASAP7 runs to retain (oldest deleted first)
ASAP7_MAX_RUNS          ?= 10

# Number of threads for detailed routing
DRT_THREADS         ?= 4

#----------------------------------------------------------------
# Phony Targets
#----------------------------------------------------------------

.PHONY: all clean help lint
.PHONY: synth floorplan place cts route parasitics sta power verify gls
.PHONY: report_timing report_power report_area
.PHONY: docker-pull docker-check docker-pdk docker-run docker-synth docker-results
SV2V                ?= /nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v

.PHONY: librelane-sky130 librelane-sky130-cpu librelane-nangate45 librelane-asap7 librelane-asap7-gpu librelane-asap7-soc
.PHONY: asap7-soc-sv2v
.PHONY: librelane-sky130-results librelane-sky130-cpu-results librelane-nangate45-results librelane-asap7-results librelane-asap7-gpu-results librelane-asap7-soc-results
.PHONY: prune-asap7-runs prune-asap7-gpu-runs prune-asap7-soc-runs
.PHONY: macro-views-asap7
.PHONY: flop-count

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
	@echo "  librelane-sky130          - Run full LibreLane flow on Sky130 (pnr/librelane/) — Phase 3 baseline"
	@echo "  librelane-sky130-cpu      - Sky130 CPU Stage 1: REAL Magic DRC + Netgen LVS (pnr/sky130/cpu/) GH#103"
	@echo "  sky130-soc-sv2v           - Convert Sky130 SoC SV files to Verilog-2005 (sanity check, pnr/sky130/soc/)"
	@echo "  librelane-sky130-soc      - Sky130 SoC Stage 2: CPU hard macro + flat periph, real DRC/LVS GH#104"
	@echo "  librelane-nangate45       - Run full LibreLane flow on FreePDK45/nangate45 (pnr/freepdk45/)"
	@echo "  librelane-asap7           - Run full LibreLane flow on ASAP7 CPU (pnr/asap7/), then prune"
	@echo "  librelane-asap7-gpu       - Run full LibreLane flow on ASAP7 GPU (pnr/asap7/gpu/), then prune"
	@echo "  librelane-asap7-soc-synth - Run Yosys synthesis only for ASAP7 SoC (pnr/asap7/soc/) — first-run check"
	@echo "  librelane-asap7-soc       - Run full LibreLane P&R for ASAP7 SoC (expect 4-8 h), then prune"
	@echo "  librelane-sky130-results        - Show metrics from latest Sky130 LibreLane run (Phase 3)"
	@echo "  librelane-sky130-cpu-results    - Show metrics from latest Sky130 CPU Stage 1 run (GH#103)"
	@echo "  librelane-sky130-soc-results    - Show metrics from latest Sky130 SoC Stage 2 run (GH#104)"
	@echo "  librelane-nangate45-results     - Show metrics from latest nangate45 LibreLane run"
	@echo "  librelane-asap7-results         - Show metrics from latest ASAP7 CPU LibreLane run"
	@echo "  flop-count RUN_DIR=<path>       - Flop count breakdown from any LibreLane run's synthesis"
	@echo "  librelane-asap7-gpu-results     - Show metrics from latest ASAP7 GPU LibreLane run"
	@echo "  librelane-asap7-soc-results     - Show metrics from latest ASAP7 SoC LibreLane run"
	@echo "  prune-asap7-runs          - Delete old CPU ASAP7 runs, keep latest ASAP7_MAX_RUNS (default 10)"
	@echo "  prune-asap7-gpu-runs      - Delete old GPU ASAP7 runs, keep latest ASAP7_MAX_RUNS (default 10)"
	@echo "  prune-asap7-soc-runs      - Delete old SoC ASAP7 runs, keep latest ASAP7_MAX_RUNS (default 10)"
	@echo "  macro-views-asap7         - Generate LEF + LIB + netlist macro views from latest ASAP7 run (BLOCK=cpu|gpu, default cpu)"
	@echo "                              (override run: make macro-views-asap7 BLOCK=gpu RUN=asap7/gpu/runs/RUN_...)"
	@echo "  asap7/template/           - Template for new ASAP7 designs (copy to asap7/<design>/)"
	@echo ""
	@echo "  LIBRELANE_DIR     = $(LIBRELANE_DIR)"
	@echo "  MANUAL_PDK_ROOT   = $(MANUAL_PDK_ROOT)"
	@echo "  DRT_THREADS       = $(DRT_THREADS)"
	@echo "  ASAP7_MAX_RUNS    = $(ASAP7_MAX_RUNS)"
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

# Sky130 Stage 1: CPU standalone with REAL Magic DRC + Netgen LVS (GH #103)
# Builds native sky130_rv32i_cpu_top.{lef,lib,nl.v} macro views.
# Uses volare PDK auto-detection (same as librelane-sky130).
librelane-sky130-cpu:
	@echo "=========================================="
	@echo "Running LibreLane flow — Sky130 CPU Stage 1 (real DRC/LVS)"
	@echo "  Config : pnr/$(LIBRELANE_SKY130_CPU_DIR)/config.json"
	@echo "  Tool   : $(LIBRELANE_DIR)"
	@echo "  Runs   : /nobackup/sky130_cpu_runs"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_SKY130_CPU_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_SKY130_CPU_DIR)/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"python3 -m librelane \
		 $(abspath $(LIBRELANE_SKY130_CPU_DIR))/config.json"

librelane-sky130-cpu-results:
	$(call librelane_results,$(LIBRELANE_SKY130_CPU_DIR))

# NOTE: the former `librelane-sky130-sram` target (standalone hardening of
# rtl/soc/sram_controller.sv as a composite macro) was REMOVED. That approach
# was abandoned: its hardened macro could never be PDN-stitched at SoC level
# (unresolvable PSM-0069, ~1001 unconnected nodes). It was replaced by a real
# OpenRAM-compiled macro (sky130_sram_4kbyte_1rw1r_32x1024_8) — see the Stage 2
# SoC section below. Config/artifacts archived to
# /nobackup/abandoned_sram_composite/.

###############################################################################
# Sky130 Stage 2: SoC (CPU hard macro + flat peripherals)  GH #104
#
# sv2v converts all SV files to Verilog-2005 so Yosys read_verilog handles
# packages, structs, and generate blocks without Synlig UHDM.
# GPU is a synthesisable tie-off stub (gpu_top_tieoff.sv); CPU is blackboxed
# (rv32i_cpu_top_stub.sv); SRAM is now ALSO a blackboxed OpenRAM hard macro
# (sky130_sram_4kbyte_1rw1r_32x1024_8_stub.sv, via +define+SRAM_SKY130 --
# see below); boot_rom remains behavioural (ROM-only, no DFFs).
#
# GH #104 SCOPE DECISION (2026-07-23, REVERSES Option C): sram_controller's
# backing store is a real sky130_sram_4kbyte_1rw1r_32x1024_8 OpenRAM hard
# macro again (1024 x 32b, 4 KB), compiled fresh via OpenRAM (see
# memory/pd/run_state.md, openram_sram4k_subtask). This is NOT the old
# custom-hardened composite sram_controller macro (whole AXI4 wrapper +
# behavioral array hardened as one block) that hit the unresolved
# PSM-0069 PDN wall -- that approach is abandoned. Instead, only the raw
# OpenRAM SRAM primitive is blackboxed (u_sram_macro, instantiated inside
# the still-synthesisable rtl/soc/sram_controller.sv control-logic RTL
# under `ifdef SRAM_SKY130`); its LEF is a standard OpenRAM PG abstract
# (vccd1/vssd1 on met3+met4), already proven connectable via
# rv32i_cpu_top's own 10 internal OpenRAM SRAMs (PSM-0040 clean). This
# macro is also ~14x smaller in area (701.64 x 673.335 um) than the
# failed composite block (2585 x 2595 um).
###############################################################################
SKY130_SOC_SV_FILES := \
	$(PROJECT_ROOT)/rtl/soc/axi_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_addr_map_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_periph_map_pkg.sv \
	$(LIBRELANE_SKY130_SOC_DIR)/rv32i_cpu_top_stub.sv \
	$(LIBRELANE_SKY130_SOC_DIR)/gpu_top_tieoff.sv \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_clkgen_stub.sv \
	$(LIBRELANE_SKY130_SOC_DIR)/pll_clkgen_pnr.sv \
	$(PROJECT_ROOT)/rtl/soc/apb4_register_bank.sv \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_apb_regs.sv \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_subsystem.sv \
	$(PROJECT_ROOT)/rtl/soc/axi4_crossbar.sv \
	$(PROJECT_ROOT)/rtl/soc/axi_lite_register_bank.sv \
	$(PROJECT_ROOT)/rtl/soc/axi_lite_interconnect.sv \
	$(PROJECT_ROOT)/rtl/soc/axi4_to_axilite.sv \
	$(PROJECT_ROOT)/rtl/soc/axilite_to_axi4.sv \
	$(PROJECT_ROOT)/rtl/soc/axil_to_apb.sv \
	$(PROJECT_ROOT)/rtl/soc/apb_interconnect.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_bus.sv \
	$(LIBRELANE_SKY130_SOC_DIR)/sky130_sram_4kbyte_1rw1r_32x1024_8_stub.sv \
	$(PROJECT_ROOT)/rtl/soc/sram_controller.sv \
	$(PROJECT_ROOT)/rtl/soc/boot_rom.sv \
	$(PROJECT_ROOT)/rtl/periph/dma_engine.sv \
	$(PROJECT_ROOT)/rtl/periph/interrupt_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/timer.sv \
	$(PROJECT_ROOT)/rtl/periph/uart_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/spi_controller.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_top.sv

SKY130_SOC_SV2V_OUT := $(abspath $(LIBRELANE_SKY130_SOC_DIR)/soc_top_sv2v.v)

sky130-soc-sv2v:
	@echo "=========================================="
	@echo "Pre-processing: sv2v SV -> Verilog-2005 (Sky130 SoC)"
	@echo "  Input: $(words $(SKY130_SOC_SV_FILES)) SV/V files"
	@echo "  Output: $(SKY130_SOC_SV2V_OUT)"
	@echo "  GPU: tie-off stub (synthesisable, no blackbox)"
	@echo "  CPU: blackbox stub (hard macro)"
	@echo "  SRAM: blackbox stub (hard macro, +define+SRAM_SKY130)"
	@echo "=========================================="
	@if [ ! -f "$(SV2V)" ]; then \
		echo "ERROR: sv2v not found at $(SV2V)"; \
		echo "Install via: nix-build '<nixpkgs>' -A haskellPackages.sv2v --no-out-link"; \
		exit 1; fi
	$(SV2V) --define=__pnr__ --define=SRAM_SKY130 $(SKY130_SOC_SV_FILES) -w $(SKY130_SOC_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(SKY130_SOC_SV2V_OUT)) lines"
	@echo "  Clocked always blocks: $$(grep -c 'always.*posedge\|always.*negedge' $(SKY130_SOC_SV2V_OUT))"
	@echo "  DFF count (reg decls): $$(grep -c '^\s*reg\s' $(SKY130_SOC_SV2V_OUT))"
	@echo "  GPU cells (should be 0): $$(grep -c 'gpu_top\b' $(SKY130_SOC_SV2V_OUT) || echo 0)"

# Sky130 Stage 2: SoC P&R with real DRC + LVS.
# Requires:  make sky130-soc-sv2v   (generates soc_top_sv2v.v)
# Requires:  pnr/sky130/cpu/macro/rv32i_cpu_top.{lef,gds,spice,lib}  (Stage-1 outputs)
# Outputs:   pnr/sky130/soc/runs/<RUN>/
# Run dir:   /nobackup/sky130_soc_runs/
librelane-sky130-soc: sky130-soc-sv2v
	@echo "=========================================="
	@echo "Running LibreLane flow — Sky130 SoC Stage 2 (real DRC/LVS)"
	@echo "  Config : pnr/$(LIBRELANE_SKY130_SOC_DIR)/config.json"
	@echo "  Tool   : $(LIBRELANE_DIR)"
	@echo "  Runs   : /nobackup/sky130_soc_runs"
	@echo "  Runtime: expect 4-10 h (3600x1800 um CPU macro + flat periph)"
	@echo "=========================================="
	@# ANTENNA FLOW ENABLED (2026-07-25, GH #104 follow-up). The antenna steps
	@# (Odb.HeuristicDiodeInsertion, Odb.DiodesOnPorts, OpenROAD.RepairAntennas,
	@# OpenROAD.CheckAntennas*) used to be in the --skip list below, which is
	@# why RUN_2026-07-24_21-36-12 reported manufacturability
	@# "Antenna: FAILED -- 557 pin / 442 net violations": the repair flow was
	@# never running, so that number was simply the UNREPAIRED state.
	@# Enabling them works -- RUN_2026-07-25_09-21-05 measured
	@# 556 pin / 440 net -> 154 pin / 129 net via 2018 inserted diodes (~72%
	@# reduction). Stage-1 CPU precedent: 2849 -> 57 pin (~98%).
	@#
	@# Odb.CheckDesignAntennaProperties STAYS SKIPPED, deliberately. It is not
	@# part of the repair flow; it requires a LEF input, which this recipe does
	@# not produce (Magic.WriteLEF is skipped below and config.json sets
	@# RUN_MAGIC_WRITE_LEF: false). Un-skipping it killed RUN_2026-07-25_09-21-05
	@# at step 54 with "CheckDesignAntennaProperties: missing required input
	@# 'LEF'" -- AFTER post-PnR STA/streamout had completed but BEFORE the
	@# DRC/LVS signoff checkers ran. Re-enable it only together with
	@# Magic.WriteLEF.
	@if [ ! -f "$(LIBRELANE_SKY130_SOC_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_SKY130_SOC_DIR)/config.json not found."; exit 1; fi
	@if [ ! -f "$(LIBRELANE_SKY130_SOC_DIR)/soc_top_sv2v.v" ]; then \
		echo "ERROR: soc_top_sv2v.v not found — run: make sky130-soc-sv2v first"; exit 1; fi
	@if [ ! -f "$(LIBRELANE_SKY130_SOC_DIR)/../cpu/macro/rv32i_cpu_top.lef" ]; then \
		echo "ERROR: CPU macro LEF missing — copy Stage-1 macro views to pnr/sky130/cpu/macro/"; exit 1; fi
	mkdir -p /nobackup/sky130_soc_runs
	@[ -L $(LIBRELANE_SKY130_SOC_DIR)/runs ] || \
		ln -sfn /nobackup/sky130_soc_runs $(LIBRELANE_SKY130_SOC_DIR)/runs
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"PYTHONPATH=$(LIBRELANE_DIR) \
		 python3 -m librelane \
		 --skip Checker.LintTimingConstructs \
		 --skip Checker.LintErrors \
		 --skip Checker.YosysSynthChecks \
		 --skip Odb.ReportDisconnectedPins \
		 --skip Checker.DisconnectedPins \
		 --skip Checker.IllegalOverlap \
		 --skip Odb.CheckDesignAntennaProperties \
		 --skip Checker.SetupViolations \
		 --skip Checker.HoldViolations \
		 --skip Checker.MaxSlewViolations \
		 --skip Checker.MaxCapViolations \
		 --skip Magic.WriteLEF \
		 $(abspath $(LIBRELANE_SKY130_SOC_DIR))/config.json"

librelane-sky130-soc-results:
	$(call librelane_results,$(LIBRELANE_SKY130_SOC_DIR))

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
	@$(MAKE) prune-asap7-runs

librelane-asap7-results:
	$(call librelane_results,$(LIBRELANE_ASAP7_DIR))

# ASAP7 GPU: uses same PDK and skip-list as librelane-asap7, but targets pnr/asap7/gpu/
librelane-asap7-gpu:
	@echo "=========================================="
	@echo "Running LibreLane flow — ASAP7 GPU"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_GPU_DIR)/config.json"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Tool     : $(LIBRELANE_DIR)"
	@echo "  Skipping : Odb.HeuristicDiodeInsertion OpenROAD.RepairAntennas"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_GPU_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_GPU_DIR)/config.json not found."; \
		echo "       Create pnr/asap7/gpu/ with a LibreLane config.json to use this target."; \
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
		 $(abspath $(LIBRELANE_ASAP7_GPU_DIR))/config.json"
	@$(MAKE) prune-asap7-gpu-runs

librelane-asap7-gpu-results:
	$(call librelane_results,$(LIBRELANE_ASAP7_GPU_DIR))

# ASAP7 SoC (Phase 5 M11): hierarchical — CPU+GPU as hard macros, flat peripherals
# Die: 720×720 µm, clock: 1750 ps (571 MHz GPU-governed), SYNTH-ONLY for first run.
# To run synthesis only (confirm elaboration before full P&R):
#   make librelane-asap7-soc-synth
# To run the full P&R closure (expect 4–8 h):
#   make librelane-asap7-soc
librelane-asap7-soc-synth:
	@echo "=========================================="
	@echo "Running LibreLane SYNTH-ONLY — ASAP7 SoC"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_SOC_DIR)/config.json"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Tool     : $(LIBRELANE_DIR)"
	@echo "  Step     : Yosys.JsonHeader (synthesis + elaboration only)"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --to Yosys.JsonHeader \
		 --skip Checker.LintTimingConstructs \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath $(LIBRELANE_ASAP7_SOC_DIR))/config.json"

librelane-asap7-soc-synth-only:
	@echo "=========================================="
	@echo "Running LibreLane SYNTH-ONLY (skip JsonHeader) — ASAP7 SoC"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_SOC_DIR)/config.json"
	@echo "  Step     : Yosys.Synthesis only (bypasses Yosys.JsonHeader)"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --from Yosys.Synthesis \
		 --to Yosys.Synthesis \
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
		 $(abspath $(LIBRELANE_ASAP7_SOC_DIR))/config.json"

###############################################################################
# sv2v SoC pre-processing step
# Converts all SoC SV files → plain Verilog-2005 so yosys read_verilog handles
# packages, packed arrays, and generate blocks without Synlig UHDM.
# Output: pnr/asap7/soc/soc_top_sv2v.v (generated, gitignored)
###############################################################################
SOC_SV_FILES := \
	$(PROJECT_ROOT)/rtl/soc/axi_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_addr_map_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_periph_map_pkg.sv \
	$(LIBRELANE_ASAP7_SOC_DIR)/rv32i_cpu_top_stub.sv \
	$(LIBRELANE_ASAP7_SOC_DIR)/gpu_top_stub.sv \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_clkgen_stub.sv \
	$(LIBRELANE_ASAP7_SOC_DIR)/pll_clkgen_pnr.sv \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_axil_regs.sv \
	$(PROJECT_ROOT)/rtl/soc/axi4_crossbar.sv \
	$(PROJECT_ROOT)/rtl/soc/axi_lite_register_bank.sv \
	$(PROJECT_ROOT)/rtl/soc/axi_lite_interconnect.sv \
	$(PROJECT_ROOT)/rtl/soc/axi4_to_axilite.sv \
	$(PROJECT_ROOT)/rtl/soc/axilite_to_axi4.sv \
	$(PROJECT_ROOT)/rtl/soc/sram_controller.sv \
	$(PROJECT_ROOT)/rtl/soc/boot_rom.sv \
	$(PROJECT_ROOT)/rtl/periph/dma_engine.sv \
	$(PROJECT_ROOT)/rtl/periph/interrupt_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/timer.sv \
	$(PROJECT_ROOT)/rtl/periph/uart_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/spi_controller.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_top.sv

SOC_SV2V_OUT := $(abspath $(LIBRELANE_ASAP7_SOC_DIR)/soc_top_sv2v.v)

asap7-soc-sv2v:
	@echo "=========================================="
	@echo "Pre-processing: sv2v SV → Verilog-2005"
	@echo "  Input: $(words $(SOC_SV_FILES)) SV/V files"
	@echo "  Output: $(SOC_SV2V_OUT)"
	@echo "=========================================="
	@if [ ! -f "$(SV2V)" ]; then \
		echo "ERROR: sv2v not found at $(SV2V)"; \
		echo "Install via: nix-build '<nixpkgs>' -A haskellPackages.sv2v --no-out-link"; \
		exit 1; fi
	$(SV2V) $(SOC_SV_FILES) -w $(SOC_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(SOC_SV2V_OUT)) lines, $$(grep -c 'always.*posedge\|always.*negedge' $(SOC_SV2V_OUT)) clocked always blocks"

librelane-asap7-soc: asap7-soc-sv2v
	@echo "=========================================="
	@echo "Running LibreLane flow — ASAP7 SoC (full P&R)"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_SOC_DIR)/config.json"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Tool     : $(LIBRELANE_DIR)"
	@echo "  Runtime  : expect 4-8 h (hierarchical, 520x520 um)"
	@echo "  Run dir  : /nobackup/asap7_soc_runs/"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/config.json not found."; exit 1; fi
	mkdir -p /nobackup/asap7_soc_runs
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --skip Checker.LintTimingConstructs \
		 --skip Checker.LintErrors \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath $(LIBRELANE_ASAP7_SOC_DIR))/config.json"
	@$(MAKE) prune-asap7-soc-runs

librelane-asap7-soc-results:
	$(call librelane_results,$(LIBRELANE_ASAP7_SOC_DIR))

# flop-count: DFF breakdown from any LibreLane run's synthesis log.
# Usage: make flop-count RUN_DIR=asap7/gpu/runs/RUN_2026-05-24_09-12-00
#        make flop-count RUN_DIR=asap7/runs/RUN_2026-05-20_06-27-10
RUN_DIR ?=

flop-count:
	@if [ -z "$(RUN_DIR)" ]; then \
		echo "Usage: make flop-count RUN_DIR=<path/to/RUN_*>"; \
		echo "  GPU runs: asap7/gpu/runs/RUN_*"; \
		echo "  CPU runs: asap7/runs/RUN_*"; \
		exit 1; fi; \
	SYNTH_LOG=$(RUN_DIR)/05-yosys-synthesis/yosys-synthesis.log; \
	if [ ! -f "$$SYNTH_LOG" ]; then \
		echo "No synthesis log in $(RUN_DIR) — has synthesis completed?"; exit 1; fi; \
	echo "=========================================="; \
	echo "Flop count — $(RUN_DIR)"; \
	echo "=========================================="; \
	grep 'mapped.*cells to.*\\DFF' "$$SYNTH_LOG" | \
	awk '{n=$$2; cell=substr($$6,2); counts[cell]+=n; tot+=n} \
	     END{for(c in counts) printf "  %-42s %8d\n",c,counts[c]; \
	         printf "  %-42s %8d\n","Total flops",tot}'

#----------------------------------------------------------------
# Run pruning: keep only the latest ASAP7_MAX_RUNS runs
# Runs are named RUN_YYYY-MM-DD_HH-MM-SS; lexicographic sort == time order.
#----------------------------------------------------------------

define prune_runs
	@RUNS_DIR="$(1)/runs"; \
	if [ ! -d "$$RUNS_DIR" ]; then exit 0; fi; \
	COUNT=$$(ls -d $$RUNS_DIR/RUN_* 2>/dev/null | wc -l); \
	if [ "$$COUNT" -le "$(ASAP7_MAX_RUNS)" ]; then \
		echo "$(2): $$COUNT run(s) present (<= $(ASAP7_MAX_RUNS)), nothing to prune."; \
		exit 0; \
	fi; \
	TO_DELETE=$$(ls -dt $$RUNS_DIR/RUN_* 2>/dev/null | tail -n +$$(($(ASAP7_MAX_RUNS)+1))); \
	NDEL=$$(echo "$$TO_DELETE" | wc -l); \
	echo "$(2): keeping latest $(ASAP7_MAX_RUNS) of $$COUNT run(s), removing $$NDEL old run(s)."; \
	echo "$$TO_DELETE" | xargs rm -rf; \
	echo "Prune complete."
endef

prune-asap7-runs:
	$(call prune_runs,$(LIBRELANE_ASAP7_DIR),ASAP7 CPU)

prune-asap7-gpu-runs:
	$(call prune_runs,$(LIBRELANE_ASAP7_GPU_DIR),ASAP7 GPU)

prune-asap7-soc-runs:
	$(call prune_runs,$(LIBRELANE_ASAP7_SOC_DIR),ASAP7 SoC)

#----------------------------------------------------------------
# ASAP7 macro views: abstract LEF + timing-model LIB + gate-level netlist
#
# Generates the three artifacts needed to instantiate a block (rv32i_cpu_top or
# gpu_top) as a hard macro in a top-level (Phase-5 SoC) P&R run.  Mirrors the
# SRAM macro convention: LEF (abstract) + LIB (timing model) + NL (blackbox
# netlist).  BLOCK selects the design (cpu | gpu, default cpu).
#
# GDS is omitted: Magic has no ASAP7 tech file and the SRAM stub has no GDS
# geometry — same reason the existing librelane-asap7 target skips streamout.
#
# Uses a standalone OpenROAD script (scripts/asap7_macro_views.tcl) against
# the saved final/odb so no full flow re-run is needed.
#
# Usage:
#   make macro-views-asap7                                   # latest CPU run
#   make macro-views-asap7 BLOCK=gpu                         # latest GPU run
#   make macro-views-asap7 BLOCK=gpu RUN=asap7/gpu/runs/RUN_… # specific run
#
# Output (cpu): pnr/asap7/cpu/macro/{rv32i_cpu_top.lef,
#                           rv32i_cpu_top__nom_tt_025C_0p7V.lib,
#                           rv32i_cpu_top.nl.v.gz}
# Output (gpu): pnr/asap7/gpu/macro/{gpu_top.lef,
#                           gpu_top__nom_tt_025C_0p7V.lib,
#                           gpu_top.nl.v.gz}
#
# The flat post-route netlist is gzipped (gpu_top.nl.v is ~103 MB raw, over
# GitHub's 100 MB limit; ~9.6 MB gzipped). LEF + LIB are read directly by P&R
# tools and stay uncompressed; run `gunzip -k <design>.nl.v.gz` to restore the
# netlist for full-flat sim/LEC. Raw .nl.v is gitignored.
#----------------------------------------------------------------

BLOCK ?= cpu

macro-views-asap7:
	@set -e; \
	case "$(BLOCK)" in \
	  cpu) DESIGN="rv32i_cpu_top"; SRAM_LIB_NAME="sram_1rw_256x32_asap7_TT_0p7V_25C.lib"; \
	       BLOCK_DIR="$(LIBRELANE_ASAP7_DIR)"; BLOCK_LABEL="CPU";; \
	  gpu) DESIGN="gpu_top";       SRAM_LIB_NAME="sram_1rw_128x32_asap7_TT_0p7V_25C.lib"; \
	       BLOCK_DIR="$(LIBRELANE_ASAP7_GPU_DIR)"; BLOCK_LABEL="GPU";; \
	  *)   echo "ERROR: BLOCK must be cpu or gpu (got '$(BLOCK)')"; exit 1;; \
	esac; \
	echo "=========================================="; \
	echo "Generating ASAP7 macro views — $$DESIGN"; \
	echo "=========================================="; \
	if [ -n "$(RUN)" ]; then CPU_RUN="$(RUN)"; \
	else CPU_RUN="$$(ls -td $$BLOCK_DIR/runs/RUN_* 2>/dev/null | head -1)"; fi; \
	if [ -z "$$CPU_RUN" ]; then \
		echo "ERROR: No ASAP7 $$BLOCK_LABEL runs found. Run 'make librelane-asap7' first."; exit 1; fi; \
	CPU_RUN="$$(realpath "$$CPU_RUN")"; \
	echo "  Run : $$CPU_RUN"; \
	ODB="$$CPU_RUN/final/odb/$$DESIGN.odb"; \
	SDC="$$CPU_RUN/final/sdc/$$DESIGN.sdc"; \
	NL="$$CPU_RUN/final/nl/$$DESIGN.nl.v"; \
	if [ ! -f "$$ODB" ]; then echo "ERROR: $$ODB not found"; exit 1; fi; \
	MACRO_DIR="$(abspath .)/$$BLOCK_DIR/macro"; \
	mkdir -p "$$MACRO_DIR"; \
	ASAP7_LD="$(MANUAL_PDK_ROOT)/asap7/libs.ref/asap7sc7p5t_SIMPLE/lib"; \
	SRAM_LIB="$(abspath $(LIBRELANE_ASAP7_ROOT))/$$SRAM_LIB_NAME"; \
	export ODB_PATH="$$ODB" \
	       SDC_PATH="$$SDC" \
	       DESIGN_NAME="$$DESIGN" \
	       MACRO_OUT_DIR="$$MACRO_DIR" \
	       ASAP7_LIBS="$$ASAP7_LD/asap7sc7p5t_AO_RVT_TT_nldm_211120.lib $$ASAP7_LD/asap7sc7p5t_INVBUF_RVT_TT_nldm_220122.lib $$ASAP7_LD/asap7sc7p5t_OA_RVT_TT_nldm_211120.lib $$ASAP7_LD/asap7sc7p5t_SEQ_RVT_TT_nldm_220123.lib $$ASAP7_LD/asap7sc7p5t_SIMPLE_RVT_TT_nldm_211120.lib $$SRAM_LIB"; \
	(cd $(LIBRELANE_DIR) && nix-shell --run \
		"openroad -exit $(abspath scripts/asap7_macro_views.tcl)"); \
	cp "$$NL" "$$MACRO_DIR/$$DESIGN.nl.v"; \
	gzip -f -6 "$$MACRO_DIR/$$DESIGN.nl.v"; \
	echo ""; \
	echo "Macro views staged to $$MACRO_DIR (netlist gzipped; gunzip -k to use):"; \
	ls -lh "$$MACRO_DIR/"

#----------------------------------------------------------------
# Schematic viewer (yosys `show` -> SVG via graphviz)
#----------------------------------------------------------------
# Renders a schematic of the CPU or GPU design using the same Synlig
# (read_systemverilog) front-end LibreLane uses, with the ASAP7 SRAM/ICG cells
# as blackboxes. xdot is not available in the shell, so output is written as SVG.
#
# SCHEM_BLOCK selects the design (cpu | gpu, default gpu); SCHEM_MODULE selects
# the module within it (defaults to the block's top: rv32i_cpu_top / gpu_top).
# Default render is the RTL-elaboration view (hierarchy preserved: submodule
# instances render as boxes) — compact and fast. SCHEM_SYNTH=1 gives the
# gate-level synthesised view, which for any non-trivial module produces a very
# large graph that graphviz `dot` lays out slowly (use only on small leaf modules).
#
#   make schematic                                  # gpu_top, RTL view
#   make schematic SCHEM_BLOCK=cpu                  # rv32i_cpu_top, RTL view
#   make schematic SCHEM_BLOCK=cpu SCHEM_MODULE=rv32i_alu
#   make schematic SCHEM_MODULE=warp_scheduler
#   make schematic SCHEM_MODULE=vector_alu SCHEM_SYNTH=1   # gate-level (slow/large)
#   (gpu-schematic is kept as an alias for `schematic SCHEM_BLOCK=gpu`)
#
# Output: pnr/asap7/schematics/schematic_<module>.svg (+ .dot)
SCHEM_BLOCK ?= gpu
SCHEM_OUTDIR := asap7/schematics

GPU_SCHEM_SRCS := \
	$(RTL_DIR)/gpu/gpu_pkg.sv \
	asap7/sram_1rw_128x32_asap7_stub.v \
	$(RTL_DIR)/gpu/vector_register_file.sv \
	$(RTL_DIR)/gpu/vector_alu.sv \
	$(RTL_DIR)/gpu/gpu_compute_unit.sv \
	$(RTL_DIR)/gpu/warp_scheduler.sv \
	$(RTL_DIR)/gpu/gpu_command_queue.sv \
	$(RTL_DIR)/gpu/gpu_memory_unit.sv \
	$(RTL_DIR)/gpu/memory_coalescer.sv \
	$(RTL_DIR)/gpu/shared_memory.sv \
	$(RTL_DIR)/gpu/gpu_top.sv

CPU_SCHEM_SRCS := \
	asap7/sram_1rw_256x32_asap7_stub.v \
	asap7/icg_asap7_stub.v \
	$(RTL_DIR)/cpu/core/rv32i_pipeline_pkg.sv \
	$(RTL_DIR)/mem/rv32i_cache_pkg.sv \
	$(RTL_DIR)/mem/rv32i_clock_gate.sv \
	$(RTL_DIR)/cpu/core/rv32i_alu.sv \
	$(RTL_DIR)/cpu/core/rv32i_branch_comp.sv \
	$(RTL_DIR)/cpu/core/rv32i_imm_gen.sv \
	$(RTL_DIR)/cpu/core/rv32i_regfile.sv \
	$(RTL_DIR)/cpu/core/rv32i_decode.sv \
	$(RTL_DIR)/cpu/core/rv32i_forwarding_unit.sv \
	$(RTL_DIR)/cpu/core/rv32i_hazard_unit.sv \
	$(RTL_DIR)/cpu/core/rv32i_interrupt_ctrl.sv \
	$(RTL_DIR)/cpu/core/rv32i_csr_file.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_if.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_id.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex1c.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex1b.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_ex2.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(RTL_DIR)/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(RTL_DIR)/mem/rv32i_icache.sv \
	$(RTL_DIR)/mem/rv32i_dcache.sv \
	$(RTL_DIR)/mem/rv32i_cache_arbiter.sv \
	$(RTL_DIR)/cpu/core/rv32i_core.sv \
	$(RTL_DIR)/cpu/rv32i_cpu_top.sv

ifeq ($(SCHEM_BLOCK),cpu)
  SCHEM_SRCS    := $(CPU_SCHEM_SRCS)
  SCHEM_MODULE  ?= rv32i_cpu_top
  SCHEM_DEFINES := -DSRAM_ASAP7 -DUSE_ICG_CELL
else
  SCHEM_SRCS    := $(GPU_SCHEM_SRCS)
  SCHEM_MODULE  ?= gpu_top
  SCHEM_DEFINES :=
endif

.PHONY: schematic gpu-schematic cpu-schematic
gpu-schematic: ; $(MAKE) schematic SCHEM_BLOCK=gpu SCHEM_MODULE=$(SCHEM_MODULE) SCHEM_SYNTH=$(SCHEM_SYNTH)
cpu-schematic: ; $(MAKE) schematic SCHEM_BLOCK=cpu SCHEM_MODULE=$(SCHEM_MODULE) SCHEM_SYNTH=$(SCHEM_SYNTH)
schematic:
	@echo "=========================================="
	@echo "Rendering yosys schematic"
	@echo "  Block  : $(SCHEM_BLOCK)"
	@echo "  Module : $(SCHEM_MODULE)"
	@echo "  Mode   : $(if $(SCHEM_SYNTH),synthesised gate-level (large/slow),RTL elaboration)"
	@echo "  Output : pnr/$(SCHEM_OUTDIR)/schematic_$(SCHEM_MODULE).svg"
	@echo "=========================================="
	@mkdir -p $(SCHEM_OUTDIR)
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"cd $(abspath .) && yosys -p ' \
		   read_systemverilog $(SCHEM_DEFINES) $(SCHEM_SRCS); \
		   $(if $(SCHEM_SYNTH),synth -top $(SCHEM_MODULE),hierarchy -top $(SCHEM_MODULE); proc; opt_clean); \
		   show -colors 1 -format svg -prefix $(SCHEM_OUTDIR)/schematic_$(SCHEM_MODULE) $(SCHEM_MODULE)'"
	@echo "Schematic written to pnr/$(SCHEM_OUTDIR)/schematic_$(SCHEM_MODULE).svg"

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
