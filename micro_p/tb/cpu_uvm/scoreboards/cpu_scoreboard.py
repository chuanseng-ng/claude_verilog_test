"""CPU Scoreboard for pyuvm.

This module implements a UVM scoreboard that validates RTL instruction commits
against the Python reference model.

Features:
- UVM component architecture (inherits from uvm_component)
- Analysis export for receiving commits from monitor
- Reference model synchronization
- Detailed error reporting
- Match/mismatch statistics
- Performance tracking (IPC/CPI metrics)
- Instruction pair coverage tracking
"""

from pyuvm import uvm_component, uvm_tlm_analysis_fifo

from tb.common.coverage_tracker import InstructionPairCoverage
from tb.common.performance_report import PerformanceTracker


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
        performance_tracker: PerformanceTracker instance for IPC/CPI metrics
        coverage_tracker: InstructionPairCoverage instance for transition tracking
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
        self.performance_tracker = PerformanceTracker()
        self.coverage_tracker = InstructionPairCoverage()

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
        # Classify instruction for tracking
        insn_type = self._classify_instruction(rtl_commit["insn"])

        # Track performance (record before validation for accurate stats)
        self.performance_tracker.record_instruction(insn_type, cycles=1)

        # Track instruction pair coverage
        self.coverage_tracker.record_instruction(insn_type)

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
            error = (
                f"Instruction mismatch: RTL=0x{rtl_commit['insn']:08x}, "
                f"Model=0x{ref_result['insn']:08x}"
            )
            self.logger.error(error)
            self.errors.append(error)
            self.mismatches += 1
            return False

        # Compare destination register write (only if RTL provides this info)
        if rtl_commit.get("rd") is not None:
            if ref_result["rd"] is not None and ref_result["rd"] != 0:
                if ref_result["rd"] != rtl_commit.get("rd"):
                    error = (
                        f"Destination register mismatch: "
                        f"RTL={rtl_commit.get('rd')}, Model={ref_result['rd']}"
                    )
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

    def _classify_instruction(self, insn):
        """Classify instruction by mnemonic for performance tracking.

        Args:
            insn: 32-bit instruction word

        Returns:
            str: Instruction mnemonic (e.g., "ADD", "ADDI", "LW", "BEQ")

        Notes:
            - Uses same decoding logic as reference model
            - Returns "UNKNOWN" for illegal instructions
            - Used for per-instruction-type performance statistics
        """
        # Extract opcode and funct fields
        opcode = insn & 0x7F
        funct3 = (insn >> 12) & 0x7
        funct7 = (insn >> 25) & 0x7F

        # U-type instructions
        if opcode == 0b0110111:
            return "LUI"
        elif opcode == 0b0010111:
            return "AUIPC"

        # J-type instructions
        elif opcode == 0b1101111:
            return "JAL"

        # I-type instructions (JALR)
        elif opcode == 0b1100111:
            if funct3 == 0b000:
                return "JALR"

        # B-type instructions
        elif opcode == 0b1100011:
            if funct3 == 0b000:
                return "BEQ"
            elif funct3 == 0b001:
                return "BNE"
            elif funct3 == 0b100:
                return "BLT"
            elif funct3 == 0b101:
                return "BGE"
            elif funct3 == 0b110:
                return "BLTU"
            elif funct3 == 0b111:
                return "BGEU"

        # Load instructions
        elif opcode == 0b0000011:
            if funct3 == 0b000:
                return "LB"
            elif funct3 == 0b001:
                return "LH"
            elif funct3 == 0b010:
                return "LW"
            elif funct3 == 0b100:
                return "LBU"
            elif funct3 == 0b101:
                return "LHU"

        # Store instructions
        elif opcode == 0b0100011:
            if funct3 == 0b000:
                return "SB"
            elif funct3 == 0b001:
                return "SH"
            elif funct3 == 0b010:
                return "SW"

        # I-type ALU instructions
        elif opcode == 0b0010011:
            if funct3 == 0b000:
                return "ADDI"
            elif funct3 == 0b010:
                return "SLTI"
            elif funct3 == 0b011:
                return "SLTIU"
            elif funct3 == 0b100:
                return "XORI"
            elif funct3 == 0b110:
                return "ORI"
            elif funct3 == 0b111:
                return "ANDI"
            elif funct3 == 0b001:
                if funct7 == 0b0000000:
                    return "SLLI"
            elif funct3 == 0b101:
                if funct7 == 0b0000000:
                    return "SRLI"
                elif funct7 == 0b0100000:
                    return "SRAI"

        # R-type ALU instructions
        elif opcode == 0b0110011:
            if funct3 == 0b000:
                if funct7 == 0b0000000:
                    return "ADD"
                elif funct7 == 0b0100000:
                    return "SUB"
            elif funct3 == 0b001:
                return "SLL"
            elif funct3 == 0b010:
                return "SLT"
            elif funct3 == 0b011:
                return "SLTU"
            elif funct3 == 0b100:
                return "XOR"
            elif funct3 == 0b101:
                if funct7 == 0b0000000:
                    return "SRL"
                elif funct7 == 0b0100000:
                    return "SRA"
            elif funct3 == 0b110:
                return "OR"
            elif funct3 == 0b111:
                return "AND"

        # Unknown/illegal instruction
        return "UNKNOWN"

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

        # Generate performance report
        try:
            self.performance_tracker.generate_report("results/performance.csv")

            # Log performance summary
            ipc = self.performance_tracker.get_ipc()
            cpi = self.performance_tracker.get_cpi()
            perf_summary = self.performance_tracker.get_summary()

            self.logger.info("=" * 60)
            self.logger.info("PERFORMANCE SUMMARY")
            self.logger.info("=" * 60)
            self.logger.info(f"Total Instructions: {self.performance_tracker.total_instructions:,}")
            self.logger.info(f"Total Cycles: {self.performance_tracker.total_cycles:,}")
            self.logger.info(f"IPC: {ipc:.2f}")
            self.logger.info(f"CPI: {cpi:.2f}")
            self.logger.info(f"Unique Instruction Types: {perf_summary['instruction_count']}")

            if perf_summary["most_common"]:
                mc = perf_summary["most_common"]
                self.logger.info(
                    f"Most Common Instruction: {mc['type']} "
                    f"({mc['count']:,} times, {mc['percentage']:.1f}%)"
                )

            self.logger.info("Performance report saved to: results/performance.csv")
        except Exception as e:
            self.logger.warning(f"Failed to generate performance report: {e}")

        self.logger.info("=" * 60)

        # Generate coverage report
        self.logger.info("COVERAGE SUMMARY")
        self.logger.info("=" * 60)
        coverage_pct = self.coverage_tracker.get_coverage_percentage()
        self.logger.info(f"Total transitions: {self.coverage_tracker.total_transitions:,}")
        self.logger.info(f"Unique pairs: {len(self.coverage_tracker.pairs)}")
        self.logger.info(f"Pair coverage: {coverage_pct:.1f}%")

        # Save detailed coverage report to file
        try:
            self.coverage_tracker.generate_report("results/coverage_pairs.txt")
            self.logger.info("Detailed coverage report: results/coverage_pairs.txt")
        except Exception as e:
            self.logger.warning(f"Failed to generate coverage report: {e}")

        self.logger.info("=" * 60)
