"""
AXI4-Lite Master BFM (Bus Functional Model)

Provides an AXI4-Lite master interface for testbenches.
Used to initiate read/write transactions on the AXI4-Lite bus.
"""

import cocotb
from cocotb.triggers import RisingEdge, Timer
from cocotb.types import LogicArray
from typing import Optional


class AXI4LiteMaster:
    """
    AXI4-Lite Master Bus Functional Model.

    Implements an AXI4-Lite master that can initiate read and write
    transactions. Useful for testing AXI4-Lite slave devices.

    Per PHASE1_ARCHITECTURE_SPEC.md:
    - Address width: 32 bits
    - Data width: 32 bits
    - Outstanding transactions: 1 (simple design)
    """

    def __init__(self, dut, name, clock, reset=None):
        """
        Initialize AXI4-Lite master.

        Args:
            dut: Device under test
            name: Prefix for signal names (e.g., 'axi_')
            clock: Clock signal
            reset: Reset signal (optional)
        """
        self.dut = dut
        self.clock = clock
        self.reset = reset

        # Write address channel
        self.awvalid = getattr(dut, f"{name}awvalid")
        self.awready = getattr(dut, f"{name}awready")
        self.awaddr = getattr(dut, f"{name}awaddr")
        self.awprot = getattr(dut, f"{name}awprot")

        # Write data channel
        self.wvalid = getattr(dut, f"{name}wvalid")
        self.wready = getattr(dut, f"{name}wready")
        self.wdata = getattr(dut, f"{name}wdata")
        self.wstrb = getattr(dut, f"{name}wstrb")

        # Write response channel
        self.bvalid = getattr(dut, f"{name}bvalid")
        self.bready = getattr(dut, f"{name}bready")
        self.bresp = getattr(dut, f"{name}bresp")

        # Read address channel
        self.arvalid = getattr(dut, f"{name}arvalid")
        self.arready = getattr(dut, f"{name}arready")
        self.araddr = getattr(dut, f"{name}araddr")
        self.arprot = getattr(dut, f"{name}arprot")

        # Read data channel
        self.rvalid = getattr(dut, f"{name}rvalid")
        self.rready = getattr(dut, f"{name}rready")
        self.rdata = getattr(dut, f"{name}rdata")
        self.rresp = getattr(dut, f"{name}rresp")

        # Initialize signals
        self._init_signals()

    def _init_signals(self):
        """Initialize all master outputs to idle state."""
        # Write address channel
        self.awvalid.value = 0
        self.awaddr.value = 0
        self.awprot.value = 0

        # Write data channel
        self.wvalid.value = 0
        self.wdata.value = 0
        self.wstrb.value = 0xF  # All bytes valid by default

        # Write response channel
        self.bready.value = 1  # Always ready to accept responses

        # Read address channel
        self.arvalid.value = 0
        self.araddr.value = 0
        self.arprot.value = 0

        # Read data channel
        self.rready.value = 1  # Always ready to accept data

    async def write(self, addr: int, data: int, strb: int = 0xF, prot: int = 0) -> int:
        """
        Perform AXI4-Lite write transaction.

        Args:
            addr: 32-bit address
            data: 32-bit data to write
            strb: Write strobes (4 bits, one per byte)
            prot: Protection type (default 0)

        Returns:
            Response code (0=OKAY, 1=EXOKAY, 2=SLVERR, 3=DECERR)
        """
        # Write address phase
        self.awvalid.value = 1
        self.awaddr.value = addr
        self.awprot.value = prot

        # Write data phase (can happen simultaneously with address)
        self.wvalid.value = 1
        self.wdata.value = data
        self.wstrb.value = strb

        # Wait for address and data handshakes
        aw_done = False
        w_done = False

        while not (aw_done and w_done):
            await RisingEdge(self.clock)

            if self.awvalid.value and self.awready.value:
                aw_done = True
                self.awvalid.value = 0

            if self.wvalid.value and self.wready.value:
                w_done = True
                self.wvalid.value = 0

        # Wait for write response
        while not (self.bvalid.value and self.bready.value):
            await RisingEdge(self.clock)

        resp = int(self.bresp.value)
        return resp

    async def read(self, addr: int, prot: int = 0) -> tuple[int, int]:
        """
        Perform AXI4-Lite read transaction.

        Args:
            addr: 32-bit address
            prot: Protection type (default 0)

        Returns:
            Tuple of (data, response)
            - data: 32-bit read data
            - response: Response code (0=OKAY, 1=EXOKAY, 2=SLVERR, 3=DECERR)
        """
        # Read address phase
        self.arvalid.value = 1
        self.araddr.value = addr
        self.arprot.value = prot

        # Wait for address handshake
        while not (self.arvalid.value and self.arready.value):
            await RisingEdge(self.clock)

        self.arvalid.value = 0

        # Wait for read data
        while not (self.rvalid.value and self.rready.value):
            await RisingEdge(self.clock)

        data = int(self.rdata.value)
        resp = int(self.rresp.value)

        return (data, resp)

    async def reset_master(self, duration_cycles: int = 10):
        """
        Assert reset and initialize master.

        Args:
            duration_cycles: Number of clock cycles to hold reset
        """
        if self.reset is None:
            return

        self.reset.value = 0  # Active-low reset
        self._init_signals()

        for _ in range(duration_cycles):
            await RisingEdge(self.clock)

        self.reset.value = 1  # Deassert reset
        await RisingEdge(self.clock)
