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

    # AXI handshake timeout (cycles)
    AXI_TIMEOUT_CYCLES = 1000

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
        The phase waits for both tasks to complete before finishing.
        """
        self.logger.info("Starting AXI memory driver")

        # Initialize AXI outputs to idle state (0) to avoid X-driven spurious handshakes
        self.dut.axi_arready_i.value = 0
        self.dut.axi_rvalid_i.value = 0
        self.dut.axi_rdata_i.value = 0
        self.dut.axi_rresp_i.value = 0
        if hasattr(self.dut, "axi_rlast_i"):
            self.dut.axi_rlast_i.value = 0
        self.dut.axi_awready_i.value = 0
        self.dut.axi_wready_i.value = 0
        self.dut.axi_bvalid_i.value = 0
        self.dut.axi_bresp_i.value = 0

        # Spawn background handlers for AXI protocol
        self._read_task = cocotb.start_soon(self.axi_read_handler())
        self._write_task = cocotb.start_soon(self.axi_write_handler())

        # Wait for both handlers to complete (keeps run_phase alive)
        # Note: In practice, these tasks run forever until simulation ends,
        # but we properly join them to ensure cleanup happens correctly
        await cocotb.triggers.Combine(self._read_task.join(), self._write_task.join())

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
            self.ref_model.memory.clear()
        self.logger.info("Memory reset complete")

    async def axi_read_handler(self):
        """Handle AXI read burst transactions.

        AXI Read Protocol (burst-capable):
        1. Master asserts arvalid + araddr (+ arlen for burst)
        2. Slave waits 1-cycle stabilization, then asserts arready
        3. Slave samples arlen (default 0); loops arlen+1 R beats:
           - asserts rvalid + rdata + rresp
           - asserts rlast on the final beat
           - waits for rready with AXI_TIMEOUT_CYCLES per-beat guard
        4. Deasserts rvalid + rlast after last beat

        Note: A 1-cycle stabilization delay is inserted between seeing arvalid
        and asserting arready.  This prevents a race condition where the AXI
        arbiter switches from an IF fetch to a MEM load between the cycle
        Python samples araddr and the cycle arready takes effect in RTL.
        """
        while True:
            await RisingEdge(self.dut.clk_i)

            if self.dut.axi_arvalid_o.value == 1:
                # Wait 1 cycle for the pipeline/arbiter to settle.
                # Without this delay, the arbiter can switch requestors
                # (IF→MEM) between the cycle we read araddr and the cycle
                # arready takes effect, causing the wrong data to be returned.
                await RisingEdge(self.dut.clk_i)

                # Re-check arvalid after stabilization
                if self.dut.axi_arvalid_o.value != 1:
                    self.dut.axi_arready_i.value = 0
                    continue

                # Accept read request (address is now stable)
                addr = int(self.dut.axi_araddr_o.value)
                # Sample burst length (default 0 for AXI4-Lite backward compat)
                arlen = int(getattr(self.dut, "axi_arlen_o", 0))
                nbeats = arlen + 1
                self.dut.axi_arready_i.value = 1
                self.logger.debug(
                    f"AXI_READ: addr=0x{addr:08x} arlen={arlen} nbeats={nbeats}"
                )

                # Next cycle: de-assert arready, begin R beats
                await RisingEdge(self.dut.clk_i)
                self.dut.axi_arready_i.value = 0

                # Drive nbeats R responses; rlast on final beat; per-beat timeout
                for beat in range(nbeats):
                    beat_addr = (addr & 0xFFFFFFFC) + beat * 4
                    data = self.read_word(beat_addr)
                    is_last = (beat == nbeats - 1)

                    self.dut.axi_rvalid_i.value = 1
                    self.dut.axi_rdata_i.value = data
                    self.dut.axi_rresp_i.value = 0  # OKAY response
                    if hasattr(self.dut, "axi_rlast_i"):
                        self.dut.axi_rlast_i.value = 1 if is_last else 0

                    # Wait for master to accept this beat (rready) with per-beat timeout
                    timeout_count = 0
                    while self.dut.axi_rready_o.value == 0:
                        timeout_count += 1
                        if timeout_count >= self.AXI_TIMEOUT_CYCLES:
                            self.dut.axi_rvalid_i.value = 0
                            if hasattr(self.dut, "axi_rlast_i"):
                                self.dut.axi_rlast_i.value = 0
                            raise TimeoutError(
                                f"AXI read data handshake timeout at beat {beat}: master did not "
                                f"assert axi_rready after {self.AXI_TIMEOUT_CYCLES} cycles "
                                f"(addr=0x{beat_addr:08x}, method=axi_read_handler)"
                            )
                        await RisingEdge(self.dut.clk_i)

                    # Beat accepted — advance clock before next beat
                    await RisingEdge(self.dut.clk_i)

                # De-assert rvalid + rlast after final beat accepted
                self.dut.axi_rvalid_i.value = 0
                if hasattr(self.dut, "axi_rlast_i"):
                    self.dut.axi_rlast_i.value = 0
            else:
                # No read request - ensure arready is low
                self.dut.axi_arready_i.value = 0

    async def axi_write_handler(self):
        """Handle AXI write burst transactions with byte-enable strobes.

        AXI Write Protocol (burst-capable, independent AW/W channels):
        1. Master asserts awvalid + awaddr + awlen (address phase)
        2. Slave accepts AW when awvalid seen (pulse awready)
        3. For each of awlen+1 W beats:
           - wait for wvalid, pulse wready, latch wdata/wstrb
           - break early when wlast seen (default 1 for single-beat compat)
           - per-beat AXI_TIMEOUT_CYCLES guard on bready handshake
        4. Slave asserts ONE bvalid + bresp; waits bready with timeout

        Byte Strobes (axi_wstrb):
        - wstrb[0] -> byte 0 (bits 7:0)
        - wstrb[1] -> byte 1 (bits 15:8)
        - wstrb[2] -> byte 2 (bits 23:16)
        - wstrb[3] -> byte 3 (bits 31:24)
        """
        while True:
            await RisingEdge(self.dut.clk_i)

            # Wait for AW valid (address channel accepted independently)
            if self.dut.axi_awvalid_o.value == 1 and self.dut.axi_awready_i.value == 0:
                aw_addr = int(self.dut.axi_awaddr_o.value)
                # Sample burst length (default 0 for AXI4-Lite backward compat)
                awlen = int(getattr(self.dut, "axi_awlen_o", 0))
                nbeats = awlen + 1
                self.dut.axi_awready_i.value = 1
                self.logger.debug(
                    f"AXI_WRITE: addr=0x{aw_addr:08x} awlen={awlen} nbeats={nbeats}"
                )

                # De-assert awready next cycle
                await RisingEdge(self.dut.clk_i)
                self.dut.axi_awready_i.value = 0

                # Consume nbeats W beats (stop early when wlast seen)
                for beat in range(nbeats):
                    # Wait for wvalid to be asserted at a rising-clock-edge boundary.
                    # Always consume a rising edge before sampling wdata/wlast so that
                    # Verilator has fully evaluated the RTL (including the combinational
                    # axi_wdata_o = wb_buf_q[axi_word_q] update from the previous beat's
                    # axi_word_q increment) before we latch the data.  If we sampled
                    # wdata without this await, the BFM would read the pre-edge value of
                    # axi_word_q (still pointing at the previous word) and capture stale
                    # data — silently wrong when words share the same value, fatally wrong
                    # when only the last word carries the CPU's store data.
                    timeout_count = 0
                    while True:
                        await RisingEdge(self.dut.clk_i)
                        if self.dut.axi_wvalid_o.value == 1:
                            break
                        timeout_count += 1
                        if timeout_count >= self.AXI_TIMEOUT_CYCLES:
                            raise TimeoutError(
                                f"AXI write W-channel timeout at beat {beat}: master did not "
                                f"assert axi_wvalid after {self.AXI_TIMEOUT_CYCLES} cycles "
                                f"(addr=0x{aw_addr:08x}, method=axi_write_handler)"
                            )

                    w_data = int(self.dut.axi_wdata_o.value)
                    w_strb = int(self.dut.axi_wstrb_o.value)
                    # wlast: default 1 so single-beat (AXI4-Lite) still terminates
                    wlast = int(getattr(self.dut, "axi_wlast_o", 1))

                    # Accept W beat — byte-strobe aware merge
                    self.dut.axi_wready_i.value = 1
                    beat_addr = (aw_addr & 0xFFFFFFFC) + beat * 4

                    old_data = self.read_word(beat_addr)
                    merged_data = 0
                    for byte_idx in range(4):
                        if w_strb & (1 << byte_idx):
                            byte_val = (w_data >> (byte_idx * 8)) & 0xFF
                        else:
                            byte_val = (old_data >> (byte_idx * 8)) & 0xFF
                        merged_data |= byte_val << (byte_idx * 8)
                    self.write_word(beat_addr, merged_data)

                    await RisingEdge(self.dut.clk_i)
                    self.dut.axi_wready_i.value = 0

                    if wlast:
                        break  # RTL asserted wlast early (or single-beat burst)

                # ONE B response per burst
                self.dut.axi_bvalid_i.value = 1
                self.dut.axi_bresp_i.value = 0  # OKAY response

                # Wait for master to accept response (bready) with timeout
                timeout_count = 0
                while self.dut.axi_bready_o.value == 0:
                    timeout_count += 1
                    if timeout_count >= self.AXI_TIMEOUT_CYCLES:
                        self.dut.axi_bvalid_i.value = 0
                        raise TimeoutError(
                            f"AXI write response handshake timeout: master did not assert "
                            f"axi_bready after {self.AXI_TIMEOUT_CYCLES} cycles "
                            f"(addr=0x{aw_addr:08x}, method=axi_write_handler)"
                        )
                    await RisingEdge(self.dut.clk_i)

                # De-assert bvalid on next cycle
                await RisingEdge(self.dut.clk_i)
                self.dut.axi_bvalid_i.value = 0
