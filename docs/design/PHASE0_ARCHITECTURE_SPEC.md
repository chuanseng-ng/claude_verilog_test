# Phase 0 Architecture Specification

RV32I Minimal CPU Core

Document status: Active (Phase-0)
Target audience: RTL, verification, tooling
Compliance reference: RISC-V International RV32I Base ISA (subset)

**Note**: This specification defines the architectural requirements. No RTL implementation
is part of Phase 0. RTL implementation begins in Phase 1 (see PHASE1_ARCHITECTURE_SPEC.md).
Phase 0 deliverables are: specifications, Python reference model, and test infrastructure.

## Scope and non-goals

### Scope

This document specifies the Phase-0 CPU architecture, including:

- Supported RV32I instruction subset
- Reset behavior
- Trap behavior
- Memory ordering rules
- Commit semantics
- Observable architectural signals for verification

The goal is to enable a deterministic, verification-first CPU core suitable for:

- cocotb + py-uvm verification
- Python golden reference modeling
- AI-assisted RTL implementation under strict constraints

### Explicit non-goals (Phase-0 exclusions)

The following are out of scope and SHALL NOT be implemented in Phase-0:

- Privilege levels
- CSRs
- Interrupts
- Exceptions other than illegal instruction
- FENCE/FENCE.I
- Atomic instructions (A extension)
- Compressed instructions (C extension)
- Misaligned memory accesses
- Speculative or out-of-order execution

Any excluded feature SHALL result in an illegal instruction trap if encountered

## Architectural overview

### Execution model

- Single-issue
- In-order
- One instruction commits at most per cycle
- No speculative architectural side effects

### Architectural state

- 32 integer registers (x0 - x31)
- Program counter (PC)
- Memory (external, architecturally visible)

**x0 SHALL be hardwired to zero at all times**

## Supported instruction subset (RV32I)

### Integer arithmetic and logic

**The CPU SHALL implement the following instructions**

```text
ADD, SUB
AND, OR, XOR
SLT, SLTU
SLL, SRL, SRA
ADDI
ANDI, ORI, XORI
SLTI, SLTIU
SLLI, SRLI, SRAI
```

### Control flow

```text
BEQ, BNE
BLT, BGE
BLTU, BGEU
JAL
JALR
```

### Load and store

```text
LB, LBU
LH, LHU
LW
SB, SH
SW
```

All loads and stores MUST be naturally aligned <br>
Misaligned accesses SHALL generate an illegal instruction trap

### Upper immediates

```text
LUI
AUIPC
```

### Illegal instructions

Any instructions SHALL be considered illegal if:

- The opcode is unsupported
- funct3/funct7 encoding is unsupported
- Instruction belongs to an excluded extension
- Memory access is misaligned
- Instruction encoding is reserved by the ISA

## Reset Behavior

### Reset type

- Active-low synchronous reset (```rst_n```)
- Sampled on the rising edge of ```clk```

### Architectural state after reset

Upon reset assertion and subsequent deassertion:

| State element          | Required value |
| ---------------------- | -------------- |
| PC                     | `RESET_PC`     |
| x0                     | 0              |
| x1–x31                 | 0              |
| Pipeline               | Empty          |
| Outstanding memory ops | None           |
| Trap state             | Inactive       |

Recommended constant:

```ini
RESET_PC = 0x0000_0000
```

### Reset exit guarantees

Within a bounded number of cycles after reset deassertion:

- Instruction fetch SHALL begin at ```RESET_PC```
- The first committed instruction SHALL originate from ```RESET_PC```

No undefined or random architectural state is permitted after reset

## Trap behavior

### Supported traps (Phase-0)

| Trap cause          | Supported |
| ------------------- | --------- |
| Illegal instruction | YES       |
| All others          | NO        |

### Trap vector

All traps SHALL transfer control to a single fixed trap vector

```ini
TRAP_VECTOR = 0x0000_0100
```

### Trap semantics

On an illegal instruction trap:

1. The faulting instruction SHALL NOT commit
2. No architectural state SHALL be modified
3. PC SHALL be set to ```TRAP_VECTOR```
4. Execution SHALL continue from ```TRAP_VECTOR```

### Precision rules

Traps SHALL be precise:

- No partial register writes
- No partial memory writes
- No subsequent instruction may commit

## Commit semantics

### Commit definition

An instruction is considered **committed** when:

- All architectural side effects are complete
- PC is updated to the next architectural value
- Register and/or memory updates are visible

At most **one instruction SHALL commit per cycle**

### Commit observability (required signals)

The implementation SHALL expose the following signals for verification:

```text
commit_valid   : Instruction committed this cycle
commit_pc      : PC of committed instruction
commit_insn    : 32-bit instruction word
```

Trap-related observability:

```text
trap_taken     : Trap occurred this cycle
trap_cause     : Encoded trap reason
```

These signals define the architectural truth boundary

## Memory ordering rules

### Memory model

Phase-0 SHALL implement **sequential consistency (SC)** for a single core

This implies:

1. Instructions commit in program order
2. Loads and stores appear atomic
3. No memory reordering is architecturally visible
4. No speculative memory side effects

### Load/store rules

| Rule                            | Requirement           |
| ------------------------------- | --------------------- |
| Load after store (same address) | Must see stored value |
| Store after load                | Appears after load    |
| Outstanding memory ops          | At most one           |
| Partial completion              | Not allowed           |

### Memory interface constraints

The memory interface SHALL:

- Support a request/valid handshake
- Complete one transaction at a time
- Preserve request order
- Never reorder responses

## Verification requirements (Phase-0)

### Reference model alignment

A Python reference model SHALL exist that:

- Implements the exact instruction subset
- Matches trap behavior
- Matches memory ordering rules
- Produces a step-by-step architectural state

The RTL SHALL be verified **only** against this reference model

### Determinism

Given identical instruction streams and memory contents:

- RTL behavior SHALL be deterministic
- No random or X-dependent behavior is permitted

## AI usage constraints (normative)

### AI MAY assist with

- RTL boilerplate
- Decoder tables
- FSM templates
- Testbench scaffolding
- cocotb drivers and monitors

### AI SHALL NOT decide

- ISA legality
- Reset semantics
- Trap semantics
- Memory ordering rules
- Commit behavior

These are **architectural invariants**

## Phase-0 exit criteria

Phase-0 SHALL be considered complete only when:

- ISA subset is frozen
- Reset behavior is frozen
- Trap behavior is frozen
- Memory ordering rules are frozen
- Commit interface is frozen
- Python reference model matches this document
- cocotb tests validate all above behaviors

No Phase-1 features SHALL begin until Phase-0 is complete
