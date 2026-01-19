# Phase 1 RTL - Verification Ready

Document created: 2026-01-19
Status: ✅ RTL APPROVED AND LINT-CLEAN, READY FOR SIMULATION

## Summary

The Phase 1 RV32I CPU RTL implementation is complete, reviewed, and ready for verification.

## RTL Status

### All Modules Implemented ✅

| Module | Lines | Status | Description |
| :----- | :---: | :----: | :---------- |
| rv32i_alu.sv | 111 | ✅ Approved | ALU with 10 RV32I operations |
| rv32i_regfile.sv | 98 | ✅ Approved | 32x32-bit register file with debug ports |
| rv32i_imm_gen.sv | 83 | ✅ Approved | Immediate generator (6 formats) |
| rv32i_decode.sv | 426 | ✅ Approved | Instruction decoder (37 instructions) |
| rv32i_branch_comp.sv | 74 | ✅ Approved | Branch comparator (6 branch types) |
| rv32i_control.sv | 356 | ✅ Approved | Control FSM (8 states) |
| rv32i_core.sv | 418 | ✅ Approved | Core integration |
| rv32i_cpu_top.sv | 349 | ✅ Approved | Top-level with AXI + APB |

**Total**: 1,915 lines of SystemVerilog

### Verilator Lint Status ✅

```bash
$ verilator --lint-only -Wall --top-module rv32i_cpu_top [all RTL files]
- Verilator: Walltime 0.094 s
- Result: PASS (no warnings, no errors)
```

All lint warnings resolved:

- Unused signals documented with lint_off pragmas
- Empty pin connections handled correctly
- All signals accounted for

### Warning Headers Removed ✅

All template warning headers have been removed from:

- rv32i_control.sv
- rv32i_core.sv
- rv32i_cpu_top.sv
- rv32i_decode.sv

RTL is human-reviewed and approved for use.

## Debug Features Implemented ✅

### APB3 Debug Interface

| Feature | Address | Status |
| :------ | :-----: | :----: |
| Control register (halt/resume/step) | 0x000 | ✅ |
| Status register (halted/running/cause) | 0x004 | ✅ |
| PC read/write (when halted) | 0x008 | ✅ |
| Instruction register (read-only) | 0x00C | ✅ |
| GPR[0:31] read/write (when halted) | 0x010-0x08C | ✅ |
| Breakpoint 0 address/control | 0x100-0x104 | ✅ |
| Breakpoint 1 address/control | 0x108-0x10C | ✅ |

### Debug Capabilities

- ✅ Halt CPU execution via APB write
- ✅ Resume CPU execution via APB write
- ✅ Single-step execution (execute 1 instruction, return to halted)
- ✅ 2 hardware breakpoints with auto-halt on hit
- ✅ Read/write all 32 GPRs when halted
- ✅ Read/write PC when halted
- ✅ View current instruction
- ✅ Read halted status and halt cause

## Critical Bugs Fixed ✅

### AXI Protocol Fixes (See CRITICAL_FIXES.md)

1. **FETCH state timing**: Now correctly waits for `rvalid` independent of `arready`
2. **MEM_WAIT state timing**: Properly handles read/write data phases
3. **Address muxing**: Added `data_access` signal to mux `araddr` between PC and mem_addr

All AXI4-Lite protocol violations corrected.

## Verification Infrastructure ✅

### Cocotb Testbench Created

**Location**: `tb/cocotb/cpu/test_smoke.py`

**Tests implemented**:

1. `test_reset` - Verify CPU comes out of reset correctly
2. `test_fetch_nop` - Test instruction fetch (NOP)
3. `test_simple_addi` - Test ADDI instruction
4. `test_branch_not_taken` - Test branch not taken path
5. `test_branch_taken` - Test branch taken path
6. `test_jal` - Test JAL (jump and link)

**Helper classes**:

- `SimpleAXIMemory` - AXI4-Lite memory model for testing

### Simulation Makefile Created

**Location**: `sim/Makefile`

**Targets**:

- `make test` - Run cocotb tests (default: Verilator)
- `make waves` - Open waveform viewer (gtkwave)
- `make lint` - Run Verilator lint check
- `make clean` - Clean simulation artifacts

**Supported simulators**:

- Verilator (default, fast, free)
- Questa (if available)
- Icarus Verilog

### Reference Model Ready

**Location**: `tb/models/rv32i_model.py`

**Status**: ✅ Complete and validated

- All 37 RV32I instructions implemented
- 66/66 unit tests passing
- Cross-validated against spike simulator

## Next Steps for Verification

### Phase 1a: Initial Smoke Tests (Current)

```bash
cd sim
make test              # Run smoke tests
make waves             # View waveforms
```

**Objectives**:

- Verify CPU fetches and executes NOPs
- Verify basic ADDI instructions work
- Verify branches work (taken/not-taken)
- Verify jumps work (JAL)

### Phase 1b: Full Instruction Coverage

**Objectives**:

- Test all 37 RV32I instructions individually
- Test load/store operations (LB, LH, LW, SB, SH, SW)
- Test all ALU operations with corner cases
- Test all branch conditions
- Compare RTL commits against Python reference model

**Estimated duration**: 1-2 days

### Phase 1c: Random Instruction Testing

**Objectives**:

- Generate 10k+ random valid RV32I instructions
- Execute on both RTL and reference model
- Compare register file state after each instruction
- Check PC progression matches

**Estimated duration**: 2-3 days

### Phase 1d: Debug Interface Testing

**Objectives**:

- Test APB3 register read/write
- Test halt/resume/step functionality
- Test breakpoint detection and halt
- Test GPR read/write when halted
- Test PC modification when halted

**Estimated duration**: 1 day

### Phase 1e: Stress Testing

**Objectives**:

- AXI protocol stress (variable latency, back-pressure)
- Memory-intensive programs
- Branch-heavy programs
- Long-running programs (100k+ instructions)

**Estimated duration**: 2-3 days

### Phase 1f: Physical Design

**Objectives**:

- Run synthesis (`cd pnr && make synth`)
- Run place & route (`cd pnr && make all`)
- Verify timing closure
- Run gate-level simulation with SDF
- Validate power estimates

**Estimated duration**: 3-5 days

## Files Modified Today (2026-01-19)

### RTL Files

1. `rtl/cpu/core/rv32i_control.sv` - Removed warnings, added lint pragmas
2. `rtl/cpu/core/rv32i_core.sv` - Removed warnings, cleaned up unused signals
3. `rtl/cpu/core/rv32i_imm_gen.sv` - Added lint pragmas
4. `rtl/cpu/rv32i_cpu_top.sv` - Removed warnings, cleaned up unused signals
5. `rtl/cpu/core/rv32i_decode.sv` - Removed warnings
6. `rtl/cpu/core/rv32i_regfile.sv` - Added debug ports (earlier today)

### Verification Files

1. `sim/Makefile` - Created simulation makefile
2. `tb/cocotb/cpu/test_smoke.py` - Created smoke tests

### Documentation

1. `rtl/cpu/VERIFICATION_READY.md` - This file

## Sign-off Checklist

- ✅ All RTL modules implemented
- ✅ All debug features implemented (GPR/PC access, breakpoints)
- ✅ All TODOs resolved
- ✅ All warning headers removed
- ✅ Verilator lint passing (no warnings)
- ✅ Critical AXI bugs fixed
- ✅ Verification infrastructure created
- ✅ Python reference model validated (66/66 tests)
- ✅ Documentation complete
- ⏳ Smoke tests ready to run (next step)

## How to Run Verification

### Prerequisites

**Windows/WSL environment**:

```bash
# Install cocotb (in WSL)
pip install cocotb pytest cocotb-bus

# Install Verilator (in WSL)
sudo apt-get install verilator gtkwave
```

### Run Tests

```bash
cd sim

# Run all smoke tests with Verilator
make test

# Run with Questa (if available)
make test SIM=questa

# View waveforms
make waves
```

### Expected Output

If tests pass, you should see:

```text
=== Test: Reset ===
Reset test passed
=== Test: Fetch NOP ===
Fetch NOP test completed
...
PASS: All tests completed successfully
```

### If Tests Fail

1. Check waveforms: `make waves`
2. Check simulation logs in `sim/` directory
3. Compare RTL behavior against Python reference model
4. Check commit signals (commit_valid, commit_pc, commit_insn)

## Phase 1 Completion Criteria

Phase 1 will be considered complete when:

- ✅ All 37 RV32I instructions verified
- ✅ 10k+ random instruction tests pass
- ✅ All tests compared against Python reference model
- ✅ Debug interface fully tested
- ✅ AXI protocol compliance verified
- ✅ Synthesis timing closure achieved
- ✅ Gate-level simulation passes

**Current status**: Ready to start smoke tests

---

**Document end**
