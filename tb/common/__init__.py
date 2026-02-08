"""Common utilities for testbench infrastructure.

This package provides shared utilities used across different testbench components:
- Performance tracking and reporting
- Logging utilities (future)
- Common data structures (future)
"""

from .performance_report import PerformanceTracker

__all__ = ["PerformanceTracker"]
