"""
AXI4-Lite Slave Agent for Memory Emulation

Provides a cocotb-based AXI4-Lite slave agent with:
- Memory model for read/write operations
- Configurable latency
- Transaction monitoring
- Error injection capabilities
"""

import cocotb
from cocotb.triggers import RisingEdge, ReadOnly, Timer
from typing import Dict, Optional
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from utils.base_components import BaseTransaction, BaseDriver, BaseMonitor, BaseAgent


class AXI4LiteTransaction(BaseTransaction):
    """AXI4-Lite transaction item"""

    def __init__(self, name: str = "axi4lite_txn"):
        super().__init__(name)
        # Write address channel
        self.awaddr: Optional[int] = None
        self.awvalid: bool = False
        self.awready: bool = False

        # Write data channel
        self.wdata: Optional[int] = None
        self.wstrb: int = 0xF
        self.wvalid: bool = False
        self.wready: bool = False

        # Write response channel
        self.bresp: int = 0  # 0=OKAY, 1=EXOKAY, 2=SLVERR, 3=DECERR
        self.bvalid: bool = False
        self.bready: bool = False

        # Read address channel
        self.araddr: Optional[int] = None
        self.arvalid: bool = False
        self.arready: bool = False

        # Read data channel
        self.rdata: Optional[int] = None
        self.rresp: int = 0
        self.rvalid: bool = False
        self.rready: bool = False

        # Transaction type
        self.is_write: bool = False
        self.is_read: bool = False

    def copy(self) -> 'AXI4LiteTransaction':
        """Create a copy of this transaction"""
        txn = AXI4LiteTransaction(self.name)
        txn.awaddr = self.awaddr
        txn.wdata = self.wdata
        txn.wstrb = self.wstrb
        txn.araddr = self.araddr
        txn.rdata = self.rdata
        txn.bresp = self.bresp
        txn.rresp = self.rresp
        txn.is_write = self.is_write
        txn.is_read = self.is_read
        return txn

    def __str__(self) -> str:
        if self.is_write:
            return f"AXI4-Lite WR: addr=0x{self.awaddr:08x} data=0x{self.wdata:08x} strb=0x{self.wstrb:x}"
        elif self.is_read:
            return f"AXI4-Lite RD: addr=0x{self.araddr:08x} data=0x{self.rdata:08x}"
        return "AXI4-Lite: Invalid transaction"


class AXI4LiteSlaveDriver(BaseDriver):
    """AXI4-Lite Slave Driver (Memory Model)"""

    def __init__(self, dut, clk, name: str = "axi4lite_slave", mem_size: int = 64*1024,
                 read_latency: int = 1, write_latency: int = 1):
        super().__init__(dut, clk, name)
        self.mem_size = mem_size
        self.memory: Dict[int, int] = {}  # Byte-addressable memory
        self.read_latency = read_latency
        self.write_latency = write_latency

        # Start driver tasks
        cocotb.start_soon(self._write_address_channel())
        cocotb.start_soon(self._write_data_channel())
        cocotb.start_soon(self._write_response_channel())
        cocotb.start_soon(self._read_address_channel())
        cocotb.start_soon(self._read_data_channel())

    async def reset(self) -> None:
        """Reset all AXI signals"""
        self.dut.m_axi_awready.value = 0
        self.dut.m_axi_wready.value = 0
        self.dut.m_axi_bvalid.value = 0
        self.dut.m_axi_bresp.value = 0
        self.dut.m_axi_arready.value = 0
        self.dut.m_axi_rvalid.value = 0
        self.dut.m_axi_rdata.value = 0
        self.dut.m_axi_rresp.value = 0

    def load_program(self, hex_file: str, base_addr: int = 0) -> None:
        """Load a hex file into memory"""
        try:
            word_count = 0
            with open(hex_file, 'r') as f:
                addr = base_addr
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('//'):
                        # Remove inline comments (split on // and take first part)
                        hex_data = line.split('//')[0].strip()
                        if not hex_data:
                            continue
                        # Parse hex data (assuming 32-bit words in hex format)
                        try:
                            data = int(hex_data, 16)
                            # Store as bytes in memory
                            for i in range(4):
                                self.memory[addr + i] = (data >> (i * 8)) & 0xFF
                            word_count += 1
                            addr += 4
                        except ValueError:
                            self.log.warning(f"Failed to parse hex line: '{hex_data}'")
                            continue
            self.log.info(f"Loaded {word_count} words from {hex_file} into memory at 0x{base_addr:08x}")
        except FileNotFoundError:
            self.log.exception(f"File not found: {hex_file}")
            raise

    def write_byte(self, addr: int, data: int) -> None:
        """Write a byte to memory"""
        if addr < self.mem_size:
            self.memory[addr] = data & 0xFF

    def read_byte(self, addr: int) -> int:
        """Read a byte from memory"""
        if addr < self.mem_size:
            return self.memory.get(addr, 0)
        return 0

    def read_word(self, addr: int) -> int:
        """Read a 32-bit word from memory"""
        word = 0
        for i in range(4):
            word |= self.read_byte(addr + i) << (i * 8)
        return word

    def write_word(self, addr: int, data: int, strb: int = 0xF) -> None:
        """Write a 32-bit word to memory with byte strobes"""
        for i in range(4):
            if strb & (1 << i):
                self.write_byte(addr + i, (data >> (i * 8)) & 0xFF)

    async def _write_address_channel(self) -> None:
        """Handle write address channel"""
        self.pending_write_addr = None
        while True:
            await RisingEdge(self.clk)
            # Accept write address
            if int(self.dut.m_axi_awvalid.value) and int(self.dut.m_axi_awready.value):
                self.pending_write_addr = int(self.dut.m_axi_awaddr.value)
                self.log.debug(f"Write address captured: 0x{self.pending_write_addr:08x}")

            # Set awready after latency
            if int(self.dut.m_axi_awvalid.value) and not int(self.dut.m_axi_awready.value):
                await Timer(self.write_latency, unit='ns')
                self.dut.m_axi_awready.value = 1
            else:
                self.dut.m_axi_awready.value = 0

    async def _write_data_channel(self) -> None:
        """Handle write data channel"""
        while True:
            await RisingEdge(self.clk)
            # Set wready after latency
            if int(self.dut.m_axi_wvalid.value) and not int(self.dut.m_axi_wready.value):
                await Timer(self.write_latency, unit='ns')
                self.dut.m_axi_wready.value = 1
            else:
                self.dut.m_axi_wready.value = 0

    async def _write_response_channel(self) -> None:
        """Handle write response channel"""
        while True:
            await RisingEdge(self.clk)
            # When both address and data are valid, perform write and send response
            if (int(self.dut.m_axi_awvalid.value) and int(self.dut.m_axi_awready.value) and
                int(self.dut.m_axi_wvalid.value) and int(self.dut.m_axi_wready.value)):

                addr = int(self.dut.m_axi_awaddr.value)
                data = int(self.dut.m_axi_wdata.value)
                strb = int(self.dut.m_axi_wstrb.value)

                # Write to memory
                self.write_word(addr, data, strb)
                self.log.debug(f"Memory write: addr=0x{addr:08x} data=0x{data:08x} strb=0x{strb:x}")

                # Send write response
                self.dut.m_axi_bvalid.value = 1
                self.dut.m_axi_bresp.value = 0  # OKAY

                # Wait for bready with timeout
                timeout_cycles = 1000
                for _cycle in range(timeout_cycles):
                    if int(self.dut.m_axi_bready.value):
                        break
                    await RisingEdge(self.clk)
                else:
                    self.log.error(f"AXI4-Lite write response timeout waiting for bready at addr=0x{addr:08x}")
                    # Continue anyway to avoid hanging the driver
                    self.dut.m_axi_bvalid.value = 0
                    continue

                await RisingEdge(self.clk)
                self.dut.m_axi_bvalid.value = 0

    async def _read_address_channel(self) -> None:
        """Handle read address channel"""
        while True:
            await RisingEdge(self.clk)
            # Set arready after latency
            if int(self.dut.m_axi_arvalid.value) and not int(self.dut.m_axi_arready.value):
                await Timer(self.read_latency, unit='ns')
                self.dut.m_axi_arready.value = 1
            else:
                self.dut.m_axi_arready.value = 0

    async def _read_data_channel(self) -> None:
        """Handle read data channel"""
        while True:
            await RisingEdge(self.clk)
            # When read address is valid, perform read and send data
            if int(self.dut.m_axi_arvalid.value) and int(self.dut.m_axi_arready.value):
                addr = int(self.dut.m_axi_araddr.value)
                data = self.read_word(addr)

                self.log.debug(f"Memory read: addr=0x{addr:08x} data=0x{data:08x}")

                # Send read data
                self.dut.m_axi_rvalid.value = 1
                self.dut.m_axi_rdata.value = data
                self.dut.m_axi_rresp.value = 0  # OKAY

                # Wait for rready with timeout
                timeout_cycles = 1000
                for _cycle in range(timeout_cycles):
                    if int(self.dut.m_axi_rready.value):
                        break
                    await RisingEdge(self.clk)
                else:
                    self.log.error(f"AXI4-Lite read data timeout waiting for rready at addr=0x{addr:08x}")
                    # Continue anyway to avoid hanging the driver
                    self.dut.m_axi_rvalid.value = 0
                    self.dut.m_axi_rdata.value = 0
                    continue

                await RisingEdge(self.clk)
                self.dut.m_axi_rvalid.value = 0
                self.dut.m_axi_rdata.value = 0


class AXI4LiteMonitor(BaseMonitor):
    """AXI4-Lite Monitor for transaction observation"""

    def __init__(self, dut, clk, name: str = "axi4lite_mon"):
        super().__init__(dut, clk, name)

    async def _monitor_loop(self) -> None:
        """Monitor AXI4-Lite transactions"""
        while True:
            await RisingEdge(self.clk)
            await ReadOnly()

            # Monitor write transactions
            if int(self.dut.m_axi_awvalid.value) and int(self.dut.m_axi_awready.value):
                txn = AXI4LiteTransaction()
                txn.is_write = True
                txn.awaddr = int(self.dut.m_axi_awaddr.value)

                # Wait for write data
                timeout_cycles = 0
                while not (int(self.dut.m_axi_wvalid.value) and int(self.dut.m_axi_wready.value)):
                    await RisingEdge(self.clk)
                    await ReadOnly()
                    timeout_cycles += 1
                    if timeout_cycles >= 1000:
                        raise TimeoutError(f"AXI4-Lite write data timeout after {timeout_cycles} cycles")

                txn.wdata = int(self.dut.m_axi_wdata.value)
                txn.wstrb = int(self.dut.m_axi_wstrb.value)

                self.log.debug(str(txn))
                self._notify_callbacks(txn)

            # Monitor read transactions
            if int(self.dut.m_axi_arvalid.value) and int(self.dut.m_axi_arready.value):
                txn = AXI4LiteTransaction()
                txn.is_read = True
                txn.araddr = int(self.dut.m_axi_araddr.value)

                # Wait for read data
                timeout_cycles = 0
                while not (int(self.dut.m_axi_rvalid.value) and int(self.dut.m_axi_rready.value)):
                    await RisingEdge(self.clk)
                    await ReadOnly()
                    timeout_cycles += 1
                    if timeout_cycles >= 1000:
                        raise TimeoutError(f"AXI4-Lite read data timeout after {timeout_cycles} cycles")

                txn.rdata = int(self.dut.m_axi_rdata.value)

                self.log.debug(str(txn))
                self._notify_callbacks(txn)


class AXI4LiteAgent(BaseAgent):
    """AXI4-Lite Agent combining driver and monitor"""

    def __init__(self, dut, clk, name: str = "axi4lite_agent",
                 mem_size: int = 64*1024, read_latency: int = 1, write_latency: int = 1):
        super().__init__(dut, clk, name)
        self.driver = AXI4LiteSlaveDriver(dut, clk, f"{name}_driver",
                                          mem_size, read_latency, write_latency)
        self.monitor = AXI4LiteMonitor(dut, clk, f"{name}_monitor")
