"""Commit Monitor for pyuvm.

This module implements a UVM monitor that observes instruction commits
from the RV32I CPU and forwards them to the scoreboard for validation.

Features:
- Passive monitoring of commit interface signals
- Transaction object creation
- Analysis port for scoreboard communication
- Configurable logging verbosity
"""

from cocotb.triggers import RisingEdge, ReadOnly
from pyuvm import uvm_monitor, uvm_analysis_port


class CommitTransaction:
    """Transaction object for instruction commits.

    Attributes:
        pc: Program counter value (32-bit)
        insn: Instruction word (32-bit)
        rd: Destination register number (future - when RTL exposes)
        rd_value: Destination register value (future - when RTL exposes)
        mem_addr: Memory address for load/store (future - when RTL exposes)
        mem_data: Memory data for load/store (future - when RTL exposes)
        mem_write: Memory write flag (future - when RTL exposes)
    """

    def __init__(self, pc, insn):
        """Create commit transaction.

        Args:
            pc: Program counter
            insn: Instruction word
        """
        self.pc = pc
        self.insn = insn
        # Future expansion when RTL provides more signals
        self.rd = None
        self.rd_value = None
        self.mem_addr = None
        self.mem_data = None
        self.mem_write = None

    def to_dict(self):
        """Convert to dictionary for scoreboard compatibility.

        Returns:
            Dictionary with commit information
        """
        return {
            'pc': self.pc,
            'insn': self.insn,
            'rd': self.rd,
            'rd_value': self.rd_value,
            'mem_addr': self.mem_addr,
            'mem_data': self.mem_data,
            'mem_write': self.mem_write
        }

    def __str__(self):
        """String representation for logging."""
        return f"Commit(PC=0x{self.pc:08x}, INSN=0x{self.insn:08x})"


class CommitMonitor(uvm_monitor):
    """UVM monitor for instruction commits.

    This monitor passively observes the commit interface from the RV32I CPU.
    When commit_valid is asserted, it captures the PC and instruction word,
    creates a CommitTransaction object, and sends it to connected scoreboards
    via the analysis port.

    Attributes:
        dut: Device under test handle
        analysis_port: UVM analysis port for sending transactions
        commit_count: Number of commits observed
        log_first_n: Log first N commits in detail (default 10)
    """

    def __init__(self, name, parent, dut, log_first_n=10):
        """Initialize commit monitor.

        Args:
            name: Component name in UVM hierarchy
            parent: Parent UVM component
            dut: Device under test handle
            log_first_n: Number of commits to log in detail (default 10)
        """
        super().__init__(name, parent)
        self.dut = dut
        self.analysis_port = uvm_analysis_port("commit_ap", self)
        self.commit_count = 0
        self.log_first_n = log_first_n

    def build_phase(self):
        """UVM build phase - called by framework."""
        super().build_phase()
        self.logger.info(f"Building {self.get_full_name()}")

    async def run_phase(self):
        """UVM run phase - monitor commit interface.

        This method runs continuously, watching for commit_valid assertions.
        When a commit occurs, it captures the transaction and broadcasts it
        to all connected scoreboards via the analysis port.
        """
        self.logger.info("Starting commit monitor")

        while True:
            await RisingEdge(self.dut.clk)
            await ReadOnly()  # Sample signals in ReadOnly region

            # Check if commit is valid
            if self.dut.commit_valid.value == 1:
                # Capture commit signals
                pc = int(self.dut.commit_pc.value)
                insn = int(self.dut.commit_insn.value)

                # Create transaction object
                txn = CommitTransaction(pc, insn)

                # Increment counter
                self.commit_count += 1

                # Log first N commits for debugging
                if self.commit_count <= self.log_first_n:
                    self.logger.info(f"Commit #{self.commit_count}: {txn}")
                elif self.commit_count == self.log_first_n + 1:
                    self.logger.info(f"(suppressing detailed logs after {self.log_first_n} commits)")

                # Broadcast to all connected scoreboards
                self.analysis_port.write(txn)

    def report_phase(self):
        """UVM report phase - print summary statistics."""
        self.logger.info(f"Commit monitor summary: {self.commit_count} commits observed")
