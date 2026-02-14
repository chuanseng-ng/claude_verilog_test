# Phase 1 RTL Integration Summary

Document created: 2026-01-19
Status: Control and integration structure created - REQUIRES HUMAN REVIEW

## Overview

This document summarizes the RTL integration structure for Phase 1 RV32I CPU, including where `rv32i_branch_comp.sv` is integrated and the overall module hierarchy.

## Module Hierarchy

```text
rv32i_cpu_top.sv (Top-level)
    ├── rv32i_core.sv (Core integration)
    │   ├── rv32i_decode.sv ✅ (Decoder - approved)
    │   ├── rv32i_imm_gen.sv ✅ (Immediate generator - quality verified)
    │   ├── rv32i_regfile.sv ✅ (Register file - quality verified)
    │   ├── rv32i_alu.sv ✅ (ALU - quality verified)
    │   ├── rv32i_branch_comp.sv ✅ (Branch comparator - quality verified)
    │   └── rv32i_control.sv ⚠️ (Control FSM - NEEDS HUMAN REVIEW)
    └── APB3 debug interface ⚠️ (NEEDS HUMAN REVIEW)
```

## Branch Comparator Integration

### Location

`rv32i_branch_comp.sv` is instantiated in **`rv32i_core.sv`** at line 245.

### Connections

**Inputs**:

- `rs1_data` - Source register 1 data from register file (read port 1)
- `rs2_data` - Source register 2 data from register file (read port 2)
- `branch_op` - Branch operation type from decoder (3-bit funct3 field)

**Output**:

- `branch_taken` - Branch condition result (1 = taken, 0 = not taken)

### Dataflow

```text
Register File (rs1_data, rs2_data)
        |
        ├────────────────┐
        │                │
        v                v
    rv32i_alu      rv32i_branch_comp
        │                │
        │                v
        │          branch_taken
        │                │
        │                v
        └───────> rv32i_control (FSM)
                       │
                       v
                  PC update logic
```

### Usage in Control FSM

The `branch_taken` signal is used by the control FSM (`rv32i_control.sv`) to determine PC updates:

1. **EXECUTE state**: Branch comparator evaluates condition in parallel with ALU
2. **WRITEBACK state**: If `branch && branch_taken`, PC updates to branch target
3. **PC update**: `pc_next = pc_reg + immediate` (branch offset from immediate generator)

### Timing

- **Combinational logic**: Branch comparator evaluates condition in the same cycle as ALU operation
- **No additional latency**: Branch decision available immediately for PC update
- **Single-cycle branches**: Branch taken/not-taken resolved in one cycle

## Created RTL Structure

### rv32i_control.sv (Control FSM)

**Status**: ⚠️ REQUIRES HUMAN REVIEW

**Purpose**: State machine for single-cycle CPU with AXI stalls

**States**:

- `RESET` - Initialize CPU
- `FETCH` - Instruction fetch via AXI read
- `DECODE` - Instruction decode
- `EXECUTE` - Execute (ALU/branch evaluation)
- `MEM_WAIT` - Wait for AXI memory transaction
- `WRITEBACK` - Register writeback and commit
- `TRAP` - Trap handling (illegal instruction)
- `HALTED` - Debug halt state

**Key Features**:

- AXI handshake management (arvalid/arready, rvalid/rready, etc.)
- Branch/jump PC update control
- Debug halt/resume/step support
- Commit signal generation
- Trap detection and handling

**Human Review Required**:

1. ✓ State transition logic correctness
2. ✓ AXI protocol compliance
3. ✓ Commit signal timing
4. ✓ Trap handling completeness
5. ✓ Debug interface behavior

### rv32i_core.sv (Core Integration)

**Status**: ⚠️ REQUIRES HUMAN REVIEW

**Purpose**: Integrates all datapath and control components

**Key Datapath Elements**:

- **Program Counter (PC)**: 32-bit register with reset to 0x0000_0000
- **Instruction Register**: Latches instruction from AXI read data
- **ALU Operand Muxes**:
  - Operand A: rs1_data or PC (for AUIPC)
  - Operand B: rs2_data or immediate
- **Register Write Data Mux**:
  - ALU result (arithmetic/logic)
  - Memory data (loads)
  - PC+4 (JAL/JALR)

**Memory Interface**:

- Load data extraction with sign/zero extension
- Store data byte enable generation (wstrb)
- Address calculation (rs1 + immediate)

**Human Review Required**:

1. ✓ Datapath connectivity correctness
2. ✓ Mux selection logic
3. ✓ PC update logic (PC+4, branch target, jump target)
4. ✓ Memory interface byte alignment
5. ✓ Register forwarding (if needed)

### rv32i_cpu_top.sv (Top-Level)

**Status**: ⚠️ REQUIRES HUMAN REVIEW

**Purpose**: Top-level integration with external interfaces

**Components**:

- `rv32i_core` instance (CPU core)
- APB3 debug interface (register map implementation)
- Breakpoint logic (2 hardware breakpoints)

**Debug Registers** (APB3):

- `0x000` DBG_CTRL - Control register (halt/resume/step/reset)
- `0x004` DBG_STATUS - Status register (halted/running/halt_cause)
- `0x008` DBG_PC - Program counter (read-only in Phase 1)
- `0x00C` DBG_INSTR - Current instruction (read-only)
- `0x100-0x10C` - Breakpoint registers (BP0, BP1)

**Missing Functionality** (to be implemented):

1. GPR read/write access via APB3 (requires register file modification)
2. PC write access when halted (requires core modification)
3. Breakpoint hit integration with halt logic

**Human Review Required**:

1. ✓ APB3 protocol compliance
2. ✓ Debug register map implementation
3. ✓ Breakpoint logic correctness
4. ✓ Debug control signal generation
5. ✓ Integration with core debug interface

## File Locations

```text
rtl/cpu/
├── rv32i_cpu_top.sv          ⚠️ NEEDS REVIEW (top-level integration)
└── core/
    ├── rv32i_alu.sv          ✅ QUALITY VERIFIED
    ├── rv32i_branch_comp.sv  ✅ QUALITY VERIFIED
    ├── rv32i_control.sv      ⚠️ NEEDS REVIEW (control FSM)
    ├── rv32i_core.sv         ⚠️ NEEDS REVIEW (core integration)
    ├── rv32i_decode.sv       ✅ APPROVED
    ├── rv32i_imm_gen.sv      ✅ QUALITY VERIFIED
    └── rv32i_regfile.sv      ✅ QUALITY VERIFIED
```

## Next Steps for Human Review

### 1. Control FSM Review (`rv32i_control.sv`)

**Review checklist**:

- [ ] State transitions cover all instruction types
- [ ] AXI handshake logic is correct (no protocol violations)
- [ ] Commit signal asserts for exactly 1 cycle
- [ ] Trap handling updates PC correctly
- [ ] Debug halt/resume/step works as specified
- [ ] Branch/jump PC updates are correct

**Testing approach**:

- Write cocotb testbench for FSM
- Test state transitions with directed tests
- Test AXI back-pressure scenarios
- Test debug halt/resume sequences

### 2. Core Integration Review (`rv32i_core.sv`)

**Review checklist**:

- [ ] All module instantiations have correct port connections
- [ ] PC update logic handles all cases (PC+4, branch, jump, JALR)
- [ ] ALU operand muxes select correct sources
- [ ] Register write data mux handles all cases
- [ ] Memory interface byte alignment is correct
- [ ] Load sign/zero extension is correct

**Testing approach**:

- Run smoke tests (simple ADD, branch, load/store)
- Test all 37 RV32I instructions
- Test branch taken/not-taken paths
- Test JAL/JALR with various targets
- Test memory operations with different alignments

### 3. Top-Level Integration Review (`rv32i_cpu_top.sv`)

**Review checklist**:

- [ ] Core instantiation is correct
- [ ] APB3 read/write logic follows protocol
- [ ] Debug register map matches MEMORY_MAP.md
- [ ] Breakpoint detection logic is correct
- [ ] Debug control signals are generated correctly

**Testing approach**:

- Test APB3 register read/write
- Test debug halt and check status
- Test breakpoint hit detection
- Test single-step execution

## Integration Quality Summary

| Module | Status | Lines | Complexity | Review Priority |
| :----: | :----: | :---: | :--------: | :-------------: |
| rv32i_decode.sv | ✅ Approved | 426 | High | N/A (done) |
| rv32i_imm_gen.sv | ✅ Verified | 83 | Low | Low |
| rv32i_regfile.sv | ✅ Verified | 79 | Low | Low |
| rv32i_alu.sv | ✅ Verified | 111 | Medium | Low |
| rv32i_branch_comp.sv | ✅ Verified | 74 | Low | Low |
| **rv32i_control.sv** | ⚠️ Needs Review | 350+ | **Very High** | **CRITICAL** |
| **rv32i_core.sv** | ⚠️ Needs Review | 450+ | **High** | **HIGH** |
| **rv32i_cpu_top.sv** | ⚠️ Needs Review | 350+ | **High** | **MEDIUM** |

## Recommendations

### Immediate Actions

1. **Human review of `rv32i_control.sv`** - CRITICAL
   - This is the most complex module
   - FSM state transitions must be verified carefully
   - AXI protocol compliance must be validated

2. **Human review of `rv32i_core.sv`** - HIGH PRIORITY
   - Datapath connectivity is critical for correctness
   - PC update logic must handle all cases
   - Memory interface must be byte-accurate

3. **Create unit tests for each module**
   - Test control FSM state transitions
   - Test core integration with simple instructions
   - Test top-level with APB3 debug access

### Verification Strategy

**Phase 1a: Module-level verification**

- Unit test each module independently
- Focus on `rv32i_control.sv` FSM first
- Use cocotb for testbenches

**Phase 1b: Integration verification**

- Test `rv32i_core.sv` with simple instruction sequences
- Compare commits with Python reference model
- Validate all 37 RV32I instructions

**Phase 1c: System verification**

- Test full `rv32i_cpu_top.sv` with debug interface
- Run 10k+ random instruction tests
- Validate AXI protocol compliance
- Test debug features (halt/resume/breakpoints)

**Phase 1d: Physical design**

- Run synthesis (`make synth`)
- Run place & route (`make all`)
- Verify timing closure
- Run gate-level simulation

## Key Integration Points

### 1. Branch Comparator → Control FSM

**Signal**: `branch_taken`
**Source**: `rv32i_branch_comp.sv`
**Destination**: `rv32i_control.sv`
**Purpose**: Determines if branch instruction should update PC to target

### 2. Decoder → All Modules

**Signals**: Multiple control signals (alu_op, mem_rd, mem_wr, etc.)
**Source**: `rv32i_decode.sv`
**Destinations**: ALU, control FSM, memory interface
**Purpose**: Drives entire datapath based on instruction decode

### 3. Register File → ALU & Branch Comparator

**Signals**: `rs1_data`, `rs2_data`
**Source**: `rv32i_regfile.sv`
**Destinations**: `rv32i_alu.sv`, `rv32i_branch_comp.sv`
**Purpose**: Provides operands for execution

### 4. Control FSM → All Modules

**Signals**: `pc_wr_en`, `regfile_wr_en`, `commit_valid`, etc.
**Source**: `rv32i_control.sv`
**Destinations**: PC register, register file, commit interface
**Purpose**: Orchestrates pipeline execution

## Conclusion

The control and integration RTL structure has been created for Phase 1. The branch comparator (`rv32i_branch_comp.sv`) is correctly integrated into the core at the EXECUTE stage, providing branch condition evaluation in parallel with ALU operations.

**Critical path for completion**:

1. Human review and approval of `rv32i_control.sv` (CRITICAL)
2. Human review and approval of `rv32i_core.sv` (HIGH)
3. Human review and approval of `rv32i_cpu_top.sv` (MEDIUM)
4. Unit testing of each module
5. Integration testing with reference model
6. System-level testing with debug interface
7. Physical design flow (synthesis, P&R, STA)

**All created modules are templates that REQUIRE HUMAN REVIEW before simulation/synthesis.**
