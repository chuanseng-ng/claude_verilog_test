# EBREAK Halt Bug Fix

**Date**: 2026-01-28
**Issue**: EBREAK instruction does not properly set halt cause in status register
**Status**: FIXED

---

## Problem Description

The EBREAK instruction (0x00100073) **does cause the CPU to halt**, but the halt **cause code** in the debug status register is reported incorrectly (shows 0x0 instead of 0x8).

---

## Root Cause

### The Bug (rv32i_cpu_top.sv:325-340)

The original `ebreak_halt` flag detection logic was:

```systemverilog
if (commit_valid && (commit_insn == 32'h00100073) && !dbg_halted) begin
  ebreak_halt <= 1'b1;
end
```

### Why This Failed

1. **EBREAK execution path**: EXECUTE → HALTED (skips WRITEBACK)
2. **commit_valid** is only asserted in WRITEBACK state (rv32i_control.sv:363)
3. **Result**: EBREAK never commits, so `commit_valid` is never true for EBREAK
4. **Consequence**: `ebreak_halt` flag never gets set

### What Actually Happened

```
State Machine Behavior:
  FETCH    → Fetches EBREAK (0x00100073)
  DECODE   → Sets ebreak = 1
  EXECUTE  → Sees ebreak=1, transitions to HALTED (skips WRITEBACK!)
  HALTED   → dbg_halted = 1, but ebreak_halt = 0 ❌

Status Register (bits [7:4] = halt cause):
  if (ebreak_halt)        → 0x8 ✓ EBREAK
  else if (bp0_hit)       → 0x2   Breakpoint 0
  else if (bp1_hit)       → 0x3   Breakpoint 1
  else if (dbg_halt_req)  → 0x1   Debug halt request
  else if (dbg_step_req)  → 0x4   Single-step
  else                    → 0x0 ❌ (reported for EBREAK)
```

---

## The Fix

### New Detection Logic

```systemverilog
logic prev_halted;

always_ff @(posedge clk or negedge rst_n) begin
  if (!rst_n) begin
    ebreak_halt <= 1'b0;
    prev_halted <= 1'b0;
  end else begin
    prev_halted <= dbg_halted;

    // Set when transitioning into HALTED state with EBREAK instruction
    if (!prev_halted && dbg_halted && (commit_insn == 32'h00100073)) begin
      ebreak_halt <= 1'b1;
    // Clear when CPU resumes
    end else if (!dbg_halted) begin
      ebreak_halt <= 1'b0;
    end
  end
end
```

### How It Works

1. **Track halted state**: `prev_halted` registers the previous cycle's halt status
2. **Detect transition**: `!prev_halted && dbg_halted` detects entry into HALTED state
3. **Check instruction**: `commit_insn == 0x00100073` verifies it's EBREAK
4. **Set flag**: `ebreak_halt <= 1'b1`

### Why This Works

- `commit_insn` is wired directly to the instruction register (rv32i_core.sv:454)
- When CPU halts due to EBREAK, instruction register still contains EBREAK
- Instruction register only updates on fetch, not during halt
- Our logic detects the HALTED state entry and checks what instruction caused it

---

## Verification

### Test Case (test_ebreak.py)

Created a minimal EBREAK test that:
1. Loads EBREAK instruction at address 0x0000
2. Halts CPU and sets PC to 0x0000
3. Resumes CPU
4. Waits for CPU to halt
5. Verifies halt cause is 0x8 (EBREAK)

### Expected Behavior (After Fix)

```
Status register when halted:
  - Bit [0] (halted)  = 1 ✓
  - Bit [1] (running) = 0 ✓
  - Bits [7:4] (halt_cause) = 0x8 ✓ EBREAK instruction
```

---

## Related Files Modified

- **rtl/cpu/rv32i_cpu_top.sv**: Fixed ebreak_halt detection logic
- **tb/cocotb/cpu/test_ebreak.py**: Created EBREAK-specific test

---

## Impact

**Minimal** - This only affects the halt cause reporting, not the halt functionality itself.

- ✅ CPU already halts correctly on EBREAK
- ✅ Debug interface already sets dbg_halted=1
- ✅ Fix only corrects the status register halt_cause field

---

## Commit Message

```
[RTL] Fix EBREAK halt cause detection

EBREAK transitions EXECUTE→HALTED without commit, so commit_valid
is never asserted. Changed ebreak_halt detection to monitor
state transitions (!halted→halted) with EBREAK instruction present.

Fixes halt_cause reporting from 0x0 to 0x8 for EBREAK.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
```
