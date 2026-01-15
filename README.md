# RV32I RISC-V Microprocessor

A fully functional RV32I RISC-V microprocessor implemented in SystemVerilog, featuring AXI4-Lite memory interface and APB3 debug interface.

## Features

- **ISA**: Complete RISC-V RV32I base integer instruction set (37 instructions)
- **Architecture**: Single-cycle execution with stalls for memory operations
- **Memory Interface**: AXI4-Lite Master for instruction fetch and data access
- **Debug Interface**: APB3 Slave with full debug capabilities
  - Halt/Resume/Single-step execution
  - Register file read/write access
  - Program counter manipulation
  - Hardware breakpoints (2 breakpoints)
- **Simulation**: Verilator-based testbench with comprehensive test suite

## Project Structure

```
├── rtl/                          # RTL source files
│   ├── rv32i_cpu_top.sv          # Top-level module
│   ├── pkg/                      # Package definitions
│   │   ├── rv32i_pkg.sv          # RISC-V types, opcodes
│   │   └── axi4lite_pkg.sv       # AXI4-Lite types
│   ├── core/                     # CPU core modules
│   │   ├── rv32i_core.sv         # CPU core wrapper
│   │   ├── rv32i_alu.sv          # Arithmetic Logic Unit
│   │   ├── rv32i_regfile.sv      # 32x32-bit register file
│   │   ├── rv32i_decode.sv       # Instruction decoder
│   │   ├── rv32i_control.sv      # Control FSM
│   │   └── rv32i_imm_gen.sv      # Immediate generator
│   ├── interfaces/               # Bus interfaces
│   │   ├── axi4lite_master.sv    # AXI4-Lite master
│   │   └── apb3_slave.sv         # APB3 debug slave
│   └── debug/
│       └── rv32i_debug.sv        # Breakpoint controller
├── tb/                           # Testbench files
│   ├── tb_rv32i_cpu_top.sv       # Main testbench
│   ├── axi4lite_mem.sv           # AXI4-Lite memory model
│   ├── apb3_master.sv            # APB3 master BFM
│   └── programs/                 # Test programs (.hex)
├── sim/                          # Simulation directory
│   ├── Makefile                  # Build automation
│   └── main.cpp                  # Verilator main
└── CLAUDE.md                     # Claude Code instructions
```

## Requirements

- **Verilator** (5.x recommended)
- **GCC/G++** with C++17 support
- **Make**
- **WSL** (Windows Subsystem for Linux) if running on Windows

## Quick Start

### Build and Run (WSL/Linux)

```bash
# Navigate to simulation directory
cd sim

# Build the simulation
make sim

# Run all tests
make run

# View waveforms (generates waveform.vcd)
make waves

# Clean build artifacts
make clean
```

### Run Unit Tests

```bash
cd sim
make test_alu        # ALU unit test
make test_regfile    # Register file unit test
make unit_tests      # All unit tests
```

## Test Suite

The testbench includes comprehensive tests:

| Test | Description |
|------|-------------|
| ALU Program | Basic arithmetic operations (ADD, ADDI) |
| Load/Store | Memory load (LW) and store (SW) operations |
| Branch | Branch instruction testing (BEQ) |
| Debug Halt/Resume | Debug halt and resume functionality |
| Debug Register Access | GPR read/write via debug interface |
| Breakpoint | Hardware breakpoint functionality |
| Single-Step | Single instruction stepping |

## Debug Interface

The APB3 debug interface provides the following registers:

| Address | Register | Description |
|---------|----------|-------------|
| 0x000 | DBG_CTRL | Control: [0]=halt, [1]=resume, [2]=step, [3]=reset |
| 0x004 | DBG_STATUS | Status: [0]=halted, [1]=running, [7:4]=halt_cause |
| 0x008 | DBG_PC | Program Counter |
| 0x00C | DBG_INSTR | Current instruction |
| 0x010-0x08C | DBG_GPR[0:31] | General purpose registers |
| 0x100 | DBG_BP0_ADDR | Breakpoint 0 address |
| 0x104 | DBG_BP0_CTRL | Breakpoint 0 control: [0]=enable |
| 0x108 | DBG_BP1_ADDR | Breakpoint 1 address |
| 0x10C | DBG_BP1_CTRL | Breakpoint 1 control: [0]=enable |

### Halt Causes

| Value | Cause |
|-------|-------|
| 0 | None |
| 1 | Debug halt request |
| 2 | Breakpoint hit |
| 3 | Single-step complete |
| 4 | EBREAK instruction |

## Supported Instructions

All RV32I base integer instructions are supported:

- **Integer Arithmetic**: ADD, ADDI, SUB, LUI, AUIPC
- **Logical**: AND, ANDI, OR, ORI, XOR, XORI
- **Shifts**: SLL, SLLI, SRL, SRLI, SRA, SRAI
- **Comparison**: SLT, SLTI, SLTU, SLTIU
- **Branches**: BEQ, BNE, BLT, BGE, BLTU, BGEU
- **Jumps**: JAL, JALR
- **Memory**: LB, LH, LW, LBU, LHU, SB, SH, SW
- **System**: ECALL, EBREAK, FENCE

## License

This project is for educational and testing purposes.
