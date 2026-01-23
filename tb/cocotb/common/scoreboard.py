"""
Scoreboard for comparing RTL against reference model.

Tracks committed instructions and compares RTL behavior against
the Python reference model.
"""

import cocotb
from cocotb.triggers import RisingEdge
from typing import Optional
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from tb.models.rv32i_model import RV32IModel


class CPUScoreboard:
    """
    Scoreboard for CPU verification.

    Compares RTL commits against Python reference model execution.
    """

    def __init__(self, ref_model: RV32IModel, log=None):
        """
        Initialize scoreboard.

        Args:
            ref_model: Python reference model instance
            log: Logger instance (optional, use dut._log)
        """
        self.ref_model = ref_model
        self.log = log if log else cocotb.log

        self.matches = 0
        self.mismatches = 0
        self.errors = []

    def check_commit(self, rtl_commit: dict):
        """
        Check an RTL commit against reference model.

        Args:
            rtl_commit: Dictionary with:
                - 'pc': PC of committed instruction
                - 'insn': Instruction word
                - 'rd': Destination register (or None)
                - 'rd_value': Value written to rd (or None)
                - 'mem_addr': Memory address accessed (or None)
                - 'mem_data': Memory data (or None)
                - 'mem_write': True if write, False if read
        """
        # Execute reference model
        ref_result = self.ref_model.step(rtl_commit["insn"])

        # Compare PC
        if ref_result["pc"] != rtl_commit["pc"]:
            error = f"PC mismatch: RTL=0x{rtl_commit['pc']:08x}, Model=0x{ref_result['pc']:08x}"
            self.log.error(error)
            self.errors.append(error)
            self.mismatches += 1
            return False

        # Compare instruction
        if ref_result["insn"] != rtl_commit["insn"]:
            error = f"Instruction mismatch: RTL=0x{rtl_commit['insn']:08x}, Model=0x{ref_result['insn']:08x}"
            self.log.error(error)
            self.errors.append(error)
            self.mismatches += 1
            return False

        # Compare destination register write (only if RTL provides this info)
        if rtl_commit.get("rd") is not None:
            if ref_result["rd"] is not None and ref_result["rd"] != 0:
                if ref_result["rd"] != rtl_commit.get("rd"):
                    error = f"Destination register mismatch: RTL={rtl_commit.get('rd')}, Model={ref_result['rd']}"
                    self.log.error(error)
                    self.errors.append(error)
                    self.mismatches += 1
                    return False

                if ref_result["rd_value"] != rtl_commit.get("rd_value"):
                    error = (
                        f"Register value mismatch for x{ref_result['rd']}: "
                        f"RTL=0x{rtl_commit.get('rd_value', 0):08x}, "
                        f"Model=0x{ref_result['rd_value']:08x}"
                    )
                    self.log.error(error)
                    self.errors.append(error)
                    self.mismatches += 1
                    return False

        # Compare memory access (only if RTL provides this info)
        if rtl_commit.get("mem_addr") is not None:
            if ref_result["mem_addr"] is not None:
                if ref_result["mem_addr"] != rtl_commit.get("mem_addr"):
                    error = (
                        f"Memory address mismatch: "
                        f"RTL=0x{rtl_commit.get('mem_addr', 0):08x}, "
                        f"Model=0x{ref_result['mem_addr']:08x}"
                    )
                    self.log.error(error)
                    self.errors.append(error)
                    self.mismatches += 1
                    return False

                if ref_result["mem_write"] != rtl_commit.get("mem_write"):
                    error = f"Memory write flag mismatch"
                    self.log.error(error)
                    self.errors.append(error)
                    self.mismatches += 1
                    return False

        self.matches += 1
        self.log.debug(f"✓ Commit matched: PC=0x{rtl_commit['pc']:08x}")
        return True

    def report(self):
        """Generate final scoreboard report."""
        total = self.matches + self.mismatches

        self.log.info("=" * 60)
        self.log.info("SCOREBOARD REPORT")
        self.log.info("=" * 60)
        self.log.info(f"Total commits checked: {total}")
        self.log.info(f"Matches: {self.matches}")
        self.log.info(f"Mismatches: {self.mismatches}")

        if self.mismatches > 0:
            self.log.error(f"TEST FAILED: {self.mismatches} mismatches")
            self.log.error("First 10 errors:")
            for i, error in enumerate(self.errors[:10]):
                self.log.error(f"  {i + 1}. {error}")
        else:
            self.log.info("TEST PASSED: All commits matched")

        self.log.info("=" * 60)

        return self.mismatches == 0
