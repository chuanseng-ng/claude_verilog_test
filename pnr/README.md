# Physical Design (Place & Route) Directory

This directory contains all artifacts related to the OpenROAD physical design flow.

## Directory Structure

```text
pnr/
├── config/         # PDK and tool configuration files
├── constraints/    # Timing (SDC) and power (UPF) constraints
├── scripts/        # TCL scripts for each flow stage
├── logs/           # Log files from each run (gitignored)
├── reports/        # Reports: timing, power, area (gitignored)
├── results/        # Final outputs: netlist, DEF, GDS (gitignored)
├── work/           # Intermediate files (gitignored)
└── Makefile        # Flow automation
```

## Flow Overview

The physical design flow consists of these stages:

1. **Synthesis** (RTL → netlist)
2. **Floorplan** (die size, I/O placement, power grid)
3. **Placement** (cell placement)
4. **CTS** (clock tree synthesis)
5. **Routing** (wire generation)
6. **Parasitic Extraction** (RC extraction)
7. **STA** (static timing analysis)
8. **Power Analysis** (dynamic + leakage power)
9. **Physical Verification** (DRC/LVS)
10. **Gate-Level Simulation** (functional + timing verification)

## Usage

See `docs/design/OPENROAD_FLOW_SPEC.md` for complete flow documentation.

### Quick Start

```bash
# Run full flow
make all

# Run individual stages
make synth
make place
make route
make sta

# Generate reports
make report_timing
make report_power
make report_area

# Clean all artifacts
make clean
```

## Phase-Specific Flows

- **Phase 1**: Single-cycle CPU core
- **Phase 2**: Pipelined CPU with interrupt controller
- **Phase 3**: Cache system (I-cache + D-cache)
- **Phase 4**: GPU-lite compute unit
- **Phase 5**: Full SoC integration

Each phase has its own constraints and configuration files in the `constraints/` directory.

## Quality Gates

Before advancing to the next phase, the design must pass:

- [x] Synthesis: WNS > -0.5ns, area within budget
- [x] Place & Route: Zero DRC violations, routing converges
- [x] Timing: WNS = 0, TNS = 0 (all corners)
- [x] Power: IR drop < 5%, power within budget
- [x] Physical Verification: DRC = 0, LVS clean
- [x] Gate-Level Sim: 100% functional match with RTL

## Target Technologies

- **Sky130**: 130nm open-source PDK (primary)
- **ASAP7**: 7nm predictive PDK (alternate)

## Tools Required

- Yosys (synthesis)
- OpenROAD (place & route)
- OpenSTA (timing analysis)
- KLayout (physical verification)
- Verilator (gate-level simulation)

## References

- OpenROAD Flow Spec: `docs/design/OPENROAD_FLOW_SPEC.md`
- UPF Power Spec: `docs/design/UPF_POWER_SPEC.md`
- SDC Timing Constraints: `constraints/*.sdc`
