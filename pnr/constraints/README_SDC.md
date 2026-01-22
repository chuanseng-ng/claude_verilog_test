# SDC Timing Constraints - Phase 1 CPU

This directory contains Synopsys Design Constraint (SDC) files for the Phase 1 RV32I CPU timing analysis.

## Files Overview

| File | Purpose | When to Use |
|:-----|:--------|:------------|
| `phase1_cpu.sdc` | Original baseline constraints | Initial synthesis |
| `phase1_cpu_enhanced.sdc` | Enhanced with full port coverage | Recommended for all stages |
| `phase1_cpu_post_cts.sdc` | Post-CTS with tighter uncertainty | After clock tree synthesis |
| `check_constraints.tcl` | Verification script | To check constraint coverage |

## Constraint Summary

### Clock Specification

| Parameter | Pre-CTS | Post-CTS |
|:----------|:--------|:---------|
| **Period** | 10.0 ns | 10.0 ns |
| **Target Frequency** | 100 MHz | 100 MHz |
| **Uncertainty** | 0.5 ns (5%) | Setup: 0.1 ns, Hold: 0.05 ns |
| **Source Latency** | 1.0 ns | 1.0 ns |
| **Transition Time** | 0.1 ns | 0.1 ns |

### Interface Timing Constraints

#### AXI4-Lite Interface (Memory)

| Signal Group | Max Input Delay | Min Input Delay | Max Output Delay | Min Output Delay |
|:-------------|:----------------|:----------------|:-----------------|:-----------------|
| Address channels | 2.0 ns | 0.5 ns | 2.0 ns | 0.5 ns |
| Data channels | 2.0 ns | 0.5 ns | 2.0 ns | 0.5 ns |
| Control signals | 2.0 ns | 0.5 ns | 2.0 ns | 0.5 ns |

**Rationale**: Based on AXI4-Lite protocol requirements with external memory controller having 2ns setup and 0.5ns hold times.

#### APB3 Interface (Debug)

| Signal Group | Max Input Delay | Min Input Delay | Max Output Delay | Min Output Delay |
|:-------------|:----------------|:----------------|:-----------------|:-----------------|
| Address/Control | 3.0 ns | 1.0 ns | 3.0 ns | 0.5 ns |
| Data | 3.0 ns | 1.0 ns | 3.0 ns | 0.5 ns |

**Rationale**: Relaxed timing for debug interface (not performance critical).

#### Commit Interface (Verification)

| Signal Group | Max Output Delay | Min Output Delay |
|:-------------|:-----------------|:-----------------|
| All commit signals | 5.0 ns | 0.0 ns |

**Rationale**: Verification-only interface, very relaxed timing.

### Design Rules

| Constraint | Value | Description |
|:-----------|:------|:------------|
| **Max Transition** | 0.5 ns (pre-CTS), 0.4 ns (post-CTS) | Maximum signal slew rate |
| **Max Capacitance** | 0.1 pF | Maximum load on output ports |
| **Max Fanout** | 16 | Maximum number of loads per net |
| **Output Load** | 0.05 pF | Assumed external load (50fF) |
| **Input Transition** | 0.2 ns | Assumed input signal slew |

## Usage Guide

### 1. Pre-Synthesis / Initial Synthesis

Use `phase1_cpu_enhanced.sdc`:

```tcl
# In your synthesis script
read_sdc pnr/constraints/phase1_cpu_enhanced.sdc
```

### 2. After Clock Tree Synthesis

Switch to `phase1_cpu_post_cts.sdc`:

```tcl
# In your post-CTS STA script
read_sdc pnr/constraints/phase1_cpu_post_cts.sdc
```

### 3. Verify Constraints

Run the verification script to ensure all ports are constrained:

```tcl
# In OpenSTA or similar tool
source pnr/constraints/check_constraints.tcl
```

**Expected output**: "PASS: All ports are properly constrained!"

### 4. Check Timing

After loading constraints, run timing analysis:

```tcl
# Setup timing (worst negative slack should be > 0)
report_checks -path_delay max -format full_clock_expanded

# Hold timing (should have no violations)
report_checks -path_delay min -format full_clock_expanded

# Clock skew (post-CTS only, should be < 100ps)
report_clock_skew -hold -setup [get_clocks clk]

# Summary
report_tns  # Total negative slack (should be 0)
report_wns  # Worst negative slack (should be > 0)
```

## False Paths

The following paths are marked as false paths (don't need timing analysis):

1. **Asynchronous Reset (`rst_n`)**
   - Reset is asynchronous and doesn't have timing relationship with clock

2. **Debug ↔ AXI Cross Paths**
   - Debug interface (APB3) and memory interface (AXI4-Lite) are independent
   - Debug operations don't affect memory timing

3. **Commit Interface Outputs**
   - Verification-only signals
   - Don't affect functional timing

## Critical Paths

Expected critical paths in the design:

1. **PC Update Path**: `pc_reg → pc_next → pc_reg`
   - Target: < 9.0 ns

2. **ALU Datapath**: `regfile → ALU → result`
   - Target: < 8.0 ns

3. **Memory Load Path**: `AXI rdata → regfile write`
   - Includes data extraction and sign extension
   - Target: < 9.0 ns

4. **Branch Decision**: `regfile → branch_comp → pc_src`
   - Target: < 7.0 ns

## Multi-Corner Analysis

For sign-off quality, analyze across PVT corners:

| Corner | Process | Voltage | Temperature | Check |
|:-------|:--------|:--------|:------------|:------|
| **SS** | Slow | 0.9V | 125°C | Worst setup (slowest) |
| **FF** | Fast | 1.1V | -40°C | Worst hold (fastest) |
| **TT** | Typical | 1.0V | 25°C | Typical performance |

Example multi-corner script:

```tcl
# Setup check at SS corner (slowest)
set_operating_conditions -max ss_1p0v_125c -library sky130_fd_sc_hd__ss_1p0v_125c
report_checks -path_delay max -corner SS

# Hold check at FF corner (fastest)
set_operating_conditions -min ff_1p1v_n40c -library sky130_fd_sc_hd__ff_1p1v_n40c
report_checks -path_delay min -corner FF
```

## Troubleshooting

### Issue: WNS (Worst Negative Slack) < 0

**Causes**:

- Critical path exceeds 10ns
- Clock uncertainty too pessimistic
- Synthesis not optimizing critical paths

**Solutions**:

1. Increase clock period (reduce target frequency)
2. Add `set_max_delay` constraints on specific critical paths
3. Use higher synthesis effort
4. Review post-CTS uncertainty values
5. Consider pipeline architecture (Phase 2)

### Issue: Hold Violations

**Causes**:

- Clock skew too large
- Fast data paths with slow clock
- Incorrect min delays

**Solutions**:

1. Review CTS results, ensure skew < 100ps
2. Add hold buffers (synthesis should do automatically)
3. Check min input/output delay values
4. Verify operating corner (should use FF for hold)

### Issue: Unconstrained Paths

**Causes**:

- Missing I/O delay constraints
- New ports added without constraints
- Wildcards not matching port names

**Solutions**:

1. Run `check_constraints.tcl` to identify missing constraints
2. Add explicit constraints for new ports
3. Use `report_checks -unconstrained` to find paths

## Timing Closure Checklist

Before declaring timing closure:

- [ ] WNS > 0 (no setup violations)
- [ ] TNS = 0 (total negative slack is zero)
- [ ] No hold violations
- [ ] Clock skew < 100ps (post-CTS)
- [ ] All input ports have input_delay constraints
- [ ] All output ports have output_delay constraints
- [ ] False paths identified and documented
- [ ] Multi-corner analysis passing (SS and FF)
- [ ] Unconstrained path report is empty

## References

- **SDC Specification**: `docs/design/SDC_TIMING_SPEC.md`
- **CPU Architecture**: `docs/design/PHASE1_ARCHITECTURE_SPEC.md`
- **OpenROAD Flow**: `docs/design/OPENROAD_FLOW_SPEC.md`
- **Synopsys SDC User Guide**: Industry standard reference
- **OpenSTA Manual**: https://github.com/The-OpenROAD-Project/OpenSTA

## Maintenance Notes

**Last Updated**: 2026-01-22

**When to Update SDC Files**:

1. RTL port changes (new interfaces, renamed ports)
2. Target frequency changes
3. Interface protocol changes (AXI, APB timing)
4. PDK selection (update library references)
5. After timing analysis reveals issues

**Human Review Required**:

- All constraint values (clock period, I/O delays)
- False path identification
- Multi-cycle path definitions (if added)
- Critical path constraints
- Multi-corner analysis results
