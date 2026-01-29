# RTL Bug Fixes - Phase 1 Verification

**Date**: 2026-01-24
**Status**: IN PROGRESS - 21/37 tests passing

---

## ✅ Fixes Implemented

### Fix #1: Branch/Jump Timing Issue
**File**: `rtl/cpu/core/rv32i_control.sv`
**Status**: ✅ IMPLEMENTED (needs verification)

**Problem**: The `take_branch_jump` flag was registered in EXECUTE state but used immediately in WRITEBACK, causing a one-cycle delay for non-memory instructions.

**Solution**: Made the flag combinational when in EXECUTE state, and use the registered value for memory instructions (which go through MEM_WAIT).

**Code Changes**:
- Added `take_branch_jump_reg` to hold the decision across MEM_WAIT
- Made `take_branch_jump` combinational: uses direct computation in EXECUTE state, registered value otherwise
- This ensures the flag is available immediately for EXECUTE → WRITEBACK path

**Expected Impact**: Should fix all 6 branch tests + 2 jump tests (8 tests total)

### Fix #2: JAL Test Encoding Error
**File**: `tb/cocotb/cpu/test_isa_compliance.py` (line 1453)
**Status**: ✅ FIXED

**Problem**: JAL backward jump used incorrect encoding `0xFF800117` (AUIPC opcode) instead of JAL opcode `0x6F`.

**Solution**: Corrected instruction encoding to `0xFF9FF0EF` (JAL x2, -8).

**Expected Impact**: Should fix JAL test

### Fix #3: Load Data Not Latched
**File**: `rtl/cpu/core/rv32i_core.sv`
**Status**: ✅ IMPLEMENTED (still failing - needs more investigation)

**Problem**: `axi_rdata` is only valid during the AXI read cycle, but was used combinationally in WRITEBACK state after it became invalid.

**Solution**: Added `mem_rdata_raw` register to latch AXI read data when `axi_rvalid && axi_rready && data_access`.

**Code Changes**:
- Added `mem_rdata_raw` signal (line ~112)
- Added latch logic (lines ~206-214)
- Updated load data extraction to use `mem_rdata_raw` instead of `axi_rdata`

**Expected Impact**: Should fix all 5 load tests

---

## ❌ Remaining Issues

### Issue #1: Branches Still Failing (6 tests)
**Tests**: BEQ, BNE, BLT, BGE, BLTU, BGEU
**Status**: ❌ STILL FAILING after Fix #1

**Symptom**: Branches are NOT being taken when they should be. Tests show "x3 should be 0 (skipped), got 99" indicating fall-through path executed instead of branch target.

**Possible Causes**:
1. Fix #1 not working as expected - timing still off
2. Branch comparator not computing `branch_taken` correctly
3. Decoder not setting `branch` signal correctly
4. PC update logic not using `pc_src` correctly

**Next Steps**:
- Add debug signals to trace `branch`, `branch_taken`, `take_branch_jump`, and `pc_src`
- Run simulation with waveforms to see actual signal values
- Verify branch comparator outputs match expected values

### Issue #2: Loads Still Return 0 (5 tests)
**Tests**: LW, LH, LHU, LB, LBU
**Status**: ❌ STILL FAILING after Fix #3

**Symptom**: All loads return `0x00000000` instead of memory data.

**Possible Causes**:
1. AXI read data not being latched correctly (timing issue with `data_access`)
2. Memory model not serving read data on AXI bus
3. Register file write enable not asserted for loads
4. Memory address calculation incorrect

**Next Steps**:
- Verify `axi_rdata` has correct value during AXI read cycle
- Verify `mem_rdata_raw` latches the data
- Verify `rd_data` gets `mem_rdata` for load instructions
- Verify `regfile_wr_en` is asserted in WRITEBACK for loads
- Check testbench `SimpleAXIMemory` is responding correctly

### Issue #3: Stores Don't Write Memory (3 tests)
**Tests**: SW, SH, SB
**Status**: ❌ NOT FIXED YET

**Symptom**: Memory stays `0x00000000` after store instruction.

**Possible Causes**:
1. AXI write transaction not completing
2. Testbench memory model not handling writes
3. Write data not being driven on `axi_wdata`
4. Write strobes (`axi_wstrb`) incorrect

**Next Steps**:
- Verify AXI write transaction completes (awvalid, wvalid, bvalid handshakes)
- Verify `axi_wdata` has correct value from `rs2_data`
- Verify `axi_wstrb` byte enables are correct
- Check testbench memory model's `axi_write_handler`

### Issue #4: Jumps Still Failing (2 tests)
**Tests**: JAL, JALR
**Status**: ❌ STILL FAILING

**Symptom**: JAL stores wrong value in link register. JALR doesn't store anything.

**Possible Causes**:
1. Similar to branch issue - pc_src not working
2. `pc_insn` register not capturing correct PC value
3. Link register write data calculation wrong (`pc_insn + 4`)
4. Register file write not happening for jumps

**Next Steps**:
- Verify `pc_insn` has the correct instruction PC
- Verify `rd_data` calculation for jumps: `pc_insn + 4`
- Verify `regfile_wr_en` is asserted for JAL/JALR
- Debug with waveforms to see actual PC values

---

## 📊 Test Summary

| Category | Passing | Failing | Total |
|----------|---------|---------|-------|
| Arithmetic | 3 | 0 | 3 |
| Logical | 6 | 0 | 6 |
| Shift | 6 | 0 | 6 |
| Comparison | 4 | 0 | 4 |
| Upper Immediate | 2 | 0 | 2 |
| **Branch** | **0** | **6** | **6** |
| **Jump** | **0** | **2** | **2** |
| **Load** | **0** | **5** | **5** |
| **Store** | **0** | **3** | **3** |
| **TOTAL** | **21** | **16** | **37** |

**Pass Rate**: 56.8% (21/37)

---

## 🔧 Recommended Next Steps

1. **Priority 1**: Debug branch issue with waveforms
   - Run single BEQ test with waveform generation
   - Trace signals: `branch`, `branch_taken`, `take_branch_jump`, `pc_src`, `pc_next`, `pc_reg`
   - Identify where the logic breaks down

2. **Priority 2**: Debug load issue with waveforms
   - Run single LW test with waveforms
   - Trace signals: `axi_rdata`, `mem_rdata_raw`, `mem_rdata`, `rd_data`, `regfile_wr_en`
   - Verify testbench memory is serving data correctly

3. **Priority 3**: Fix store issue
   - Verify AXI write handshakes in waveforms
   - Check testbench memory write handler

4. **Priority 4**: Fix jump issue
   - Likely fixed once branch issue is resolved
   - Verify `pc_insn` logic and link register calculation

---

## 📝 Files Modified

1. `rtl/cpu/core/rv32i_control.sv` - Branch/jump timing fix
2. `rtl/cpu/core/rv32i_core.sv` - Load data latch
3. `tb/cocotb/cpu/test_isa_compliance.py` - JAL encoding fix

---

**END OF REPORT**
