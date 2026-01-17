# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-phase RV32I RISC-V microprocessor + GPU-lite SoC project

**Current Phase**: Phase 0 (Specification & Reference Models)

**Status**: All specifications complete, reference model implementation in progress

**Target**: Build a complete SoC with CPU, GPU, caches, and peripherals through incremental phases

## Project Phases

See `docs/ROADMAP.md` for complete phase plan and `docs/PHASE_STATUS.md` for current status.

### Phase 0 (Current): Foundations

- **Status**: Specifications complete, reference model implementation in progress
- **Goal**: Finalize all specifications and reference models
- **Deliverables**: Architecture specs (✅ complete), Python reference models (🟡 in progress), test infrastructure (🟡 in progress)
- **No RTL yet**
- **Exit Criteria**: All 7 specifications approved, Python reference models tested and validated

### Phase 1 (Next): Minimal RV32I Core

- **ISA**: RISC-V RV32I (37 base integer instructions)
- **Architecture**: Single-cycle (stalls on memory operations)
- **Memory Interface**: AXI4-Lite Master (unified instruction/data)
- **Debug Interface**: APB3 Slave (halt/resume/step/breakpoints)
- **No interrupts** (deferred to Phase 2)

### Phase 2-5: Future Phases

- **Phase 2**: 5-stage pipelined CPU + interrupt support (timer + external)
- **Phase 3**: Memory system with I-cache + D-cache (write-back, no coherence)
- **Phase 4**: GPU-lite SIMT compute engine (8-lane warps, single compute unit, no graphics)
- **Phase 5**: SoC integration (CPU + GPU + DMA + UART + SPI + Timer + Boot ROM)

**Note**: GPU in Phase 4 requires Phase 2+ CPU for interrupt support (kernel completion notifications)

## Key Documentation

**Always refer to these specifications** (do not rely on non-existent RTL):

| Document | Purpose |
| :------- | :------ |
| `docs/ROADMAP.md` | High-level project plan and phases |
| `docs/PHASE_STATUS.md` | Current project status and next steps |
| `docs/design/PHASE0_ARCHITECTURE_SPEC.md` | CPU architectural requirements (Phase 0) |
| `docs/design/PHASE1_ARCHITECTURE_SPEC.md` | CPU implementation spec (Phase 1) |
| `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md` | GPU architecture spec (Phase 4) |
| `docs/design/RTL_DEFINITION.md` | Interface signal definitions |
| `docs/design/MEMORY_MAP.md` | Address space and register map |
| `docs/design/REFERENCE_MODEL_SPEC.md` | Python reference model API |
| `docs/verification/VERIFICATION_PLAN.md` | Verification strategy by phase |

## Frequently Used Commands

### Phase 0 (Current): Reference Model and Tests

```bash
# Run reference model unit tests
cd tb/tests
pytest test_rv32i_model.py -v

# Run reference model with coverage
pytest --cov=tb.models --cov-report=html

# Test memory model
pytest test_memory_model.py -v
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

### Phase 0 Workflow (Current)

1. **Read specifications**: Always start with docs in `docs/design/`
2. **Implement reference model**: Write Python models per `REFERENCE_MODEL_SPEC.md`
3. **Test reference model**: Use pytest, cross-validate vs spike
4. **Setup testbench**: Prepare cocotb infrastructure
5. **Review**: Ensure specs are complete before proceeding to Phase 1

### Phase 1+ Workflow (Future)

1. **Write RTL**: Implement modules per Phase 1 spec
2. **Lint**: Run Verilator lint checks
3. **Write tests**: Create cocotb tests
4. **Run tests**: Compare RTL vs reference model via scoreboard
5. **Debug**: Use waveforms and logs to fix mismatches
6. **Iterate**: Refine until all tests pass

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
│   │   └── REFERENCE_MODEL_SPEC.md
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

**Current priorities** (Phase 0 - Specifications Complete ✅):

**Remaining Implementation Tasks**:

1. **Python reference model implementation** (AI-assisted, human-verified)
   - `tb/models/rv32i_model.py` - CPU instruction-accurate model
   - `tb/models/gpu_kernel_model.py` - GPU SIMT execution model
   - `tb/models/memory_model.py` - Shared memory model
   - AI may assist with: Boilerplate code, simple instruction implementations
   - Human must: Verify complex instructions, approve all logic, final review

2. **cocotb test infrastructure setup** (AI-assisted)
   - cocotb environment configuration
   - Test harness scaffolding
   - Driver templates for AXI4-Lite and APB3
   - AI may assist with: Infrastructure scaffolding, boilerplate code
   - Human must: Review and approve test strategy

3. **Final specification review** (HUMAN-ONLY)
   - Review all 7 specification documents
   - Approve Phase 0 completion
   - Authorize transition to Phase 1

## Questions?

Refer to specifications in `docs/` - they are the source of truth.
