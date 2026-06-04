# Supported Instructions

## Phase 1 ✅ (Complete — RV32I Base)

All 37 RV32I base integer instructions (verified and passing):

- **Integer Arithmetic**: ADD, ADDI, SUB, LUI, AUIPC
- **Logical**: AND, ANDI, OR, ORI, XOR, XORI
- **Shifts**: SLL, SLLI, SRL, SRLI, SRA, SRAI
- **Comparison**: SLT, SLTI, SLTU, SLTIU
- **Branches**: BEQ, BNE, BLT, BGE, BLTU, BGEU
- **Jumps**: JAL, JALR
- **Memory**: LB, LH, LW, LBU, LHU, SB, SH, SW
- **System**: ECALL, EBREAK, FENCE

## Phase 2 ✅ (Verification Complete — RV32I + Zicsr)

All Phase 1 instructions PLUS:

- **CSR Instructions**: CSRRW, CSRRS, CSRRC, CSRRWI, CSRRSI, CSRRCI
- **CSR Registers** (M-mode):
  - Machine trap setup: `mstatus`, `mie`, `mtvec`
  - Machine trap handling: `mscratch`, `mepc`, `mcause`, `mtval`, `mip`
  - Machine counter/timers: `mcycle`, `minstret`
- **Interrupt Support**: Timer interrupt (MTIP), external interrupt (MEIP)

See [`docs/design/PHASE0_ARCHITECTURE_SPEC.md`](../design/PHASE0_ARCHITECTURE_SPEC.md)
for RV32I semantics and
[`docs/design/PHASE2_ARCHITECTURE_SPEC.md`](../design/PHASE2_ARCHITECTURE_SPEC.md)
for CSR and interrupt details.
