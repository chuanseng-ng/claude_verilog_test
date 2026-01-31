"""Base Sequence for pyuvm CPU tests.

This module provides the base sequence class that all CPU test sequences
inherit from. It provides common utilities and lifecycle hooks.

Features:
- UVM sequence lifecycle (pre_body, body, post_body)
- Common sequence utilities
- Access to environment components
- Proper sequence structure
"""

from pyuvm import uvm_sequence


class BaseSequence(uvm_sequence):
    """Base class for all CPU test sequences.

    This sequence provides common functionality for all CPU tests:
    - Lifecycle hooks (pre_body, post_body)
    - Access to sequencer
    - Common utilities

    Child classes should override body() to implement test logic.

    In a typical test:
        Test creates sequence → sequence.start(sequencer) →
        pre_body() → body() → post_body()

    Attributes:
        None (base class is minimal)
    """

    def __init__(self, name):
        """Initialize base sequence.

        Args:
            name: Sequence name for identification
        """
        super().__init__(name)

    async def pre_body(self):
        """Pre-body phase - called before body().

        Use this for:
        - Setup operations
        - Resource locking
        - Pre-conditions

        Child classes can override to add custom pre-body logic.
        Always call super().pre_body() first.
        """
        # Default: no pre-body operations
        pass

    async def body(self):
        """Body phase - main sequence logic.

        This is the main sequence execution phase. Child classes
        MUST override this method to implement test logic.

        Raises:
            NotImplementedError: If child class doesn't override
        """
        raise NotImplementedError(
            f"{self.__class__.__name__} must implement body() method"
        )

    async def post_body(self):
        """Post-body phase - called after body().

        Use this for:
        - Cleanup operations
        - Resource release
        - Post-conditions

        Child classes can override to add custom post-body logic.
        Always call super().post_body() last.
        """
        # Default: no post-body operations
        pass
