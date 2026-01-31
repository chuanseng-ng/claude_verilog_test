"""
Wrapper for pyuvm random instruction tests.

This file imports and re-exports the pyuvm random tests so they can be
discovered by cocotb when running from the tb/cocotb/cpu/ directory.
"""

# Add project root to path to find tb.cpu_uvm modules
import sys
from pathlib import Path

# Get project root (tb/cocotb/cpu -> ../../.. -> project root)
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import all test functions from the cpu_uvm random tests module
from tb.cpu_uvm.tests.test_random_uvm import (
    test_random_single_uvm,
    test_random_multi_seed_uvm,
)

# Re-export for cocotb discovery
__all__ = [
    'test_random_single_uvm',
    'test_random_multi_seed_uvm',
]
