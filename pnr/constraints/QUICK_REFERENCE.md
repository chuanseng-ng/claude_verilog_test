# SDC Quick Reference Card - Phase 1 CPU

## Clock Constraints

```tcl
# 100 MHz clock
create_clock -name clk -period 10.0 [get_ports clk]

# Pre-CTS uncertainty
set_clock_uncertainty 0.5 [get_clocks clk]

# Post-CTS uncertainty
set_clock_uncertainty -setup 0.1 [get_clocks clk]
set_clock_uncertainty -hold 0.05 [get_clocks clk]
```

## I/O Timing Quick Reference

### AXI4-Lite (Memory Interface)

```tcl
# Inputs (max=2.0ns, min=0.5ns)
set_input_delay -clock clk -max 2.0 [get_ports axi_arready]
set_input_delay -clock clk -max 2.0 [get_ports axi_rdata[*]]
set_input_delay -clock clk -max 2.0 [get_ports axi_rvalid]
set_input_delay -clock clk -max 2.0 [get_ports axi_awready]
set_input_delay -clock clk -max 2.0 [get_ports axi_wready]
set_input_delay -clock clk -max 2.0 [get_ports axi_bvalid]

# Outputs (max=2.0ns, min=0.5ns)
set_output_delay -clock clk -max 2.0 [get_ports axi_araddr[*]]
set_output_delay -clock clk -max 2.0 [get_ports axi_arvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_rready]
set_output_delay -clock clk -max 2.0 [get_ports axi_awaddr[*]]
set_output_delay -clock clk -max 2.0 [get_ports axi_awvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_wdata[*]]
set_output_delay -clock clk -max 2.0 [get_ports axi_wstrb[*]]
set_output_delay -clock clk -max 2.0 [get_ports axi_wvalid]
set_output_delay -clock clk -max 2.0 [get_ports axi_bready]
```

### APB3 (Debug Interface)

```tcl
# Inputs (max=3.0ns, min=1.0ns)
set_input_delay -clock clk -max 3.0 [get_ports apb_paddr[*]]
set_input_delay -clock clk -max 3.0 [get_ports apb_psel]
set_input_delay -clock clk -max 3.0 [get_ports apb_penable]
set_input_delay -clock clk -max 3.0 [get_ports apb_pwrite]
set_input_delay -clock clk -max 3.0 [get_ports apb_pwdata[*]]

# Outputs (max=3.0ns, min=0.5ns)
set_output_delay -clock clk -max 3.0 [get_ports apb_prdata[*]]
set_output_delay -clock clk -max 3.0 [get_ports apb_pready]
set_output_delay -clock clk -max 3.0 [get_ports apb_pslverr]
```

## False Paths

```tcl
# Reset (async)
set_false_path -from [get_ports rst_n]

# Debug <-> AXI independence
set_false_path -from [get_ports apb_*] -to [get_ports axi_*]
set_false_path -from [get_ports axi_*] -to [get_ports apb_*]

# Verification-only outputs
set_false_path -to [get_ports commit_*]
set_false_path -to [get_ports trap_*]
```

## Design Rules

```tcl
# Pre-CTS
set_max_transition 0.5 [current_design]
set_max_capacitance 0.1 [all_outputs]
set_max_fanout 16 [current_design]
set_load 0.05 [all_outputs]
set_input_transition 0.2 [all_inputs]

# Post-CTS (tighter transition)
set_max_transition 0.4 [current_design]
```

## Common STA Commands

```tcl
# Load SDC
read_sdc constraints/phase1_cpu_enhanced.sdc

# Setup check (WNS should be > 0)
report_checks -path_delay max -format full_clock_expanded -nworst 10

# Hold check (should have zero violations)
report_checks -path_delay min -format full_clock_expanded -nworst 10

# Slack summaries
report_wns  # Worst negative slack
report_tns  # Total negative slack

# Clock analysis
report_clock_skew -hold -setup [get_clocks clk]
report_clock_properties [all_clocks]

# Find unconstrained paths
report_checks -unconstrained

# Path groups (by endpoint)
report_timing -group [get_clocks clk] -sort_by slack
```

## Target Metrics (100 MHz)

| Metric | Target | Notes |
|:-------|:-------|:------|
| Clock Period | 10.0 ns | 100 MHz |
| WNS (setup) | > 0 ns | No violations |
| TNS (setup) | 0 ns | Sum of all violations |
| WNS (hold) | > 0 ns | No violations |
| Clock Skew | < 100 ps | Post-CTS |
| Setup Margin | > 1.0 ns | 10% margin recommended |

## Multi-Corner Corners

```tcl
# Worst setup (SS corner)
set_operating_conditions -max ss_1p0v_125c
report_checks -path_delay max

# Worst hold (FF corner)
set_operating_conditions -min ff_1p1v_n40c
report_checks -path_delay min

# Typical (TT corner)
set_operating_conditions typical
```

## Port Count Reference

Phase 1 CPU (`rv32i_cpu_top`):

| Port Type | Count |
|:----------|:------|
| Clock/Reset | 2 |
| AXI4-Lite | 25 (10 inputs, 15 outputs) |
| APB3 | 8 (6 inputs, 2 outputs) |
| Commit | 5 (all outputs) |
| **Total** | **40 ports** |

## Timing Budget Breakdown

For 10ns period with 0.5ns uncertainty (pre-CTS):

| Stage | Budget | Description |
|:------|:-------|:------------|
| Clock uncertainty | 0.5 ns | Jitter + skew |
| Clock-to-Q | 0.5 ns | Flip-flop output delay |
| Logic delay | 7.5 ns | Combinational logic |
| Setup time | 0.5 ns | Flip-flop input |
| Margin | 1.0 ns | Safety margin (10%) |
| **Total** | **10.0 ns** | One clock cycle |

## Critical Path Examples

```tcl
# PC update path
set_max_delay 9.0 -from [get_pins u_core/pc_reg*] -to [get_pins u_core/pc_next*]

# ALU path
set_max_delay 8.0 -from [get_pins u_core/u_alu/operand_*] -to [get_pins u_core/u_alu/result*]

# Branch comparator
set_max_delay 7.0 -from [get_pins u_core/u_regfile/*] -to [get_pins u_core/branch_taken]
```

## Troubleshooting Quick Guide

| Problem | Quick Fix |
|:--------|:----------|
| WNS < 0 | 1. Increase period<br>2. Add path constraints<br>3. Higher synthesis effort |
| Hold violations | 1. Check CTS skew<br>2. Verify FF corner<br>3. Add hold buffers |
| Unconstrained paths | 1. Run check_constraints.tcl<br>2. Check I/O delays<br>3. Review wildcards |
| High skew | 1. Improve CTS<br>2. Balance clock tree<br>3. Check fanout |

## File Locations

```text
pnr/constraints/
├── phase1_cpu.sdc              # Original baseline
├── phase1_cpu_enhanced.sdc     # Enhanced (use this)
├── phase1_cpu_post_cts.sdc     # Post-CTS version
├── check_constraints.tcl       # Verification script
├── README_SDC.md               # Full documentation
└── QUICK_REFERENCE.md          # This file
```

---

**Quick Start**: Use `phase1_cpu_enhanced.sdc` for synthesis and pre-CTS, switch to `phase1_cpu_post_cts.sdc` after CTS.

**Last Updated**: 2026-01-22
