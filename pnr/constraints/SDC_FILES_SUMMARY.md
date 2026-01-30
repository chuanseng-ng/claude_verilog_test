# SDC Files Summary - Phase 1 RV32I CPU

## Overview

This directory contains comprehensive Synopsys Design Constraint (SDC) files for the Phase 1 RV32I CPU design. These files ensure proper timing constraints are met during synthesis, place-and-route, and static timing analysis (STA).

## Created Files

### 1. SDC Constraint Files

#### `phase1_cpu.sdc` (Baseline)
- **Status**: Original baseline constraints from specification
- **Purpose**: Initial synthesis and timing analysis
- **Features**:
  - Basic clock definition (100 MHz)
  - Input/output delays for AXI4-Lite and APB3
  - False path definitions
  - Design rule constraints

#### `phase1_cpu_enhanced.sdc` (✅ Recommended)
- **Status**: Enhanced version with comprehensive coverage
- **Purpose**: Production use for all synthesis/PnR stages
- **Features**:
  - Detailed comments explaining each constraint
  - Explicit port constraints (no wildcards for critical signals)
  - Individual bit-level constraints for multi-bit buses
  - Enhanced documentation and rationale
  - Critical path placeholders (commented out, ready to enable)

**Use this file for**: Synthesis, floorplanning, placement, routing (pre-CTS)

#### `phase1_cpu_post_cts.sdc` (Post-CTS)
- **Status**: Optimized for post-clock-tree synthesis
- **Purpose**: STA after clock tree is synthesized
- **Features**:
  - Tighter clock uncertainty (0.1ns setup, 0.05ns hold vs 0.5ns pre-CTS)
  - Separate setup/hold uncertainty values
  - Tighter max_transition (0.4ns vs 0.5ns)
  - Comments about clock network latency modeling

**Use this file for**: Post-CTS STA, routing, final timing analysis

### 2. Verification and Documentation

#### `check_constraints.tcl` (Verification Script)
- **Purpose**: Automated verification that all ports are constrained
- **Features**:
  - Checks clock definitions
  - Verifies input delay coverage
  - Verifies output delay coverage
  - Reports unconstrained paths
  - Checks design rule constraints
  - Generates summary report with warnings/errors

**Usage**:
```tcl
source pnr/constraints/check_constraints.tcl
```

#### `README_SDC.md` (Complete Documentation)
- **Purpose**: Full documentation of SDC files and usage
- **Contents**:
  - File overview and selection guide
  - Complete constraint value tables
  - Interface timing specifications
  - Usage guide for each design stage
  - Multi-corner analysis guide
  - Troubleshooting section
  - Timing closure checklist

#### `QUICK_REFERENCE.md` (Quick Lookup)
- **Purpose**: Fast reference during synthesis/STA sessions
- **Contents**:
  - Clock constraint templates
  - I/O timing quick reference
  - Common STA commands
  - Target metrics
  - Port count reference
  - Timing budget breakdown
  - Troubleshooting quick fixes

#### `SDC_FILES_SUMMARY.md` (This File)
- **Purpose**: High-level overview of all SDC-related files

## Design Specifications

### Clock Domain

| Parameter | Pre-CTS | Post-CTS |
|:----------|:--------|:---------|
| Frequency | 100 MHz | 100 MHz |
| Period | 10.0 ns | 10.0 ns |
| Uncertainty | 0.5 ns (5%) | Setup: 0.1 ns, Hold: 0.05 ns |
| Source Latency | 1.0 ns | 1.0 ns |

### Interface Summary

| Interface | Type | Ports | Input Delay (max/min) | Output Delay (max/min) |
|:----------|:-----|:------|:----------------------|:-----------------------|
| AXI4-Lite | Memory (master) | 25 | 2.0 / 0.5 ns | 2.0 / 0.5 ns |
| APB3 | Debug (slave) | 8 | 3.0 / 1.0 ns | 3.0 / 0.5 ns |
| Commit | Verification (output) | 5 | N/A | 5.0 / 0.0 ns |

### Total Port Count
- **Inputs**: 18 (excluding clock/reset)
- **Outputs**: 20
- **Total**: 40 ports (including clk, rst_n)

## Workflow Recommendations

### Synthesis Stage
1. Use `phase1_cpu_enhanced.sdc`
2. Run synthesis with timing-driven optimization
3. Check WNS (should be > 0)
4. Generate timing reports

### Floorplan/Placement Stage
1. Continue using `phase1_cpu_enhanced.sdc`
2. Optimize for wire length and congestion
3. Verify preliminary timing estimates

### Clock Tree Synthesis Stage
1. Run CTS
2. **Switch to** `phase1_cpu_post_cts.sdc`
3. Verify clock skew < 100ps
4. Check setup/hold timing

### Routing Stage
1. Use `phase1_cpu_post_cts.sdc`
2. Run detailed routing
3. Extract parasitics (RC)
4. Re-run STA with RC annotations

### Final STA
1. Use `phase1_cpu_post_cts.sdc`
2. Run multi-corner analysis (SS, FF, TT)
3. Check timing closure checklist
4. Generate sign-off reports

## Verification Checklist

Before sign-off, verify:

- [ ] Run `check_constraints.tcl` → PASS
- [ ] All ports have I/O delay constraints
- [ ] WNS > 0 (all corners)
- [ ] TNS = 0 (all corners)
- [ ] No hold violations
- [ ] Clock skew < 100ps (post-CTS)
- [ ] Max transition violations = 0
- [ ] Max capacitance violations = 0
- [ ] Unconstrained path report empty

## Constraint Philosophy

### Conservative Pre-CTS Values
The pre-CTS SDC uses conservative estimates because:
1. Clock tree not yet built (skew unknown)
2. Wire parasitics estimated (not extracted)
3. Need margin for subsequent stages

### Aggressive Post-CTS Values
The post-CTS SDC uses tighter values because:
1. Clock tree is built (skew is known)
2. Parasitics can be extracted
3. Physical design is mostly complete

### Interface Timing Rationale

**AXI4-Lite (2.0ns / 0.5ns)**:
- Based on typical SRAM/memory controller timing
- Allows 20% of clock cycle for external interface
- Conservative to support wide range of memory types

**APB3 (3.0ns / 1.0ns)**:
- Debug interface, not performance critical
- Relaxed to ease routing and reduce congestion
- 30% of clock cycle margin

**Commit (5.0ns / 0.0ns)**:
- Verification only, doesn't affect functionality
- Very relaxed to avoid constraining critical paths
- Effectively unconstrained

## Future Phase Updates

### Phase 2 (Pipelined CPU)
- Increase target frequency (200-500 MHz)
- Add multi-cycle path constraints for pipeline stages
- Define forwarding path constraints
- Add interrupt signal constraints

### Phase 3 (Cache System)
- Add SRAM timing models
- Multi-cycle paths for cache access
- Cache coherence protocol timing

### Phase 4 (GPU Integration)
- Multi-clock domain constraints
- Clock domain crossing (CDC) constraints
- Asynchronous FIFO timing

### Phase 5 (Full SoC)
- Multiple asynchronous clock domains
- Peripheral interface timing (UART, SPI)
- Power domain constraints
- Always-on clock domain

## References

| Document | Location | Purpose |
|:---------|:---------|:--------|
| SDC Timing Spec | `docs/design/SDC_TIMING_SPEC.md` | Complete SDC specification |
| Phase 1 Architecture | `docs/design/PHASE1_ARCHITECTURE_SPEC.md` | CPU architecture details |
| RTL Definition | `docs/design/RTL_DEFINITION.md` | Interface signal definitions |
| Memory Map | `docs/design/MEMORY_MAP.md` | Address space and registers |
| OpenROAD Flow | `docs/design/OPENROAD_FLOW_SPEC.md` | Physical design flow |

## Change Log

### 2026-01-22 - Initial SDC Files Created
- Created `phase1_cpu_enhanced.sdc` with comprehensive port coverage
- Created `phase1_cpu_post_cts.sdc` for post-CTS analysis
- Created `check_constraints.tcl` verification script
- Created `README_SDC.md` full documentation
- Created `QUICK_REFERENCE.md` quick lookup guide
- Baseline `phase1_cpu.sdc` already exists from specification

### Future Updates
- Update after PDK selection (add library-specific constraints)
- Update after first synthesis run (add critical path constraints if needed)
- Update after multi-corner analysis (refine I/O timing if needed)

## Contact and Support

For questions about SDC constraints:
1. Refer to `README_SDC.md` for detailed documentation
2. Use `QUICK_REFERENCE.md` for quick lookups
3. Run `check_constraints.tcl` to verify coverage
4. See `docs/design/SDC_TIMING_SPEC.md` for specification

---

**Recommended Starting Point**: Use `phase1_cpu_enhanced.sdc` for all initial work, then switch to `phase1_cpu_post_cts.sdc` after clock tree synthesis.

**Last Updated**: 2026-01-22
