"""
Memory Model for RV32I CPU and GPU Reference Models

Provides a simple sparse memory implementation with alignment checking.
Conforms to REFERENCE_MODEL_SPEC.md.
"""


class MisalignedAccessError(Exception):
    """Exception raised when accessing memory with incorrect alignment."""

    pass  # pylint: disable=unnecessary-pass


class MemoryModel:
    """
    Sparse memory model with alignment checking.

    Implements a simple byte-addressable memory using a dictionary
    for sparse storage. Enforces natural alignment requirements per
    PHASE0_ARCHITECTURE_SPEC.md.
    """

    def __init__(self):
        """Initialize empty sparse memory."""
        self.mem = {}  # Sparse storage: {byte_address: byte_value}

    def read(self, addr: int, size: int = 4) -> int:
        """
        Read size bytes from addr (must be naturally aligned).

        Args:
            addr: Address to read from
            size: Access size in bytes (1, 2, or 4)

        Returns:
            Data value read from memory (little-endian)

        Raises:
            MisalignedAccessError: If addr is not aligned to size
            ValueError: If size is not 1, 2, or 4

        Examples:
            >>> mem = MemoryModel()
            >>> mem.write(0x1000, 0x12345678, 4)
            >>> mem.read(0x1000, 4)
            305419896  # 0x12345678
            >>> mem.read(0x1000, 1)
            120  # 0x78 (least significant byte)
        """
        if size not in [1, 2, 4]:
            raise ValueError(f"Invalid size {size}, must be 1, 2, or 4")

        # Check natural alignment
        if addr % size != 0:
            raise MisalignedAccessError(
                f"Address 0x{addr:08x} not aligned to {size}-byte boundary"
            )

        # Read bytes from sparse memory (little-endian)
        value = 0
        for i in range(size):
            byte_val = self.mem.get(addr + i, 0)  # Default to 0 if not written
            value |= byte_val << (i * 8)

        return value

    def write(self, addr: int, data: int, size: int = 4):
        """
        Write size bytes to addr (must be naturally aligned).

        Args:
            addr: Address to write to
            data: Data value to write
            size: Access size in bytes (1, 2, or 4)

        Raises:
            MisalignedAccessError: If addr is not aligned to size
            ValueError: If size is not 1, 2, or 4

        Examples:
            >>> mem = MemoryModel()
            >>> mem.write(0x1000, 0x12345678, 4)
            >>> mem.write(0x1004, 0xAB, 1)
        """
        if size not in [1, 2, 4]:
            raise ValueError(f"Invalid size {size}, must be 1, 2, or 4")

        # Check natural alignment
        if addr % size != 0:
            raise MisalignedAccessError(
                f"Address 0x{addr:08x} not aligned to {size}-byte boundary"
            )

        # Write bytes to sparse memory (little-endian)
        for i in range(size):
            byte_val = (data >> (i * 8)) & 0xFF
            self.mem[addr + i] = byte_val

    def load_program(self, program: dict[int, int], word_size: int = 4):
        """
        Load a program into memory.

        Convenience method for loading instruction words or data.

        Args:
            program: Dictionary mapping {address: value}
            word_size: Size of each value in bytes (default 4)

        Examples:
            >>> mem = MemoryModel()
            >>> program = {
            ...     0x0000: 0x00000093,  # addi x1, x0, 0
            ...     0x0004: 0x00100113,  # addi x2, x0, 1
            ... }
            >>> mem.load_program(program)
        """
        for addr, value in program.items():
            self.write(addr, value, word_size)

    def dump(self, start_addr: int, end_addr: int) -> dict[int, int]:
        """
        Dump memory contents in a range.

        Args:
            start_addr: Starting address (inclusive)
            end_addr: Ending address (exclusive)

        Returns:
            Dictionary mapping {address: byte_value} for all written bytes
            in the range

        Examples:
            >>> mem = MemoryModel()
            >>> mem.write(0x1000, 0x12345678, 4)
            >>> mem.dump(0x1000, 0x1004)
            {4096: 120, 4097: 86, 4098: 52, 4099: 18}
        """
        return {
            addr: self.mem[addr]
            for addr in range(start_addr, end_addr)
            if addr in self.mem
        }

    def clear(self):
        """Clear all memory contents."""
        self.mem.clear()

    def __repr__(self):
        """String representation showing number of bytes stored."""
        return f"MemoryModel({len(self.mem)} bytes stored)"
