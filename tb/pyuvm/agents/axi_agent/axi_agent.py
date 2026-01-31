"""AXI Agent for pyuvm.

This module implements a UVM agent that wraps the AXI memory driver.
It provides proper UVM hierarchy and configuration management.

Features:
- Agent wrapper for AXIMemoryDriver
- Reference model configuration
- DUT handle management
- Proper UVM lifecycle
"""

from pyuvm import uvm_agent
from .axi_driver import AXIMemoryDriver


class AXIAgent(uvm_agent):
    """UVM agent for AXI4-Lite memory interface.

    This agent wraps the AXIMemoryDriver and provides proper UVM hierarchy.
    It manages configuration (DUT handle, reference model) and instantiates
    the driver during the build phase.

    The agent is configured with:
    - dut: Device under test handle
    - ref_model: Optional reference model for memory synchronization

    In a typical testbench hierarchy:
        CPUEnvironment
        └── AXIAgent
            └── AXIMemoryDriver

    Attributes:
        dut: Device under test handle
        ref_model: Optional RV32IModel for memory synchronization
        driver: AXIMemoryDriver instance (created in build_phase)
    """

    def __init__(self, name, parent, dut, ref_model=None):
        """Initialize AXI agent.

        Args:
            name: Component name in UVM hierarchy
            parent: Parent UVM component (typically CPUEnvironment)
            dut: Device under test handle
            ref_model: Optional RV32IModel for memory synchronization
        """
        super().__init__(name, parent)
        self.dut = dut
        self.ref_model = ref_model
        self.driver = None  # Created in build_phase

    def build_phase(self):
        """UVM build phase - create driver.

        This phase instantiates the AXIMemoryDriver with the configured
        DUT handle and reference model.
        """
        super().build_phase()
        self.logger.info(f"Building {self.get_full_name()}")

        # Create AXI memory driver
        self.driver = AXIMemoryDriver(
            "axi_driver",
            self,
            dut=self.dut,
            ref_model=self.ref_model
        )

        self.logger.info("AXI agent build complete")

    def connect_phase(self):
        """UVM connect phase - no connections needed for AXI agent.

        The AXI driver handles protocol directly, no TLM connections required.
        """
        super().connect_phase()
        self.logger.info("AXI agent connect phase complete")
