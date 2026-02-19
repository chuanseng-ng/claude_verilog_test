"""
Coverage tracking for Phase 1 RV32I CPU verification.

Three coverage metrics for Phase 1 exit criteria:
  1. Instruction coverage  — 37/37 RV32I base instructions executed
  2. FSM state coverage    — 8/8 CPU states visited
  3. RTL code coverage     — collected by Verilator (opt-in via COVERAGE=1)
"""

from pathlib import Path


# ---------------------------------------------------------------------------
# Instruction Coverage
# ---------------------------------------------------------------------------

# Maps (opcode, funct3, funct7_or_None) -> instruction name for all 37 RV32I.
# funct7_or_None is None when funct7 is not part of the primary discriminator.
_RV32I_INSTRUCTIONS = {
    # U-type / J-type  (no funct3/funct7)
    (0x37, None, None): "LUI",
    (0x17, None, None): "AUIPC",
    (0x6F, None, None): "JAL",
    # I-type — JALR
    (0x67, 0x0, None): "JALR",
    # B-type — branches
    (0x63, 0x0, None): "BEQ",
    (0x63, 0x1, None): "BNE",
    (0x63, 0x4, None): "BLT",
    (0x63, 0x5, None): "BGE",
    (0x63, 0x6, None): "BLTU",
    (0x63, 0x7, None): "BGEU",
    # I-type — loads
    (0x03, 0x0, None): "LB",
    (0x03, 0x1, None): "LH",
    (0x03, 0x2, None): "LW",
    (0x03, 0x4, None): "LBU",
    (0x03, 0x5, None): "LHU",
    # S-type — stores
    (0x23, 0x0, None): "SB",
    (0x23, 0x1, None): "SH",
    (0x23, 0x2, None): "SW",
    # I-type — immediate arithmetic  (funct7 not present, except shifts)
    (0x13, 0x0, None): "ADDI",
    (0x13, 0x2, None): "SLTI",
    (0x13, 0x3, None): "SLTIU",
    (0x13, 0x4, None): "XORI",
    (0x13, 0x6, None): "ORI",
    (0x13, 0x7, None): "ANDI",
    (0x13, 0x1, 0x00): "SLLI",
    (0x13, 0x5, 0x00): "SRLI",
    (0x13, 0x5, 0x20): "SRAI",
    # R-type — register arithmetic
    (0x33, 0x0, 0x00): "ADD",
    (0x33, 0x0, 0x20): "SUB",
    (0x33, 0x1, 0x00): "SLL",
    (0x33, 0x2, 0x00): "SLT",
    (0x33, 0x3, 0x00): "SLTU",
    (0x33, 0x4, 0x00): "XOR",
    (0x33, 0x5, 0x00): "SRL",
    (0x33, 0x5, 0x20): "SRA",
    (0x33, 0x6, 0x00): "OR",
    (0x33, 0x7, 0x00): "AND",
}

_TOTAL_INSTRUCTIONS = len(_RV32I_INSTRUCTIONS)  # 37


def _decode_key(insn_word: int):
    """Return the lookup key (opcode, funct3_or_None, funct7_or_None) for insn_word."""
    opcode = insn_word & 0x7F
    funct3 = (insn_word >> 12) & 0x7
    funct7 = (insn_word >> 25) & 0x7F

    # U-type / J-type: opcode only
    if opcode in (0x37, 0x17, 0x6F):
        return (opcode, None, None)

    # B-type, loads, stores, JALR, most I-type: opcode + funct3 only
    if opcode in (0x63, 0x03, 0x23, 0x67):
        return (opcode, funct3, None)

    # I-type arithmetic: shifts use funct7; others do not
    if opcode == 0x13:
        if funct3 in (0x1, 0x5):  # SLLI, SRLI, SRAI
            return (opcode, funct3, funct7)
        return (opcode, funct3, None)

    # R-type: opcode + funct3 + funct7
    if opcode == 0x33:
        return (opcode, funct3, funct7)

    return None  # Unknown / not in RV32I base


class InstructionCoverage:
    """Tracks which of the 37 RV32I base instructions have been exercised."""

    def __init__(self):
        self._seen: set = set()

    def record(self, insn_word: int) -> None:
        """Decode insn_word and mark the corresponding instruction as seen."""
        key = _decode_key(insn_word)
        if key in _RV32I_INSTRUCTIONS:
            self._seen.add(key)

    @property
    def covered(self) -> int:
        return len(self._seen)

    @property
    def is_complete(self) -> bool:
        return self.covered == _TOTAL_INSTRUCTIONS

    def report(self) -> str:
        lines = [f"Instruction Coverage: {self.covered}/{_TOTAL_INSTRUCTIONS}"]
        missing = [name for key, name in _RV32I_INSTRUCTIONS.items() if key not in self._seen]
        if missing:
            lines.append("  Missing instructions:")
            for name in sorted(missing):
                lines.append(f"    - {name}")
        else:
            lines.append("  All 37 instructions covered.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# State Coverage
# ---------------------------------------------------------------------------

STATE_NAMES = {
    0: "RESET",
    1: "FETCH",
    2: "DECODE",
    3: "EXECUTE",
    4: "MEM_WAIT",
    5: "WRITEBACK",
    6: "TRAP",
    7: "HALTED",
}
_TOTAL_STATES = len(STATE_NAMES)  # 8


class StateCoverage:
    """Tracks which of the 8 CPU FSM states have been visited."""

    def __init__(self):
        self._seen: set = set()

    def record(self, state_val: int) -> None:
        """Mark state_val as visited (silently ignore unknown values)."""
        if state_val in STATE_NAMES:
            self._seen.add(state_val)

    @property
    def covered(self) -> int:
        return len(self._seen)

    @property
    def is_complete(self) -> bool:
        return self.covered == _TOTAL_STATES

    def report(self) -> str:
        lines = [f"State Coverage: {self.covered}/{_TOTAL_STATES}"]
        missing = [name for val, name in STATE_NAMES.items() if val not in self._seen]
        if missing:
            lines.append("  Missing states:")
            for name in sorted(missing):
                lines.append(f"    - {name}")
        else:
            lines.append("  All 8 states covered.")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unified Coverage Report
# ---------------------------------------------------------------------------


class CoverageReport:
    """Aggregates instruction and state coverage; writes a summary file."""

    def __init__(self):
        self.instr_cov = InstructionCoverage()
        self.state_cov = StateCoverage()

    def generate(self, output_path: str = "reports/coverage_summary.txt") -> str:
        """Write unified coverage report to output_path and return it as a string.

        Creates the parent directory automatically if it doesn't exist.
        """
        instr_pct = self.instr_cov.covered / _TOTAL_INSTRUCTIONS * 100 if _TOTAL_INSTRUCTIONS else 0
        state_pct = self.state_cov.covered / _TOTAL_STATES * 100 if _TOTAL_STATES else 0

        instr_status = "PASS" if self.instr_cov.is_complete else "FAIL"
        state_status = "PASS" if self.state_cov.is_complete else "FAIL"

        lines = [
            "=" * 48,
            "COVERAGE SUMMARY REPORT",
            "=" * 48,
            f"Instruction Coverage: {self.instr_cov.covered}/{_TOTAL_INSTRUCTIONS}"
            f" ({instr_pct:.0f}%)  [{instr_status}]",
            f"State Coverage:       {self.state_cov.covered}/{_TOTAL_STATES}"
            f"   ({state_pct:.0f}%)  [{state_status}]",
            "=" * 48,
            "",
            self.instr_cov.report(),
            "",
            self.state_cov.report(),
        ]

        report_str = "\n".join(lines)

        # Write to file
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report_str + "\n")

        return report_str
