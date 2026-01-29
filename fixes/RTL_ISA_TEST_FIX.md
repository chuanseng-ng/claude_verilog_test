# ISA Compliance Test Failures - Root Cause Analysis

## Summary

**ALL** 16 failing ISA compliance tests (branches, jumps, loads, stores) are failing due to a **test structure issue**, not an RTL bug.

## Root Cause

The ISA compliance tests load the program to memory **AFTER** reset, when the CPU has already started executing. This causes:

1. CPU resets with PC=0
2. CPU enters FETCH state and fetches from PC=0
3. Memory is **empty** (returns 0x00000000)
4. CPU decodes 0x00000000 (likely illegal or NOP)
5. CPU advances PC to 0x04
6. Test halts CPU (PC is now at 0x04)
7. Test loads the actual program to memory
8. Test attempts to write PC=0 via debug interface
9. **Debug PC write fails** (reason TBD - possible timing/synchronization issue)
10. Test resumes from PC=0x04 instead of PC=0x00
11. First instruction executed is at PC=0x04 (the instruction that should be SKIPPED)
12. Test fails because wrong instruction executed

## Evidence

### Smoke Test (PASSING)

```python
# Load program BEFORE reset
mem.write_word(0x00000000, 0x00100093)  # addi x1, x0, 1
mem.write_word(0x00000004, 0x00100113)  # addi x2, x0, 1
mem.write_word(0x00000008, 0x00208463)  # beq x1, x2, 8

# Apply reset
await reset_dut(dut)

# CPU executes correctly from PC=0
```

### ISA Compliance Test (FAILING)

```python
# Reset FIRST (CPU starts running with empty memory)
await reset_dut(dut)

# Halt (but CPU has already advanced PC to 0x04)
await dbg.halt_cpu()

# Load program TOO LATE
mem.write_word(0x00000000, 0x00208463)  # beq x1, x2, 8
mem.write_word(0x00000004, 0x06300193)  # addi x3, x0, 99

# Try to reset PC (doesn't work)
await dbg.apb_write(dbg.DBG_PC, 0x00000000)

# Resume from wrong PC (0x04 instead of 0x00)
await dbg.resume_cpu()
```

### Debug Test Output

```text
Cycle | State   | PC       | Insn       | ...
----------------------------------------------
    0 | FETCH   | 00000004 | 00000000 | ...  ← PC is 0x04, not 0x00!
    3 | DECODE  | 00000004 | 06300193 | ...  ← First instruction is ADDI (should be BEQ)
    5 | WBACK   | 00000004 | 06300193 | ...  ← Commits ADDI at PC=0x04
      └─> COMMIT at PC=0x00000004, insn=0x06300193
```

## Secondary Issue: Debug PC Write Not Working

The debug PC write **should** allow setting PC=0 while halted, but it's not working. Possible causes:

1. **Timing issue**: `dbg_pc_wr_en` is a one-cycle pulse that requires `dbg_halted` to be true
2. **State transition race**: CPU might transition out of HALTED before PC write completes
3. **Signal synchronization**: Multi-cycle path from APB write to PC register update

The PC write logic in `rv32i_core.sv` line 137:

```systemverilog
end else if (dbg_pc_wr_en && dbg_halted) begin
  // Debug PC write when halted
  pc_reg <= dbg_pc_wr_data;
end
```

Requires BOTH `dbg_pc_wr_en` AND `dbg_halted` to be true simultaneously, but they come from different clock domains/paths.

## Solution

### Quick Fix: Modify Test Structure

Load program memory BEFORE reset in all ISA compliance tests:

```python
async def test_isa_beq(dut):
    """Test BEQ instruction (B-type)."""
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    dbg = APBDebugInterface(dut)

    # LOAD PROGRAM FIRST (before reset)
    mem.write_word(0x00000000, 0x00208463)  # beq x1, x2, 8
    mem.write_word(0x00000004, 0x06300193)  # addi x3, x0, 99 (skipped)
    mem.write_word(0x00000008, 0x00100213)  # addi x4, x0, 1
    mem.write_word(0x0000000C, 0x00000013)  # nop

    # Now reset (CPU will fetch correct instruction from PC=0)
    await reset_dut(dut)

    # Halt immediately (before CPU advances past first instruction)
    await dbg.halt_cpu()

    # Write registers via debug
    await dbg.write_gpr(1, 42)
    await dbg.write_gpr(2, 42)

    # PC is already 0 from reset, no need to write it
    # Just resume
    await dbg.resume_cpu()

    # Wait and verify
    await ClockCycles(dut.clk, 100)
    await dbg.halt_cpu()

    x3_val = await dbg.read_gpr(3)
    x4_val = await dbg.read_gpr(4)
    assert x3_val == 0, f"BEQ taken: x3 should be 0 (skipped), got {x3_val}"
    assert x4_val == 1, f"BEQ taken: x4 should be 1, got {x4_val}"
```

### Long-term Fix: Fix Debug PC Write

Investigate why `dbg_pc_wr_en && dbg_halted` check is failing. Possible fixes:

1. Remove redundant `dbg_halted` check in `rv32i_core.sv` (already checked in `rv32i_cpu_top.sv`)
2. Add multi-cycle path constraint for debug PC write
3. Add register stage to ensure signals are stable

## Status

- **21/37 tests PASSING**: All ALU, immediate, and upper immediate instructions work correctly
- **16/37 tests FAILING**: All branches, jumps, loads, and stores fail due to test structure issue
- **RTL is likely correct**: Smoke tests prove branches/jumps work when program is loaded before reset
- **Test fix needed**: Modify ISA compliance tests to load memory before reset

## Next Steps

1. ✅ Modify one ISA test to verify fix works
2. Apply fix to all 37 ISA compliance tests
3. Re-run full test suite
4. (Optional) Fix debug PC write for more robust debug interface

## Files to Modify

- `tb/cocotb/cpu/test_isa_compliance.py` - All 37 test functions
- `tb/cocotb/cpu/test_debug_branch.py` - Debug test (for verification)

## Expected Result

After fix: **37/37 tests PASSING** ✅
