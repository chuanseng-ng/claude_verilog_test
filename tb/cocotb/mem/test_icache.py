"""
I-Cache unit tests — Phase 3
DUT: rv32i_icache

Tests:
  - Basic hit (1-cycle response after fill)
  - Basic miss (stall until AXI refill completes)
  - Conflict miss (two addresses mapping to same index)
  - Sequential fetch (16 B line → 4 instructions, 1 miss then 3 hits)
  - FENCE.I invalidation (cache miss forced after ic_invalidate_i pulse)
  - Boundary test (last set, wrap-around addresses)

AXI slave modelled directly in Python (no rv32i_cpu_top).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

# Cache geometry (must match rv32i_cache_pkg.sv)
LINE_WORDS = 4  # 4 words per 16-byte line
AXI_RESP_OK = 0b00


# ---------------------------------------------------------------------------
# Minimal AXI4-Lite read-only slave — handles I-cache refill beats
# ---------------------------------------------------------------------------


class SimpleICacheAXIMem:
    """
    Simple read-only AXI4-Lite slave for I-cache refill.

    Keeps a word-addressed dictionary as backing store.
    Configurable fixed latency (arready_delay + rvalid_delay cycles).
    """

    def __init__(self, dut, latency: int = 0):
        self.dut = dut
        self.latency = latency  # cycles before asserting arready/rvalid
        self.mem: dict[int, int] = {}  # word_addr → 32-bit word
        self._task = cocotb.start_soon(self._handler())

    def write_word(self, byte_addr: int, data: int):
        self.mem[byte_addr >> 2] = data & 0xFFFF_FFFF

    def stop(self):
        self._task.cancel()

    async def _handler(self):
        dut = self.dut
        while True:
            # Wait for AR valid
            while not dut.axi_arvalid_o.value:
                await RisingEdge(dut.clk)

            # Optional latency before accepting the address
            if self.latency:
                await ClockCycles(dut.clk, self.latency)

            # Assert arready; sample address AFTER the handshake edge so we
            # capture the address that the DUT actually registered (i.e. the
            # value stable when both ARVALID and ARREADY are high together).
            dut.axi_arready_i.value = 1
            await RisingEdge(dut.clk)
            # Both ARVALID and ARREADY were high on the previous edge — the
            # address is now stable; sample it here.
            addr = int(dut.axi_araddr_o.value)
            dut.axi_arready_i.value = 0

            # Send read data
            if self.latency:
                await ClockCycles(dut.clk, self.latency)

            word_addr = addr >> 2
            data = self.mem.get(word_addr, 0xDEAD_BEEF)

            dut.axi_rvalid_i.value = 1
            dut.axi_rdata_i.value = data
            dut.axi_rresp_i.value = AXI_RESP_OK

            await RisingEdge(dut.clk)
            while not dut.axi_rready_o.value:
                await RisingEdge(dut.clk)

            dut.axi_rvalid_i.value = 0
            dut.axi_rdata_i.value = 0


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------


async def _reset(dut, cycles: int = 4):
    """Assert reset for `cycles` clock cycles then release."""
    dut.rst_n.value = 0
    dut.ic_valid_i.value = 0
    dut.ic_addr_i.value = 0
    dut.ic_invalidate_i.value = 0
    dut.axi_arready_i.value = 0
    dut.axi_rvalid_i.value = 0
    dut.axi_rdata_i.value = 0
    dut.axi_rresp_i.value = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _fetch(dut, addr: int, timeout: int = 64) -> int:
    """
    Assert ic_valid_i + ic_addr_i and wait until ic_stall_o deasserts
    (cache hit).  Returns ic_rdata_o.  Raises on timeout.
    """
    dut.ic_valid_i.value = 1
    dut.ic_addr_i.value = addr
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        if not dut.ic_stall_o.value:
            data = int(dut.ic_rdata_o.value)
            dut.ic_valid_i.value = 0
            return data
    raise TimeoutError(f"ic_stall_o never deasserted for addr={addr:#010x}")


def _line_base(addr: int) -> int:
    """Return 16-byte aligned base of the line containing addr."""
    return addr & ~0xF


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@cocotb.test()
async def test_basic_miss_then_hit(dut):
    """First access (miss) stalls until AXI refill, then same addr hits."""
    dut._log.info("=== test_basic_miss_then_hit ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = SimpleICacheAXIMem(dut, latency=0)
    BASE = 0x0000_0000
    for w in range(LINE_WORDS):
        mem.write_word(BASE + w * 4, 0x0000_0013 + w)  # distinct NOPs

    await _reset(dut)

    # First access → miss
    data0 = await _fetch(dut, BASE)
    assert data0 == 0x0000_0013, f"Got {data0:#010x}"
    dut._log.info(f"Miss fill OK, data={data0:#010x}")

    # Second access to same address → hit.
    # After _fetch() returns at CS_TAG_CHECK, the FSM still needs one edge to
    # return to CS_IDLE, then two more edges for CS_IDLE→CS_SRAM_LATCH→CS_TAG_CHECK.
    # Stall deasserts (hit=1) at CS_TAG_CHECK, 3 edges after ic_valid_i is reasserted.
    dut.ic_valid_i.value = 1
    dut.ic_addr_i.value = BASE
    await RisingEdge(dut.clk)  # CS_TAG_CHECK → CS_IDLE (stall=1: ic_valid_i=1 in IDLE)
    await RisingEdge(dut.clk)  # CS_IDLE → CS_SRAM_LATCH (stall=1)
    await RisingEdge(dut.clk)  # CS_SRAM_LATCH → CS_TAG_CHECK (hit: stall=0)
    assert not dut.ic_stall_o.value, "Expected cache hit (no stall) on second access"
    data1 = int(dut.ic_rdata_o.value)
    dut.ic_valid_i.value = 0
    assert data1 == 0x0000_0013, f"Hit returned wrong data: {data1:#010x}"
    dut._log.info("Hit OK")

    mem.stop()


@cocotb.test()
async def test_line_fill_all_words(dut):
    """
    Fetch all 4 words of a 16-byte cache line.
    After the first (miss) fill, the remaining 3 words hit in 1 cycle each.
    """
    dut._log.info("=== test_line_fill_all_words ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = SimpleICacheAXIMem(dut, latency=0)
    BASE = 0x0000_1000
    words = [0xDEAD_0001, 0xDEAD_0002, 0xDEAD_0003, 0xDEAD_0004]
    for w, val in enumerate(words):
        mem.write_word(BASE + w * 4, val)

    await _reset(dut)

    results = []
    for w in range(LINE_WORDS):
        data = await _fetch(dut, BASE + w * 4)
        results.append(data)

    for w, (got, expected) in enumerate(zip(results, words)):
        assert got == expected, f"Word[{w}]: got {got:#010x}, expected {expected:#010x}"

    dut._log.info(f"All 4 words correct: {[hex(v) for v in results]}")
    mem.stop()


@cocotb.test()
async def test_conflict_miss(dut):
    """
    Two addresses that map to the same cache set cause conflict misses.

    The cache is 256-set direct-mapped with 16-byte lines → index = addr[11:4].
    Addresses 0x0000 and 0x1000 both map to index 0.  Accessing them
    alternately forces a miss + refill on every access.
    """
    dut._log.info("=== test_conflict_miss ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = SimpleICacheAXIMem(dut, latency=0)
    # Two lines that alias to index 0 (addr[11:4] = 0)
    ADDR_A = 0x0000_0000  # tag=0,  index=0
    ADDR_B = 0x0001_0000  # tag=1,  index=0

    mem.write_word(ADDR_A, 0xAAAA_AAAA)
    for w in range(1, LINE_WORDS):
        mem.write_word(ADDR_A + w * 4, 0)

    mem.write_word(ADDR_B, 0xBBBB_BBBB)
    for w in range(1, LINE_WORDS):
        mem.write_word(ADDR_B + w * 4, 0)

    await _reset(dut)

    # Access A (miss fill)
    a0 = await _fetch(dut, ADDR_A)
    assert a0 == 0xAAAA_AAAA, f"Got {a0:#010x}"

    # Access B (conflict miss — evicts A)
    b0 = await _fetch(dut, ADDR_B)
    assert b0 == 0xBBBB_BBBB, f"Got {b0:#010x}"

    # Re-access A (conflict miss again — evicts B)
    a1 = await _fetch(dut, ADDR_A)
    assert a1 == 0xAAAA_AAAA, f"Got {a1:#010x}"

    dut._log.info("Conflict miss sequence: PASS")
    mem.stop()


@cocotb.test()
async def test_axi_latency(dut):
    """Verify cache works correctly with non-zero AXI latency (3-cycle stall)."""
    dut._log.info("=== test_axi_latency ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = SimpleICacheAXIMem(dut, latency=3)
    BASE = 0x0000_2000
    mem.write_word(BASE, 0xCAFE_BABE)
    for w in range(1, LINE_WORDS):
        mem.write_word(BASE + w * 4, 0)

    await _reset(dut)

    data = await _fetch(dut, BASE, timeout=128)
    assert data == 0xCAFE_BABE, f"Got {data:#010x}"
    dut._log.info(f"Latency=3 fill OK: {data:#010x}")

    mem.stop()


@cocotb.test()
async def test_fence_i_invalidation(dut):
    """
    FENCE.I: after ic_invalidate_i pulse, subsequent access must miss.

    Sequence:
      1. Fill the cache line for ADDR.
      2. Pulse ic_invalidate_i for 1 cycle.
      3. Verify the next access stalls again (triggers another miss).
    """
    dut._log.info("=== test_fence_i_invalidation ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = SimpleICacheAXIMem(dut, latency=0)
    BASE = 0x0000_3000
    mem.write_word(BASE, 0x1234_5678)
    for w in range(1, LINE_WORDS):
        mem.write_word(BASE + w * 4, 0)

    await _reset(dut)

    # Initial fill
    data = await _fetch(dut, BASE)
    assert data == 0x1234_5678

    # Verify hit.
    # After _fetch() returns at CS_TAG_CHECK, the FSM still needs one edge to
    # return to CS_IDLE, then two more edges for CS_IDLE→CS_SRAM_LATCH→CS_TAG_CHECK.
    # Stall deasserts (hit=1) at CS_TAG_CHECK, 3 edges after ic_valid_i is reasserted.
    dut.ic_valid_i.value = 1
    dut.ic_addr_i.value = BASE
    await RisingEdge(dut.clk)  # CS_TAG_CHECK → CS_IDLE (stall=1: ic_valid_i=1 in IDLE)
    await RisingEdge(dut.clk)  # CS_IDLE → CS_SRAM_LATCH (stall=1)
    await RisingEdge(dut.clk)  # CS_SRAM_LATCH → CS_TAG_CHECK (hit: stall=0)
    assert not dut.ic_stall_o.value, "Expected hit before invalidation"
    dut.ic_valid_i.value = 0

    # FENCE.I invalidation pulse
    dut.ic_invalidate_i.value = 1
    await RisingEdge(dut.clk)
    dut.ic_invalidate_i.value = 0

    # Allow a couple of cycles for the invalidation to propagate
    await ClockCycles(dut.clk, 2)

    # Now the same address must miss (stall before returning data)
    miss_detected = False
    dut.ic_valid_i.value = 1
    dut.ic_addr_i.value = BASE
    for _ in range(4):  # check first few cycles for stall
        await RisingEdge(dut.clk)
        if dut.ic_stall_o.value:
            miss_detected = True
            break

    assert miss_detected, "Expected cache miss after ic_invalidate_i — stall not seen"

    # Wait for the re-fill to complete
    for _ in range(64):
        await RisingEdge(dut.clk)
        if not dut.ic_stall_o.value:
            break
    else:
        raise TimeoutError("Stall never deasserted after FENCE.I re-fill")

    dut.ic_valid_i.value = 0
    dut._log.info("FENCE.I invalidation + re-fill: PASS")
    mem.stop()


@cocotb.test()
async def test_no_access_when_invalid(dut):
    """ic_valid_i=0 must not trigger a fetch or assert stall."""
    dut._log.info("=== test_no_access_when_invalid ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = SimpleICacheAXIMem(dut, latency=0)
    await _reset(dut)

    # Hold ic_valid_i=0 for several cycles, verify no stall and no AXI traffic
    dut.ic_valid_i.value = 0
    dut.ic_addr_i.value = 0x1234_5678
    for _ in range(8):
        await RisingEdge(dut.clk)
        assert not dut.ic_stall_o.value, "ic_stall_i asserted without ic_valid_i"
        assert not dut.axi_arvalid_o.value, "ic_axi_arvalid_o asserted without ic_valid_i"

    dut._log.info("No spurious fetch: PASS")
    mem.stop()


@cocotb.test()
async def test_boundary_high_set(dut):
    """Access the highest cache set (index=255, addr[11:4]=0xFF)."""
    dut._log.info("=== test_boundary_high_set ===")

    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    mem = SimpleICacheAXIMem(dut, latency=0)
    # index=255 → addr[11:4]=0xFF → addr = 0x?FF0..0xFFF
    BASE = 0x0000_0FF0
    mem.write_word(BASE, 0xFACE_CAFE)
    for w in range(1, LINE_WORDS):
        mem.write_word(BASE + w * 4, 0)

    await _reset(dut)

    data = await _fetch(dut, BASE)
    assert data == 0xFACE_CAFE, f"Got {data:#010x}"
    dut._log.info(f"High-set fill OK: {data:#010x}")

    mem.stop()
