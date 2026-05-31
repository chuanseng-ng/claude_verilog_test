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
        self.error_map = {}        # {addr: 'SLVERR'|'DECERR'} — affects both R and W
        self.write_error_map = {}  # {addr: 'SLVERR'|'DECERR'} — affects W only

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
            "total_awready_stalls": 0,
            "total_wready_stalls": 0,
            "total_bvalid_stalls": 0,
        }

        # Protocol violation tracking
        self.violations = []

        # Start AXI handlers (keep handles so callers can cancel on teardown)
        self._read_task = cocotb.start_soon(self.axi_read_handler())
        self._write_task = cocotb.start_soon(self.axi_write_handler())

    def stop(self):
        """Cancel background handler tasks (call at end of each test)."""
        self._read_task.cancel()
        self._write_task.cancel()

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

    def inject_write_error(self, addr, error_type="SLVERR"):
        """Configure error response for write transactions only (not reads).

        Use this when the address will also be read (e.g. write-allocate) to
        avoid unintended SLVERR on the read that would prevent dirty-line creation.

        Args:
            addr: Address to inject write error at
            error_type: 'SLVERR' (0b10) or 'DECERR' (0b11)
        """
        assert error_type in ["SLVERR", "DECERR"], f"Invalid error type: {error_type}"
        self.write_error_map[addr & 0xFFFFFFFC] = error_type

    def clear_errors(self):
        """Clear all error injections."""
        self.error_map.clear()
        self.write_error_map.clear()

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

        Implements AXI4 burst read protocol:
        1. Wait for arvalid
        2. Apply arready delay (back-pressure) + 1-cycle stabilization
        3. Assert arready to accept address; sample arlen (default 0)
        4. Apply rvalid delay (data latency) before first beat
        5. For each of arlen+1 beats:
           - assert rvalid + rdata + rresp (per-beat error injection)
           - assert rlast on the final beat
           - wait for rready handshake
        6. Deassert rvalid + rlast; increment read_count once per burst

        Note: A 1-cycle stabilization delay is always inserted before asserting
        arready.  This prevents a race condition where the AXI arbiter switches
        from an IF fetch to a MEM load between the cycle Python samples araddr
        and the cycle arready takes effect in RTL.

        Protocol checks (if enabled):
        - araddr stability during arvalid assertion
        - arvalid doesn't wait for arready (valid-before-ready rule)
        """
        while True:
            await RisingEdge(self.dut.clk_i)

            if self.dut.axi_arvalid_o.value == 1:
                # Wait 1 cycle for the pipeline/arbiter to settle before
                # reading the address.  Without this, the arbiter can switch
                # requestors (IF→MEM) between the cycle we sample araddr and
                # the cycle arready takes effect, causing wrong data.
                await RisingEdge(self.dut.clk_i)

                # Re-check arvalid after stabilization
                if self.dut.axi_arvalid_o.value != 1:
                    self.dut.axi_arready_i.value = 0
                    continue

                addr = int(self.dut.axi_araddr_o.value)
                # Sample burst length (default 0 for AXI4-Lite backward compat)
                arlen = int(getattr(self.dut, "axi_arlen_o", 0))
                nbeats = arlen + 1
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

                await RisingEdge(self.dut.clk_i)
                self.dut.axi_arready_i.value = 0

                # Apply rvalid delay (data latency) before first beat
                if self.next_read_rvalid_delay > 0:
                    for _ in range(self.next_read_rvalid_delay):
                        await RisingEdge(self.dut.clk_i)

                    # Update stall statistics
                    self.stats["total_rvalid_stalls"] += self.next_read_rvalid_delay
                    if self.next_read_rvalid_delay > self.stats["max_rvalid_stall"]:
                        self.stats["max_rvalid_stall"] = self.next_read_rvalid_delay

                # Drive nbeats of R data; per-beat error injection at addr+4*beat
                for beat in range(nbeats):
                    beat_addr = (addr & 0xFFFFFFFC) + beat * 4
                    data = self.read_word(beat_addr)
                    is_last = (beat == nbeats - 1)

                    # Per-beat error injection (check error_map at beat_addr)
                    if beat_addr in self.error_map:
                        error_type = self.error_map[beat_addr]
                        if error_type == "SLVERR":
                            self.dut.axi_rresp_i.value = 0b10
                        else:  # DECERR
                            self.dut.axi_rresp_i.value = 0b11
                    else:
                        self.dut.axi_rresp_i.value = 0b00  # OKAY

                    self.dut.axi_rvalid_i.value = 1
                    self.dut.axi_rdata_i.value = data
                    if hasattr(self.dut, "axi_rlast_i"):
                        self.dut.axi_rlast_i.value = 1 if is_last else 0

                    # Wait for rready handshake
                    while self.dut.axi_rready_o.value == 0:
                        await RisingEdge(self.dut.clk_i)

                    await RisingEdge(self.dut.clk_i)

                # Deassert rvalid + rlast after final beat accepted
                self.dut.axi_rvalid_i.value = 0
                if hasattr(self.dut, "axi_rlast_i"):
                    self.dut.axi_rlast_i.value = 0

                # Reset delays for next transaction; count once per burst
                self.next_read_arready_delay = 0
                self.next_read_rvalid_delay = 0
                self.stats["read_count"] += 1

            else:
                # Keep arready low when no valid request
                self.dut.axi_arready_i.value = 0

    async def axi_write_handler(self):
        """Handle AXI write transactions with delay/error injection.

        Implements AXI4 burst write protocol:
        1. Wait for awvalid (address phase, independent of wvalid)
        2. Apply awready delay (back-pressure) and accept AW
        3. Sample awlen (default 0); loop nbeats W beats:
           - wait for wvalid, apply wready delay, accept W data with wstrb merge
           - break early when wlast seen (default 1 for single-beat compat)
        4. Apply bvalid delay; assert ONE bvalid response; wait bready

        Protocol checks (if enabled):
        - awaddr/wdata stability during valid assertion
        - awvalid/wvalid don't wait for ready signals
        """
        while True:
            await RisingEdge(self.dut.clk_i)

            # Wait for AW valid (address channel — independent of W channel for burst)
            if (
                self.dut.axi_awvalid_o.value == 1
                and self.dut.axi_awready_i.value == 0
            ):
                addr = int(self.dut.axi_awaddr_o.value)
                # Sample burst length (default 0 for AXI4-Lite backward compat)
                awlen = int(getattr(self.dut, "axi_awlen_o", 0))
                nbeats = awlen + 1

                # Apply awready delay (back-pressure on address channel only)
                aw_delay = self.next_write_awready_delay
                if aw_delay > 0:
                    for _ in range(aw_delay):
                        if self.protocol_check:
                            curr_addr = int(self.dut.axi_awaddr_o.value)
                            if curr_addr != addr:
                                self.violations.append(
                                    f"Write: awaddr changed during awvalid assertion "
                                    f"(0x{addr:08x} -> 0x{curr_addr:08x})"
                                )
                            if self.dut.axi_awvalid_o.value == 0:
                                self.violations.append(
                                    "Write: awvalid deasserted before awready handshake"
                                )
                        await RisingEdge(self.dut.clk_i)

                    self.stats["total_awready_stalls"] += aw_delay
                    if aw_delay > self.stats["max_awready_stall"]:
                        self.stats["max_awready_stall"] = aw_delay

                # Accept address
                self.dut.axi_awready_i.value = 1
                await RisingEdge(self.dut.clk_i)
                self.dut.axi_awready_i.value = 0

                # Consume nbeats of W channel (stop early on wlast)
                for beat in range(nbeats):
                    # Wait for wvalid to be asserted at a rising-clock-edge boundary.
                    # Always consume a rising edge before sampling wdata/wlast so that
                    # Verilator has fully evaluated the RTL (including the combinational
                    # axi_wdata_o = wb_buf_q[axi_word_q] update from the previous beat's
                    # axi_word_q increment) before we latch the data.
                    while True:
                        await RisingEdge(self.dut.clk_i)
                        if self.dut.axi_wvalid_o.value == 1:
                            break

                    data = int(self.dut.axi_wdata_o.value)
                    wstrb = int(self.dut.axi_wstrb_o.value)
                    # wlast: default 1 so single-beat (AXI4-Lite) still terminates
                    wlast = int(getattr(self.dut, "axi_wlast_o", 1))

                    # Apply wready delay (back-pressure on data channel)
                    w_delay = self.next_write_wready_delay
                    if w_delay > 0:
                        for _ in range(w_delay):
                            if self.protocol_check:
                                curr_data = int(self.dut.axi_wdata_o.value)
                                if curr_data != data:
                                    self.violations.append(
                                        f"Write: wdata changed during wvalid assertion "
                                        f"(0x{data:08x} -> 0x{curr_data:08x})"
                                    )
                                if self.dut.axi_wvalid_o.value == 0:
                                    self.violations.append(
                                        "Write: wvalid deasserted before wready handshake"
                                    )
                            await RisingEdge(self.dut.clk_i)

                        self.stats["total_wready_stalls"] += w_delay
                        if w_delay > self.stats["max_wready_stall"]:
                            self.stats["max_wready_stall"] = w_delay

                    # Accept W beat — byte-strobe aware merge
                    self.dut.axi_wready_i.value = 1
                    beat_addr = (addr & 0xFFFFFFFC) + beat * 4
                    current_word = self.mem.get(beat_addr, 0)
                    merged_word = current_word
                    for byte_idx in range(4):
                        if wstrb & (1 << byte_idx):
                            byte_val = (data >> (byte_idx * 8)) & 0xFF
                            byte_mask = 0xFF << (byte_idx * 8)
                            merged_word = (merged_word & ~byte_mask) | (byte_val << (byte_idx * 8))
                    self.write_word(beat_addr, merged_word)

                    await RisingEdge(self.dut.clk_i)
                    self.dut.axi_wready_i.value = 0

                    if wlast:
                        break  # RTL asserted wlast early (or single-beat burst)

                # Update per-beat wready stall stats
                self.stats["total_wready_stalls"] += 0  # already tracked in loop

                # Apply bvalid delay (response latency)
                if self.next_write_bvalid_delay > 0:
                    for _ in range(self.next_write_bvalid_delay):
                        await RisingEdge(self.dut.clk_i)

                    self.stats["total_bvalid_stalls"] += self.next_write_bvalid_delay
                    if self.next_write_bvalid_delay > self.stats["max_bvalid_stall"]:
                        self.stats["max_bvalid_stall"] = self.next_write_bvalid_delay

                # Check for error injection (error_map affects both R+W; write_error_map W only)
                aligned_addr = addr & 0xFFFFFFFC
                write_err = self.error_map.get(aligned_addr) or self.write_error_map.get(aligned_addr)
                if write_err == "SLVERR":
                    self.dut.axi_bresp_i.value = 0b10
                elif write_err == "DECERR":
                    self.dut.axi_bresp_i.value = 0b11
                else:
                    self.dut.axi_bresp_i.value = 0b00  # OKAY

                # ONE B response per burst
                self.dut.axi_bvalid_i.value = 1

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
