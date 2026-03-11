# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-phase RV32I RISC-V microprocessor + GPU-lite SoC project

**Current Phase**: Phase 3 (Memory System & Caches - RTL Implementation)

**Status**: Phase 2 complete (2026-03-08, 75 MHz on Sky130), Phase 3 RTL implementation in progress

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

### Phase 2: Pipelined CPU ✅ COMPLETE

- **Status**: ✅ Complete (2026-03-08) — 75 MHz on Sky130 130nm
- **ISA**: RV32I + Zicsr (CSR instructions)
- **Architecture**: 5-stage in-order pipeline (IF/ID/EX/MEM/WB)
- **Interrupt Support**: M-mode (timer + external interrupts)
- **Hazard Handling**: Detection, stalling, forwarding
- **Achieved Frequency**: 75 MHz on Sky130 130nm (200 MHz target not met due to PDK limitations)
- **Verification**: 111/111 tests passing, 50,000 random instructions, 0 failures

### Phase 3 (Current): Memory System & Caches

- **Status**: 🔄 RTL implementation in progress (started 2026-03-08)
- **Architecture**: L1 I-Cache (4 KB, direct-mapped) + L1 D-Cache (4 KB, direct-mapped, write-back)
- **Cache Line**: 16 bytes (4 words); 256 sets; 4 AXI4-Lite transactions per refill
- **FENCE.I**: Supported — invalidates I-cache in 1 cycle
- **Target Frequency**: 75 MHz on Sky130 (realistic for SRAM-based cache)

### Phase 3-5: Future Phases

- **Phase 3**: Memory system with I-cache + D-cache (write-back, no coherence) ← CURRENT
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
| `docs/design/PHASE2_ARCHITECTURE_SPEC.md` | Pipelined CPU spec (Phase 2) - ✅ Complete |
| `docs/design/PHASE3_ARCHITECTURE_SPEC.md` | Cache architecture spec (Phase 3) - ✅ Approved |
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

### Phase 2 Workflow ✅ Complete

1. ✅ **Architecture approved**: All design decisions finalized
2. ✅ **Write RTL**: All 14 pipeline modules implemented
3. ✅ **Initial testing**: 115/115 regression tests passing
4. ✅ **Comprehensive verification**: 111/111 tests passing (all 7 suites)
5. ✅ **Random regression**: 50,000 instructions, 0 failures
6. ✅ **Backend flow**: 75 MHz achieved on Sky130 130nm
7. ✅ **Sign-off**: Phase 2 complete (2026-03-08)

### Phase 3 Workflow (Current)

1. ✅ **Architecture approved**: All 6 design decisions finalized (2026-03-08)
2. 🔄 **Write RTL**: Cache package, I-cache, D-cache, arbiter + modified pipeline stages
3. ⏸️ **Unit tests**: I-cache unit tests, D-cache unit tests
4. ⏸️ **Integration tests**: Full CPU + caches; FENCE.I correctness
5. ⏸️ **Phase 2 regression**: All 111 tests must pass (FENCE.I now valid, not a trap)
6. ⏸️ **Random regression**: 50,000+ instructions with caches enabled
7. ⏸️ **Backend flow**: Synthesis + P&R + STA at 75 MHz (Sky130, SRAM macros)
8. ⏸️ **Sign-off**: Coverage analysis, final review

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
├── rtl/
│   ├── cpu/
│   │   ├── rv32i_cpu_top.sv           # Top-level (AXI4-Lite + APB3)
│   │   ├── rv32i_axi_arbiter.sv       # Phase 2 arbiter (replaced by cache arbiter in Phase 3)
│   │   └── core/
│   │       ├── rv32i_core.sv          # Core wrapper (MODIFIED in Phase 3: adds caches)
│   │       ├── rv32i_pipeline_pkg.sv  # Pipeline structs (MODIFIED: fence_i added)
│   │       ├── rv32i_hazard_unit.sv   # Hazard unit (MODIFIED: renamed stall signals)
│   │       ├── rv32i_decode.sv        # Decoder (MODIFIED: FENCE.I added)
│   │       └── pipeline/
│   │           ├── rv32i_pipeline_if.sv   # IF stage (MODIFIED: cache interface)
│   │           ├── rv32i_pipeline_id.sv   # ID stage
│   │           ├── rv32i_pipeline_ex.sv   # EX stage
│   │           ├── rv32i_pipeline_mem.sv  # MEM stage (MODIFIED: cache + FENCE.I)
│   │           └── rv32i_pipeline_wb.sv   # WB stage
│   ├── mem/                           # NEW in Phase 3: cache RTL
│   │   ├── rv32i_cache_pkg.sv         # Cache parameters and types
│   │   ├── rv32i_icache.sv            # I-cache (4 KB, direct-mapped)
│   │   ├── rv32i_dcache.sv            # D-cache (4 KB, write-back)
│   │   └── rv32i_cache_arbiter.sv     # D$ priority AXI arbiter
│   ├── gpu/
│   ├── periph/
│   └── soc/
├── tb/                       # Testbench
│   ├── models/               # Python reference models
│   │   ├── rv32i_model.py
│   │   ├── cache_model.py             # NEW in Phase 3: DirectMappedCache
│   │   ├── gpu_kernel_model.py
│   │   └── memory_model.py
│   ├── tests/                # Unit tests for models
│   │   ├── test_rv32i_model.py
│   │   └── test_gpu_model.py
│   └── cocotb/               # cocotb testbenches
│       ├── cpu/              # CPU tests (Phase 1+)
│       └── mem/              # Cache tests (Phase 3+)
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

**Current priorities** (Phase 3 - Memory System & Caches):

**Phase 0 Complete** ✅:

- ✅ All 7 specifications approved (2026-01-18)
- ✅ Python reference models validated (66/66 tests passing)
- ✅ cocotb test infrastructure ready

**Phase 1 Complete** ✅ (2026-02-13):

- ✅ All 8 RTL modules implemented (~1,900 lines)
- ✅ All 9/9 verification exit criteria met
- ✅ ISA compliance: 37/37 instructions passing
- ✅ Random testing: 10,000 instructions, 0 failures
- ✅ Archived to `micro_p/` directory

**Phase 2 Complete** ✅ (2026-03-08):

- ✅ Architecture specification approved (2026-02-14)
- ✅ All 14 pipeline modules implemented
- ✅ Comprehensive verification: 111/111 tests passing
- ✅ Random regression: 50,000 instructions, 0 failures
- ✅ Backend: 75 MHz achieved on Sky130 130nm
- ✅ Constraints: `pnr/constraints/phase2_cpu.sdc`, `pnr/constraints/phase2_cpu.upf`

**Phase 3 Current Tasks**:

1. **RTL Implementation** (in progress)
   - 🔄 `rtl/mem/rv32i_cache_pkg.sv` — cache parameters and types
   - 🔄 `rtl/mem/rv32i_icache.sv` — I-cache (4 KB, direct-mapped, FENCE.I)
   - 🔄 `rtl/mem/rv32i_dcache.sv` — D-cache (4 KB, write-back + write-allocate)
   - 🔄 `rtl/mem/rv32i_cache_arbiter.sv` — D$ priority AXI arbiter
   - 🔄 Modified pipeline stages: `rv32i_pipeline_if.sv`, `rv32i_pipeline_mem.sv`
   - 🔄 Modified support: `rv32i_decode.sv` (FENCE.I), `rv32i_hazard_unit.sv` (stall rename)
   - 🔄 Modified core: `rv32i_core.sv` (cache instantiation)

2. **Reference Model** (parallel with RTL)
   - 🔄 `tb/models/cache_model.py` — `DirectMappedCache` class

3. **Verification** (follows RTL completion)
   - ⏸️ Unit tests: `tb/cocotb/mem/test_icache.py`, `test_dcache.py`
   - ⏸️ Integration: `tb/cocotb/mem/test_cache_integration.py`
   - ⏸️ Phase 2 regression (all 111 tests; FENCE.I now valid)
   - ⏸️ Random regression: 50,000+ instructions with caches

4. **Physical Design** (follows verification)
   - ⏸️ Synthesis + P&R + STA at 75 MHz on Sky130
   - ⏸️ `pnr/constraints/phase3_cache.sdc` and `phase3_cache.upf`

## Questions?

Refer to specifications in `docs/` - they are the source of truth.
