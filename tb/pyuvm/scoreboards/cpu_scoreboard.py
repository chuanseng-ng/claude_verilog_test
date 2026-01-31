"""CPU Scoreboard for pyuvm.

This module implements a UVM scoreboard that validates RTL instruction commits
against the Python reference model.

Features:
- UVM component architecture (inherits from uvm_component)
- Analysis export for receiving commits from monitor
- Reference model synchronization
- Detailed error reporting
- Match/mismatch statistics
"""

from pyuvm import uvm_component, uvm_tlm_analysis_fifo


class CPUScoreboard(uvm_component):
    """UVM scoreboard for CPU commit validation.

    This scoreboard receives commit transactions from the CommitMonitor,
    executes the reference model, and compares the results to validate
    RTL correctness.

    The scoreboard tracks:
    - PC values
    - Instruction words
    - Register writes (when RTL exposes)
    - Memory accesses (when RTL exposes)

    Attributes:
        ref_model: Python reference model instance
        commit_fifo: FIFO for receiving commits from monitor
        matches: Number of successful comparisons
        mismatches: Number of failed comparisons
        errors: List of error messages
    """

    def __init__(self, name, parent, ref_model):
        """Initialize CPU scoreboard.

        Args:
            name: Component name in UVM hierarchy
            parent: Parent UVM component
            ref_model: RV32IModel instance for reference comparison
        """
        super().__init__(name, parent)
        self.ref_model = ref_model
        self.commit_fifo = None  # Created in build_phase
        self.matches = 0
        self.mismatches = 0
        self.errors = []

    def build_phase(self):
        """UVM build phase - create FIFO for receiving commits."""
        super().build_phase()
        self.commit_fifo = uvm_tlm_analysis_fifo("commit_fifo", self)
        self.logger.info(f"Building {self.get_full_name()}")

    async def run_phase(self):
        """UVM run phase - process commits from monitor.

        This method runs continuously, pulling commit transactions from
        the FIFO and validating them against the reference model.
        """
        self.logger.info("Starting scoreboard validation")

        while True:
            # Get next commit from monitor (blocks until available)
            commit_txn = await self.commit_fifo.get()

            # Convert transaction to dict for compatibility
            rtl_commit = commit_txn.to_dict()

            # Validate against reference model
            self.check_commit(rtl_commit)

    def check_commit(self, rtl_commit):
        """Check an RTL commit against reference model.

        Args:
            rtl_commit: Dictionary with:
                - 'pc': PC of committed instruction
                - 'insn': Instruction word
                - 'rd': Destination register (or None)
                - 'rd_value': Value written to rd (or None)
                - 'mem_addr': Memory address accessed (or None)
                - 'mem_data': Memory data (or None)
                - 'mem_write': True if write, False if read

        Returns:
            True if validation passed, False otherwise
        """
        # Execute reference model
        ref_result = self.ref_model.step(rtl_commit["insn"])

        # Compare PC
        if ref_result["pc"] != rtl_commit["pc"]:
            error = f"PC mismatch: RTL=0x{rtl_commit['pc']:08x}, Model=0x{ref_result['pc']:08x}"
            self.logger.error(error)
            self.errors.append(error)
            self.mismatches += 1
            return False

        # Compare instruction
        if ref_result["insn"] != rtl_commit["insn"]:
            error = f"Instruction mismatch: RTL=0x{rtl_commit['insn']:08x}, Model=0x{ref_result['insn']:08x}"
            self.logger.error(error)
            self.errors.append(error)
            self.mismatches += 1
            return False

        # Compare destination register write (only if RTL provides this info)
        if rtl_commit.get("rd") is not None:
            if ref_result["rd"] is not None and ref_result["rd"] != 0:
                if ref_result["rd"] != rtl_commit.get("rd"):
                    error = f"Destination register mismatch: RTL={rtl_commit.get('rd')}, Model={ref_result['rd']}"
                    self.logger.error(error)
                    self.errors.append(error)
                    self.mismatches += 1
                    return False

                if ref_result["rd_value"] != rtl_commit.get("rd_value"):
                    error = (
                        f"Register value mismatch for x{ref_result['rd']}: "
                        f"RTL=0x{rtl_commit.get('rd_value', 0):08x}, "
                        f"Model=0x{ref_result['rd_value']:08x}"
                    )
                    self.logger.error(error)
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
                    self.logger.error(error)
                    self.errors.append(error)
                    self.mismatches += 1
                    return False

                if ref_result["mem_write"] != rtl_commit.get("mem_write"):
                    error = "Memory write flag mismatch"
                    self.logger.error(error)
                    self.errors.append(error)
                    self.mismatches += 1
                    return False

        # Validation passed
        self.matches += 1
        self.logger.debug(f"✓ Commit matched: PC=0x{rtl_commit['pc']:08x}")
        return True

    def report_phase(self):
        """UVM report phase - generate final scoreboard report."""
        total = self.matches + self.mismatches

        self.logger.info("=" * 60)
        self.logger.info("SCOREBOARD REPORT")
        self.logger.info("=" * 60)
        self.logger.info(f"Total commits checked: {total}")
        self.logger.info(f"Matches: {self.matches}")
        self.logger.info(f"Mismatches: {self.mismatches}")

        if self.mismatches > 0:
            self.logger.error(f"TEST FAILED: {self.mismatches} mismatches")
            self.logger.error("First 10 errors:")
            for i, error in enumerate(self.errors[:10]):
                self.logger.error(f"  {i + 1}. {error}")
        else:
            self.logger.info("TEST PASSED: All commits matched")

        self.logger.info("=" * 60)

        # Assert if mismatches found (fails the test)
        assert self.mismatches == 0, f"Scoreboard validation FAILED: {self.mismatches} errors"
