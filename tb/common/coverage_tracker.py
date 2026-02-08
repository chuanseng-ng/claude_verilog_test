"""Instruction pair coverage tracker for RV32I verification.

This module tracks instruction-to-instruction transitions to ensure comprehensive
coverage of instruction interactions and dependencies.
"""

import os


class InstructionPairCoverage:
    """Track instruction-to-instruction transitions (instruction pairs).

    Monitors which instruction combinations have been tested to ensure
    comprehensive coverage of instruction interactions. This helps identify
    gaps in test coverage for sequences like:
    - Data hazards (e.g., ADD→ADD with register dependency)
    - Control flow patterns (e.g., LUI→JALR for function calls)
    - Memory sequences (e.g., SW→LW to same address)

    Attributes:
        pairs: Dictionary mapping (insn_type_A, insn_type_B) to occurrence count
        prev_insn_type: Previous instruction type for transition tracking
        total_transitions: Total number of transitions recorded
    """

    def __init__(self):
        """Initialize coverage tracker with empty statistics."""
        self.pairs = {}  # {(insn_type_A, insn_type_B): count}
        self.prev_insn_type = None
        self.total_transitions = 0

    def record_instruction(self, insn_type):
        """Record instruction and track transition from previous instruction.

        Args:
            insn_type: String identifier for instruction type (e.g., "ADD", "BEQ")
        """
        if self.prev_insn_type is not None:
            pair = (self.prev_insn_type, insn_type)
            self.pairs[pair] = self.pairs.get(pair, 0) + 1
            self.total_transitions += 1
        self.prev_insn_type = insn_type

    def get_coverage_percentage(self):
        """Calculate percentage of possible pairs covered.

        Dynamically computes the number of unique instruction types seen
        to avoid >100% coverage when additional instruction types are present.

        Phase 1 instruction count (baseline):
        - ALU: ADD, SUB, SLL, SLT, SLTU, XOR, SRL, SRA, OR, AND (10)
        - ALU-I: ADDI, SLTI, SLTIU, XORI, ORI, ANDI, SLLI, SRLI, SRAI (9)
        - Upper: LUI, AUIPC (2)
        Total: 21 instructions (441 possible pairs)

        Returns:
            Coverage percentage (0-100)
        """
        # Extract all unique instruction types seen
        all_types = set()
        for insn_a, insn_b in self.pairs.keys():
            all_types.add(insn_a)
            all_types.add(insn_b)

        # Compute maximum possible pairs based on actual types observed
        num_instruction_types = len(all_types) if all_types else 21  # Fallback to 21
        max_pairs = num_instruction_types * num_instruction_types
        covered_pairs = len(self.pairs)
        return 100.0 * covered_pairs / max_pairs if max_pairs > 0 else 0.0

    def get_uncovered_pairs(self, all_instruction_types):
        """Find pairs that have never been tested.

        Args:
            all_instruction_types: Set of all instruction type strings

        Returns:
            List of (insn_a, insn_b) tuples for pairs never seen
        """
        missing_pairs = []
        for insn_a in sorted(all_instruction_types):
            for insn_b in sorted(all_instruction_types):
                if (insn_a, insn_b) not in self.pairs:
                    missing_pairs.append((insn_a, insn_b))
        return missing_pairs

    def generate_report(self, output_file="results/coverage_pairs.txt"):
        """Generate detailed coverage report.

        Creates a text report with:
        - Overall coverage statistics
        - Top 20 most common instruction pairs
        - Coverage gap analysis (pairs never tested)

        Args:
            output_file: Path to output file (default: results/coverage_pairs.txt)
        """
        # Ensure output directory exists
        output_dir = os.path.dirname(output_file)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        with open(output_file, "w", encoding="utf-8") as f:
            f.write("Instruction Pair Coverage Report\n")
            f.write("=" * 60 + "\n")
            f.write(f"Total transitions: {self.total_transitions:,}\n")
            f.write(f"Unique pairs: {len(self.pairs)}\n")
            f.write(f"Coverage: {self.get_coverage_percentage():.1f}%\n\n")

            # Top 20 most common pairs
            f.write("Top 20 Most Common Pairs:\n")
            f.write("-" * 60 + "\n")
            sorted_pairs = sorted(self.pairs.items(), key=lambda x: x[1], reverse=True)
            for (insn_a, insn_b), count in sorted_pairs[:20]:
                percentage = 100.0 * count / self.total_transitions
                f.write(f"  {insn_a:10s} → {insn_b:10s}: {count:6d} ({percentage:5.2f}%)\n")

            # Coverage gaps (pairs never seen)
            f.write("\n" + "=" * 60 + "\n")
            f.write("Coverage Gaps Analysis:\n")
            f.write("-" * 60 + "\n")

            # Extract all instruction types seen
            all_types = set()
            for insn_a, insn_b in self.pairs.keys():
                all_types.add(insn_a)
                all_types.add(insn_b)

            missing_pairs = self.get_uncovered_pairs(all_types)

            f.write(f"Instruction types seen: {len(all_types)}\n")
            f.write(f"Missing pairs: {len(missing_pairs)}\n\n")

            if missing_pairs:
                f.write("Sample missing pairs (first 20):\n")
                for insn_a, insn_b in missing_pairs[:20]:
                    f.write(f"  {insn_a:10s} → {insn_b:10s}: NEVER TESTED\n")

                if len(missing_pairs) > 20:
                    f.write(f"  ... and {len(missing_pairs) - 20} more missing pairs\n")
            else:
                f.write("All possible pairs covered!\n")

            # Distribution analysis by first instruction
            f.write("\n" + "=" * 60 + "\n")
            f.write("Transition Distribution by First Instruction:\n")
            f.write("-" * 60 + "\n")

            first_insn_counts = {}
            for (insn_a, insn_b), count in self.pairs.items():
                first_insn_counts[insn_a] = first_insn_counts.get(insn_a, 0) + count

            for insn in sorted(first_insn_counts.keys()):
                count = first_insn_counts[insn]
                percentage = 100.0 * count / self.total_transitions
                f.write(f"  {insn:10s}: {count:6d} transitions ({percentage:5.2f}%)\n")

    def reset(self):
        """Reset coverage tracking to initial state.

        Useful for starting fresh coverage collection or between test phases.
        """
        self.pairs = {}
        self.prev_insn_type = None
        self.total_transitions = 0
