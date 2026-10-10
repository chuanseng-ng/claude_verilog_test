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
| [Section 11 (below)](#11-i2c-startstop-condition-times-bead-gecv) | 2026-10-10 | I2C bit engine | LOW (P3) | ✅ Fixed |

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

## 11. I2C START/STOP Condition Times (bead gecv)

**File**: `rtl/periph/i2c_bit_engine.sv` (tick reload for `S_ST_LO`, `S_RS_HI`, `S_STP_HI`, `S_STP_FREE`)
**Date**: 2026-10-10
**Severity**: P3 (no external I2C slave is attached in any flow; software could mask it with a delay)
**Found by**: bead pnfw item 3 (verification-orchestrator), measured on the bus

### Issue Fixed
- **Problem**: every START/STOP condition phase lasted ONE tick (N = CLKDIV+1 clk, a quarter bit period), about half the I2C minimum at the Standard divisor. Measured at 100 MHz clk: tBUF 2.53 us at CLKDIV=249 (min 4.7) and 0.66 us at CLKDIV=62 (min 1.3); tSU;STO 2.53 us (min 4.0, Fast 0.66 vs 0.6); tHD;STA 2.50 us (min 4.0); tSU;STA of a repeated START 2.53 us (min 4.7). The Fast-mode tHD;STA/tSU;STA/tSU;STO met their 0.6 us by only 0.03..0.06 us.
- **Impact**: a driver that wrote the next CMD on the first APB access after `STATUS.busy` dropped produced a STOP->START gap below spec; a Standard-mode slave could miss the START or STOP.
- **Fix**: the phase lengths are now whole-tick counts set by the tick reload (no new state, `state_e` still 17 names / 5 bits): `S_ST_LO`, `S_RS_HI`, `S_STP_HI` = 2 ticks (reload `2N-1`), `S_STP_FREE` = 3 ticks (`3N-1`). 2 ticks = 5.0 us at 100 kHz clears the tightest Standard minimum (4.7 us); at 400 kHz 2 ticks = 1.25 us clears 0.6 us but NOT tBUF's 1.3 us, hence 3 ticks (1.875 us; Standard 7.5 us). Because a tick is exactly 1/(4 f_scl), the guarantee holds at any CLKDIV for a Standard-mode bus <= 100 kHz and a Fast-mode bus <= 400 kHz; it does not cover > 400 kHz and tBUF is enforced only after this master's own STOP (derivation table in the module header).
- **Busy semantics**: the bus-free interval is INSIDE `STATUS.busy` and the DONE event of a STOP command is raised at its end (3 ticks after the STOP edge instead of 1). Commands written during the interval are ignored like any busy-time command, so tBUF holds even for a command written on the first APB access after busy drops.
- **Not changed**: data-bit timing (period exactly 4N, tLOW/tHIGH) and `K = floor(N/8)` (bead cd15 stays deferred).
- **Cost**: `tick_q` 17 -> 18 bits (+1 flop; `S_STP_FREE` reload is `0x2FFFF` at CLKDIV=0xFFFF), one 18-bit constant-3 adder in the reload mux, no new states.
- **Tests**: `test_i2c_stop_to_start_bus_free_time_meets_spec` (was `expect_fail=True`, limits unchanged), new `test_i2c_start_stop_condition_times_meet_spec` (tSU;STO, tHD;STA on START and repeated START, tSU;STA, strict spec limits, both divisors), `test_i2c_busy_covers_bus_free_time`, `test_i2c_condition_tick_reloads_at_clkdiv_ffff`. All red on the old RTL, green after.

---

## 12. GPU Warp Count Saturated at 7 (bead 47lf, GH #254)

**Files**: `rtl/gpu/gpu_pkg.sv` (new `WARP_CNT_W`), `rtl/gpu/gpu_top.sv` (`n_warps_w`), `rtl/gpu/warp_scheduler.sv` (`n_warps_active_i`, `n_warps_q`, issue compare, `all_done`)
**Date**: 2026-10-10
**Severity**: P2 (silent: the kernel completed with `STATUS[done]` set and no error, but 8 of the 64 permitted threads never ran)
**Found by**: bead a5ze (`kernel_block_warps.py`), root-caused with `n_warps_w` / `u_sched.n_warps_q` sampled in simulation

### Issue Fixed
- **Problem**: the warp COUNT (0..8) was held in `WARP_W` = 3 bits, the width of a warp ID (0..7). `gpu_top` capped it at `N_WARPS-1` = 7, so `BLOCK_X` 57..64 (true count 8) ran warps 0..6 and warp 7 (threads 56..63) never executed. Measured before the fix: `n_warps_w` = `n_warps_q` = 7 for every `BLOCK_X` in 57..64 and above; 56 lane stores of 64 expected, the 8 missing being exactly lanes 56..63; no wrong values, no extra stores.
- **Hypothesis confirmed, with one addition**: the representable-range diagnosis in the bead was right (counter width). The cap at 7 was a deliberate-looking guard on top of it, and the same truncation hid in two more places in `warp_scheduler`: the `all_done` compare cast `n_warps_q` back to `WARP_W` bits (so a count of 8 would read as 0 and the kernel would be declared done at once) and the issue compare `cand_i < n_warps_q` was 3 bits against a 3-bit register. Widening only `gpu_top` would have been wrong.
- **Fix**: `gpu_pkg::WARP_CNT_W = $clog2(N_WARPS + 1)` = 4. `n_warps_w`, `warp_scheduler.n_warps_active_i` and `n_warps_q` are `WARP_CNT_W` wide; the cap is `N_WARPS` (`raw > N_WARPS ? N_WARPS : raw`); the issue and `all_done` compares are done at `WARP_CNT_W` width. Warp IDs, `rr_ptr`, the register file and every `WARP_W` signal are unchanged.
- **Not changed (decided, not missed)**:
  - `BLOCK_X` > 64 is still truncated, now to the 8 warps that exist (previously 7). The spec text conflicts with the frozen Phase 4 architecture (`PHASE4_GPU_ARCHITECTURE_SPEC.md:66` says up to 256 threads / 32 warps per block; CLAUDE.md and the 8-deep warp storage say 8 warps / 64 threads). Honouring it needs warp storage or multi-pass block execution, not a width fix. Pinned by `test_block_sizes_above_cap`.
  - `BLOCK_X` = 0 yields a count of 0: no warp ever issues and `kernel_done_o` requires `n_warps_q != 0`, so STATUS[done] never sets and the launch hangs until CTRL reset. Pre-existing, unchanged, deliberately not pinned by a test.
  - A partially filled last warp runs all 8 lanes (`init_mask_i` is a constant `0xFF`; `gpu_ref_model.py` and `tb/models/gpu_kernel_model.py` both do the same). Tail lanes are not masked at any `BLOCK_X`, e.g. 9 runs 16 lanes. Not a regression and not the reported defect; follow-up bead.
  - No run-time-indexed mux was added, and `warp_scheduler.sv` `warp_pc[next_warp]` / `warp_mask[next_warp]` (the `ma7`-class read) is untouched.
- **Register map / software**: the count is internal. It is not readable through `GPU_STATUS`, the perf counters (`perf_cnt_q[0..13]` count cycles / retires / issues / pushes / AXI requests) or any `sw/` source, so no field width, offset or driver changed.
- **Python model**: `tb/models/gpu_kernel_model.py` did NOT have the bug (`warps_per_block = ceil(threads/8)`, no cap, a list of warp dicts), nor does `tb/cocotb/gpu/gpu_ref_model.py` (a single-warp interpreter driven once per warp). That is why no model comparison caught it: nothing compared the multi-warp RTL against either model above 56 threads.
- **Same class elsewhere in `rtl/gpu`**: none found. The other 3-bit quantities are warp IDs (0..7). No 6-bit thread count exists, `BLOCK_Y`/`BLOCK_Z` and the grid dimensions are stored but unused in Phase 4, and there is no active-warps perf counter.
- **Tests** (red on the old RTL, green after): `kernel_block_warps.py` `test_block_sizes_57_to_64` (`expect_fail` removed, limits unchanged, now every size 57..64 individually), `test_lane_results_match_model` (all lanes of every warp vs `GpuRefModel` at `BLOCK_X` 1, 8, 9, 56, 57, 58, 60, 63, 64), `test_block_sizes_above_cap` (65, 72, 128, 1023); `test_warp_scheduler.py` `test_eight_warps_issue_and_complete`.
- **Physical design**: `gpu_top` is a hard macro on ASAP7 (`pnr/asap7/soc/macro/gpu_top.*`) and cannot be re-hardened on this host (beads `ma7` / `lxv` / `2kn`). The committed macro views are now functionally behind this RTL (and were already Synlig-built, see `ma7`). No PD run was made. The GPU is not in the Sky130 SoC.

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
