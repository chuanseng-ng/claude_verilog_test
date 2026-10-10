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
  test_mcycle_counts_every_clock_cycle           mcycle vs the testbench clock count (kiit)
  test_counters_match_cycle_model_random         per-cycle counter state vs CsrModel.tick() over
                                                 random programs with events coinciding with CSRs
  test_counter_carry_vs_write_alignment          low/high-word carry against a write to the other
                                                 half, swept over the alignment
  test_counters_through_trap_and_mret            counters keep counting in trap-entry / MRET cycles
  test_minstret_matches_retirements_between_reads  minstret delta == retire strobes between reads
"""

import random
from dataclasses import dataclass

import cocotb
from cocotb.triggers import ReadOnly, RisingEdge

from sim.riscv_encoder import (
    ADDI,
    BEQ,
    BNE,
    CSRRC,
    CSRRCI,
    CSRRS,
    CSRRSI,
    CSRRW,
    CSRRWI,
    EBREAK,
    ECALL,
    JAL,
    LUI,
    LW,
    MRET,
    SW,
)
from tb.cocotb.common.clock_reset import reset_dut
from tb.cocotb.cpu.phase2_test_utils import _setup_test
from tb.models.csr_model import (
    CSR_DCACHE_FLUSH,
    CSR_DCACHE_INVAL,
    CSR_MARCHID,
    CSR_MCAUSE,
    CSR_MCOUNTINHIBIT,
    CSR_MCYCLE,
    CSR_MCYCLEH,
    CSR_MEPC,
    CSR_MHARTID,
    CSR_MHPMCOUNTER3,
    CSR_MHPMCOUNTER4,
    CSR_MHPMCOUNTER5,
    CSR_MIE,
    CSR_MIMPID,
    CSR_MINSTRET,
    CSR_MINSTRETH,
    CSR_MIP,
    CSR_MSTATUS,
    CSR_MTVEC,
    CSR_MVENDORID,
    CsrModel,
    IllegalCsrError,
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


async def fresh_run(
    dut, mem, dbg, program: list[int], preset=None, *, timer_irq=0, ext_irq=0, timeout_cycles=6000
):
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
    await dbg.wait_halted(timeout_cycles=timeout_cycles)


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
            bad.append(
                f"  op {i} {op.describe()}: rd=x{i + 1} got {got:#010x}, want {want[i]:#010x}"
            )
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


# ---------------------------------------------------------------------------
# Counter accuracy against the testbench's own cycle count (bead a5ze slice 2)
# ---------------------------------------------------------------------------
N_FILLER = 8  # back-to-back legal CSR reads between the two counter samples
CSR_PC_A, CSR_PC_M = 0x04, 0x08  # first mcycle / minstret sample (loop body start)


def _counter_loop_program(filler_csr: int = CSR_MIMPID) -> tuple[list[int], int, int]:
    """Loop body: sample mcycle (A), sample minstret (M), N CSR reads, sample both again."""
    body = [
        CSRRS(1, CSR_MCYCLE, 0),  # A  @0x04
        CSRRS(3, CSR_MINSTRET, 0),  # M  @0x08
        *[CSRRS(0, filler_csr, 0)] * N_FILLER,
    ]
    pc_b = 4 + 4 * len(body)
    body += [CSRRS(2, CSR_MCYCLE, 0), CSRRS(4, CSR_MINSTRET, 0)]  # B, B'
    bne_pc = 4 + 4 * len(body) + 4  # after the ADDI
    body += [ADDI(5, 5, -1), BNE(5, 0, 4 - bne_pc)]
    return [ADDI(5, 0, 2), *body, EBREAK()], pc_b, pc_b + 4


async def _sample_counters(dut, mem, dbg, filler_csr: int = CSR_MIMPID):
    """Run the loop; return (d_mcycle, tb_cycles, d_minstret, tb_commits) for the LAST pass."""
    program, pc_b, pc_bm = _counter_loop_program(filler_csr)
    commit_cycle: dict[int, int] = {}
    commits: list[int] = []  # cycle number of every commit
    state = {"n": 0}

    async def watch():
        while True:
            await RisingEdge(dut.clk_i)
            state["n"] += 1
            if int(dut.commit_valid_o.value):
                commit_cycle[int(dut.commit_pc_o.value)] = state["n"]
                commits.append(state["n"])

    task = cocotb.start_soon(watch())
    await fresh_run(dut, mem, dbg, program)
    task.cancel()
    d_cycle = (await dbg.read_gpr(2) - await dbg.read_gpr(1)) & 0xFFFF_FFFF
    d_inst = (await dbg.read_gpr(4) - await dbg.read_gpr(3)) & 0xFFFF_FFFF
    tb_cycles = commit_cycle[pc_b] - commit_cycle[CSR_PC_A]
    # Instructions the testbench saw commit between the two minstret samples (CSR instructions
    # take several cycles each here, so this is not the cycle distance).
    tb_commits = len([c for c in commits if commit_cycle[CSR_PC_M] < c <= commit_cycle[pc_bm]])
    return d_cycle, tb_cycles, d_inst, tb_commits


# Regression test for bead kiit / GH #260 (was a strict expect_fail until the fix): the counters sat
# in the else of "if (csr_access && !csr_illegal)", so every cycle a legal CSR instruction was in EX
# dropped ALL increments.  Measured before the fix: 20 counted over 30 real cycles in a window of
# 10 CSR instructions.  The +-1 tolerance below must not be widened.
@cocotb.test()
async def test_mcycle_counts_every_clock_cycle(dut):
    """mcycle is a cycle counter: across a CSR-heavy window it must advance by the number of
    clocks the testbench saw, not skip the cycles in which a CSR instruction is in EX.

    The window holds 10 CSR instructions in a row.  The reference is the testbench's own count of
    clocks between the commits of the two samples (same pipeline offset, so equal to the EX-to-EX
    distance).
    """
    mem, dbg = await _setup_test(dut)
    d_cycle, tb_cycles, d_inst, tb_commits = await _sample_counters(dut, mem, dbg)
    dut._log.info(f"mcycle delta {d_cycle} vs testbench cycles {tb_cycles}")
    dut._log.info(f"minstret delta {d_inst} vs testbench commits {tb_commits}")
    assert abs(d_cycle - tb_cycles) <= 1, (
        f"mcycle advanced {d_cycle} over {tb_cycles} real clock cycles"
    )


@cocotb.test()
async def test_mcycle_counts_through_read_only_mcycle_reads(dut):
    """Reading mcycle itself with CSRRS rd, mcycle, x0 does not write it, so it must not stall it.

    Same window as above, but the filler CSR instructions are read-only accesses to mcycle.  A fix
    that lets a CSR write override the increment without checking that the instruction writes at
    all would write the stale value back on every one of these reads.
    """
    mem, dbg = await _setup_test(dut)
    d_cycle, tb_cycles, _, _ = await _sample_counters(dut, mem, dbg, CSR_MCYCLE)
    assert abs(d_cycle - tb_cycles) <= 1, (
        f"mcycle advanced {d_cycle} over {tb_cycles} cycles with read-only mcycle fillers"
    )


# ---------------------------------------------------------------------------
# Cycle-accurate counter checker (bead kiit)
# ---------------------------------------------------------------------------
_CTR_WORDS = {
    "mcycle": (CSR_MCYCLE, CSR_MCYCLEH),
    "minstret": (CSR_MINSTRET, CSR_MINSTRETH),
    "hpm3": (CSR_MHPMCOUNTER3,),
    "hpm4": (CSR_MHPMCOUNTER4,),
    "hpm5": (CSR_MHPMCOUNTER5,),
}
_STROBE = {
    "minstret": "retire_i",
    "hpm3": "icache_miss_i",
    "hpm4": "dcache_miss_i",
    "hpm5": "branch_mispred_i",
}
_INHIBIT_BIT = {"mcycle": 0, "minstret": 2, "hpm3": 3, "hpm4": 4, "hpm5": 5}
_STATE = {
    CSR_MCYCLE: ("mcycle_q", 0),
    CSR_MCYCLEH: ("mcycle_q", 32),
    CSR_MINSTRET: ("minstret_q", 0),
    CSR_MINSTRETH: ("minstret_q", 32),
    CSR_MHPMCOUNTER3: ("mhpmcounter3_q", 0),
    CSR_MHPMCOUNTER4: ("mhpmcounter4_q", 0),
    CSR_MHPMCOUNTER5: ("mhpmcounter5_q", 0),
    CSR_MCOUNTINHIBIT: ("mcountinhibit_q", 0),
}
_SIGNALS = (
    "csr_access",
    "csr_addr",
    "csr_op",
    "csr_wdata",
    "rs1_addr",
    "csr_illegal",
    "trap_entry",
    "mret",
    "retire_i",
    "branch_mispred_i",
    "icache_miss_i",
    "dcache_miss_i",
)
_CSR_KIND = {1: "RW", 2: "RS", 3: "RC", 5: "RW", 6: "RS", 7: "RC"}


class CounterMonitor:
    """Steps CsrModel.tick() once per clock from the CSR file's own inputs and compares the full
    counter state (mcycle[h], minstret[h], mhpmcounter3-5, mcountinhibit) with the DUT every cycle.

    Samples are taken after each rising edge, when the inputs for the NEXT edge have settled, so
    the model's prediction made at sample n is compared with the DUT state seen at sample n + 1.
    ``cov`` counts the cycles in which a counter's increment coincided with each kind of CSR
    activity, so a test can prove its stimulus really produced the case it claims to check.
    """

    def __init__(self, dut):
        self.dut = dut
        self.csr = dut.u_core.u_csr
        self.cycle = 0
        self.mismatches: list[str] = []
        self.cov: dict[str, int] = {}
        self.minstret_reads: list[int] = []  # retire strobes already counted at each read in EX
        self.retired = 0
        self._task = None
        self._model: CsrModel | None = None

    def start(self):
        self._task = cocotb.start_soon(self._run())

    def stop(self):
        if self._task is not None:
            self._task.cancel()

    def _bump(self, key: str):
        self.cov[key] = self.cov.get(key, 0) + 1

    def _snapshot(self) -> dict[int, int]:
        out = {}
        for csr, (name, shift) in _STATE.items():
            out[csr] = (int(getattr(self.csr, name).value) >> shift) & 0xFFFF_FFFF
        return out

    async def _run(self):
        while True:
            await RisingEdge(self.dut.clk_i)
            await ReadOnly()
            if not int(self.csr.rst_n.value):
                self._model, self.retired = None, 0
                continue
            snap = self._snapshot()
            if self._model is None:
                self._model = CsrModel()
                self._model.regs.update(snap)
            else:
                for csr, want in snap.items():
                    got = self._model.regs[csr]
                    if got != want and len(self.mismatches) < 8:
                        self.mismatches.append(
                            f"cycle {self.cycle} csr {csr:#05x}: "
                            f"DUT {want:#010x}, model {got:#010x}"
                        )
                self._model.regs.update(snap)  # resync so one bug is reported once
            self._step(snap[CSR_MCOUNTINHIBIT])
            self.cycle += 1

    def _step(self, inhibit: int):
        sig = {n: int(getattr(self.csr, n).value) for n in _SIGNALS}
        legal = bool(sig["csr_access"]) and not sig["csr_illegal"]
        squashed = bool(sig["trap_entry"] or sig["mret"])
        addr, op = sig["csr_addr"], sig["csr_op"]
        imm = bool(op & 4)
        wdata_low = sig["csr_wdata"] & 0x1F
        writes = _CSR_KIND.get(op) == "RW" or (wdata_low != 0 if imm else sig["rs1_addr"] != 0)
        if legal and addr == CSR_MINSTRET:
            self.minstret_reads.append(self.retired)
        access = None
        if legal and not squashed:
            access = (_CSR_KIND[op], addr, sig["csr_wdata"], imm, not imm and sig["rs1_addr"] == 0)
        for name, words in _CTR_WORDS.items():
            strobe = 1 if name == "mcycle" else sig[_STROBE[name]]
            if not strobe or inhibit >> _INHIBIT_BIT[name] & 1:
                continue
            if sig["trap_entry"]:
                self._bump(f"{name}:event_in_trap_entry")
            elif sig["mret"]:
                self._bump(f"{name}:event_in_mret")
            elif legal and addr in words:
                self._bump(f"{name}:event_with_{'write' if writes else 'readonly'}_to_self")
            elif legal:
                self._bump(f"{name}:event_with_csr_to_other")
            else:
                self._bump(f"{name}:event_no_csr")
            # a write to one half of a 64-bit counter on the cycle its low word wraps
            if name in ("mcycle", "minstret") and legal and not squashed and writes:
                if addr in words and self._model.regs[words[0]] == 0xFFFF_FFFF:
                    self._bump(f"{name}:write_{'lo' if addr == words[0] else 'hi'}_at_wrap")
        if sig["retire_i"]:
            self.retired += 1
        try:
            self._model.tick(
                retire=bool(sig["retire_i"]),
                icache_miss=bool(sig["icache_miss_i"]),
                dcache_miss=bool(sig["dcache_miss_i"]),
                branch_mispred=bool(sig["branch_mispred_i"]),
                access=access,
            )
        except IllegalCsrError:
            self.mismatches.append(
                f"cycle {self.cycle}: model rejects csr {addr:#05x} the RTL took"
            )


_COUNTER_CSRS = [
    CSR_MCYCLE,
    CSR_MCYCLEH,
    CSR_MINSTRET,
    CSR_MINSTRETH,
    CSR_MHPMCOUNTER3,
    CSR_MHPMCOUNTER4,
    CSR_MHPMCOUNTER5,
]
_NOP = ADDI(0, 0, 0)
DATA_BASE = 0x4000
POISON = ADDI(31, 31, 1)  # sits in the shadow of a taken branch / jump; never architecturally run
_TAKEN_BEQ = BEQ(0, 0, 8)


def _random_csr_instr(rng: random.Random, rd: int, addr: int) -> list[int]:
    kind = rng.choice(["RW", "RS", "RC"])
    if rng.random() < 0.4:
        return [_IMM_FORM[kind](rd, addr, rng.choice([0, 1, 5, 31]))]
    if rng.random() < 0.4:
        return [_REG_FORM[kind](rd, addr, 0)]
    value = rng.choice([0, 1, 0xFFFF_FFFF, 0xFFFF_FFF0, rng.getrandbits(32)])
    return [*li(SRC, value), _REG_FORM[kind](rd, addr, SRC)]


def random_counter_program(seed: int, n_items: int = 90) -> list[int]:
    """Straight-line program mixing counter CSR accesses with I$ / D$ misses and taken branches.

    Straight-line code walks into a new I$ line every four instructions, loads from fresh 16-byte
    lines miss in the D$, and taken forward branches / JALs raise the redirect strobe, so the three
    event counters see events at many different offsets from the CSR instructions.
    """
    rng = random.Random(seed)
    prog = [*li(5, DATA_BASE)]
    load_off = 0
    unfreeze_at = -1
    for i in range(n_items):
        rd = 6 + rng.randrange(20)
        roll = rng.random()
        if roll < 0.30:
            prog += _random_csr_instr(rng, rd, rng.choice(_COUNTER_CSRS))
        elif roll < 0.48:
            if rng.random() < 0.5:
                prog.append(CSRRS(rd, CSR_MIMPID, 0))
            else:
                prog += _random_csr_instr(rng, rd, rng.choice([CSR_MEPC, CSR_MCAUSE]))
        elif roll < 0.62:
            prog += [ADDI(rd, rd, 1)] * rng.randrange(1, 4)
        elif roll < 0.78 and load_off < 2000:
            prog.append(LW(29, 5, load_off))
            load_off += 16 + 4 * rng.randrange(3)
        elif roll < 0.90:
            prog += [_TAKEN_BEQ, POISON]
        elif roll < 0.96:
            prog += [JAL(0, 8), POISON]
        elif unfreeze_at < 0:
            mask = rng.choice([0x1, 0x4, 0x8, 0x10, 0x20])
            prog += [*li(SRC, mask), CSRRW(0, CSR_MCOUNTINHIBIT, SRC)]
            unfreeze_at = i + 3
        if 0 <= unfreeze_at <= i:
            prog.append(CSRRW(0, CSR_MCOUNTINHIBIT, 0))
            unfreeze_at = -1
    if unfreeze_at >= 0:
        prog.append(CSRRW(0, CSR_MCOUNTINHIBIT, 0))
    return [*prog, EBREAK()]


def _assert_clean(mon: CounterMonitor, what: str):
    assert mon.cycle > 20, f"{what}: monitor saw only {mon.cycle} cycles"
    assert not mon.mismatches, (
        f"{what}: counter state diverged from the spec model:\n  " + "\n  ".join(mon.mismatches)
    )


async def _run_monitored(dut, mem, dbg, program, **kw) -> CounterMonitor:
    mon = CounterMonitor(dut)
    mon.start()
    try:
        await fresh_run(dut, mem, dbg, program, **kw)
        await RisingEdge(dut.clk_i)
    finally:
        mon.stop()
    return mon


@cocotb.test()
async def test_counters_match_cycle_model_random(dut):
    """Every counter equals the spec model after every cycle, with events coinciding with CSRs."""
    mem, dbg = await _setup_test(dut)
    total: dict[str, int] = {}
    for seed in range(1, 9):
        prog = random_counter_program(seed)
        mon = await _run_monitored(dut, mem, dbg, prog, timeout_cycles=20000)
        _assert_clean(mon, f"seed {seed}")
        for k, v in mon.cov.items():
            total[k] = total.get(k, 0) + v
    dut._log.info(f"coverage: {dict(sorted(total.items()))}")
    # The stimulus must really hit each coincidence, or a green run proves nothing.
    for name in _CTR_WORDS:
        for case in (
            "event_with_csr_to_other",
            "event_with_readonly_to_self",
            "event_with_write_to_self",
        ):
            assert total.get(f"{name}:{case}", 0) > 0, f"stimulus never produced {name}:{case}"


def _carry_alignment_program() -> list[int]:
    """Write a low word that wraps ``d`` increments later, then write one half ``n`` NOPs after."""
    prog: list[int] = []
    for pair_lo, pair_hi in ((CSR_MCYCLE, CSR_MCYCLEH), (CSR_MINSTRET, CSR_MINSTRETH)):
        for target in (pair_lo, pair_hi):
            for d in range(6):
                for n in range(5):
                    prog += [*li(SRC, (0xFFFF_FFFF - d) & 0xFFFF_FFFF), CSRRW(0, pair_lo, SRC)]
                    prog += [*li(SRC, 0x1234_0000 + 16 * d + n), *([_NOP] * n)]
                    prog += [CSRRW(0, target, SRC)]
    return [*prog, EBREAK()]


@cocotb.test()
async def test_counter_carry_vs_write_alignment(dut):
    """A write to one half of mcycle / minstret at the cycle the low word wraps follows the spec.

    Write to the low word: the written value wins and the discarded increment's carry must not
    reach the high word.  Write to the high word: the written value wins, the low word keeps
    counting.  The (d, n) sweep moves the write across the wrap cycle; the monitor coverage proves
    that both a low-word and a high-word write landed exactly on it, for both counters.
    """
    mem, dbg = await _setup_test(dut)
    mon = await _run_monitored(dut, mem, dbg, _carry_alignment_program(), timeout_cycles=60000)
    _assert_clean(mon, "carry alignment sweep")
    dut._log.info(f"coverage: {dict(sorted(mon.cov.items()))}")
    for name in ("mcycle", "minstret"):
        for half in ("lo", "hi"):
            assert mon.cov.get(f"{name}:write_{half}_at_wrap", 0) > 0, (
                f"sweep never wrote {name} {half} word on the wrap cycle"
            )


@cocotb.test()
async def test_counters_through_trap_and_mret(dut):
    """Counters keep counting in the cycles a trap is taken and MRET executes."""
    handler = 0x200
    prog = [*li(SRC, handler), CSRRW(0, CSR_MTVEC, SRC)]
    for _ in range(4):
        prog += [ADDI(6, 6, 1), ECALL(), ADDI(7, 7, 1)]
    prog.append(EBREAK())
    prog += [_NOP] * (handler // 4 - len(prog))
    prog += [CSRRS(8, CSR_MEPC, 0), ADDI(8, 8, 4), CSRRW(0, CSR_MEPC, 8), MRET()]
    mem, dbg = await _setup_test(dut)
    mon = await _run_monitored(dut, mem, dbg, prog, timeout_cycles=20000)
    _assert_clean(mon, "trap/mret")
    dut._log.info(f"coverage: {dict(sorted(mon.cov.items()))}")
    assert mon.cov.get("mcycle:event_in_trap_entry", 0) >= 4, "no trap-entry cycles seen"
    assert mon.cov.get("mcycle:event_in_mret", 0) >= 4, "no MRET cycles seen"
    assert await dbg.read_gpr(6) == 4 and await dbg.read_gpr(7) == 4, "trap handler did not return"


@cocotb.test()
async def test_minstret_matches_retirements_between_reads(dut):
    """minstret read by a CSR instruction == retire strobes counted before that instruction's EX.

    Counted at the commit interface (retire_i == commit_valid_o), so older instructions still in
    flight when the read executes are correctly NOT yet included.  A retirement that lands in the
    same cycle as an earlier CSR instruction's EX must not be dropped.
    """
    rng = random.Random(7)
    prog: list[int] = []
    n_reads = 14
    for k in range(n_reads):
        for _ in range(rng.randrange(0, 5)):
            instr = rng.choice([ADDI(20, 20, 1), CSRRS(0, CSR_MIMPID, 0), _TAKEN_BEQ])
            prog.append(instr)
            if instr == _TAKEN_BEQ:
                prog.append(POISON)
        prog.append(CSRRS(k + 1, CSR_MINSTRET, 0))
    prog.append(EBREAK())
    mem, dbg = await _setup_test(dut)
    mon = await _run_monitored(dut, mem, dbg, prog)
    _assert_clean(mon, "minstret reads")
    assert len(mon.minstret_reads) == n_reads, mon.minstret_reads
    got = [await dbg.read_gpr(k + 1) for k in range(n_reads)]
    assert got == mon.minstret_reads, (
        f"minstret read {got} != retirements counted {mon.minstret_reads}"
    )
