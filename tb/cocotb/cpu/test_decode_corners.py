"""
Decode / MEM-stage corner cases for rv32i_cpu_top (bead a5ze).

  test_load_extraction_all_offsets   LB/LBU at byte offsets 0-3 and LH/LHU at halfword offsets
                                     0-1, on a word with the sign bit set in every byte/half
                                     lane and on one with it clear (rv32i_pipeline_mem
                                     load-data extraction); expected values come from the
                                     RISC-V load definition, computed here in Python
  test_illegal_encodings_trap        SYSTEM funct3=100, every non-canonical FENCE.I
                                     encoding (rd, rs1 or imm non-zero) and reserved MISC-MEM
                                     funct3 values raise illegal
                                     instruction: mcause 2, mepc = the bad PC, and the
                                     instruction after it never commits
  test_fence_is_a_nop                FENCE (funct3=000) retires without a trap and without
                                     disturbing the program
"""

import cocotb

from sim.riscv_encoder import (
    ADDI,
    CSRRS,
    CSRRW,
    EBREAK,
    LB,
    LBU,
    LH,
    LHU,
)
from tb.cocotb.cpu.phase2_test_utils import _setup_test
from tb.cocotb.cpu.test_csr_access import fresh_run, li

DATA = 0x400
CSR_MTVEC = 0x305
CSR_MEPC = 0x341
CSR_MCAUSE = 0x342
HANDLER = 0x100
ILLEGAL_INSN = 2


def _sext(value: int, bits: int) -> int:
    value &= (1 << bits) - 1
    return value - (1 << bits) if value >> (bits - 1) else value


def _expected_load(word: int, offset: int, size: int, unsigned: bool) -> int:
    raw = (word >> (8 * offset)) & ((1 << (8 * size)) - 1)
    return raw if unsigned else _sext(raw, 8 * size) & 0xFFFF_FFFF


@cocotb.test()
async def test_load_extraction_all_offsets(dut):
    """Sub-word loads pick the right lane and extend per the signed / unsigned opcode."""
    mem, dbg = await _setup_test(dut)
    words = {DATA: 0x8091_A2B3, DATA + 4: 0x7F6E_5D4C}

    loads = []  # (instruction builder, addr offset in the word, size, unsigned)
    for word_off in (0, 4):
        for off in range(4):
            loads.append((LB, word_off, off, 1, False))
            loads.append((LBU, word_off, off, 1, True))
        for off in (0, 2):
            loads.append((LH, word_off, off, 2, False))
            loads.append((LHU, word_off, off, 2, True))
    # 24 loads -> destination registers x1..x24, base address in x30.
    program = [ADDI(30, 0, DATA)]
    for i, (build, word_off, off, _size, _uns) in enumerate(loads):
        program.append(build(i + 1, 30, word_off + off))
    program.append(EBREAK())

    await fresh_run(dut, mem, dbg, program, words)
    bad = []
    for i, (build, word_off, off, size, unsigned) in enumerate(loads):
        got = await dbg.read_gpr(i + 1)
        want = _expected_load(words[DATA + word_off], off, size, unsigned)
        if got != want:
            bad.append(
                f"  {build.__name__} +{word_off + off}: got {got:#010x}, want {want:#010x}"
            )
    assert not bad, "load extraction mismatch:\n" + "\n".join(bad)


def _system_funct3_100() -> int:
    return (0x300 << 20) | (1 << 15) | (0b100 << 12) | (1 << 7) | 0b1110011


def _fence_i(*, rd: int = 0, rs1: int = 0, imm: int = 0) -> int:
    return (imm << 20) | (rs1 << 15) | (0b001 << 12) | (rd << 7) | 0b0001111


ILLEGAL_WORDS = [
    ("SYSTEM funct3=100", _system_funct3_100()),
    ("FENCE.I rd!=0", _fence_i(rd=1)),
    ("FENCE.I rs1!=0", _fence_i(rs1=1)),
    ("FENCE.I imm!=0", _fence_i(imm=1)),
    # MISC-MEM funct3 other than 000 (FENCE) / 001 (FENCE.I) is reserved: rv32i_decode.sv:510-512
    ("MISC-MEM funct3=010", (0b010 << 12) | 0b0001111),
    ("MISC-MEM funct3=111", (0b111 << 12) | 0b0001111),
]


@cocotb.test()
async def test_illegal_encodings_trap(dut):
    """Each reserved encoding traps with mcause=2 at its own PC and does not retire."""
    mem, dbg = await _setup_test(dut)
    for label, bad_word in ILLEGAL_WORDS:
        program = [
            ADDI(1, 0, HANDLER),
            CSRRW(0, CSR_MTVEC, 1),
            bad_word,  # PC 0x08
            ADDI(2, 0, 99),  # must be squashed
            EBREAK(),
        ]
        handler = [CSRRS(3, CSR_MCAUSE, 0), CSRRS(4, CSR_MEPC, 0), EBREAK()]
        await fresh_run(dut, mem, dbg, program, {HANDLER + 4 * i: w for i, w in enumerate(handler)})

        cause = await dbg.read_gpr(3)
        epc = await dbg.read_gpr(4)
        squashed = await dbg.read_gpr(2)
        assert cause == ILLEGAL_INSN, f"{label}: mcause={cause:#x}, want {ILLEGAL_INSN}"
        assert epc == 0x08, f"{label}: mepc={epc:#x}, want 0x8 (the offending PC)"
        assert squashed == 0, f"{label}: the instruction after it committed (x2={squashed})"


@cocotb.test()
async def test_fence_is_a_nop(dut):
    """FENCE (any pred/succ) retires as a NOP: execution continues and no trap is taken."""
    mem, dbg = await _setup_test(dut)
    fence = (0x0FF << 20) | 0b0001111  # FENCE iorw, iorw
    fence_w = (0x011 << 20) | 0b0001111  # FENCE w, w
    program = [
        ADDI(1, 0, HANDLER),
        CSRRW(0, CSR_MTVEC, 1),
        *li(5, 0x1234_5678),
        fence,
        fence_w,
        ADDI(2, 5, 1),  # executes after both fences
        EBREAK(),
    ]
    handler = [ADDI(3, 0, 0x55), EBREAK()]  # only reachable through a trap
    await fresh_run(dut, mem, dbg, program, {HANDLER + 4 * i: w for i, w in enumerate(handler)})
    assert await dbg.read_gpr(2) == 0x1234_5679
    assert await dbg.read_gpr(3) == 0, "a trap handler ran: FENCE must not raise an exception"
