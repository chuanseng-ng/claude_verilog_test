"""Zicsr reference model for the rv32i_csr_file M-mode CSR set (bead a5ze).

Expected-value source for tb/cocotb/cpu/test_csr_access.py.  Written from the project specs, not
from the RTL: docs/design/PHASE2_ARCHITECTURE_SPEC.md section 4.2 (mstatus / mie / mtvec / mepc /
mcause / mip / ID registers), the Phase 5 M7 performance-counter map (mcountinhibit, mcycle[h],
minstret[h], mhpmcounter3-5) and the RISC-V Zicsr rule that CSRRS/CSRRC with a zero source do not
write.

The model holds no free-running state: the counters only change through writes, so a test must
freeze them with mcountinhibit before comparing a read against the model.
"""

from __future__ import annotations

CSR_MSTATUS = 0x300
CSR_MIE = 0x304
CSR_MTVEC = 0x305
CSR_MCOUNTINHIBIT = 0x320
CSR_MEPC = 0x341
CSR_MCAUSE = 0x342
CSR_MIP = 0x344
CSR_MCYCLE = 0xB00
CSR_MINSTRET = 0xB02
CSR_MHPMCOUNTER3 = 0xB03
CSR_MHPMCOUNTER4 = 0xB04
CSR_MHPMCOUNTER5 = 0xB05
CSR_MCYCLEH = 0xB80
CSR_MINSTRETH = 0xB82
CSR_MVENDORID = 0xF11
CSR_MARCHID = 0xF12
CSR_MIMPID = 0xF13
CSR_MHARTID = 0xF14
CSR_DCACHE_FLUSH = 0x7C0
CSR_DCACHE_INVAL = 0x7C1

MASK32 = 0xFFFF_FFFF
MSTATUS_MPP = 0x1800  # hardwired to M-mode
MSTATUS_WRITABLE = 0x88  # MIE[3], MPIE[7]
MIE_WRITABLE = 0x880  # MTIE[7], MEIE[11]
MCOUNTINHIBIT_WRITABLE = 0x3D  # bits 0, 2, 3, 4, 5; bit 1 reserved
MIMPID_PHASE5 = 5

# Plain 32-bit read/write registers (no WARL mask).
_FULL = (CSR_MEPC, CSR_MCAUSE, CSR_MCYCLE, CSR_MCYCLEH, CSR_MINSTRET, CSR_MINSTRETH)
_HPM = (CSR_MHPMCOUNTER3, CSR_MHPMCOUNTER4, CSR_MHPMCOUNTER5)
_READ_ONLY = {
    CSR_MVENDORID: 0,
    CSR_MARCHID: 0,
    CSR_MIMPID: MIMPID_PHASE5,
    CSR_MHARTID: 0,
}
_MAINTENANCE = {CSR_DCACHE_FLUSH: "flush", CSR_DCACHE_INVAL: "inval"}


class IllegalCsr(Exception):
    """Access to an unimplemented CSR address (the RTL raises an illegal-instruction trap)."""


class CsrModel:
    """Architectural state and access semantics of the M-mode CSR file."""

    def __init__(self) -> None:
        self.regs: dict[int, int] = {
            CSR_MSTATUS: 0,  # MIE / MPIE bits only; MPP is added on read
            CSR_MIE: 0,
            CSR_MTVEC: 0,
            CSR_MCOUNTINHIBIT: 0,
            **dict.fromkeys(_FULL, 0),
            **dict.fromkeys(_HPM, 0),
        }
        self.maintenance: list[str] = []

    def read(self, addr: int, *, timer_irq: int = 0, ext_irq: int = 0) -> int:
        if addr == CSR_MSTATUS:
            return MSTATUS_MPP | self.regs[CSR_MSTATUS]
        if addr == CSR_MIP:
            return (timer_irq & 1) << 7 | (ext_irq & 1) << 11
        if addr in _READ_ONLY:
            return _READ_ONLY[addr]
        if addr in _MAINTENANCE:
            return 0
        if addr in self.regs:
            return self.regs[addr]
        raise IllegalCsr(f"CSR {addr:#05x} is not implemented")

    def execute(
        self,
        kind: str,
        addr: int,
        operand: int,
        *,
        imm: bool = False,
        suppress_write: bool = False,
        timer_irq: int = 0,
        ext_irq: int = 0,
    ) -> int:
        """Run one CSR instruction; return the old value (what rd receives).

        ``kind`` is "RW", "RS" or "RC".  ``operand`` is the rs1 value, or the 5-bit uimm when
        ``imm``.  ``suppress_write`` is True for the register form with rs1 == x0 (an immediate
        of 0 is detected here).  CSRRW always writes.
        """
        old = self.read(addr, timer_irq=timer_irq, ext_irq=ext_irq)
        operand &= 0x1F if imm else MASK32
        if kind not in ("RW", "RS", "RC"):
            raise ValueError(f"unknown CSR op {kind!r}")
        writes = kind == "RW" or not (suppress_write or (imm and operand == 0))
        if not writes:
            return old
        new = {"RW": operand, "RS": old | operand, "RC": old & ~operand & MASK32}[kind]
        self._write(addr, new)
        return old

    def _write(self, addr: int, value: int) -> None:
        value &= MASK32
        if addr in _MAINTENANCE:
            self.maintenance.append(_MAINTENANCE[addr])
        elif addr == CSR_MSTATUS:
            self.regs[addr] = value & MSTATUS_WRITABLE
        elif addr == CSR_MIE:
            self.regs[addr] = value & MIE_WRITABLE
        elif addr == CSR_MTVEC:
            self.regs[addr] = value & ~0x3 & MASK32
        elif addr == CSR_MCOUNTINHIBIT:
            self.regs[addr] = value & MCOUNTINHIBIT_WRITABLE
        elif addr in _FULL or addr in _HPM:
            self.regs[addr] = value
        # mip and the ID registers are read-only: the write is silently ignored.
