# Instruction Fetch Timing Analysis

## Problem Statement

Branch/Jump/Load/Store instructions all fail despite correct logic. Investigating if the issue is related to when the instruction register updates.

---

## State Machine Flow

```text
RESET → FETCH → DECODE → EXECUTE → WRITEBACK → FETCH → ...
                                 ↓
                           MEM_WAIT (if mem_rd or mem_wr)
                                 ↓
                           WRITEBACK
```

---

## Detailed Cycle-by-Cycle Timeline (Non-Memory Instruction)

### Example: BEQ x1, x2, +8 at PC=0x00

**Assumptions:**

- SimpleAXIMemory responds in 1 cycle (sets rvalid in cycle after arvalid)
- rs1=42, rs2=42, so branch should be taken

---

### Cycle 1: FETCH (PC=0x00)

**State**: FETCH

**Control Outputs:**

```text
axi_arvalid = 1  // Request instruction
axi_rready  = 1  // Ready to receive
pc_wr_en    = 0
```

**Events:**

- CPU requests instruction at PC=0x00
- Memory sees arvalid=1, prepares to respond

---

### Cycle 2: FETCH → DECODE (Clock Edge)

**At Rising Edge:**

- Memory sets: `axi_rvalid=1`, `axi_rdata=0x00208463` (BEQ instruction)
- Condition met: `axi_rvalid && axi_rready && !data_access = 1`
- **Instruction register latches: instruction ← 0x00208463** ✓
- State register updates: `current_state ← DECODE`

**After Rising Edge (DECODE state):**

**State**: DECODE

**Decoder Outputs** (combinational from instruction=0x00208463):

```text
branch    = 1
branch_op = 000 (BEQ)
jump      = 0
rs1       = 1
rs2       = 2
...
```

**Control Outputs:**

```text
axi_arvalid = 0
axi_rready  = 0
```

---

### Cycle 3: DECODE → EXECUTE (Clock Edge)

**At Rising Edge:**

- State register updates: `current_state ← EXECUTE`

**After Rising Edge (EXECUTE state):**

**State**: EXECUTE

**Datapath:**

- Register file reads: `rs1_data=42`, `rs2_data=42`
- Branch comparator: `branch_taken = (rs1_data == rs2_data) = 1` ✓

**Control FSM:** (combinational)

```text
pc_wr_en = 0  // Don't update PC yet
```

**At END of Cycle (before next rising edge):**

- Register update in control.sv:

  ```text
  take_branch_jump_reg <= (branch && branch_taken) || jump
  take_branch_jump_reg <= (1 && 1) || 0 = 1  ✓
  ```

---

### Cycle 4: EXECUTE → WRITEBACK (Clock Edge) ⚠️ CRITICAL CYCLE

**At Rising Edge:**

- State register updates: `current_state ← WRITEBACK`
- **take_branch_jump_reg latches to 1** ✓

**After Rising Edge (WRITEBACK state):**

**State**: WRITEBACK

**Control Outputs:** (combinational)

```text
pc_wr_en         = 1      // Update PC
pc_src           = take_branch_jump_reg = 1  // Use branch target
regfile_wr_en    = reg_wr_en = 0  // BEQ doesn't write register
commit_valid     = 1
```

**Datapath:**

- PC update (combinational): `pc_next = pc_insn + imm = 0x00 + 0x08 = 0x08` ✓

**At END of Cycle (before next rising edge):**

- Nothing registered yet for PC

---

### Cycle 5: WRITEBACK → FETCH (Clock Edge) 🔥 **PROBLEM DETECTED**

**At Rising Edge:**

- State register updates: `current_state ← FETCH`
- **PC register updates: `pc_reg ← pc_next = 0x08`** ✓
- **What about instruction register?** 🤔

**After Rising Edge (FETCH state):**

**State**: FETCH

**Control Outputs:** (combinational)

```text
axi_arvalid = 1  // Request NEXT instruction
axi_rready  = 1
axi_araddr  = pc_reg = 0x08  // ✓ Correct address (branch target)
```

**Memory sees:** arvalid=1, araddr=0x08

---

### Cycle 6: FETCH (waiting for memory) ⚠️ **POTENTIAL ISSUE**

**State**: FETCH

**Memory Response:**

- Memory sets: `axi_rvalid=1`, `axi_rdata=0x00100213` (ADDI x4, x0, 1 - branch target)
- Condition: `axi_rvalid && axi_rready && !data_access = 1`
- **Instruction register updates: instruction ← 0x00100213** ✓

**Decoder Outputs** (NOW changed to ADDI):

```text
branch    = 0  ❌ Changed!
branch_op = ???
jump      = 0
...
```

**BUT WAIT:** We're still in FETCH state, decoder outputs don't matter yet.

---

## Key Question: When Does the Problem Occur?

Looking at the timing, **the instruction register update timing looks CORRECT**:

1. BEQ instruction loaded in cycle 2
2. Decoder sees BEQ in cycles 2-4 (DECODE, EXECUTE, WRITEBACK)
3. Branch decision made in cycle 3 (EXECUTE)
4. Branch decision registered in cycle 4
5. PC updated in cycle 5 based on registered decision
6. Next instruction fetched in cycle 6

**This should work!** So why doesn't it?

---

## Hypothesis: The Problem is NOT Timing

If the instruction fetch timing is correct, then the problem must be elsewhere:

### Possibility 1: Debug Register Writes Not Working ⚠️

The BEQ test uses APB debug interface to write x1=42, x2=42:

```python
await dbg.write_gpr(1, 42)  # Write x1
await dbg.write_gpr(2, 42)  # Write x2
```

**What if these writes don't actually work?**

- Register file would still have x1=0, x2=0
- Branch comparator would see 0==0, `branch_taken=1` ✓
- Branch SHOULD be taken!

**Unless...**

### Possibility 2: Register File Reads During Execution ⚠️

When does the register file read rs1_data and rs2_data?

Looking at rv32i_core.sv:

```systemverilog
rv32i_regfile u_regfile (
  .rd_addr1      (rs1),        // From decoder
  .rd_data1      (rs1_data),   // Combinational output
  .rd_addr2      (rs2),
  .rd_data2      (rs2_data),
  ...
);
```

Register file reads are **combinational**:

- `rs1` comes from decoder (based on instruction register)
- `rs1_data` is combinational based on `rs1`

**In EXECUTE state:**

- instruction = BEQ instruction
- Decoder outputs: rs1=1, rs2=2
- Register file outputs: rs1_data=regs[1], rs2_data=regs[2]

**This should work IF regs[1] and regs[2] were written!**

### Possibility 3: Debug Writes Require CPU to be Halted ⚠️ **LIKELY ISSUE!**

Looking at rv32i_cpu_top.sv line 257:

```systemverilog
if (apb_paddr >= 12'h010 && apb_paddr <= 12'h08C && apb_paddr[1:0] == 2'b00 && dbg_halted) begin
```

**Debug register writes REQUIRE `dbg_halted=1`!**

Let's check the test sequence:

```python
await dbg.halt_cpu()           # Halt CPU
await dbg.write_gpr(1, 42)     # Write x1 (should work - halted)
await dbg.write_gpr(2, 42)     # Write x2 (should work - halted)
mem.write_word(0x00000000, 0x00208463)  # Load BEQ
await dbg.resume_cpu()         # Resume CPU
await ClockCycles(dut.clk, 100)  # Run
await dbg.halt_cpu()           # Halt again
x3_val = await dbg.read_gpr(3)  # Check result
```

**The sequence looks correct!** Writes happen while halted.

---

## Alternative Hypothesis: PC Update Issue ⚠️

Let me check the PC update logic more carefully.

From rv32i_core.sv lines 136-151:

```systemverilog
always_comb begin
  if (pc_src) begin
    // Branch or jump taken
    if (jump && jalr) begin
      // JALR: PC = (rs1 + imm) & ~1
      pc_next = (rs1_data + immediate) & 32'hFFFF_FFFE;
    end else begin
      // JAL or Branch: PC = instruction_PC + imm
      // Use pc_insn (captured at fetch) instead of pc_reg
      pc_next = pc_insn + immediate;
    end
  end else begin
    // Normal: PC = PC + 4
    pc_next = pc_reg + 32'd4;
  end
end
```

**For BEQ:**

- `pc_src = 1` (branch taken)
- `jump = 0` (not a jump)
- Path taken: `pc_next = pc_insn + immediate`

**What is `pc_insn`?**

From lines 190-201, `pc_insn` is updated when:

```systemverilog
if (axi_rvalid && axi_rready && !data_access) begin
  if (axi_arvalid && axi_arready && !data_access) begin
    pc_insn <= axi_araddr;
  end else begin
    pc_insn <= fetch_addr;
  end
end
```

**When does this happen?**

- When instruction fetch completes (rvalid && rready)
- Updates to either `axi_araddr` (if AR and R happen same cycle) or `fetch_addr`

**For BEQ at PC=0x00:**

- Instruction fetched at PC=0x00
- When fetch completes: `pc_insn ← 0x00` ✓
- Branch target: `pc_next = 0x00 + 0x08 = 0x08` ✓

**This looks correct!**

---

## CRITICAL REALIZATION: Immediate Value! 🔥

**What is the immediate value for BEQ?**

BEQ instruction: `0x00208463`

```text
Bits [31:25] [24:20] [19:15] [14:12] [11:8] [7]   [6:0]
     0000000  00010   00001   000     0100   0    1100011
     imm[12]  rs2     rs1     funct3  imm[4:1] imm[11] opcode
     imm[10:5]
```

Let me decode this properly:

- opcode = 1100011 (branch) ✓
- rs1 = 00001 (x1) ✓
- rs2 = 00010 (x2) ✓
- funct3 = 000 (BEQ) ✓
- imm[11] = 0
- imm[4:1] = 0100
- imm[10:5] = 000000
- imm[12] = 0

**B-type immediate encoding:**
`imm[12:1] = {imm[12], imm[10:5], imm[4:1], imm[11]}`

From instruction:

```text
imm[12] = 0
imm[11] = 0
imm[10:5] = 000000
imm[4:1] = 0100 (binary 4)
imm[0] = 0 (always 0 for branches)
```

So: `imm = 0_0_000000_0100_0 = 0x08` ✓ Correct!

---

## Testing Hypothesis: What if branch_taken = 0?

If `rs1_data != rs2_data`, then:

- `branch_taken = 0`
- `take_branch_jump_reg = (branch && branch_taken) = 0`
- `pc_src = 0`
- `pc_next = pc_reg + 4 = 0x04` ✓ Falls through

**But the test says x3=99, which means ADDI at 0x04 WAS executed.**

This means:

- Either branch was taken and PC=0x08, but somehow came back to 0x04?
- Or branch was NOT taken and PC=0x04 (fall-through)

**The test expects x3=0 (skipped), but gets x3=99 (executed).**

**This confirms: Branch is NOT being taken when it should be!**

---

## Final Hypothesis: Signal Values are Wrong 🎯

The timing is correct, but the **signal values** must be wrong:

1. **Either:** `rs1_data` or `rs2_data` have wrong values (not 42)
2. **Or:** `branch_taken` is not being computed correctly
3. **Or:** `take_branch_jump_reg` is not being set
4. **Or:** `pc_src` is not using `take_branch_jump_reg`

**Need to add debug outputs to see actual signal values!**

---

## Conclusion

The instruction fetch timing appears **CORRECT**. The problem is likely:

1. **Debug register writes not actually writing to register file**
2. **Register file reads returning wrong values**
3. **Branch comparator not computing correctly**
4. **take_branch_jump_reg not being set**
5. **pc_src not being used correctly**

**NEXT STEP:** Add debug outputs to RTL to expose:

- `rs1_data`, `rs2_data` values during EXECUTE
- `branch_taken` signal
- `take_branch_jump_reg` value
- `pc_src` value during WRITEBACK

---

**END OF TIMING ANALYSIS**
