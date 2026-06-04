"""
soc_model.py — Phase 5 (M9) SoC reference model.

Composes existing RV32IModel (CPU golden) and MemoryModel (sparse byte
memory) into a SoC-level golden model for the boot test scoreboard.

Architecture:
  ROM  : 0x0000_1000 – 0x0000_1FFF  (4 KB, read-only, loaded from hex file)
  SRAM : 0x0000_2000 – 0x0FFF_FFFF  (sparse write-back, initially empty)
  Other: DECERR (not modelled; CPU should not reach these in the boot test)

Reset PC override:
  The real CPU resets at 0x0000_0000, but after the RESET_PC RTL fix it
  resets at 0x0000_1000 (ROM_BASE).  This model always starts at ROM_BASE
  so the golden trace is correct for the fixed RTL.

Usage::

    model = SoCModel("path/to/boot.hex")
    model.boot()
    pcs  = model.committed_pcs    # list[int] — PCs in commit order
    state = model.final_state()   # dict with registers + SRAM snapshot

Public API:
    SoCModel(hex_path, rom_base, sram_base, sram_size)
    .boot(max_insns)     — run until EBREAK or max_insns
    .committed_pcs       — list of committed PCs (in order)
    .final_state()       — dict: regs, sram
    .sram_word(addr)     — read a 32-bit word from SRAM model
"""

import sys
from pathlib import Path
from typing import cast

# Allow import from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from tb.models.memory_model import MemoryModel
from tb.models.rv32i_model import RV32IModel

ROM_BASE = 0x0000_1000
ROM_LIMIT = 0x0000_1FFF  # inclusive
ROM_WORDS = 1024

SRAM_BASE = 0x0000_2000
SRAM_LIMIT = 0x0FFF_FFFF  # inclusive


class SoCModel:
    """Composed SoC reference model for the M9 boot test.

    Instantiates RV32IModel with a custom memory that has ROM and SRAM
    regions.  The CPU model's own MemoryModel is replaced with a
    SoCMemoryAdapter that routes accesses to the correct region.
    """

    def __init__(
        self,
        hex_path: str | None = None,
        rom_base: int = ROM_BASE,
        sram_base: int = SRAM_BASE,
        sram_size: int = SRAM_LIMIT - SRAM_BASE + 1,
    ):
        self.rom_base = rom_base
        self.sram_base = sram_base
        self.sram_limit = sram_base + sram_size - 1

        # Sparse ROM storage (word-indexed from rom_base)
        self._rom: dict[int, int] = {}  # byte_addr → word_value (4-byte aligned)

        # Sparse SRAM storage
        self._sram_mem = MemoryModel()  # byte-addressable sparse model

        # Load hex image into ROM
        if hex_path is not None:
            self._load_hex(hex_path, rom_base)

        # Build the RV32I CPU model with ROM_BASE as reset PC
        # Compose: replace the model's memory with our SoC memory adapter
        self.cpu = RV32IModel(reset_pc=rom_base)
        # ROM window tracks the caller-provided rom_base (same size as the
        # default ROM range), mirroring how sram_limit is derived above.
        rom_limit = rom_base + (ROM_LIMIT - ROM_BASE)
        # Duck-typed standin for MemoryModel; cast keeps the type checker happy.
        self.cpu.memory = cast(
            MemoryModel,
            _SoCMemoryAdapter(
                self._rom, self._sram_mem, rom_base, rom_limit, sram_base, self.sram_limit
            ),
        )

        # Committed PC stream (populated by boot())
        self.committed_pcs: list[int] = []

    # ── Hex loading ──────────────────────────────────────────────────────────

    def _load_hex(self, path: str, base: int) -> None:
        """Load a $readmemh-format hex file into the ROM region.

        One 32-bit word per line (no address tags); word[0] maps to base.
        """
        with open(path) as f:
            for idx, line in enumerate(f):
                line = line.strip()
                if not line or line.startswith("//") or line.startswith("#"):
                    continue
                word = int(line, 16)
                addr = base + idx * 4
                self._rom[addr] = word

    # ── Execution ─────────────────────────────────────────────────────────────

    def boot(self, max_insns: int = 2000) -> None:
        """Run the CPU golden model until EBREAK or max_insns retire.

        Populates self.committed_pcs with the PC of every *retired* instruction.

        EBREAK is a halt, not a retire: in the RTL it triggers a CPU halt and
        never asserts commit_valid, so the DUT produces no commit for it.  To
        keep the golden commit stream aligned with the DUT, EBREAK is therefore
        treated as a halt boundary and is NOT recorded in committed_pcs.
        """
        self.committed_pcs = []
        self.halted = False
        for _ in range(max_insns):
            try:
                result = self.cpu.step()
            except Exception as exc:
                # EBREAK / illegal-instruction causes the model to raise.
                # EBREAK halts without retiring → stop without recording a PC.
                name = type(exc).__name__
                if "Trap" in name or "EBREAK" in str(exc).upper() or "ebreak" in str(exc).lower():
                    self.halted = True
                    break
                # Other exception: re-raise
                raise
            # EBREAK halts without asserting commit_valid in the RTL — do not
            # count it as a committed instruction.
            if result.get("insn") == 0x00100073:  # EBREAK encoding
                self.halted = True
                break
            self.committed_pcs.append(result["pc"])

    def run(self, n_cycles: int = 2000) -> None:
        """Alias for boot() — run for up to n_cycles instructions."""
        self.boot(max_insns=n_cycles)

    # ── Observability ─────────────────────────────────────────────────────────

    def sram_word(self, byte_addr: int) -> int:
        """Read a 32-bit word from the SRAM model (little-endian)."""
        return self._sram_mem.read(byte_addr, 4)

    def final_state(self) -> dict:
        """Return a snapshot of CPU registers and written SRAM words.

        Returns:
            dict with keys:
              'regs'       : list[int] of 32 register values (x0–x31)
              'pc'         : current PC
              'sram_words' : dict[int, int] mapping byte_addr → word_value
                             for every word that has been written to SRAM
        """
        # Collect written SRAM words (byte_addr must be 4-byte aligned)
        sram_words: dict[int, int] = {}
        written_bytes = set(self._sram_mem.mem.keys())
        for b in sorted(written_bytes):
            aligned = b & ~0x3
            if aligned not in sram_words:
                try:
                    sram_words[aligned] = self._sram_mem.read(aligned, 4)
                except Exception:
                    pass

        return {
            "regs": list(self.cpu.regs),
            "pc": self.cpu.pc,
            "sram_words": sram_words,
        }


# ── Internal memory adapter ───────────────────────────────────────────────────


class _SoCMemoryAdapter:
    """Adapts the RV32IModel memory interface to route ROM vs SRAM accesses.

    Conforms to the same duck-typed interface as MemoryModel:
      .read(addr, size) -> int
      .write(addr, value, size)
      .mem             (dict: exposed for raw inspection; maps to SRAM model)
    """

    def __init__(
        self,
        rom: dict[int, int],
        sram: MemoryModel,
        rom_base: int,
        rom_limit: int,
        sram_base: int,
        sram_limit: int,
    ):
        self._rom = rom
        self._sram = sram
        self._rom_base = rom_base
        self._rom_limit = rom_limit
        self._sram_base = sram_base
        self._sram_limit = sram_limit

        # Expose SRAM model's internal dict so callers can inspect writes
        self.mem = sram.mem

    def read(self, addr: int, size: int = 4) -> int:
        if self._rom_base <= addr <= self._rom_limit:
            return self._read_rom(addr, size)
        if self._sram_base <= addr <= self._sram_limit:
            return self._sram.read(addr, size)
        raise ValueError(f"SoCMemoryAdapter: unmapped read at 0x{addr:08x} (size={size})")

    def write(self, addr: int, value: int, size: int = 4) -> None:
        if self._rom_base <= addr <= self._rom_limit:
            raise PermissionError(f"SoCMemoryAdapter: write to ROM at 0x{addr:08x}")
        if self._sram_base <= addr <= self._sram_limit:
            self._sram.write(addr, value, size)
            return
        raise ValueError(f"SoCMemoryAdapter: unmapped write at 0x{addr:08x} (size={size})")

    def _read_rom(self, addr: int, size: int) -> int:
        """Read from the ROM dict (word-granular storage, byte read supported)."""
        if size == 4:
            word_addr = addr & ~0x3
            return self._rom.get(word_addr, 0)
        # Sub-word reads: extract bytes from word
        word_addr = addr & ~0x3
        word = self._rom.get(word_addr, 0)
        byte_off = addr & 0x3
        raw = word >> (byte_off * 8)
        if size == 1:
            return raw & 0xFF
        if size == 2:
            return raw & 0xFFFF
        return raw & 0xFFFFFFFF
