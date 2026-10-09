"""
reg_walk.py -- reusable cocotb register-walk helper (bead claude_verilog_test-7ovx, GH #216).

Why: the GH #216 coverage review found that most of the missing toggle coverage on the SoC's
register-bank peripherals (and on the soc_bus / axil / apb fabric) is upper data and address bits
that never see BOTH a 0->1 and a 1->0, because the directed tests write small values to a few
low offsets.  This helper walks every register of a peripheral with a fixed pattern set and
checks the read-back against the DOCUMENTED register map, so the same stimulus that toggles the
bits also proves behaviour: it is a checker first and a toggle generator second.

What it checks, per register (see `Reg`):
  * the value read straight after reset equals the documented idle value (live bits excepted);
  * every pattern write is read back as   (model & ~wmask) | (written & wmask)   -- so writable
    bits take the written value, and every NON-writable bit (RO status, reserved, WO/W1C/W1P
    registers that read 0) provably keeps its value no matter what is written;
  * byte-lane strobes: a write with pstrb = 1<<k changes only lane k, and only inside wmask;
  * no APB transaction returns PSLVERR (these banks never signal one; `expect_err` overrides);
  * unmapped words read 0 and writing them disturbs nothing (`walk_unmapped`), which is also the
    only test that catches a snoop decoding too few address bits;
  * after the walk every register is rewritten to its reset value, so the walk leaves the
    peripheral as it found it.

Pattern set (task spec): walking ones (32), 0xFFFFFFFF, 0x00000000, 0xA5A5A5A5, 0x5A5A5A5A, and
optionally walking zeros.  Patterns are ANDed with `Reg.drive` before they are written: a bit
outside `drive` is never driven to 1.  That is how a register with a side-effect bit stays safe
(START, a power-mode request, a watchdog enable) while the rest of the register is still walked.

What it does NOT do, by design (each is a per-register `skip` with a printed reason, never a
silent omission): registers whose WRITE has a side effect that the walk cannot undo or that
changes later registers -- FIFO pushes, key/data apertures, command pulses, watchdog feed.  The
owning suite tests those.

A mismatch is reported, not adapted to: the collected `Report.mismatches` are raised together
by `Report.assert_clean()` so one run lists every disagreement between RTL and the register map.

The helper only needs an object with `async write(addr, data, strb=0xF) -> ok` and
`async read(addr) -> (data, ok)` (bfm.apb4_master.APB4Master), so the unit suites use it directly;
`tb/cocotb/soc/soc_reg_fw.py` turns the same `Reg` tables into CPU firmware for the SoC level.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

M32 = 0xFFFF_FFFF

WALKING_ONES = tuple(1 << i for i in range(32))
WALKING_ZEROS = tuple(M32 ^ (1 << i) for i in range(32))
CONST_PATTERNS = (M32, 0x0000_0000, 0xA5A5_A5A5, 0x5A5A_5A5A, M32, 0x0000_0000)
# Short set: enough for a data bit to see both edges, used where the full set is too slow (SoC).
SHORT_PATTERNS = (0xA5A5_A5A5, 0x5A5A_5A5A, M32, 0x0000_0000)


def patterns(walking_zeros: bool = True) -> tuple:
    """Full pattern list: walking ones, constants, optionally walking zeros."""
    return WALKING_ONES + CONST_PATTERNS + (WALKING_ZEROS if walking_zeros else ())


@dataclass(frozen=True)
class Reg:
    """One register of a documented register map.

    offset  byte offset inside the peripheral's APB window.
    reset   documented value seen when the peripheral is idle straight after reset.  For a
            hardware-written register this is the idle value, not RESET_VAL of the bank.
    wmask   software-writable bits.  0 => read-only (or write-only registers that read 0).
    live    bits driven by hardware that may legitimately change: never compared.
    drive   bits the walk may drive to 1.  Excluding a bit keeps a side-effect bit (START,
            enable, power-mode request) from ever being set.  Bits of `wmask` outside `drive`
            therefore stay at 0 and must read back 0.
    skip    None, or the reason this register is NOT walked (printed in the report).
    recheck False for a register whose idle value legitimately moves once the walk has run
            (a free-running counter): it is still checked strictly in the first pass.
    kind    informational label: "rw", "ro", "wo0" (WO/snoop, reads 0), "w1c", "w1p", "rsvd".
    """

    name: str
    offset: int
    reset: int = 0
    wmask: int = 0
    live: int = 0
    drive: int = M32
    skip: Optional[str] = None
    recheck: bool = True
    kind: str = "auto"

    def __post_init__(self) -> None:
        assert self.offset % 4 == 0, f"{self.name}: offset must be word aligned"
        assert self.reset == self.reset & M32 and self.wmask == self.wmask & M32
        # The restore write is `reset & drive`; a reset-1 writable bit outside `drive` could not
        # be restored.  Fail at table-construction time rather than leave the DUT altered.
        assert (self.reset & self.wmask & ~self.drive & M32) == 0, (
            f"{self.name}: reset bit outside drive mask cannot be restored"
        )
        if self.kind == "auto":
            kind = "rw" if self.wmask else "ro"
            object.__setattr__(self, "kind", kind)

    @property
    def check(self) -> int:
        """Bits compared on read-back."""
        return ~self.live & M32


@dataclass
class Mismatch:
    reg: str
    offset: int
    what: str
    wrote: Optional[int]
    got: int
    expected: int

    def __str__(self) -> str:
        w = "-" if self.wrote is None else f"0x{self.wrote:08x}"
        return (f"{self.reg}@0x{self.offset:03x} {self.what}: wrote {w} "
                f"read 0x{self.got:08x} expected 0x{self.expected:08x}")


@dataclass
class Report:
    walked: list = field(default_factory=list)
    skipped: list = field(default_factory=list)       # (name, reason)
    mismatches: list = field(default_factory=list)
    writes: int = 0
    reads: int = 0

    def assert_clean(self) -> None:
        assert not self.mismatches, (
            f"{len(self.mismatches)} register-map mismatch(es) "
            f"({self.writes} writes, {self.reads} reads):\n  "
            + "\n  ".join(str(m) for m in self.mismatches[:40])
        )

    def summary(self) -> str:
        return (f"walked {len(self.walked)} regs ({self.writes} writes / {self.reads} reads), "
                f"skipped {len(self.skipped)}: "
                + "; ".join(f"{n} ({r})" for n, r in self.skipped))


async def _wr(m, rep: Report, addr: int, data: int, strb: int, expect_err: bool, who: str) -> None:
    ok = await m.write(addr, data & M32, strb)
    rep.writes += 1
    if ok == expect_err:  # ok means pslverr==0; expect_err True means we wanted SLVERR
        rep.mismatches.append(Mismatch(who, addr, "write pslverr", data & M32, int(not ok), int(expect_err)))


async def _rd(m, rep: Report, addr: int, expect_err: bool, who: str) -> int:
    data, ok = await m.read(addr)
    rep.reads += 1
    if ok == expect_err:
        rep.mismatches.append(Mismatch(who, addr, "read pslverr", None, int(not ok), int(expect_err)))
    return data & M32


def _expect(model: int, wmask: int, written: int, strb: int) -> int:
    """Register-bank write semantics: only wstrb lanes, only wmask bits."""
    lanes = 0
    for b in range(4):
        if (strb >> b) & 1:
            lanes |= 0xFF << (8 * b)
    m = wmask & lanes
    return (model & ~m & M32) | (written & m)


async def walk_registers(
    master,
    regs: Iterable[Reg],
    *,
    pats: Optional[Iterable[int]] = None,
    strobes: bool = True,
    expect_err: bool = False,
    settle=None,
    report: Optional[Report] = None,
) -> Report:
    """Walk `regs` through `master`; return the Report (call `.assert_clean()` to fail on any
    mismatch).  `settle` is an optional coroutine function awaited between a write and its
    read-back (for a peripheral whose bank is behind a slower clock).  Registers are processed
    in list order, so put a register that must be sampled before another one disturbs it first."""
    rep = report if report is not None else Report()
    plist = tuple(pats) if pats is not None else patterns()
    regs = list(regs)
    models: dict = {}

    async def rd(r: Reg) -> int:
        v = await _rd(master, rep, r.offset, expect_err, r.name)
        if settle is not None:
            await settle()
        return v

    # ---- pass 1: reset value, pattern walk, byte lanes, restore -----------------------------
    for r in regs:
        if r.skip is not None:
            rep.skipped.append((r.name, r.skip))
            continue
        rep.walked.append(r.name)
        first = await rd(r)
        if (first ^ r.reset) & r.check:
            rep.mismatches.append(Mismatch(r.name, r.offset, "reset/idle value", None, first, r.reset))
        model = r.reset & r.check
        for p in plist:
            w = p & r.drive
            await _wr(master, rep, r.offset, w, 0xF, expect_err, r.name)
            model = _expect(model, r.wmask, w, 0xF) & r.check
            got = await rd(r)
            if (got ^ model) & r.check:
                rep.mismatches.append(Mismatch(r.name, r.offset, "readback", w, got, model))
        if strobes:
            # Establish a known non-trivial base, then flip one lane at a time with its strobe.
            base = 0xA5A5_A5A5 & r.drive
            await _wr(master, rep, r.offset, base, 0xF, expect_err, r.name)
            model = _expect(model, r.wmask, base, 0xF) & r.check
            for lane in range(4):
                w = (~base & M32) & r.drive
                await _wr(master, rep, r.offset, w, 1 << lane, expect_err, r.name)
                model = _expect(model, r.wmask, w, 1 << lane) & r.check
                got = await rd(r)
                if (got ^ model) & r.check:
                    rep.mismatches.append(
                        Mismatch(r.name, r.offset, f"strobe lane {lane}", w, got, model))
            # pstrb = 0: nothing may change.
            await _wr(master, rep, r.offset, M32 & r.drive, 0x0, expect_err, r.name)
            got = await rd(r)
            if (got ^ model) & r.check:
                rep.mismatches.append(Mismatch(r.name, r.offset, "pstrb=0 write", M32, got, model))
        # Restore to the documented reset value.
        await _wr(master, rep, r.offset, r.reset & r.drive, 0xF, expect_err, r.name)
        model = _expect(model, r.wmask, r.reset & r.drive, 0xF) & r.check
        got = await rd(r)
        if (got ^ model) & r.check:
            rep.mismatches.append(Mismatch(r.name, r.offset, "restore", r.reset, got, model))
        models[r.offset] = r.reset & r.check

    # ---- pass 2: everything still holds its reset value after all the other writes ----------
    for r in regs:
        if r.skip is not None or not r.recheck:
            continue
        got = await rd(r)
        if (got ^ models[r.offset]) & r.check:
            rep.mismatches.append(Mismatch(r.name, r.offset, "cross-talk recheck", None, got,
                                           models[r.offset]))
    return rep


async def walk_unmapped(
    master,
    first_unmapped_word: int,
    *,
    addr_w: int = 12,
    regs: Iterable[Reg] = (),
    report: Optional[Report] = None,
    expect_err: bool = False,
) -> Report:
    """Probe the unmapped words of a 2**addr_w-byte window: they read 0, and writing all-ones /
    alternating patterns to them changes nothing (no aliasing onto a mapped register, no snoop
    firing on a partially-decoded address).  `regs` (the walked map) is re-read afterwards and
    compared with each register's documented idle value, which is what turns "dropped" from an
    assumption into a check.  Probes the power-of-two words (one address bit set at a time), the
    top word and two alternating-bit words."""
    rep = report if report is not None else Report()
    top = (1 << addr_w) - 4
    cand = set()
    for b in range(2, addr_w):
        cand.add(1 << b)
    cand.update({top, 0xAAA & ~3 & top, 0x554 & ~3 & top})
    probes = sorted(a for a in cand if a // 4 >= first_unmapped_word and a <= top)
    for i, a in enumerate(probes):
        v = 0xFFFF_FFFF if i % 2 == 0 else 0xA5A5_A5A5
        await _wr(master, rep, a, v, 0xF, expect_err, "unmapped")
        got = await _rd(master, rep, a, expect_err, "unmapped")
        if got != 0:
            rep.mismatches.append(Mismatch("unmapped", a, "read-as-zero", v, got, 0))
    for r in regs:
        if r.skip is not None or not r.recheck:
            continue
        got = await _rd(master, rep, r.offset, expect_err, r.name)
        if (got ^ r.reset) & r.check:
            rep.mismatches.append(Mismatch(r.name, r.offset, "after unmapped writes", None, got, r.reset))
    return rep


async def walk_bank(master, regs, first_unmapped_word: int, *, log=None, **kw) -> Report:
    """The standard unit-level entry point: walk `regs`, probe the unmapped window, log the
    summary and fail on any mismatch.  Returns the Report."""
    regs = list(regs)
    rep = await walk_registers(master, regs, **kw)
    await walk_unmapped(master, first_unmapped_word, regs=regs, report=rep,
                        expect_err=kw.get("expect_err", False))
    if log is not None:
        log.info(rep.summary())
    rep.assert_clean()
    return rep


async def check_w1c(
    master,
    stat_off: int,
    clr_off: int,
    pairs,
    *,
    stat_live: int = 0,
    name: str = "w1c",
    report: Optional[Report] = None,
) -> Report:
    """W1C semantics of a sticky status register, checked bit by bit.

    PRECONDITION (the caller's job, and the reason this is a separate helper from the walk): every
    status bit named in `pairs` is currently set and will not set itself again, and nothing else
    that matters is pending.  `pairs` is [(clr_bit, stat_bit), ...] because some blocks map IRQ_CLR
    bit k onto a different status bit (NPU: clr0->done STATUS[1], clr1->cfg_rejected STATUS[6]).

    Checks, in order: the clear register reads 0 before and after every write; clearing nothing
    (all zero) and clearing only bits that are not pending change nothing; then each pair is
    cleared ALONE and exactly that status bit drops -- every other pending bit survives; after the
    last, no pair bit remains.  Together this proves "write 1 clears the matching bit, write 0
    does not, unrelated bits are untouched", not merely that the register reads 0."""
    rep = report if report is not None else Report()
    clr_bits = 0
    stat_bits = 0
    for c, s in pairs:
        clr_bits |= 1 << c
        stat_bits |= 1 << s
    cmp = ~stat_live & M32

    async def st() -> int:
        return await _rd(master, rep, stat_off, False, name)

    async def clr_reads_zero(when: str) -> None:
        v = await _rd(master, rep, clr_off, False, name)
        if v != 0:
            rep.mismatches.append(Mismatch(name, clr_off, f"clear register reads non-zero {when}", None, v, 0))

    cur = await st()
    if (cur & stat_bits) != stat_bits:
        rep.mismatches.append(Mismatch(name, stat_off, "precondition: pending bits not all set",
                                       None, cur, cur | stat_bits))
        return rep
    await clr_reads_zero("before any write")
    # Writing zero, or ones to bits that are not clear-wired, must not clear anything.
    for w, what in ((0, "write 0"), (~clr_bits & M32, "write 1s outside the clear-wired bits")):
        await _wr(master, rep, clr_off, w, 0xF, False, name)
        got = await st()
        if (got ^ cur) & cmp:
            rep.mismatches.append(Mismatch(name, stat_off, f"{what} changed STATUS", w, got, cur))
    # Strobe-gated: a 1 written with its byte strobe low must not clear.
    for c, s in pairs:
        lane = c // 8
        off_strobes = 0xF & ~(1 << lane)
        await _wr(master, rep, clr_off, 1 << c, off_strobes, False, name)
        got = await st()
        if (got ^ cur) & cmp:
            rep.mismatches.append(Mismatch(name, stat_off, f"clr bit {c} with its byte strobe low cleared STATUS",
                                           1 << c, got, cur))
    for c, s in pairs:
        await _wr(master, rep, clr_off, 1 << c, 0xF, False, name)
        want = (cur & ~(1 << s)) & cmp
        got = (await st()) & cmp
        if got != want:
            rep.mismatches.append(Mismatch(name, stat_off, f"clr bit {c} -> STATUS bit {s}", 1 << c, got, want))
        cur = (cur & ~(1 << s))
        await clr_reads_zero(f"after clr bit {c}")
    return rep
