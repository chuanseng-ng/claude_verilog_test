# RV32I RISC-V Microprocessor + GPU-Lite SoC

[![QA Checks](https://github.com/chuanseng-ng/claude_verilog_test/actions/workflows/qa-checks.yml/badge.svg)](https://github.com/chuanseng-ng/claude_verilog_test/actions/workflows/qa-checks.yml)
[![Tests](https://github.com/chuanseng-ng/claude_verilog_test/actions/workflows/tests.yml/badge.svg)](https://github.com/chuanseng-ng/claude_verilog_test/actions/workflows/tests.yml)

Multi-phase project building a complete SoC with RV32I RISC-V CPU, GPU-lite compute engine, memory system, and peripherals.

## Project Vision

This project incrementally builds a fully functional SoC:

1. **Phase 0**: Specification & Reference Models ✅ **COMPLETE** (2026-01-18)
2. **Phase 1**: Minimal RV32I CPU (single-cycle) ✅ **COMPLETE** (2026-02-13)
3. **Phase 2**: Pipelined CPU (5-stage + interrupts) ✅ **COMPLETE** (2026-03-08)
4. **Phase 3**: Memory System (I-cache + D-cache) ✅ **COMPLETE** (2026-05-21)
5. **Phase 4**: GPU-Lite Compute Engine (SIMT) ✅ **COMPLETE** (2026-05-27)
6. **Phase 5**: SoC Integration (peripherals, boot ROM) ✅ **COMPLETE** (2026-06-24)
7. **Phase 6**: IP expansion — GPIO/I2C/PWM/WDT/TRNG/AES-SHA, INT8 NPU ✅ **complete** (Sky130 Gate B harden closed 2026-10-05)
8. **Phase 7**: Mixed-signal charge-pump PLL (dual-PDK, AMS RNM) ✅ M-a–M-c complete

## Current Status

Phases 0–5 complete. **Phase 6 complete** (epic `f7vs` closed 2026-10-05): **6a** (GPIO — also hardened on Sky130 — plus PWM, WDT, TRNG, I2C), **6b** (AES-128 + SHA-256 crypto accelerator) and **6c** (INT8 4×4 NPU with a 4 KB hard-macro weight SRAM). Two tracks are open: **DFT** (scan + JTAG + MBIST for the Sky130 SoC, epic `j41m`) and **FPGA prototyping** (epic `hlrm`, Stage 0 done, no hardware yet).

**The strongest result in this project is the Sky130 SoC**, because Sky130 is the only node here with
genuine physical verification (ASAP7 and FreePDK45 skip Magic/KLayout/Netgen entirely). As of
2026-09-26, `RUN_2026-09-26_00-07-59` onward:

| Sky130 SoC gate | Result |
| :-------------- | :----- |
| Netgen LVS | **PASSED** — "Circuits match uniquely", 0 errors |
| Setup, all 9 corners | **0 violations** (worst +7.08 ns) |
| Hold, all 9 corners | **0 violations** (worst +0.14 ns) |
| Routing DRC | **0** |
| Frequency / power / util | 40 MHz · ~48 mW · ~39 % |

⚠️ Caveats that matter: the SRAM macro is characterized at **TT only**, so "9 corners" means 9 corner
*labels* backed by one macro model; Magic DRC reports 9,081 violations, a waived PDK artifact
(bead `45a`); and KLayout DRC is currently **deferred, not waived** (it OOM-killed an 8.5 GB step on a
15 GB host). Detail → [`docs/SKY130_REAL_DRC_LVS_EVALUATION.md`](docs/SKY130_REAL_DRC_LVS_EVALUATION.md).

**Latest batched Sky130 SoC harden (Gate B, `RUN_2026-10-05_06-50-11`, bead `f7vs.15`, PR #214)** covers all Phase 6 IP: setup met at all 9 corners (worst is max_ss **+0.579 ns**, the thin corner to watch), hold 0 violators at all 9, Netgen LVS clear, routing DRC 0, 81.0 mW total, 44.8 % utilisation, 1 703 620 µm² stdcell. KLayout DRC skipped, not waived. Antenna 210 nets / 305 pins accepted by user decision (2026-10-05); the `e45j` slew/cap counts are recorded, not gating. Source: Doc: ds:ch:phase6-ip-expansion-plan:8-physical-design-two-gates-not-one.

⚠️ **Every ASAP7 figure below is unvalidated**, and the ASAP7 CPU/GPU macros additionally rest on a
netlist with a **proven frontend miscompile** (beads `u99`/`ma7` — a Synlig-built netlist mis-executes
a branch). Those are shelved pending a ≥32 GB host. See `CLAUDE.md` for the full exposure.

| Phase | Status | Date | Headline result |
| :---- | :----- | :--- | :-------------- |
| 0 — Specs & reference models | ✅ | 2026-01-18 | 66/66 model tests passing |
| 1 — Minimal RV32I CPU | ✅ | 2026-02-13 | 9/9 exit criteria; 37/37 ISA; 10k random, 0 fail |
| 2 — Pipelined CPU + interrupts | ✅ | 2026-03-08 | 111/111 tests; 50k random; 75 MHz Sky130 |
| 3 — L1 I/D caches | ✅ | 2026-05-21 | 139/139 regression; ASAP7 **1418 MHz / 27.27 mW / 3,844 µm²** ⚠️ unvalidated (bead `8f3`/`0p6`) |
| 4 — GPU-Lite SIMT | ✅ | 2026-05-27 | GPU+CPU regression green; ASAP7 **571 MHz / 262 mW** ⚠️ unvalidated (bead `8f3`/`0p6`) |
| 5 — SoC integration | ✅ | 2026-06-24 | M1–M12 done; ASAP7 SoC 571 MHz / 62.9 mW ⚠️ unvalidated (bead `8f3`/`0p6`). Current RTL re-measured on the fixed flow (bead `0d0`): −727 ps / 781 violators / hold clean / 283.6 mW — not closed |
| 6a — GPIO controller | ✅ | 2026-09-26 | APB4, 32-pin, `0x2000_A000`; `test_gpio` 16/16, `soc_all` 217/217. **Sky130: LVS PASSED, setup + hold both clean at all 9 corners** |
| 6b — CRYPTO (AES-128 + SHA-256) | ✅ | 2026-10-03 | APB4 index 12, IRQ 10; `test_crypto` 41/41 (FIPS-197 + SP 800-38A vectors); Gate A 277 875 µm² |
| 6c — INT8 NPU (4×4) | ✅ | 2026-10-04 | APB4 index 13, IRQ 11; `test_npu` 39/39, `test_soc_npu` 1/1; Gate A 203 179 µm² stdcell + 4 KB macro |
| 6 — Gate B (batched Sky130 harden) | ✅ | 2026-10-05 | `RUN_2026-10-05_06-50-11`: setup met 9/9 corners, hold 0, LVS clear, routing DRC 0 (`f7vs.15`, PR #214) |
| DFT — scan + MBIST + JTAG (`j41m`) | 🚧 | — | Stage 0 architecture (PR #250); Stage 1a fabric RTL (PR #258, bead open); Stage 1b JTAG TAP (PR #270). MBIST not built |
| FPGA prototype (`hlrm`) | 🚧 | — | Stage 0 open-tool resource counts, no hardware (PR #279); board recommendation Nexys Video XC7A200T (PR #283); ECP5 fmax lower bound ~48–52 MHz CPU |

Full per-phase records and feature lists → Doc: cr:status:phase-history.

## Project Structure

Top level: `rtl/` (CPU, GPU, caches, peripherals, SoC), `tb/` (Python models + cocotb),
`docs/` (specs), `pnr/` (physical design), `sim/`, `micro_p/` (archived Phase 1).

Full directory tree → Doc: um:guide:project-structure.

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
Doc: um:guide:quick-start.

## Documentation

Core specifications in `docs/`:

| Document | Purpose |
| :------- | :------ |
| `Doc: cr:status:roadmap` | Project phases and overall plan |
| `Doc: cr:status:phase-status` | Current phase status and next steps |
| `Doc: ds:ch:phase0-architecture` | CPU architectural requirements |
| `Doc: ds:ch:phase1-architecture` | Phase 1 CPU spec (single-cycle) ✅ Complete |
| `Doc: ds:ch:phase2-architecture` | Phase 2 CPU spec (5-stage pipeline) ✅ Complete |
| `Doc: ds:ch:phase3-architecture` | Phase 3 cache spec (I-cache + D-cache) ✅ Complete |
| `Doc: ds:ch:phase4-gpu-architecture` | GPU architecture specification (Phase 4) |
| `Doc: ds:ch:rtl-definition` | Interface signal definitions |
| `Doc: ds:mm:memory-map` | Address space and register map |
| `Doc: ds:ch:reference-model` | Python reference model API |
| `SKY130_REAL_DRC_LVS_EVALUATION.md` | Sky130 real DRC/LVS sign-off — the only genuinely verified node |
| `LIBRELANE_PATCHING_EVALUATION.md` | Whether/how to patch the shared LibreLane install |
| `Doc: ds:ch:verification-plan` | Verification strategy by phase |
| `design/DFT_ARCHITECTURE.md` | DFT scan + MBIST + JTAG architecture for the Sky130 SoC (epic `j41m`) |
| `FPGA_STAGE0_EVALUATION.md` | FPGA Stage 0 feasibility: yosys resource counts, no hardware (epic `hlrm`) |
| `FPGA_BOARD_SELECTION.md` | FPGA board recommendation and measured ECP5 fmax lower bound (epic `hlrm`) |
| `Doc: um:guide:coding-guidelines` | Coding practices & style guidelines (RTL + Python + shell) |
| `Doc: um:guide:coding-compliance-audit` | Guidelines compliance audit and remediation backlog |

The README detail set is in the User Manual and the Changes record
(`docs/manual/`). To build the PDFs, see [`docs/README.md`](docs/README.md).

| Document | Purpose |
| :------- | :------ |
| `Doc: cr:status:phase-history` | Per-phase completion records and feature lists |
| `Doc: um:guide:quick-start` | Build/run commands for every phase |
| `Doc: um:guide:supported-instructions` | RV32I + Zicsr instruction tables |
| `Doc: um:guide:debug-interface` | APB3 debug register map |
| `Doc: um:guide:project-structure` | Full repository directory tree |

## Supported Instructions

RV32I base (Phase 1, 37 instructions) + Zicsr/interrupts (Phase 2) — full tables in
Doc: um:guide:supported-instructions.

## Debug Interface

APB3 slave: halt/resume/step, register and PC access, 2 hardware breakpoints. Register
map in Doc: um:guide:debug-interface;
complete definitions in Doc: ds:mm:memory-map.

## Contributing

This is a specification-driven project with clear phase boundaries. Contributions should:

1. Follow the current phase's scope (Phase 6 — IP expansion — is complete; current tracks are DFT `j41m` and FPGA `hlrm`)
2. Maintain consistency with specifications in `docs/`
3. Include appropriate tests (pytest for Phase 0, cocotb for Phase 1+)

## License

This project is for educational and testing purposes.
