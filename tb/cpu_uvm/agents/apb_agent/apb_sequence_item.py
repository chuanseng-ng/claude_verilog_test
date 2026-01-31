"""APB Debug Sequence Item for pyuvm.

This module defines the transaction item used for APB debug sequences.
It represents a single debug operation (halt, resume, register write, etc.).

Features:
- UVM sequence item structure
- Support for all APB debug operations
- Randomization support (future)
"""

from pyuvm import uvm_sequence_item


class APBDebugSequenceItem(uvm_sequence_item):
    """Sequence item for APB debug operations.

    This transaction represents a single debug command that can be
    sent from a sequence to the APB debug driver.

    Transaction types:
    - HALT: Halt the CPU
    - RESUME: Resume the CPU
    - STEP: Single-step one instruction
    - RESET: Reset the CPU
    - WRITE_GPR: Write general purpose register
    - READ_GPR: Read general purpose register
    - WRITE_PC: Write program counter
    - READ_PC: Read program counter
    - SET_BP: Set breakpoint
    - CLEAR_BP: Clear breakpoint

    Attributes:
        op: Operation type (string)
        addr: Address (for register/breakpoint operations)
        data: Data value (for write operations)
        reg_num: Register number (for GPR operations)
        bp_num: Breakpoint number (0 or 1)
        result: Result value (for read operations)
    """

    def __init__(self, name="apb_debug_item"):
        """Initialize APB debug sequence item.

        Args:
            name: Transaction name
        """
        super().__init__(name)
        self.op = None
        self.addr = 0
        self.data = 0
        self.reg_num = 0
        self.bp_num = 0
        self.result = None

    def __str__(self):
        """String representation for logging."""
        if self.op == "WRITE_GPR":
            return f"APBDebugItem({self.op}, x{self.reg_num}=0x{self.data:08x})"
        elif self.op == "READ_GPR":
            return f"APBDebugItem({self.op}, x{self.reg_num})"
        elif self.op == "SET_BP":
            return f"APBDebugItem({self.op}, bp{self.bp_num}=0x{self.addr:08x})"
        else:
            return f"APBDebugItem({self.op})"
