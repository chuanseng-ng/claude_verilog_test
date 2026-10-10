"""Unit tests for tb/models/csr_model.py (bead a5ze).

The model is the expected-value source for tb/cocotb/cpu/test_csr_access.py, so it is pinned here
against the project spec (docs/design/PHASE2_ARCHITECTURE_SPEC.md section 4.2, PHASE5 M7 counters)
and the Zicsr write-suppression rule, independently of the RTL.
"""

import pytest

from tb.models.csr_model import (
    CSR_MCOUNTINHIBIT,
    CSR_MCYCLEH,
    CSR_MEPC,
    CSR_MIE,
    CSR_MIMPID,
    CSR_MIP,
    CSR_MSTATUS,
    CSR_MTVEC,
    CsrModel,
    IllegalCsr,
)


def test_reset_state():
    m = CsrModel()
    # MPP is hardwired to 2'b11, so mstatus reads 0x1800 out of reset.
    assert m.read(CSR_MSTATUS) == 0x1800
    assert m.read(CSR_MIE) == 0
    assert m.read(CSR_MTVEC) == 0
    assert m.read(CSR_MCOUNTINHIBIT) == 0


def test_mstatus_only_mie_mpie_writable():
    m = CsrModel()
    m.execute("RW", CSR_MSTATUS, 0xFFFFFFFF)
    assert m.read(CSR_MSTATUS) == 0x1800 | 0x88
    m.execute("RW", CSR_MSTATUS, 0)
    assert m.read(CSR_MSTATUS) == 0x1800


def test_set_and_clear_with_register_and_immediate():
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
    m = CsrModel()
    m.execute("RW", CSR_MEPC, 0xFF)
    # A register source that holds 0 but is not x0 still writes (RC of 0 is a no-op by value).
    m.execute("RS", CSR_MEPC, 0, suppress_write=False)
    assert m.read(CSR_MEPC) == 0xFF


def test_mtvec_mode_forced_to_direct():
    m = CsrModel()
    m.execute("RW", CSR_MTVEC, 0x201)
    assert m.read(CSR_MTVEC) == 0x200
    m.execute("RS", CSR_MTVEC, 0x3)
    assert m.read(CSR_MTVEC) == 0x200


def test_mcountinhibit_bit1_reserved_and_upper_bits_zero():
    m = CsrModel()
    m.execute("RW", CSR_MCOUNTINHIBIT, 0xFFFFFFFF)
    assert m.read(CSR_MCOUNTINHIBIT) == 0x3D


def test_read_only_csrs_ignore_writes():
    m = CsrModel()
    m.execute("RW", CSR_MIMPID, 0xFFFFFFFF)
    assert m.read(CSR_MIMPID) == 5
    for addr in (0xF11, 0xF12, 0xF14):
        m.execute("RW", addr, 0xFFFFFFFF)
        assert m.read(addr) == 0
    m.execute("RW", CSR_MIP, 0xFFFFFFFF)
    assert m.read(CSR_MIP) == 0


def test_mip_follows_irq_inputs():
    m = CsrModel()
    assert m.read(CSR_MIP, timer_irq=1) == 0x80
    assert m.read(CSR_MIP, ext_irq=1) == 0x800
    assert m.read(CSR_MIP, timer_irq=1, ext_irq=1) == 0x880
    assert m.execute("RS", CSR_MIP, 0, suppress_write=True, timer_irq=1, ext_irq=1) == 0x880


def test_maintenance_csrs_read_zero_and_record_fire():
    m = CsrModel()
    assert m.execute("RW", 0x7C0, 1) == 0
    assert m.execute("RS", 0x7C1, 1) == 0
    assert m.maintenance == ["flush", "inval"]
    # Suppressed set/clear does not fire.
    m.execute("RS", 0x7C0, 0, suppress_write=True)
    m.execute("RC", 0x7C1, 0, imm=True)
    assert m.maintenance == ["flush", "inval"]


def test_unimplemented_csr_is_illegal():
    m = CsrModel()
    with pytest.raises(IllegalCsr):
        m.read(0xBFF)
    with pytest.raises(IllegalCsr):
        m.execute("RW", 0x7C2, 0)


def test_64bit_counters_split_across_low_and_high_words():
    m = CsrModel()
    m.execute("RW", CSR_MCYCLEH, 0xDEADBEEF)
    assert m.read(CSR_MCYCLEH) == 0xDEADBEEF
    assert m.read(0xB00) == 0
    m.execute("RW", 0xB82, 0x1)
    assert m.read(0xB82) == 1
    assert m.read(0xB02) == 0
