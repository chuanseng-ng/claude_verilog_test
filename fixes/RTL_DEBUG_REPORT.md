# RTL Debug Report - Branch/Load/Store Issues

**Date**: 2026-01-24
**Current Status**: 21/37 tests PASSING (57%), 16/37 tests FAILING (43%)

---

## Problem Summary

After implementing 3 RTL fixes, **all 16 failing tests remain failing**:
- ❌ Branches (6): BEQ, BNE, BLT, BGE, BLTU, BGEU
- ❌ Jumps (2): JAL, JALR
- ❌ Loads (5): LW, LH, LHU, LB, LBU
- ❌ Stores (3): SW, SH, SB

---

## Fixes Attempted

### Fix #1: Branch Timing (v1 - Failed)
**Attempt**: Made `take_branch_jump` combinational in EXECUTE/WRITEBACK states
**Result**: Still failing - decoder outputs change when instruction updates

### Fix #2: Branch Timing (v2 - Failed)
**Attempt**: Always use registered `take_branch_jump_reg` value
**Rationale**: Decoder signals (`branch`, `jump`) are combinational based on instruction register. When transitioning from EXECUTE→WRITEBACK, instruction register updates with next instruction, changing decoder outputs.
**Result**: Still failing - indicates the issue is deeper

### Fix #3: Load Data Latch (Failed)
**Attempt**: Added `mem_rdata_raw` register to latch AXI read data
**Result**: Loads still return 0 - AXI data likely not being served or latched incorrectly

### Fix #4: JAL Encoding (Fixed in test)
**Attempt**: Fixed JAL test instruction encoding from `0xFF800117` (AUIPC) to `0xFF9FF0EF` (JAL)
**Result**: Test encoding fixed, but JAL still fails due to other issues

---

## Root Cause Analysis

### Issue #1: Branch Instructions Not Taking

**Observations**:
- BEQ test sets x1=42, x2=42
- BEQ x1, x2, +8 should branch to skip ADDI x3, x0, 99
- Test result: x3=99, meaning ADDI executed (branch NOT taken)

**Possible Root Causes**:

1. **Debug Register Writes Not Working**:
   - APB writes to set x1=42, x2=42 may not actually write to register file
   - Registers might still be 0, so branch comparator sees 0==0 and should branch, but doesn't
   - OR registers are written but read back as 0

2. **Branch Comparator Issue**:
   - `branch_taken` signal not being computed correctly
   - `rs1_data` or `rs2_data` not getting correct values from register file

3. **PC Update Logic Issue**:
   - `pc_src` not being used correctly to select branch target
   - `pc_next` calculation incorrect for branches

4. **Timing/Sequencing Issue**:
   - Branch decision registered at wrong time
   - Instruction register updates interfering with decision

**Evidence Needed**:
- Value of `rs1_data` and `rs2_data` during branch execution
- Value of `branch_taken` signal
- Value of `take_branch_jump_reg` in WRITEBACK state
- Value of `pc_src` when PC updates
- Actual PC value after branch instruction

### Issue #2: Loads Return 0

**Observations**:
- All load instructions (LW, LH, LHU, LB, LBU) return 0 instead of memory data

**Possible Root Causes**:

1. **AXI Read Transaction Not Completing**:
   - Memory model not responding to AXI read requests
   - AXI handshake signals incorrect

2. **Data Not Being Latched**:
   - `mem_rdata_raw` register added but may not be latching at correct time
   - `data_access` flag may not be set correctly

3. **Register File Write Not Happening**:
   - `regfile_wr_en` not asserted for load instructions in WRITEBACK
   - `rd_data` mux not selecting `mem_rdata` for loads

4. **Test Setup Issue**:
   - Memory not being pre-loaded with test data
   - Load address calculation incorrect

**Evidence Needed**:
- AXI read transaction waveforms (arvalid, arready, rvalid, rready, rdata)
- Value of `data_access` signal during load
- Value of `axi_rdata` when rvalid=1
- Value of `mem_rdata_raw` after latch
- Value of `rd_data` in WRITEBACK
- Value of `regfile_wr_en` in WRITEBACK

### Issue #3: Stores Don't Write Memory

**Observations**:
- All store instructions write 0 to memory instead of register data

**Possible Root Causes**:

1. **AXI Write Transaction Not Completing**:
   - Memory model not handling AXI write correctly
   - AXI handshake signals incorrect

2. **Write Data Not Driven**:
   - `axi_wdata` not getting correct value from `rs2_data`
   - `axi_wstrb` byte enables incorrect

3. **Memory Model Bug**:
   - `SimpleAXIMemory.axi_write_handler()` not writing to memory dict
   - Write happening but at wrong address

**Evidence Needed**:
- AXI write transaction waveforms (awvalid, awready, wvalid, wready, bvalid, bready, wdata, wstrb)
- Value of `rs2_data` (store data)
- Value of `axi_wdata`
- Value of `axi_awaddr` (store address)
- Memory contents after store

---

## Recommended Next Steps

Given that 3 fixes have failed to resolve the issues, we need better visibility:

### Option A: Add RTL Debug Signals ⭐ RECOMMENDED
1. Add commit interface signals:
   - `commit_rd` - destination register number
   - `commit_rd_we` - register write enable
   - `commit_rd_data` - register write data
2. Add branch debug signals (make visible at top level):
   - `debug_branch_taken`
   - `debug_take_branch_jump`
   - `debug_rs1_data`
   - `debug_rs2_data`
3. Re-run tests and examine cocotb logs for signal values

### Option B: Simplify Test Case
1. Create minimal standalone test:
   - Just test one BEQ instruction
   - Add extensive logging
   - Single-step through state machine
2. Verify each stage:
   - Debug register writes actually work
   - Register file reads return correct values
   - Branch comparator computes correctly
   - PC updates to correct target

### Option C: Check Instruction Fetch Timing
The issue might be that we're making the branch decision based on the WRONG instruction:
1. In EXECUTE state, instruction register has instruction N
2. We compute branch decision for instruction N
3. CPU starts fetching instruction N+1 (speculative)
4. Instruction register updates with instruction N+1 BEFORE we commit instruction N
5. In WRITEBACK, we use branch decision that was based on instruction N, but decoder now shows instruction N+1

**This requires checking when instruction register updates relative to state transitions!**

### Option D: Review State Machine Timing
The single-cycle design may have fundamental timing issues:
1. Non-memory instructions go EXECUTE → WRITEBACK in consecutive cycles
2. PC updates in WRITEBACK
3. New instruction fetch starts immediately
4. When does instruction register update?
5. Are we making decisions based on stale or premature instruction data?

---

## VCD Analysis Attempts

Attempted to analyze VCD waveforms but:
- VCD file is large (1.8MB, 302 signals, 18551 timestamps)
- Python VCD parser created but shows limited useful data
- Need better filtering to find the BEQ test execution window
- Branch signals appear mostly inactive in sampled time windows

**Recommendation**: Use a proper waveform viewer (GTKWave) or add more logging to tests.

---

## Testbench Analysis

### SimpleAXIMemory Model
**Read Handler** (lines 149-172):
```python
- Waits for axi_arvalid=1
- Sets axi_arready=1 for 1 cycle
- Sets axi_rvalid=1 with data
- Waits for axi_rready=1
- Clears axi_rvalid
```
**Looks correct** - follows AXI4-Lite protocol

**Write Handler** (lines 173-197):
```python
- Waits for axi_awvalid=1 AND axi_wvalid=1
- Sets axi_awready=1, axi_wready=1 for 1 cycle
- Writes to memory dict
- Sets axi_bvalid=1
- Waits for axi_bready=1
- Clears axi_bvalid
```
**Looks correct** - follows AXI4-Lite protocol

### APB Debug Interface
**Register Writes** (rv32i_cpu_top.sv lines 255-263):
```systemverilog
if (apb_paddr >= 12'h010 && apb_paddr <= 12'h08C && apb_paddr[1:0] == 2'b00 && dbg_halted) begin
  dbg_reg_wr_en   <= 1'b1;
  dbg_reg_wr_addr <= apb_paddr[6:2] - 5'd4;
  dbg_reg_wr_data <= apb_pwdata;
end
```
**Address calculation check**:
- GPR[1] at 0x014: paddr[6:2] = 5, 5-4 = 1 ✓
- GPR[2] at 0x018: paddr[6:2] = 6, 6-4 = 2 ✓
**Looks correct**

---

## Conclusion

After 3 failed fixes, the root cause remains unclear. The issues are likely:
1. **Timing/sequencing** problems in the state machine
2. **Signal propagation** issues (decisions based on wrong instruction)
3. **Hidden bugs** in datapath connections

**Immediate Action Required**: Add debug visibility to RTL or create minimal test case with extensive logging to identify where the logic breaks down.

---

**END OF REPORT**
