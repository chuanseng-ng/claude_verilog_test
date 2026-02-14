"""
Wrapper for pyuvm stress tests.

This file imports and re-exports the pyuvm stress tests so they can be
discovered by cocotb when running from the tb/cocotb/cpu/ directory.
"""

# Add project root to path to find tb.cpu_uvm modules
import sys
from pathlib import Path

# Get project root (tb/cocotb/cpu -> ../../.. -> project root)
project_root = Path(__file__).resolve().parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import all test functions from the cpu_uvm stress tests module
from tb.cpu_uvm.tests.test_stress_uvm import (
    test_stress_alu_intensive,
    test_stress_immediate_heavy,
    test_stress_jump_heavy,
    test_stress_shift_intensive,
)

# Re-export for cocotb discovery
__all__ = [
    "test_stress_alu_intensive",
    "test_stress_jump_heavy",
    "test_stress_shift_intensive",
    "test_stress_immediate_heavy",
]
