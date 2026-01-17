# RV32I RISC-V Microprocessor + GPU-Lite SoC

Multi-phase project building a complete SoC with RV32I RISC-V CPU, GPU-lite compute engine, memory system, and peripherals.

## Project Vision

This project incrementally builds a fully functional SoC through 6 phases:

1. **Phase 0** (Current): Specification & Reference Models
2. **Phase 1**: Minimal RV32I CPU (single-cycle)
3. **Phase 2**: Pipelined CPU (5-stage + interrupts)
4. **Phase 3**: Memory System (I-cache + D-cache)
5. **Phase 4**: GPU-Lite Compute Engine (SIMT)
6. **Phase 5**: SoC Integration (peripherals, boot ROM)

## Current Status: Phase 0 (Specification Phase)

**Completed**:

- All architectural specifications finalized
- Interface definitions (AXI4-Lite, APB3)
- Memory map and register definitions
- Verification strategy documented

**In Progress**:

- Python reference model implementation
- cocotb test infrastructure setup

**No RTL exists yet** - RTL implementation begins in Phase 1

## Planned Features (Phase 1+)

- **ISA**: Complete RISC-V RV32I base integer instruction set (37 instructions)
- **Architecture**: Single-cycle execution (Phase 1) → 5-stage pipeline (Phase 2)
- **Memory Interface**: AXI4-Lite Master for instruction fetch and data access
- **Debug Interface**: APB3 Slave with full debug capabilities
  - Halt/Resume/Single-step execution
  - Register file read/write access
  - Program counter manipulation
  - Hardware breakpoints (2 breakpoints)
- **GPU-Lite**: SIMT compute engine with 8-lane warp execution (Phase 4)
- **SoC**: DMA, UART, SPI, Timer, Boot ROM (Phase 5)

## Project Structure

```text
├── docs/                         # Specifications (Phase 0)
│   ├── ROADMAP.md                # Project phases and plan
│   ├── PHASE_STATUS.md           # Current phase status
│   ├── design/
│   │   ├── PHASE0_ARCHITECTURE_SPEC.md   # CPU architectural spec
│   │   ├── PHASE1_ARCHITECTURE_SPEC.md   # CPU implementation spec (Phase 1)
│   │   ├── PHASE4_GPU_ARCHITECTURE_SPEC.md # GPU architecture spec (Phase 4)
│   │   ├── RTL_DEFINITION.md     # Interface signal definitions
│   │   ├── MEMORY_MAP.md         # Address space and registers
│   │   └── REFERENCE_MODEL_SPEC.md # Python reference model API
│   └── verification/
│       └── VERIFICATION_PLAN.md  # Verification strategy
├── tb/                           # Testbench and reference models
│   ├── models/                   # Python reference models (Phase 0)
│   │   ├── rv32i_model.py        # CPU instruction-accurate model
│   │   ├── gpu_kernel_model.py   # GPU SIMT execution model
│   │   └── memory_model.py       # Memory system model
│   ├── tests/                    # Unit tests for reference models
│   │   ├── test_rv32i_model.py
│   │   └── test_gpu_model.py
│   └── cocotb/                   # cocotb testbenches (Phase 1+)
├── rtl/                          # RTL source files (Phase 1+)
│   ├── cpu/                      # (empty - Phase 1)
│   ├── gpu/                      # (empty - Phase 4)
│   ├── mem/                      # (empty - Phase 3)
│   ├── periph/                   # (empty - Phase 5)
│   └── soc/                      # (empty - Phase 5)
├── sim/                          # Simulation scripts (Phase 1+)
└── CLAUDE.md                     # Claude Code instructions
```

## Requirements

### Phase 0 (Current)

- **Python** 3.8+ with pytest
- **cocotb** (for test infrastructure setup)

### Phase 1+ (Future)

- **Verilator** (5.x recommended)
- **GCC/G++** with C++17 support
- **Make**
- **WSL** (Windows Subsystem for Linux) if running on Windows

## Quick Start

### Phase 0: Reference Model Testing (Current)

```bash
# Navigate to test directory
cd tb/tests

# Run reference model unit tests
pytest test_rv32i_model.py -v

# Run with coverage
pytest --cov=tb.models --cov-report=html

# Test memory model
pytest test_memory_model.py -v
```

### Phase 1+: RTL Simulation (Future)

```bash
# Navigate to simulation directory
cd sim

# Build and run simulation
make sim
make run

# Run with waveforms
make waves

# Run cocotb tests
make test

# Clean build artifacts
make clean
```

## Documentation

Key documents in `docs/`:

| Document | Purpose |
| :------- | :------ |
| `ROADMAP.md` | Project phases and overall plan |
| `PHASE_STATUS.md` | Current phase status and next steps |
| `design/PHASE0_ARCHITECTURE_SPEC.md` | CPU architectural requirements |
| `design/PHASE1_ARCHITECTURE_SPEC.md` | CPU implementation specification (Phase 1) |
| `design/PHASE4_GPU_ARCHITECTURE_SPEC.md` | GPU architecture specification (Phase 4) |
| `design/RTL_DEFINITION.md` | Interface signal definitions |
| `design/MEMORY_MAP.md` | Address space and register map |
| `design/REFERENCE_MODEL_SPEC.md` | Python reference model API |
| `verification/VERIFICATION_PLAN.md` | Verification strategy by phase |

## Debug Interface (Phase 1+)

The planned APB3 debug interface will provide the following registers:

| Address | Register | Description |
| :------ | :------- | :---------- |
| 0x000 | DBG_CTRL | Control: [0]=halt, [1]=resume, [2]=step, [3]=reset |
| 0x004 | DBG_STATUS | Status: [0]=halted, [1]=running, [7:4]=halt_cause |
| 0x008 | DBG_PC | Program Counter |
| 0x00C | DBG_INSTR | Current instruction |
| 0x010-0x08C | DBG_GPR[0:31] | General purpose registers |
| 0x100 | DBG_BP0_ADDR | Breakpoint 0 address |
| 0x104 | DBG_BP0_CTRL | Breakpoint 0 control: [0]=enable |
| 0x108 | DBG_BP1_ADDR | Breakpoint 1 address |
| 0x10C | DBG_BP1_CTRL | Breakpoint 1 control: [0]=enable |

See `docs/design/MEMORY_MAP.md` for complete register definitions.

## Supported Instructions (Phase 1+)

The RV32I implementation will support all 37 base integer instructions:

- **Integer Arithmetic**: ADD, ADDI, SUB, LUI, AUIPC
- **Logical**: AND, ANDI, OR, ORI, XOR, XORI
- **Shifts**: SLL, SLLI, SRL, SRLI, SRA, SRAI
- **Comparison**: SLT, SLTI, SLTU, SLTIU
- **Branches**: BEQ, BNE, BLT, BGE, BLTU, BGEU
- **Jumps**: JAL, JALR
- **Memory**: LB, LH, LW, LBU, LHU, SB, SH, SW
- **System**: ECALL, EBREAK, FENCE

See `docs/design/PHASE0_ARCHITECTURE_SPEC.md` for instruction semantics.

## Project Phases

For detailed phase descriptions and current status, see:

- `docs/ROADMAP.md` - Complete project plan and phase descriptions
- `docs/PHASE_STATUS.md` - Current phase status and next steps

## Contributing

This is a specification-driven project with clear phase boundaries. Contributions should:

1. Follow the current phase's scope (currently Phase 0)
2. Maintain consistency with specifications in `docs/`
3. Include appropriate tests (pytest for Phase 0, cocotb for Phase 1+)

## License

This project is for educational and testing purposes.
