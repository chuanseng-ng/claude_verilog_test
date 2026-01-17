# Phase 1 Architecture Specification

RV32I Single-Cycle CPU with System Interfaces

Document status: Draft (Phase-1)
Target audience: RTL implementation, integration, verification
Compliance reference: Phase 0 Architecture Specification

**Prerequisites**: Phase 0 must be complete (specifications finalized, Python reference model implemented)

## Overview

Phase 1 implements the RV32I CPU core specified in Phase 0 with additional system interfaces:

- AXI4-Lite master for memory access (unified instruction/data)
- APB3 slave for debug/control registers
- Observable commit signals for verification

This specification defines the RTL implementation requirements beyond the architectural
specification in PHASE0_ARCHITECTURE_SPEC.md.

## Microarchitecture

### Pipeline organization

**Single-cycle execution with AXI stalls**

Stages:

1. **FETCH**: Instruction fetch via AXI4-Lite
2. **DECODE**: Instruction decode and register read
3. **EXECUTE**: ALU operation or address calculation
4. **MEMORY**: Load/store via AXI4-Lite (if applicable)
5. **WRITEBACK**: Register write

Timing:

- One instruction retires per cycle (when not stalled)
- AXI transactions may stall pipeline
- No instruction overlap (true single-cycle)

### State machine

The CPU control FSM has the following states:

```text
RESET       → FETCH
FETCH       → DECODE (when AXI read completes)
DECODE      → EXECUTE
EXECUTE     → MEM_WAIT (for loads/stores)
EXECUTE     → WRITEBACK (for non-memory instructions)
MEM_WAIT    → WRITEBACK (when AXI transaction completes)
WRITEBACK   → FETCH
TRAP        → FETCH (traps handled immediately, PC updated to TRAP_VECTOR)
```

Debug states (APB3 controlled):

```text
Any state   → HALTED (when halt requested via APB3)
HALTED      → FETCH (when resume requested via APB3)
HALTED      → FETCH (single-step: execute 1 instruction then return to HALTED)
```

### RTL module hierarchy

```text
rv32i_cpu_top              # Top-level integration
├── rv32i_core             # CPU core wrapper
│   ├── rv32i_control      # FSM and control logic
│   ├── rv32i_decode       # Instruction decoder
│   ├── rv32i_alu          # ALU (all RV32I operations)
│   ├── rv32i_regfile      # 32x32-bit register file
│   └── rv32i_imm_gen      # Immediate generator
├── axi4lite_master        # AXI4-Lite master interface
├── apb3_slave             # APB3 slave for debug
└── rv32i_debug            # Debug controller (breakpoints)
```

### Module interfaces

#### rv32i_cpu_top (top-level)

```systemverilog
module rv32i_cpu_top (
    // Clock and reset
    input  logic        clk,
    input  logic        rst_n,

    // AXI4-Lite master (unified instruction/data)
    // Write address channel
    output logic [31:0] axi_awaddr,
    output logic        axi_awvalid,
    input  logic        axi_awready,

    // Write data channel
    output logic [31:0] axi_wdata,
    output logic [3:0]  axi_wstrb,
    output logic        axi_wvalid,
    input  logic        axi_wready,

    // Write response channel
    input  logic [1:0]  axi_bresp,
    input  logic        axi_bvalid,
    output logic        axi_bready,

    // Read address channel
    output logic [31:0] axi_araddr,
    output logic        axi_arvalid,
    input  logic        axi_arready,

    // Read data channel
    input  logic [31:0] axi_rdata,
    input  logic [1:0]  axi_rresp,
    input  logic        axi_rvalid,
    output logic        axi_rready,

    // APB3 slave (debug/control)
    input  logic [11:0] apb_paddr,
    input  logic        apb_psel,
    input  logic        apb_penable,
    input  logic        apb_pwrite,
    input  logic [31:0] apb_pwdata,
    output logic [31:0] apb_prdata,
    output logic        apb_pready,
    output logic        apb_pslverr,

    // Commit interface (verification observability)
    output logic        commit_valid,
    output logic [31:0] commit_pc,
    output logic [31:0] commit_insn,
    output logic        trap_taken,
    output logic [3:0]  trap_cause
);
```

## System interfaces

### AXI4-Lite master interface

**Protocol**: AMBA AXI4-Lite (ARM IHI 0022E)

**Configuration**:

- Address width: 32 bits
- Data width: 32 bits
- No burst support (AXI-Lite restriction)
- No exclusive access
- No cache/QoS/region signals

**Usage**:

- Unified interface for instruction fetch and data access
- Instruction fetch: Read transaction to PC address
- Load: Read transaction to calculated address
- Store: Write transaction to calculated address

**Transaction ordering**:

- Sequential consistency maintained
- One outstanding transaction at a time
- No transaction reordering

**Error handling**:

- `axi_rresp != 2'b00` on read → illegal instruction trap
- `axi_bresp != 2'b00` on write → illegal instruction trap
- Slave error treated as illegal instruction (Phase 1 limitation)

**Byte lane strobes** (`axi_wstrb`):

| Instruction | Address[1:0] | wstrb   | Description         |
|:-----------:|:------------:|:-------:|:-------------------:|
| SB          | 2'b00        | 4'b0001 | Store byte 0        |
| SB          | 2'b01        | 4'b0010 | Store byte 1        |
| SB          | 2'b10        | 4'b0100 | Store byte 2        |
| SB          | 2'b11        | 4'b1000 | Store byte 3        |
| SH          | 2'b00        | 4'b0011 | Store halfword 0    |
| SH          | 2'b10        | 4'b1100 | Store halfword 1    |
| SW          | 2'b00        | 4'b1111 | Store word          |

**Load data extraction**: The CPU must extract the correct bytes from `axi_rdata`
based on the load instruction and address alignment.

### APB3 slave interface (debug)

**Protocol**: AMBA APB3 (ARM IHI 0024C)

**Configuration**:

- Address width: 12 bits (4KB address space)
- Data width: 32 bits
- Single-cycle reads/writes (pready always high when selected)

**Address map**: See MEMORY_MAP.md for complete debug register map

**Key registers**:

| Address     | Register       | Access | Description                                      |
|:-----------:|:--------------:|:------:|:------------------------------------------------:|
| 0x000       | DBG_CTRL       | RW     | [0]=halt, [1]=resume, [2]=step, [3]=reset        |
| 0x004       | DBG_STATUS     | RO     | [0]=halted, [1]=running, [7:4]=halt_cause        |
| 0x008       | DBG_PC         | RW     | Program counter (writable when halted)           |
| 0x00C       | DBG_INSTR      | RO     | Current instruction word                         |
| 0x010-0x08C | DBG_GPR[0:31]  | RW     | General purpose registers (writable when halted) |
| 0x100       | DBG_BP0_ADDR   | RW     | Breakpoint 0 address                             |
| 0x104       | DBG_BP0_CTRL   | RW     | [0]=enable                                       |
| 0x108       | DBG_BP1_ADDR   | RW     | Breakpoint 1 address                             |
| 0x10C       | DBG_BP1_CTRL   | RW     | [0]=enable                                       |

**Debug operations**:

**Halt**:

1. Write `DBG_CTRL[0] = 1`
2. CPU transitions to HALTED state at next safe point
3. `DBG_STATUS[0]` reads as `1` when halted

**Resume**:

1. Write `DBG_CTRL[1] = 1`
2. CPU transitions to FETCH state
3. `DBG_STATUS[1]` reads as `1` when running

**Single-step**:

1. While halted, write `DBG_CTRL[2] = 1`
2. CPU executes one instruction and returns to HALTED
3. Useful for instruction-by-instruction debugging

**Register access**:

- GPRs and PC writable only when CPU is halted
- Writes ignored when CPU is running
- `DBG_INSTR` always reflects the current instruction fetch

**Breakpoints**:

- 2 hardware breakpoints (address match)
- When PC matches enabled breakpoint, CPU halts
- `DBG_STATUS[7:4]` indicates halt cause:
  - `4'b0001`: Debug halt request
  - `4'b0010`: Breakpoint 0 hit
  - `4'b0011`: Breakpoint 1 hit
  - `4'b0100`: Single-step complete
  - `4'b1000`: EBREAK instruction

### Commit interface (verification)

**Purpose**: Observable commit signals for testbench scoreboard comparison

**Signals**:

```systemverilog
output logic        commit_valid,   // High for 1 cycle when instruction commits
output logic [31:0] commit_pc,      // PC of committed instruction
output logic [31:0] commit_insn,    // 32-bit instruction word
output logic        trap_taken,     // High for 1 cycle when trap taken
output logic [3:0]  trap_cause      // Encoded trap reason
```

**Behavior**:

- `commit_valid` asserts for exactly 1 cycle when instruction completes
- No commit on trapped instruction (trap_taken asserts instead)
- Scoreboard compares {commit_pc, commit_insn} with reference model

**Trap causes**:

- `4'b0001`: Illegal instruction
- `4'b0010`: (Reserved for future use)
- Others: Reserved

## RTL coding guidelines

### Language

- SystemVerilog IEEE 1800-2017
- Synthesizable subset only
- No SystemVerilog assertions in RTL (use in testbench only)

### Style

- 2-space indentation
- snake_case for signals and modules
- ALL_CAPS for parameters and constants
- Registered outputs preferred
- Avoid latches (all case statements must have default)
- Avoid combinational loops

### Resets

- Active-low synchronous reset (`rst_n`)
- All sequential elements must reset to known state
- Reset values must match PHASE0_ARCHITECTURE_SPEC.md requirements

### Clocking

- Single clock domain (`clk`)
- All flops triggered on positive edge
- No clock gating in Phase 1

### Interfaces

- Use `logic` for all signals (not `wire` or `reg`)
- Explicit port directions
- Group related signals with comments

## AI/Human responsibility boundaries

### AI MAY assist with

- Module scaffolding (ports, parameters)
- Register file implementation (with x0 = 0 constraint)
- ALU implementation (given truth tables)
- Immediate generator (given RV32I encoding)
- AXI4-Lite state machine boilerplate
- APB3 slave register read/write logic
- Testbench cocotb drivers

### AI MUST NOT decide

- Control FSM state transitions (human must approve)
- Trap handling logic (must match Phase 0 spec exactly)
- Debug halt/resume semantics
- AXI transaction ordering
- Reset behavior
- Commit signal timing

### Human MUST review

- All control FSM code
- Decoder truth tables for completeness
- AXI/APB protocol compliance
- Reset initialization
- Commit interface correctness

## Verification requirements (Phase 1)

### Testbench architecture

- cocotb for clock/reset/interface drivers
- pyuvm for sequences and scoreboards
- Python reference model (from Phase 0)

### Required tests

1. **Smoke test**: Simple ADD/SUB sequence
2. **ISA coverage**: All 37 RV32I instructions
3. **Random instruction streams**: 10k+ instructions
4. **Debug interface**: Halt/resume/step/breakpoint tests
5. **AXI protocol**: Handshake, error response
6. **Trap handling**: Illegal instruction detection

### Exit criteria

- 100% RV32I instruction coverage (37 instructions)
- Pass 10,000+ random instruction tests with zero failures
- Pass all directed debug interface tests
- Zero known failing test seeds
- All commits match Python reference model

## Known limitations (Phase 1)

The following are known limitations that will be addressed in later phases:

1. **No interrupts**: Interrupt support deferred to Phase 2+
2. **No CSRs**: CSR instructions treated as illegal
3. **No FENCE**: FENCE/FENCE.I treated as illegal
4. **No performance counters**: Added in later phases
5. **Single outstanding transaction**: Only one AXI transaction at a time
6. **Trap handling limited**: Only illegal instruction trap supported

## File organization

```text
rtl/
├── cpu/
│   ├── rv32i_cpu_top.sv       # Top-level integration
│   └── core/
│       ├── rv32i_core.sv      # Core wrapper
│       ├── rv32i_control.sv   # Control FSM
│       ├── rv32i_decode.sv    # Decoder
│       ├── rv32i_alu.sv       # ALU
│       ├── rv32i_regfile.sv   # Register file
│       └── rv32i_imm_gen.sv   # Immediate generator
├── interfaces/
│   ├── axi4lite_master.sv     # AXI4-Lite master
│   └── apb3_slave.sv          # APB3 slave
└── debug/
    └── rv32i_debug.sv         # Debug controller

tb/
├── cocotb/
│   ├── tb_rv32i_cpu_top.py    # Top-level testbench
│   ├── axi4lite_slave.py      # AXI4-Lite memory model
│   └── apb3_master.py         # APB3 debug driver
└── pyuvm/
    ├── env.py                 # UVM environment
    ├── sequences/             # Test sequences
    └── scoreboard/            # Reference model comparison
```

## References

- PHASE0_ARCHITECTURE_SPEC.md: Architectural requirements
- RTL_DEFINITION.md: System-level interface definitions
- MEMORY_MAP.md: Complete address map
- REFERENCE_MODEL_SPEC.md: Python reference model API
- VERIFICATION_PLAN.md: Phase 1 verification strategy
- RISC-V ISA Manual Volume I: RV32I Base Integer Instruction Set
- AMBA AXI4-Lite Protocol Specification (ARM IHI 0022E)
- AMBA APB3 Protocol Specification (ARM IHI 0024C)
