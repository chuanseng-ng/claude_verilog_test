#================================================================
# OpenROAD Physical Design Flow - Makefile
# Target: Phase 3 RV32I CPU + L1 I-Cache + L1 D-Cache
# PDK: Sky130 HD (sky130_fd_sc_hd)
# Frequency: 75 MHz (13.333 ns period)
#================================================================

# Doc: tm:pd:makefile, cr:pd:makefile
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

ORFS_ROOT            ?= $(HOME)/Downloads/Github/OpenROAD-flow-scripts

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
SOC_CONFIG ?= config.json
# New designs: copy pnr/asap7/template/ as a starting point

# Maximum number of ASAP7 runs to retain (oldest deleted first)
ASAP7_MAX_RUNS          ?= 10

# Number of threads for detailed routing
DRT_THREADS         ?= 4

ASAP7_OPENROAD_BIN  ?= /nix/store/hgqrwa4687mf7n0y2x6lcgx1kj42sfga-openroad-26Q2/bin/openroad

ASAP7_STA_BIN       ?= /nix/store/q5ycjmn0d9awbcq05c75z2rmgwjgbc9g-opensta/bin/sta

ASAP7_OR_SHIM_DIR   := $(abspath .openroad-shim)

# Empty by default, so every non-ASAP7 flow keeps LibreLane's own OpenROAD.
OR_PATH_PREFIX      :=

SYNTH_GATE_PLUGIN_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))plugins)
SYNTH_GATE_ENV       := PYTHONPATH=$(SYNTH_GATE_PLUGIN_DIR):\$$PYTHONPATH


#----------------------------------------------------------------
# Phony Targets
#----------------------------------------------------------------

.PHONY: all clean help lint
.PHONY: synth floorplan place cts route parasitics sta power verify gls
.PHONY: report_timing report_power report_area
.PHONY: docker-pull docker-check docker-pdk docker-run docker-synth docker-results
SV2V                ?= /nix/store/bknj130bjxz018c73yawkjmbzjhppqbc-sv2v-0.0.13.1/bin/sv2v

.PHONY: install-asap7-rcx-rules check-asap7-rcx-rules check-asap7-openroad
.PHONY: librelane-sky130 librelane-sky130-cpu librelane-nangate45 librelane-asap7 librelane-asap7-gpu librelane-asap7-soc
.PHONY: librelane-asap7-soc-multiclock
.PHONY: librelane-asap7-soc-multiclock-hier
.PHONY: librelane-asap7-3014 librelane-asap7-gpu-3014
.PHONY: check-cdc-timing-asap7-soc check-cdc-timing-sky130-soc
.PHONY: asap7-soc-sv2v
.PHONY: librelane-sky130-results librelane-sky130-cpu-results librelane-nangate45-results librelane-asap7-results librelane-asap7-gpu-results librelane-asap7-soc-results
.PHONY: prune-asap7-runs prune-asap7-gpu-runs prune-asap7-soc-runs
.PHONY: check-asap7-routing check-asap7-gpu-routing check-asap7-soc-routing
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
	@echo "  install-asap7-rcx-rules   - Vendor the real ASAP7 OpenRCX rules from ORFS_ROOT into MANUAL_PDK_ROOT"
	@echo "  check-asap7-rcx-rules     - Fail loudly if the ASAP7 RCX rules are still the 0-byte stub"
	@echo "  librelane-asap7           - Run full LibreLane flow on ASAP7 CPU (pnr/asap7/), verify routing, then prune"
	@echo "  librelane-asap7-gpu       - Run full LibreLane flow on ASAP7 GPU (pnr/asap7/gpu/), verify routing, then prune"
	@echo "  librelane-asap7-soc-synth - Run Yosys synthesis only for ASAP7 SoC (pnr/asap7/soc/) — first-run check"
	@echo "  librelane-asap7-soc       - Run full LibreLane P&R for ASAP7 SoC (expect 4-8 h), verify routing, then prune"
	@echo "  librelane-asap7-soc-multiclock - GH #96: same flow with the 2-clock SDC (config_multiclock.json)"
	@echo "                              (SOC_CONFIG overrides the config file for all three librelane-asap7-soc* targets)"
	@echo "  check-cdc-timing-asap7-soc - Post-route CDC budget check (OpenSTA, phase5_soc_multiclock_check.sdc; GH #96)"
	@echo "  check-cdc-timing-sky130-soc - Post-route CDC budget check, Sky130 SoC (sky130_soc_cdc_check.sdc; bead j41m.5)"
	@echo "  check-asap7-routing        - Fail loudly if the latest ASAP7 CPU run committed zero routed wires (bead xy6)"
	@echo "  check-asap7-gpu-routing    - Fail loudly if the latest ASAP7 GPU run committed zero routed wires (bead xy6)"
	@echo "  check-asap7-soc-routing    - Fail loudly if the latest ASAP7 SoC run committed zero routed wires (bead xy6)"
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

# RTL sources in compile order (packages first, top last).
# Mirrors the import-closed order proven in pnr/asap7/cpu/config.json; see
# tools/verif/check_source_closure.py, which now gates this list.
RTL_SOURCES := \
	../sim/sram_1rw_256x32_verilator.v \
	$(RTL_DIR)/soc/axi_pkg.sv \
	$(RTL_DIR)/soc/soc_addr_map_pkg.sv \
	$(RTL_DIR)/cpu/core/rv32i_pipeline_pkg.sv \
	$(RTL_DIR)/mem/rv32i_cache_pkg.sv \
	$(RTL_DIR)/soc/dft/mem_collar.sv \
	$(RTL_DIR)/soc/dft/mbist_ctrl.sv \
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
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
		 $(abspath $(LIBRELANE_SKY130_DIR))/config.json"

librelane-sky130-results:
	$(call librelane_results,$(LIBRELANE_SKY130_DIR))

SKY130_CPU_SV_FILES := \
	$(PROJECT_ROOT)/rtl/soc/axi_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_addr_map_pkg.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_pipeline_pkg.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_cache_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mem_collar.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_ctrl.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_alu.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_branch_comp.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_imm_gen.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_regfile.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_decode.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_forwarding_unit.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_hazard_unit.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_interrupt_ctrl.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_csr_file.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_if.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_id.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_ex.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_ex1c.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_ex1b.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_ex2.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_icache.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_dcache.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_cache_arbiter.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_core.sv \
	$(PROJECT_ROOT)/rtl/cpu/rv32i_cpu_top.sv

SKY130_CPU_SV2V_DEFINES := --define=PDK_sky130A --define=SCL_sky130_fd_sc_hd \
	--define=__librelane__ --define=__pnr__ --define=SRAM_SKY130
SKY130_CPU_SV2V_OUT     := $(abspath $(LIBRELANE_SKY130_CPU_DIR)/rv32i_cpu_top_sv2v.v)

.PHONY: sky130-cpu-sv2v
sky130-cpu-sv2v:
	@echo "=========================================="
	@echo "Pre-processing: sv2v SV -> Verilog-2005 (Sky130 CPU macro, bead dud4)"
	@echo "  Input : $(words $(SKY130_CPU_SV_FILES)) SV files"
	@echo "  Output: $(SKY130_CPU_SV2V_OUT)"
	@echo "=========================================="
	@if [ ! -f "$(SV2V)" ]; then \
		echo "ERROR: sv2v not found at $(SV2V)"; \
		echo "Install via: nix-build '<nixpkgs>' -A haskellPackages.sv2v --no-out-link"; \
		exit 1; fi
	$(SV2V) $(SKY130_CPU_SV2V_DEFINES) $(SKY130_CPU_SV_FILES) -w $(SKY130_CPU_SV2V_OUT)
	@# sv2v strips the `/* verilator lint_off/on BLKLOOPINIT */` pair that wraps the
	@# cache valid-array reset loops; without it LibreLane's Checker.LintErrors
	@# (Verilator on the flattened Verilog-2005) hard-fails. Same fix and rationale
	@# as asap7-cpu-sv2v (lint only; no effect on synthesis).
	sed -i '1i /* verilator lint_off BLKLOOPINIT */' $(SKY130_CPU_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(SKY130_CPU_SV2V_OUT)) lines"

# Prints the exact sv2v inputs of the Sky130 CPU macro ("DEFINES ..." then one "FILE <path>" per line) so
# tools/verif/synth_gate/ci_smoke.sh elaborates the same source list/defines the flow uses (single source of truth).
.PHONY: sky130-cpu-sv2v-inputs
sky130-cpu-sv2v-inputs:
	@echo "DEFINES $(SKY130_CPU_SV2V_DEFINES)"
	@for f in $(SKY130_CPU_SV_FILES); do echo "FILE $$f"; done

.PHONY: sky130-soc-sv2v-inputs asap7-soc-sv2v-inputs
sky130-soc-sv2v-inputs:
	@echo "DEFINES $(SKY130_SOC_SV2V_DEFINES)"
	@for f in $(SKY130_SOC_SV_FILES); do echo "FILE $$(readlink -f $$f)"; done

asap7-soc-sv2v-inputs:
	@echo "DEFINES $(SOC_SV2V_DEFINES)"
	@for f in $(SOC_SV_FILES); do echo "FILE $$(readlink -f $$f)"; done

librelane-sky130-cpu: sky130-cpu-sv2v
	@echo "=========================================="
	@echo "Running LibreLane flow — Sky130 CPU Stage 1 (real DRC/LVS)"
	@echo "  Config : pnr/$(LIBRELANE_SKY130_CPU_DIR)/config.json"
	@echo "  Tool   : $(LIBRELANE_DIR)"
	@echo "  Runs   : /nobackup/sky130_cpu_runs"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_SKY130_CPU_DIR)/config.json" ]; then \
		echo "ERROR: $(LIBRELANE_SKY130_CPU_DIR)/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) CVT_SCAN_OPENROAD=$(ASAP7_OPENROAD_BIN) PYTHONPATH=$(SYNTH_GATE_PLUGIN_DIR):$(SKY130_SOC_PLUGIN_DIR):\$$PYTHONPATH python3 -m librelane \
		 $(abspath $(LIBRELANE_SKY130_CPU_DIR))/config.json"

.PHONY: sky130-cpu-pin-lock-check
sky130-cpu-pin-lock-check:
	python3 $(PROJECT_ROOT)/tools/verif/pin_lock.py check \
		--lef $(PROJECT_ROOT)/pnr/sky130/cpu/macro/rv32i_cpu_top.lef \
		--def $(PROJECT_ROOT)/pnr/sky130/cpu/pin_template.def $(if $(NEW_LEF),--new-lef $(NEW_LEF))

librelane-sky130-cpu-results:
	$(call librelane_results,$(LIBRELANE_SKY130_CPU_DIR))


SKY130_SOC_SV_FILES := \
	$(PROJECT_ROOT)/rtl/soc/axi_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_addr_map_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_periph_map_pkg.sv \
	$(LIBRELANE_SKY130_SOC_DIR)/rv32i_cpu_top_stub.sv \
	$(LIBRELANE_SKY130_SOC_DIR)/gpu_top_tieoff.sv \
	$(LIBRELANE_SKY130_SOC_DIR)/sky130_clkcells_stub.v \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_clkgen_stub.sv \
	$(LIBRELANE_SKY130_SOC_DIR)/pll_clkgen_pnr.sv \
	$(PROJECT_ROOT)/rtl/soc/apb4_register_bank.sv \
	$(PROJECT_ROOT)/rtl/soc/pmu.sv \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_apb_regs.sv \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_subsystem.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_clk_mux.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_rst_mux.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_ctrl_ports.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/jtag_tap.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_clk_switch.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_ctrl.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_ctrl.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_xing.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_ctl_hold.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_status_sync.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mem_collar.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/soc_mbist.sv \
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
	$(PROJECT_ROOT)/rtl/periph/gpio_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/pwm_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/watchdog_timer.sv \
	$(PROJECT_ROOT)/rtl/periph/trng_lfsr_entropy.sv \
	$(PROJECT_ROOT)/rtl/periph/trng.sv \
	$(PROJECT_ROOT)/rtl/periph/i2c_bit_engine.sv \
	$(PROJECT_ROOT)/rtl/periph/i2c_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/aes128_core.sv \
	$(PROJECT_ROOT)/rtl/periph/sha256_core.sv \
	$(PROJECT_ROOT)/rtl/periph/crypto_accel.sv \
	$(PROJECT_ROOT)/rtl/npu/npu_mac_array.sv \
	$(PROJECT_ROOT)/rtl/npu/npu_weight_mem.sv \
	$(PROJECT_ROOT)/rtl/npu/npu_top.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_clock_gate.sv \
	$(PROJECT_ROOT)/rtl/soc/cdc/cdc_sync.sv \
	$(PROJECT_ROOT)/rtl/soc/cdc/cdc_reset_sync.sv \
	$(PROJECT_ROOT)/rtl/soc/cdc/cdc_gray_fifo.sv \
	$(PROJECT_ROOT)/rtl/soc/async_axi_fifo.sv \
	$(PROJECT_ROOT)/rtl/soc/apb_cdc_bridge.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_top.sv

SKY130_SOC_SV2V_OUT := $(abspath $(LIBRELANE_SKY130_SOC_DIR)/soc_top_sv2v.v)
# One definition, used by the sv2v recipe below AND by sky130-soc-sv2v-inputs (CI), so the gate
# elaborates exactly what the flow elaborates.
SKY130_SOC_SV2V_DEFINES := --define=__pnr__ --define=SRAM_SKY130 --define=USE_SKY130_CLKCELLS

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
	$(SV2V) $(SKY130_SOC_SV2V_DEFINES) $(SKY130_SOC_SV_FILES) -w $(SKY130_SOC_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(SKY130_SOC_SV2V_OUT)) lines"
	@echo "  Clocked always blocks: $$(grep -c 'always.*posedge\|always.*negedge' $(SKY130_SOC_SV2V_OUT))"
	@echo "  DFF count (reg decls): $$(grep -c '^\s*reg\s' $(SKY130_SOC_SV2V_OUT))"
	@echo "  GPU cells (should be 0): $$(grep -c 'gpu_top\b' $(SKY130_SOC_SV2V_OUT) || echo 0)"

DFT_TAP_CHECK_ARGS := --tap-prefix u_dft_ctrl.u_tap --tap-prefix u_dft_ctrl.u_tck_cg \
	--tap-prefix u_dft_ctrl.u_clk_sw --tap-prefix u_dft_ctrl.u_sw_rst --tap-alt-clock scan_clk_i \
	--scan-mode-net u_dft_ctrl.scan_mode_o --expect-tap-flops 20 \
	--tap-allowed-nets u_dft_ctrl.tap_scan --tap-allowed-nets u_dft_ctrl.tap_serial \
	--tap-allowed-nets u_dft_ctrl.tap_rst_assert --tap-allowed-nets u_dft_ctrl.tap_scan_en \
	--tap-allowed-nets u_dft_ctrl.test_clk_o --tap-allowed-nets tdo_o --tap-allowed-nets tdo_oe_o \
	--expect-reset-sync u_dft_ctrl.u_tap.u_trst_sync=u_dft_ctrl.u_tap \
	--expect-reset-sync u_dft_ctrl.u_sw_rst=u_dft_ctrl.u_clk_sw \
	--tap-allowed-nets u_dft_ctrl.mbist_ctl_o --tap-allowed-nets u_dft_ctrl.mbist_wr_o \
	--tap-allowed-nets u_dft_ctrl.mbist_rst_tck_n_o --tap-allowed-nets u_dft_ctrl.mbist_force_o \
	--expect-reset-sync u_mbist.u_xing_core.u_rd_rst=u_mbist.u_xing_core.u_fifo@any \
	--expect-reset-sync u_mbist.g_cpu.u_xing_cpu.u_rd_rst=u_mbist.g_cpu.u_xing_cpu.u_fifo@any \
	--tck-prefix u_mbist --expect-tck-flops 290 \
	--tck-sink u_mbist.u_xing_core.u_fifo.u_wr_ptr_to_rd --tck-sink u_mbist.u_xing_core.u_hold \
	--tck-sink u_mbist.g_cpu.u_xing_cpu.u_fifo.u_wr_ptr_to_rd --tck-sink u_mbist.g_cpu.u_xing_cpu.u_hold
.PHONY: dft-scan-check
dft-scan-check: sky130-soc-sv2v
	YOSYS=$(YOSYS) python3 $(PROJECT_ROOT)/tools/dft/check_scan_clk_rst.py \
		--netlist $(SKY130_SOC_SV2V_OUT) --models $(PROJECT_ROOT)/tools/dft/sky130_cell_models.v --expect-gates 20 $(DFT_TAP_CHECK_ARGS) --expect-clock-gates 1

# (--models: the clock roots are hand-instantiated sky130 cells since USE_SKY130_CLKCELLS; the netlist carries only their
# black-box stubs, so the checker needs the analysis models to trace the enable / select cones through them.)
# Same proof on the ASAP7 SoC netlist. That netlist instantiates ICGx1_ASAP7_75t_R and sram_1rw_256x32_asap7
# without defining them, so the checker needs the analysis models (it fails rather than pass vacuously).
.PHONY: dft-scan-check-asap7
dft-scan-check-asap7: asap7-soc-sv2v
	YOSYS=$(YOSYS) python3 $(PROJECT_ROOT)/tools/dft/check_scan_clk_rst.py \
		--netlist $(SOC_SV2V_OUT) --models $(PROJECT_ROOT)/tools/dft/asap7_cell_models.v --expect-gates 20 $(DFT_TAP_CHECK_ARGS) --expect-clock-gates 1

.PHONY: dft-scan-check-cpu-macro dft-scan-check-cpu-macro-asap7
dft-scan-check-cpu-macro: sky130-cpu-sv2v
	YOSYS=$(YOSYS) python3 $(PROJECT_ROOT)/tools/dft/check_scan_clk_rst.py \
		--netlist $(SKY130_CPU_SV2V_OUT) --top rv32i_cpu_top --models $(PROJECT_ROOT)/pnr/sky130/sky130_sram_1kbyte_1rw1r_32x256_8_stub.v \
		--clock-port clk_i --max-async-pins 0 --expect-seq-min 900 --all-latches-need-scan-mode

dft-scan-check-cpu-macro-asap7: asap7-cpu-sv2v
	YOSYS=$(YOSYS) python3 $(PROJECT_ROOT)/tools/dft/check_scan_clk_rst.py \
		--netlist $(CPU_SV2V_OUT) --top rv32i_cpu_top --models $(PROJECT_ROOT)/tools/dft/asap7_cell_models.v \
		--clock-port clk_i --max-async-pins 0 --expect-seq-min 900 --all-latches-need-scan-mode --expect-latches-min 10 --expect-clock-gates 10

# Sky130 Stage 2: SoC P&R with real DRC + LVS.
# Requires:  make sky130-soc-sv2v   (generates soc_top_sv2v.v)
# Requires:  pnr/sky130/cpu/macro/rv32i_cpu_top.{lef,gds,spice,lib}  (Stage-1 outputs)

# Extra --skip flags appended to the Sky130 SoC invocation. Empty by default, so
# `librelane-sky130-soc` is unchanged and the adopted sign-off stays reproducible.
SKY130_SOC_EXTRA_SKIP ?=

SKY130_SOC_CONFIG ?= config_rccal.json
SKY130_SOC_PLUGIN_DIR := $(abspath $(LIBRELANE_SKY130_SOC_DIR)/plugin)
SKY130_SOC_KLAYOUT_SKIP := --skip KLayout.DRC --skip Checker.KLayoutDRC
SKY130_SOC_STOCK_MAXCAP_SKIP := $(if $(filter config.json,$(SKY130_SOC_CONFIG)),--skip Checker.MaxCapViolations,)

librelane-sky130-soc-noklayout:
	@echo "=========================================="
	@echo "Sky130 SoC WITHOUT KLayout DRC (bead 00ef)"
	@echo "  Skipping: KLayout.DRC + Checker.KLayoutDRC"
	@echo "  Reason  : 8.5 GB peak OOM-killed the full run before Netgen.LVS"
	@echo "  NOTE    : KLayout DRC is DEFERRED, not waived."
	@echo "=========================================="
	@$(MAKE) librelane-sky130-soc \
		SKY130_SOC_EXTRA_SKIP="$(SKY130_SOC_KLAYOUT_SKIP)"

# Pre-adoption flow (config.json, no RC calibration, stock max-cap checker skipped) for A/B comparison.
librelane-sky130-soc-norccal:
	@$(MAKE) librelane-sky130-soc SKY130_SOC_CONFIG=config.json

librelane-sky130-soc-norccal-noklayout:
	@$(MAKE) librelane-sky130-soc-noklayout SKY130_SOC_CONFIG=config.json

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
	@# HOLD CHECKER NOW GATES (2026-07-26, bead claude_verilog_test-y7v).
	@# --skip Checker.HoldViolations was removed: RUN_2026-07-25_13-29-40
	@# reported nom_tt hold WNS -0.0923 ns (1 endpoint,
	@# apb_paddr_i[4] -> u_cpu/apb_paddr_i[4]) and the skip meant the flow
	@# signed off anyway. Hold is now a hard gate at the sign-off corner.
	@#
	@# ORDERING (measured on RUN_2026-07-26_09-36-48, not assumed): the
	@# timing checkers run at the END of the flow, not next to the STA that
	@# feeds them. Actual step order is 50-openroad-stapostpnr,
	@# 52-magic-streamout, 54-magic-drc, 55-klayout-drc,
	@# 58-magic-spiceextraction, 59-netgen-lvs, 60-checker-lvs,
	@# 61-checker-holdviolations, 62-misc-reportmanufacturability.
	@# So a residual hold violation costs only the manufacturability report --
	@# Magic/KLayout DRC and Netgen LVS have all completed by then and their
	@# results are on disk. This is UNLIKE Odb.CheckDesignAntennaProperties,
	@# which sits at step 54 mid-flow and did kill RUN_2026-07-25_09-21-05
	@# before DRC/LVS. Do not generalise from that one to the checkers.
	@#
	@# SETUP CHECKER NOW GATES TOO (2026-07-26). --skip Checker.SetupViolations
	@# was removed once RUN_2026-07-26_16-05-43 closed setup at every gated
	@# corner. Both timing checkers are now live.
	@#
	@# Why this is safe despite ss-corner setup failing by -6 to -9 ns: the
	@# checkers gate only the corners matched by TIMING_VIOLATION_CORNERS,
	@# which sky130A sets at PDK level to ['*tt*']. Verified from
	@# RUN_2026-07-26_16-05-43/resolved.json -- SETUP_VIOLATION_CORNERS and
	@# HOLD_VIOLATION_CORNERS are both null, so both fall back to that PDK
	@# value (librelane/steps/checker.py get_corner_wildcards). Margins at the
	@# three gated corners:
	@#     setup  nom_tt +1.3873 | min_tt +2.5656 | max_tt +0.3391
	@#     hold   nom_tt +0.1444 | min_tt +0.2489 | max_tt +0.0923
	@# max_tt is the tightest on both and is the one to watch. The ss corners
	@# (setup -6.30 / -7.72 / -8.94) are outside the gate BY PDK DESIGN, not
	@# by our choice, and remain untrustworthy anyway while the SRAM macro is
	@# single-corner -- GH #120 / bead claude_verilog_test-o1i.
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
		"CVT_SCAN_OPENROAD=$(ASAP7_OPENROAD_BIN) PYTHONPATH=$(LIBRELANE_DIR):$(SKY130_SOC_PLUGIN_DIR):$(SYNTH_GATE_PLUGIN_DIR) \
		 python3 -m librelane \
		 --skip Checker.LintTimingConstructs \
		 --skip Checker.LintErrors \
		 --skip Checker.YosysSynthChecks \
		 --skip Odb.ReportDisconnectedPins \
		 --skip Checker.DisconnectedPins \
		 --skip Checker.IllegalOverlap \
		 --skip Odb.CheckDesignAntennaProperties \
		 --skip Checker.MaxSlewViolations \
		 --skip Magic.WriteLEF \
		 $(SKY130_SOC_STOCK_MAXCAP_SKIP) \
		 $(SKY130_SOC_EXTRA_SKIP) \
		 $(abspath $(LIBRELANE_SKY130_SOC_DIR))/$(SKY130_SOC_CONFIG)"

# e45j: kept as an alias of the (now rccal-default) -noklayout target for existing notes and scripts.
librelane-sky130-soc-rccal-noklayout:
	@$(MAKE) librelane-sky130-soc-noklayout

# Re-run the named max-cap waiver check on a finished Sky130 SoC run (also done inside the flow by the
# CVT.MaxCapViolations step). SKY130_SOC_MAXCAP_RUN defaults to the newest run dir; exit 0 pass / 1 unwaived / 2 input error.
#   make -C pnr sky130-soc-maxcap-check [SKY130_SOC_MAXCAP_RUN=/nobackup/sky130_soc_runs/RUN_...] [STRICT_STALE=1]
SKY130_SOC_RUNS_DIR ?= /nobackup/sky130_soc_runs
SKY130_SOC_MAXCAP_RUN ?= $(shell ls -1d $(SKY130_SOC_RUNS_DIR)/RUN_2* 2>/dev/null | tail -1)
sky130-soc-maxcap-check:
	@test -d "$(SKY130_SOC_MAXCAP_RUN)" || { echo "ERROR: run dir not found: '$(SKY130_SOC_MAXCAP_RUN)' (set SKY130_SOC_MAXCAP_RUN=...)"; exit 2; }
	python3 $(LIBRELANE_SKY130_SOC_DIR)/plugin/cvt_maxcap_waiver.py "$(SKY130_SOC_MAXCAP_RUN)" \
		--waivers $(LIBRELANE_SKY130_SOC_DIR)/constraints/max_cap_waivers.json \
		$(if $(STRICT_STALE),--strict-stale,)

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
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
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

librelane-asap7 librelane-asap7-gpu librelane-asap7-soc \
librelane-asap7-soc-synth librelane-asap7-soc-synth-only \
librelane-asap7-soc-multiclock librelane-asap7-soc-multiclock-hier \
macro-views-asap7 \
librelane-asap7-coalescer-rtl librelane-asap7-coalescer-hls \
librelane-asap7-hazard-rtl librelane-asap7-hazard-hls \
librelane-asap7-valu-rtl librelane-asap7-valu-hls \
librelane-asap7-valu-hls-comb: \
	OR_PATH_PREFIX := export PATH=$(ASAP7_OR_SHIM_DIR):\$$PATH; export PYTHONPATH=\$$(python3 -c 'import click,os;print(os.path.dirname(os.path.dirname(click.__file__)))')\$${PYTHONPATH:+:\$$PYTHONPATH};

check-asap7-openroad:
	@if [ ! -x "$(ASAP7_OPENROAD_BIN)" ]; then \
	  echo "ERROR: ASAP7_OPENROAD_BIN not executable: $(ASAP7_OPENROAD_BIN)"; \
	  echo "       Re-resolve with: nix build --no-link --print-out-paths nixpkgs#openroad"; \
	  echo "       then set ASAP7_OPENROAD_BIN=<path>/bin/openroad"; \
	  exit 1; fi
	@v=$$("$(ASAP7_OPENROAD_BIN)" -version 2>&1 | head -1); \
	  case "$$v" in \
	    *edf00dff*) echo "ERROR: ASAP7_OPENROAD_BIN is the known-bad build ($$v)."; \
	                echo "       It cannot grant pin access on ASAP7 -- see bead ocm."; \
	                exit 1 ;; \
	  esac; \
	  echo "  ok: ASAP7 OpenROAD = $$v  ($(ASAP7_OPENROAD_BIN))"
	@if [ ! -x "$(ASAP7_STA_BIN)" ]; then \
	  echo "ERROR: ASAP7_STA_BIN not executable: $(ASAP7_STA_BIN)"; \
	  echo "       Re-resolve with: nix build --no-link --print-out-paths nixpkgs#opensta"; \
	  echo "       then set ASAP7_STA_BIN=<path>/bin/sta"; \
	  exit 1; fi
	@v=$$("$(ASAP7_STA_BIN)" -version 2>&1 | head -1); \
	  case "$$v" in \
	    2.7.0*) echo "ERROR: ASAP7_STA_BIN is the known-bad build ($$v)."; \
	            echo "       It corrupts report_power to inf/NaN -- see bead zwc."; \
	            exit 1 ;; \
	  esac; \
	  echo "  ok: ASAP7 sta = $$v  ($(ASAP7_STA_BIN))"
	@mkdir -p $(ASAP7_OR_SHIM_DIR)
	@ln -sf $(ASAP7_OPENROAD_BIN) $(ASAP7_OR_SHIM_DIR)/openroad
	@echo "  ok: shim $(ASAP7_OR_SHIM_DIR)/openroad -> $(ASAP7_OPENROAD_BIN)"
	@ln -sf $(ASAP7_STA_BIN) $(ASAP7_OR_SHIM_DIR)/sta
	@echo "  ok: shim $(ASAP7_OR_SHIM_DIR)/sta -> $(ASAP7_STA_BIN)"
	@# Non-vacuous: prove odbpy's third-party imports actually resolve under the
	@# chosen openroad's embedded interpreter. Without this, the flow runs all the
	@# way to Odb.SetPowerConnections before failing.
	@cd $(LIBRELANE_DIR) && nix-shell --run "export PYTHONPATH=\$$(python3 -c 'import click,os;print(os.path.dirname(os.path.dirname(click.__file__)))'):$(LIBRELANE_DIR)/librelane/scripts/odbpy; $(ASAP7_OPENROAD_BIN) -python -c 'import click, rich, yaml, ioplace_parser'" >/dev/null 2>&1 \
	  || { echo "ERROR: odbpy imports do not resolve under $(ASAP7_OPENROAD_BIN)."; \
	       echo "       Every Odb.* step would fail with ModuleNotFoundError."; exit 1; }
	@echo "  ok: odbpy imports (click, rich, yaml, ioplace_parser) resolve"
	@# Non-vacuous, bead claude_verilog_test-djm: everything above only proves
	@# ASAP7_OPENROAD_BIN itself is a valid, non-known-bad 26Q2 binary -- it does
	@# NOT prove the calling target's actual invocation ("openroad" resolved via
	@# bare PATH inside nix-shell) uses it. That requires the calling target to be
	@# in the OR_PATH_PREFIX list at pnr/Makefile:911-918; that list is manually
	@# maintained per-target, so a newly-added target that depends on this rule
	@# but forgets to join the list silently falls back to nix-shell's own
	@# bundled OpenROAD (OR_PATH_PREFIX defaults to empty at line 181) -- the
	@# exact failure this whole check exists to prevent, just one hop further.
	@# Target-specific variables propagate to prerequisites, so $(OR_PATH_PREFIX)
	@# is non-empty here whenever this runs as a prerequisite of a properly-
	@# listed target, and empty otherwise -- making this a direct test of the gap.
	@resolved=$$(cd $(LIBRELANE_DIR) && nix-shell --run "$(OR_PATH_PREFIX) command -v openroad" 2>/dev/null); \
	  case "$$resolved" in \
	    */.openroad-shim/openroad) echo "  ok: 'openroad' resolves to pinned shim ($$resolved)" ;; \
	    *) echo "ERROR: 'openroad' resolves to '$$resolved', not the pinned 26Q2 shim"; \
	       echo "       ($(ASAP7_OR_SHIM_DIR)/openroad)."; \
	       echo "       The calling target depends on check-asap7-openroad but is"; \
	       echo "       missing from the OR_PATH_PREFIX target list at"; \
	       echo "       pnr/Makefile:911-918 -- see bead claude_verilog_test-djm."; \
	       exit 1 ;; \
	  esac

install-asap7-rcx-rules:
	@python3 $(abspath ../tools/setup/install_asap7_rcx_rules.py) \
		--orfs-root $(ORFS_ROOT) --pdk-root $(MANUAL_PDK_ROOT)

# Fails loudly (non-zero) if the PDK still carries the 0-byte RCX rules stub.
# Run before any ASAP7 flow that relies on RUN_SPEF_EXTRACTION/RUN_MCSTA.
check-asap7-rcx-rules:
	@python3 $(abspath ../tools/setup/install_asap7_rcx_rules.py) \
		--pdk-root $(MANUAL_PDK_ROOT) --check-only

CPU_SV_FILES := \
	$(PROJECT_ROOT)/rtl/soc/axi_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_addr_map_pkg.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_pipeline_pkg.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_cache_pkg.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mem_collar.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_ctrl.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_clock_gate.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_alu.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_branch_comp.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_imm_gen.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_regfile.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_decode.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_forwarding_unit.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_hazard_unit.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_interrupt_ctrl.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_csr_file.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_if.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_id.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_ex.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_ex1c.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_ex1b.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_ex2.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/pipeline/rv32i_pipeline_wb.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_icache.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_dcache.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_cache_arbiter.sv \
	$(PROJECT_ROOT)/rtl/cpu/core/rv32i_core.sv \
	$(PROJECT_ROOT)/rtl/cpu/rv32i_cpu_top.sv

CPU_SV2V_DEFINES := --define=SRAM_ASAP7 --define=USE_ICG_CELL
CPU_SV2V_OUT      := $(abspath $(LIBRELANE_ASAP7_DIR)/rv32i_cpu_top_sv2v.v)

.PHONY: asap7-cpu-sv2v
asap7-cpu-sv2v:
	@echo "=========================================="
	@echo "Pre-processing: sv2v SV -> Verilog-2005 (ASAP7 CPU macro, bead ma7)"
	@echo "  Input : $(words $(CPU_SV_FILES)) SV files"
	@echo "  Output: $(CPU_SV2V_OUT)"
	@echo "=========================================="
	@if [ ! -f "$(SV2V)" ]; then \
		echo "ERROR: sv2v not found at $(SV2V)"; \
		echo "Install via: nix-build '<nixpkgs>' -A haskellPackages.sv2v --no-out-link"; \
		exit 1; fi
	$(SV2V) $(CPU_SV2V_DEFINES) $(CPU_SV_FILES) -w $(CPU_SV2V_OUT)
	@# sv2v strips inline comments, including the
	@# `/* verilator lint_off/on BLKLOOPINIT */` pair that
	@# rtl/mem/rv32i_icache.sv and rv32i_dcache.sv wrap around their
	@# reset-loop `for (j...) valid_array[j] <= ...;` pattern (a KNOWN,
	@# already-accepted-by-this-project Verilator limitation on non-blocking
	@# array-element assignment inside a for loop -- the RTL comment is proof
	@# it was already anticipated for direct SV linting). Without the pragma,
	@# LibreLane's Checker.LintErrors (Verilator, plain-Verilog-2005 mode on
	@# the flattened output) hard-fails with 3 BLKLOOPINIT errors at the two
	@# loop sites, even though the design is otherwise unchanged. A single
	@# lint_off with no matching lint_on suppresses BLKLOOPINIT for the rest
	@# of the file (documented Verilator behaviour), which is safe here since
	@# these are the only two occurrences of the pattern in this design.
	@# Verified 2026-09-19: `verilator --lint-only` on the patched output
	@# exits 0 with only benign UNUSEDSIGNAL/UNDRIVEN warnings on stub
	@# blackbox pins (same ones LibreLane's own _deps.vlt already waives).
	sed -i '1i /* verilator lint_off BLKLOOPINIT */' $(CPU_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(CPU_SV2V_OUT)) lines"

# ASAP7: uses manually structured PDK under MANUAL_PDK_ROOT
# Config directory pnr/asap7/ must exist with a valid config.json.
librelane-asap7: check-asap7-rcx-rules check-asap7-openroad asap7-cpu-sv2v
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
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
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
	@$(MAKE) check-asap7-routing
	@$(MAKE) prune-asap7-runs

# ---------------------------------------------------------------------------
# LibreLane 3.0.14 runs (config_3014.json)
LIBRELANE_3014_DIR  ?= /nobackup/librelane-3.0.14

LIBRELANE_3014_SKIPS := \
		 --skip Checker.LintTimingConstructs \
		 --skip Odb.ReportDisconnectedPins \
		 --skip Checker.DisconnectedPins \
		 --skip Magic.SpiceExtraction \
		 --skip Checker.IllegalOverlap \
		 --skip Odb.CheckDesignAntennaProperties \
		 --skip Checker.LVS \
		 --skip Magic.StreamOut \
		 --skip KLayout.StreamOut \
		 --skip Magic.WriteLEF \
		 --skip Checker.SetupViolations \
		 --skip Checker.HoldViolations \
		 --skip Checker.MaxSlewViolations \
		 --skip Checker.MaxCapViolations

define librelane_3014_run
	@echo "=========================================="
	@echo "Running LibreLane 3.0.14 flow — $(2)"
	@echo "  Config   : pnr/$(1)/config_3014.json"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Tool     : $(LIBRELANE_3014_DIR)"
	@echo "=========================================="
	@if [ ! -d "$(LIBRELANE_3014_DIR)" ]; then \
		echo "ERROR: $(LIBRELANE_3014_DIR) not found."; \
		echo "       The 3.0.14 worktree lives outside the repo; recreate it before running."; \
		exit 1; fi
	@if [ ! -f "$(1)/config_3014.json" ]; then \
		echo "ERROR: pnr/$(1)/config_3014.json not found."; exit 1; fi
	cd $(LIBRELANE_3014_DIR) && nix develop --command env PYTHONPATH=$(SYNTH_GATE_PLUGIN_DIR):$$PYTHONPATH python3 -m librelane \
		 --manual-pdk \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 $(LIBRELANE_3014_SKIPS) \
		 $(abspath $(1))/config_3014.json
endef

librelane-asap7-3014:
	$(call librelane_3014_run,$(LIBRELANE_ASAP7_DIR),ASAP7 CPU)
	@$(MAKE) check-asap7-routing

librelane-asap7-gpu-3014:
	$(call librelane_3014_run,$(LIBRELANE_ASAP7_GPU_DIR),ASAP7 GPU)
	@$(MAKE) check-asap7-gpu-routing

librelane-asap7-results:
	$(call librelane_results,$(LIBRELANE_ASAP7_DIR))

GPU_SV_FILES := \
	$(PROJECT_ROOT)/rtl/gpu/gpu_pkg.sv \
	$(PROJECT_ROOT)/rtl/gpu/vector_register_file.sv \
	$(PROJECT_ROOT)/rtl/gpu/vector_alu.sv \
	$(PROJECT_ROOT)/rtl/gpu/gpu_compute_unit.sv \
	$(PROJECT_ROOT)/rtl/gpu/warp_scheduler.sv \
	$(PROJECT_ROOT)/rtl/gpu/gpu_command_queue.sv \
	$(PROJECT_ROOT)/rtl/gpu/gpu_memory_unit.sv \
	$(PROJECT_ROOT)/rtl/gpu/memory_coalescer.sv \
	$(PROJECT_ROOT)/rtl/gpu/shared_memory.sv \
	$(PROJECT_ROOT)/rtl/gpu/gpu_top.sv

GPU_SV2V_OUT := $(abspath $(LIBRELANE_ASAP7_GPU_DIR)/gpu_top_sv2v.v)

.PHONY: asap7-gpu-sv2v
asap7-gpu-sv2v:
	@echo "=========================================="
	@echo "Pre-processing: sv2v SV -> Verilog-2005 (ASAP7 GPU macro, bead ma7 -- config switch only, re-harden deferred)"
	@echo "  Input : $(words $(GPU_SV_FILES)) SV files"
	@echo "  Output: $(GPU_SV2V_OUT)"
	@echo "=========================================="
	@if [ ! -f "$(SV2V)" ]; then \
		echo "ERROR: sv2v not found at $(SV2V)"; \
		echo "Install via: nix-build '<nixpkgs>' -A haskellPackages.sv2v --no-out-link"; \
		exit 1; fi
	$(SV2V) $(GPU_SV_FILES) -w $(GPU_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(GPU_SV2V_OUT)) lines"

# ASAP7 GPU: uses same PDK and skip-list as librelane-asap7, but targets pnr/asap7/gpu/
librelane-asap7-gpu: check-asap7-openroad asap7-gpu-sv2v
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
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
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
	@$(MAKE) check-asap7-gpu-routing
	@$(MAKE) prune-asap7-gpu-runs

librelane-asap7-gpu-results:
	$(call librelane_results,$(LIBRELANE_ASAP7_GPU_DIR))

# ASAP7 SoC (Phase 5 M11): hierarchical — CPU+GPU as hard macros, flat peripherals
# Die: 720×720 µm, clock: 1750 ps (571 MHz GPU-governed), SYNTH-ONLY for first run.
# To run synthesis only (confirm elaboration before full P&R):
#   make librelane-asap7-soc-synth
# To run the full P&R closure (expect 4–8 h):
#   make librelane-asap7-soc
librelane-asap7-soc-synth: check-asap7-openroad
	@echo "=========================================="
	@echo "Running LibreLane SYNTH-ONLY — ASAP7 SoC"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Tool     : $(LIBRELANE_DIR)"
	@echo "  Step     : Yosys.JsonHeader (synthesis + elaboration only)"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG) not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
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
		 $(abspath $(LIBRELANE_ASAP7_SOC_DIR))/$(SOC_CONFIG)"

librelane-asap7-soc-synth-only: check-asap7-openroad
	@echo "=========================================="
	@echo "Running LibreLane SYNTH-ONLY (skip JsonHeader) — ASAP7 SoC"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)"
	@echo "  Step     : Yosys.Synthesis only (bypasses Yosys.JsonHeader)"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG) not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
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
		 $(abspath $(LIBRELANE_ASAP7_SOC_DIR))/$(SOC_CONFIG)"

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
	$(PROJECT_ROOT)/rtl/soc/pll/pll_apb_regs.sv \
	$(PROJECT_ROOT)/rtl/soc/pll/pll_subsystem.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_clk_mux.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_rst_mux.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_ctrl_ports.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/jtag_tap.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_clk_switch.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/dft_ctrl.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_ctrl.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_xing.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_ctl_hold.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mbist_status_sync.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/mem_collar.sv \
	$(PROJECT_ROOT)/rtl/soc/dft/soc_mbist.sv \
	$(PROJECT_ROOT)/rtl/soc/axi4_crossbar.sv \
	$(PROJECT_ROOT)/rtl/soc/axi_lite_register_bank.sv \
	$(PROJECT_ROOT)/rtl/soc/apb4_register_bank.sv \
	$(PROJECT_ROOT)/rtl/soc/pmu.sv \
	$(PROJECT_ROOT)/rtl/soc/axi_lite_interconnect.sv \
	$(PROJECT_ROOT)/rtl/soc/axi4_to_axilite.sv \
	$(PROJECT_ROOT)/rtl/soc/axilite_to_axi4.sv \
	$(PROJECT_ROOT)/rtl/soc/axil_to_apb.sv \
	$(PROJECT_ROOT)/rtl/soc/apb_interconnect.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_bus.sv \
	$(PROJECT_ROOT)/rtl/soc/sram_controller.sv \
	$(PROJECT_ROOT)/rtl/soc/boot_rom.sv \
	$(PROJECT_ROOT)/rtl/periph/dma_engine.sv \
	$(PROJECT_ROOT)/rtl/periph/interrupt_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/timer.sv \
	$(PROJECT_ROOT)/rtl/periph/uart_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/spi_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/gpio_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/pwm_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/watchdog_timer.sv \
	$(PROJECT_ROOT)/rtl/periph/trng_lfsr_entropy.sv \
	$(PROJECT_ROOT)/rtl/periph/trng.sv \
	$(PROJECT_ROOT)/rtl/periph/i2c_bit_engine.sv \
	$(PROJECT_ROOT)/rtl/periph/i2c_controller.sv \
	$(PROJECT_ROOT)/rtl/periph/aes128_core.sv \
	$(PROJECT_ROOT)/rtl/periph/sha256_core.sv \
	$(PROJECT_ROOT)/rtl/periph/crypto_accel.sv \
	$(PROJECT_ROOT)/rtl/npu/npu_mac_array.sv \
	$(PROJECT_ROOT)/rtl/npu/npu_weight_mem.sv \
	$(PROJECT_ROOT)/rtl/npu/npu_top.sv \
	$(PROJECT_ROOT)/rtl/mem/rv32i_clock_gate.sv \
	$(PROJECT_ROOT)/rtl/soc/cdc/cdc_sync.sv \
	$(PROJECT_ROOT)/rtl/soc/cdc/cdc_reset_sync.sv \
	$(PROJECT_ROOT)/rtl/soc/cdc/cdc_gray_fifo.sv \
	$(PROJECT_ROOT)/rtl/soc/async_axi_fifo.sv \
	$(PROJECT_ROOT)/rtl/soc/apb_cdc_bridge.sv \
	$(PROJECT_ROOT)/rtl/soc/soc_top.sv

SOC_SV2V_OUT := $(abspath $(LIBRELANE_ASAP7_SOC_DIR)/soc_top_sv2v.v)

#----------------------------------------------------------------
# sv2v defines for the ASAP7 SoC.
SOC_SV2V_DEFINES := --define=USE_ICG_CELL --define=__pnr__ --define=SRAM_ASAP7

#----------------------------------------------------------------
# asap7_soc_preflight: shared launch guards for every ASAP7 SoC P&R target.
define asap7_soc_preflight
	mkdir -p /nobackup/asap7_soc_runs
	@if [ -e "$(LIBRELANE_ASAP7_SOC_DIR)/runs" ] && [ ! -L "$(LIBRELANE_ASAP7_SOC_DIR)/runs" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/runs is a REAL directory, not the /nobackup symlink."; \
		echo "  A run started before the symlink existed (or two runs raced) and LibreLane"; \
		echo "  created it on '/', which has far less headroom than a ~6 GB run needs."; \
		echo "  A plain 'ln -sfn' here would silently nest the link INSIDE that directory"; \
		echo "  (runs/asap7_soc_runs) and the run would still land on '/'. Fix by hand:"; \
		echo "    mv $(LIBRELANE_ASAP7_SOC_DIR)/runs/RUN_* /nobackup/asap7_soc_runs/"; \
		echo "    rm -rf $(LIBRELANE_ASAP7_SOC_DIR)/runs"; \
		echo "  then re-run this target."; \
		df -h / | tail -1; \
		exit 1; fi
	@[ -L $(LIBRELANE_ASAP7_SOC_DIR)/runs ] || \
		ln -sfn /nobackup/asap7_soc_runs $(LIBRELANE_ASAP7_SOC_DIR)/runs
	@if [ ! -f "$(SOC_SV2V_OUT)" ]; then \
		echo "ERROR: soc_top_sv2v.v not found — run: make asap7-soc-sv2v first"; exit 1; fi
	@for f in macro/rv32i_cpu_top.lef macro/gpu_top.lef \
	          macro/rv32i_cpu_top__nom_tt_025C_0p7V.lib macro/gpu_top__nom_tt_025C_0p7V.lib; do \
		if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/$$f" ]; then \
			echo "ERROR: macro view $$f missing under $(LIBRELANE_ASAP7_SOC_DIR)/."; \
			echo "  Stage the .lib files with:"; \
			echo "    cp pnr/asap7/cpu/macro/rv32i_cpu_top__nom_tt_025C_0p7V.lib pnr/asap7/soc/macro/"; \
			echo "    cp pnr/asap7/gpu/macro/gpu_top__nom_tt_025C_0p7V.lib       pnr/asap7/soc/macro/"; \
			echo "  Do NOT bulk-copy the block macro dirs: the SoC .lef abstracts are"; \
			echo "  NOT the same files as pnr/asap7/{cpu,gpu}/macro/*.lef, and overwriting"; \
			echo "  them changes the PDN/routing environment of the run-14 sign-off."; \
			exit 1; fi; \
	done
endef

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
	$(SV2V) $(SOC_SV2V_DEFINES) $(SOC_SV_FILES) -w $(SOC_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(SOC_SV2V_OUT)) lines, $$(grep -c 'always.*posedge\|always.*negedge' $(SOC_SV2V_OUT)) clocked always blocks"

librelane-asap7-soc: asap7-soc-sv2v check-asap7-openroad
	@echo "=========================================="
	@echo "Running LibreLane flow — ASAP7 SoC (full P&R)"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Tool     : $(LIBRELANE_DIR)"
	@echo "  Runtime  : expect 4-8 h (hierarchical, 520x520 um)"
	@echo "  Run dir  : /nobackup/asap7_soc_runs/"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG) not found."; exit 1; fi
	$(call asap7_soc_preflight)
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
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
		 $(abspath $(LIBRELANE_ASAP7_SOC_DIR))/$(SOC_CONFIG)"
	@$(MAKE) check-asap7-soc-routing
	@$(MAKE) prune-asap7-soc-runs

librelane-asap7-soc-multiclock: SOC_CONFIG = config_multiclock.json
librelane-asap7-soc-multiclock: asap7-soc-sv2v check-asap7-openroad
	@echo "=========================================="
	@echo "Running LibreLane flow — ASAP7 SoC MULTICLOCK (GH #96)"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)"
	@echo "  SDC      : constraints/phase5_soc_multiclock.sdc (sys_clk 1750 ps / cpu_clk 780 ps)"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Runtime  : expect 4-8 h full flow (~75 min to OpenROAD.STAPrePNR)"
	@echo "  Run dir  : /nobackup/asap7_soc_runs/"
	@echo "  Extra    : $(LIBRELANE_EXTRA_ARGS)"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG) not found."; exit 1; fi
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/constraints/phase5_soc_multiclock.sdc" ]; then \
		echo "ERROR: multiclock SDC missing — copy pnr/constraints/phase5_soc_multiclock.sdc"; exit 1; fi
	$(call asap7_soc_preflight)
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
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
		 $(LIBRELANE_EXTRA_ARGS) \
		 $(abspath $(LIBRELANE_ASAP7_SOC_DIR))/$(SOC_CONFIG)"
	@if [ -z "$(LIBRELANE_EXTRA_ARGS)" ]; then \
		$(MAKE) check-asap7-soc-routing; \
	else \
		echo "NOTE: LIBRELANE_EXTRA_ARGS set ($(LIBRELANE_EXTRA_ARGS)) -- this may be a"; \
		echo "      partial run (e.g. --to before DetailedRouting). Skipping the"; \
		echo "      routing gate; run 'make check-asap7-soc-routing' by hand once a"; \
		echo "      full flow (through DetailedRouting) has completed."; \
	fi

librelane-asap7-soc-multiclock-hier: SOC_CONFIG = config_multiclock_hier.json
librelane-asap7-soc-multiclock-hier: asap7-soc-sv2v check-asap7-openroad
	@echo "=========================================="
	@echo "Running LibreLane flow — ASAP7 SoC MULTICLOCK HIERARCHICAL (bead je8/2kn)"
	@echo "  Config   : pnr/$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)"
	@echo "  SDC      : constraints/phase5_soc_multiclock.sdc (sys_clk 1750 ps / cpu_clk 780 ps)"
	@echo "  PDK root : $(MANUAL_PDK_ROOT)"
	@echo "  Runtime  : expect 4-8 h full flow (~75 min to OpenROAD.STAPrePNR)"
	@echo "  Run dir  : /nobackup/asap7_soc_runs/"
	@echo "  Extra    : $(LIBRELANE_EXTRA_ARGS)"
	@echo "=========================================="
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG)" ]; then \
		echo "ERROR: $(LIBRELANE_ASAP7_SOC_DIR)/$(SOC_CONFIG) not found."; exit 1; fi
	@if [ ! -f "$(LIBRELANE_ASAP7_SOC_DIR)/constraints/phase5_soc_multiclock.sdc" ]; then \
		echo "ERROR: multiclock SDC missing — copy pnr/constraints/phase5_soc_multiclock.sdc"; exit 1; fi
	$(call asap7_soc_preflight)
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
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
		 $(LIBRELANE_EXTRA_ARGS) \
		 $(abspath $(LIBRELANE_ASAP7_SOC_DIR))/$(SOC_CONFIG)"
	@if [ -z "$(LIBRELANE_EXTRA_ARGS)" ]; then \
		$(MAKE) check-asap7-soc-routing; \
	else \
		echo "NOTE: LIBRELANE_EXTRA_ARGS set ($(LIBRELANE_EXTRA_ARGS)) -- this may be a"; \
		echo "      partial run (e.g. --to before DetailedRouting). Skipping the"; \
		echo "      routing gate; run 'make check-asap7-soc-routing' by hand once a"; \
		echo "      full flow (through DetailedRouting) has completed."; \
	fi

librelane-asap7-soc-results:
	$(call librelane_results,$(LIBRELANE_ASAP7_SOC_DIR))

#----------------------------------------------------------------
# check-cdc-timing-asap7-soc: post-route CDC budget verification.
check-cdc-timing-asap7-soc:
	@CDC_RUN_DIR="$(RUN_DIR)"; \
	if [ -z "$$CDC_RUN_DIR" ]; then \
		CDC_RUN_DIR=$$(ls -td /nobackup/asap7_soc_runs/RUN_* 2>/dev/null | head -1); fi; \
	if [ -z "$$CDC_RUN_DIR" ]; then \
		echo "No ASAP7 SoC run found under /nobackup/asap7_soc_runs/ and RUN_DIR not set."; \
		echo "Run 'make librelane-asap7-soc' first (with PNR_SDC_FILE pointed at"; \
		echo "phase5_soc_multiclock.sdc -- GH #96 scope), or pass RUN_DIR= explicitly."; \
		exit 1; fi; \
	echo "=========================================="; \
	echo "Post-route CDC budget check — ASAP7 SoC"; \
	echo "  Run dir : $$CDC_RUN_DIR"; \
	echo "  SDC     : $(abspath constraints/phase5_soc_multiclock_check.sdc)"; \
	echo "=========================================="; \
	CDC_LOG=$$(mktemp /tmp/check_cdc_timing.XXXXXX.log); \
	( cd $(LIBRELANE_ASAP7_SOC_DIR) && \
		CDC_CHECK_RUN_DIR="$$CDC_RUN_DIR" \
		CDC_CHECK_SDC="$(abspath constraints/phase5_soc_multiclock_check.sdc)" \
		sta $(abspath $(PROJECT_ROOT))/pnr/scripts/check_cdc_timing.tcl ) > "$$CDC_LOG" 2>&1; \
	STA_EXIT=$$?; \
	cat "$$CDC_LOG"; \
	if grep -qE "CDC-EXCEPTION-MISS|budget VIOLATED|CDC-CHECK-RESULT: FAIL|CDC-CHECK-SETUP-ERROR" "$$CDC_LOG"; then \
		echo "=========================================="; \
		echo "FAIL: check-cdc-timing-asap7-soc -- CDC finding marker(s) present in log (see above), regardless of sta's own exit code ($$STA_EXIT)."; \
		echo "  Log saved at: $$CDC_LOG"; \
		grep -E "CDC-EXCEPTION-MISS|budget VIOLATED|CDC-CHECK-RESULT|CDC-CHECK-SETUP-ERROR" "$$CDC_LOG" | sed 's/^/  marker: /'; \
		echo "=========================================="; \
		rm -f "$$CDC_LOG"; \
		exit 1; \
	fi; \
	if [ "$$STA_EXIT" -ne 0 ]; then \
		echo "=========================================="; \
		echo "FAIL: check-cdc-timing-asap7-soc -- sta exited $$STA_EXIT with no recognised CDC finding marker in the log; treating as a tool/setup error."; \
		echo "  Log saved at: $$CDC_LOG"; \
		echo "=========================================="; \
		rm -f "$$CDC_LOG"; \
		exit "$$STA_EXIT"; \
	fi; \
	rm -f "$$CDC_LOG"

CDC_CORNER ?=
CDC_CORNERS ?= nom_tt_025C_1v80 max_ss_100C_1v60
CDC_CORNERS_ALL := nom_tt_025C_1v80 nom_ss_100C_1v60 nom_ff_n40C_1v95 min_tt_025C_1v80 min_ss_100C_1v60 min_ff_n40C_1v95 max_tt_025C_1v80 max_ss_100C_1v60 max_ff_n40C_1v95
check-cdc-timing-sky130-soc:
	@CDC_RUN_DIR="$(RUN_DIR)"; \
	if [ -z "$$CDC_RUN_DIR" ]; then \
		CDC_RUN_DIR=$$(ls -td /nobackup/sky130_soc_runs/RUN_* 2>/dev/null | head -1); fi; \
	if [ -z "$$CDC_RUN_DIR" ]; then \
		echo "No Sky130 SoC run found under /nobackup/sky130_soc_runs/ and RUN_DIR not set."; exit 1; fi; \
	CORNERS="$(if $(strip $(CDC_CORNER)),$(CDC_CORNER),$(if $(filter all,$(CDC_CORNERS)),$(CDC_CORNERS_ALL),$(CDC_CORNERS)))"; \
	echo "=========================================="; \
	echo "Post-route CDC budget check -- Sky130 SoC"; \
	echo "  Run dir : $$CDC_RUN_DIR"; \
	echo "  Corners : $$CORNERS"; \
	echo "  SDC     : $(abspath $(LIBRELANE_SKY130_SOC_DIR)/constraints/sky130_soc_cdc_check.sdc)"; \
	echo "=========================================="; \
	mkdir -p /nobackup/sky130_soc_runs/cdc_check_reports; \
	FAILED=""; SUMMARY=""; \
	for CORNER in $$CORNERS; do \
		echo ""; echo "---- corner $$CORNER ----"; \
		CDC_LOG=$$(mktemp /tmp/check_cdc_timing_sky130.XXXXXX.log); \
		( cd $(LIBRELANE_DIR) && nix-shell --run \
			"CDC_CHECK_RUN_DIR=$$CDC_RUN_DIR CDC_CHECK_CORNER=$$CORNER \
			 CDC_CHECK_PNR_DIR=$(abspath .) \
			 CDC_CHECK_REPORTS=/nobackup/sky130_soc_runs/cdc_check_reports/$$(basename $$CDC_RUN_DIR)_$$CORNER \
			 $(if $(CDC_SKEW_FRAC),CDC_CHECK_SKEW_FRAC=$(CDC_SKEW_FRAC)) $(if $(CDC_SKEW_LIMIT),CDC_CHECK_SKEW_LIMIT=$(CDC_SKEW_LIMIT)) \
			 sta -no_init -exit $(abspath scripts/check_cdc_timing_sky130.tcl)" ) > "$$CDC_LOG" 2>&1; \
		STA_EXIT=$$?; \
		grep -v 'Creating black box' "$$CDC_LOG"; \
		if grep -qE "CDC-EXCEPTION-MISS|budget VIOLATED|bit-skew VIOLATED|CDC-CHECK-RESULT: FAIL|CDC-CHECK-SETUP-ERROR" "$$CDC_LOG"; then \
			echo "FAIL: corner $$CORNER -- CDC finding marker(s) present (sta exit $$STA_EXIT). Log: $$CDC_LOG"; \
			FAILED="$$FAILED $$CORNER"; SUMMARY="$$SUMMARY\n  $$CORNER: FAIL"; continue; fi; \
		if [ "$$STA_EXIT" -ne 0 ]; then \
			echo "FAIL: corner $$CORNER -- sta exited $$STA_EXIT with no recognised marker (tool/setup error). Log: $$CDC_LOG"; \
			FAILED="$$FAILED $$CORNER"; SUMMARY="$$SUMMARY\n  $$CORNER: FAIL (sta exit $$STA_EXIT)"; continue; fi; \
		if ! grep -q "CDC-CHECK-RESULT: PASS" "$$CDC_LOG"; then \
			echo "FAIL: corner $$CORNER -- no PASS marker in the log (a check that did not report is not a pass). Log: $$CDC_LOG"; \
			FAILED="$$FAILED $$CORNER"; SUMMARY="$$SUMMARY\n  $$CORNER: FAIL (no PASS marker)"; continue; fi; \
		SUMMARY="$$SUMMARY\n  $$CORNER: PASS"; \
		rm -f "$$CDC_LOG"; \
	done; \
	echo ""; echo "=========================================="; \
	printf "CDC check summary ($$CDC_RUN_DIR):$$SUMMARY\n"; \
	if [ -n "$$FAILED" ]; then \
		echo "FAIL: check-cdc-timing-sky130-soc -- failing corner(s):$$FAILED"; exit 1; fi; \
	echo "PASS: check-cdc-timing-sky130-soc -- all corners pass: $$CORNERS"

# flop-count: DFF breakdown from any LibreLane run's synthesis log.
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

# Deletes old run directories, keeping the newest ASAP7_MAX_RUNS.
define prune_runs
	@RUNS_DIR="$(1)/runs"; \
	if [ ! -d "$$RUNS_DIR" ]; then exit 0; fi; \
	COUNT=$$(ls -d $$RUNS_DIR/RUN_* 2>/dev/null | wc -l); \
	if [ "$$COUNT" -le "$(ASAP7_MAX_RUNS)" ]; then \
		echo "$(2): $$COUNT run(s) present (<= $(ASAP7_MAX_RUNS)), nothing to prune."; \
		exit 0; \
	fi; \
	CANDIDATES=$$(ls -dt $$RUNS_DIR/RUN_* 2>/dev/null | tail -n +$$(($(ASAP7_MAX_RUNS)+1))); \
	TO_DELETE=""; KEPT_SIGNOFF=""; \
	for d in $$CANDIDATES; do \
		if [ -e "$$d/.signoff" ]; then KEPT_SIGNOFF="$$KEPT_SIGNOFF $$d"; \
		else TO_DELETE="$$TO_DELETE $$d"; fi; \
	done; \
	if [ -n "$$KEPT_SIGNOFF" ]; then \
		echo "$(2): PROTECTED (.signoff marker), not pruned:"; \
		for d in $$KEPT_SIGNOFF; do echo "    $$d"; done; \
	fi; \
	if [ -z "$$TO_DELETE" ]; then echo "$(2): nothing eligible to prune."; exit 0; fi; \
	NDEL=$$(echo $$TO_DELETE | wc -w); \
	echo "$(2): keeping latest $(ASAP7_MAX_RUNS) of $$COUNT run(s); DELETING $$NDEL old run(s):"; \
	for d in $$TO_DELETE; do echo "    rm -rf $$d"; done; \
	rm -rf $$TO_DELETE; \
	echo "Prune complete."
endef

prune-asap7-runs:
	$(call prune_runs,$(LIBRELANE_ASAP7_DIR),ASAP7 CPU)

prune-asap7-gpu-runs:
	$(call prune_runs,$(LIBRELANE_ASAP7_GPU_DIR),ASAP7 GPU)

prune-asap7-soc-runs:
	$(call prune_runs,$(LIBRELANE_ASAP7_SOC_DIR),ASAP7 SoC)

#----------------------------------------------------------------
# Routing sign-off gate: fail loudly if detailed routing committed zero wires.
# This runs BEFORE the corresponding prune-asap7-*-runs target so a failing
define check_routing
	@LATEST=$$(ls -td $(1)/runs/RUN_* 2>/dev/null | head -1); \
	if [ -z "$$LATEST" ]; then \
		echo "ERROR: no completed LibreLane run found in pnr/$(1)/runs/ -- cannot verify routing."; \
		exit 2; \
	fi; \
	echo "=========================================="; \
	echo "$(2): verifying detailed routing actually committed wires"; \
	echo "  Run: $$LATEST"; \
	echo "=========================================="; \
	python3 $(abspath ../tools/verif/check_asap7_routing.py) "$$LATEST"
endef

check-asap7-routing:
	$(call check_routing,$(LIBRELANE_ASAP7_DIR),ASAP7 CPU)

check-asap7-gpu-routing:
	$(call check_routing,$(LIBRELANE_ASAP7_GPU_DIR),ASAP7 GPU)

check-asap7-soc-routing:
	$(call check_routing,$(LIBRELANE_ASAP7_SOC_DIR),ASAP7 SoC)


BLOCK ?= cpu

macro-views-asap7: check-asap7-openroad
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
	if [ -n "$(SKY130_SOC_RUN)" ]; then CPU_RUN="$(SKY130_SOC_RUN)"; \
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
		"$(OR_PATH_PREFIX) openroad -exit $(abspath scripts/asap7_macro_views.tcl)"); \
	cp "$$NL" "$$MACRO_DIR/$$DESIGN.nl.v"; \
	gzip -f -6 "$$MACRO_DIR/$$DESIGN.nl.v"; \
	echo ""; \
	echo "Macro views staged to $$MACRO_DIR (netlist gzipped; gunzip -k to use):"; \
	ls -lh "$$MACRO_DIR/"

#----------------------------------------------------------------
# Schematic viewer (yosys `show` -> SVG via graphviz)
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
	$(RTL_DIR)/soc/dft/mem_collar.sv \
	$(RTL_DIR)/soc/dft/mbist_ctrl.sv \
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
		$(OPENLANE1_DIR)/runs \
		$(LIBRELANE_SKY130_DIR)/runs \
		$(LIBRELANE_NANGATE45_DIR)/runs \
		$(LIBRELANE_ASAP7_DIR)/runs
	@echo "Clean complete."

#----------------------------------------------------------------
# End of Makefile
#----------------------------------------------------------------


.PHONY: librelane-asap7-coalescer-rtl
librelane-asap7-coalescer-rtl: check-asap7-openroad
	@echo "=========================================="
	@echo "ASAP7 leaf-block PPA (GH #119 r8r) -- memory_coalescer, hand-RTL arm"
	@echo "  Config   : pnr/asap7/coalescer_rtl/config.json"
	@echo "  Stopping : OpenROAD.STAPrePNR (area+timing+power; no floorplan/route)"
	@echo "=========================================="
	@if [ ! -f "asap7/coalescer_rtl/config.json" ]; then \
		echo "ERROR: asap7/coalescer_rtl/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --to OpenROAD.STAPrePNR \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath asap7/coalescer_rtl)/config.json"

.PHONY: librelane-asap7-coalescer-hls
librelane-asap7-coalescer-hls: check-asap7-openroad
	@echo "=========================================="
	@echo "ASAP7 leaf-block PPA (GH #119 r8r) -- memory_coalescer, HLS arm (generated .v + wire-only shim)"
	@echo "  Config   : pnr/asap7/coalescer_hls/config.json"
	@echo "  Stopping : OpenROAD.STAPrePNR (area+timing+power; no floorplan/route)"
	@echo "=========================================="
	@if [ ! -f "asap7/coalescer_hls/config.json" ]; then \
		echo "ERROR: asap7/coalescer_hls/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --to OpenROAD.STAPrePNR \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath asap7/coalescer_hls)/config.json"

.PHONY: librelane-asap7-hazard-rtl
librelane-asap7-hazard-rtl: check-asap7-openroad
	@echo "=========================================="
	@echo "ASAP7 leaf-block PPA (GH #119 r8r) -- rv32i_hazard_unit, hand-RTL arm (purely combinational, virtual clock)"
	@echo "  Config   : pnr/asap7/hazard_rtl/config.json"
	@echo "  Stopping : OpenROAD.STAPrePNR (area+timing+power; no floorplan/route)"
	@echo "=========================================="
	@if [ ! -f "asap7/hazard_rtl/config.json" ]; then \
		echo "ERROR: asap7/hazard_rtl/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --to OpenROAD.STAPrePNR \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath asap7/hazard_rtl)/config.json"

.PHONY: librelane-asap7-hazard-hls
librelane-asap7-hazard-hls: check-asap7-openroad
	@echo "=========================================="
	@echo "ASAP7 leaf-block PPA (GH #119 r8r) -- rv32i_hazard_unit, HLS arm (generated .v + wire-only shim)"
	@echo "  Config   : pnr/asap7/hazard_hls/config.json"
	@echo "  Stopping : OpenROAD.STAPrePNR (area+timing+power; no floorplan/route)"
	@echo "=========================================="
	@if [ ! -f "asap7/hazard_hls/config.json" ]; then \
		echo "ERROR: asap7/hazard_hls/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --to OpenROAD.STAPrePNR \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath asap7/hazard_hls)/config.json"

.PHONY: librelane-asap7-r8r-all
librelane-asap7-r8r-all: librelane-asap7-coalescer-rtl librelane-asap7-coalescer-hls librelane-asap7-hazard-rtl librelane-asap7-hazard-hls librelane-asap7-valu-rtl librelane-asap7-valu-hls
	@echo ""
	@echo "All four GH #119 Stage 2 runs complete."

.PHONY: librelane-asap7-valu-rtl
librelane-asap7-valu-rtl: check-asap7-openroad
	@echo "=========================================="
	@echo "ASAP7 leaf-block PPA (GH #119 r8r) -- vector_alu, hand-RTL arm (purely combinational, virtual clock)"
	@echo "  Config   : pnr/asap7/valu_rtl/config.json"
	@echo "  Stopping : OpenROAD.STAPrePNR (area+timing+power; no floorplan/route)"
	@echo "=========================================="
	@if [ ! -f "asap7/valu_rtl/config.json" ]; then \
		echo "ERROR: asap7/valu_rtl/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --to OpenROAD.STAPrePNR \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath asap7/valu_rtl)/config.json"

R8R_VALU_HLS_SHIM_SV := \
	$(PROJECT_ROOT)/rtl/gpu/gpu_pkg.sv \
	$(PROJECT_ROOT)/hls/gpu/vector_alu/shim/vector_alu_hls.sv
R8R_VALU_HLS_SV2V_OUT := /nobackup/hls/out/vector_alu/vector_alu_hls_sv2v.v

.PHONY: r8r-valu-hls-sv2v
r8r-valu-hls-sv2v:
	@echo "=========================================="
	@echo "Pre-processing: sv2v SV -> Verilog-2005 (GH #119 r8r baseline shim, bead b0t)"
	@echo "  Input : $(R8R_VALU_HLS_SHIM_SV)"
	@echo "  Output: $(R8R_VALU_HLS_SV2V_OUT)"
	@echo "=========================================="
	@if [ ! -f "$(SV2V)" ]; then \
		echo "ERROR: sv2v not found at $(SV2V)"; \
		echo "Install via: nix-build '<nixpkgs>' -A haskellPackages.sv2v --no-out-link"; \
		exit 1; fi
	@mkdir -p $(dir $(R8R_VALU_HLS_SV2V_OUT))
	$(SV2V) $(R8R_VALU_HLS_SHIM_SV) -w $(R8R_VALU_HLS_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(R8R_VALU_HLS_SV2V_OUT)) lines"

.PHONY: librelane-asap7-valu-hls
librelane-asap7-valu-hls: check-asap7-openroad r8r-valu-hls-sv2v
	@echo "=========================================="
	@echo "ASAP7 leaf-block PPA (GH #119 r8r) -- vector_alu, HLS arm (generated .v + wire-only shim, USE_SYNLIG:false + sv2v per bead b0t)"
	@echo "  Config   : pnr/asap7/valu_hls/config.json"
	@echo "  Stopping : OpenROAD.STAPrePNR (area+timing+power; no floorplan/route)"
	@echo "=========================================="
	@if [ ! -f "asap7/valu_hls/config.json" ]; then \
		echo "ERROR: asap7/valu_hls/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --to OpenROAD.STAPrePNR \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath asap7/valu_hls)/config.json"

EGT_VALU_HLS_COMB_SHIM_SV := \
	$(PROJECT_ROOT)/rtl/gpu/gpu_pkg.sv \
	$(PROJECT_ROOT)/hls/gpu/vector_alu/shim/vector_alu_hls.sv
EGT_VALU_HLS_COMB_SV2V_OUT := /nobackup/hls/out/egt/sdc_longclk/vector_alu_hls_sv2v.v

.PHONY: egt-valu-hls-comb-sv2v
egt-valu-hls-comb-sv2v:
	@echo "=========================================="
	@echo "Pre-processing: sv2v SV -> Verilog-2005 (GH #119 egt comb-candidate shim, bead gcd)"
	@echo "  Input : $(EGT_VALU_HLS_COMB_SHIM_SV)"
	@echo "  Output: $(EGT_VALU_HLS_COMB_SV2V_OUT)"
	@echo "=========================================="
	@if [ ! -f "$(SV2V)" ]; then \
		echo "ERROR: sv2v not found at $(SV2V)"; \
		echo "Install via: nix-build '<nixpkgs>' -A haskellPackages.sv2v --no-out-link"; \
		exit 1; fi
	@mkdir -p $(dir $(EGT_VALU_HLS_COMB_SV2V_OUT))
	$(SV2V) $(EGT_VALU_HLS_COMB_SHIM_SV) -w $(EGT_VALU_HLS_COMB_SV2V_OUT)
	@echo "sv2v complete: $$(wc -l < $(EGT_VALU_HLS_COMB_SV2V_OUT)) lines"

.PHONY: librelane-asap7-valu-hls-comb
librelane-asap7-valu-hls-comb: check-asap7-openroad egt-valu-hls-comb-sv2v
	@echo "=========================================="
	@echo "ASAP7 leaf-block PPA (GH #119 egt) -- vector_alu, HLS combinational-candidate arm"
	@echo "  (Bambu --speculative-sdc-scheduling --clock-period=100: zero-register, zero-latency)"
	@echo "  Config   : pnr/asap7/valu_hls_comb/config.json"
	@echo "  Stopping : OpenROAD.STAPrePNR (area+timing+power; no floorplan/route)"
	@echo "=========================================="
	@if [ ! -f "asap7/valu_hls_comb/config.json" ]; then \
		echo "ERROR: asap7/valu_hls_comb/config.json not found."; exit 1; fi
	cd $(LIBRELANE_DIR) && nix-shell --run \
		"$(OR_PATH_PREFIX) $(SYNTH_GATE_ENV) python3 -m librelane \
		 --pdk-root $(MANUAL_PDK_ROOT) \
		 --manual-pdk \
		 --to OpenROAD.STAPrePNR \
		 --skip Checker.YosysSynthChecks \
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
		 $(abspath asap7/valu_hls_comb)/config.json"
