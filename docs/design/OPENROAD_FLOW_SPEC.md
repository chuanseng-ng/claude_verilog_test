# OpenROAD Physical Design Flow Specification

Document status: Phase 1 integration
Target audience: Physical design engineers, verification engineers
Applies to: All phases (1-5)

## Overview

This document specifies the OpenROAD-based physical design flow for all IP blocks in the RV32I+GPU SoC project. The flow is executed incrementally for each new IP block starting from Phase 1.

### Goals

1. **Silicon readiness**: Ensure all RTL is physically implementable
2. **Early validation**: Identify timing/power/area issues early
3. **Realistic constraints**: Guide RTL design with physical feedback
4. **Tape-out quality**: Achieve DRC/LVS clean designs

### Scope

- **Phase 1**: CPU core (single-cycle RV32I)
- **Phase 2**: Pipelined CPU with interrupt controller
- **Phase 3**: I-cache + D-cache + memory controller
- **Phase 4**: GPU-lite compute unit
- **Phase 5**: Full SoC integration

## Tool Stack

### OpenROAD Tools

| Tool | Purpose | Version |
| :--: | :-----: | :-----: |
| Yosys | RTL synthesis | 0.35+ |
| OpenROAD | Place & Route | 2.0+ |
| OpenSTA | Static timing analysis | 2.5+ |
| TritonCTS | Clock tree synthesis | (integrated in OpenROAD) |
| TritonRoute | Detailed routing | (integrated in OpenROAD) |
| OpenRCX | Parasitic extraction | (integrated in OpenROAD) |
| KLayout | Physical verification (DRC/LVS) | 0.28+ |
| Magic | Physical verification (backup) | 8.3+ |

### Supporting Tools

| Tool | Purpose | Version |
| :--: | :-----: | :-----: |
| Verilator | Gate-level simulation | 5.0+ |
| Icarus Verilog | UPF-aware simulation (alternate) | 12.0+ |
| GTKWave | Waveform viewing | 3.3+ |

### Technology Libraries

| PDK | Node | Source | Status |
| :-: | :--: | :----: | :----: |
| Sky130 | 130nm | SkyWater + Google | Primary target |
| ASAP7 | 7nm (predictive) | Arizona State University | Alternate target |

## Physical Design Flow

### Stage 1: RTL to Netlist (Synthesis)

**Tool**: Yosys

**Inputs**:

- RTL files (SystemVerilog)
- Technology library (.lib)
- Synthesis constraints (SDC)

**Steps**:

1. Read RTL and technology library
2. Apply synthesis directives (flattening, optimization)
3. Technology mapping
4. Optimization (area, timing, power)
5. Generate gate-level netlist

**Outputs**:

- Gate-level netlist (.v)
- Synthesis report (area, timing, power)
- Hierarchy report

**Key Parameters**:

```tcl
# Synthesis settings
set_max_area 0           # Optimize for area
set_max_delay 10.0       # Target clock period (ns)
set_flatten false        # Preserve hierarchy
```

**Quality Metrics**:

- Zero synthesis warnings (critical)
- Area within budget (TBD per phase)
- Worst negative slack (WNS) > -0.5ns

### Stage 2: Floorplanning

**Tool**: OpenROAD

**Inputs**:

- Gate-level netlist
- Technology LEF
- Macro LEF (for SRAMs, if present)

**Steps**:

1. Initialize floorplan (aspect ratio, core area)
2. Place I/O pins
3. Place macros (SRAMs, hard IPs)
4. Create power grid (VDD/VSS stripes)
5. Tapcell and endcap insertion

**Outputs**:

- Floorplan DEF
- Power grid report

**Key Parameters**:

```tcl
# Floorplan settings
set DIE_AREA "0 0 1000 1000"    # um x um
set CORE_UTILIZATION 0.60       # 60% utilization
set ASPECT_RATIO 1.0            # Square die
```

**Quality Metrics**:

- Core utilization: 50-70%
- Aspect ratio: 0.8-1.2 (prefer square)
- Power grid IR drop < 5%

### Stage 3: Placement

**Tool**: OpenROAD (global + detailed placement)

**Inputs**:

- Floorplan DEF
- Gate-level netlist
- Timing constraints (SDC)

**Steps**:

1. Global placement (coarse cell locations)
2. Legalization (snap to grid, remove overlaps)
3. Detailed placement (optimize local wiring)
4. Placement optimization (timing-driven)

**Outputs**:

- Placed DEF
- Placement density map
- Congestion map

**Key Parameters**:

```tcl
# Placement settings
set PLACE_DENSITY 0.65          # Target density
set ENABLE_TIMING_DRIVEN true   # Timing-aware placement
```

**Quality Metrics**:

- Zero overlaps
- Uniform density (no hotspots)
- Routing congestion < 80%

### Stage 4: Clock Tree Synthesis (CTS)

**Tool**: TritonCTS (within OpenROAD)

**Inputs**:

- Placed DEF
- Clock constraints (SDC)
- CTS configuration

**Steps**:

1. Build clock tree topology
2. Insert clock buffers
3. Balance clock latency
4. Minimize clock skew

**Outputs**:

- DEF with clock tree
- Clock tree report (skew, latency, insertion delay)

**Key Parameters**:

```tcl
# CTS settings
set CTS_TARGET_SKEW 0.1         # ns
set CTS_CLUSTERING true         # Enable clustering
```

**Quality Metrics**:

- Clock skew < 100ps (target)
- Clock latency < 2ns
- Clock tree power < 20% of total

### Stage 5: Routing

**Tool**: TritonRoute (within OpenROAD)

**Inputs**:

- DEF with clock tree
- Technology LEF
- Routing rules

**Steps**:

1. Global routing (coarse wire planning)
2. Track assignment
3. Detailed routing (actual wire generation)
4. Antenna fixing
5. DRC fixing

**Outputs**:

- Routed DEF
- Routing report (DRC violations, wire lengths)

**Key Parameters**:

```tcl
# Routing settings
set ROUTING_LAYERS "met1 met2 met3 met4"
set MIN_ROUTING_LAYER met1
set MAX_ROUTING_LAYER met4
```

**Quality Metrics**:

- Zero DRC violations
- Via count minimized
- Wire length optimized

### Stage 6: Parasitic Extraction

**Tool**: OpenRCX (within OpenROAD)

**Inputs**:

- Routed DEF
- Technology LEF

**Steps**:

1. Extract wire capacitance
2. Extract wire resistance
3. Calculate coupling capacitance
4. Generate SPEF file

**Outputs**:

- SPEF (Standard Parasitic Exchange Format)
- Parasitic summary report

**Quality Metrics**:

- SPEF complete (all nets)
- Coupling cap < 30% of total cap

### Stage 7: Static Timing Analysis (STA)

**Tool**: OpenSTA

**Inputs**:

- Gate-level netlist
- SDC constraints
- SPEF parasitics
- Technology libraries (.lib, all corners)

**Steps**:

1. Read netlist and constraints
2. Read parasitic data (SPEF)
3. Propagate clock arrival times
4. Check setup timing (data before clock)
5. Check hold timing (data stable after clock)
6. Report worst paths

**Outputs**:

- Timing reports (setup, hold, clock)
- Slack summary
- Critical path report

**Key Checks**:

```tcl
# Timing checks
report_checks -path_delay min_max -format full_clock_expanded
report_tns    # Total negative slack
report_wns    # Worst negative slack
report_clock_skew
```

**Quality Metrics**:

- WNS (worst negative slack) > 0 (no violations)
- TNS (total negative slack) = 0
- Hold violations = 0

### Stage 8: Power Analysis

**Tool**: OpenROAD power estimation

**Inputs**:

- Routed DEF with SPEF
- VCD (Value Change Dump) from simulation
- Technology libraries

**Steps**:

1. Read design and activity data
2. Calculate switching power
3. Calculate leakage power
4. Calculate internal power
5. Generate power report

**Outputs**:

- Power report (total, per-module, per-net)
- Power grid analysis

**Key Metrics**:

```tcl
# Power analysis
report_power -hierarchy all
report_power_grid -vsrc Vsrc_loc.txt
```

**Quality Metrics**:

- Total power within budget (TBD per phase)
- IR drop < 5% on power grid
- Clock tree power < 20% of total

### Stage 9: Physical Verification

**Tool**: KLayout (primary), Magic (backup)

**Inputs**:

- GDS II (layout file)
- Technology DRC rules
- Technology LVS rules

**Steps**:

1. **DRC (Design Rule Check)**: Verify layout vs technology rules
   - Metal spacing, width, enclosure
   - Via rules
   - Antenna rules
2. **LVS (Layout vs Schematic)**: Verify layout matches netlist
   - Netlist extraction from layout
   - Comparison with gate-level netlist

**Outputs**:

- DRC report (violations)
- LVS report (match/mismatch)

**Quality Metrics**:

- DRC violations = 0
- LVS clean (no mismatch)

### Stage 10: Gate-Level Simulation

**Tool**: Verilator + cocotb

**Inputs**:

- Gate-level netlist (.v)
- SDF (Standard Delay Format) from STA
- Testbench (same as RTL)

**Steps**:

1. Compile gate-level netlist with SDF delays
2. Run functional tests (from Phase 0/1)
3. Compare commits with RTL reference model
4. Verify timing (setup/hold) with back-annotated delays

**Outputs**:

- Simulation log
- VCD waveform
- Commit comparison report

**Quality Metrics**:

- 100% functional match with RTL
- Zero timing violations in simulation
- Zero X (unknown) propagation

## Power-Aware Design Flow (UPF)

### UPF Specification

**Purpose**: Define power intent for multi-domain designs

**Key Concepts**:

1. **Power domains**: Regions with independent power supplies
2. **Supply networks**: VDD/VSS nets for each domain
3. **Isolation cells**: Prevent X propagation across powered-down domains
4. **Level shifters**: Handle voltage differences between domains
5. **Retention cells**: Preserve state during power-down
6. **Power state tables (PST)**: Define legal power mode combinations

### UPF Structure

```tcl
# Example UPF for CPU core (Phase 1)

# Create power domains
create_power_domain PD_TOP
create_power_domain PD_CORE -elements {i_rv32i_core}
create_power_domain PD_DEBUG -elements {i_rv32i_debug}

# Create supply nets
create_supply_net VDD_TOP -domain PD_TOP
create_supply_net VDD_CORE -domain PD_CORE
create_supply_net VDD_DEBUG -domain PD_DEBUG
create_supply_net VSS -domain PD_TOP

# Connect supplies to ports
connect_supply_net VDD_TOP -ports {VDD}
connect_supply_net VSS -ports {VSS}

# Define supply sets
create_supply_set SS_TOP -function {power VDD_TOP} -function {ground VSS}
create_supply_set SS_CORE -function {power VDD_CORE} -function {ground VSS}

# Define isolation strategies
set_isolation ISO_CORE -domain PD_CORE \
    -isolation_power_net VDD_TOP \
    -isolation_ground_net VSS \
    -clamp_value 0

# Define retention strategies
set_retention RET_CORE -domain PD_CORE \
    -retention_power_net VDD_TOP \
    -retention_ground_net VSS

# Power state table
add_power_state PD_TOP \
    -state ACTIVE {-supply_expr {power == FULL_ON}} \
    -state IDLE {-supply_expr {power == FULL_ON}} \
    -state SLEEP {-supply_expr {power == OFF}}

add_power_state PD_CORE \
    -state ACTIVE {-supply_expr {power == FULL_ON}} \
    -state GATED {-supply_expr {power == OFF}}
```

### Power-Aware Simulation

**Tool**: Verilator with UPF support (or Icarus Verilog)

**Steps**:

1. Compile netlist with UPF annotations
2. Apply power state sequences (active → idle → sleep → active)
3. Verify isolation cells block X propagation
4. Verify retention cells preserve state
5. Check power sequencing (turn-on/turn-off order)

**Checks**:

- No X propagation during power-down

- Retention registers hold values
- Isolation cells clamp to safe values
- Power domains sequence correctly

## Timing Constraints (SDC)

### SDC Structure

```tcl
# Example SDC for CPU core (Phase 1)

# Clock definitions
create_clock -name clk -period 10.0 [get_ports clk]
set_clock_uncertainty 0.5 [get_clocks clk]
set_clock_latency -source 1.0 [get_clocks clk]

# Input delays
set_input_delay -clock clk -max 2.0 [all_inputs]
set_input_delay -clock clk -min 0.5 [all_inputs]

# Output delays
set_output_delay -clock clk -max 2.0 [all_outputs]
set_output_delay -clock clk -min 0.5 [all_outputs]

# False paths (debug interface)
set_false_path -from [get_ports apb_*] -to [get_ports axi_*]

# Multi-cycle paths (if any)
# set_multicycle_path 2 -from [get_pins state_reg*] -to [get_pins next_state*]

# Load constraints
set_load 0.05 [all_outputs]

# Driving cell
set_driving_cell -lib_cell BUF_X1 [all_inputs]
```

### SDC Best Practices

1. **Clock period**: Based on target frequency (e.g., 100 MHz = 10ns)
2. **Clock uncertainty**: Account for jitter (5-10% of period)
3. **Input/output delays**: Based on interface timing specs (e.g., AXI4-Lite tSU/tH)
4. **False paths**: Debug paths, asynchronous resets
5. **Multi-cycle paths**: Slow control paths that can take >1 cycle

## Directory Structure

```text
pnr/                            # Place & Route artifacts
├── Makefile                    # Top-level flow automation
├── config/                     # Configuration files
│   ├── sky130_config.tcl       # Sky130 PDK config
│   └── asap7_config.tcl        # ASAP7 PDK config
├── constraints/                # Timing and power constraints
│   ├── phase1_cpu.sdc          # Timing constraints
│   ├── phase1_cpu.upf          # Power intent
│   └── phase1_cpu_loads.tcl    # Load models
├── scripts/                    # Flow scripts
│   ├── 01_synth.tcl            # Synthesis
│   ├── 02_floorplan.tcl        # Floorplanning
│   ├── 03_place.tcl            # Placement
│   ├── 04_cts.tcl              # Clock tree synthesis
│   ├── 05_route.tcl            # Routing
│   ├── 06_sta.tcl              # Static timing analysis
│   ├── 07_power.tcl            # Power analysis
│   └── 08_verify.tcl           # Physical verification
├── logs/                       # Log files (per run)
│   ├── synth.log
│   ├── place.log
│   └── ...
├── reports/                    # Reports (per run)
│   ├── synth_area.rpt
│   ├── timing_setup.rpt
│   ├── power.rpt
│   └── ...
├── results/                    # Final outputs
│   ├── phase1_cpu.v            # Gate-level netlist
│   ├── phase1_cpu.def          # Final DEF
│   ├── phase1_cpu.spef         # Parasitics
│   ├── phase1_cpu.sdf          # Delays
│   └── phase1_cpu.gds          # Layout (GDS II)
└── work/                       # Intermediate files (gitignored)
    └── ...
```

## Flow Automation (Makefile)

```makefile
# Top-level Makefile for OpenROAD flow

# Configuration
PDK ?= sky130
TOP_MODULE ?= rv32i_cpu_top
CLOCK_PERIOD ?= 10.0

# Directories
CONFIG_DIR := config
SCRIPTS_DIR := scripts
LOGS_DIR := logs
REPORTS_DIR := reports
RESULTS_DIR := results
WORK_DIR := work

# Flow targets
.PHONY: all clean synth floorplan place cts route sta power verify gls

all: synth floorplan place cts route sta power verify gls

synth:
	@echo "Running synthesis..."
	yosys -c $(SCRIPTS_DIR)/01_synth.tcl | tee $(LOGS_DIR)/synth.log

floorplan:
	@echo "Running floorplan..."
	openroad -no_init -exit $(SCRIPTS_DIR)/02_floorplan.tcl | tee $(LOGS_DIR)/floorplan.log

place:
	@echo "Running placement..."
	openroad -no_init -exit $(SCRIPTS_DIR)/03_place.tcl | tee $(LOGS_DIR)/place.log

cts:
	@echo "Running CTS..."
	openroad -no_init -exit $(SCRIPTS_DIR)/04_cts.tcl | tee $(LOGS_DIR)/cts.log

route:
	@echo "Running routing..."
	openroad -no_init -exit $(SCRIPTS_DIR)/05_route.tcl | tee $(LOGS_DIR)/route.log

sta:
	@echo "Running STA..."
	sta $(SCRIPTS_DIR)/06_sta.tcl | tee $(LOGS_DIR)/sta.log

power:
	@echo "Running power analysis..."
	openroad -no_init -exit $(SCRIPTS_DIR)/07_power.tcl | tee $(LOGS_DIR)/power.log

verify:
	@echo "Running physical verification..."
	klayout -b -r $(SCRIPTS_DIR)/08_verify.tcl | tee $(LOGS_DIR)/verify.log

gls:
	@echo "Running gate-level simulation..."
	cd ../sim && make gls

clean:
	rm -rf $(WORK_DIR) $(LOGS_DIR) $(REPORTS_DIR) $(RESULTS_DIR)

# Helper targets
report_timing:
	@grep "slack" $(REPORTS_DIR)/timing_setup.rpt

report_power:
	@grep "Total Power" $(REPORTS_DIR)/power.rpt

report_area:
	@grep "Chip area" $(REPORTS_DIR)/synth_area.rpt
```

## Quality Gates

Each phase must pass these quality gates before moving to the next phase:

### Gate 1: Synthesis

- [x] Zero synthesis errors
- [x] Zero critical warnings
- [x] Area within budget (TBD per phase)
- [x] WNS > -0.5ns (post-synthesis)

### Gate 2: Place & Route

- [x] Floorplan converges (no overlap, <70% utilization)
- [x] Placement converges (zero overlaps)
- [x] Routing converges (zero DRC violations)
- [x] Clock tree skew < 100ps

### Gate 3: Timing Closure

- [x] WNS = 0 (no setup violations)
- [x] TNS = 0 (no hold violations)
- [x] All corners passing (fast/slow/typical)

### Gate 4: Power Closure

- [x] Total power within budget
- [x] IR drop < 5%
- [x] Electromigration (EM) violations = 0

### Gate 5: Physical Verification

- [x] DRC violations = 0
- [x] LVS clean (no mismatch)
- [x] Antenna violations = 0

### Gate 6: Gate-Level Simulation

- [x] 100% functional match with RTL
- [x] Zero timing violations (with SDF)
- [x] UPF power modes functional

## AI/Human Responsibilities

### AI MAY assist with

- Initial UPF template generation
- Basic SDC constraint files
- Flow script boilerplate
- Power domain declarations
- Report parsing and summarization

### AI MUST NOT decide

- Power architecture (number of domains, isolation strategy)
- Clock constraints (period, uncertainty, latency)
- Critical timing paths
- Power state tables
- Floorplan strategy

### Human MUST review

- All UPF power intent
- All SDC timing constraints
- Synthesis QoR (area, timing, power)
- Place & Route convergence
- Timing closure strategy
- Power analysis results
- Physical verification results

## Phase-Specific Considerations

### Phase 1: Single-Cycle CPU

- **Target frequency**: 100 MHz (10ns period)
- **Power domains**: Single domain (no UPF yet, but prepare infrastructure)
- **Focus**: Timing closure, area optimization

### Phase 2: Pipelined CPU

- **Target frequency**: 200-500 MHz (5-2ns period)
- **Power domains**: Core + debug (2 domains)
- **Focus**: Clock tree quality, pipeline timing

### Phase 3: Cache System

- **Target frequency**: Match CPU frequency
- **Power domains**: Core + I-cache + D-cache (3 domains)
- **Focus**: SRAM macro integration, power gating

### Phase 4: GPU Compute Unit

- **Target frequency**: 100-200 MHz (parallel throughput more important)
- **Power domains**: GPU as separate domain with DVFS
- **Focus**: Datapath optimization, power efficiency

### Phase 5: Full SoC

- **Target frequency**: Multiple clock domains
- **Power domains**: 5+ domains (CPU, GPU, periph, always-on, etc.)
- **Focus**: Hierarchical P&R, system-level timing closure

## References

- OpenROAD Documentation: https://openroad.readthedocs.io/
- Sky130 PDK: https://skywater-pdk.readthedocs.io/
- ASAP7 PDK: http://asap.asu.edu/asap/
- UPF 3.0 Specification: IEEE 1801-2015
- SDC 2.1 Specification: Synopsys Design Constraints
- Verilator Manual: https://verilator.org/guide/latest/
