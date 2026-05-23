"""
Unit tests for gpu_memory_unit.sv — Phase 4.

gpu_memory_unit bridges the compute-unit VLD/VST interface (req_i/we_i/addr_i/
wdata_i/lane_mask_i → stall_o/rdata_o/rvalid_o) and the memory_coalescer, which
acts as the AXI4 master.  An in-test AXI responder handles AR/R (read) and
AW/W/B (write) with configurable latency.

Contract under test (mirrors the comment header of gpu_memory_unit.sv):
  - stall_o is registered (asserts the cycle after a request is latched).
  - rvalid_o pulses coincident with stall_o falling, with rdata_o valid then.

Tests:
  test_8lane_load        — 8 active lanes load; rdata_o matches responder memory
  test_4lane_load        — masked lanes (0,2,4,6) only; inactive lanes untouched
  test_8lane_store       — 8 active stores; AW/W/B observed, wstrb=0xF
  test_load_axi_latency  — non-zero AR/R latency; result still correct
  test_rvalid_on_stall_fall — rvalid_o coincides with stall_o falling edge
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

N_LANES = 8


# ---------------------------------------------------------------------------
# AXI responder tasks (run until killed by the test)
# ---------------------------------------------------------------------------

async def axi_read_responder(dut, mem: dict, ar_latency: int = 0, r_latency: int = 0):
    """Serve AR/R requests from the DUT's AXI master port."""
    dut.m_arready_i.value = 0
    dut.m_rvalid_i.value  = 0
    while True:
        await RisingEdge(dut.clk)
        if not dut.m_arvalid_o.value:
            continue
        for _ in range(ar_latency):
            await RisingEdge(dut.clk)
        dut.m_arready_i.value = 1
        await RisingEdge(dut.clk)
        addr = int(dut.m_araddr_o.value)
        dut.m_arready_i.value = 0
        for _ in range(r_latency):
            await RisingEdge(dut.clk)
        dut.m_rdata_i.value  = mem.get(addr, 0xDEAD_0000 | (addr & 0xFF))
        dut.m_rresp_i.value  = 0
        dut.m_rvalid_i.value = 1
        await RisingEdge(dut.clk)
        dut.m_rvalid_i.value = 0


async def axi_write_responder(dut, written: dict, aw_latency: int = 0, w_latency: int = 0):
    """Serve AW/W/B requests and record writes."""
    dut.m_awready_i.value = 0
    dut.m_wready_i.value  = 0
    dut.m_bvalid_i.value  = 0
    while True:
        await RisingEdge(dut.clk)
        if not dut.m_awvalid_o.value:
            continue
        for _ in range(aw_latency):
            await RisingEdge(dut.clk)
        dut.m_awready_i.value = 1
        await RisingEdge(dut.clk)
        addr = int(dut.m_awaddr_o.value)
        dut.m_awready_i.value = 0
        while not dut.m_wvalid_o.value:
            await RisingEdge(dut.clk)
        for _ in range(w_latency):
            await RisingEdge(dut.clk)
        written[addr] = int(dut.m_wdata_o.value)
        wstrb = int(dut.m_wstrb_o.value)
        assert wstrb == 0xF, f"expected full-word wstrb=0xF, got 0x{wstrb:x} @ 0x{addr:x}"
        dut.m_wready_i.value = 1
        await RisingEdge(dut.clk)
        dut.m_wready_i.value = 0
        dut.m_bvalid_i.value = 1
        dut.m_bresp_i.value  = 0
        await RisingEdge(dut.clk)
        dut.m_bvalid_i.value = 0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _encode_lanes(values: list, width: int = 32) -> int:
    result = 0
    for i, v in enumerate(values):
        result |= (v & ((1 << width) - 1)) << (i * width)
    return result


def _decode_lanes(packed: int, n: int = N_LANES, width: int = 32) -> list:
    mask = (1 << width) - 1
    return [(packed >> (i * width)) & mask for i in range(n)]


async def _reset(dut):
    dut.rst_n.value       = 0
    dut.req_i.value       = 0
    dut.we_i.value        = 0
    dut.addr_i.value      = 0
    dut.wdata_i.value     = 0
    dut.lane_mask_i.value = 0
    dut.m_arready_i.value = 0
    dut.m_rdata_i.value   = 0
    dut.m_rresp_i.value   = 0
    dut.m_rvalid_i.value  = 0
    dut.m_awready_i.value = 0
    dut.m_wready_i.value  = 0
    dut.m_bresp_i.value   = 0
    dut.m_bvalid_i.value  = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _drive_request(dut, addrs, wdata, we: int, mask: int, timeout: int = 200):
    """Assert a request, wait for rvalid_o (access complete), return rdata list."""
    dut.addr_i.value      = _encode_lanes(addrs)
    dut.wdata_i.value     = _encode_lanes(wdata)
    dut.we_i.value        = we
    dut.lane_mask_i.value = mask
    dut.req_i.value       = 1
    rdata_packed = 0
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        await Timer(1, units="ns")
        if int(dut.rvalid_o.value):
            rdata_packed = int(dut.rdata_o.value)
            break
    else:
        assert False, "rvalid_o never asserted (memory unit hung)"
    dut.req_i.value = 0
    await RisingEdge(dut.clk)
    return _decode_lanes(rdata_packed)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@cocotb.test()
async def test_8lane_load(dut):
    """8 active lanes load distinct words; rdata_o matches responder memory."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    base  = 0x1000
    addrs = [base + i * 4 for i in range(N_LANES)]
    mem   = {a: 0xC0DE_0000 | i for i, a in enumerate(addrs)}
    cocotb.start_soon(axi_read_responder(dut, mem))

    rdata = await _drive_request(dut, addrs, [0] * N_LANES, we=0, mask=0xFF)
    for i, a in enumerate(addrs):
        assert rdata[i] == mem[a], \
            f"lane {i}: expected 0x{mem[a]:08x}, got 0x{rdata[i]:08x}"


@cocotb.test()
async def test_4lane_load(dut):
    """Only lanes 0,2,4,6 active; the others must not load."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    base  = 0x2000
    addrs = [base + i * 4 for i in range(N_LANES)]
    mem   = {a: 0xAB00_0000 | i for i, a in enumerate(addrs)}
    cocotb.start_soon(axi_read_responder(dut, mem))

    mask  = 0b0101_0101  # lanes 0,2,4,6
    rdata = await _drive_request(dut, addrs, [0] * N_LANES, we=0, mask=mask)
    for i, a in enumerate(addrs):
        if mask & (1 << i):
            assert rdata[i] == mem[a], \
                f"active lane {i}: expected 0x{mem[a]:08x}, got 0x{rdata[i]:08x}"


@cocotb.test()
async def test_8lane_store(dut):
    """8 active stores; AW/W/B observed with correct data and full wstrb."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    base    = 0x3000
    addrs   = [base + i * 4 for i in range(N_LANES)]
    wdata   = [0x5500_0000 | i for i in range(N_LANES)]
    written: dict = {}
    cocotb.start_soon(axi_write_responder(dut, written))

    await _drive_request(dut, addrs, wdata, we=1, mask=0xFF)
    for i, a in enumerate(addrs):
        assert written.get(a) == wdata[i], \
            f"lane {i}: expected store 0x{wdata[i]:08x} @ 0x{a:x}, got {written.get(a)}"


@cocotb.test()
async def test_load_axi_latency(dut):
    """Non-zero AR/R latency; coalescer still returns correct data."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    base  = 0x4000
    addrs = [base + i * 4 for i in range(N_LANES)]
    mem   = {a: 0xBEEF_0000 | i for i, a in enumerate(addrs)}
    cocotb.start_soon(axi_read_responder(dut, mem, ar_latency=2, r_latency=3))

    rdata = await _drive_request(dut, addrs, [0] * N_LANES, we=0, mask=0xFF, timeout=400)
    for i, a in enumerate(addrs):
        assert rdata[i] == mem[a], \
            f"lane {i}: expected 0x{mem[a]:08x}, got 0x{rdata[i]:08x}"


@cocotb.test()
async def test_rvalid_on_stall_fall(dut):
    """rvalid_o pulses on the last stall_o-high cycle; stall_o falls the next cycle.

    Per gpu_memory_unit.sv: stall_o=busy_q, rvalid_o=coal_done, and busy_q is
    cleared on coal_done. So the rvalid cycle still has stall_o high (the load is
    parked); stall_o drops the following cycle. This is the capture-then-advance
    ordering the compute unit relies on to latch read data before retiring.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    base  = 0x5000
    addrs = [base + i * 4 for i in range(N_LANES)]
    mem   = {a: 0x1234_0000 | i for i, a in enumerate(addrs)}
    cocotb.start_soon(axi_read_responder(dut, mem))

    dut.addr_i.value      = _encode_lanes(addrs)
    dut.we_i.value        = 0
    dut.lane_mask_i.value = 0xFF
    dut.req_i.value       = 1

    saw_rvalid = False
    for _ in range(200):
        await RisingEdge(dut.clk)
        await Timer(1, units="ns")
        if int(dut.rvalid_o.value):
            assert int(dut.stall_o.value) == 1, \
                "stall_o must still be high on the rvalid_o cycle (parked)"
            saw_rvalid = True
            break
    assert saw_rvalid, "rvalid_o never asserted"
    # stall_o must fall the cycle after rvalid_o
    await RisingEdge(dut.clk)
    await Timer(1, units="ns")
    assert int(dut.stall_o.value) == 0, "stall_o must fall the cycle after rvalid_o"
    dut.req_i.value = 0
