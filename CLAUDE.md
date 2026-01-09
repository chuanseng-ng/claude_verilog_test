# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

RV32I RISC-V microprocessor implemented in SystemVerilog with:

- **ISA**: RISC-V RV32I (37 base integer instructions)
- **Architecture**: Single-cycle (stalls on memory operations)
- **Memory Interface**: AXI4-Lite Master
- **Debug Interface**: APB3 Slave

## Build Commands

```bash
# Navigate to simulation directory
cd sim

# Build main testbench
make sim

# Run simulation
make run

# Run with waveform viewing
make waves

# Run unit tests
make test_alu        # ALU unit test
make test_regfile    # Register file unit test
make unit_tests      # All unit tests

# Clean build artifacts
make clean
```

## Architecture

```text
rtl/
├── rv32i_cpu_top.sv          # Top-level (AXI + APB)
├── pkg/
│   ├── rv32i_pkg.sv          # RISC-V types, opcodes
│   └── axi4lite_pkg.sv       # AXI4-Lite types
├── core/
│   ├── rv32i_core.sv         # CPU core wrapper
│   ├── rv32i_alu.sv          # ALU (all RV32I ops)
│   ├── rv32i_regfile.sv      # 32x32-bit registers
│   ├── rv32i_decode.sv       # Instruction decoder
│   ├── rv32i_control.sv      # Control FSM
│   └── rv32i_imm_gen.sv      # Immediate generator
├── interfaces/
│   ├── axi4lite_master.sv    # AXI4-Lite master
│   └── apb3_slave.sv         # APB3 debug slave
└── debug/
    └── rv32i_debug.sv        # Breakpoint controller
```

## Debug Interface (APB3)

| Address | Register | Description |
| :-----: | :------: | :---------: |
| 0x000 | DBG_CTRL | [0]=halt, [1]=resume, [2]=step, [3]=reset |
| 0x004 | DBG_STATUS | [0]=halted, [1]=running, [7:4]=halt_cause |
| 0x008 | DBG_PC | Program Counter |
| 0x00C | DBG_INSTR | Current instruction |
| 0x010-0x08C | DBG_GPR[0:31] | General purpose registers |
| 0x100 | DBG_BP0_ADDR | Breakpoint 0 address |
| 0x104 | DBG_BP0_CTRL | [0]=enable |
| 0x108 | DBG_BP1_ADDR | Breakpoint 1 address |
| 0x10C | DBG_BP1_CTRL | [0]=enable |

## Key Design Decisions

- Single-cycle core with AXI stalls for memory operations
- Unified AXI bus for instruction fetch and data access
- x0 register hardwired to zero in `rv32i_regfile.sv`
- EBREAK instruction triggers CPU halt
- Debug writes only allowed when CPU is halted

## Test Programs

Located in `tb/programs/`:

- `simple_add.hex` - Basic ALU operations
- `load_store.hex` - Memory load/store tests
- `branch_test.hex` - All branch conditions
