"""Zicsr reference model for the rv32i_csr_file M-mode CSR set (bead a5ze).

Expected-value source for tb/cocotb/cpu/test_csr_access.py.  Written from the project specs, not
from the RTL: docs/design/PHASE2_ARCHITECTURE_SPEC.md section 4.2 (mstatus / mie / mtvec / mepc /
mcause / mip / ID registers), the Phase 5 M7 performance-counter map (mcountinhibit, mcycle[h],
minstret[h], mhpmcounter3-5) and the RISC-V Zicsr rule that CSRRS/CSRRC with a zero source do not
write.

execute() is the untimed instruction view: the counters only change through writes, so a test
that compares a read against it must freeze them with mcountinhibit first.  tick() is the
cycle-accurate view (bead kiit): it also advances the free-running counters, so a monitor can
step it once per clock and compare the whole counter state with the DUT every cycle.
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
MASK64 = (1 << 64) - 1


class IllegalCsrError(Exception):
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
        """Architectural value of ``addr``; raises IllegalCsrError if unimplemented."""
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
        raise IllegalCsrError(f"CSR {addr:#05x} is not implemented")

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
        if not self._writes(kind, operand, imm, suppress_write):
            return old
        self._write(addr, self._new_value(kind, old, operand))
        return old

    @staticmethod
    def _writes(kind: str, operand: int, imm: bool, suppress_write: bool) -> bool:
        """Zicsr: CSRRW always writes; CSRRS/CSRRC skip the write for rs1 == x0 / uimm == 0."""
        return kind == "RW" or not (suppress_write or (imm and operand == 0))

    @staticmethod
    def _new_value(kind: str, old: int, operand: int) -> int:
        return {"RW": operand, "RS": old | operand, "RC": old & ~operand & MASK32}[kind]

    def tick(
        self,
        *,
        retire: bool = False,
        icache_miss: bool = False,
        dcache_miss: bool = False,
        branch_mispred: bool = False,
        access: tuple[str, int, int, bool, bool] | None = None,
    ) -> None:
        """Advance the counters by one clock (bead kiit).

        ``access`` is the CSR instruction in EX this cycle as ``(kind, addr, operand, imm,
        suppress_write)`` (same meaning as execute()); None when there is none, or when it is
        squashed by a trap entry / MRET in the same cycle.  Semantics, from the RISC-V privileged
        spec and the project's "write wins over increment" rule:

        * every counter whose mcountinhibit bit was clear at the START of the cycle counts, whatever
          instruction is in EX -- mcountinhibit itself takes effect from the next cycle;
        * a CSR write replaces the addressed 32-bit register only; every other counter still counts;
        * the write beats the same-cycle increment of its own register, and a write to the low word
          of mcycle / minstret also discards the carry that increment would have produced, while a
          write to the high word leaves the low word counting (its wrap carry is lost);
        * CSRRS/CSRRC with a zero source do not write, so the counter they read keeps counting.
        """
        inh = self.regs[CSR_MCOUNTINHIBIT]
        nxt: dict[int, int] = {}
        for bit, pair, fire in (
            (0, (CSR_MCYCLE, CSR_MCYCLEH), True),
            (2, (CSR_MINSTRET, CSR_MINSTRETH), retire),
        ):
            if fire and not inh >> bit & 1:
                total = ((self.regs[pair[1]] << 32 | self.regs[pair[0]]) + 1) & MASK64
                nxt[pair[0]], nxt[pair[1]] = total & MASK32, total >> 32
        for bit, csr, fire in (
            (3, CSR_MHPMCOUNTER3, icache_miss),
            (4, CSR_MHPMCOUNTER4, dcache_miss),
            (5, CSR_MHPMCOUNTER5, branch_mispred),
        ):
            if fire and not inh >> bit & 1:
                nxt[csr] = (self.regs[csr] + 1) & MASK32
        if access is not None:
            kind, addr, operand, imm, suppress = access
            old = self.read(addr)  # raises IllegalCsrError: the RTL squashes the write
            operand &= 0x1F if imm else MASK32
            if self._writes(kind, operand, imm, suppress):
                new = self._new_value(kind, old, operand)
                if addr in _FULL or addr in _HPM:
                    nxt[addr] = new & MASK32
                    if addr in (CSR_MCYCLE, CSR_MINSTRET):
                        nxt.pop(addr + 0x80, None)  # carry into the high word is discarded
                else:
                    self._write(addr, new)
        self.regs.update(nxt)

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
