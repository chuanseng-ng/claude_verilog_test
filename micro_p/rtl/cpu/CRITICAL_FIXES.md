# Critical AXI Protocol Fixes

Document created: 2026-01-19
Status: CRITICAL BUGS FIXED

## Issue Identified

User identified critical bugs in the AXI4-Lite protocol handling in `rv32i_control.sv` and `rv32i_core.sv`.

## Bug 1: Incorrect AXI Read Timing in FETCH State

### Problem

Original code in `rv32i_control.sv` FETCH state:

```systemverilog
FETCH: begin
  // INCORRECT: Assumes rvalid asserts same cycle as arready
  if (axi_arready && axi_arvalid) begin
    if (axi_rvalid) begin
      // ...
    end
  end
end
```

**Why this is wrong**:

In AXI4-Lite protocol, the address phase and data phase are **independent**:

1. **Address phase**: `arvalid && arready` → address handshake complete
2. **Data phase**: `rvalid && rready` → data handshake complete

**`rvalid` can come many cycles after `arready`** depending on memory latency. The original code would only transition to DECODE if all three signals (`arready`, `arvalid`, `rvalid`) were high in the same cycle, which violates the protocol and causes the CPU to hang waiting for an impossible condition.

### Fix

Updated FETCH state (rv32i_control.sv:75-88):

```systemverilog
FETCH: begin
  // Wait for AXI read data phase to complete
  // Note: Address phase (arvalid/arready) and data phase (rvalid/rready)
  // are independent. rvalid can come many cycles after arready.
  if (axi_rvalid && axi_rready) begin
    // Data received, check for AXI error
    if (axi_rresp != 2'b00) begin
      next_state = TRAP;  // AXI error -> illegal instruction trap
    end else begin
      next_state = DECODE;
    end
  end
  // Otherwise stay in FETCH state waiting for rvalid

  // Debug halt request during fetch
  if (dbg_halt_req) begin
    next_state = HALTED;
  end
end
```

**Key changes**:

- ✅ Only check `rvalid && rready` for data phase completion
- ✅ Don't check `arready` in the transition condition (address phase happens separately via output logic)
- ✅ Stay in FETCH state until data arrives (can be many cycles later)

---

## Bug 2: Incorrect AXI Read/Write Timing in MEM_WAIT State

### Problem

Original code had the same issue in MEM_WAIT state for load operations.

### Fix

Updated MEM_WAIT state (rv32i_control.sv:115-138):

```systemverilog
MEM_WAIT: begin
  if (mem_rd) begin
    // Load: wait for read data phase
    // Note: Address phase may have completed earlier
    if (axi_rvalid && axi_rready) begin
      if (axi_rresp != 2'b00) begin
        next_state = TRAP;  // AXI error
      end else begin
        next_state = WRITEBACK;
      end
    end
    // Otherwise stay in MEM_WAIT waiting for rvalid
  end else if (mem_wr) begin
    // Store: wait for write response phase
    // Note: Address and data phases may have completed earlier
    if (axi_bvalid && axi_bready) begin
      if (axi_bresp != 2'b00) begin
        next_state = TRAP;  // AXI error
      end else begin
        next_state = WRITEBACK;
      end
    end
    // Otherwise stay in MEM_WAIT waiting for bvalid
  end
end
```

**Key changes**:

- ✅ Loads: Only check `rvalid && rready` for completion
- ✅ Stores: Only check `bvalid && bready` for completion
- ✅ Address/data phases handled separately in output logic

---

## Bug 3: Missing AXI Address Mux

### Problem

Original code in `rv32i_core.sv`:

```systemverilog
// INCORRECT: Always uses PC for read address
assign axi_araddr = pc_reg;
```

**Why this is wrong**:

The CPU uses a unified instruction/data bus (AXI4-Lite), so `axi_araddr` must be multiplexed:

1. **During FETCH**: `araddr` = `pc_reg` (fetching instruction)
2. **During MEM_WAIT (loads)**: `araddr` = `mem_addr` (loading data from calculated address)

Without this mux, loads would incorrectly use the PC as the data address, causing all loads to fetch from the wrong memory location.

### Fix

Added control signal `data_access` to FSM (rv32i_control.sv:46):

```systemverilog
output logic        data_access      // 1=data access (MEM_WAIT), 0=instruction fetch (FETCH)
```

Drive `data_access` high in MEM_WAIT state (rv32i_control.sv:270):

```systemverilog
MEM_WAIT: begin
  data_access = 1'b1;  // Data access mode (not instruction fetch)
  // ...
end
```

Use `data_access` to mux `axi_araddr` (rv32i_core.sv:143-146):

```systemverilog
// AXI read address mux
// Select between instruction fetch (PC) and data access (mem_addr)
// - data_access=0 (FETCH state): araddr = PC (fetching instruction)
// - data_access=1 (MEM_WAIT state): araddr = mem_addr (loading data)
assign axi_araddr = data_access ? mem_addr : pc_reg;
```

**Key changes**:

- ✅ Added `data_access` control signal from FSM
- ✅ Mux `axi_araddr` based on CPU state
- ✅ FETCH uses PC, MEM_WAIT uses calculated address

---

## AXI Protocol Summary

### Correct AXI4-Lite Read Transaction

```text
Cycle 0:  Master asserts arvalid, araddr
Cycle 0:  Slave may or may not assert arready
Cycle N:  Slave asserts arready (address handshake complete)
          Master must keep arvalid high until arready seen
Cycle M:  Slave asserts rvalid, rdata, rresp (M >= N, can be many cycles later)
          Master asserts rready to accept data
Cycle M:  Data handshake complete (rvalid && rready)
```

**Key insight**: Address phase (cycle N) and data phase (cycle M) are independent. M can be >> N.

### Correct AXI4-Lite Write Transaction

```text
Cycle 0:  Master asserts awvalid, awaddr, wvalid, wdata, wstrb
Cycle 0:  Slave may or may not assert awready, wready
Cycle N:  Slave asserts awready (address handshake)
Cycle P:  Slave asserts wready (data handshake)
Cycle Q:  Slave asserts bvalid, bresp (write response, Q >= max(N,P))
          Master asserts bready to accept response
Cycle Q:  Response handshake complete (bvalid && bready)
```

---

## Files Modified

1. **`rtl/cpu/core/rv32i_control.sv`**
   - Fixed FETCH state transition logic (line 75-88)
   - Fixed MEM_WAIT state transition logic (line 115-138)
   - Added `data_access` output signal (line 46)
   - Set `data_access=1` in MEM_WAIT state (line 270)

2. **`rtl/cpu/core/rv32i_core.sv`**
   - Added `data_access` signal (line 104)
   - Connected `data_access` to control FSM (line 264)
   - Fixed `axi_araddr` mux (line 143-146)

---

## Impact

**Without these fixes**:

- ❌ CPU would hang in FETCH waiting for impossible AXI condition
- ❌ CPU would hang in MEM_WAIT for the same reason
- ❌ All load instructions would fetch data from wrong address (PC instead of calculated address)
- ❌ CPU completely non-functional

**With these fixes**:

- ✅ Proper AXI protocol compliance
- ✅ CPU can fetch instructions with variable memory latency
- ✅ CPU can execute load instructions correctly
- ✅ Unified instruction/data bus works correctly

---

## Testing Recommendations

### 1. AXI Protocol Compliance

Test with AXI slave that has variable latency:

```python
# cocotb testbench
class VariableLatencyAXISlave:
    async def handle_read(self, addr):
        # Randomize arready assertion (0-5 cycles)
        await Timer(random.randint(0, 5), units='ns')
        self.arready.value = 1
        await RisingEdge(self.clk)
        self.arready.value = 0

        # Randomize rvalid assertion (0-10 cycles after arready)
        await Timer(random.randint(0, 10), units='ns')
        self.rvalid.value = 1
        self.rdata.value = data
        await RisingEdge(self.clk)
        self.rvalid.value = 0
```

### 2. Load Instruction Testing

Verify load uses calculated address, not PC:

```python
# cocotb test
@cocotb.test()
async def test_load_address(dut):
    # Execute: LW x1, 100(x0)
    # Expected: araddr = 0 + 100 = 0x64 (NOT PC)

    pc_value = dut.u_core.pc_reg.value
    load_addr = 0x64

    # Wait for MEM_WAIT state
    await wait_for_state(dut, MEM_WAIT)

    # Check araddr is load address, not PC
    assert dut.axi_araddr.value == load_addr
    assert dut.axi_araddr.value != pc_value
```

### 3. State Machine Testing

Test FETCH → DECODE transition with delayed rvalid:

```python
@cocotb.test()
async def test_delayed_rvalid(dut):
    # FETCH state
    assert_state(dut, FETCH)

    # arvalid and arready both high
    await wait_for(dut.axi_arvalid & dut.axi_arready)

    # Wait several cycles before asserting rvalid
    await Timer(50, units='ns')

    # Assert rvalid
    dut.axi_rvalid.value = 1
    await RisingEdge(dut.clk)

    # Should transition to DECODE now
    assert_state(dut, DECODE)
```

---

## Status

**✅ CRITICAL BUGS FIXED**

All three critical AXI protocol bugs have been identified and corrected. The CPU should now:

1. Correctly wait for AXI data phase (rvalid) independent of address phase
2. Handle variable memory latency
3. Use the correct address for both instruction fetch and data loads

**Requires**: Human verification through simulation and testing.

---

## Review Checklist

Before approving these fixes, verify:

- [ ] FETCH state correctly waits for `rvalid` regardless of `arready` timing
- [ ] MEM_WAIT state correctly waits for `rvalid` (loads) or `bvalid` (stores)
- [ ] `data_access` signal correctly indicates FETCH vs MEM_WAIT state
- [ ] `axi_araddr` mux correctly selects PC vs mem_addr
- [ ] AXI handshake signals (`arvalid`, `rready`, etc.) are driven correctly in output logic
- [ ] Variable latency AXI slave works correctly with CPU
- [ ] Load instructions use calculated address, not PC

---

**Document end**
