# SDC Timing Constraints Specification

Document status: Phase 1 integration
Target audience: Physical design engineers, timing engineers, STA analysts
Standard: Synopsys Design Constraints (SDC) 2.1

## Overview

This document specifies timing constraints for the RV32I+GPU SoC using Synopsys Design Constraints (SDC) format. Timing constraints are essential for static timing analysis (STA) and guide synthesis and place & route tools.

### Timing Verification Goals

1. **Setup timing**: Ensure data arrives before clock edge (with margin)
2. **Hold timing**: Ensure data remains stable after clock edge
3. **Clock quality**: Minimize skew and jitter
4. **Interface timing**: Meet AXI, APB protocol requirements

### Timing Closure Strategy

- **Phase 1**: 100 MHz (10ns period), single clock, simple constraints
- **Phase 2**: 200-500 MHz (5-2ns period), pipeline timing critical
- **Phase 3**: Cache access timing, SRAM models
- **Phase 4**: Multi-clock domains (CPU clock + GPU clock)
- **Phase 5**: Full SoC with multiple asynchronous clocks

## SDC Concepts

### Clock Definition

A **clock** defines the periodic signal that synchronizes the design.

```tcl
create_clock -name clk -period 10.0 [get_ports clk]
```

**Parameters**:

- `-name`: Clock name (for reference)
- `-period`: Clock period in ns
- `[get_ports clk]`: Clock source (port or pin)

### Clock Uncertainty

**Clock uncertainty** accounts for jitter and skew in the clock network.

```tcl
set_clock_uncertainty 0.5 [get_clocks clk]
```

**Typical values**:

- **Pre-CTS**: 5-10% of period (conservative estimate)
- **Post-CTS**: 1-3% of period (after clock tree is built)

### Clock Latency

**Clock latency** is the delay from clock source to register clock pins.

```tcl
# Source latency (external delay before chip)
set_clock_latency -source 1.0 [get_clocks clk]

# Network latency (internal clock tree delay)
set_clock_latency 0.5 [get_clocks clk]
```

### Input/Output Delays

**Input delay**: Time from external clock edge to data arrival at input port
**Output delay**: Time from output port to external register clock pin

```tcl
# Input delay (external device has tSU = 2ns)
set_input_delay -clock clk -max 2.0 [get_ports data_in]
set_input_delay -clock clk -min 0.5 [get_ports data_in]

# Output delay (external device has tH = 1ns)
set_output_delay -clock clk -max 2.0 [get_ports data_out]
set_output_delay -clock clk -min 0.5 [get_ports data_out]
```

### False Paths

**False paths** are signal paths that do not require timing analysis.

**Examples**:

- Asynchronous reset paths
- Paths between unrelated clock domains
- Test/debug paths

```tcl
# Async reset is a false path
set_false_path -from [get_ports rst_n]

# Debug interface doesn't need to meet AXI timing
set_false_path -from [get_ports apb_*] -to [get_ports axi_*]
```

### Multi-Cycle Paths

**Multi-cycle paths** are paths that have more than one clock cycle to propagate.

**Example**: A slow control path that takes 2 cycles

```tcl
# This path has 2 cycles instead of 1
set_multicycle_path 2 -from [get_pins ctrl_reg*] -to [get_pins next_state*]
set_multicycle_path 1 -hold -from [get_pins ctrl_reg*] -to [get_pins next_state*]
```

**Note**: Always specify both setup (default) and hold multicycle paths.

### Clock Groups

**Clock groups** define relationships between clocks (synchronous, asynchronous, exclusive).

```tcl
# Define asynchronous clock groups (no timing checks between them)
set_clock_groups -asynchronous \
    -group [get_clocks clk_cpu] \
    -group [get_clocks clk_gpu]
```

## Phase 1: Single-Cycle CPU

### Timing Requirements

| Parameter | Value | Notes |
| :-------: | :---: | :---: |
| Target frequency | 100 MHz | 10ns period |
| Clock uncertainty | 0.5ns (5%) | Pre-CTS estimate |
| Setup margin | 10% | 1ns margin |
| Hold margin | 0.1ns | Minimal |

### SDC File: phase1_cpu.sdc

```tcl
#=============================================
# Phase 1: Single-cycle RV32I CPU
# Target: 100 MHz (10ns period)
#=============================================

#---------------------------------------------
# Clock Definition
#---------------------------------------------

# Create primary clock
create_clock -name clk -period 10.0 [get_ports clk]

# Clock uncertainty (pre-CTS)
set_clock_uncertainty 0.5 [get_clocks clk]

# Clock latency (source: external PLL)
set_clock_latency -source 1.0 [get_clocks clk]

# Clock transition time (slew)
set_clock_transition 0.1 [get_clocks clk]

#---------------------------------------------
# Input Constraints
#---------------------------------------------

# AXI4-Lite input delays (based on protocol timing)
# Assume external memory controller with 2ns setup, 0.5ns hold
set_input_delay -clock clk -max 2.0 [get_ports axi_*ready]
set_input_delay -clock clk -max 2.0 [get_ports axi_rdata]
set_input_delay -clock clk -max 2.0 [get_ports axi_rresp]
set_input_delay -clock clk -max 2.0 [get_ports axi_rvalid]
set_input_delay -clock clk -max 2.0 [get_ports axi_bvalid]
set_input_delay -clock clk -max 2.0 [get_ports axi_bresp]

set_input_delay -clock clk -min 0.5 [get_ports axi_*ready]
set_input_delay -clock clk -min 0.5 [get_ports axi_rdata]
set_input_delay -clock clk -min 0.5 [get_ports axi_rresp]
set_input_delay -clock clk -min 0.5 [get_ports axi_rvalid]
set_input_delay -clock clk -min 0.5 [get_ports axi_bvalid]
set_input_delay -clock clk -min 0.5 [get_ports axi_bresp]

# APB3 input delays (debug interface, less critical)
set_input_delay -clock clk -max 3.0 [get_ports apb_paddr]
set_input_delay -clock clk -max 3.0 [get_ports apb_psel]
set_input_delay -clock clk -max 3.0 [get_ports apb_penable]
set_input_delay -clock clk -max 3.0 [get_ports apb_pwrite]
set_input_delay -clock clk -max 3.0 [get_ports apb_pwdata]

set_input_delay -clock clk -min 1.0 [get_ports apb_*]

#---------------------------------------------
# Output Constraints
#---------------------------------------------

# AXI4-Lite output delays
set_output_delay -clock clk -max 2.0 [get_ports axi_awaddr]
set_output_delay -clock clk -max 2.0 [get_ports axi_awvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_wdata]
set_output_delay -clock clk -max 2.0 [get_ports axi_wstrb]
set_output_delay -clock clk -max 2.0 [get_ports axi_wvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_araddr]
set_output_delay -clock clk -max 2.0 [get_ports axi_arvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_rready]
set_output_delay -clock clk -max 2.0 [get_ports axi_bready]

set_output_delay -clock clk -min 0.5 [all_outputs]

# APB3 output delays
set_output_delay -clock clk -max 3.0 [get_ports apb_prdata]
set_output_delay -clock clk -max 3.0 [get_ports apb_pready]
set_output_delay -clock clk -max 3.0 [get_ports apb_pslverr]

# Commit interface (verification only, relaxed)
set_output_delay -clock clk -max 5.0 [get_ports commit_*]
set_output_delay -clock clk -max 5.0 [get_ports trap_*]

#---------------------------------------------
# False Paths
#---------------------------------------------

# Asynchronous reset
set_false_path -from [get_ports rst_n]

# Debug paths don't affect AXI timing
set_false_path -from [get_ports apb_*] -to [get_ports axi_*]
set_false_path -from [get_ports axi_*] -to [get_ports apb_*]

# Commit interface is for verification only
set_false_path -to [get_ports commit_*]
set_false_path -to [get_ports trap_*]

#---------------------------------------------
# Load and Drive Constraints
#---------------------------------------------

# Output load (assume 50fF capacitance)
set_load 0.05 [all_outputs]

# Input drive (assume BUF_X1 driving inputs)
set_driving_cell -lib_cell BUF_X1 -library sky130_fd_sc_hd [all_inputs]

#---------------------------------------------
# Area Constraint (for synthesis)
#---------------------------------------------

# No specific area constraint (optimize for timing)
set_max_area 0

#---------------------------------------------
# Environment
#---------------------------------------------

# Operating conditions
set_operating_conditions -max typical -min typical

# Wire load model (for pre-layout synthesis)
# set_wire_load_model -name "conservative" -library sky130_fd_sc_hd

#---------------------------------------------
# Design Rule Constraints
#---------------------------------------------

# Max transition time (slew rate)
set_max_transition 0.5 [current_design]

# Max capacitance
set_max_capacitance 0.1 [all_outputs]

# Max fanout
set_max_fanout 16 [current_design]
```

### Post-CTS SDC Updates (Phase 1)

After clock tree synthesis, update uncertainty:

```tcl
# Remove pre-CTS uncertainty
remove_clock_uncertainty [get_clocks clk]

# Add post-CTS uncertainty (tighter)
set_clock_uncertainty -setup 0.1 [get_clocks clk]
set_clock_uncertainty -hold 0.05 [get_clocks clk]
```

## Phase 2: Pipelined CPU

### Timing Requirements

| Parameter | Value | Notes |
| :-------: | :---: | :---: |
| Target frequency | 200-500 MHz | 5-2ns period |
| Clock uncertainty | 2-5% | More aggressive |
| Pipeline stages | 5 | Fetch, Decode, Exec, Mem, WB |
| Critical path | ALU → register file | ~1-2ns |

### SDC Additions (Phase 2)

```tcl
#=============================================
# Phase 2: Pipelined CPU
# Target: 200 MHz (5ns period)
#=============================================

# Higher frequency clock
create_clock -name clk -period 5.0 [get_ports clk]

# Tighter uncertainty
set_clock_uncertainty 0.25 [get_clocks clk]

# Multi-cycle path for slow control paths
# Control FSM may take 2 cycles to update
set_multicycle_path 2 -setup -from [get_pins i_rv32i_control/state_reg*] \
                              -to [get_pins i_rv32i_control/next_state*]
set_multicycle_path 1 -hold  -from [get_pins i_rv32i_control/state_reg*] \
                              -to [get_pins i_rv32i_control/next_state*]

# Pipeline stage boundaries (critical paths)
# These should meet single-cycle timing
set_max_delay 5.0 -from [get_pins */fetch_stage/*] -to [get_pins */decode_stage/*]
set_max_delay 5.0 -from [get_pins */decode_stage/*] -to [get_pins */execute_stage/*]
set_max_delay 5.0 -from [get_pins */execute_stage/*] -to [get_pins */memory_stage/*]
set_max_delay 5.0 -from [get_pins */memory_stage/*] -to [get_pins */writeback_stage/*]

# Forwarding paths (critical for hazard handling)
set_max_delay 4.0 -from [get_pins */execute_stage/alu_result*] \
                   -to [get_pins */execute_stage/forward_mux*]
```

## Phase 3: Cache System

### Timing Requirements

| Parameter | Value | Notes |
| :-------: | :---: | :---: |
| Target frequency | Match CPU | 200-500 MHz |
| Cache access | 1-2 cycles | Tag + data lookup |
| SRAM access | 0.5-1ns | Technology dependent |

### SDC Additions (Phase 3)

```tcl
#=============================================
# Phase 3: Cache System
#=============================================

# SRAM timing models (from memory compiler)
# These are vendor-specific timing files
read_liberty -lib_name icache_sram_lib icache_sram_tt_1p0v_25c.lib
read_liberty -lib_name dcache_sram_lib dcache_sram_tt_1p0v_25c.lib

# Cache access timing (2-cycle for tag + data)
set_multicycle_path 2 -setup -from [get_pins i_icache/tag_array/*] \
                              -to [get_pins i_icache/data_array/*]
set_multicycle_path 1 -hold  -from [get_pins i_icache/tag_array/*] \
                              -to [get_pins i_icache/data_array/*]

# Write-back buffer timing (D-cache)
set_max_delay 5.0 -from [get_pins i_dcache/wb_buffer/*] \
                   -to [get_ports axi_wdata]

# Cache-CPU interface timing
set_max_delay 3.0 -from [get_pins i_cpu_core/*] -to [get_pins i_icache/*]
set_max_delay 3.0 -from [get_pins i_dcache/*] -to [get_pins i_cpu_core/*]
```

## Phase 4: GPU with Multiple Clocks

### Timing Requirements

| Parameter | Value | Notes |
| :-------: | :---: | :---: |
| CPU clock | 200-500 MHz | 5-2ns period |
| GPU clock | 100-200 MHz | 10-5ns period (lower for power) |
| Clock domain crossing | Async FIFO | 2-3 cycle latency |

### SDC Additions (Phase 4)

```tcl
#=============================================
# Phase 4: GPU-Lite Compute Engine
#=============================================

# GPU clock (independent from CPU)
create_clock -name clk_gpu -period 10.0 [get_ports clk_gpu]
set_clock_uncertainty 0.5 [get_clocks clk_gpu]

# Define clock groups (CPU and GPU are asynchronous)
set_clock_groups -asynchronous \
    -group [get_clocks clk] \
    -group [get_clocks clk_gpu]

# False paths between clock domains (handled by async FIFO)
set_false_path -from [get_clocks clk] -to [get_clocks clk_gpu]
set_false_path -from [get_clocks clk_gpu] -to [get_clocks clk]

# GPU internal timing
# Warp scheduler to SIMT lanes
set_max_delay 10.0 -from [get_pins i_gpu/warp_scheduler/*] \
                    -to [get_pins i_gpu/simt_lanes/*]

# Vector ALU timing (8 lanes in parallel)
set_max_delay 8.0 -from [get_pins i_gpu/simt_lanes/lane_*/alu_in*] \
                   -to [get_pins i_gpu/simt_lanes/lane_*/alu_out*]

# GPU register file access (multi-cycle due to size)
set_multicycle_path 2 -setup -from [get_pins i_gpu/regfile/*] \
                              -to [get_pins i_gpu/simt_lanes/*]
set_multicycle_path 1 -hold  -from [get_pins i_gpu/regfile/*] \
                              -to [get_pins i_gpu/simt_lanes/*]
```

## Phase 5: Full SoC with Multiple Clocks

### Timing Requirements

| Parameter | Value | Notes |
| :-------: | :---: | :---: |
| CPU clock | 200-500 MHz | Main system clock |
| GPU clock | 100-200 MHz | Compute clock |
| Peripheral clock | 50-100 MHz | UART, SPI, Timer |
| Always-on clock | 32 kHz | RTC, wake-up logic |

### SDC File: phase5_soc.sdc

```tcl
#=============================================
# Phase 5: Full SoC Integration
#=============================================

#---------------------------------------------
# Clock Definitions
#---------------------------------------------

# Main system clock (CPU)
create_clock -name clk_sys -period 5.0 [get_ports clk_sys]
set_clock_uncertainty 0.25 [get_clocks clk_sys]

# GPU compute clock
create_clock -name clk_gpu -period 10.0 [get_ports clk_gpu]
set_clock_uncertainty 0.5 [get_clocks clk_gpu]

# Peripheral clock (divided from sys clock)
create_generated_clock -name clk_periph \
    -source [get_ports clk_sys] \
    -divide_by 4 \
    [get_pins i_clk_div/clk_out]
set_clock_uncertainty 0.5 [get_clocks clk_periph]

# Always-on clock (RTC)
create_clock -name clk_aon -period 30517.6 [get_ports clk_aon]
set_clock_uncertainty 100.0 [get_clocks clk_aon]

#---------------------------------------------
# Clock Groups
#---------------------------------------------

# Asynchronous clock groups
set_clock_groups -asynchronous \
    -group [get_clocks clk_sys] \
    -group [get_clocks clk_gpu] \
    -group [get_clocks clk_periph] \
    -group [get_clocks clk_aon]

#---------------------------------------------
# Inter-Domain Timing
#---------------------------------------------

# CPU <-> GPU interface (async FIFO)
set_false_path -from [get_clocks clk_sys] -to [get_clocks clk_gpu]
set_false_path -from [get_clocks clk_gpu] -to [get_clocks clk_sys]

# CPU <-> Peripherals (async FIFO or synchronizer)
set_max_delay 20.0 -from [get_clocks clk_sys] -to [get_clocks clk_periph]
set_max_delay 10.0 -from [get_clocks clk_periph] -to [get_clocks clk_sys]

# Always-on <-> System (wake-up path)
set_max_delay 1000.0 -from [get_clocks clk_aon] -to [get_clocks clk_sys]

#---------------------------------------------
# False Paths
#---------------------------------------------

# Test/scan paths
set_false_path -from [get_ports test_mode]
set_false_path -from [get_ports scan_enable]

# Power control signals (quasi-static)
set_false_path -from [get_ports pwr_*]

#---------------------------------------------
# I/O Timing
#---------------------------------------------

# External memory interface (DDR-like timing)
create_clock -name clk_mem -period 2.5 [get_ports mem_clk]
set_input_delay -clock clk_mem -max 0.5 [get_ports mem_dq*]
set_input_delay -clock clk_mem -min -0.3 [get_ports mem_dq*]
set_output_delay -clock clk_mem -max 0.5 [get_ports mem_dq*]
set_output_delay -clock clk_mem -min -0.3 [get_ports mem_dq*]

# UART (slow, relaxed timing)
set_input_delay -clock clk_periph -max 10.0 [get_ports uart_rx]
set_output_delay -clock clk_periph -max 10.0 [get_ports uart_tx]

# SPI (medium speed)
set_input_delay -clock clk_periph -max 5.0 [get_ports spi_miso]
set_output_delay -clock clk_periph -max 5.0 [get_ports spi_mosi]
set_output_delay -clock clk_periph -max 5.0 [get_ports spi_sclk]
```

## Multi-Corner Analysis

For sign-off, analyze timing across process, voltage, temperature (PVT) corners:

### Corner Definitions

| Corner | Process | Voltage | Temp | Purpose |
| :----: | :-----: | :-----: | :--: | :-----: |
| **SS** | Slow | 0.9V (min) | 125°C (max) | Worst setup (slowest) |
| **FF** | Fast | 1.1V (max) | -40°C (min) | Worst hold (fastest) |
| **TT** | Typical | 1.0V (nom) | 25°C (nom) | Typical case |
| **SF** | Slow NMOS, Fast PMOS | 0.95V | 85°C | Skew analysis |
| **FS** | Fast NMOS, Slow PMOS | 1.05V | 0°C | Skew analysis |

### Multi-Corner SDC

```tcl
# Worst setup corner (SS)
set_operating_conditions -max ss_1p0v_125c -library sky130_fd_sc_hd__ss_1p0v_125c
set_timing_derate -early 0.97
set_timing_derate -late 1.03

# Worst hold corner (FF)
set_operating_conditions -min ff_1p1v_n40c -library sky130_fd_sc_hd__ff_1p1v_n40c
set_timing_derate -early 1.03
set_timing_derate -late 0.97

# Check setup at SS corner
report_checks -path_delay max -corner SS

# Check hold at FF corner
report_checks -path_delay min -corner FF
```

## STA Checks and Reports

### Key Reports

```tcl
# Setup timing (WNS = Worst Negative Slack)
report_checks -path_delay max -format full_clock_expanded -nworst 10

# Hold timing
report_checks -path_delay min -format full_clock_expanded -nworst 10

# Clock skew
report_clock_skew -hold -setup [get_clocks clk]

# Clock tree summary
report_clock_properties [all_clocks]

# Unconstrained paths
report_checks -unconstrained

# Slack summary
report_tns  # Total negative slack
report_wns  # Worst negative slack

# Timing by group
report_timing -group [get_clocks clk] -sort_by slack
```

### Timing Closure Checklist

- [ ] WNS (worst negative slack) > 0 (no violations)
- [ ] TNS (total negative slack) = 0
- [ ] Hold violations = 0
- [ ] Clock skew < 100ps (post-CTS)
- [ ] All I/O paths constrained
- [ ] False paths identified
- [ ] Multi-cycle paths reviewed
- [ ] All corners passing (SS, FF, TT, SF, FS)

## SDC Best Practices

1. **Constrain all clocks**: Every clock must have `create_clock`
2. **Constrain all I/Os**: All inputs/outputs need delays
3. **Use realistic values**: Based on interface specs (AXI, APB)
4. **Identify false paths**: Async resets, debug paths
5. **Multi-cycle paths**: Document assumptions clearly
6. **Check unconstrained paths**: Run `report_checks -unconstrained`
7. **Multi-corner analysis**: Always check SS (setup) and FF (hold)
8. **Incremental refinement**: Start conservative, tighten based on results

## AI/Human Responsibilities

### AI MAY assist with

- SDC template generation (clock definitions, I/O delays)
- Basic constraint boilerplate
- Report parsing and slack summarization
- Multi-corner script generation

### AI MUST NOT decide

- Clock period (target frequency)
- Input/output delay values
- False path identification
- Multi-cycle path strategy
- Clock group relationships

### Human MUST review

- All SDC constraint files
- Timing reports (setup, hold, clock)
- Critical path analysis
- Timing closure strategy
- Multi-corner results

## References

- Synopsys Design Constraints (SDC) User Guide
- OpenSTA Manual: https://github.com/The-OpenROAD-Project/OpenSTA
- IEEE 1364-2005: Verilog Timing Checks
- "Static Timing Analysis for Nanometer Designs" by Bhasker & Chadha
