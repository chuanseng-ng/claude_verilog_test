"""Unit tests for tb/models/csr_model.py (bead a5ze).

The model is the expected-value source for tb/cocotb/cpu/test_csr_access.py, so it is pinned here
against the project spec (docs/design/PHASE2_ARCHITECTURE_SPEC.md section 4.2, PHASE5 M7 counters)
and the Zicsr write-suppression rule, independently of the RTL.
"""

import pytest

from tb.models.csr_model import (
    CSR_MCOUNTINHIBIT,
    CSR_MCYCLE,
    CSR_MCYCLEH,
    CSR_MEPC,
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
    CsrModel,
    IllegalCsrError,
)


def test_reset_state():
    """Reset state."""
    m = CsrModel()
    # MPP is hardwired to 2'b11, so mstatus reads 0x1800 out of reset.
    assert m.read(CSR_MSTATUS) == 0x1800
    assert m.read(CSR_MIE) == 0
    assert m.read(CSR_MTVEC) == 0
    assert m.read(CSR_MCOUNTINHIBIT) == 0


def test_mstatus_only_mie_mpie_writable():
    """Mstatus only mie mpie writable."""
    m = CsrModel()
    m.execute("RW", CSR_MSTATUS, 0xFFFFFFFF)
    assert m.read(CSR_MSTATUS) == 0x1800 | 0x88
    m.execute("RW", CSR_MSTATUS, 0)
    assert m.read(CSR_MSTATUS) == 0x1800


def test_set_and_clear_with_register_and_immediate():
    """Set and clear with register and immediate."""
    m = CsrModel()
    assert m.execute("RS", CSR_MIE, 0x80) == 0
    assert m.read(CSR_MIE) == 0x80
    assert m.execute("RS", CSR_MIE, 0x800) == 0x80
    assert m.read(CSR_MIE) == 0x880
    assert m.execute("RC", CSR_MIE, 0x80) == 0x880
    assert m.read(CSR_MIE) == 0x800
    # Immediate forms use the zero-extended 5-bit field only.
    m2 = CsrModel()
    m2.execute("RW", CSR_MSTATUS, 0x8, imm=True)
    assert m2.read(CSR_MSTATUS) & 0x8
    m2.execute("RC", CSR_MSTATUS, 0x8, imm=True)
    assert m2.read(CSR_MSTATUS) & 0x8 == 0


def test_rs_rc_with_zero_source_do_not_write():
    """Rs rc with zero source do not write."""
    m = CsrModel()
    m.execute("RW", CSR_MEPC, 0x1234)
    # rs1 == x0 (register form) or uimm == 0 (immediate form): read-only access.
    assert m.execute("RC", CSR_MEPC, 0, suppress_write=True) == 0x1234
    assert m.read(CSR_MEPC) == 0x1234
    assert m.execute("RC", CSR_MEPC, 0, imm=True) == 0x1234
    assert m.read(CSR_MEPC) == 0x1234
    # CSRRW always writes, even with a zero source.
    m.execute("RW", CSR_MEPC, 0, suppress_write=True)
    assert m.read(CSR_MEPC) == 0


def test_register_form_with_x0_source_vs_nonzero_register_value():
    """Register form with x0 source vs nonzero register value."""
    m = CsrModel()
    m.execute("RW", CSR_MEPC, 0xFF)
    # A register source that holds 0 but is not x0 still writes (RC of 0 is a no-op by value).
    m.execute("RS", CSR_MEPC, 0, suppress_write=False)
    assert m.read(CSR_MEPC) == 0xFF


def test_mtvec_mode_forced_to_direct():
    """Mtvec mode forced to direct."""
    m = CsrModel()
    m.execute("RW", CSR_MTVEC, 0x201)
    assert m.read(CSR_MTVEC) == 0x200
    m.execute("RS", CSR_MTVEC, 0x3)
    assert m.read(CSR_MTVEC) == 0x200


def test_mcountinhibit_bit1_reserved_and_upper_bits_zero():
    """Mcountinhibit bit1 reserved and upper bits zero."""
    m = CsrModel()
    m.execute("RW", CSR_MCOUNTINHIBIT, 0xFFFFFFFF)
    assert m.read(CSR_MCOUNTINHIBIT) == 0x3D


def test_read_only_csrs_ignore_writes():
    """Read only csrs ignore writes."""
    m = CsrModel()
    m.execute("RW", CSR_MIMPID, 0xFFFFFFFF)
    assert m.read(CSR_MIMPID) == 5
    for addr in (0xF11, 0xF12, 0xF14):
        m.execute("RW", addr, 0xFFFFFFFF)
        assert m.read(addr) == 0
    m.execute("RW", CSR_MIP, 0xFFFFFFFF)
    assert m.read(CSR_MIP) == 0


def test_mip_follows_irq_inputs():
    """Mip follows irq inputs."""
    m = CsrModel()
    assert m.read(CSR_MIP, timer_irq=1) == 0x80
    assert m.read(CSR_MIP, ext_irq=1) == 0x800
    assert m.read(CSR_MIP, timer_irq=1, ext_irq=1) == 0x880
    assert m.execute("RS", CSR_MIP, 0, suppress_write=True, timer_irq=1, ext_irq=1) == 0x880


def test_maintenance_csrs_read_zero_and_record_fire():
    """Maintenance csrs read zero and record fire."""
    m = CsrModel()
    assert m.execute("RW", 0x7C0, 1) == 0
    assert m.execute("RS", 0x7C1, 1) == 0
    assert m.maintenance == ["flush", "inval"]
    # Suppressed set/clear does not fire.
    m.execute("RS", 0x7C0, 0, suppress_write=True)
    m.execute("RC", 0x7C1, 0, imm=True)
    assert m.maintenance == ["flush", "inval"]


def test_unimplemented_csr_is_illegal():
    """Unimplemented csr is illegal."""
    m = CsrModel()
    with pytest.raises(IllegalCsrError):
        m.read(0xBFF)
    with pytest.raises(IllegalCsrError):
        m.execute("RW", 0x7C2, 0)


def test_64bit_counters_split_across_low_and_high_words():
    """64bit counters split across low and high words."""
    m = CsrModel()
    m.execute("RW", CSR_MCYCLEH, 0xDEADBEEF)
    assert m.read(CSR_MCYCLEH) == 0xDEADBEEF
    assert m.read(0xB00) == 0
    m.execute("RW", 0xB82, 0x1)
    assert m.read(0xB82) == 1
    assert m.read(0xB02) == 0


# ---------------------------------------------------------------------------
# tick(): cycle-accurate counter semantics (bead kiit / GH #260)
# ---------------------------------------------------------------------------
EVENTS = {
    CSR_MHPMCOUNTER3: "icache_miss",
    CSR_MHPMCOUNTER4: "dcache_miss",
    CSR_MHPMCOUNTER5: "branch_mispred",
}


def test_tick_counts_every_cycle_without_a_csr_access():
    """tick counts every cycle without a csr access."""
    m = CsrModel()
    for _ in range(5):
        m.tick()
    assert m.read(CSR_MCYCLE) == 5
    assert m.read(CSR_MINSTRET) == 0  # event counters need their event


def test_tick_events_count_only_when_strobed():
    """tick events count only when strobed."""
    m = CsrModel()
    m.tick(retire=True, icache_miss=True, dcache_miss=True, branch_mispred=True)
    m.tick(retire=True)
    assert m.read(CSR_MINSTRET) == 2
    assert [m.read(c) for c in EVENTS] == [1, 1, 1]


@pytest.mark.parametrize("csr", [CSR_MCYCLE, CSR_MINSTRET, *EVENTS])
def test_tick_csr_access_to_another_csr_drops_no_increment(csr):
    """A legal CSR instruction in EX (reading or writing a different CSR) freezes nothing."""
    m = CsrModel()
    ev = {"retire": True, "icache_miss": True, "dcache_miss": True, "branch_mispred": True}
    # A read-only form of the register under test must not stop it either.
    m.tick(**ev, access=("RS", csr, 0, False, True))
    m.tick(**ev, access=("RW", CSR_MEPC, 0x1234, False, False))  # write to a non-counter
    m.tick(**ev, access=("RS", CSR_MIMPID, 0, False, True))
    assert m.read(csr) == 3
    assert m.read(CSR_MCYCLE) == 3
    assert [m.read(c) for c in (CSR_MINSTRET, *EVENTS)] == [3, 3, 3, 3]


@pytest.mark.parametrize("csr", [CSR_MCYCLE, CSR_MINSTRET, *EVENTS])
def test_tick_write_beats_increment_of_its_own_register_only(csr):
    """Write wins for the addressed register; all the others still count."""
    m = CsrModel()
    ev = {"retire": True, "icache_miss": True, "dcache_miss": True, "branch_mispred": True}
    m.tick(**ev, access=("RW", csr, 100, False, False))
    assert m.read(csr) == 100
    for other in {CSR_MCYCLE, CSR_MINSTRET, *EVENTS} - {csr}:
        assert m.read(other) == 1


def test_tick_write_low_word_discards_the_carry_into_the_high_word():
    """tick write low word discards the carry into the high word."""
    m = CsrModel()
    m.execute("RW", CSR_MCYCLE, 0xFFFF_FFFF)
    m.execute("RW", CSR_MCYCLEH, 7)
    m.tick(access=("RW", CSR_MCYCLE, 5, False, False))
    assert (m.read(CSR_MCYCLEH), m.read(CSR_MCYCLE)) == (7, 5)  # no phantom carry
    m.execute("RW", CSR_MINSTRET, 0xFFFF_FFFF)
    m.tick(retire=True, access=("RW", CSR_MINSTRET, 9, False, False))
    assert (m.read(CSR_MINSTRETH), m.read(CSR_MINSTRET)) == (0, 9)


def test_tick_write_high_word_leaves_the_low_word_counting():
    """tick write high word leaves the low word counting (its wrap carry is lost)."""
    m = CsrModel()
    m.execute("RW", CSR_MCYCLE, 0xFFFF_FFFF)
    m.tick(access=("RW", CSR_MCYCLEH, 3, False, False))
    assert (m.read(CSR_MCYCLEH), m.read(CSR_MCYCLE)) == (3, 0)
    m.tick(retire=True, access=("RW", CSR_MINSTRETH, 4, False, False))
    assert m.read(CSR_MINSTRETH) == 4
    assert m.read(CSR_MINSTRET) == 1


def test_tick_low_word_wrap_carries_into_the_high_word():
    """tick low word wrap carries into the high word."""
    m = CsrModel()
    m.execute("RW", CSR_MCYCLE, 0xFFFF_FFFF)
    m.tick(access=("RS", CSR_MIMPID, 0, False, True))
    assert (m.read(CSR_MCYCLEH), m.read(CSR_MCYCLE)) == (1, 0)


def test_tick_mcountinhibit_applies_from_the_next_cycle():
    """The inhibit mask sampled at the start of the cycle gates the counters."""
    m = CsrModel()
    m.tick(access=("RW", CSR_MCOUNTINHIBIT, 0x3D, False, False))
    assert m.read(CSR_MCYCLE) == 1  # still counted: the old mask was 0
    m.tick(retire=True, icache_miss=True)
    assert m.read(CSR_MCYCLE) == 1 and m.read(CSR_MINSTRET) == 0
    m.tick(access=("RW", CSR_MCOUNTINHIBIT, 0, False, False))
    assert m.read(CSR_MCYCLE) == 1  # still frozen this cycle
    m.tick()
    assert m.read(CSR_MCYCLE) == 2


def test_tick_inhibit_bit_stops_only_its_counter():
    """tick inhibit bit stops only its counter."""
    m = CsrModel()
    m.execute("RW", CSR_MCOUNTINHIBIT, 1 << 4)  # hpmcounter4 only
    m.tick(retire=True, icache_miss=True, dcache_miss=True, branch_mispred=True)
    assert [m.read(c) for c in (CSR_MCYCLE, CSR_MINSTRET, *EVENTS)] == [1, 1, 1, 0, 1]


def test_tick_illegal_csr_access_raises():
    """tick illegal csr access raises."""
    with pytest.raises(IllegalCsrError):
        CsrModel().tick(access=("RW", 0xBFF, 0, False, False))


def test_tick_register_and_immediate_set_clear_forms():
    """tick register and immediate set clear forms."""
    m = CsrModel()
    m.tick(access=("RW", CSR_MHPMCOUNTER3, 0xF0, False, False))
    m.tick(access=("RC", CSR_MHPMCOUNTER3, 0x30, True, False))  # imm 0x30 -> uimm 0x10
    assert m.read(CSR_MHPMCOUNTER3) == 0xE0
    m.tick(icache_miss=True, access=("RS", CSR_MHPMCOUNTER3, 0, True, False))  # uimm 0: read only
    assert m.read(CSR_MHPMCOUNTER3) == 0xE1
    assert m.read(CSR_MINSTRETH) == 0


# ---------------------------------------------------------------------------
# minstret / minstreth write semantics (bead f7z3)
# ---------------------------------------------------------------------------
def _write(m, csr, value, seq, *, retire=False):
    """Execute ``CSRRW x0, csr, value`` as instruction ``seq`` in the cycle this call ticks."""
    m.tick(retire=retire, access=("RW", csr, value, False, False), access_seq=seq)


def _retire(m, n=1):
    for _ in range(n):
        m.tick(retire=True)


def test_minstret_writers_own_retirement_does_not_increment():
    """Spec: the instruction that writes minstret does not add 1 on top of the written value."""
    m = CsrModel()
    _write(m, CSR_MINSTRET, 100, seq=0)
    assert m.read(CSR_MINSTRET) == 100
    _retire(m)  # the writer retires
    assert m.read(CSR_MINSTRET) == 100
    _retire(m)  # the next instruction does count
    assert m.read(CSR_MINSTRET) == 101


@pytest.mark.parametrize("csr", [CSR_MINSTRET, CSR_MINSTRETH])
def test_minstret_write_absorbs_older_instructions_still_in_flight(csr):
    """Instructions 0 and 1 are in flight when instruction 2 writes: their strobes land after the
    write but belong before it, so they must not count on top of it."""
    m = CsrModel()
    _write(m, csr, 50, seq=2)
    _retire(m, 3)  # older 0, older 1, the writer itself
    if csr == CSR_MINSTRET:
        assert m.read(CSR_MINSTRET) == 50
    else:
        # high-word write: the older retirements still count in the low word (they are real
        # retirements) -- only the writer's own strobe is absorbed, and their carry is dropped.
        assert (m.read(CSR_MINSTRETH), m.read(CSR_MINSTRET)) == (50, 2)
    _retire(m)
    expect_low = 51 if csr == CSR_MINSTRET else 3
    assert m.read(CSR_MINSTRET) == expect_low


def test_minstret_write_same_cycle_strobe_is_an_older_instruction():
    """The strobe in the write cycle itself belongs to an older instruction: low write overrides
    it, high write lets it count in the low word."""
    m = CsrModel()
    _write(m, CSR_MINSTRET, 9, seq=1, retire=True)  # instr 0 retires in the cycle instr 1 writes
    assert m.read(CSR_MINSTRET) == 9
    _retire(m)  # the writer
    assert m.read(CSR_MINSTRET) == 9
    m = CsrModel()
    _write(m, CSR_MINSTRETH, 9, seq=1, retire=True)
    assert (m.read(CSR_MINSTRETH), m.read(CSR_MINSTRET)) == (9, 1)


def test_minstret_high_write_discards_the_carry_of_older_retirements():
    """An older retirement wrapping the low word would carry into the high word it is
    overwriting; the carry must not land on top of the written value."""
    m = CsrModel()
    m.execute("RW", CSR_MINSTRET, 0xFFFF_FFFF)
    _write(m, CSR_MINSTRETH, 7, seq=1)
    _retire(m, 2)  # older (wraps the low word, no carry) + writer
    assert (m.read(CSR_MINSTRETH), m.read(CSR_MINSTRET)) == (7, 0)
    _retire(m)  # a younger instruction now counts normally
    assert (m.read(CSR_MINSTRETH), m.read(CSR_MINSTRET)) == (7, 1)


def test_minstret_zeroing_both_halves_back_to_back_reads_zero():
    """csrw minstret, x0 ; csrw minstreth, x0 with both writers in flight together."""
    m = CsrModel()
    m.execute("RW", CSR_MINSTRET, 0x1234)
    m.execute("RW", CSR_MINSTRETH, 0x5678)
    _write(m, CSR_MINSTRET, 0, seq=1)  # instruction 0 is older and still in flight
    _write(m, CSR_MINSTRETH, 0, seq=2)  # instruction 1 (the first writer) is in flight too
    _retire(m, 3)
    assert (m.read(CSR_MINSTRETH), m.read(CSR_MINSTRET)) == (0, 0)


def test_minstret_older_absorbed_by_a_low_write_stays_absorbed_under_a_later_high_write():
    """Instruction 0 retires before the low writer (1), so its strobe must stay dropped when the
    high writer (3) executes while it is still in flight; instruction 2 (between the writers)
    counts in the low word."""
    m = CsrModel()
    _write(m, CSR_MINSTRET, 10, seq=1)
    _write(m, CSR_MINSTRETH, 20, seq=3)
    _retire(m, 4)  # 0 (dropped), 1 (writer), 2 (low only), 3 (writer)
    assert (m.read(CSR_MINSTRETH), m.read(CSR_MINSTRET)) == (20, 11)


def test_minstret_read_only_forms_do_not_absorb_anything():
    """CSRRS / CSRRC with a zero source do not write, so they absorb no retirement."""
    m = CsrModel()
    m.tick(access=("RS", CSR_MINSTRET, 0, False, True), access_seq=3)
    m.tick(access=("RC", CSR_MINSTRETH, 0, True, False), access_seq=4)
    _retire(m, 5)
    assert m.read(CSR_MINSTRET) == 5


def test_minstret_write_while_inhibited_still_absorbs_in_flight_strobes():
    """Strobes are consumed in program order even while mcountinhibit[2] stops counting, so the
    absorption must not leak past the inhibited window."""
    m = CsrModel()
    m.execute("RW", CSR_MCOUNTINHIBIT, 0x4)
    _write(m, CSR_MINSTRET, 40, seq=1)
    _retire(m, 2)  # older + writer, both inhibited anyway
    m.execute("RW", CSR_MCOUNTINHIBIT, 0)
    _retire(m)
    assert m.read(CSR_MINSTRET) == 41


def test_mcycle_write_has_no_in_flight_term():
    """mcycle counts clocks, not retirements: a write only beats its own cycle's increment, and
    the writer's retirement strobe changes nothing."""
    m = CsrModel()
    m.tick(access=("RW", CSR_MCYCLE, 500, False, False), access_seq=4)
    m.tick(retire=True)
    m.tick(retire=True)
    assert m.read(CSR_MCYCLE) == 502
