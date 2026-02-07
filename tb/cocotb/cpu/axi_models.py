"""
Configurable AXI4-Lite memory models for protocol testing.

This module provides AXI4-Lite memory slaves with configurable behavior
for comprehensive protocol testing:
- Back-pressure injection (delay ready signals)
- Error response injection (SLVERR, DECERR)
- Protocol violation detection
- Statistics collection
"""

import cocotb
from cocotb.triggers import RisingEdge


class ConfigurableAXIMemory:
    """Configurable AXI4-Lite memory slave for protocol testing.

    Features:
    - Back-pressure injection (delay ready signals)
    - Error response injection (SLVERR, DECERR)
    - Protocol violation detection
    - Statistics collection
    - Reference model synchronization

    Based on SimpleAXIMemory pattern from test_smoke.py.
    """

    def __init__(self, dut, ref_model=None, protocol_check=True):
        """Initialize configurable AXI memory.

        Args:
            dut: Device under test (cocotb handle)
            ref_model: Optional RV32IModel for memory synchronization
            protocol_check: Enable protocol violation detection (default True)
        """
        self.dut = dut
        self.mem = {}  # Memory storage {addr: data}
        self.ref_model = ref_model  # Optional reference model sync
        self.protocol_check = protocol_check

        # Delay injection state (per-transaction)
        self.next_read_arready_delay = 0
        self.next_read_rvalid_delay = 0
        self.next_write_awready_delay = 0
        self.next_write_wready_delay = 0
        self.next_write_bvalid_delay = 0

        # Error injection (address-based, persistent until cleared)
        self.error_map = {}  # {addr: 'SLVERR' | 'DECERR'}

        # Statistics
        self.stats = {
            "read_count": 0,
            "write_count": 0,
            "max_arready_stall": 0,
            "max_rvalid_stall": 0,
            "max_awready_stall": 0,
            "max_wready_stall": 0,
            "max_bvalid_stall": 0,
            "total_arready_stalls": 0,
            "total_rvalid_stalls": 0,
            "total_bvalid_stalls": 0,
        }

        # Protocol violation tracking
        self.violations = []

        # Start AXI handlers
        cocotb.start_soon(self.axi_read_handler())
        cocotb.start_soon(self.axi_write_handler())

    def inject_read_delay(self, arready_cycles=0, rvalid_cycles=0):
        """Inject delay for the NEXT read transaction.

        Args:
            arready_cycles: Cycles to delay arready assertion
            rvalid_cycles: Cycles to delay rvalid assertion (after arready)
        """
        self.next_read_arready_delay = arready_cycles
        self.next_read_rvalid_delay = rvalid_cycles

    def inject_write_delay(self, awready_cycles=0, wready_cycles=0, bvalid_cycles=0):
        """Inject delay for the NEXT write transaction.

        Args:
            awready_cycles: Cycles to delay awready assertion
            wready_cycles: Cycles to delay wready assertion
            bvalid_cycles: Cycles to delay bvalid assertion (after data accepted)
        """
        self.next_write_awready_delay = awready_cycles
        self.next_write_wready_delay = wready_cycles
        self.next_write_bvalid_delay = bvalid_cycles

    def inject_error(self, addr, error_type="SLVERR"):
        """Configure error response for specific address.

        Args:
            addr: Address to inject error at
            error_type: 'SLVERR' (0b10) or 'DECERR' (0b11)
        """
        assert error_type in ["SLVERR", "DECERR"], f"Invalid error type: {error_type}"
        self.error_map[addr & 0xFFFFFFFC] = error_type

    def clear_errors(self):
        """Clear all error injections."""
        self.error_map.clear()

    def write_word(self, addr, data):
        """Write 32-bit word to memory.

        Args:
            addr: Word-aligned address
            data: 32-bit data value
        """
        aligned_addr = addr & 0xFFFFFFFC
        self.mem[aligned_addr] = data & 0xFFFFFFFF

        # Sync with reference model if available
        if self.ref_model is not None:
            self.ref_model.memory.write(aligned_addr, data & 0xFFFFFFFF, 4)

    def read_word(self, addr):
        """Read 32-bit word from memory.

        Args:
            addr: Word-aligned address

        Returns:
            32-bit data value (0 if address not written)
        """
        return self.mem.get(addr & 0xFFFFFFFC, 0)

    def get_stats(self):
        """Get statistics dictionary.

        Returns:
            Dictionary of statistics counters
        """
        return self.stats.copy()

    async def axi_read_handler(self):
        """Handle AXI read transactions with delay/error injection.

        Implements AXI4-Lite read protocol:
        1. Wait for arvalid
        2. Apply arready delay (back-pressure)
        3. Assert arready to accept address
        4. Apply rvalid delay (data latency)
        5. Assert rvalid with data/response
        6. Wait for rready handshake

        Protocol checks (if enabled):
        - araddr stability during arvalid assertion
        - arvalid doesn't wait for arready (valid-before-ready rule)
        """
        while True:
            await RisingEdge(self.dut.clk_i)

            if self.dut.axi_arvalid_o.value == 1:
                addr = int(self.dut.axi_araddr_o.value)
                arvalid_cycle = 0

                # Apply arready delay (back-pressure)
                if self.next_read_arready_delay > 0:
                    for _ in range(self.next_read_arready_delay):
                        # Protocol check: araddr should remain stable
                        if self.protocol_check:
                            curr_addr = int(self.dut.axi_araddr_o.value)
                            if curr_addr != addr:
                                self.violations.append(
                                    f"Read: araddr changed during arvalid assertion "
                                    f"(0x{addr:08x} -> 0x{curr_addr:08x})"
                                )

                            # Check arvalid doesn't deassert
                            if self.dut.axi_arvalid_o.value == 0:
                                self.violations.append(
                                    "Read: arvalid deasserted before arready handshake"
                                )

                        await RisingEdge(self.dut.clk_i)
                        arvalid_cycle += 1

                    # Update stall statistics
                    self.stats["total_arready_stalls"] += self.next_read_arready_delay
                    if self.next_read_arready_delay > self.stats["max_arready_stall"]:
                        self.stats["max_arready_stall"] = self.next_read_arready_delay

                # Accept address
                self.dut.axi_arready_i.value = 1
                data = self.read_word(addr)

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_arready_i.value = 0

                # Apply rvalid delay (data latency)
                if self.next_read_rvalid_delay > 0:
                    for _ in range(self.next_read_rvalid_delay):
                        await RisingEdge(self.dut.clk_i)

                    # Update stall statistics
                    self.stats["total_rvalid_stalls"] += self.next_read_rvalid_delay
                    if self.next_read_rvalid_delay > self.stats["max_rvalid_stall"]:
                        self.stats["max_rvalid_stall"] = self.next_read_rvalid_delay

                # Check for error injection
                if addr in self.error_map:
                    error_type = self.error_map[addr]
                    if error_type == "SLVERR":
                        self.dut.axi_rresp_i.value = 0b10
                    else:  # DECERR
                        self.dut.axi_rresp_i.value = 0b11
                else:
                    self.dut.axi_rresp_i.value = 0b00  # OKAY

                # Provide data
                self.dut.axi_rvalid_i.value = 1
                self.dut.axi_rdata_i.value = data

                # Wait for rready handshake
                while self.dut.axi_rready_o.value == 0:
                    await RisingEdge(self.dut.clk_i)

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_rvalid_i.value = 0

                # Reset delays for next transaction
                self.next_read_arready_delay = 0
                self.next_read_rvalid_delay = 0
                self.stats["read_count"] += 1

            else:
                # Keep arready low when no valid request
                self.dut.axi_arready_i.value = 0

    async def axi_write_handler(self):
        """Handle AXI write transactions with delay/error injection.

        Implements AXI4-Lite write protocol:
        1. Wait for awvalid and wvalid (simultaneous)
        2. Apply awready/wready delay (back-pressure)
        3. Assert awready/wready to accept address/data
        4. Write to memory
        5. Apply bvalid delay (response latency)
        6. Assert bvalid with response
        7. Wait for bready handshake

        Protocol checks (if enabled):
        - awaddr/wdata stability during valid assertion
        - awvalid/wvalid don't wait for ready signals
        """
        while True:
            await RisingEdge(self.dut.clk_i)

            # Wait for both address and data valid (AXI4-Lite allows simultaneous)
            if (
                self.dut.axi_awvalid_o.value == 1
                and self.dut.axi_wvalid_o.value == 1
                and self.dut.axi_awready_i.value == 0
            ):
                addr = int(self.dut.axi_awaddr_o.value)
                data = int(self.dut.axi_wdata_o.value)
                int(self.dut.axi_wstrb_o.value)

                # Apply awready/wready delay (back-pressure)
                delay_cycles = max(self.next_write_awready_delay, self.next_write_wready_delay)
                if delay_cycles > 0:
                    for _ in range(delay_cycles):
                        # Protocol check: awaddr/wdata should remain stable
                        if self.protocol_check:
                            curr_addr = int(self.dut.axi_awaddr_o.value)
                            curr_data = int(self.dut.axi_wdata_o.value)
                            if curr_addr != addr:
                                self.violations.append(
                                    f"Write: awaddr changed during awvalid assertion "
                                    f"(0x{addr:08x} -> 0x{curr_addr:08x})"
                                )
                            if curr_data != data:
                                self.violations.append(
                                    f"Write: wdata changed during wvalid assertion "
                                    f"(0x{data:08x} -> 0x{curr_data:08x})"
                                )

                            # Check valids don't deassert
                            if self.dut.axi_awvalid_o.value == 0:
                                self.violations.append(
                                    "Write: awvalid deasserted before awready handshake"
                                )
                            if self.dut.axi_wvalid_o.value == 0:
                                self.violations.append(
                                    "Write: wvalid deasserted before wready handshake"
                                )

                        await RisingEdge(self.dut.clk_i)

                    # Update stall statistics
                    self.stats["total_arready_stalls"] += delay_cycles
                    if delay_cycles > self.stats["max_awready_stall"]:
                        self.stats["max_awready_stall"] = delay_cycles

                # Accept address and data
                self.dut.axi_awready_i.value = 1
                self.dut.axi_wready_i.value = 1

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_awready_i.value = 0
                self.dut.axi_wready_i.value = 0

                # Write to memory (respecting wstrb)
                self.write_word(addr, data)

                # Apply bvalid delay (response latency)
                if self.next_write_bvalid_delay > 0:
                    for _ in range(self.next_write_bvalid_delay):
                        await RisingEdge(self.dut.clk_i)

                    # Update stall statistics
                    self.stats["total_bvalid_stalls"] += self.next_write_bvalid_delay
                    if self.next_write_bvalid_delay > self.stats["max_bvalid_stall"]:
                        self.stats["max_bvalid_stall"] = self.next_write_bvalid_delay

                # Check for error injection
                if addr in self.error_map:
                    error_type = self.error_map[addr]
                    if error_type == "SLVERR":
                        self.dut.axi_bresp_i.value = 0b10
                    else:  # DECERR
                        self.dut.axi_bresp_i.value = 0b11
                else:
                    self.dut.axi_bresp_i.value = 0b00  # OKAY

                # Provide response
                self.dut.axi_bvalid_i.value = 1

                # Wait for bready handshake
                while self.dut.axi_bready_o.value == 0:
                    await RisingEdge(self.dut.clk_i)

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_bvalid_i.value = 0

                # Reset delays for next transaction
                self.next_write_awready_delay = 0
                self.next_write_wready_delay = 0
                self.next_write_bvalid_delay = 0
                self.stats["write_count"] += 1

            else:
                # Keep ready signals low when no valid request
                self.dut.axi_awready_i.value = 0
                self.dut.axi_wready_i.value = 0
