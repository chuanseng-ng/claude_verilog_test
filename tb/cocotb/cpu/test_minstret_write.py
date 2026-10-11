"""Directed tests for a CSR write to minstret / minstreth (bead f7z3).

RISC-V privileged spec: a write to minstret takes effect as if every older instruction had
already retired, and the writing instruction's own retirement does not increment the counter.  The
core applies the write in EX while the retirement strobe trails EX by five stages, so before the
fix older in-flight instructions and the writer itself retired on top of the written value.

Expected values come from the spec, not from the RTL:

* ``V <= minstret read <= V + n`` where ``n`` is the number of instructions that retired between
  the writer and the reader (read from the commit stream), and the read is exactly ``V`` when the
  reader directly follows the writer (``n == 0``);
* a read may trail by at most ONE retirement (the reader's immediate predecessor has not
  retired yet when the reader executes in EX).  That read lag is separate from f7z3 and is pinned
  by ``test_minstret_matches_retirements_between_reads``; it is allowed for here, never more;
* every test also runs the per-cycle ``CounterMonitor`` against ``CsrModel.tick()``, which models
  the in-flight absorption by program-order index (tb/models/csr_model.py).

  test_write_read_back_at_distance          write, then a read 0..3 instructions later, at four
                                            instruction-cache alignments
  test_write_with_older_instruction_in_flight  ALU / CSR / load hit / load miss / load-use / taken
                                            branch in front of the write, and a branch behind it
  test_zeroing_both_halves_back_to_back     csrw minstret ; csrw minstreth reads (0, 0)
  test_low_half_wrap_carries_only_younger_retirements   write 0xFFFFFFFF, no spurious carry
  test_high_half_write_keeps_counting_the_low_half
  test_read_only_forms_are_not_writes       CSRRS/CSRRC rs1=x0, CSRRSI/CSRRCI uimm=0
  test_set_clear_forms_write_with_nonzero_source
  test_wrong_path_write_is_ignored          CSR writes in a taken branch / JAL shadow
  test_write_in_the_cycle_of_a_trap_entry   writer in EX when an older load's trap is taken
  test_mcycle_write_wins_and_counts_on      mcycle / mcycleh analysis (no in-flight term)
  test_hpm_event_of_older_load_lands_after_write   mhpmcounter4 analysis (time-ordered event)
"""

import cocotb
from cocotb.triggers import RisingEdge

from sim.riscv_encoder import (
    ADD,
    ADDI,
    BEQ,
    CSRRC,
    CSRRCI,
    CSRRS,
    CSRRSI,
    CSRRW,
    EBREAK,
    JAL,
    LW,
    MRET,
)
from tb.cocotb.cpu.phase2_test_utils import _setup_test
from tb.cocotb.cpu.test_csr_access import (
    DATA_BASE,
    POISON,
    CounterMonitor,
    _assert_clean,
    arch_csr_seqs,
    fresh_run,
    li,
)
from tb.models.csr_model import (
    CSR_MCYCLE,
    CSR_MCYCLEH,
    CSR_MEPC,
    CSR_MHPMCOUNTER4,
    CSR_MIMPID,
    CSR_MINSTRET,
    CSR_MINSTRETH,
    CSR_MTVEC,
)

V = 0x1000  # a value no retirement count in these programs can reach by accident
NOP = ADDI(0, 0, 0)
TAKEN_BEQ = BEQ(0, 0, 8)
READ_LAG = 1  # documented: a CSR read does not see its immediate predecessor's retirement


class Prog:
    """Instruction list that remembers the pc of each emitted instruction."""

    def __init__(self):
        self.words: list[int] = []

    def emit(self, *words: int) -> int:
        """Append ``words``; return the pc of the first one."""
        pc = 4 * len(self.words)
        self.words.extend(words)
        return pc

    def done(self) -> list[int]:
        return [*self.words, EBREAK()]


class CommitLog:
    """The commit stream (pc of every retired instruction, in order) for one program run."""

    def __init__(self, dut):
        self.dut = dut
        self.pcs: list[int] = []
        self.mon: CounterMonitor | None = None
        self._task = None

    def start(self):
        self._task = cocotb.start_soon(self._run())

    def stop(self):
        if self._task is not None:
            self._task.cancel()

    async def _run(self):
        while True:
            await RisingEdge(self.dut.clk_i)
            if int(self.dut.commit_valid_o.value):
                self.pcs.append(int(self.dut.commit_pc_o.value))

    def between(self, first_pc: int, second_pc: int) -> int:
        """Instructions retired strictly between the retirements at the two pcs."""
        return self.pcs.index(second_pc) - self.pcs.index(first_pc) - 1


async def run_prog(dut, mem, dbg, prog: list[int], **kw) -> tuple[CounterMonitor, CommitLog]:
    """Run ``prog`` with the per-cycle counter monitor and the commit log attached."""
    mon = CounterMonitor(dut, arch_csr_seqs(prog))
    log = CommitLog(dut)
    log.mon = mon
    mon.start()
    log.start()
    try:
        await fresh_run(dut, mem, dbg, prog, timeout_cycles=kw.pop("timeout_cycles", 20000), **kw)
        await RisingEdge(dut.clk_i)
    finally:
        mon.stop()
        log.stop()
    return mon, log


def check_read(
    log: CommitLog, writer_pc: int, reader_pc: int, base: int, got: int, what: str, *, model=True
):
    """Spec check of one counter-word read ``got`` after the write of ``base`` at ``writer_pc``."""
    n = log.between(writer_pc, reader_pc)
    assert base <= got <= base + n, (
        f"{what}: read {got:#x} after writing {base:#x} with {n} instruction(s) retired in "
        f"between; the written value must win, so {base:#x}..{base + n:#x} is the only legal range"
    )
    assert got >= base + n - READ_LAG, (
        f"{what}: read {got:#x} lost more than the documented one-instruction read lag "
        f"(expected {base + n - READ_LAG:#x}..{base + n:#x}): "
        "retirements after the write were dropped"
    )
    if n == 0:
        assert got == base, f"{what}: reader directly after the writer must read exactly {base:#x}"
    if model and log.mon is not None:  # per-cycle model check last: spec violations report first
        _assert_clean(log.mon, what)


# ---------------------------------------------------------------------------
@cocotb.test()
async def test_write_read_back_at_distance(dut):
    """csrrw minstret, V ; d instructions ; csrrs minstret -- d = 0..3 at four I$ alignments."""
    mem, dbg = await _setup_test(dut)
    for pad in range(4):
        for d in range(4):
            p = Prog()
            p.emit(*li(5, V), *([NOP] * pad), ADDI(6, 0, 1), ADDI(6, 0, 2))
            w = p.emit(CSRRW(0, CSR_MINSTRET, 5))
            p.emit(*[ADDI(7, 0, k) for k in range(d)])
            r = p.emit(CSRRS(1, CSR_MINSTRET, 0))
            mon, log = await run_prog(dut, mem, dbg, p.done())
            what = f"pad={pad} d={d}"
            check_read(log, w, r, V, await dbg.read_gpr(1), what)


@cocotb.test()
async def test_write_with_older_instruction_in_flight(dut):
    """The older instruction in front of the write is still retiring when the write executes."""
    mem, dbg = await _setup_test(dut)
    fresh_line = DATA_BASE + 0x100

    def lw_miss(p):  # first touch of a D$ line: miss, then the writer follows immediately
        p.emit(*li(8, fresh_line), LW(6, 8, 0))

    def lw_hit(p):
        p.emit(*li(8, DATA_BASE), LW(6, 8, 0), NOP, NOP, NOP, LW(9, 8, 4))

    def load_use(p):
        p.emit(*li(8, DATA_BASE + 0x200), LW(6, 8, 0), ADD(7, 6, 6))

    def csr_read(p):
        p.emit(CSRRS(6, CSR_MIMPID, 0))

    def alu(p):
        p.emit(ADDI(6, 0, 1), ADDI(6, 0, 2))

    def branch_in_front(p):
        p.emit(TAKEN_BEQ, POISON)

    def minstret_read(p):
        p.emit(CSRRS(6, CSR_MINSTRET, 0))

    cases = {
        "alu": alu,
        "csr_read": csr_read,
        "minstret_read": minstret_read,
        "load_hit": lw_hit,
        "load_miss": lw_miss,
        "load_use": load_use,
        "branch_in_front": branch_in_front,
    }
    for name, front in cases.items():
        for pad in range(4):
            p = Prog()
            p.emit(*li(5, V), *([NOP] * pad))
            front(p)
            w = p.emit(CSRRW(0, CSR_MINSTRET, 5))
            r = p.emit(CSRRS(1, CSR_MINSTRET, 0))
            mon, log = await run_prog(dut, mem, dbg, p.done())
            what = f"{name} pad={pad}"
            check_read(log, w, r, V, await dbg.read_gpr(1), what)

    # A taken branch BEHIND the write: the write executes, the branch flush kills only younger
    # instructions, and the reader after the branch target still sees the written value.
    for pad in range(4):
        p = Prog()
        p.emit(*li(5, V), *([NOP] * pad), ADDI(6, 0, 1))
        w = p.emit(CSRRW(0, CSR_MINSTRET, 5))
        p.emit(TAKEN_BEQ, POISON)
        r = p.emit(CSRRS(1, CSR_MINSTRET, 0))
        mon, log = await run_prog(dut, mem, dbg, p.done())
        what = f"branch_behind pad={pad}"
        check_read(log, w, r, V, await dbg.read_gpr(1), what)


@cocotb.test()
async def test_zeroing_both_halves_back_to_back(dut):
    """The usual `csrw minstret, x0 ; csrw minstreth, x0` reads (0, 0) -- both writers overlap in
    the pipeline, and neither one's own retirement may leak into either word."""
    mem, dbg = await _setup_test(dut)
    for pad in range(4):
        for gap in range(3):
            p = Prog()
            p.emit(*([NOP] * (8 + pad)))  # a non-zero count to zero
            w_lo = p.emit(CSRRW(0, CSR_MINSTRET, 0))
            p.emit(*([NOP] * gap))
            w_hi = p.emit(CSRRW(0, CSR_MINSTRETH, 0))
            r_lo = p.emit(CSRRS(1, CSR_MINSTRET, 0))
            r_hi = p.emit(CSRRS(2, CSR_MINSTRETH, 0))
            mon, log = await run_prog(dut, mem, dbg, p.done())
            what = f"pad={pad} gap={gap}"
            # minstret after both writes: the low word restarts at 0 at csrw minstret and counts
            # the `gap` instructions and the high-word writer's neighbours afterwards.
            n_lo = log.between(w_lo, r_lo)
            got_lo = await dbg.read_gpr(1)
            assert n_lo - 1 - READ_LAG <= got_lo <= n_lo - 1, (
                f"{what}: minstret read {got_lo} after zeroing; {n_lo - 1} instruction(s) retired "
                f"between the zeroing write and the read (excluding the high-word writer)"
            )
            if gap == 0:
                assert got_lo == 0, f"{what}: back-to-back zeroing must read minstret == 0"
            check_read(log, w_hi, r_hi, 0, await dbg.read_gpr(2), what + " minstreth")


@cocotb.test()
async def test_low_half_wrap_carries_only_younger_retirements(dut):
    """Write minstret = 0xFFFFFFFF.  An older in-flight retirement would wrap the low word and
    carry into minstreth on top of the write; only retirements after the writer may carry."""
    mem, dbg = await _setup_test(dut)
    for pad in range(4):
        p = Prog()
        p.emit(*li(5, 0xFFFF_FFFF), *([NOP] * pad), ADDI(6, 0, 1), ADDI(6, 0, 2))
        w = p.emit(CSRRW(0, CSR_MINSTRET, 5))
        r_hi = p.emit(CSRRS(1, CSR_MINSTRETH, 0))  # directly after the writer: no carry yet
        p.emit(*[NOP] * 6)
        r_hi2 = p.emit(CSRRS(2, CSR_MINSTRETH, 0))
        r_lo2 = p.emit(CSRRS(3, CSR_MINSTRET, 0))
        mon, log = await run_prog(dut, mem, dbg, p.done())
        what = f"pad={pad}"
        assert await dbg.read_gpr(1) == 0, f"{what}: spurious carry into minstreth after the write"
        # Many instructions later the low word has wrapped exactly once.
        assert await dbg.read_gpr(2) == 1, f"{what}: minstreth should be 1 after the wrap"
        n = log.between(w, r_lo2)
        lo = await dbg.read_gpr(3)
        assert n - 1 - READ_LAG <= lo <= n - 1, (
            f"{what}: low word {lo:#x} after {n} retirements past the wrap"
        )
        assert r_hi < r_hi2 < r_lo2
        _assert_clean(mon, what)


@cocotb.test()
async def test_high_half_write_keeps_counting_the_low_half(dut):
    """A write to minstreth replaces the high word only; the low word keeps counting the older
    in-flight instructions (they are real retirements) but not the writer."""
    mem, dbg = await _setup_test(dut)
    for pad in range(4):
        for gap in range(3):
            p = Prog()
            p.emit(*li(5, 7), *([NOP] * pad), ADDI(6, 0, 1), ADDI(6, 0, 2))
            w0 = p.emit(CSRRW(0, CSR_MINSTRET, 0))  # low word := 0
            p.emit(*([ADDI(7, 0, k) for k in range(gap)]))
            w = p.emit(CSRRW(0, CSR_MINSTRETH, 5))  # high word := 7
            r_hi = p.emit(CSRRS(1, CSR_MINSTRETH, 0))
            r_lo = p.emit(CSRRS(2, CSR_MINSTRET, 0))
            mon, log = await run_prog(dut, mem, dbg, p.done())
            what = f"pad={pad} gap={gap}"
            check_read(log, w, r_hi, 7, await dbg.read_gpr(1), what + " minstreth")
            # Spec: low word = instructions retired after the low writer, minus the writers
            # themselves (the high writer's own retirement does not count either).
            n = log.between(w0, r_lo) - 1
            lo = await dbg.read_gpr(2)
            assert n - READ_LAG <= lo <= n, (
                f"{what}: minstret read {lo}, expected {n - READ_LAG}..{n}"
            )
            _assert_clean(mon, what)


@cocotb.test()
async def test_read_only_forms_are_not_writes(dut):
    """CSRRS/CSRRC with rs1 == x0 and CSRRSI/CSRRCI with uimm == 0 only read: they absorb no
    retirement, so the count keeps advancing through them."""
    mem, dbg = await _setup_test(dut)
    for csr in (CSR_MINSTRET, CSR_MINSTRETH):
        p = Prog()
        p.emit(*li(5, V), ADDI(6, 0, 1), ADDI(6, 0, 2))
        w = p.emit(CSRRW(0, CSR_MINSTRET, 5))
        for form in (
            CSRRS(0, csr, 0),
            CSRRC(0, csr, 0),
            CSRRSI(0, csr, 0),
            CSRRCI(0, csr, 0),
        ) * 2:
            p.emit(form)
        r = p.emit(CSRRS(1, CSR_MINSTRET, 0))
        mon, log = await run_prog(dut, mem, dbg, p.done())
        what = f"read-only forms on {csr:#x}"
        got = await dbg.read_gpr(1)
        check_read(log, w, r, V, got, what)
        assert got >= V + 8 - READ_LAG, f"{what}: read-only accesses must not stop the count"


@cocotb.test()
async def test_set_clear_forms_write_with_nonzero_source(dut):
    """CSRRS / CSRRC / CSRRSI / CSRRCI with a non-zero source DO write: older in-flight
    retirements and their own retirement must not land on the modified value either."""
    mem, dbg = await _setup_test(dut)
    cases = {
        "csrrs": lambda p: p.emit(CSRRS(0, CSR_MINSTRET, 5)),
        "csrrc": lambda p: p.emit(CSRRC(0, CSR_MINSTRET, 5)),
        "csrrsi": lambda p: p.emit(CSRRSI(0, CSR_MINSTRET, 0x10)),
        "csrrci": lambda p: p.emit(CSRRCI(0, CSR_MINSTRET, 0x01)),
    }
    for name, write in cases.items():
        for pad in range(4):
            p = Prog()
            # Establish a quiet, known value first (csrw + a few instructions so it settles),
            # then modify it with the form under test and read back immediately.
            p.emit(*li(5, V), *([NOP] * pad))
            p.emit(CSRRW(0, CSR_MINSTRET, 5))
            p.emit(*([NOP] * 8))
            p.emit(ADDI(6, 0, 1), ADDI(6, 0, 2))
            w = write(p)
            r = p.emit(CSRRS(1, CSR_MINSTRET, 0))
            mon, log = await run_prog(dut, mem, dbg, p.done())
            what = f"{name} pad={pad}"
            got = await dbg.read_gpr(1)
            # The modified value derives from the (lagging) value read at the writer's own EX, so
            # only the oracle pins it exactly; the spec-level facts are: the read directly after
            # the writer must see a value from the writer's own result, never that value + 1/+2.
            want = {  # value the CSR instruction computed, from the monitor's EX-time read
                "csrrs": lambda v: v | V,
                "csrrc": lambda v: v & ~V,
                "csrrsi": lambda v: v | 0x10,
                "csrrci": lambda v: v & ~0x01,
            }[name]
            before = [val for (_, addr, val) in mon.read_log if addr == CSR_MINSTRET][-2]
            assert got == want(before) & 0xFFFF_FFFF, (
                f"{what}: read {got:#x}, the instruction computed {want(before) & 0xFFFFFFFF:#x} "
                f"from {before:#x}; the result must not be incremented by retirements"
            )
            assert log.between(w, r) == 0
            _assert_clean(mon, what)


@cocotb.test()
async def test_wrong_path_write_is_ignored(dut):
    """CSR writes in the shadow of a taken branch / JAL never execute: no value lands, and no
    suppression state is left behind to eat later retirements."""
    mem, dbg = await _setup_test(dut)
    shapes = {
        "beq": BEQ(0, 0, 12),
        "jal": JAL(0, 12),
    }
    for name, jump in shapes.items():
        for pad in range(4):
            p = Prog()
            p.emit(*li(5, V), *([NOP] * pad), ADDI(6, 0, 1))
            p.emit(jump)
            p.emit(CSRRW(0, CSR_MINSTRET, 5), CSRRW(0, CSR_MINSTRETH, 5))  # wrong path
            r_lo = p.emit(CSRRS(1, CSR_MINSTRET, 0))
            r_hi = p.emit(CSRRS(2, CSR_MINSTRETH, 0))
            p.emit(*([NOP] * 6))
            r_lo2 = p.emit(CSRRS(3, CSR_MINSTRET, 0))
            mon, log = await run_prog(dut, mem, dbg, p.done())
            what = f"{name} pad={pad}"
            lo, hi, lo2 = [await dbg.read_gpr(r) for r in (1, 2, 3)]
            n_lo = log.pcs.index(r_lo)  # retired before the first read: the whole count so far
            assert hi == 0, f"{what}: wrong-path write to minstreth took effect ({hi:#x})"
            assert n_lo - READ_LAG <= lo <= n_lo, (
                f"{what}: minstret {lo:#x} but {n_lo} instructions retired (wrong-path write "
                f"of {V:#x} must not execute)"
            )
            assert r_hi > r_lo
            n_between = log.between(r_lo, r_lo2)
            # lo2 - lo = n_between + 1 (r_lo itself retires between the two reads), each read
            # lagging by 0 or 1: the difference is n_between .. n_between + 2.
            assert lo + n_between <= lo2 <= lo + n_between + 2, (
                f"{what}: later retirements were eaten after a flushed write: {lo2:#x}"
            )
            _assert_clean(mon, what)


@cocotb.test()
async def test_write_in_the_cycle_of_a_trap_entry(dut):
    """An older misaligned load traps (MEM stage) in the cycle a younger minstret write is in EX:
    the squashed write takes no effect and leaves no state; re-executed after the handler it wins
    over everything, including the handler's own retirements."""
    handler = 0x400
    mem, dbg = await _setup_test(dut)
    squashed = 0
    for pad in range(4):
        for gap in range(5):
            p = Prog()
            p.emit(*li(8, handler), CSRRW(0, CSR_MTVEC, 8))
            p.emit(*li(5, DATA_BASE), *li(7, V), *([NOP] * pad))
            p.emit(LW(6, 5, 1))  # misaligned -> load-address-misaligned trap from MEM
            p.emit(*([NOP] * gap))
            w = p.emit(CSRRW(0, CSR_MINSTRET, 7))
            r = p.emit(CSRRS(1, CSR_MINSTRET, 0))
            p.emit(EBREAK())
            p.emit(*([NOP] * (handler // 4 - len(p.words))))
            p.emit(CSRRS(9, CSR_MEPC, 0), ADDI(9, 9, 4), CSRRW(0, CSR_MEPC, 9), MRET())
            # No program-order oracle here: the trap makes the architectural stream dynamic (and a
            # writer younger than the trapping load may execute once before it is flushed and
            # again after the handler), so the checks are the spec-level bounds below.
            mon, log = await run_prog(dut, mem, dbg, p.words)
            what = f"pad={pad} gap={gap}"
            squashed += mon.cov.get("csr_in_trap_entry", 0)
            check_read(log, w, r, V, await dbg.read_gpr(1), what, model=False)
    dut._log.info(f"CSR instructions squashed by a trap entry in their EX cycle: {squashed}")
    assert squashed > 0, "no program put a minstret write in EX during a trap entry"


@cocotb.test()
async def test_mcycle_write_wins_and_counts_on(dut):
    """mcycle / mcycleh (no in-flight term: they count clocks, not retirements).  A write beats
    its own cycle's increment and the counter then runs from the written value: the read d
    instructions later sees V + (EX-to-EX distance - 1).  Expected to pass before and after f7z3."""
    mem, dbg = await _setup_test(dut)
    for csr in (CSR_MCYCLE, CSR_MCYCLEH):
        for d in range(4):
            p = Prog()
            p.emit(*li(5, V), ADDI(6, 0, 1), ADDI(6, 0, 2))
            p.emit(CSRRW(0, csr, 5))
            p.emit(*[ADDI(7, 0, k) for k in range(d)])
            p.emit(CSRRS(1, csr, 0))
            mon, _ = await run_prog(dut, mem, dbg, p.done())
            (c_w, _, _), (c_r, _, _) = [e for e in mon.read_log if e[1] == csr][:2]
            got = await dbg.read_gpr(1)
            if csr == CSR_MCYCLE:
                assert got == V + (c_r - c_w - 1), (
                    f"mcycle d={d}: read {got:#x}, want {V + c_r - c_w - 1:#x} "
                    f"({c_r - c_w} cycles between the EX cycles)"
                )
            else:  # the high word only moves on a low-word wrap, which cannot happen from V
                assert got == V, f"mcycleh d={d}: read {got:#x}, want {V:#x}"
            _assert_clean(mon, f"csr={csr:#x} d={d}")


@cocotb.test()
async def test_hpm_event_of_older_load_lands_after_write(dut):
    """mhpmcounter4 counts a physical event in the cycle it happens.  The D$ miss of a load older
    than the writer is raised from MEM after the write has executed, and counts on top of it (a
    time-ordered event, not a program-ordered retirement; spec has no program-order rule for hpm
    events).  The model sees the same strobes, so this documents the behaviour rather than
    judging it: see the open question in the f7z3 PR."""
    mem, dbg = await _setup_test(dut)
    p = Prog()
    p.emit(*li(5, V), *li(8, DATA_BASE + 0x300))
    p.emit(LW(6, 8, 0))  # D$ miss
    w = p.emit(CSRRW(0, CSR_MHPMCOUNTER4, 5))
    r = p.emit(CSRRS(1, CSR_MHPMCOUNTER4, 0))
    mon, log = await run_prog(dut, mem, dbg, p.done())
    _assert_clean(mon, "hpm4 older miss")
    got = await dbg.read_gpr(1)
    dut._log.info(f"hpm4 read after write of {V:#x} with an older D$ miss in flight: {got:#x}")
    assert V <= got <= V + 1
    assert log.between(w, r) == 0
