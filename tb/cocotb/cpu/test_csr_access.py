"""
CSR-file access coverage for rv32i_cpu_top (bead a5ze, Zicsr / Phase 5 M7).

Every test runs a generated CSR instruction sequence on the DUT and compares each rd with the
expected value from tb/models/csr_model.py, which is written from the project spec
(docs/design/PHASE2_ARCHITECTURE_SPEC.md 4.2, PHASE5 M7 counter map), not from the RTL.  The
GPR results are read back through the APB debug window, so no internal signal is touched.

  test_mstatus_all_ops              CSRRW/RS/RC and the three immediate forms on mstatus, incl.
                                    the rs1==x0 / uimm==0 write suppression and WARL masking
  test_mie_mtvec_mepc_mcause_ops    the same op matrix on mie, mtvec (MODE forced to 0), mepc,
                                    mcause, mcountinhibit (bit 1 and bits [31:6] read 0)
  test_id_mip_and_readonly_csrs     mvendorid/marchid/mimpid/mhartid read values, mip following
                                    timer_irq_i / ext_irq_i, writes to read-only CSRs ignored,
                                    0x7C0 / 0x7C1 read back 0
  test_counter_words_frozen         mcycle[h], minstret[h], mhpmcounter3-5 written and read back
                                    with every op while mcountinhibit freezes them
  test_counter_carry_into_high_word mcycle / minstret low-word wrap carries into the high word
  test_dcache_flush_op_forms        0x7C0 fires only for non-suppressed forms (observed as a
                                    write-back reaching the AXI memory)
  test_dcache_inval_op_forms        0x7C1 likewise (observed as a dirty line being discarded)
"""

from dataclasses import dataclass

import cocotb
from cocotb.triggers import RisingEdge

from sim.riscv_encoder import (
    ADDI,
    CSRRC,
    CSRRCI,
    CSRRS,
    CSRRSI,
    CSRRW,
    CSRRWI,
    EBREAK,
    LUI,
    LW,
    SW,
)
from tb.cocotb.common.clock_reset import reset_dut
from tb.cocotb.cpu.phase2_test_utils import _setup_test
from tb.models.csr_model import (
    CSR_DCACHE_FLUSH,
    CSR_DCACHE_INVAL,
    CSR_MCAUSE,
    CSR_MCOUNTINHIBIT,
    CSR_MCYCLE,
    CSR_MCYCLEH,
    CSR_MEPC,
    CSR_MHARTID,
    CSR_MHPMCOUNTER3,
    CSR_MHPMCOUNTER4,
    CSR_MHPMCOUNTER5,
    CSR_MARCHID,
    CSR_MIE,
    CSR_MIMPID,
    CSR_MINSTRET,
    CSR_MINSTRETH,
    CSR_MIP,
    CSR_MSTATUS,
    CSR_MTVEC,
    CSR_MVENDORID,
    CsrModel,
)

_REG_FORM = {"RW": CSRRW, "RS": CSRRS, "RC": CSRRC}
_IMM_FORM = {"RW": CSRRWI, "RS": CSRRSI, "RC": CSRRCI}
SRC = 30  # scratch GPR holding the register-form operand
FREEZE_ALL = 0x3D  # mcountinhibit: cycle, instret, hpm3, hpm4, hpm5


@dataclass(frozen=True)
class Op:
    """One CSR instruction.  rd is assigned by position (x1, x2, ...)."""

    kind: str  # "RW" | "RS" | "RC"
    addr: int
    operand: int = 0
    imm: bool = False  # CSRR?I form: operand is the 5-bit uimm
    x0: bool = False  # register form with rs1 == x0 (operand is 0)
    check: bool = True  # False: rd is timing-dependent (a counter's value before it was frozen)

    def describe(self) -> str:
        form = "I" if self.imm else ("(x0)" if self.x0 else "")
        return f"CSRR{self.kind[1]}{form} {self.addr:#05x}, {self.operand:#x}"


def li(rd: int, value: int) -> list[int]:
    """Load a 32-bit constant (LUI + ADDI with the sign correction)."""
    value &= 0xFFFF_FFFF
    lo = value & 0xFFF
    if lo >= 0x800:
        lo -= 0x1000
    hi = ((value - lo) >> 12) & 0xF_FFFF
    return [LUI(rd, hi), ADDI(rd, rd, lo)]


def assemble(ops: list[Op]) -> list[int]:
    assert len(ops) <= 28, "rd registers x1..x28 only"
    prog: list[int] = []
    for i, op in enumerate(ops):
        rd = i + 1
        if op.imm:
            prog.append(_IMM_FORM[op.kind](rd, op.addr, op.operand))
        elif op.x0:
            prog.append(_REG_FORM[op.kind](rd, op.addr, 0))
        else:
            prog += li(SRC, op.operand)
            prog.append(_REG_FORM[op.kind](rd, op.addr, SRC))
    prog.append(EBREAK())
    return prog


def expected_results(ops: list[Op], *, timer_irq: int = 0, ext_irq: int = 0) -> CsrModel:
    """Run ``ops`` through the model; the model's per-op old values are kept on the side."""
    model = CsrModel()
    model.results = []  # type: ignore[attr-defined]
    for op in ops:
        old = model.execute(
            op.kind,
            op.addr,
            op.operand,
            imm=op.imm,
            suppress_write=op.x0 and op.kind != "RW",
            timer_irq=timer_irq,
            ext_irq=ext_irq,
        )
        model.results.append(old)  # type: ignore[attr-defined]
    return model


async def fresh_run(dut, mem, dbg, program: list[int], preset=None, *, timer_irq=0, ext_irq=0):
    """Reset the DUT and run ``program`` against a re-seeded memory (the clock keeps running).

    One clock and one AXI memory model per cocotb test; every program gets a fresh reset.
    """
    mem.mem.clear()
    mem.mem.update(preset or {})
    await reset_dut(dut)
    dut.timer_irq_i.value = timer_irq
    dut.ext_irq_i.value = ext_irq
    for i, word in enumerate(program):
        mem.write_word(4 * i, word)
    await RisingEdge(dut.clk_i)
    await dbg.wait_halted(timeout_cycles=6000)


async def run_ops(dut, mem, dbg, ops: list[Op], *, timer_irq: int = 0, ext_irq: int = 0):
    """Run ``ops`` on the DUT and assert every rd against the model."""
    await fresh_run(dut, mem, dbg, assemble(ops), timer_irq=timer_irq, ext_irq=ext_irq)
    want = expected_results(ops, timer_irq=timer_irq, ext_irq=ext_irq).results  # type: ignore[attr-defined]
    bad = []
    for i, op in enumerate(ops):
        if not op.check:
            continue
        got = await dbg.read_gpr(i + 1)
        if got != want[i]:
            bad.append(f"  op {i} {op.describe()}: rd=x{i + 1} got {got:#010x}, want {want[i]:#010x}")
    assert not bad, "CSR result mismatch vs spec model:\n" + "\n".join(bad)


def full_matrix(addr: int, a: int, b: int) -> list[Op]:
    """Every op x form on one CSR: reads see the effect of the previous write."""
    return [
        Op("RW", addr, a),
        Op("RS", addr, b),
        Op("RC", addr, a),
        Op("RS", addr, 0, x0=True),  # read only, no write
        Op("RC", addr, 0, x0=True),
        Op("RW", addr, 0x15, imm=True),
        Op("RS", addr, 0x0A, imm=True),
        Op("RC", addr, 0x05, imm=True),
        Op("RS", addr, 0, imm=True),  # uimm == 0: no write
        Op("RC", addr, 0, imm=True),
        Op("RW", addr, 0, x0=True),  # CSRRW with x0 DOES write 0
        Op("RS", addr, 0, x0=True),
    ]


@cocotb.test()
async def test_mstatus_all_ops(dut):
    """mstatus: MIE/MPIE writable, MPP hardwired 0x1800, every op and form."""
    mem, dbg = await _setup_test(dut)
    ops = [
        *full_matrix(CSR_MSTATUS, 0x88, 0x8),
        Op("RW", CSR_MSTATUS, 0xFFFF_FFFF),  # all-ones: only MIE|MPIE stick
        Op("RC", CSR_MSTATUS, 0x8),  # clear MIE only
        Op("RS", CSR_MSTATUS, 0x1F, imm=True),  # imm set: MIE again (+ ignored bits)
        Op("RC", CSR_MSTATUS, 0x1F, imm=True),  # imm clear
        Op("RS", CSR_MSTATUS, 0, x0=True),
    ]
    await run_ops(dut, mem, dbg, ops)


@cocotb.test()
async def test_mie_mtvec_mepc_mcause_ops(dut):
    """The op matrix on the other architectural CSRs, with their WARL rules."""
    mem, dbg = await _setup_test(dut)
    ops = [
        *full_matrix(CSR_MIE, 0x880, 0x80),
        Op("RW", CSR_MIE, 0xFFFF_FFFF),  # only MTIE|MEIE stick
        *full_matrix(CSR_MTVEC, 0x2000_0100, 0x203),
        Op("RW", CSR_MTVEC, 0x0000_0103),  # MODE bits forced to 0
        Op("RS", CSR_MTVEC, 0, x0=True),
    ]
    await run_ops(dut, mem, dbg, ops)


@cocotb.test()
async def test_mepc_mcause_mcountinhibit_ops(dut):
    """mepc / mcause are plain 32-bit RW; mcountinhibit masks to bits 0,2,3,4,5."""
    mem, dbg = await _setup_test(dut)
    ops = [
        *full_matrix(CSR_MEPC, 0xDEAD_BEE0, 0x0000_FF00),
        Op("RW", CSR_MCAUSE, 0x8000_000B),
        Op("RS", CSR_MCAUSE, 0x0000_0002),
        Op("RC", CSR_MCAUSE, 0x8000_0000),
        Op("RS", CSR_MCAUSE, 0x1F, imm=True),
        Op("RC", CSR_MCAUSE, 0x0F, imm=True),
        Op("RS", CSR_MCAUSE, 0, x0=True),
    ]
    await run_ops(dut, mem, dbg, ops)

    ops = [
        Op("RW", CSR_MCOUNTINHIBIT, 0xFFFF_FFFF),  # bit 1 and [31:6] read back 0
        Op("RC", CSR_MCOUNTINHIBIT, 0x4),
        Op("RS", CSR_MCOUNTINHIBIT, 0x2),  # reserved bit: stays 0
        Op("RS", CSR_MCOUNTINHIBIT, 0x1F, imm=True),
        Op("RC", CSR_MCOUNTINHIBIT, 0x1F, imm=True),
        Op("RW", CSR_MCOUNTINHIBIT, 0, x0=True),
        Op("RS", CSR_MCOUNTINHIBIT, 0, x0=True),
    ]
    await run_ops(dut, mem, dbg, ops)


@cocotb.test()
async def test_id_mip_and_readonly_csrs(dut):
    """ID CSRs read their spec values; mip mirrors the IRQ pins; writes to them are ignored."""
    mem, dbg = await _setup_test(dut)
    ops = [
        Op("RS", CSR_MVENDORID, 0, x0=True),
        Op("RS", CSR_MARCHID, 0, x0=True),
        Op("RS", CSR_MIMPID, 0, x0=True),
        Op("RS", CSR_MHARTID, 0, x0=True),
        Op("RW", CSR_MVENDORID, 0xFFFF_FFFF),  # write ignored ...
        Op("RS", CSR_MVENDORID, 0, x0=True),  # ... still 0
        Op("RW", CSR_MARCHID, 0xFFFF_FFFF),
        Op("RS", CSR_MARCHID, 0, x0=True),
        Op("RW", CSR_MIMPID, 0xFFFF_FFFF),
        Op("RS", CSR_MIMPID, 0, x0=True),
        Op("RW", CSR_MHARTID, 0xFFFF_FFFF),
        Op("RS", CSR_MHARTID, 0, x0=True),
        Op("RW", CSR_DCACHE_FLUSH, 0, x0=True),  # write-only maintenance CSRs read 0
        Op("RW", CSR_DCACHE_INVAL, 0, x0=True),
        Op("RS", CSR_DCACHE_FLUSH, 0, x0=True),
        Op("RS", CSR_DCACHE_INVAL, 0, x0=True),
    ]
    await run_ops(dut, mem, dbg, ops)

    # mip follows the pins in all four combinations; MIE is 0 so no trap is taken.
    for timer_irq, ext_irq in ((0, 0), (1, 0), (0, 1), (1, 1)):
        mip_ops = [
            Op("RS", CSR_MIP, 0, x0=True),
            Op("RW", CSR_MIP, 0xFFFF_FFFF),  # read-only: write ignored
            Op("RS", CSR_MIP, 0, x0=True),
            Op("RC", CSR_MIP, 0xFFFF_FFFF),
            Op("RS", CSR_MIP, 0xFFFF_FFFF),
            Op("RS", CSR_MIP, 0, x0=True),
        ]
        await run_ops(dut, mem, dbg, mip_ops, timer_irq=timer_irq, ext_irq=ext_irq)


@cocotb.test()
async def test_counter_words_frozen(dut):
    """Write and read every counter word with all ops while mcountinhibit freezes them."""
    mem, dbg = await _setup_test(dut)
    freeze = [Op("RW", CSR_MCOUNTINHIBIT, FREEZE_ALL)]
    for csr in (CSR_MCYCLE, CSR_MCYCLEH, CSR_MINSTRET, CSR_MINSTRETH):
        ops = freeze + [
            Op("RW", csr, 0xA5A5_5A5A, check=False),  # old value = count before the freeze
            Op("RS", csr, 0x0000_FFFF),
            Op("RC", csr, 0x00FF_00FF),
            Op("RW", csr, 0x13, imm=True),
            Op("RS", csr, 0x0C, imm=True),
            Op("RC", csr, 0x01, imm=True),
            Op("RS", csr, 0, x0=True),
            Op("RC", csr, 0, imm=True),
        ]
        await run_ops(dut, mem, dbg, ops)
    for csr in (CSR_MHPMCOUNTER3, CSR_MHPMCOUNTER4, CSR_MHPMCOUNTER5):
        ops = freeze + [
            Op("RW", csr, 0xFFFF_FFF0, check=False),
            Op("RC", csr, 0x0000_00F0),
            Op("RS", csr, 0x8000_0001),
            Op("RW", csr, 0x1F, imm=True),
            Op("RC", csr, 0x10, imm=True),
            Op("RS", csr, 0, x0=True),
        ]
        await run_ops(dut, mem, dbg, ops)

    # Both words of one 64-bit counter are independent registers.
    ops = freeze + [
        Op("RW", CSR_MCYCLE, 0x1111_1111, check=False),
        Op("RW", CSR_MCYCLEH, 0x2222_2222, check=False),
        Op("RS", CSR_MCYCLE, 0, x0=True),
        Op("RS", CSR_MCYCLEH, 0, x0=True),
        Op("RW", CSR_MINSTRET, 0x3333_3333, check=False),
        Op("RW", CSR_MINSTRETH, 0x4444_4444, check=False),
        Op("RS", CSR_MINSTRET, 0, x0=True),
        Op("RS", CSR_MINSTRETH, 0, x0=True),
        Op("RS", CSR_MCYCLE, 0, x0=True),
    ]
    await run_ops(dut, mem, dbg, ops)


@cocotb.test()
async def test_counter_carry_into_high_word(dut):
    """A low-word wrap carries into mcycleh / minstreth (64-bit counters, M7)."""
    nop = ADDI(0, 0, 0)
    program = [
        *li(SRC, FREEZE_ALL),
        CSRRW(0, CSR_MCOUNTINHIBIT, SRC),
        CSRRW(0, CSR_MCYCLEH, 0),
        CSRRW(0, CSR_MINSTRETH, 0),
        *li(SRC, 0xFFFF_FFFF),
        CSRRW(0, CSR_MCYCLE, SRC),
        CSRRW(0, CSR_MINSTRET, SRC),
        CSRRW(0, CSR_MCOUNTINHIBIT, 0),  # release: both counters now run
        *([nop] * 6),
        CSRRS(1, CSR_MCYCLEH, 0),
        CSRRS(2, CSR_MINSTRETH, 0),
        CSRRS(3, CSR_MCYCLE, 0),
        CSRRS(4, CSR_MINSTRET, 0),
        EBREAK(),
    ]
    mem, dbg = await _setup_test(dut)
    await fresh_run(dut, mem, dbg, program)
    mcycleh, minstreth, mcycle, minstret = [await dbg.read_gpr(r) for r in (1, 2, 3, 4)]
    assert mcycleh == 1, f"mcycle wrap must carry into mcycleh: got {mcycleh:#x}"
    assert minstreth == 1, f"minstret wrap must carry into minstreth: got {minstreth:#x}"
    # After the wrap the low words restart near 0: a handful of cycles / retired instructions.
    assert mcycle < 64, f"mcycle low word should have restarted near 0, got {mcycle:#x}"
    assert minstret < 32, f"minstret low word should have restarted near 0, got {minstret:#x}"


# ---------------------------------------------------------------------------
# D-cache maintenance CSRs: which instruction forms actually fire
# ---------------------------------------------------------------------------
DATA_ADDR = 0x400
DIRTY = 0xDEAD_BEEF
STALE = 0x1111_1111

# (label, builder(rd=0, csr, scratch=7) -> instruction, fires)
FORMS = [
    ("CSRRW x0", lambda csr: CSRRW(0, csr, 0), True),
    ("CSRRW x7", lambda csr: CSRRW(0, csr, 7), True),
    ("CSRRS x7", lambda csr: CSRRS(0, csr, 7), True),
    ("CSRRC x7", lambda csr: CSRRC(0, csr, 7), True),
    ("CSRRS x0", lambda csr: CSRRS(0, csr, 0), False),
    ("CSRRC x0", lambda csr: CSRRC(0, csr, 0), False),
    ("CSRRWI 0", lambda csr: CSRRWI(0, csr, 0), True),
    ("CSRRWI 1", lambda csr: CSRRWI(0, csr, 1), True),
    ("CSRRSI 1", lambda csr: CSRRSI(0, csr, 1), True),
    ("CSRRCI 1", lambda csr: CSRRCI(0, csr, 1), True),
    ("CSRRSI 0", lambda csr: CSRRSI(0, csr, 0), False),
    ("CSRRCI 0", lambda csr: CSRRCI(0, csr, 0), False),
]


@cocotb.test()
async def test_dcache_flush_op_forms(dut):
    """0x7C0 writes the dirty line back for every non-suppressed form, never for x0/uimm0 RS/RC."""
    mem, dbg = await _setup_test(dut)
    for label, build, fires in FORMS:
        program = [
            ADDI(5, 0, DATA_ADDR),
            *li(6, DIRTY),
            ADDI(7, 0, 1),
            SW(6, 5, 0),  # dirty line in the write-back D-cache; memory still 0
            build(CSR_DCACHE_FLUSH),
            EBREAK(),
        ]
        await fresh_run(dut, mem, dbg, program, {})
        for _ in range(600):  # the flush scan keeps running after the CPU halts
            await RisingEdge(dut.clk_i)
        got = mem.read_word(DATA_ADDR)
        want = DIRTY if fires else 0
        assert got == want, (
            f"{label} on dcache_flush: memory[{DATA_ADDR:#x}]={got:#010x}, "
            f"want {want:#010x} ({'flush must fire' if fires else 'suppressed, no flush'})"
        )


@cocotb.test()
async def test_dcache_inval_op_forms(dut):
    """0x7C1 discards the dirty line for every non-suppressed form; suppressed forms keep it."""
    mem, dbg = await _setup_test(dut)
    for label, build, fires in FORMS:
        program = [
            ADDI(5, 0, DATA_ADDR),
            *li(6, DIRTY),
            ADDI(7, 0, 1),
            SW(6, 5, 0),  # dirty in cache; memory holds STALE
            build(CSR_DCACHE_INVAL),
            LW(8, 5, 0),
            EBREAK(),
        ]
        await fresh_run(dut, mem, dbg, program, {DATA_ADDR: STALE})
        got = await dbg.read_gpr(8)
        want = STALE if fires else DIRTY
        assert got == want, (
            f"{label} on dcache_inval: load returned {got:#010x}, want {want:#010x} "
            f"({'dirty line must be discarded' if fires else 'suppressed, line kept'})"
        )
