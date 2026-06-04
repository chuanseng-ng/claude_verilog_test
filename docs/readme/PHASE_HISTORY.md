# Phase History

Detailed completion records for each project phase. For the high-level map and
current status, see the root [`README.md`](../../README.md) and
[`docs/PHASE_STATUS.md`](../PHASE_STATUS.md).

## Phase 0 Complete ✅ (2026-01-18)

- ✅ All 7 architectural specifications finalized and approved
- ✅ Python reference models implemented and validated (66/66 tests passing)
- ✅ cocotb test infrastructure ready

## Phase 1 Complete ✅ (2026-02-13)

- ✅ All 8 RTL modules implemented (~1,900 lines)
- ✅ All 9/9 verification exit criteria met
- ✅ 37/37 RV32I instructions verified
- ✅ 10,000 random instructions, 0 failures
- ✅ AXI protocol compliance verified (11/11 tests)
- ✅ Debug interface complete (6/6 tests)
- ✅ Full coverage: 37/37 instructions, 8/8 FSM states
- ✅ Archived to `micro_p/` directory

## Phase 2 Complete ✅ (2026-03-08)

- ✅ Architecture approved (5-stage pipeline + interrupts + CSR)
- ✅ All 14 RTL modules implemented
- ✅ Comprehensive verification: 111/111 tests passing (all 7 suites)
- ✅ Random regression: 50,000 instructions (500 seeds × 100), 0 failures
- ✅ IRQ latency: ≤3 cycles from assertion to trap_taken
- ✅ Backend: 75 MHz achieved on Sky130 130nm

## Phase 3 Complete ✅ (2026-05-21)

- ✅ L1 I-Cache (4 KB, direct-mapped) + L1 D-Cache (4 KB, write-back + write-allocate)
- ✅ FENCE.I: 1-cycle I-cache invalidation
- ✅ Cache arbiter: D$ priority over I$ (D-write > D-read > I-read)
- ✅ Verification: I-cache 7/7, D-cache 8/8, integration 5/5; **139/139 full regression**
- ✅ PPA sign-off (ASAP7 7nm, Run 43, 2026-05-20): **1418 MHz / 27.27 mW / 3,844 µm²**, 0 DRC, 0 antenna

## Phase 4 Complete ✅ (2026-05-27)

- ✅ 9/9 GPU-Lite RTL modules (`rtl/gpu/`): top, command queue, warp scheduler, compute unit, vector regfile, vector ALU, memory unit, coalescer, shared memory
- ✅ SIMT execution: 8-lane warps, round-robin scheduler, single-level divergence stack, 16 KB / 32-bank shared memory
- ✅ Verification: GPU unit + kernel tests green; CPU re-gate 140/140 + 100k random; 1,000-kernel random regression, 0 deadlocks/mismatches
- ✅ PPA sign-off (ASAP7 7nm, Run `RUN_2026-05-28_06-29-48`): **571 MHz (1.75 ns) / 262 mW / 115,600 µm² die / 60,500 µm² stdcell**, Setup WS +197.3 ps, Hold WS +16.3 ps (0 viol), 0 antenna

## Implemented Features

### Phase 1 (Complete) ✅

- **ISA**: Complete RISC-V RV32I base integer instruction set (37 instructions)
- **Architecture**: Single-cycle execution with AXI stalls
- **Memory Interface**: AXI4-Lite Master (unified instruction/data bus)
- **Debug Interface**: APB3 Slave with full capabilities
  - Halt/Resume/Single-step execution
  - Register file read/write access
  - Program counter manipulation
  - Hardware breakpoints (2 breakpoints)

### Phase 2 ✅

- **ISA**: RV32I + Zicsr (CSR instructions: CSRRW/S/C/I variants)
- **Architecture**: 5-stage in-order pipeline (IF/ID/EX/MEM/WB)
- **Interrupt Support**: RISC-V M-mode (timer + external interrupts)
- **Hazard Handling**: Detection, stalling, EX/MEM/WB forwarding
- **Target Performance**: 1 IPC at 200 MHz (2x Phase 1 frequency)
- **AXI Arbitration**: Priority arbiter for IF vs MEM requests
- **Debug Interface**: Enhanced with pipeline drain support
- **GPU-Lite**: SIMT compute engine with 8-lane warp execution (Phase 4)
- **SoC**: DMA, UART, SPI, Timer, Boot ROM (Phase 5)
