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

## Directory status (which flow is live)

| Directory | Status |
| :-------- | :----- |
| `asap7/cpu/`, `asap7/gpu/`, `asap7/soc/` | **LIVE** — the ASAP7 flows (`librelane-asap7`, `-gpu`, `-soc`, `-soc-multiclock`) |
| `asap7/template/` | Copy-me starting point for a new ASAP7 design; no target of its own. Its `check_source_closure.py` "gap" is a placeholder-path artifact, not a defect |
| `sky130/cpu/`, `sky130/soc/` | **LIVE** — the only flows with real Magic DRC + Netgen LVS (`librelane-sky130-cpu`, `librelane-sky130-soc`, GH #102/#103/#104) |
| `freepdk45/` | **DORMANT but intentional** — no per-node replacement exists; `librelane-nangate45` is the only path to that node |
| `librelane/` | **SUPERSEDED** by `sky130/cpu/`, which was forked from it with DRC/LVS enabled (`docs/SKY130_REAL_DRC_LVS_EVALUATION.md` §Stage 1). Last run 2026-03-25; `librelane-sky130` kept as a fallback |
| `openlane1/` | **SUPERSEDED** by `sky130/cpu/`. Docker/OL1 path (`docker-run`, `docker-synth`, `docker-results`) kept as a fallback; last run 2026-03-15 |

Both superseded directories carry the stale `VERILOG_FILES` package-closure gap tracked in bead
`135` — run `python3 tools/verif/check_source_closure.py <config.json>` before trusting either.
`openlane/` (speculative OpenLane-2 scaffolding, never wired to any Makefile target) was deleted;
LibreLane is the OL2-lineage tool this project uses.

> **Two flows coexist here.** The *Usage* / *Quick Start* section above drives the standalone
> Yosys + OpenROAD + OpenSTA script flow (`pnr/scripts/0*.tcl`, reading `pnr/config/` and
> `pnr/constraints/`) — those targets are real and still work. The per-node directories in the
> table below are the LibreLane flows, invoked through the `librelane-*` targets instead. Run
> `make -C pnr help` for the authoritative target list.

## Phase-Specific Flows

- **Phase 1**: Single-cycle CPU core
- **Phase 2**: Pipelined CPU with interrupt controller
- **Phase 3**: Cache system (I-cache + D-cache)
- **Phase 4**: GPU-lite compute unit
- **Phase 5**: Full SoC integration

Each phase has its own constraints and configuration files in the `constraints/` directory.

ASAP7 GPU block (`gpu_top`) is signed off at **571 MHz / 262 mW / 115,600 µm²**
(`asap7/gpu/runs/RUN_2026-05-28_06-29-48`); see `docs/GPU_ASAP7_RUN_HISTORY.md`.
CPU (`rv32i_cpu_top`) is signed off at 1418 MHz (`docs/CPU_ASAP7_RUN_HISTORY.md`).

## Hard-Macro Views (Phase-5 SoC hand-off)

Export a signed-off ASAP7 block as LEF + LIB + netlist for hierarchical SoC P&R:

```bash
make macro-views-asap7 BLOCK=gpu     # latest GPU run → asap7/gpu/macro/
make macro-views-asap7               # latest CPU run → asap7/cpu/macro/ (BLOCK=cpu default)
```

The flat post-route netlist is committed gzipped (`<design>.nl.v.gz`; the raw GPU netlist is
~103 MB, over GitHub's 100 MB limit). Run `gunzip -k <design>.nl.v.gz` to restore it. The LEF
(gitignored, regenerated on demand) and LIB are read directly by P&R tools.

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
