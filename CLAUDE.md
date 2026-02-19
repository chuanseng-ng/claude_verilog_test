# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-phase RV32I RISC-V microprocessor + GPU-lite SoC project

**Current Phase**: Phase 2 (Pipelined CPU - Verification)

**Status**: Phase 1 complete (2026-02-13), Phase 2 RTL complete (2026-02-16), verification in progress

**Target**: Build a complete SoC with CPU, GPU, caches, and peripherals through incremental phases

## Project Phases

See `docs/ROADMAP.md` for complete phase plan and `docs/PHASE_STATUS.md` for current status.

### Phase 0: Foundations ✅ COMPLETE

- **Status**: ✅ Complete and approved (2026-01-18)
- **Goal**: Finalize all specifications and reference models
- **Deliverables**: Architecture specs (✅ complete), Python reference models (✅ 66/66 tests passing), test infrastructure (✅ complete)
- **No RTL** (as planned)
- **Exit Criteria Met**: All 7 specifications approved, Python reference models tested and validated, cocotb infrastructure ready

### Phase 1: Minimal RV32I Core ✅ COMPLETE

- **Status**: ✅ Complete (2026-02-13)
- **ISA**: RISC-V RV32I (37 base integer instructions)
- **Architecture**: Single-cycle (stalls on memory operations)
- **Memory Interface**: AXI4-Lite Master (unified instruction/data)
- **Debug Interface**: APB3 Slave (halt/resume/step/breakpoints)
- **Verification**: 9/9 exit criteria met, archived to `micro_p/`

### Phase 2 (Current): Pipelined CPU

- **Status**: RTL complete (2026-02-16), verification in progress
- **ISA**: RV32I + Zicsr (CSR instructions)
- **Architecture**: 5-stage in-order pipeline (IF/ID/EX/MEM/WB)
- **Interrupt Support**: M-mode (timer + external interrupts)
- **Hazard Handling**: Detection, stalling, forwarding
- **Target Frequency**: 200 MHz (2x Phase 1)

### Phase 2-5: Future Phases

- **Phase 2**: 5-stage pipelined CPU + interrupt support (timer + external)
- **Phase 3**: Memory system with I-cache + D-cache (write-back, no coherence)
- **Phase 4**: GPU-lite SIMT compute engine (8-lane warps, single compute unit, no graphics)
- **Phase 5**: SoC integration (CPU + GPU + DMA + UART + SPI + Timer + Boot ROM)

**Note**: GPU in Phase 4 requires Phase 2+ CPU for interrupt support (kernel completion notifications)

## Key Documentation

**Always refer to these specifications** (do not rely on non-existent RTL):

### Architecture & Design

| Document | Purpose |
| :------- | :------ |
| `docs/ROADMAP.md` | High-level project plan and phases |
| `docs/PHASE_STATUS.md` | Current project status and next steps |
| `docs/design/PHASE0_ARCHITECTURE_SPEC.md` | CPU architectural requirements (Phase 0) |
| `docs/design/PHASE1_ARCHITECTURE_SPEC.md` | CPU implementation spec (Phase 1) - ✅ Complete |
| `docs/design/PHASE2_ARCHITECTURE_SPEC.md` | Pipelined CPU spec (Phase 2) - ✅ Approved |
| `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md` | GPU architecture spec (Phase 4) |
| `docs/design/RTL_DEFINITION.md` | Interface signal definitions |
| `docs/design/MEMORY_MAP.md` | Address space and register map |
| `docs/design/REFERENCE_MODEL_SPEC.md` | Python reference model API |

### Physical Design (NEW)

| Document | Purpose |
| :------- | :------ |
| `docs/design/OPENROAD_FLOW_SPEC.md` | Complete OpenROAD flow documentation |
| `docs/design/UPF_POWER_SPEC.md` | Power intent and UPF specification |
| `docs/design/SDC_TIMING_SPEC.md` | Timing constraints and STA guidelines |
| `pnr/README.md` | Physical design directory structure |
| `pnr/constraints/phase1_cpu.sdc` | Phase 1 timing constraints |
| `pnr/constraints/phase1_cpu.upf` | Phase 1 power intent |

### Verification

| Document | Purpose |
| :------- | :------ |
| `docs/verification/VERIFICATION_PLAN.md` | Verification strategy (RTL + physical design) |
| `TODO_PHASE1_VERIFICATION.md` | Phase 1 verification progress tracking |
| `docs/RANDOM_TESTS_STATUS.md` | Random instruction test results and guide |

### RTL Fixes & Debugging

| Document | Purpose |
| :------- | :------ |
| `fixes/FIXES_INDEX.md` | ⭐ **Central reference for all RTL bug fixes** |
| `fixes/README.md` | Fixes directory guide and navigation |
| `fixes/CRITICAL_FIXES.md` | Critical AXI protocol fixes (2026-01-19) |
| `fixes/RTL_BUG_FIXES.md` | Branch/jump/memory fixes (2026-01-24) |
| `CLEANUP_SUMMARY.md` | Documentation organization summary |

**Note**: All RTL bugs discovered during development are documented in `fixes/` with full analysis, impact assessment, and validation. Start with `fixes/FIXES_INDEX.md` for quick reference.

## Frequently Used Commands

### Phase 0 (Complete): Reference Model and Tests

```bash
# Run reference model unit tests
cd tb/tests
pytest test_rv32i_model.py -v

# Run reference model with coverage
pytest --cov=tb.models --cov-report=html

# Test memory model
pytest test_memory_model.py -v
```

### Phase 1: OpenROAD Back-End Flow (NEW)

```bash
# Navigate to physical design directory
cd pnr

# Run full flow (synthesis through power analysis)
make all

# Run individual stages
make synth        # RTL synthesis
make floorplan    # Floorplanning
make place        # Placement
make cts          # Clock tree synthesis
make route        # Routing
make parasitics   # RC extraction
make sta          # Static timing analysis
make power        # Power analysis

# Generate reports
make report_timing   # Show timing summary
make report_power    # Show power summary
make report_area     # Show area summary
make report_summary  # Show all reports

# Clean build artifacts
make clean
```

### Phase 1+: Simulation Commands (When RTL exists)

#### WSL Commands (Windows Environment)

```bash
# Build and run simulation
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make sim"
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make run"

# Clean and rebuild
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make clean && make run"

# Run with waveform generation
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make waves"

# Run cocotb tests
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make test"
```

#### Native Linux/WSL Commands

```bash
# Navigate to simulation directory
cd sim

# Build and run cocotb tests
make test

# Run specific test
make test TEST=test_simple_add

# Run with waveforms
make waves

# Clean build artifacts
make clean
```

### Git Commands

```bash
# Check status
git status

# View recent commits
git log --oneline -5

# Create feature branch
git checkout -b feature/branch-name

# Commit with co-author
git commit -m "$(cat <<'EOF'
[Category] Commit message

Description here.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

## Planned Architecture (Phase 1)

**Note**: This architecture will be implemented in Phase 1. No RTL currently exists.

```text
rtl/
└── cpu/
    ├── rv32i_cpu_top.sv          # Top-level (AXI + APB)
    └── core/
        ├── rv32i_core.sv         # CPU core wrapper
        ├── rv32i_control.sv      # Control FSM
        ├── rv32i_decode.sv       # Instruction decoder
        ├── rv32i_alu.sv          # ALU (all RV32I ops)
        ├── rv32i_regfile.sv      # 32x32-bit registers
        └── rv32i_imm_gen.sv      # Immediate generator
```

See `docs/design/PHASE1_ARCHITECTURE_SPEC.md` for complete module specifications.

## Planned Debug Interface (APB3)

**Note**: To be implemented in Phase 1. Specification ready in `docs/design/MEMORY_MAP.md`.

| Address | Register | Description |
| :-----: | :------: | :---------: |
| 0x000 | DBG_CTRL | [0]=halt, [1]=resume, [2]=step, [3]=reset |
| 0x004 | DBG_STATUS | [0]=halted, [1]=running, [7:4]=halt_cause |
| 0x008 | DBG_PC | Program Counter (RW when halted) |
| 0x00C | DBG_INSTR | Current instruction (RO) |
| 0x010-0x08C | DBG_GPR[0:31] | General purpose registers (RW when halted) |
| 0x100 | DBG_BP0_ADDR | Breakpoint 0 address |
| 0x104 | DBG_BP0_CTRL | [0]=enable |
| 0x108 | DBG_BP1_ADDR | Breakpoint 1 address |
| 0x10C | DBG_BP1_CTRL | [0]=enable |

Complete register map in `docs/design/MEMORY_MAP.md`.

## Key Design Decisions (From Specifications)

**Phase 1 CPU**:

- Single-cycle execution with AXI stalls for memory operations
- Unified AXI4-Lite bus for instruction fetch and data access
- x0 register hardwired to zero (per RV32I spec)
- EBREAK instruction triggers CPU halt
- Debug writes only allowed when CPU is halted
- Only illegal instruction traps supported (no interrupts in Phase 1)
- Naturally aligned memory accesses only (misaligned = trap)

**Phase 4 GPU**:

- SIMT execution model (8 lanes per warp)
- Single compute unit
- Round-robin warp scheduling
- One-level divergence handling
- No cache coherence with CPU
- Memory coalescing when possible

## Reference Model (Python)

**Phase 0 deliverable**: Python reference models for CPU and GPU

**Location**: `tb/models/`

**Key files**:

- `rv32i_model.py` - CPU instruction-accurate model
- `gpu_kernel_model.py` - GPU SIMT execution model
- `memory_model.py` - Shared memory model

**Usage**:

```python
from tb.models.rv32i_model import RV32IModel

cpu = RV32IModel()
cpu.load_program({0x0000: 0x00000093})  # addi x1, x0, 0
result = cpu.step(0x00000093)
assert result['rd'] == 1
```

See `docs/design/REFERENCE_MODEL_SPEC.md` for complete API.

## Verification Strategy

**Phase 0 focus**:

1. Implement Python reference models
2. Unit test reference models (pytest)
3. Cross-validate CPU model vs RISC-V spike simulator
4. Setup cocotb infrastructure

**Phase 1+ focus**:

1. cocotb for interface drivers
2. pyuvm for test sequences and scoreboards
3. Compare RTL commits against reference model
4. Random instruction testing (10k+ instructions)

See `docs/verification/VERIFICATION_PLAN.md` for phase-by-phase verification plan.

## Common Workflow

### Phase 0 Workflow ✅ Complete

1. ✅ **Read specifications**: All docs in `docs/design/` reviewed
2. ✅ **Implement reference model**: Python models per `REFERENCE_MODEL_SPEC.md` complete
3. ✅ **Test reference model**: pytest passing (66/66 tests), cross-validated
4. ✅ **Setup testbench**: cocotb infrastructure ready
5. ✅ **Review**: All specs approved, ready for Phase 1

### Phase 1 Workflow ✅ Complete

1. ✅ **Write RTL**: All 8 modules implemented
2. ✅ **Lint**: Verilator lint checks passing
3. ✅ **Write tests**: Comprehensive cocotb test suite
4. ✅ **Run tests**: All tests passing (9/9 exit criteria met)
5. ✅ **Debug**: Major bugs fixed (branch/jump, load data, regfile)
6. ✅ **Complete**: Phase 1 archived to `micro_p/`, ready for Phase 2

### Phase 2 Workflow (Current)

1. ✅ **Architecture approved**: All design decisions finalized
2. ✅ **Write RTL**: All 14 pipeline modules implemented
3. ✅ **Initial testing**: 115/115 regression tests passing
4. 🔄 **Comprehensive verification**: Pipeline hazards, interrupts, CSR
5. 🔄 **Performance validation**: IPC measurement, frequency checks
6. 🔄 **Backend flow**: Synthesis, P&R, STA at 200 MHz
7. ⏸️ **Sign-off**: Coverage analysis, final review

## Project Structure

```text
.
├── docs/                     # All specifications
│   ├── ROADMAP.md
│   ├── PHASE_STATUS.md
│   ├── design/
│   │   ├── PHASE0_ARCHITECTURE_SPEC.md
│   │   ├── PHASE1_ARCHITECTURE_SPEC.md
│   │   ├── PHASE4_GPU_ARCHITECTURE_SPEC.md
│   │   ├── RTL_DEFINITION.md
│   │   ├── MEMORY_MAP.md
│   │   ├── REFERENCE_MODEL_SPEC.md
│   │   ├── OPENROAD_FLOW_SPEC.md    # NEW: Physical design flow
│   │   ├── UPF_POWER_SPEC.md        # NEW: Power intent
│   │   └── SDC_TIMING_SPEC.md       # NEW: Timing constraints
│   └── verification/
│       └── VERIFICATION_PLAN.md
├── rtl/                      # RTL (empty - Phase 1+)
│   ├── cpu/
│   ├── gpu/
│   ├── mem/
│   ├── periph/
│   └── soc/
├── tb/                       # Testbench
│   ├── models/               # Python reference models
│   │   ├── rv32i_model.py
│   │   ├── gpu_kernel_model.py
│   │   └── memory_model.py
│   ├── tests/                # Unit tests for models
│   │   ├── test_rv32i_model.py
│   │   └── test_gpu_model.py
│   └── cocotb/               # cocotb testbenches (Phase 1+)
├── sim/                      # Simulation scripts
├── pnr/                      # Physical design (NEW in Phase 1)
│   ├── Makefile              # Flow automation
│   ├── config/               # PDK configuration
│   ├── constraints/          # SDC + UPF files
│   ├── scripts/              # TCL flow scripts
│   ├── logs/                 # Flow logs (gitignored)
│   ├── reports/              # Reports (gitignored)
│   └── results/              # Netlist, DEF, GDS (gitignored)
└── CLAUDE.md                 # This file
```

## AI/Human Boundaries

### AI MAY assist with

- Python boilerplate (class structure, imports)
- Simple instruction implementations (after human verification)
- cocotb driver scaffolding
- Test case generation
- Documentation formatting

### Human MUST

- Write and approve all specifications
- Implement complex instructions (branches, loads, stores)
- Design control FSMs
- Define verification strategy
- Review all AI-generated code
- Make architectural decisions

See each phase in `docs/verification/VERIFICATION_PLAN.md` for detailed AI/Human responsibilities.

## Commit Message Convention

Use the format: `[Category] Brief description`

Categories:

- `[Fix]` - Bug fixes
- `[Feature]` - New features
- `[Code]` - Code changes/refactoring
- `[Env]` - Environment/build changes
- `[Doc]` - Documentation updates
- `[Test]` - Test additions/changes
- `[Spec]` - Specification updates

## Next Steps

See `docs/PHASE_STATUS.md` for current status and immediate next steps.

**Current priorities** (Phase 2 - Verification + Physical Design):

**Phase 0 Complete** ✅:

- ✅ All 7 specifications approved (2026-01-18)
- ✅ Python reference models validated (66/66 tests passing)
- ✅ cocotb test infrastructure ready

**Phase 1 Complete** ✅ (2026-02-13):

- ✅ All 8 RTL modules implemented (~1,900 lines)
- ✅ All 9/9 verification exit criteria met
- ✅ ISA compliance: 37/37 instructions passing
- ✅ Random testing: 10,000 instructions, 0 failures
- ✅ AXI protocol tests: 11/11 passing
- ✅ Debug interface tests: 6/6 passing
- ✅ Coverage: 37/37 instructions, 8/8 FSM states
- ✅ Archived to `micro_p/` directory

**Phase 2 RTL Complete** ✅ (2026-02-16):

- ✅ Architecture specification approved (2026-02-14)
- ✅ All 14 pipeline modules implemented
- ✅ Initial regression: 115/115 tests passing
- ✅ Backend constraints ready (phase2_cpu.sdc, phase2_cpu.upf)

**Phase 2 Current Tasks**:

1. **Comprehensive Verification** (in progress)
   - 🔄 Pipeline hazard tests (RAW, WAR, WAW dependencies)
   - 🔄 Interrupt and CSR instruction tests
   - 🔄 Debug interface tests (pipeline drain verification)
   - 🔄 Random instruction regression (target: 50k+ instructions)
   - 🔄 AXI arbiter protocol tests (IF vs MEM priority)
   - 🔄 Coverage collection (instruction, state, branch coverage)

2. **Performance Validation**
   - 🔄 IPC (instructions per cycle) measurement
   - 🔄 Frequency validation (target: 200 MHz)
   - 🔄 Pipeline efficiency analysis
   - 🔄 Interrupt latency measurement

3. **Physical Design Flow** (Phase 2 constraints ready)
   - Run synthesis with Phase 2 constraints
   - Execute place & route at 200 MHz target
   - Perform static timing analysis (STA)
   - Run power analysis (with power gating)
   - Validate timing closure
   - Gate-level simulation with SDF back-annotation

## Questions?

Refer to specifications in `docs/` - they are the source of truth.
