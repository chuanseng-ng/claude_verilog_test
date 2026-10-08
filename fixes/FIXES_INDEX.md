# RV32I CPU - RTL Fixes Reference Guide

**Last Updated**: 2026-01-29
**Status**: All documented fixes applied and validated

---

## Overview

This directory contains documentation for all RTL bugs discovered and fixed during Phase 1 development (2026-01-18 to 2026-01-29). All fixes have been applied to the RTL and validated through testing.

---

## Quick Reference

| Fix Document | Date | Category | Severity | Status |
|:-------------|:----:|:---------|:--------:|:------:|
| [CRITICAL_FIXES.md](#1-critical-axi-protocol-fixes) | 2026-01-19 | AXI Protocol | CRITICAL | ✅ Fixed |
| [RTL_BUG_FIXES.md](#2-branch-jump-and-memory-fixes) | 2026-01-24 | Control/Memory | HIGH | ✅ Fixed |
| [RTL_DEBUG_REPORT.md](#3-rtl-debug-report) | 2026-01-24 | Analysis | INFO | ✅ Complete |
| [TIMING_ANALYSIS.md](#4-timing-analysis) | 2026-01-25 | Timing | MEDIUM | ✅ Fixed |
| [RTL_ISA_TEST_FIX.md](#5-isa-test-fixes) | 2026-01-25 | Test/RTL | MEDIUM | ✅ Fixed |
| [TEST_FIX_SUMMARY.md](#6-test-fix-summary) | 2026-01-25 | Test | LOW | ✅ Fixed |
| [EBREAK_BUG_FIX.md](#7-ebreak-halt-detection-fix) | 2026-01-28 | Debug | MEDIUM | ✅ Fixed |
| [PC_MISMATCH_FIX.md](#8-pc-mismatch-logging-fix) | 2026-01-28 | Test | LOW | ✅ Fixed |
| [Section 9 (below)](#9-axi-lite-ring-phantom-decerr-r-beat-bead-3xtv) | 2026-10-07 | AXI-Lite Protocol | MEDIUM (P2) | ✅ Fixed |
| [Section 10 (below)](#10-uart-rx-false-start-window-bead-rqvo) | 2026-10-09 | UART RX | LOW (P3) | ✅ Fixed |

---

## Fix Timeline

```
2026-01-19: Critical AXI protocol bugs (CPU non-functional)
2026-01-24: Branch/jump timing, load data latching, register file reads
2026-01-25: ISA test fixes, timing constraints
2026-01-28: EBREAK halt detection, PC mismatch logging
```

---

## 1. Critical AXI Protocol Fixes

**File**: [CRITICAL_FIXES.md](CRITICAL_FIXES.md)
**Date**: 2026-01-19
**Severity**: 🔴 CRITICAL (CPU non-functional without these fixes)

### Issues Fixed

#### Bug 1: Incorrect AXI Read Timing in FETCH State
- **Problem**: Code assumed `rvalid` asserts same cycle as `arready` (violates AXI protocol)
- **Impact**: CPU hung waiting for impossible condition
- **Fix**: Changed to wait only for `rvalid && rready` (data phase), independent of address phase
- **Files**: `rv32i_control.sv` (FETCH state)

#### Bug 2: Incorrect AXI Read/Write Timing in MEM_WAIT State
- **Problem**: Same protocol violation for load/store operations
- **Impact**: CPU hung on all memory operations
- **Fix**: Wait only for data phase completion (`rvalid`/`bvalid`)
- **Files**: `rv32i_control.sv` (MEM_WAIT state)

#### Bug 3: Missing AXI Address Mux
- **Problem**: `axi_araddr` always used PC (not multiplexed for data accesses)
- **Impact**: All loads fetched from wrong address (PC instead of calculated address)
- **Fix**: Added `data_access` control signal and address mux
- **Files**: `rv32i_control.sv`, `rv32i_core.sv`

### Validation
- ✅ Variable latency AXI slave works correctly
- ✅ Load instructions use calculated address (not PC)
- ✅ FETCH and MEM_WAIT states handle multi-cycle transactions

---

## 2. Branch, Jump, and Memory Fixes

**File**: [RTL_BUG_FIXES.md](RTL_BUG_FIXES.md)
**Date**: 2026-01-24
**Severity**: 🟠 HIGH (Instructions failed tests)

### Issues Fixed

#### Bug 1: Branch/Jump Timing Issue
- **Problem**: Branch decision computed but not registered before state transition
- **Impact**: JAL backward jumps failed, branch tests unreliable
- **Fix**: Added `branch_decision_reg` to latch decision at end of EXECUTE state
- **Files**: `rv32i_control.sv`
- **Tests Fixed**: JAL backward jump, all 6 branch instructions

#### Bug 2: Load Data Latching
- **Problem**: Load data not latched from AXI read response
- **Impact**: All 5 load instructions failed
- **Fix**: Added `mem_rdata_raw` register to capture `axi_rdata`
- **Files**: `rv32i_core.sv`
- **Tests Fixed**: LW, LH, LHU, LB, LBU (all 5 load instructions)

#### Bug 3: Register File Synchronous Reads
- **Problem**: Register values not available until next cycle
- **Impact**: Store instructions failed (register values not ready in time)
- **Fix**: Changed register file to combinational reads
- **Files**: `rv32i_regfile.sv`
- **Tests Fixed**: SW, SH, SB (all 3 store instructions)

### Test Results
- **Before**: 21/37 ISA tests passing (57%)
- **After**: 37/37 ISA tests passing (100%) 🎉

---

## 3. RTL Debug Report

**File**: [RTL_DEBUG_REPORT.md](RTL_DEBUG_REPORT.md)
**Date**: 2026-01-24
**Severity**: ℹ️ INFO (Debug analysis document)

### Content
- Detailed analysis of branch/jump failures
- SW instruction failure investigation
- Signal trace analysis
- Led to fixes documented in RTL_BUG_FIXES.md

**Purpose**: Historical debug record, not a fix document per se.

---

## 4. Timing Analysis

**File**: [TIMING_ANALYSIS.md](TIMING_ANALYSIS.md)
**Date**: 2026-01-25
**Severity**: 🟡 MEDIUM (Test timing issues)

### Issues Fixed

#### Issue 1: Insufficient Wait Time After Resume
- **Problem**: Test checked GPRs immediately after resume (values not yet updated)
- **Impact**: Intermittent test failures
- **Fix**: Added 5-10 clock cycle delay before checking results
- **Files**: Test files

#### Issue 2: AXI Transaction Timing
- **Problem**: Tests didn't account for multi-cycle AXI transactions
- **Impact**: Race conditions in test assertions
- **Fix**: Added proper synchronization in test infrastructure
- **Files**: `test_smoke.py`, memory models

### Validation
- ✅ All timing-related test failures resolved
- ✅ Tests now robust against variable memory latency

---

## 5. ISA Test Fixes

**File**: [RTL_ISA_TEST_FIX.md](RTL_ISA_TEST_FIX.md)
**Date**: 2026-01-25
**Severity**: 🟡 MEDIUM (Test infrastructure)

### Issues Fixed

#### Issue 1: Incorrect Instruction Encodings
- **Problem**: Some test encodings didn't match RV32I spec
- **Impact**: Tests checked wrong behavior
- **Fix**: Corrected encodings using `riscv_encoder.py`
- **Files**: `test_isa_compliance.py`

#### Issue 2: Test Initialization Issues
- **Problem**: CPU not properly halted before register initialization
- **Impact**: Register writes during execution caused corruption
- **Fix**: Created `reset_dut_halted()` helper function
- **Files**: `test_smoke.py`, test infrastructure

### Test Results
- ✅ All 37 ISA compliance tests passing
- ✅ Proper test initialization prevents corruption

---

## 6. Test Fix Summary

**File**: [TEST_FIX_SUMMARY.md](TEST_FIX_SUMMARY.md)
**Date**: 2026-01-25
**Severity**: 🟢 LOW (Test improvements)

### Summary
- Consolidated test infrastructure improvements
- Documents test pattern standardization
- Reference for test writing best practices

---

## 7. EBREAK Halt Detection Fix

**File**: [EBREAK_BUG_FIX.md](EBREAK_BUG_FIX.md)
**Date**: 2026-01-28
**Severity**: 🟡 MEDIUM (Debug interface)

### Issue Fixed

#### Problem: EBREAK Halt Cause Incorrect
- **Problem**: EBREAK instruction halted CPU, but `halt_cause` reported 0x0 instead of 0x8
- **Root Cause**: EBREAK transitions EXECUTE→HALTED (skips WRITEBACK), so `commit_valid` never asserted
- **Impact**: Debug interface couldn't distinguish EBREAK halt from other halt causes
- **Fix**:
  - Exposed `ebreak` signal from decoder as `debug_ebreak`
  - Two-stage detection: latch when decoded, set halt cause when entering HALTED
- **Files**: `rv32i_core.sv`, `rv32i_cpu_top.sv`

### Validation
- ✅ EBREAK halt cause correctly reported as 0x8
- ✅ Test `test_ebreak.py` passes

---

## 8. PC Mismatch Logging Fix

**File**: [PC_MISMATCH_FIX.md](PC_MISMATCH_FIX.md)
**Date**: 2026-01-28
**Severity**: 🟢 LOW (Cosmetic logging issue)

### Issue Fixed

#### Problem: Spurious PC Mismatch Logs
- **Problem**: Tests logged PC mismatches during execution, but scoreboard reported 0 mismatches
- **Root Cause**: Monitor task read RTL signals during state transitions (non-commit cycles)
- **Impact**: Confusing logs (but no actual failures)
- **Fix**: Enhanced commit detection logic, cleaned up orphaned monitor tasks
- **Files**: `test_random_instructions.py`, monitor infrastructure

### Validation
- ✅ Clean logs with 0 false PC mismatch errors
- ✅ Scoreboard still validates correctly

---

## 9. AXI-Lite Ring Phantom DECERR R Beat (bead 3xtv)

**File**: `rtl/soc/axi_lite_interconnect.sv` (read engine, `R_DATA`, unmapped branch)
**Date**: 2026-10-07
**Severity**: P2 (error path only; legal accesses unaffected)
**Fix request**: `fr_null_20261006_170941_00` (found by bead 8riq stall tests)

### Issue Fixed
- **Problem**: one read to an unmapped address (AXI-Lite ring window gap or above the APB limit) returned TWO DECERR R beats whenever `rready` was high. The unmapped branch drove `r_dvalid_d = 1` for as long as `rstate == R_DATA`, but the state only leaves `R_DATA` on `r_hs`, one cycle after `r_dvalid_q` captured the beat. In that handshake cycle `r_dreg_ready = 1`, so `r_dvalid_q` reloaded a second time.
- **Impact**: a response with no outstanding request (protocol violation); the phantom beat was consumed as the reply to the master's NEXT read (resp=DECERR, data=0 instead of its data). Mapped reads and the unmapped write path were never affected.
- **Fix**: `r_dvalid_d = !r_dvalid_q` in the unmapped branch, so the beat is offered only while the output register is empty. Depends on the registered `r_dvalid_q` only: no READY->VALID loop, no runtime-indexed mux, mapped-slave timing (bead rvb fan-out register) unchanged.
- **Tests**: `test_axil_apb_fabric.test_ring_unmapped_read_single_beat` (was `expect_fail=True`) now passes; the `_drain_r` stray-beat workaround was removed from `test_ring_decerr_with_master_stalls`.

---

## 10. UART RX False-Start Window (bead rqvo)

**File**: `rtl/periph/uart_controller.sv` (RX FSM, `RX_START`)
**Date**: 2026-10-09
**Severity**: P3 (only after line glitches / noise; normal traffic unaffected)
**Found by**: bead 05wf coverage agent (PR #234); fix approved by the user 2026-10-08

### Issue Fixed
- **Problem**: a false start (line low at the START edge, majority HIGH at the mid-bit samples, os_phase 7/8/9) was only rejected at `bit_tick` (phase 15 wrap), so the FSM sat in `RX_START` for the rest of the bit period.
- **Impact**: a genuine START falling edge landing in that window (phases ~10-15 after the glitch) was not framed from its own edge. The receiver returned to idle up to ~6 oversample ticks late, re-aligned on the already-low line, and sampled every following bit off-centre: lost or mis-framed byte.
- **Fix**: reject at the os_tick with `os_phase_q == 10 && rx_maj` (the same point `RX_STOP` uses, since `rx_s9_q` is registered one tick earlier) and return to `RX_IDLE`, which re-arms level-based START detection on the next os_tick. The `bit_tick` branch now goes unconditionally to `RX_DATA` (a majority-HIGH vote can no longer reach it). Accepted-START timing is unchanged.
- **Tests**: new `test_uart.test_rx_false_start_then_real_start` (2-clock glitch, then a real 8N1 frame starting 9..15 clocks after the glitch, byte-exact, no framing error, no spurious extra byte). Failed on the old RTL at gap 10; passes after. `test_rx_false_start_rejected` (05wf-5) did not encode the buggy timing and is unchanged.

---

## Impact Summary

### Critical Fixes (CPU Non-Functional → Functional)
1. ✅ AXI protocol compliance (CRITICAL_FIXES.md)
2. ✅ Branch/jump timing (RTL_BUG_FIXES.md)
3. ✅ Load data latching (RTL_BUG_FIXES.md)
4. ✅ Register file combinational reads (RTL_BUG_FIXES.md)

### Test Coverage Improvement
- **Start**: 0/37 ISA tests passing (0%)
- **After AXI fixes**: CPU functional, basic tests pass
- **After RTL_BUG_FIXES**: 37/37 ISA tests passing (100%) 🎉
- **After random tests**: 10,000 random instructions, 0 failures 🎉

### Test Infrastructure Improvements
- ✅ Timing robustness (TIMING_ANALYSIS.md)
- ✅ Test initialization (RTL_ISA_TEST_FIX.md)
- ✅ Instruction encodings (RTL_ISA_TEST_FIX.md)
- ✅ Debug interface (EBREAK_BUG_FIX.md)
- ✅ Logging cleanup (PC_MISMATCH_FIX.md)

---

## Files Modified (RTL)

### Control Logic
- `rtl/cpu/core/rv32i_control.sv`
  - AXI protocol fixes (FETCH, MEM_WAIT states)
  - Branch decision registration
  - `data_access` control signal

### Core Integration
- `rtl/cpu/core/rv32i_core.sv`
  - AXI address mux
  - Load data latching (`mem_rdata_raw`)
  - EBREAK signal exposure (`debug_ebreak`)

### Register File
- `rtl/cpu/core/rv32i_regfile.sv`
  - Combinational reads (removed synchronous logic)

### Top-Level
- `rtl/cpu/rv32i_cpu_top.sv`
  - EBREAK halt detection (two-stage)
  - Debug status reporting

---

## Verification Status

### Phase 1 Exit Criteria (5/9 met)
- ✅ Smoke tests: 6/6 pass
- ✅ Scoreboard mismatches: 0
- ✅ Instruction coverage: 37/37 (100%)
- ✅ Random instruction tests: 10,000 instructions, 0 failures
- ✅ Failing random seeds: 0 (100/100 seeds pass)
- ❌ AXI protocol tests: Not started (Task 4 - NEXT)
- ⚠️ Debug interface tests: Partial (Task 5)
- ❌ Code coverage: Not tracked (Task 6)
- ❌ State coverage: Not tracked (Task 6)

### Confidence Level
**HIGH** - All critical RTL bugs fixed, comprehensive test coverage achieved.

---

## References

### Main Project Documentation
- `CLAUDE.md` - Project overview and workflow
- `TODO_PHASE1_VERIFICATION.md` - Verification task tracking
- `README.md` - Repository overview

### Specifications
- `docs/design/PHASE1_ARCHITECTURE_SPEC.md` - CPU architecture
- `docs/design/RTL_DEFINITION.md` - Interface definitions
- `docs/design/MEMORY_MAP.md` - Address space and registers
- `docs/verification/VERIFICATION_PLAN.md` - Test strategy

---

**Document Maintenance**:
- This index is updated whenever new fixes are documented
- Old fix documents are never deleted (historical record)
- Severity ratings help prioritize review and understanding
- All fixes are validated through tests before being marked "Fixed"

---

**End of Fixes Index**
