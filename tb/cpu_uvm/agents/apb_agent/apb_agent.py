"""APB Agent for pyuvm.

This module implements a UVM agent that wraps the APB debug driver
and provides sequence-based test stimulus.

Features:
- Agent wrapper for APBDebugDriver
- Sequencer for sequence-driven testing
- Proper TLM connections
- Proper UVM lifecycle
"""

from pyuvm import uvm_agent, uvm_sequencer
from .apb_driver import APBDebugDriver


class APBAgent(uvm_agent):
    """UVM agent for APB3 debug interface.

    This agent wraps the APBDebugDriver and provides a sequencer for
    sequence-based testing. It manages the UVM hierarchy and TLM
    connections between sequencer and driver.

    In a typical testbench hierarchy:
        CPUEnvironment
        └── APBAgent
            ├── Sequencer (uvm_sequencer)
            └── APBDebugDriver

    The sequencer and driver are connected via TLM ports:
        driver.seq_item_port <-> sequencer.seq_item_export

    Attributes:
        dut: Device under test handle
        sequencer: UVM sequencer for APB debug transactions
        driver: APBDebugDriver instance
    """

    def __init__(self, name, parent, dut):
        """Initialize APB agent.

        Args:
            name: Component name in UVM hierarchy
            parent: Parent UVM component (typically CPUEnvironment)
            dut: Device under test handle
        """
        super().__init__(name, parent)
        self.dut = dut
        self.sequencer = None  # Created in build_phase
        self.driver = None  # Created in build_phase

    def build_phase(self):
        """UVM build phase - create sequencer and driver.

        This phase instantiates:
        1. UVM sequencer for APBDebugSequenceItem transactions
        2. APBDebugDriver for protocol handling
        """
        super().build_phase()
        self.logger.info(f"Building {self.get_full_name()}")

        # Create sequencer for APB debug sequences
        self.sequencer = uvm_sequencer("apb_sequencer", self)

        # Create APB debug driver
        self.driver = APBDebugDriver("apb_driver", self, dut=self.dut)

        self.logger.info("APB agent build complete")

    def connect_phase(self):
        """UVM connect phase - connect sequencer to driver.

        Connects the sequencer's seq_item_export to the driver's seq_item_port.
        This enables sequence items to flow from sequences through the sequencer
        to the driver.
        """
        super().connect_phase()
        self.logger.info("Connecting APB agent components")

        # Connect sequencer to driver
        # Note: Driver's seq_item_port is inherited from uvm_driver base class
        self.driver.seq_item_port.connect(self.sequencer.seq_item_export)

        self.logger.info("APB agent connect phase complete")
