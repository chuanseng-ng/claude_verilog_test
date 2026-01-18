"""
Unit tests for MemoryModel.

Tests the sparse memory implementation with alignment checking.
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from tb.models.memory_model import MemoryModel, MisalignedAccessError


class TestMemoryModel:
    """Test cases for MemoryModel."""

    def test_initialization(self):
        """Test memory model initializes empty."""
        mem = MemoryModel()
        assert len(mem.mem) == 0

    def test_word_read_write(self):
        """Test 4-byte (word) read/write."""
        mem = MemoryModel()
        mem.write(0x1000, 0x12345678, 4)
        assert mem.read(0x1000, 4) == 0x12345678

    def test_halfword_read_write(self):
        """Test 2-byte (halfword) read/write."""
        mem = MemoryModel()
        mem.write(0x1000, 0xABCD, 2)
        assert mem.read(0x1000, 2) == 0xABCD

    def test_byte_read_write(self):
        """Test 1-byte read/write."""
        mem = MemoryModel()
        mem.write(0x1000, 0x42, 1)
        assert mem.read(0x1000, 1) == 0x42

    def test_little_endian(self):
        """Test little-endian byte ordering."""
        mem = MemoryModel()
        mem.write(0x1000, 0x12345678, 4)

        # Read individual bytes
        assert mem.read(0x1000, 1) == 0x78  # LSB
        assert mem.read(0x1001, 1) == 0x56
        assert mem.read(0x1002, 1) == 0x34
        assert mem.read(0x1003, 1) == 0x12  # MSB

    def test_word_alignment(self):
        """Test word alignment requirement."""
        mem = MemoryModel()

        # Aligned access should work
        mem.write(0x1000, 0x12345678, 4)
        assert mem.read(0x1000, 4) == 0x12345678

        # Misaligned access should fail
        with pytest.raises(MisalignedAccessError):
            mem.write(0x1001, 0x12345678, 4)

        with pytest.raises(MisalignedAccessError):
            mem.read(0x1002, 4)

    def test_halfword_alignment(self):
        """Test halfword alignment requirement."""
        mem = MemoryModel()

        # Aligned access should work
        mem.write(0x1000, 0xABCD, 2)
        mem.write(0x1002, 0x1234, 2)
        assert mem.read(0x1000, 2) == 0xABCD
        assert mem.read(0x1002, 2) == 0x1234

        # Misaligned access should fail
        with pytest.raises(MisalignedAccessError):
            mem.write(0x1001, 0xABCD, 2)

        with pytest.raises(MisalignedAccessError):
            mem.read(0x1003, 2)

    def test_byte_no_alignment(self):
        """Test byte access has no alignment requirement."""
        mem = MemoryModel()

        # All addresses should work for byte access
        for addr in range(0x1000, 0x1010):
            mem.write(addr, addr & 0xFF, 1)
            assert mem.read(addr, 1) == (addr & 0xFF)

    def test_sparse_memory(self):
        """Test sparse memory (unwritten locations read as 0)."""
        mem = MemoryModel()

        # Reading unwritten location should return 0
        assert mem.read(0x1000, 4) == 0
        assert mem.read(0x2000, 1) == 0

        # Write to one location
        mem.write(0x1000, 0xDEADBEEF, 4)

        # Nearby unwritten location still reads as 0
        assert mem.read(0x1004, 4) == 0
        assert mem.read(0x2000, 4) == 0

        # Written location reads correctly
        assert mem.read(0x1000, 4) == 0xDEADBEEF

    def test_load_program(self):
        """Test load_program convenience method."""
        mem = MemoryModel()

        program = {
            0x0000: 0x00000093,  # addi x1, x0, 0
            0x0004: 0x00100113,  # addi x2, x0, 1
            0x0008: 0x002081b3,  # add x3, x1, x2
        }

        mem.load_program(program)

        assert mem.read(0x0000, 4) == 0x00000093
        assert mem.read(0x0004, 4) == 0x00100113
        assert mem.read(0x0008, 4) == 0x002081b3

    def test_dump(self):
        """Test memory dump functionality."""
        mem = MemoryModel()

        mem.write(0x1000, 0x12345678, 4)

        dump = mem.dump(0x1000, 0x1004)

        # Should have 4 bytes
        assert len(dump) == 4
        assert dump[0x1000] == 0x78
        assert dump[0x1001] == 0x56
        assert dump[0x1002] == 0x34
        assert dump[0x1003] == 0x12

    def test_clear(self):
        """Test memory clear."""
        mem = MemoryModel()

        mem.write(0x1000, 0xDEADBEEF, 4)
        assert len(mem.mem) > 0

        mem.clear()
        assert len(mem.mem) == 0
        assert mem.read(0x1000, 4) == 0

    def test_invalid_size(self):
        """Test invalid access sizes are rejected."""
        mem = MemoryModel()

        with pytest.raises(ValueError):
            mem.write(0x1000, 0x12345678, 3)

        with pytest.raises(ValueError):
            mem.read(0x1000, 8)

    def test_overlapping_writes(self):
        """Test overlapping writes work correctly."""
        mem = MemoryModel()

        # Write word
        mem.write(0x1000, 0xDEADBEEF, 4)

        # Overwrite middle bytes
        mem.write(0x1001, 0xAA, 1)
        mem.write(0x1002, 0xBB, 1)

        # Read back word
        result = mem.read(0x1000, 4)
        assert result == 0xDEBBAAEF  # Little-endian: [EF AA BB DE]

    def test_repr(self):
        """Test string representation."""
        mem = MemoryModel()
        assert "0 bytes" in repr(mem)

        mem.write(0x1000, 0x12345678, 4)
        assert "4 bytes" in repr(mem)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
