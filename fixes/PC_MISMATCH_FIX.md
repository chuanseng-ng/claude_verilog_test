# PC Mismatch Error Fix - Monitor Task Cleanup

**Date**: 2026-01-28
**Issue**: PC mismatch errors during random instruction tests
**Status**: ✅ FIXED

---

## Problem Description

During random instruction tests, hundreds of PC mismatch errors were logged:
```
ERROR PC mismatch: RTL=0x00000000, Model=0x0000018c
ERROR PC mismatch: RTL=0x00000004, Model=0x00000190
ERROR PC mismatch: RTL=0x00000008, Model=0x00000194
...
```

Despite these errors, tests still reported **100% pass rate** with **0 mismatches**, creating confusion about the actual test status.

---

## Root Cause

### The Bug

**Orphaned monitor tasks accumulating across test seeds**

1. Each seed starts a new `monitor_commits` coroutine:
   ```python
   cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=commit_count))
   ```

2. Monitor tasks run indefinitely (infinite `while True` loop)

3. When a seed completes, its monitor task **continues running**

4. Next seed starts with fresh model (PC=0x0000), but old monitors still have stale models

5. Result: Multiple monitors checking the same commits with different model states

### The Accumulation

```
Seed 0: Creates monitor₀ (model PC ends at 0x18c)
  ↓
Seed 1: Creates monitor₁ (model PC starts at 0x0)
        Now 2 monitors running!
  ↓
Seed 2: Creates monitor₂ (model PC starts at 0x0)
        Now 3 monitors running!
  ↓
...
  ↓
Seed 99: Creates monitor₉₉
         Now 100 monitors running! 😱
```

### Why Tests Still Passed

- Only the **current seed's scoreboard** is checked for pass/fail
- Old monitors log errors but their scoreboards are abandoned
- Final scoreboard report only shows the active seed's results

---

## The Fix

### Implementation

**Store and cancel monitor tasks**:

```python
# Before (BROKEN):
cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=commit_count))

# After (FIXED):
monitor_task = cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=commit_count))

# ... seed execution ...

# Clean up task after seed completes
monitor_task.kill()
```

### Changes Made

File: `tb/cocotb/cpu/test_random_instructions.py`

1. **Line 87**: Store monitor task handle
   ```python
   monitor_task = cocotb.start_soon(monitor_commits(...))
   ```

2. **Line 106**: Cancel on timeout
   ```python
   monitor_task.kill()
   raise RuntimeError(...)
   ```

3. **Line 112**: Cancel after normal completion
   ```python
   monitor_task.kill()
   ```

---

## Results

### Before Fix

```
Runtime: 94.36 seconds
PC mismatch errors: Hundreds (100+ per seed after seed 1)
Active monitors at end: 100 concurrent tasks
```

### After Fix

```
Runtime: 41.94 seconds ✅ (55% faster!)
PC mismatch errors: 0 ✅ (100% eliminated!)
Active monitors at end: 1 ✅ (99% reduction)
```

### Test Output

**Before**:
```
7230.00ns INFO  Total commits checked: 99
7230.00ns INFO  Mismatches: 0
7230.00ns INFO  Seed 0: PASSED
7350.00ns ERROR PC mismatch: RTL=0x00000000, Model=0x0000018c  ← Noise!
8420.00ns ERROR PC mismatch: RTL=0x00000000, Model=0x00000190  ← Noise!
8480.00ns ERROR PC mismatch: RTL=0x00000004, Model=0x00000194  ← Noise!
...
```

**After**:
```
7230.00ns INFO  Total commits checked: 99
7230.00ns INFO  Mismatches: 0
7230.00ns INFO  Seed 0: PASSED
14470.00ns INFO Total commits checked: 99  ← Clean!
14470.00ns INFO Mismatches: 0              ← Clean!
14470.00ns INFO Seed 1: PASSED             ← Clean!
```

---

## Performance Analysis

### Why 2× Speedup?

By seed 99, there were **100 concurrent monitor tasks** all checking the same commits:
- Each commit triggered 100 scoreboard checks (1 valid, 99 stale)
- Each stale check: model step + PC comparison + logging
- 100 instructions × 99 extra checks = **9,900 wasted operations per seed**

With proper cleanup:
- Only 1 monitor active per seed
- 100× reduction in unnecessary work
- **55% runtime reduction** (94s → 42s)

---

## Lessons Learned

### Task Lifecycle Management

1. **Always store task handles** when using `cocotb.start_soon()`
   ```python
   task = cocotb.start_soon(some_coroutine())
   ```

2. **Clean up tasks** when they're no longer needed
   ```python
   task.kill()
   ```

3. **Monitor for resource leaks**
   - Infinite loops in coroutines need cleanup
   - Task accumulation causes performance degradation
   - Stale state causes confusing error messages

### Test Infrastructure Best Practices

1. **One monitor per test** - don't accumulate background tasks
2. **Explicit cleanup** - especially for infinite loops
3. **Clear error messages** - stale state can mislead debugging
4. **Performance testing** - resource leaks show up as slowdowns

---

## Related Issues

This fix resolves:
- ✅ PC mismatch error spam
- ✅ Confusing "tests pass but show errors" behavior
- ✅ Performance degradation in multi-seed tests
- ✅ Resource leak in test infrastructure

---

## Verification

### Test Command
```bash
cd tb/cocotb/cpu
make random
```

### Expected Output
```
Total seeds:     100
Passing seeds:   100 (100.0%)
Failing seeds:   0 (0.0%)
PC mismatch errors: 0
Runtime: ~42 seconds
```

### Actual Results
✅ **All expectations met!**

---

**Fix Committed**: 2026-01-28
**Test Status**: ✅ PASSING
**Performance**: ⚡ 55% faster
