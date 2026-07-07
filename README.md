# RV32I RISC-V Microprocessor + GPU-Lite SoC

[![QA Checks](https://github.com/chuanseng-ng/claude_verilog_test/actions/workflows/qa-checks.yml/badge.svg)](https://github.com/chuanseng-ng/claude_verilog_test/actions/workflows/qa-checks.yml)
[![Tests](https://github.com/chuanseng-ng/claude_verilog_test/actions/workflows/tests.yml/badge.svg)](https://github.com/chuanseng-ng/claude_verilog_test/actions/workflows/tests.yml)

Multi-phase project building a complete SoC with RV32I RISC-V CPU, GPU-lite compute engine, memory system, and peripherals.

## Project Vision

This project incrementally builds a fully functional SoC through 6 phases:

1. **Phase 0**: Specification & Reference Models ✅ **COMPLETE** (2026-01-18)
2. **Phase 1**: Minimal RV32I CPU (single-cycle) ✅ **COMPLETE** (2026-02-13)
3. **Phase 2**: Pipelined CPU (5-stage + interrupts) ✅ **COMPLETE** (2026-03-08)
4. **Phase 3**: Memory System (I-cache + D-cache) ✅ **COMPLETE** (2026-05-21)
5. **Phase 4**: GPU-Lite Compute Engine (SIMT) ✅ **COMPLETE** (2026-05-27)
6. **Phase 5**: SoC Integration (peripherals, boot ROM) 🚧 In Progress

## Current Status

Phase 5 (SoC Integration) in progress; Phases 0–4 complete.

| Phase | Status | Date | Headline result |
| :---- | :----- | :--- | :-------------- |
| 0 — Specs & reference models | ✅ | 2026-01-18 | 66/66 model tests passing |
| 1 — Minimal RV32I CPU | ✅ | 2026-02-13 | 9/9 exit criteria; 37/37 ISA; 10k random, 0 fail |
| 2 — Pipelined CPU + interrupts | ✅ | 2026-03-08 | 111/111 tests; 50k random; 75 MHz Sky130 |
| 3 — L1 I/D caches | ✅ | 2026-05-21 | 139/139 regression; ASAP7 **1418 MHz / 27.27 mW / 3,844 µm²** |
| 4 — GPU-Lite SIMT | ✅ | 2026-05-27 | GPU+CPU regression green; ASAP7 **571 MHz / 262 mW** |
| 5 — SoC integration | 🚧 | — | M1–M8 done; M9 SoC verification in progress |

Full per-phase records and feature lists → [`docs/readme/PHASE_HISTORY.md`](docs/readme/PHASE_HISTORY.md).

## Project Structure

Top level: `rtl/` (CPU, GPU, caches, peripherals, SoC), `tb/` (Python models + cocotb),
`docs/` (specs), `pnr/` (physical design), `sim/`, `micro_p/` (archived Phase 1).

Full directory tree → [`docs/readme/PROJECT_STRUCTURE.md`](docs/readme/PROJECT_STRUCTURE.md).

## Requirements

### Reference Models & Tests

- **Python** 3.8+ with pytest
- **cocotb** (for test infrastructure setup)

### RTL Simulation & Backend

- **Verilator** (5.x recommended)
- **GCC/G++** with C++17 support
- **Make**
- **WSL** (Windows Subsystem for Linux) if running on Windows

## Quick Start

Phase 0 reference-model tests (canonical entry point):

```bash
cd tb/tests
pytest -v        # 66 reference-model unit tests
```

Per-phase build/run commands (cocotb CPU suites, cache sims, random regression) →
[`docs/readme/QUICK_START.md`](docs/readme/QUICK_START.md).

## Documentation

Core specifications in `docs/`:

| Document | Purpose |
| :------- | :------ |
| `ROADMAP.md` | Project phases and overall plan |
| `PHASE_STATUS.md` | Current phase status and next steps |
| `design/PHASE0_ARCHITECTURE_SPEC.md` | CPU architectural requirements |
| `design/PHASE1_ARCHITECTURE_SPEC.md` | Phase 1 CPU spec (single-cycle) ✅ Complete |
| `design/PHASE2_ARCHITECTURE_SPEC.md` | Phase 2 CPU spec (5-stage pipeline) ✅ Complete |
| `design/PHASE3_ARCHITECTURE_SPEC.md` | Phase 3 cache spec (I-cache + D-cache) ✅ Complete |
| `design/PHASE4_GPU_ARCHITECTURE_SPEC.md` | GPU architecture specification (Phase 4) |
| `design/RTL_DEFINITION.md` | Interface signal definitions |
| `design/MEMORY_MAP.md` | Address space and register map |
| `design/REFERENCE_MODEL_SPEC.md` | Python reference model API |
| `verification/VERIFICATION_PLAN.md` | Verification strategy by phase |
| `development/CODING_GUIDELINES.md` | Coding practices & style guidelines (RTL + Python + shell) |
| `development/CODING_COMPLIANCE_AUDIT.md` | Guidelines compliance audit and remediation backlog |

README detail set in `docs/readme/`:

| Document | Purpose |
| :------- | :------ |
| `readme/PHASE_HISTORY.md` | Per-phase completion records and feature lists |
| `readme/QUICK_START.md` | Build/run commands for every phase |
| `readme/SUPPORTED_INSTRUCTIONS.md` | RV32I + Zicsr instruction tables |
| `readme/DEBUG_INTERFACE.md` | APB3 debug register map |
| `readme/PROJECT_STRUCTURE.md` | Full repository directory tree |

## Supported Instructions

RV32I base (Phase 1, 37 instructions) + Zicsr/interrupts (Phase 2) — full tables in
[`docs/readme/SUPPORTED_INSTRUCTIONS.md`](docs/readme/SUPPORTED_INSTRUCTIONS.md).

## Debug Interface

APB3 slave: halt/resume/step, register and PC access, 2 hardware breakpoints. Register
map in [`docs/readme/DEBUG_INTERFACE.md`](docs/readme/DEBUG_INTERFACE.md);
complete definitions in [`docs/design/MEMORY_MAP.md`](docs/design/MEMORY_MAP.md).

## Contributing

This is a specification-driven project with clear phase boundaries. Contributions should:

1. Follow the current phase's scope (Phase 5 — SoC integration)
2. Maintain consistency with specifications in `docs/`
3. Include appropriate tests (pytest for Phase 0, cocotb for Phase 1+)

## License

This project is for educational and testing purposes.
