# Phase 2 Architecture Specification

RV32I 5-Stage Pipelined CPU with Interrupt Support

Document status: APPROVED — All open questions resolved (2026-02-14). RTL implementation may begin.
Target audience: RTL Designer, Verification Engineer, Backend Engineer
Compliance reference: Phase 1 Architecture Specification, RISC-V ISA Volume I (RV32I + Zicsr)

**Prerequisites**: Phase 1 exit criteria must be met (all 9/9 verified on 2026-02-13)

---

## 1. Overview

Phase 2 transforms the single-cycle Phase 1 CPU into a 5-stage in-order pipeline. The primary goals are:

- **Throughput**: Approach 1 IPC at 200 MHz (2x frequency vs Phase 1's 100 MHz target)
- **Interrupt support**: RISC-V M-mode interrupts (timer + external) with minimal CSR set
- **Backward compatibility**: Identical AXI4-Lite and APB3 external interfaces as Phase 1
- **Incremental design**: Reuse Phase 1 leaf modules (ALU, regfile, imm_gen, branch_comp, decoder with additions); replace the monolithic FSM with pipelined datapath

### 1.1 What Changes from Phase 1

| Aspect | Phase 1 | Phase 2 |
|--------|---------|---------|
| Execution model | Single-cycle FSM | 5-stage in-order pipeline |
| Target frequency | 100 MHz | 200 MHz |
| Interrupt support | None | M-mode (timer + external) |
| CSR instructions | Illegal (trap) | CSRRW/S/C/I variants |
| Hazard handling | N/A (one instruction at a time) | Detect + stall + forward |
| AXI bus arbitration | Sequential (IF then MEM) | Priority arbiter (IF vs MEM) |
| Debug halt | Immediate (any state) | Drain pipeline then halt |
| Commit signal | FSM WRITEBACK state | WB stage retire |

### 1.2 What Does NOT Change from Phase 1

- External port names and signal widths on `rv32i_cpu_top` (AXI4-Lite + APB3 + commit interface)
- Active-low synchronous reset (`rst_n_i`)
- Single clock domain
- RISC-V RV32I base instruction semantics
- x0 hardwired to zero
- Debug register map (MEMORY_MAP.md) — same APB3 address space
- Trap vector at 0x0000_0000 for Phase 2 (upgraded to `mtvec` in this phase)
- Naturally aligned memory only (misaligned = trap)

---

## 2. Microarchitecture

### 2.1 Five-Stage Pipeline Overview

```
Clock:   ___   ___   ___   ___   ___   ___   ___   ___
        |   | |   | |   | |   | |   | |   | |   | |   |

Instr 1: [IF ] [ID ] [EX ] [MEM] [WB ]
Instr 2:       [IF ] [ID ] [EX ] [MEM] [WB ]
Instr 3:             [IF ] [ID ] [EX ] [MEM] [WB ]
Instr 4:                   [IF ] [ID ] [EX ] [MEM] [WB ]
```

| Stage | Name | Function |
|-------|------|----------|
| IF | Instruction Fetch | Present PC on AXI AR channel; latch instruction from AXI R channel |
| ID | Instruction Decode | Decode instruction; read register file; generate immediate; detect CSR access |
| EX | Execute | ALU operation; branch/jump resolution; address calculation; interrupt check |
| MEM | Memory | Load/store via AXI; CSR read/write |
| WB | Write Back | Write result to register file; retire instruction; update commit interface |

### 2.2 Pipeline Registers

Four sets of pipeline registers separate the five stages. All pipeline registers are clocked on the positive edge and reset to safe NOP values on `rst_n` or flush.

#### IF/ID Pipeline Register

Captures the fetched instruction and its PC.

```systemverilog
typedef struct packed {
    logic [31:0] pc;          // PC of fetched instruction
    logic [31:0] instruction; // Fetched instruction word
    logic        valid;       // 1 = instruction valid (0 after flush/stall insert)
} if_id_reg_t;
```

Reset/flush value: `'{pc: '0, instruction: 32'h0000_0013, valid: 1'b0}` (NOP)

#### ID/EX Pipeline Register

Captures all decode outputs and register-read results.

```systemverilog
typedef struct packed {
    logic [31:0] pc;           // Instruction PC (for branch/jump target, JAL return address)
    logic [31:0] rs1_data;     // Register file rs1 read result
    logic [31:0] rs2_data;     // Register file rs2 read result
    logic [31:0] immediate;    // Sign-extended immediate
    logic [4:0]  rs1_addr;     // rs1 address (for forwarding detection)
    logic [4:0]  rs2_addr;     // rs2 address (for forwarding detection)
    logic [4:0]  rd_addr;      // Destination register address
    logic [3:0]  alu_op;       // ALU operation encoding
    logic [1:0]  alu_src_a;    // ALU A mux select: 00=rs1, 01=PC, 10=zero
    logic        alu_src_b;    // ALU B mux select: 0=rs2, 1=imm
    logic        reg_wr_en;    // Register write enable
    logic        mem_rd;       // Load operation
    logic        mem_wr;       // Store operation
    logic [2:0]  mem_size;     // 000=byte, 001=half, 010=word
    logic        mem_unsigned; // Unsigned load
    logic        branch;       // Branch instruction
    logic [2:0]  branch_op;    // Branch comparison type
    logic        jump;         // JAL or JALR
    logic        jalr;         // JALR (register-relative)
    logic        csr_access;   // CSR read/write instruction
    logic [11:0] csr_addr;     // 12-bit CSR address
    logic [2:0]  csr_op;       // CSR operation (funct3: RW/RS/RC/RWI/RSI/RCI)
    logic        ebreak;       // EBREAK instruction
    logic        illegal;      // Illegal instruction
    logic        valid;        // Stage valid
} id_ex_reg_t;
```

Reset/flush value: All control signals 0, valid=0.

#### EX/MEM Pipeline Register

Captures ALU result, branch decision, store data, and CSR write value.

```systemverilog
typedef struct packed {
    logic [31:0] pc;           // Instruction PC
    logic [31:0] alu_result;   // ALU output (also used as memory address)
    logic [31:0] rs2_data;     // Store data (after forwarding)
    logic [31:0] csr_rdata;    // CSR read data (available from EX stage)
    logic [4:0]  rd_addr;      // Destination register address
    logic        reg_wr_en;    // Register write enable
    logic        mem_rd;       // Load operation
    logic        mem_wr;       // Store operation
    logic [2:0]  mem_size;     // Memory access size
    logic        mem_unsigned; // Unsigned load
    logic        csr_access;   // CSR instruction
    logic [11:0] csr_addr;     // CSR address
    logic [31:0] csr_wdata;    // Value to write into CSR (from EX stage)
    logic        branch_taken; // Branch resolved as taken
    logic        jump;         // Jump instruction
    logic        jalr;         // JALR
    logic        pc_redirect;  // 1 = pipeline must be flushed and PC redirected
    logic [31:0] pc_target;    // Redirect target address
    logic        trap_valid;   // Trap/interrupt taken this instruction
    logic [31:0] trap_cause;   // Full 32-bit mcause value (bit31=interrupt, [3:0]=code)
    logic        valid;        // Stage valid
} ex_mem_reg_t;
```

#### MEM/WB Pipeline Register

Captures memory read data for forwarding and final writeback.

```systemverilog
typedef struct packed {
    logic [31:0] pc;           // Instruction PC
    logic [31:0] alu_result;   // ALU result (non-load writeback data)
    logic [31:0] mem_rdata;    // Loaded and byte-extracted data
    logic [31:0] csr_rdata;    // CSR read data to write to rd
    logic [4:0]  rd_addr;      // Destination register address
    logic        reg_wr_en;    // Register write enable
    logic        mem_rd;       // Was this a load (selects mem_rdata for writeback)
    logic        csr_access;   // CSR instruction (selects csr_rdata for writeback)
    logic        jump;         // JAL/JALR (selects PC+4 for writeback)
    logic        trap_valid;   // Trap taken this cycle
    logic [31:0] trap_cause;   // mcause value
    logic        valid;        // Stage valid
} mem_wb_reg_t;
```

### 2.3 ASCII Data Path Diagram

```
                          5-Stage Pipeline Data Path
  =========================================================================

  ┌─────────────────────────────────────────────────────────────────────┐
  │                         AXI Arbiter                                 │
  │   IF request ──────────────────────────┐                            │
  │   MEM request ─────────────────────────┼──► AXI4-Lite Master        │
  └───────────────────────────────────────────────────────────────────── ┘

         IF                 ID                 EX               MEM              WB
  ┌──────────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────┐   ┌───────────┐
  │              │   │              │   │            │   │           │   │           │
  │  PC ──────►AXI   │ Decode ──────►   │  ALU ──────►  │ AXI Load/ │   │ Regfile   │
  │  Insn reg    │   │ Regfile read │   │  Branch    │   │ Store     │   │ write     │
  │              │   │ Imm gen      │   │  Compare   │   │ CSR RW    │   │           │
  │              │   │ CSR detect   │   │  Interrupt │   │           │   │ commit_   │
  │              │   │              │   │  check     │   │           │   │ valid     │
  └──────┬───────┘   └──────┬───────┘   └─────┬──────┘   └─────┬─────┘   └─────┬─────┘
         │                  │                  │                │               │
     IF/ID reg          ID/EX reg          EX/MEM reg      MEM/WB reg          │
         │                  │                  │                │               │
         └──────────────────┴──────────────────┴────────────────┘               │
                                                                                │
  Forwarding paths:                                                             │
    EX→EX:  EX/MEM.alu_result ──────────────────────────────► ID/EX ALU A/B   │
    MEM→EX: MEM/WB.{alu_result|mem_rdata} ──────────────────► ID/EX ALU A/B   │
    WB→EX:  WB rd_data ──────────────────────────────────────► ID/EX ALU A/B  │
                                                                                │
  Hazard Unit inputs:                                                           │
    ID/EX.rs1_addr, ID/EX.rs2_addr                                             │
    EX/MEM.rd_addr, EX/MEM.mem_rd, EX/MEM.reg_wr_en                           │
    MEM/WB.rd_addr, MEM/WB.reg_wr_en                                           │
                                                                                │
  Hazard Unit outputs:                                                          │
    stall_if, stall_id, flush_id, flush_ex                                      │
    fwd_a_sel[1:0], fwd_b_sel[1:0]                                             │
```

### 2.4 Key Design Decisions

**Decision 1: Branch resolution in EX stage**

- Branches are resolved in the EX stage (ALU + branch comparator available)
- Branch comparator takes forwarded operands
- On a taken branch: flush IF and ID stages (2-cycle penalty)
- On not-taken branch: no flush (normal pipeline flow continues)
- Rationale: EX resolution is the standard choice for 5-stage pipelines; ID resolution requires a dedicated comparator and complicates forwarding

**Decision 2: JAL resolved in ID stage**

- JAL target = PC + offset is computable in ID (PC known, offset in immediate)
- Flush only the IF stage (1-cycle penalty)
- Rationale: JAL is common in function calls; saving 1 cycle vs EX resolution reduces code execution time

**Decision 3: JALR resolved in EX stage**

- JALR target = (rs1 + imm) & ~1 requires the register value → must wait for EX
- Flush IF and ID stages (2-cycle penalty)
- Rationale: Same as branches; register data is not available in ID without stalling anyway

**Decision 4: No branch prediction**

- Phase 2 uses a static "not taken" assumption (no prediction hardware)
- Branch penalty is fixed: 2 cycles for taken branch, 0 for not-taken
- Rationale: Keeps hardware simple; branch prediction deferred to Phase 3+

**Decision 5: Register file bypass policy**

- Register file reads are combinational (as in Phase 1)
- Forwarding covers EX→EX, MEM→EX, and WB→EX paths
- No WB→ID bypass needed because WB completes before ID needs the value (the WB write and the regfile read of the next instruction happen on the same clock edge; regfile read takes priority by using registered WB write data)
- A load-use hazard (load followed immediately by dependent instruction) requires 1 stall cycle; forwarding alone cannot cover it because MEM data is not available until end of MEM stage

**Decision 6: AXI bus arbitration for IF vs MEM**

- Phase 1 used sequential: IF first, then MEM
- Phase 2 needs concurrent IF and MEM access → priority arbiter required
- **MEM wins over IF** when both request simultaneously (a load/store is on the critical path; IF can be stalled)
- When MEM wins, IF stage is stalled (PC held, IF/ID register frozen)
- Rationale: Memory hazards stall the pipeline anyway; prioritizing MEM reduces total latency

**Decision 7: Debug halt — drain then halt**

- Phase 1 halted immediately at any FSM state
- Phase 2 must drain the pipeline to a consistent architectural state before halting
- Halt request: stop accepting new IF requests, allow in-flight instructions to complete, then enter HALTED state
- This ensures the PC visible via DBG_PC reflects the next instruction to execute
- Rationale: Pipelined halting mid-stream leaves instructions in ambiguous state; architectural correctness requires a clean drain

**Decision 8: Interrupt taken at instruction boundaries**

- Interrupts are checked at the start of the EX stage
- When an enabled interrupt is pending and `mstatus.MIE = 1`, the instruction entering EX is squashed and replaced by a trap-entry sequence
- The flushed instructions (IF and ID stages) are discarded
- Rationale: Instruction-boundary interrupts ensure precise interrupt semantics; the interrupt appears to have been taken before the instruction that was in EX

---

## 3. Hazard Handling Strategy

### 3.1 Data Hazards — RAW Forwarding

RAW (Read-After-Write) hazards occur when a later instruction reads a register being written by an earlier instruction still in the pipeline.

**Forwarding paths**:

| Path | Source Stage | Destination | Condition |
|------|-------------|-------------|-----------|
| EX→EX | EX/MEM.alu_result | ID/EX ALU operand A or B | EX/MEM.rd_addr == ID/EX.rs1_addr (or rs2_addr) AND EX/MEM.reg_wr_en AND rd_addr != 0 |
| MEM→EX | MEM/WB.result | ID/EX ALU operand A or B | MEM/WB.rd_addr == ID/EX.rs1_addr (or rs2_addr) AND MEM/WB.reg_wr_en AND rd_addr != 0 |
| WB→EX | WB rd_data | ID/EX ALU operand A or B | WB.rd_addr == ID/EX.rs1_addr (or rs2_addr) AND WB.reg_wr_en AND rd_addr != 0 |

**Forwarding mux encoding** (`fwd_a_sel`, `fwd_b_sel`):

| Value | Meaning |
|-------|---------|
| 2'b00 | Use register file output (no forwarding) |
| 2'b01 | Forward from EX/MEM (EX→EX path) |
| 2'b10 | Forward from MEM/WB (MEM→EX path) |
| 2'b11 | Reserved (must not occur; use WB write port directly) |

**Priority rule**: EX/MEM takes priority over MEM/WB when both would match (the more recent write wins).

**Store data forwarding**: The forwarding mux for `rs2_data` (store data) in the EX/MEM register must also be forwarded because stores use rs2 as write data. The same `fwd_b_sel` signal applies.

### 3.2 Load-Use Hazard — 1-Cycle Stall

A load-use hazard occurs when the instruction immediately following a load reads the loaded register.

```
Cycle:  1    2    3    4    5    6    7
LW  :  [IF] [ID] [EX] [MEM][WB ]
ADD :       [IF] [ID] [ID] [EX] [MEM][WB]   ← stalled 1 cycle in ID
```

**Detection** (in hazard unit, evaluated each cycle):
```
load_use_hazard = id_ex.mem_rd AND
                  id_ex.rd_addr != 0 AND
                  (id_ex.rd_addr == if_id.rs1_addr OR
                   id_ex.rd_addr == if_id.rs2_addr)
```

**Action** on detection:
1. Stall IF (freeze PC register and IF/ID register)
2. Stall ID (freeze ID/EX register)
3. Insert bubble into EX (flush ID/EX → NOP for next cycle's EX stage)

Note: The "stall ID" and "insert bubble" happen simultaneously: the ID/EX register keeps its current values for one more cycle, and a NOP propagates into the EX stage on the stalled cycle.

### 3.3 Control Hazards — Flush Policy

| Instruction | Resolution Stage | Flush | Penalty |
|-------------|-----------------|-------|---------|
| Branch (taken) | EX | IF and ID | 2 cycles |
| Branch (not-taken) | EX | None | 0 cycles |
| JAL | ID | IF | 1 cycle |
| JALR | EX | IF and ID | 2 cycles |
| Trap/Interrupt | EX | IF and ID | 2 cycles |

**Flush implementation**: Set `valid=0` in the flushed pipeline registers (IF/ID, ID/EX). On the next cycle, those stages produce NOPs that propagate harmlessly through the pipeline.

**PC redirect**: When a flush is required, the PC register is overwritten with the redirect target:
- Taken branch: `pc_insn_ex + branch_offset`
- JAL: `pc_insn_id + jal_offset` (ID-stage redirect)
- JALR: `(rs1_data_forwarded + imm) & ~1`
- Trap/Interrupt: `mtvec` register value

### 3.4 Structural Hazards — AXI Stall Propagation

When the AXI bus is stalled (waiting for memory response), all pipeline stages must freeze:

**AXI-IF stall** (instruction fetch waiting for `axi_rvalid`):
- Stall IF stage (hold PC, freeze IF/ID register)
- All downstream stages continue normally

**AXI-MEM stall** (load/store waiting for `axi_rvalid` or `axi_bvalid`):
- Stall IF, ID, EX, and MEM stages simultaneously
- Hold all pipeline registers frozen
- This is equivalent to a global pipeline freeze for load/store latency

**Why global freeze for MEM stall**: With a unified AXI bus, when MEM stage holds the bus, IF cannot proceed either (the arbiter grants MEM priority). Freezing all stages is safe because no architectural state has been committed yet for instructions in IF/ID/EX.

### 3.5 Hazard Detection Unit Interface

```systemverilog
module rv32i_hazard_unit (
    // From ID/EX register (instruction currently in EX)
    input  logic [4:0]  id_ex_rs1_addr,
    input  logic [4:0]  id_ex_rs2_addr,
    input  logic [4:0]  id_ex_rd_addr,
    input  logic        id_ex_mem_rd,
    input  logic        id_ex_reg_wr_en,

    // From EX/MEM register (instruction currently in MEM)
    input  logic [4:0]  ex_mem_rd_addr,
    input  logic        ex_mem_reg_wr_en,
    input  logic        ex_mem_mem_rd,

    // From MEM/WB register (instruction currently in WB)
    input  logic [4:0]  mem_wb_rd_addr,
    input  logic        mem_wb_reg_wr_en,

    // From IF/ID register (instruction currently in ID — needed for load-use)
    input  logic [4:0]  if_id_rs1_addr,
    input  logic [4:0]  if_id_rs2_addr,

    // AXI stall indicators
    input  logic        if_axi_stall,     // IF stage waiting for instruction fetch
    input  logic        mem_axi_stall,    // MEM stage waiting for load/store

    // Branch/jump/trap flush (from EX stage)
    input  logic        ex_pc_redirect,   // Flush needed (branch taken/jump/trap)

    // JAL flush (from ID stage)
    input  logic        id_jal_taken,     // JAL detected in ID → flush IF

    // Outputs — pipeline control
    output logic        stall_pc,         // Hold PC register
    output logic        stall_if_id,      // Hold IF/ID register
    output logic        stall_id_ex,      // Hold ID/EX register
    output logic        stall_ex_mem,     // Hold EX/MEM register
    output logic        flush_if_id,      // Clear IF/ID (insert NOP)
    output logic        flush_id_ex,      // Clear ID/EX (insert NOP)

    // Outputs — forwarding selects
    output logic [1:0]  fwd_a_sel,        // ALU A forwarding select
    output logic [1:0]  fwd_b_sel,        // ALU B forwarding select
    output logic [1:0]  fwd_store_sel     // Store data (rs2) forwarding select
);
```

---

## 4. Interrupt Architecture

### 4.1 RISC-V M-Mode Interrupt Overview

Phase 2 implements a minimal M-mode interrupt subsystem per the RISC-V Privileged Architecture specification, supporting:
- Machine timer interrupt (MTIP in `mip`)
- Machine external interrupt (MEIP in `mip`)

All interrupts operate in Machine mode (the only privilege level implemented). No U-mode or S-mode.

### 4.2 CSR Register Set (Minimal — Phase 2)

| CSR Address | Name | Description |
|:-----------:|------|-------------|
| 0x300 | `mstatus` | Machine status register |
| 0x304 | `mie` | Machine interrupt enable |
| 0x305 | `mtvec` | Trap vector base address |
| 0x341 | `mepc` | Exception PC |
| 0x342 | `mcause` | Trap cause |
| 0x344 | `mip` | Machine interrupt pending (read-only from software view) |
| 0xF11 | `mvendorid` | Vendor ID (read-only, 0x0) |
| 0xF12 | `marchid` | Architecture ID (read-only, 0x0) |
| 0xF13 | `mimpid` | Implementation ID (read-only, phase-specific) |
| 0xF14 | `mhartid` | Hardware thread ID (read-only, 0x0) |

#### mstatus — Machine Status Register (0x300)

Only the following bits are implemented. All other bits read as 0 and writes are ignored.

| Bits | Field | Description |
|------|-------|-------------|
| [3] | MIE | Machine Interrupt Enable (1=enabled, 0=disabled) |
| [7] | MPIE | Machine Prior Interrupt Enable (saved MIE on trap entry) |
| [12:11] | MPP | Machine Previous Privilege (hardwired to 2'b11 in Phase 2 — always M-mode) |

**Trap entry behavior**: `MPIE ← MIE; MIE ← 0; MPP ← current_privilege (11)`
**MRET behavior**: `MIE ← MPIE; MPIE ← 1; PC ← mepc`

#### mie — Machine Interrupt Enable (0x304)

| Bits | Field | Description |
|------|-------|-------------|
| [7] | MTIE | Machine Timer Interrupt Enable |
| [11] | MEIE | Machine External Interrupt Enable |

All other bits read as 0.

#### mtvec — Trap Vector (0x305)

| Bits | Field | Description |
|------|-------|-------------|
| [31:2] | BASE | 4-byte aligned trap handler base address |
| [1:0] | MODE | 0=Direct (all traps jump to BASE), 1=Vectored (Phase 3+) |

**Phase 2 restriction**: Only Direct mode (MODE=0) is supported. If software writes MODE!=0, the MODE field is forced to 0.

Default value after reset: 0x0000_0000 (matches Phase 1 behavior — trap vector at address 0).

#### mepc — Machine Exception PC (0x341)

Holds the PC of the instruction that was interrupted or caused an exception. On MRET, PC is restored from mepc. Software can write mepc for exception return address modification.

#### mcause — Machine Cause Register (0x342)

| Bits | Field | Description |
|------|-------|-------------|
| [31] | Interrupt | 1=interrupt, 0=exception |
| [30:0] | Exception Code | Cause code |

Implemented cause codes:

| mcause | Type | Description |
|--------|------|-------------|
| 0x80000007 | Interrupt | Machine timer interrupt |
| 0x8000000B | Interrupt | Machine external interrupt |
| 0x00000002 | Exception | Illegal instruction |
| 0x00000004 | Exception | Load address misaligned |
| 0x00000006 | Exception | Store/AMO address misaligned |
| 0x00000003 | Exception | Breakpoint (EBREAK) |

**Note**: In Phase 1, EBREAK caused a debug halt without setting mcause. In Phase 2, EBREAK also sets `mcause=3` before halting. The debug interface still halts the CPU; the EBREAK trap behavior is additionally recorded in mcause.

#### mip — Machine Interrupt Pending (0x344)

Read-only from software perspective; bits are set by hardware interrupt inputs.

| Bits | Field | Description |
|------|-------|-------------|
| [7] | MTIP | Machine Timer Interrupt Pending (driven by `timer_irq_i`) |
| [11] | MEIP | Machine External Interrupt Pending (driven by `ext_irq_i`) |

### 4.3 CSR Instruction Set (Zicsr Extension)

Six CSR instructions are added to the decoder:

| Instruction | funct3 | Description |
|-------------|--------|-------------|
| CSRRW rd, csr, rs1 | 3'b001 | Atomic read/write CSR |
| CSRRS rd, csr, rs1 | 3'b010 | Atomic read/set bits in CSR |
| CSRRC rd, csr, rs1 | 3'b011 | Atomic read/clear bits in CSR |
| CSRRWI rd, csr, uimm | 3'b101 | Atomic read/write CSR (immediate) |
| CSRRSI rd, csr, uimm | 3'b110 | Atomic read/set bits in CSR (immediate) |
| CSRRCI rd, csr, uimm | 3'b111 | Atomic read/clear bits in CSR (immediate) |

**MRET instruction**: Opcode `SYSTEM (0x73)`, funct3=0, funct7=0x18, rs2=0x02. Decoded as a special instruction type.

**CSR access semantics**:
- `CSRRW`: `rd ← CSR; CSR ← rs1` (if rd=x0, CSR write but no read side-effect)
- `CSRRS`: `rd ← CSR; CSR ← CSR | rs1` (if rs1=x0, no write)
- `CSRRC`: `rd ← CSR; CSR ← CSR & ~rs1` (if rs1=x0, no write)
- `CSRRWI/CSRRSI/CSRRCI`: Same but use zero-extended 5-bit immediate instead of rs1

**Illegal CSR access**: Accessing an unimplemented CSR address is an illegal instruction trap.

### 4.4 Interrupt Input Signals

Two new input ports are added to `rv32i_cpu_top`:

```systemverilog
input  logic  ext_irq_i,    // External interrupt request (level-sensitive, active-high)
input  logic  timer_irq_i,  // Timer interrupt request (level-sensitive, active-high)
```

Both signals are **level-sensitive** (not edge-triggered). Software must clear the interrupt source before returning from the handler (the interrupt will re-fire if the source remains asserted).

Both signals are **synchronous** to `clk_i` and require no metastability synchronizer within the CPU (the SoC integration must synchronize external signals before connecting to the CPU).

### 4.5 Interrupt Handling Flow

**Interrupt take sequence** (occurs at start of EX stage, before instruction execution):

```
1. Check: mstatus.MIE == 1 AND (mie.MTIE AND mip.MTIP) OR (mie.MEIE AND mip.MEIP)
2. If interrupt pending and enabled:
   a. mepc ← ID/EX.pc  (PC of the instruction being squashed)
   b. mcause ← interrupt cause (priority: external > timer)
   c. mstatus.MPIE ← mstatus.MIE
   d. mstatus.MIE ← 0
   e. mstatus.MPP ← 2'b11
   f. Flush IF and ID pipeline stages
   g. Redirect PC to mtvec (direct mode: jump to BASE address)
   h. Squash EX stage instruction (convert to NOP bubble)
```

**Interrupt latency**: Maximum 2 cycles from interrupt assertion to first instruction of handler executing in IF stage.
- Cycle 0: Interrupt asserted; instruction at EX stage checks interrupt enable
- Cycle 1: Flush IF and ID; CSRs updated; PC redirected to mtvec
- Cycle 2: First handler instruction in IF stage

**MRET sequence** (executes as a normal instruction in EX stage):

```
1. PC ← mepc
2. mstatus.MIE ← mstatus.MPIE
3. mstatus.MPIE ← 1
4. Flush IF and ID pipeline stages (PC redirect)
```

### 4.6 Nested Interrupts — Disabled in Phase 2

Nested interrupts are NOT supported in Phase 2. Rationale:

1. When a trap is taken, `mstatus.MIE` is cleared to 0, preventing any further interrupts from being taken during the handler
2. The handler must explicitly re-enable interrupts (`CSRRS mstatus, mstatus, MIE_BIT`) if nesting is desired
3. Since `MIE=0` during handler execution, nested interrupts cannot occur without explicit software action
4. This matches the RISC-V specification's default trap behavior

This is consistent with the RISC-V specification and is the expected behavior. Document this explicitly so verification does not expect nested interrupt delivery without MRET + re-enable.

---

## 5. RTL Module Hierarchy

### 5.1 Module Hierarchy Diagram

```
rv32i_cpu_top_v2                    # Top-level (same external interface as Phase 1)
├── rv32i_core_v2                   # Pipelined CPU core wrapper
│   ├── rv32i_pipeline_if           # IF stage + AXI-IF interface
│   ├── rv32i_pipeline_id           # ID stage (decode + regfile read + imm gen)
│   │   ├── rv32i_decode            # REUSED from Phase 1 (with additions)
│   │   └── rv32i_imm_gen           # REUSED from Phase 1 (unchanged)
│   ├── rv32i_pipeline_ex           # EX stage (ALU + branch + interrupt check)
│   │   ├── rv32i_alu               # REUSED from Phase 1 (unchanged)
│   │   └── rv32i_branch_comp       # REUSED from Phase 1 (unchanged)
│   ├── rv32i_pipeline_mem          # MEM stage + AXI-MEM interface
│   ├── rv32i_pipeline_wb           # WB stage (regfile write + commit)
│   │   └── rv32i_regfile           # REUSED from Phase 1 (unchanged)
│   ├── rv32i_hazard_unit           # NEW: Stall and forward control
│   ├── rv32i_forwarding_unit       # NEW: Forwarding mux selects
│   ├── rv32i_csr_file              # NEW: CSR register file
│   └── rv32i_interrupt_ctrl        # NEW: Interrupt priority and masking
├── rv32i_axi_arbiter               # NEW: IF vs MEM AXI arbitration
└── rv32i_debug_v2                  # UPDATED: Pipeline-aware debug controller
```

### 5.2 Module Reuse vs New Development

#### Unchanged from Phase 1

| Module | File | Notes |
|--------|------|-------|
| `rv32i_alu` | `rtl/cpu/core/rv32i_alu.sv` | No changes needed; all RV32I ALU ops already implemented |
| `rv32i_regfile` | `rtl/cpu/core/rv32i_regfile.sv` | No changes; combinational reads and debug write port preserved |
| `rv32i_imm_gen` | `rtl/cpu/core/rv32i_imm_gen.sv` | No changes; all immediate formats already supported |
| `rv32i_branch_comp` | `rtl/cpu/core/rv32i_branch_comp.sv` | No changes; all branch comparisons already implemented |

#### Modified from Phase 1

| Module | File | Modifications |
|--------|------|--------------|
| `rv32i_decode` | `rtl/cpu/core/rv32i_decode.sv` | Add CSR instruction decoding (CSRRW/S/C/I, MRET); add `csr_access`, `csr_addr`, `csr_op` outputs; EBREAK now generates `trap_cause=3` (breakpoint) instead of only `ebreak` signal |
| `rv32i_cpu_top` | `rtl/cpu/rv32i_cpu_top.sv` | Add `ext_irq_i`, `timer_irq_i` ports; update debug logic for pipeline-aware halt; rename to `rv32i_cpu_top_v2` OR update in-place (human decision required — see Section 9) |
| APB debug registers | In `rv32i_cpu_top` | Add CSR access via APB for debug visibility; DBG_PC now reads `mepc` when halted during interrupt handler |

#### New Modules

| Module | File | Description |
|--------|------|-------------|
| `rv32i_pipeline_if` | `rtl/cpu/core/pipeline/rv32i_pipeline_if.sv` | PC register, AXI-IF state machine, IF/ID register |
| `rv32i_pipeline_id` | `rtl/cpu/core/pipeline/rv32i_pipeline_id.sv` | Decode, regfile read, immediate generation, ID/EX register |
| `rv32i_pipeline_ex` | `rtl/cpu/core/pipeline/rv32i_pipeline_ex.sv` | ALU, branch resolution, interrupt check, EX/MEM register |
| `rv32i_pipeline_mem` | `rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv` | AXI-MEM state machine, byte extraction, MEM/WB register |
| `rv32i_pipeline_wb` | `rtl/cpu/core/pipeline/rv32i_pipeline_wb.sv` | Regfile write mux, commit signal generation |
| `rv32i_hazard_unit` | `rtl/cpu/core/rv32i_hazard_unit.sv` | Stall and flush control; load-use detection |
| `rv32i_forwarding_unit` | `rtl/cpu/core/rv32i_forwarding_unit.sv` | Forwarding mux select logic |
| `rv32i_csr_file` | `rtl/cpu/core/rv32i_csr_file.sv` | CSR registers: mstatus, mie, mtvec, mepc, mcause, mip |
| `rv32i_interrupt_ctrl` | `rtl/cpu/core/rv32i_interrupt_ctrl.sv` | Interrupt priority, masking, and pending status |
| `rv32i_axi_arbiter` | `rtl/cpu/rv32i_axi_arbiter.sv` | Priority-based AXI arbiter (MEM > IF) |
| `rv32i_core_v2` | `rtl/cpu/rv32i_core_v2.sv` | Replaces rv32i_core; wires all pipeline stages |

### 5.3 New File Organization

```
rtl/
├── cpu/
│   ├── rv32i_cpu_top_v2.sv        # Updated top-level with interrupt ports
│   ├── rv32i_axi_arbiter.sv       # IF vs MEM AXI arbitration
│   └── core/
│       ├── rv32i_core_v2.sv       # Pipelined core wrapper
│       ├── rv32i_hazard_unit.sv   # Hazard detection
│       ├── rv32i_forwarding_unit.sv # Forwarding mux selects
│       ├── rv32i_csr_file.sv      # CSR register file
│       ├── rv32i_interrupt_ctrl.sv # Interrupt controller
│       ├── rv32i_decode.sv        # MODIFIED: add CSR decode
│       ├── rv32i_alu.sv           # UNCHANGED
│       ├── rv32i_regfile.sv       # UNCHANGED
│       ├── rv32i_imm_gen.sv       # UNCHANGED
│       ├── rv32i_branch_comp.sv   # UNCHANGED
│       └── pipeline/
│           ├── rv32i_pipeline_if.sv
│           ├── rv32i_pipeline_id.sv
│           ├── rv32i_pipeline_ex.sv
│           ├── rv32i_pipeline_mem.sv
│           └── rv32i_pipeline_wb.sv
```

---

## 6. Interface Changes

### 6.1 Top-Level Port Additions

The following ports are ADDED to `rv32i_cpu_top` (v2). All existing Phase 1 ports are preserved unchanged.

```systemverilog
module rv32i_cpu_top_v2 (
    // ================================================================
    // ALL PHASE 1 PORTS PRESERVED UNCHANGED
    // ================================================================
    input  logic        clk_i,
    input  logic        rst_n_i,

    // AXI4-Lite Master (unchanged signals, same widths)
    output logic [31:0] axi_awaddr_o,
    output logic        axi_awvalid_o,
    input  logic        axi_awready_i,
    output logic [31:0] axi_wdata_o,
    output logic [3:0]  axi_wstrb_o,
    output logic        axi_wvalid_o,
    input  logic        axi_wready_i,
    input  logic [1:0]  axi_bresp_i,
    input  logic        axi_bvalid_i,
    output logic        axi_bready_o,
    output logic [31:0] axi_araddr_o,
    output logic        axi_arvalid_o,
    input  logic        axi_arready_i,
    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
    output logic        axi_rready_o,

    // APB3 Slave (unchanged)
    input  logic [11:0] apb_paddr_i,
    input  logic        apb_psel_i,
    input  logic        apb_penable_i,
    input  logic        apb_pwrite_i,
    input  logic [31:0] apb_pwdata_i,
    output logic [31:0] apb_prdata_o,
    output logic        apb_pready_o,
    output logic        apb_pslverr_o,

    // Commit Interface (unchanged)
    output logic        commit_valid_o,
    output logic [31:0] commit_pc_o,
    output logic [31:0] commit_insn_o,
    output logic        trap_taken_o,
    output logic [3:0]  trap_cause_o,

    // Debug outputs (Phase 1 debug signals preserved for testbench compatibility)
    output logic [31:0] debug_rs1_data_o,
    output logic [31:0] debug_rs2_data_o,
    output logic        debug_branch_taken_o,
    output logic        debug_take_branch_jump_o,
    output logic        debug_pc_src_o,
    output logic [3:0]  debug_state_o,
    output logic        debug_ebreak_o,

    // ================================================================
    // NEW PHASE 2 PORTS
    // ================================================================
    input  logic        ext_irq_i,    // External interrupt (level-sensitive, active-high)
    input  logic        timer_irq_i   // Timer interrupt (level-sensitive, active-high)
);
```

### 6.2 Commit Interface Adaptation

In Phase 1, `commit_valid` was asserted exactly in the WRITEBACK FSM state. In Phase 2, `commit_valid_o` is asserted when an instruction retires in the WB stage.

**Behavioral change**: A committed instruction in Phase 2 may have completed its ALU/memory operation 2-4 cycles earlier, but the retire event (and commit signal) still occurs exactly once per instruction, at the WB stage.

**Trap handling**: Traps (exceptions and interrupts) continue to use `trap_taken_o` with `commit_valid_o` deasserted. The `trap_cause_o` field is extended to 4 bits from Phase 1 but the encoding changes to match RISC-V `mcause` exception codes:

| `trap_cause_o` | Description |
|:--------------:|-------------|
| 4'b0010 | Illegal instruction (mcause=2) |
| 4'b0011 | Breakpoint / EBREAK (mcause=3) |
| 4'b0100 | Load address misaligned (mcause=4) |
| 4'b0110 | Store address misaligned (mcause=6) |
| 4'b0111 | Machine timer interrupt (mcause[30:0]=7, bit31=1) |
| 4'b1011 | Machine external interrupt (mcause[30:0]=11, bit31=1) |

**Important**: Interrupts also assert `trap_taken_o` (not `commit_valid_o`). The instruction that was in EX when the interrupt was taken is squashed; it does NOT commit.

### 6.3 Debug Interface — Pipeline-Aware Halt

The APB3 debug interface address map is preserved unchanged. Behavioral changes:

**Halt procedure** (Phase 2):
1. Set `dbg_halt_req = 1`
2. CPU stops accepting new instructions (stops issuing IF requests)
3. Wait for pipeline to drain (in-flight instructions complete normally)
4. CPU enters HALTED state when WB stage has nothing more to commit
5. `DBG_STATUS[0]` reads as 1

**Halt latency**: Up to 5 cycles (time for instructions already in pipeline to reach WB).

**PC when halted**: `DBG_PC` reads the PC of the **next instruction to execute** (the instruction that would have been fetched next). This is consistent with Phase 1 behavior.

**Resume**: Same as Phase 1 — set `DBG_CTRL[1]`, CPU begins IF at the halted PC.

**Single-step**: Same as Phase 1 semantics — execute one instruction, return to HALTED. The pipeline drain mechanism ensures the step instruction fully commits before re-entering HALTED.

**Register access when halted**: Unchanged from Phase 1. GPRs and PC readable and writable via APB3.

**CSR visibility via APB3** (new in Phase 2): Add read-only APB3 registers for CSR inspection:

| Address | Register | Description |
|---------|----------|-------------|
| 0x200 | DBG_MSTATUS | Current mstatus value |
| 0x204 | DBG_MIE | Current mie value |
| 0x208 | DBG_MTVEC | Current mtvec value |
| 0x20C | DBG_MEPC | Current mepc value |
| 0x210 | DBG_MCAUSE | Current mcause value |
| 0x214 | DBG_MIP | Current mip value (pending interrupts) |

These registers are read-only (APB writes to these addresses return `pslverr=1`).

### 6.4 AXI Interface — Arbitration

The single AXI4-Lite master interface is preserved. Arbitration between IF and MEM is handled internally by `rv32i_axi_arbiter`.

**Arbiter behavior**:
- When only IF requests: grant to IF
- When only MEM requests: grant to MEM
- When both request simultaneously: grant to MEM (priority); stall IF
- The arbiter presents a single AXI4-Lite master to the external bus

**AXI protocol compliance**: The arbiter must not issue overlapping transactions. One transaction must complete (address + data phases) before the next begins. This maintains Phase 1's "one outstanding transaction at a time" constraint.

---

## 7. Verification Strategy

### 7.1 Testbench Architecture

The Phase 2 testbench extends the Phase 1 infrastructure:
- Same cocotb + pyuvm framework
- Same AXI4-Lite slave memory model (from Phase 1)
- Same APB3 master debug driver (from Phase 1)
- Updated scoreboard to model pipeline behavior
- New interrupt driver (assert/deassert `ext_irq_i` and `timer_irq_i`)
- Python reference model updated with CSR state and interrupt model

### 7.2 Test Plan

#### Group 1: Pipeline Correctness (Regression)

Run all Phase 1 tests against the Phase 2 pipeline. These must pass without modification (backward compatibility).

| Test | Priority | Description |
|------|----------|-------------|
| All 37 RV32I instruction tests | P0 | Functional correctness preserved |
| Random instruction streams (10k+) | P0 | No false commits |
| AXI protocol tests | P0 | Unchanged interface compliance |
| Debug interface tests | P0 | Halt/resume/step/breakpoints work |

#### Group 2: Data Hazard Tests (New)

| Test | Description | What to Check |
|------|-------------|---------------|
| RAW back-to-back (EX→EX) | `ADD x1, x0, x0; ADD x2, x1, x0` | x2 gets forwarded value from EX |
| RAW with gap (MEM→EX) | One instruction between dependent pair | MEM→EX forwarding path |
| RAW with two gaps (WB→EX) | Two instructions between dependent pair | WB write + regfile read |
| Load-use stall | `LW x1, 0(x0); ADD x2, x1, x0` | 1-cycle stall inserted |
| No stall for gap | `LW x1, 0(x0); NOP; ADD x2, x1, x0` | No stall needed with NOP |
| Store after load (same reg) | `LW x1, 0(x0); SW x1, 4(x0)` | Store data forwarded correctly |
| Back-to-back stores | `SW x1, 0(x0); SW x2, 4(x0)` | No hazard, correct AXI transactions |
| x0 forwarding | `ADD x0, x1, x2; ADD x3, x0, x4` | x0 always reads as 0 |
| Multi-dependency | `ADD x1, x2, x3; ADD x4, x1, x1` | Both operands forwarded |

#### Group 3: Control Hazard Tests (New)

| Test | Description | What to Check |
|------|-------------|---------------|
| Branch taken | BEQ with equal values | 2-cycle flush; correct PC redirect |
| Branch not-taken | BEQ with unequal values | No flush; pipeline continues |
| Branch with RAW | Dependent value used in branch | Forwarding to branch comparator |
| JAL flush | Jump and link | 1-cycle flush; rd=PC+4 correct |
| JALR flush | Jump register | 2-cycle flush; target = (rs1+imm)&~1 |
| JAL → immediate dep | JAL followed by use of ra | RAW hazard across control transfer |
| Consecutive branches | Back-to-back branch instructions | Flush and refetch correct each time |

#### Group 4: Interrupt Tests (New)

| Test | Description | What to Check |
|------|-------------|---------------|
| Timer IRQ delivery | Assert `timer_irq_i`; MIE=1; MTIE=1 | Handler entered; mepc correct; mstatus updated |
| External IRQ delivery | Assert `ext_irq_i`; MIE=1; MEIE=1 | Handler entered correctly |
| IRQ with MIE=0 | Assert IRQ while MIE disabled | Interrupt NOT taken |
| IRQ with MTIE=0 | Assert timer IRQ while MTIE=0 | Timer interrupt NOT taken |
| MRET | Return from interrupt handler | PC restored from mepc; MIE restored |
| IRQ latency | Measure cycles from assert to handler | Must be ≤ 2 cycles |
| IRQ during load-use stall | IRQ arrives while pipeline is stalled | IRQ eventually delivered after stall |
| IRQ during AXI stall | IRQ arrives during MEM stage AXI wait | IRQ taken after AXI completes |
| IRQ vs exception priority | Illegal instruction + IRQ simultaneously | Exception takes priority (check RV spec) |
| EBREAK → debug halt | EBREAK while MIE=1 | Debug halt; NOT interrupt; mepc and mcause set |

#### Group 5: CSR Instruction Tests (New)

| Test | Description | What to Check |
|------|-------------|---------------|
| CSRRW | Read and write mtvec | Correct rd value; mtvec updated |
| CSRRS | Set bits in mie | Correct bit-set behavior |
| CSRRC | Clear bits in mie | Correct bit-clear behavior |
| CSRRWI/CSRRSI/CSRRCI | Immediate variants | Same as above with imm operand |
| CSR RAW hazard | Write mtvec then immediately read | CSR forwarding (or 1-cycle stall) |
| Illegal CSR address | Access undefined CSR | Illegal instruction trap |
| Read-only CSR write | Write to mhartid | Illegal instruction trap |
| CSR write to mstatus | Enable/disable MIE | Interrupt gate responds correctly |

#### Group 6: Debug Interface (Updated)

| Test | Description | What to Check |
|------|-------------|---------------|
| Halt during execution | Halt request mid-stream | Pipeline drains; correct halt PC |
| Halt during load-use stall | Halt while pipeline stalled | Drains cleanly |
| Halt during interrupt handler | Halt while handler is executing | Halts at correct point in handler |
| Read CSR via APB | Read DBG_MSTATUS, DBG_MEPC | Correct CSR values visible |
| Resume after halt | Resume from halt | Correct instruction executed next |

#### Group 7: AXI Stress Tests (Updated)

| Test | Description | What to Check |
|------|-------------|---------------|
| IF + MEM contention | Load/store while IF also pending | Arbiter grants MEM; IF stalled |
| AXI back-pressure | Randomize arready/rvalid/bvalid | No protocol violations |
| AXI stall with pending IRQ | IRQ arrives during AXI wait | IRQ taken after MEM stage completes |

### 7.3 Coverage Goals

In addition to Phase 1 coverage metrics:

| Coverage Metric | Target | Notes |
|----------------|--------|-------|
| Forwarding path EX→EX activated | 100% | Per instruction type |
| Forwarding path MEM→EX activated | 100% | Per instruction type |
| Load-use stall activated | 100% | At least 100 occurrences |
| Branch taken + flush | 100% | All branch types |
| Branch not-taken | 100% | All branch types |
| JAL flush | 100% | |
| JALR flush | 100% | |
| Interrupt delivery | 100% | Both timer and external |
| MRET | 100% | |
| All CSR instructions | 100% | All six variants |
| MIE gate (IRQ blocked) | 100% | Interrupt arrives while MIE=0 |
| AXI IF + MEM contention | ≥50% of load/store cycles | |

### 7.4 Python Reference Model Updates

The Phase 1 Python reference model (`tb/models/rv32i_model.py`) must be updated to model:

1. **CSR state**: Add `mstatus`, `mie`, `mtvec`, `mepc`, `mcause`, `mip` fields to `RV32IModel`
2. **CSR instructions**: Implement `CSRRW`, `CSRRS`, `CSRRC`, `CSRRWI`, `CSRRSI`, `CSRRCI`, `MRET`
3. **Interrupt model**: Add `step_with_interrupt(irq_pending_bits)` method that checks interrupt delivery before executing the instruction
4. **Trap handler**: On interrupt or exception, update CSRs and redirect PC to `mtvec`
5. **MRET**: Implement return from trap (restore PC from mepc, restore MIE from MPIE)

**Scoreboard impact**: The scoreboard must now compare CSR state after each instruction, not just register file state.

### 7.5 Random Instruction Testing — Phase 2 Additions

Extend the random instruction generator (`tb/generators/rv32i_instr_gen.py`) to:
1. Generate CSR instructions with valid CSR addresses
2. Generate interrupt enable/disable sequences (set/clear MIE via CSRRS/CSRRC)
3. Inject random interrupt events at random instruction boundaries
4. Generate load-use sequences (load immediately followed by dependent instruction)
5. Generate branch-heavy sequences (>50% branch instructions, mix taken/not-taken)

Target: 50,000+ random instructions with interrupt injection, zero failures.

---

## 8. Physical Design Targets

### 8.1 Frequency and Timing

| Parameter | Value | Notes |
|-----------|-------|-------|
| Target clock frequency | 200 MHz | 5.0 ns period |
| Clock uncertainty | 0.25 ns | 5% pre-CTS (tighter than Phase 1 due to higher freq) |
| Input delay (AXI) | 1.0 ns max, 0.25 ns min | Tighter than Phase 1 |
| Output delay (AXI) | 1.0 ns max, 0.25 ns min | Tighter than Phase 1 |
| Setup margin target | ≥ 0.1 ns WNS | Sign-off criterion |
| Hold margin target | ≥ 0.0 ns TNS | Sign-off criterion |

### 8.2 Area Target

| Technology | Phase 1 (single-cycle) | Phase 2 (5-stage) | Notes |
|-----------|----------------------|------------------|-------|
| Sky130 (130nm) | ~50k µm² | ~90k µm² | Pipeline registers add ~40% area |
| ASAP7 (7nm) | ~5k µm² | ~9k µm² | Same ratio |

The pipeline registers and new modules (hazard unit, forwarding unit, CSR file, arbiter) add area. The area increase is expected and acceptable.

### 8.3 Power Budget

| Parameter | Phase 1 | Phase 2 Target | Notes |
|-----------|---------|---------------|-------|
| Total power | < 10 mW @ 100 MHz | < 25 mW @ 200 MHz | 2.5x frequency; more logic |
| Clock tree | < 20% of total | < 25% of total | Longer pipeline → more clock sinks |
| Leakage | Baseline | < 2x Phase 1 | More sequential elements |

### 8.4 Critical Paths to Watch

The following combinational paths are expected to be timing-critical at 200 MHz. The Backend Engineer must analyze and potentially break these with pipeline registers or architectural changes.

| Critical Path | Estimated Depth | Mitigation |
|--------------|----------------|-----------|
| Forwarding mux → ALU operand → ALU result → EX/MEM register | 5-8 logic levels | ALU must complete in one cycle; forwarding mux is on the critical path |
| Branch comparator → PC redirect → IF/ID register | 4-6 logic levels | Branch resolution is critical; comparator must be fast |
| CSR read → ALU operand B (CSRRS/CSRRC) | 3-5 logic levels | CSR file read is combinational; must be fast |
| AXI arbiter decision → arvalid/araddr propagation | 2-3 logic levels | Arbiter is combinational; should not be timing-critical |
| Hazard unit → stall signals → pipeline register enable | 3-5 logic levels | Stall propagation must be single cycle |

### 8.5 SDC Changes from Phase 1

The Phase 2 SDC file (`pnr/constraints/phase2_cpu.sdc`) changes from Phase 1:

```
# Phase 2 clock - doubled frequency
create_clock -name clk -period 5.0 [get_ports clk_i]

# Uncertainty tightened
set_clock_uncertainty 0.25 [get_clocks clk]

# New ports: interrupt inputs
set_input_delay -clock clk -max 1.0 [get_ports {ext_irq_i timer_irq_i}]
set_input_delay -clock clk -min 0.25 [get_ports {ext_irq_i timer_irq_i}]

# AXI delays tightened for 200 MHz
set_input_delay  -clock clk -max 1.0 [get_ports axi_*_i]
set_input_delay  -clock clk -min 0.25 [get_ports axi_*_i]
set_output_delay -clock clk -max 1.0 [get_ports axi_*_o]
set_output_delay -clock clk -min 0.25 [get_ports axi_*_o]

# Commit interface (verification only — false path in silicon)
set_false_path -from [get_ports {commit_valid_o commit_pc_o commit_insn_o}]

# Debug interface (APB3 — slow path, multi-cycle acceptable)
set_multicycle_path -setup 2 -from [get_ports apb_*_i]
set_multicycle_path -hold  1 -from [get_ports apb_*_i]
```

### 8.6 Clock Gating Opportunities

Phase 2 introduces opportunities for clock gating that Phase 1 did not have:

| Gating Opportunity | Savings | Notes |
|-------------------|---------|-------|
| Pipeline register enable (stall) | Medium | When stage is stalled, no switching activity |
| CSR file gating | Low | CSR writes are infrequent |
| Forwarding mux gating | Low | Only active when hazard detected |

Clock gating implementation is left to the Backend Engineer. The RTL should use standard `always_ff` with enable signals (not explicit clock gating) to allow synthesis tools to infer clock gates.

---

## 9. Implementation Roadmap

The following sub-tasks are numbered with dependency notation `[depends: N]`.

### Sub-task 1: Update Python Reference Model (CSR + Interrupt Support)
**Agent**: Verification Engineer
**Priority**: P0 (blocks all CSR and interrupt testing)
**Objective**: Extend `tb/models/rv32i_model.py` to model CSRs and interrupt delivery
**Deliverables**:
- Updated `rv32i_model.py` with CSR state machine
- Updated `test_rv32i_model.py` with ≥ 30 new CSR/interrupt test cases
- All 66 Phase 0 tests still passing
**References**: Section 4.2 (CSR register set), Section 4.5 (interrupt flow)

### Sub-task 2: Write PHASE2_ARCHITECTURE_SPEC.md [depends: human approval]
**Agent**: RTL Architect
**Priority**: P0 (prerequisite for all Phase 2 work)
**Objective**: Complete this document and obtain human approval
**Deliverables**: This document, approved and merged

### Sub-task 3: Update rv32i_decode.sv for CSR Instructions [depends: 2]
**Agent**: RTL Designer
**Priority**: P0 (required before pipeline stages can be implemented)
**Objective**: Add CSR instruction decoding (6 CSR variants + MRET) to existing decoder
**Inputs**: Section 4.3 (CSR instruction set), existing `rv32i_decode.sv`
**Deliverables**: Updated `rv32i_decode.sv` with new outputs: `csr_access`, `csr_addr`, `csr_op`
**Constraints**: All Phase 1 decoder outputs must remain backward compatible

### Sub-task 4: Implement rv32i_csr_file.sv [depends: 3]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: CSR register file with mstatus, mie, mtvec, mepc, mcause, mip
**Inputs**: Section 4.2 (CSR register set), Section 4.5 (interrupt flow)
**Deliverables**: `rtl/cpu/core/rv32i_csr_file.sv`
**Constraints**: mtvec MODE forced to 0; mip is read-only from software; see CSR access semantics in Section 4.3

### Sub-task 5: Implement rv32i_interrupt_ctrl.sv [depends: 4]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Interrupt priority, masking, and pending detection
**Inputs**: Section 4.3-4.6, new port definitions in Section 6.1
**Deliverables**: `rtl/cpu/core/rv32i_interrupt_ctrl.sv`
**Constraints**: Level-sensitive inputs; external > timer priority; output is single `irq_taken` pulse with `irq_cause` output

### Sub-task 6: Implement rv32i_hazard_unit.sv [depends: 2]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Stall and flush control for load-use, control hazards, AXI stalls
**Inputs**: Section 3.5 (hazard unit interface), Section 3.1-3.4
**Deliverables**: `rtl/cpu/core/rv32i_hazard_unit.sv`
**Constraints**: Purely combinational; must be simulatable standalone

### Sub-task 7: Implement rv32i_forwarding_unit.sv [depends: 2]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Forwarding mux select signals for EX→EX, MEM→EX, WB→EX paths
**Inputs**: Section 3.1 (forwarding paths)
**Deliverables**: `rtl/cpu/core/rv32i_forwarding_unit.sv`
**Constraints**: Purely combinational; EX/MEM takes priority over MEM/WB

### Sub-task 8: Implement rv32i_axi_arbiter.sv [depends: 2]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: AXI priority arbiter (MEM > IF); single AXI4-Lite master output
**Inputs**: Section 6.4
**Deliverables**: `rtl/cpu/rv32i_axi_arbiter.sv`
**Constraints**: One outstanding transaction at a time; MEM priority; IF stall signaling

### Sub-task 9: Implement Pipeline Stage Modules [depends: 6, 7, 8]
**Agent**: RTL Designer
**Priority**: P0 (all must be done before core integration)
**Objective**: Five pipeline stage modules per Section 2.2
**Deliverables**:
- `rtl/cpu/core/pipeline/rv32i_pipeline_if.sv`
- `rtl/cpu/core/pipeline/rv32i_pipeline_id.sv`
- `rtl/cpu/core/pipeline/rv32i_pipeline_ex.sv` (includes branch resolution + interrupt check)
- `rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv`
- `rtl/cpu/core/pipeline/rv32i_pipeline_wb.sv`
**Constraints**: Pipeline registers as struct types per Section 2.2; flush values per Section 2.2

### Sub-task 10: Integrate rv32i_core_v2.sv [depends: 3, 4, 5, 6, 7, 9]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Wire all pipeline stages into core wrapper
**Inputs**: Section 5.1 (module hierarchy), Section 5.3 (file organization)
**Deliverables**: `rtl/cpu/rv32i_core_v2.sv`
**Constraints**: Reuse unchanged modules (ALU, regfile, imm_gen, branch_comp) by instantiation inside pipeline stage modules

### Sub-task 11: Update rv32i_cpu_top_v2.sv [depends: 10]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Add interrupt ports; update debug logic for pipeline-aware halt; add CSR APB3 registers
**Inputs**: Section 6.1-6.3
**Deliverables**: `rtl/cpu/rv32i_cpu_top_v2.sv`
**Constraints**: All Phase 1 external port names and semantics preserved

### Sub-task 12: Directed Hazard Verification Tests [depends: 10 + reference model sub-task 1]
**Agent**: Verification Engineer
**Priority**: P0
**Objective**: Implement Group 2 (data hazard) and Group 3 (control hazard) test cases
**Inputs**: Section 7.2 (test plan groups 2 and 3)
**Deliverables**: `tb/cocotb/cpu/test_pipeline_hazards.py`
**Constraints**: Use existing AXI slave model; compare against updated Python reference model

### Sub-task 13: Interrupt Verification Tests [depends: 11]
**Agent**: Verification Engineer
**Priority**: P0
**Objective**: Implement Group 4 (interrupt) and Group 5 (CSR) test cases
**Inputs**: Section 7.2 (test plan groups 4 and 5)
**Deliverables**: `tb/cocotb/cpu/test_interrupts.py`, `tb/cocotb/cpu/test_csr.py`
**Constraints**: Interrupt driver must support both level assertion timing and duration control

### Sub-task 14: Random Instruction Regression with CSR + Interrupt [depends: 12, 13]
**Agent**: Verification Engineer
**Priority**: P0
**Objective**: Update random instruction generator; run 50k+ instructions with interrupts
**Inputs**: Section 7.5
**Deliverables**: Updated `tb/generators/rv32i_instr_gen.py`; test results showing 0 failures
**Constraints**: Must cover all forwarding paths and interrupt delivery paths per coverage goals

### Sub-task 15: Debug Interface Verification (Updated) [depends: 11]
**Agent**: Verification Engineer
**Priority**: P1
**Objective**: Verify pipeline-aware halt/resume; CSR visibility via APB3
**Inputs**: Section 7.2 (Group 6), Section 6.3
**Deliverables**: Updated `tb/cocotb/cpu/test_debug_interface.py`

### Sub-task 16: Physical Design — Synthesis and P&R at 200 MHz [depends: all RTL sub-tasks]
**Agent**: Backend Engineer
**Priority**: P1 (can overlap with sub-task 14 in parallel)
**Objective**: Synthesis + place & route + STA at 200 MHz
**Inputs**: Section 8 (physical design targets), SDC in Section 8.5
**Deliverables**: Updated `pnr/constraints/phase2_cpu.sdc`; timing closure report; area and power reports
**Constraints**: WNS = 0, TNS = 0 on all corners; if timing closure requires RTL changes, file an architectural issue

---

## 10. Open Questions — Human Approval Required

The following decisions require human approval before RTL implementation begins. Per the AI/Human boundary in CLAUDE.md, these architectural decisions are human-owned.

### OQ-1: In-Place Update vs New Module Names

**Decision (2026-02-14)**: ✅ **Option B — Modify in-place.**

Phase 1 RTL has been archived to `micro_p/rtl/` as a frozen legacy copy. The files in `rtl/cpu/` may be modified directly. Module names (`rv32i_cpu_top`, `rv32i_core`, etc.) are preserved. Testbench changes are minimised — only new ports and signals need updating.

### OQ-2: Interrupt Priority

**Decision (2026-02-14)**: ✅ **External interrupt (MEIP) > Timer interrupt (MTIP).**

Matches the RISC-V privileged spec recommendation. When both are pending and enabled, the external interrupt is taken first.

### OQ-3: EBREAK Behavior in Phase 2

**Decision (2026-02-14)**: ✅ **Option C — EBREAK sets `mcause=3`, saves `mepc=PC`, AND triggers the debug halt.**

Consistent with Phase 1 debug halt behaviour while also populating CSR state so a debugger can inspect the cause after halt.

### OQ-4: CSR Write Side-Effects in EX Stage

**Decision (2026-02-14)**: ✅ **CSR write takes effect in EX, same cycle as the interrupt check. CSR write has priority.**

If a CSR instruction in EX clears `mstatus.MIE`, the interrupt check in the same cycle sees `MIE=0` and does not take the interrupt.

### OQ-5: Debug Halt During Interrupt Handler

**Decision (2026-02-14)**: ✅ **Halt immediately once the pipeline drains. Do not wait for MRET.**

The debugger can inspect `mepc` and `mcause` via APB3 to determine the interrupt context at the point of halt.

### OQ-6: AXI Transaction Atomicity During Pipeline Flush

**Decision (2026-02-14)**: ✅ **Complete the in-flight AXI transaction and discard the response if it belongs to a flushed instruction.**

AXI4-Lite protocol compliance is non-negotiable — a transaction cannot be abandoned once started. The CPU tracks a `pending_flush` flag; if set when the AXI response arrives, the response data is discarded and the pipeline resumes from the correct redirect PC.

### OQ-7: Frequency Target Fallback

**Decision (2026-02-14)**: ✅ **Prefer 200 MHz. Relaxation only after all other options are exhausted, in this order:**

1. **First**: Add a pipeline register to break the critical path (forwarding mux or ALU output). This keeps Sky130 as the target technology.
2. **Second**: Switch to ASAP7 (7nm predictive PDK) if the Sky130 critical path cannot close at 200 MHz after pipelining.
3. **Last resort**: Relax the frequency target (e.g., to 150 MHz) only if both options above have been exhausted and documented.

Each step requires re-running the OpenROAD back-end flow and reporting results before proceeding to the next option.

---

## 11. Appendix: Instruction Encoding Reference for New Instructions

### CSR Instructions (Zicsr)

```
31        20 19    15 14  12 11    7 6      0
[ csr[11:0] | rs1[4:0] | 011 | rd[4:0] | 1110011 ]  CSRRC
[ csr[11:0] | rs1[4:0] | 010 | rd[4:0] | 1110011 ]  CSRRS
[ csr[11:0] | rs1[4:0] | 001 | rd[4:0] | 1110011 ]  CSRRW
[ csr[11:0] | uimm[4:0]| 111 | rd[4:0] | 1110011 ]  CSRRCI
[ csr[11:0] | uimm[4:0]| 110 | rd[4:0] | 1110011 ]  CSRRSI
[ csr[11:0] | uimm[4:0]| 101 | rd[4:0] | 1110011 ]  CSRRWI
```

### MRET Instruction

```
31        20 19    15 14  12 11    7 6      0
[ 001100000010 | 00000 | 000 | 00000 | 1110011 ]  MRET
```
Full encoding: `0x30200073`

---

## 12. References

- PHASE0_ARCHITECTURE_SPEC.md: Architectural requirements (ISA, reset, traps)
- PHASE1_ARCHITECTURE_SPEC.md: Single-cycle implementation (PRESERVED)
- RTL_DEFINITION.md: Interface signal definitions
- MEMORY_MAP.md: APB3 debug register map (extended in Phase 2)
- REFERENCE_MODEL_SPEC.md: Python reference model API (to be updated)
- VERIFICATION_PLAN.md: Phase-aligned verification strategy
- RISC-V ISA Volume I: RV32I Base Integer Instruction Set (v20191213)
- RISC-V ISA Volume II: Privileged Architecture Specification (v20211203) — Chapter 3 (Machine-Level ISA)
- AMBA AXI4-Lite Protocol Specification (ARM IHI 0022E)
- AMBA APB Protocol Specification v2.0 (ARM IHI 0024C)
- docs/design/OPENROAD_FLOW_SPEC.md: Physical design flow
- docs/design/SDC_TIMING_SPEC.md: Timing constraint guidelines
- pnr/constraints/phase1_cpu.sdc: Phase 1 SDC (baseline for Phase 2)
