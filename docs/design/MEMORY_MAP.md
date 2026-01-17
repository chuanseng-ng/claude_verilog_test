# Memory Map Specification

Complete address space allocation for RV32I SoC

Document status: Active
Last updated: 2026-01-17

## Overview

This document defines the memory map for all phases of the project, from single-CPU (Phase 1)
through full SoC integration (Phase 5).

## Address Space (32-bit)

Total addressable space: 4 GB (0x0000_0000 to 0xFFFF_FFFF)

### Global Memory Map (Phase 5 SoC)

| Address Range              | Size    | Region              | Description                 |
|:--------------------------:|:-------:|:-------------------:|:---------------------------:|
| 0x0000_0000 - 0x0000_00FF  | 256 B   | Reset & Traps       | Reset vector, trap handlers |
| 0x0000_0100 - 0x0000_0FFF  | 3.75 KB | Boot ROM            | Initial boot code           |
| 0x0000_1000 - 0x0FFF_FFFF  | ~256 MB | Main Memory (RAM)   | Instruction and data        |
| 0x1000_0000 - 0x1FFF_FFFF  | 256 MB  | Reserved            | Future memory expansion     |
| 0x2000_0000 - 0x2000_0FFF  | 4 KB    | CPU Debug (APB3)    | CPU debug registers         |
| 0x2000_1000 - 0x2000_1FFF  | 4 KB    | GPU Control (APB3)  | GPU registers               |
| 0x2000_2000 - 0x2000_2FFF  | 4 KB    | UART (APB3)         | UART peripheral             |
| 0x2000_3000 - 0x2000_3FFF  | 4 KB    | SPI (APB3)          | SPI master                  |
| 0x2000_4000 - 0x2000_4FFF  | 4 KB    | Timer (APB3)        | System timer                |
| 0x2000_5000 - 0x2FFF_FFFF  | ~256 MB | Reserved            | Future peripherals          |
| 0x3000_0000 - 0x7FFF_FFFF  | 1.25 GB | Reserved            | Future use                  |
| 0x8000_0000 - 0xFFFF_FFFF  | 2 GB    | External Memory     | Off-chip memory/devices     |

## Phase-Specific Maps

### Phase 0-1: Single CPU (No SoC Integration)

In Phases 0-1, only the CPU exists. The AXI4-Lite master connects directly to a simple memory model.

**AXI4-Lite address space**:

| Address Range              | Size    | Description                 |
|:--------------------------:|:-------:|:---------------------------:|
| 0x0000_0000 - 0x0000_00FF  | 256 B   | Reset & trap vectors        |
| 0x0000_0100 - 0x0000_FFFF  | ~64 KB  | Program memory              |
| 0x0001_0000 - 0xFFFF_FFFF  | ~16 MB  | Data memory                 |

**APB3 debug interface** (CPU-local, 12-bit address):

See CPU Debug Registers section below.

### Phase 2-3: Pipelined CPU with Caches

Same as Phase 1, but with cache between CPU and memory.

**Cache configuration**:

- I-Cache: 4 KB, direct-mapped
- D-Cache: 4 KB, direct-mapped
- No cache coherence (single CPU)

### Phase 4: CPU + GPU (Pre-SoC Integration)

**AXI address space** (shared between CPU and GPU):

| Address Range              | Size    | Description                 |
|:--------------------------:|:-------:|:---------------------------:|
| 0x0000_0000 - 0x0FFF_FFFF  | 256 MB  | Shared memory (CPU+GPU)     |
| 0x2000_0000 - 0x2000_0FFF  | 4 KB    | CPU Debug registers         |
| 0x2000_1000 - 0x2000_1FFF  | 4 KB    | GPU Control registers       |

### Phase 5: Full SoC

See Global Memory Map above.

## Detailed Register Maps

### CPU Debug Registers (APB3 Slave)

**Base address**: 0x2000_0000 (in SoC), local offset 0x000 (APB3 12-bit addressing)

**Address width**: 12 bits (4 KB space, but only ~400 bytes used)

#### Control and Status Registers

| Offset | Name           | Access | Reset Value | Description                              |
|:------:|:--------------:|:------:|:-----------:|:----------------------------------------:|
| 0x000  | DBG_CTRL       | RW     | 0x0000_0000 | Debug control                            |
| 0x004  | DBG_STATUS     | RO     | 0x0000_0002 | Debug status                             |
| 0x008  | DBG_PC         | RW*    | 0x0000_0000 | Program counter                          |
| 0x00C  | DBG_INSTR      | RO     | 0x0000_0000 | Current instruction word                 |

*Writable only when CPU is halted

**DBG_CTRL (0x000)**: Debug Control Register

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:4  | Reserved   | RO     | Reserved, read as 0                            |
| 3     | RESET_REQ  | W1     | Write 1 to reset CPU (self-clearing)           |
| 2     | STEP_REQ   | W1     | Write 1 to single-step (self-clearing)         |
| 1     | RESUME_REQ | W1     | Write 1 to resume execution (self-clearing)    |
| 0     | HALT_REQ   | W1     | Write 1 to halt execution (self-clearing)      |

**DBG_STATUS (0x004)**: Debug Status Register

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:8  | Reserved   | RO     | Reserved, read as 0                            |
| 7:4   | HALT_CAUSE | RO     | Halt reason (see encoding below)               |
| 3:2   | Reserved   | RO     | Reserved, read as 0                            |
| 1     | RUNNING    | RO     | 1 = CPU running, 0 = CPU halted                |
| 0     | HALTED     | RO     | 1 = CPU halted, 0 = CPU running                |

**HALT_CAUSE encoding**:

- `4'b0000`: Not halted
- `4'b0001`: Debug halt request (via DBG_CTRL)
- `4'b0010`: Breakpoint 0 hit
- `4'b0011`: Breakpoint 1 hit
- `4'b0100`: Single-step complete
- `4'b1000`: EBREAK instruction executed
- Others: Reserved

#### General Purpose Registers

| Offset      | Name         | Access | Description                              |
|:-----------:|:------------:|:------:|:----------------------------------------:|
| 0x010       | DBG_GPR0     | RO     | x0 (always 0)                            |
| 0x014       | DBG_GPR1     | RW*    | x1 (ra - return address)                 |
| 0x018       | DBG_GPR2     | RW*    | x2 (sp - stack pointer)                  |
| 0x01C       | DBG_GPR3     | RW*    | x3 (gp - global pointer)                 |
| 0x020       | DBG_GPR4     | RW*    | x4 (tp - thread pointer)                 |
| 0x024-0x038 | DBG_GPR5-9   | RW*    | x5-x9 (t0-t4 - temporaries)              |
| 0x03C-0x044 | DBG_GPR10-11 | RW*    | x10-x11 (a0-a1 - args/return values)     |
| 0x048-0x05C | DBG_GPR12-15 | RW*    | x12-x15 (a2-a5 - arguments)              |
| 0x060-0x074 | DBG_GPR16-19 | RW*    | x16-x19 (a6-a7, s2-s3 - args/saved)      |
| 0x078-0x08C | DBG_GPR20-31 | RW*    | x20-x31 (s4-s11, t3-t6 - saved/temps)    |

*Writable only when CPU is halted

**Register offsets**:

- DBG_GPR[n] is at offset `0x010 + (n * 4)`
- Example: x15 (a5) is at offset 0x010 + (15 * 4) = 0x04C

#### Breakpoint Registers

| Offset | Name         | Access | Reset Value | Description                              |
|:------:|:------------:|:------:|:-----------:|:----------------------------------------:|
| 0x100  | DBG_BP0_ADDR | RW     | 0x0000_0000 | Breakpoint 0 address                     |
| 0x104  | DBG_BP0_CTRL | RW     | 0x0000_0000 | Breakpoint 0 control                     |
| 0x108  | DBG_BP1_ADDR | RW     | 0x0000_0000 | Breakpoint 1 address                     |
| 0x10C  | DBG_BP1_CTRL | RW     | 0x0000_0000 | Breakpoint 1 control                     |

**DBG_BPn_CTRL format**:

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:1  | Reserved   | RO     | Reserved, read as 0                            |
| 0     | ENABLE     | RW     | 1 = Breakpoint enabled, 0 = disabled           |

**Breakpoint behavior**:

- When PC matches `DBG_BPn_ADDR` and `DBG_BPn_CTRL[0] = 1`, CPU halts
- `DBG_STATUS[7:4]` set to indicate which breakpoint triggered
- Instruction at breakpoint address NOT executed before halt

#### Reserved Space

| Offset        | Description                              |
|:-------------:|:----------------------------------------:|
| 0x110-0xFFF   | Reserved for future debug features       |

### GPU Control Registers (APB3 Slave)

**Base address**: 0x2000_1000 (in SoC), local offset 0x000

**Phase**: Phase 4+

#### GPU Core Registers

| Offset | Name             | Access | Reset Value | Description                              |
|:------:|:----------------:|:------:|:-----------:|:----------------------------------------:|
| 0x000  | GPU_CTRL         | RW     | 0x0000_0000 | GPU control                              |
| 0x004  | GPU_STATUS       | RO     | 0x0000_0001 | GPU status                               |
| 0x008  | GPU_KERNEL_ADDR  | RW     | 0x0000_0000 | Kernel start address                     |
| 0x00C  | GPU_GRID_DIM_X   | RW     | 0x0000_0000 | Grid dimension X                         |
| 0x010  | GPU_GRID_DIM_Y   | RW     | 0x0000_0000 | Grid dimension Y                         |
| 0x014  | GPU_GRID_DIM_Z   | RW     | 0x0000_0000 | Grid dimension Z                         |
| 0x018  | GPU_BLOCK_DIM_X  | RW     | 0x0000_0000 | Block dimension X                        |
| 0x01C  | GPU_BLOCK_DIM_Y  | RW     | 0x0000_0000 | Block dimension Y                        |
| 0x020  | GPU_BLOCK_DIM_Z  | RW     | 0x0000_0000 | Block dimension Z                        |
| 0x024  | GPU_WARP_SIZE    | RO     | 0x0000_0008 | Warp size (fixed at 8 in Phase 4)        |
| 0x028  | GPU_NUM_WARPS    | RO     | 0x0000_0004 | Number of warps (implementation-defined) |
| 0x02C  | GPU_PC           | RO     | 0x0000_0000 | Current kernel PC (debug)                |

**GPU_CTRL (0x000)**: GPU Control Register

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:2  | Reserved   | RO     | Reserved, read as 0                            |
| 1     | RESET      | W1     | Write 1 to reset GPU (self-clearing)           |
| 0     | START      | W1     | Write 1 to start kernel (self-clearing)        |

**GPU_STATUS (0x004)**: GPU Status Register

| Bit   | Name       | Access | Description                                    |
|:-----:|:----------:|:------:|:----------------------------------------------:|
| 31:3  | Reserved   | RO     | Reserved, read as 0                            |
| 2     | ERROR      | RO     | 1 = Error occurred                             |
| 1     | DONE       | RO     | 1 = Kernel complete, 0 = not done              |
| 0     | IDLE       | RO     | 1 = GPU idle, 0 = GPU busy                     |

**Kernel launch sequence**:

1. Write `GPU_KERNEL_ADDR` with kernel instruction address
2. Write `GPU_GRID_DIM_*` and `GPU_BLOCK_DIM_*` with dimensions
3. Write `GPU_CTRL[0] = 1` to start execution
4. Poll `GPU_STATUS[1]` or wait for interrupt to detect completion

### Peripheral Registers (Phase 5)

#### UART Registers

**Base address**: 0x2000_2000

| Offset | Name        | Access | Description                              |
|:------:|:-----------:|:------:|:----------------------------------------:|
| 0x000  | UART_TX     | WO     | Transmit data register                   |
| 0x004  | UART_RX     | RO     | Receive data register                    |
| 0x008  | UART_STATUS | RO     | Status register                          |
| 0x00C  | UART_CTRL   | RW     | Control register                         |
| 0x010  | UART_BAUD   | RW     | Baud rate divisor                        |

#### SPI Registers

**Base address**: 0x2000_3000

| Offset | Name        | Access | Description                              |
|:------:|:-----------:|:------:|:----------------------------------------:|
| 0x000  | SPI_TX      | WO     | Transmit data register                   |
| 0x004  | SPI_RX      | RO     | Receive data register                    |
| 0x008  | SPI_STATUS  | RO     | Status register                          |
| 0x00C  | SPI_CTRL    | RW     | Control register                         |
| 0x010  | SPI_CLK_DIV | RW     | Clock divisor                            |
| 0x014  | SPI_CS_CTRL | RW     | Chip select control                      |

#### Timer Registers

**Base address**: 0x2000_4000

| Offset | Name         | Access | Description                              |
|:------:|:------------:|:------:|:----------------------------------------:|
| 0x000  | TMR_COUNTER  | RO     | Current counter value                    |
| 0x004  | TMR_COMPARE  | RW     | Compare value (triggers interrupt)       |
| 0x008  | TMR_CTRL     | RW     | Timer control                            |
| 0x00C  | TMR_PRESCALE | RW     | Clock prescaler                          |

## Reset and Trap Vectors

### Reset Vector

**Address**: 0x0000_0000

**Behavior**: PC loads this address on reset. Typically contains a jump to boot ROM.

**Example boot code**:

```assembly
0x0000_0000:  jal x0, 0x100    # Jump to trap handler setup
```

### Trap Vector

**Address**: 0x0000_0100 (TRAP_VECTOR constant in PHASE0_ARCHITECTURE_SPEC.md)

**Behavior**: PC loads this address on any trap (illegal instruction in Phase 1).

**Example trap handler**:

```assembly
0x0000_0100:  # Trap handler entry
              # Save context
              # Determine trap cause
              # Handle or abort
```

## Address Alignment Requirements

All addresses must be naturally aligned:

| Access Size   | Alignment Requirement | Valid addr[1:0] |
|:-------------:|:---------------------:|:---------------:|
| Byte (8-bit)  | 1-byte aligned        | Any             |
| Half (16-bit) | 2-byte aligned        | 00, 10          |
| Word (32-bit) | 4-byte aligned        | 00              |

**Misaligned accesses**: Phase 1 treats misaligned accesses as illegal instruction traps.

## Memory Access Permissions (Future)

Phase 1 has no memory protection. Future phases may add:

- Read/write/execute permissions
- Privileged vs user mode access
- Memory protection unit (MPU)

## SoC Interconnect (Phase 5)

The SoC uses an AXI4-Lite crossbar to route transactions:

**Masters**:

- CPU AXI4-Lite master
- GPU AXI4-Lite master

**Slaves**:

- Main memory (0x0000_0000 - 0x0FFF_FFFF)
- APB bridge (0x2000_0000 - 0x2FFF_FFFF)
- External memory (0x8000_0000 - 0xFFFF_FFFF)

**APB bridge** converts AXI4-Lite to APB3 for peripherals:

- CPU debug registers
- GPU control registers
- UART, SPI, Timer

## Testing Recommendations

### Address Decode Testing

- Verify all valid addresses return correct data
- Verify invalid addresses return AXI DECERR or APB pslverr
- Test boundary addresses (e.g., 0x0FFF_FFFC, 0x1000_0000)

### Alignment Testing

- Test misaligned accesses trigger traps
- Test all valid alignments work correctly

### Debug Register Testing

- Test halt/resume/step sequences
- Test breakpoint triggers
- Test register read/write when halted
- Test writes ignored when running

## References

- PHASE0_ARCHITECTURE_SPEC.md: Reset and trap behavior
- PHASE1_ARCHITECTURE_SPEC.md: CPU debug interface details
- PHASE4_GPU_ARCHITECTURE_SPEC.md: GPU register specifications
- RTL_DEFINITION.md: Interface signal definitions
