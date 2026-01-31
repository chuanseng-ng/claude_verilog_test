"""CPU Environment for pyuvm.

This module implements the top-level UVM environment for CPU testing.
It integrates all agents, monitors, and scoreboards into a complete
verification environment.

Features:
- Complete UVM testbench hierarchy
- AXI memory agent
- APB debug agent
- Commit monitor
- CPU scoreboard with reference model
- Automatic component connectivity
"""

from pyuvm import uvm_env
from ..agents.axi_agent.axi_agent import AXIAgent
from ..agents.apb_agent.apb_agent import APBAgent
from ..monitors.commit_monitor import CommitMonitor
from ..scoreboards.cpu_scoreboard import CPUScoreboard


class CPUEnvironment(uvm_env):
    """Top-level UVM environment for CPU verification.

    This environment creates and connects all verification components:
    - AXI Agent: Handles AXI4-Lite memory transactions
    - APB Agent: Handles APB3 debug interface
    - Commit Monitor: Observes instruction commits
    - CPU Scoreboard: Validates commits against reference model

    The environment establishes the following connections:
        CommitMonitor.analysis_port -> CPUScoreboard.commit_fifo

    Configuration requirements:
    - dut: Device under test handle
    - ref_model: RV32IModel reference model instance

    In a typical test hierarchy:
        CPUTest (uvm_test)
        └── CPUEnvironment (uvm_env)
            ├── AXIAgent
            │   └── AXIMemoryDriver
            ├── APBAgent
            │   ├── Sequencer
            │   └── APBDebugDriver
            ├── CommitMonitor
            └── CPUScoreboard

    Attributes:
        dut: Device under test handle
        ref_model: RV32IModel for reference checking
        axi_agent: AXI memory agent
        apb_agent: APB debug agent
        commit_monitor: Instruction commit monitor
        scoreboard: CPU scoreboard for validation
    """

    def __init__(self, name, parent, dut, ref_model):
        """Initialize CPU environment.

        Args:
            name: Component name in UVM hierarchy
            parent: Parent UVM component (typically CPUTest)
            dut: Device under test handle
            ref_model: RV32IModel for reference checking
        """
        super().__init__(name, parent)
        self.dut = dut
        self.ref_model = ref_model

        # Components (created in build_phase)
        self.axi_agent = None
        self.apb_agent = None
        self.commit_monitor = None
        self.scoreboard = None

    def build_phase(self):
        """UVM build phase - create all verification components.

        Creates:
        1. AXI Agent (with reference model for memory sync)
        2. APB Agent (for debug interface)
        3. Commit Monitor (to observe instruction commits)
        4. CPU Scoreboard (to validate against reference model)
        """
        super().build_phase()
        self.logger.info(f"Building {self.get_full_name()}")

        # Create AXI memory agent (with reference model)
        self.axi_agent = AXIAgent(
            "axi_agent",
            self,
            dut=self.dut,
            ref_model=self.ref_model
        )

        # Create APB debug agent
        self.apb_agent = APBAgent(
            "apb_agent",
            self,
            dut=self.dut
        )

        # Create commit monitor
        self.commit_monitor = CommitMonitor(
            "commit_monitor",
            self,
            dut=self.dut,
            log_first_n=10  # Log first 10 commits in detail
        )

        # Create CPU scoreboard
        self.scoreboard = CPUScoreboard(
            "cpu_scoreboard",
            self,
            ref_model=self.ref_model
        )

        self.logger.info("CPU environment build complete")

    def connect_phase(self):
        """UVM connect phase - connect analysis ports.

        Connects the commit monitor's analysis port to the scoreboard's
        analysis FIFO. This enables the monitor to send commit transactions
        to the scoreboard for validation.

        Connection:
            commit_monitor.analysis_port -> scoreboard.commit_fifo.analysis_export
        """
        super().connect_phase()
        self.logger.info("Connecting CPU environment components")

        # Connect monitor to scoreboard
        self.commit_monitor.analysis_port.connect(
            self.scoreboard.commit_fifo.analysis_export
        )

        self.logger.info("CPU environment connect phase complete")

    def end_of_elaboration_phase(self):
        """UVM end_of_elaboration phase - print hierarchy.

        This phase is called after all components are built and connected.
        It's useful for debugging the testbench structure.
        """
        super().end_of_elaboration_phase()
        self.logger.info("CPU environment hierarchy:")
        self.logger.info(f"  └── {self.get_full_name()}")
        self.logger.info(f"      ├── axi_agent: {self.axi_agent.get_full_name()}")
        self.logger.info(f"      ├── apb_agent: {self.apb_agent.get_full_name()}")
        self.logger.info(f"      ├── commit_monitor: {self.commit_monitor.get_full_name()}")
        self.logger.info(f"      └── scoreboard: {self.scoreboard.get_full_name()}")
