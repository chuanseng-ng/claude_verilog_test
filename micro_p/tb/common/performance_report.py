"""Performance tracking and reporting for CPU benchmarking.

This module provides utilities to track CPU performance metrics including:
- IPC (Instructions Per Cycle)
- CPI (Cycles Per Instruction)
- Per-instruction-type statistics
- CSV report generation

Usage:
    tracker = PerformanceTracker()
    tracker.record_instruction("ADD", cycles=1)
    tracker.record_instruction("ADDI", cycles=1)
    tracker.generate_report("results/performance.csv")

    print(f"IPC: {tracker.get_ipc():.2f}")
    print(f"CPI: {tracker.get_cpi():.2f}")
"""

import csv
import os
from collections import defaultdict


class PerformanceTracker:
    """Track CPU performance metrics (IPC/CPI) and instruction execution statistics.

    This class maintains counters for total instructions executed, total cycles consumed,
    and per-instruction-type statistics. It can generate CSV reports suitable for
    analysis and visualization.

    Attributes:
        total_instructions: Total number of instructions executed
        total_cycles: Total number of cycles consumed
        instruction_stats: Dictionary mapping instruction type to {"count": N, "cycles": M}
    """

    def __init__(self):
        """Initialize performance tracker with zero counters."""
        self.total_instructions = 0
        self.total_cycles = 0
        # Dictionary: {insn_type: {"count": N, "cycles": M}}
        self.instruction_stats = defaultdict(lambda: {"count": 0, "cycles": 0})

    def record_instruction(self, insn_type, cycles=1):
        """Record instruction execution with cycle count.

        Args:
            insn_type: Instruction mnemonic (e.g., "ADD", "ADDI", "LW", "BEQ")
            cycles: Number of cycles consumed (default: 1 for single-cycle CPU)

        Notes:
            - For Phase 1 single-cycle CPU, cycles should always be 1
            - Future pipelined designs may have variable cycles per instruction
        """
        # Update totals
        self.total_instructions += 1
        self.total_cycles += cycles

        # Update per-instruction-type stats
        self.instruction_stats[insn_type]["count"] += 1
        self.instruction_stats[insn_type]["cycles"] += cycles

    def get_ipc(self):
        """Calculate instructions per cycle.

        Returns:
            float: IPC (instructions/cycle). Returns 0 if no cycles recorded.

        Notes:
            - IPC = total_instructions / total_cycles
            - For single-cycle CPU with no stalls, IPC should approach 1.0
            - Lower IPC indicates pipeline stalls or multi-cycle operations
        """
        return self.total_instructions / self.total_cycles if self.total_cycles > 0 else 0.0

    def get_cpi(self):
        """Calculate cycles per instruction.

        Returns:
            float: CPI (cycles/instruction). Returns 0 if no instructions recorded.

        Notes:
            - CPI = total_cycles / total_instructions
            - CPI is the reciprocal of IPC (CPI = 1 / IPC)
            - For single-cycle CPU with no stalls, CPI should be 1.0
            - Higher CPI indicates more cycles needed per instruction
        """
        return self.total_cycles / self.total_instructions if self.total_instructions > 0 else 0.0

    def generate_report(self, output_file="results/performance.csv"):
        """Generate CSV performance report.

        Args:
            output_file: Path to CSV output file (default: results/performance.csv)

        Creates a CSV file with columns:
            - instruction_type: Instruction mnemonic
            - count: Number of times executed
            - percentage: Percentage of total instructions
            - avg_cpi: Average CPI for this instruction type

        The report includes a summary row with totals and overall IPC/CPI.
        """
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        # Sort instruction types alphabetically for consistent output
        sorted_types = sorted(self.instruction_stats.keys())

        # Write CSV file
        with open(output_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)

            # Header
            writer.writerow(["instruction_type", "count", "percentage", "avg_cpi"])

            # Per-instruction-type rows
            for insn_type in sorted_types:
                stats = self.instruction_stats[insn_type]
                count = stats["count"]
                cycles = stats["cycles"]

                # Calculate metrics
                percentage = (
                    (count / self.total_instructions * 100) if self.total_instructions > 0 else 0.0
                )
                avg_cpi = (cycles / count) if count > 0 else 0.0

                # Write row
                writer.writerow([insn_type, count, f"{percentage:.2f}", f"{avg_cpi:.2f}"])

            # Summary row
            overall_cpi = self.get_cpi()
            writer.writerow(["TOTAL", self.total_instructions, "100.00", f"{overall_cpi:.2f}"])

    def get_summary(self):
        """Get performance summary as dictionary.

        Returns:
            dict: Performance summary with keys:
                - total_instructions: Total instructions executed
                - total_cycles: Total cycles consumed
                - ipc: Instructions per cycle
                - cpi: Cycles per instruction
                - instruction_count: Number of unique instruction types
                - most_common: Most frequently executed instruction type
        """
        summary = {
            "total_instructions": self.total_instructions,
            "total_cycles": self.total_cycles,
            "ipc": self.get_ipc(),
            "cpi": self.get_cpi(),
            "instruction_count": len(self.instruction_stats),
            "most_common": None,
        }

        # Find most common instruction
        if self.instruction_stats:
            most_common_type = max(
                self.instruction_stats.keys(), key=lambda k: self.instruction_stats[k]["count"]
            )
            summary["most_common"] = {
                "type": most_common_type,
                "count": self.instruction_stats[most_common_type]["count"],
                "percentage": (
                    self.instruction_stats[most_common_type]["count"]
                    / self.total_instructions
                    * 100
                )
                if self.total_instructions > 0
                else 0.0,
            }

        return summary
