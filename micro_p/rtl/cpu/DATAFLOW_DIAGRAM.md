# Phase 1 RV32I CPU Dataflow Diagram

Document created: 2026-01-19

## Top-Level Block Diagram

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         rv32i_cpu_top.sv                                 │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                      rv32i_core.sv                                 │ │
│  │                                                                    │ │
│  │  ┌──────────┐   ┌────────────┐   ┌─────────────┐   ┌──────────┐  │ │
│  │  │    PC    │──▶│  Decoder   │──▶│  Imm Gen    │──▶│   ALU    │  │ │
│  │  │ Register │   │ rv32i_     │   │ rv32i_      │   │ rv32i_   │  │ │
│  │  │          │   │ decode.sv  │   │ imm_gen.sv  │   │ alu.sv   │  │ │
│  │  └──────────┘   └────────────┘   └─────────────┘   └──────────┘  │ │
│  │       ▲              │                                   │         │ │
│  │       │              │                                   │         │ │
│  │       │              ▼                                   ▼         │ │
│  │  ┌────────┐    ┌──────────────┐                  ┌──────────────┐ │ │
│  │  │Control │◀───│ Register File│◀─────────────────│ Write Data   │ │ │
│  │  │  FSM   │    │   rv32i_     │                  │     Mux      │ │ │
│  │  │        │    │ regfile.sv   │                  └──────────────┘ │ │
│  │  └────────┘    └──────────────┘                                   │ │
│  │       ▲              │     │                                       │ │
│  │       │              │     │                                       │ │
│  │       │              ▼     ▼                                       │ │
│  │       │         ┌─────────────────┐                               │ │
│  │       └─────────│  Branch Comp    │                               │ │
│  │                 │  rv32i_branch_  │                               │ │
│  │                 │  comp.sv        │                               │ │
│  │                 └─────────────────┘                               │ │
│  │                                                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                    APB3 Debug Interface                            │ │
│  │                  (Breakpoints, Halt/Resume)                        │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
     ▲                                                          ▲
     │                                                          │
 AXI4-Lite                                                   APB3
 (Memory)                                                  (Debug)
```

## Detailed Dataflow: Instruction Execution

### 1. FETCH Stage

```text
┌─────────────────────────────────────────────────────────────┐
│                        FETCH                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  PC Register ──▶ axi_araddr ──▶ AXI Read ──▶ Instruction   │
│     (32b)           (32b)        Transaction    Register    │
│                                                    (32b)     │
│                                                             │
│  Control FSM:                                               │
│  - Assert axi_arvalid                                       │
│  - Wait for axi_arready                                     │
│  - Wait for axi_rvalid                                      │
│  - Latch axi_rdata into instruction register                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2. DECODE Stage

```text
┌─────────────────────────────────────────────────────────────┐
│                       DECODE                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Instruction ──▶ rv32i_decode.sv                            │
│     (32b)                │                                  │
│                          ├──▶ rs1, rs2, rd (5b each)        │
│                          ├──▶ alu_op (4b)                   │
│                          ├──▶ alu_src_a, alu_src_b (1b)     │
│                          ├──▶ imm_fmt (3b)                  │
│                          ├──▶ reg_wr_en (1b)                │
│                          ├──▶ mem_rd, mem_wr (1b each)      │
│                          ├──▶ branch, jump, jalr (1b each)  │
│                          ├──▶ branch_op (3b)                │
│                          └──▶ illegal (1b)                  │
│                                                             │
│  Instruction ──▶ rv32i_imm_gen.sv                           │
│     (32b)                │                                  │
│  imm_fmt ───────────────┘                                   │
│                          │                                  │
│                          └──▶ immediate (32b)               │
│                                                             │
│  Register File:                                             │
│  rs1 ──▶ rd_addr1 ──▶ rd_data1 (rs1_data)                  │
│  rs2 ──▶ rd_addr2 ──▶ rd_data2 (rs2_data)                  │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 3. EXECUTE Stage

```text
┌─────────────────────────────────────────────────────────────┐
│                      EXECUTE                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ALU Operand A Mux:                                         │
│  ┌──────────────┐                                           │
│  │ alu_src_a=0  │──▶ rs1_data                               │
│  │ alu_src_a=1  │──▶ PC                                     │
│  └──────────────┘                                           │
│         │                                                   │
│         └────────▶ alu_operand_a                            │
│                                                             │
│  ALU Operand B Mux:                                         │
│  ┌──────────────┐                                           │
│  │ alu_src_b=0  │──▶ rs2_data                               │
│  │ alu_src_b=1  │──▶ immediate                              │
│  └──────────────┘                                           │
│         │                                                   │
│         └────────▶ alu_operand_b                            │
│                                                             │
│  rv32i_alu.sv:                                              │
│  ┌──────────────────────────────────┐                       │
│  │ alu_operand_a ──┐                │                       │
│  │ alu_operand_b ──┼──▶ ALU Logic   │──▶ alu_result (32b)  │
│  │ alu_op ─────────┘                │                       │
│  └──────────────────────────────────┘                       │
│                                                             │
│  rv32i_branch_comp.sv: (parallel to ALU)                    │
│  ┌──────────────────────────────────┐                       │
│  │ rs1_data ────┐                   │                       │
│  │ rs2_data ────┼──▶ Compare Logic  │──▶ branch_taken (1b) │
│  │ branch_op ───┘                   │                       │
│  └──────────────────────────────────┘                       │
│                                                             │
│  Branch/Jump Decision:                                      │
│  - If (branch && branch_taken): pc_src = 1                  │
│  - If (jump): pc_src = 1                                    │
│  - Else: pc_src = 0                                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 4. MEMORY Stage (if mem_rd or mem_wr)

```text
┌─────────────────────────────────────────────────────────────┐
│                      MEMORY                                 │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  LOAD (mem_rd = 1):                                         │
│  ┌─────────────────────────────────┐                        │
│  │ Address = alu_result            │                        │
│  │ axi_araddr ◀── alu_result       │                        │
│  │ axi_arvalid ◀── 1               │                        │
│  │                                 │                        │
│  │ Wait for axi_rvalid             │                        │
│  │ mem_rdata ◀── axi_rdata         │                        │
│  │                                 │                        │
│  │ Extract and sign-extend:        │                        │
│  │ - Byte: [7:0] with sign-ext     │                        │
│  │ - Halfword: [15:0] with sign-ext│                        │
│  │ - Word: [31:0] (no extension)   │                        │
│  └─────────────────────────────────┘                        │
│                                                             │
│  STORE (mem_wr = 1):                                        │
│  ┌─────────────────────────────────┐                        │
│  │ Address = alu_result            │                        │
│  │ axi_awaddr ◀── alu_result       │                        │
│  │ axi_awvalid ◀── 1               │                        │
│  │                                 │                        │
│  │ Data = rs2_data                 │                        │
│  │ axi_wdata ◀── rs2_data          │                        │
│  │                                 │                        │
│  │ Byte enable (wstrb):            │                        │
│  │ - Byte: 0001/0010/0100/1000     │                        │
│  │ - Halfword: 0011/1100           │                        │
│  │ - Word: 1111                    │                        │
│  │                                 │                        │
│  │ Wait for axi_bvalid             │                        │
│  └─────────────────────────────────┘                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 5. WRITEBACK Stage

```text
┌─────────────────────────────────────────────────────────────┐
│                    WRITEBACK                                │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Register Write Data Mux:                                   │
│  ┌──────────────────────────┐                               │
│  │ mem_rd = 1  ──▶ mem_rdata│                               │
│  │ jump = 1    ──▶ PC + 4   │──▶ rd_data (32b)             │
│  │ else        ──▶ alu_result│                              │
│  └──────────────────────────┘                               │
│         │                                                   │
│         └────────▶ rv32i_regfile.sv                         │
│                         │                                   │
│                         ├── wr_addr ◀── rd                  │
│                         ├── wr_data ◀── rd_data             │
│                         └── wr_en ◀── regfile_wr_en         │
│                                                             │
│  PC Update:                                                 │
│  ┌──────────────────────────┐                               │
│  │ pc_src = 0  ──▶ PC + 4   │                               │
│  │ pc_src = 1  ──▶ PC + imm │──▶ pc_next (32b)             │
│  │              or (rs1+imm)│      (JALR case)              │
│  └──────────────────────────┘                               │
│         │                                                   │
│         └────────▶ PC Register                              │
│                                                             │
│  Commit:                                                    │
│  commit_valid ◀── 1                                         │
│  commit_pc ◀── PC                                           │
│  commit_insn ◀── instruction                                │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

## Branch Comparator Integration Detail

```text
┌──────────────────────────────────────────────────────────────────┐
│             rv32i_branch_comp.sv Integration                     │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Inputs (from rv32i_core.sv):                                    │
│  ┌────────────────┐                                              │
│  │ rs1_data (32b) │──┐                                           │
│  │ rs2_data (32b) │──┼──▶ Branch Comparator                      │
│  │ branch_op (3b) │──┘                                           │
│  └────────────────┘                                              │
│                                                                  │
│  Branch Operations (funct3):                                     │
│  ┌──────────┬─────────┬────────────────────────┐                 │
│  │ Encoding │  Name   │ Condition              │                 │
│  ├──────────┼─────────┼────────────────────────┤                 │
│  │ 3'b000   │ BEQ     │ rs1 == rs2             │                 │
│  │ 3'b001   │ BNE     │ rs1 != rs2             │                 │
│  │ 3'b100   │ BLT     │ $signed(rs1) < rs2     │                 │
│  │ 3'b101   │ BGE     │ $signed(rs1) >= rs2    │                 │
│  │ 3'b110   │ BLTU    │ rs1 < rs2 (unsigned)   │                 │
│  │ 3'b111   │ BGEU    │ rs1 >= rs2 (unsigned)  │                 │
│  └──────────┴─────────┴────────────────────────┘                 │
│                                                                  │
│  Output:                                                         │
│  ┌─────────────────┐                                             │
│  │ branch_taken    │──▶ rv32i_control.sv (FSM)                   │
│  │ (1b)            │                                             │
│  └─────────────────┘                                             │
│                                                                  │
│  Timing:                                                         │
│  - Combinational logic (zero additional latency)                 │
│  - Evaluates in parallel with ALU during EXECUTE stage           │
│  - Result available for PC update in WRITEBACK stage             │
│                                                                  │
│  Usage in Control FSM:                                           │
│  ┌────────────────────────────────────────────────────┐          │
│  │ if (branch && branch_taken) {                      │          │
│  │   pc_src = 1;  // Update PC to branch target      │          │
│  │   pc_next = pc_reg + immediate;                   │          │
│  │ }                                                  │          │
│  └────────────────────────────────────────────────────┘          │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

## Control FSM State Diagram

```text
                    ┌─────────┐
                    │  RESET  │
                    └────┬────┘
                         │
                         ▼
                    ┌─────────┐
                    │  FETCH  │◀──────────────┐
                    └────┬────┘               │
                         │                    │
                         │ axi_rvalid         │
                         │                    │
                         ▼                    │
                    ┌─────────┐               │
                    │ DECODE  │               │
                    └────┬────┘               │
                         │                    │
                         │ !illegal           │
                         │                    │
                         ▼                    │
                    ┌─────────┐               │
                    │ EXECUTE │               │
                    └────┬────┘               │
                         │                    │
                    ┌────┴────┐               │
                    │         │               │
         mem_rd/mem_wr       else             │
                    │         │               │
                    ▼         ▼               │
              ┌──────────┐  ┌────────────┐   │
              │ MEM_WAIT │  │ WRITEBACK  │───┘
              └────┬─────┘  └────────────┘
                   │                ▲
                   │ AXI complete   │
                   │                │
                   └────────────────┘

         Debug Halt:
              Any State ──▶ HALTED
              HALTED ──(resume/step)──▶ FETCH

         Trap:
              DECODE/MEM_WAIT ──(error)──▶ TRAP ──▶ FETCH
```

## Module Signal Flow Summary

### rv32i_decode.sv

**In**: instruction (32b)
**Out**: rs1, rs2, rd (5b), alu_op (4b), control signals (multiple)

### rv32i_imm_gen.sv

**In**: instruction (32b), imm_fmt (3b)
**Out**: immediate (32b)

### rv32i_regfile.sv

**In**: clk, rst_n, wr_en, wr_addr (5b), wr_data (32b), rd_addr1 (5b), rd_addr2 (5b)
**Out**: rd_data1 (32b), rd_data2 (32b)

### rv32i_alu.sv

**In**: operand_a (32b), operand_b (32b), alu_op (4b)
**Out**: result (32b)

### rv32i_branch_comp.sv ⭐

**In**: rs1_data (32b), rs2_data (32b), branch_op (3b)
**Out**: branch_taken (1b)

### rv32i_control.sv

**In**: branch, jump, mem_rd, mem_wr, reg_wr_en, illegal_insn, branch_taken, AXI handshakes, debug signals
**Out**: pc_wr_en, pc_src, regfile_wr_en, commit_valid, trap_valid, AXI control signals

## Critical Paths (Timing)

### Longest Combinational Paths

1. **Instruction → Register File → ALU → Write Data**
   - instruction[31:0] → decode → rs1/rs2 → regfile → rs1_data/rs2_data → ALU → alu_result → rd_data mux → wr_data
   - **Estimated delay**: ~3-4ns @ Sky130

2. **Instruction → Register File → Branch Comp → PC Update**
   - instruction[31:0] → decode → rs1/rs2 → regfile → rs1_data/rs2_data → branch_comp → branch_taken → PC mux
   - **Estimated delay**: ~2-3ns @ Sky130

3. **PC → Instruction Fetch → Decode**
   - PC → AXI address → external memory → AXI data → instruction register
   - **Estimated delay**: Variable (AXI latency dependent)

## Verification Points

### Key Signals to Monitor

1. **PC progression**: Verify PC updates correctly (PC+4, branch target, jump target)
2. **Instruction commits**: Verify commit_valid pulses for each instruction
3. **Branch behavior**: Verify branch_taken matches expected condition
4. **Register writes**: Verify regfile updates on correct cycles
5. **Memory transactions**: Verify AXI handshakes follow protocol
6. **Debug interface**: Verify halt/resume/step behavior

### Scoreboard Comparison Points

- **PC value** at commit
- **Instruction** at commit
- **Register file state** after writeback
- **Memory writes** (address, data, strobes)
- **Branch taken/not-taken** decisions

## Summary

The RV32I CPU dataflow has been structured with:

1. **Clear pipeline stages**: FETCH → DECODE → EXECUTE → MEMORY → WRITEBACK
2. **Proper branch integration**: `rv32i_branch_comp.sv` evaluates in EXECUTE, informs PC update in WRITEBACK
3. **Modular design**: Each functional unit is a separate module
4. **Control FSM**: Orchestrates all stages and handles AXI protocol
5. **Debug support**: APB3 interface for halt/resume/step/breakpoints

**Branch comparator location**: Integrated in `rv32i_core.sv`, evaluates branch conditions in parallel with ALU during EXECUTE stage.
