"""AXI4-Lite Memory Driver for pyuvm.

This module implements a UVM driver that models an AXI4-Lite memory slave.
It replaces the SimpleAXIMemory class used in legacy cocotb tests.

Features:
- Full AXI4-Lite protocol handling (read/write)
- Byte-enable write strobes support
- Reference model memory synchronization
- Proper UVM lifecycle management
"""

import cocotb
from cocotb.triggers import RisingEdge
from pyuvm import uvm_driver


class AXIMemoryDriver(uvm_driver):
    """UVM driver for AXI4-Lite memory slave model.

    This driver implements the AXI4-Lite slave protocol for memory operations.
    It handles both read and write transactions, with proper byte-strobe support
    for partial word writes.

    The driver automatically synchronizes writes with the reference model if provided,
    ensuring consistency between RTL memory and reference model memory.

    Attributes:
        dut: Device under test (DUT) handle
        ref_model: Optional reference model for memory synchronization
        mem: Dictionary storing memory contents {addr: data}
    """

    def __init__(self, name, parent, dut, ref_model=None):
        """Initialize AXI memory driver.

        Args:
            name: Component name in UVM hierarchy
            parent: Parent UVM component
            dut: Device under test handle
            ref_model: Optional RV32IModel for memory synchronization
        """
        super().__init__(name, parent)
        self.dut = dut
        self.ref_model = ref_model
        self.mem = {}  # Memory buffer: {addr: 32-bit word}
        self._read_task = None
        self._write_task = None

    def build_phase(self):
        """UVM build phase - called by framework."""
        super().build_phase()
        self.logger.info(f"Building {self.get_full_name()}")

    async def run_phase(self):
        """UVM run phase - spawn AXI protocol handlers.

        This phase starts the background tasks for handling AXI read and write
        transactions. These tasks run concurrently and respond to DUT signals.
        """
        self.logger.info("Starting AXI memory driver")

        # Spawn background handlers for AXI protocol
        self._read_task = cocotb.start_soon(self.axi_read_handler())
        self._write_task = cocotb.start_soon(self.axi_write_handler())

        # Keep run_phase alive while handlers run
        # The handlers will run until simulation ends
        await cocotb.triggers.NullTrigger()

    async def final_phase(self):
        """UVM final phase - cleanup background tasks."""
        self.logger.info("Stopping AXI memory driver")

        # Kill background tasks if they're still running
        if self._read_task is not None:
            self._read_task.kill()
        if self._write_task is not None:
            self._write_task.kill()

    def write_word(self, addr, data):
        """Write 32-bit word to memory.

        Automatically synchronizes with reference model if available.

        Args:
            addr: Word-aligned address (will be aligned to 4-byte boundary)
            data: 32-bit data value
        """
        aligned_addr = addr & 0xFFFFFFFC
        masked_data = data & 0xFFFFFFFF

        self.mem[aligned_addr] = masked_data

        # Sync with reference model
        if self.ref_model is not None:
            self.ref_model.memory.write(aligned_addr, masked_data, 4)

    def read_word(self, addr):
        """Read 32-bit word from memory.

        Args:
            addr: Word-aligned address (will be aligned to 4-byte boundary)

        Returns:
            32-bit data value (0 if address not written)
        """
        aligned_addr = addr & 0xFFFFFFFC
        return self.mem.get(aligned_addr, 0)

    def reset_memory(self):
        """Clear all memory contents.

        Use this between tests to ensure clean state.
        Also clears reference model memory if available.
        """
        self.mem.clear()
        if self.ref_model is not None:
            self.ref_model.memory.mem.clear()
        self.logger.info("Memory reset complete")

    async def axi_read_handler(self):
        """Handle AXI read transactions.

        AXI Read Protocol:
        1. Master asserts arvalid + araddr
        2. Slave asserts arready (1 cycle)
        3. Slave asserts rvalid + rdata + rresp (wait for rready)
        4. Master asserts rready
        5. Transaction completes
        """
        while True:
            await RisingEdge(self.dut.clk)

            if self.dut.axi_arvalid.value == 1:
                # Accept read request
                self.dut.axi_arready.value = 1
                addr = int(self.dut.axi_araddr.value)
                data = self.read_word(addr)

                # Next cycle: de-assert arready, assert rvalid with data
                await RisingEdge(self.dut.clk)
                self.dut.axi_arready.value = 0
                self.dut.axi_rvalid.value = 1
                self.dut.axi_rdata.value = data
                self.dut.axi_rresp.value = 0  # OKAY response

                # Wait for master to accept read data (rready)
                while self.dut.axi_rready.value == 0:
                    await RisingEdge(self.dut.clk)

                # De-assert rvalid on next cycle
                await RisingEdge(self.dut.clk)
                self.dut.axi_rvalid.value = 0
            else:
                # No read request - ensure arready is low
                self.dut.axi_arready.value = 0

    async def axi_write_handler(self):
        """Handle AXI write transactions with byte-enable strobes.

        AXI Write Protocol:
        1. Master asserts awvalid + awaddr AND wvalid + wdata + wstrb
        2. Slave asserts awready + wready (1 cycle)
        3. Slave processes write with byte strobes
        4. Slave asserts bvalid + bresp (wait for bready)
        5. Master asserts bready
        6. Transaction completes

        Byte Strobes (axi_wstrb):
        - wstrb[0] -> byte 0 (bits 7:0)
        - wstrb[1] -> byte 1 (bits 15:8)
        - wstrb[2] -> byte 2 (bits 23:16)
        - wstrb[3] -> byte 3 (bits 31:24)

        For partial word writes, we read the existing word, merge the bytes
        based on strobes, and write back the merged result.
        """
        while True:
            await RisingEdge(self.dut.clk)

            # Wait for both address and data phases (simplified AXI - both together)
            if self.dut.axi_awvalid.value == 1 and self.dut.axi_wvalid.value == 1:
                # Accept write request
                self.dut.axi_awready.value = 1
                self.dut.axi_wready.value = 1

                addr = int(self.dut.axi_awaddr.value)
                new_data = int(self.dut.axi_wdata.value)
                wstrb = int(self.dut.axi_wstrb.value)

                # Next cycle: de-assert ready signals
                await RisingEdge(self.dut.clk)
                self.dut.axi_awready.value = 0
                self.dut.axi_wready.value = 0

                # Read existing word (for byte-masked writes)
                old_data = self.read_word(addr)

                # Merge bytes based on write strobes
                merged_data = 0
                for byte_idx in range(4):
                    if wstrb & (1 << byte_idx):
                        # Use new byte from wdata
                        byte_val = (new_data >> (byte_idx * 8)) & 0xFF
                    else:
                        # Keep old byte from existing word
                        byte_val = (old_data >> (byte_idx * 8)) & 0xFF
                    merged_data |= (byte_val << (byte_idx * 8))

                # Write merged word to memory (and sync with ref model)
                self.write_word(addr, merged_data)

                # Assert write response
                self.dut.axi_bvalid.value = 1
                self.dut.axi_bresp.value = 0  # OKAY response

                # Wait for master to accept response (bready)
                while self.dut.axi_bready.value == 0:
                    await RisingEdge(self.dut.clk)

                # De-assert bvalid on next cycle
                await RisingEdge(self.dut.clk)
                self.dut.axi_bvalid.value = 0
