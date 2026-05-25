"""
Smoke tests for gpu_top.sv — Phase 4 Group 7.

Tests:
  test_reg_write_read   — write kernel descriptor regs, read them back
  test_status_idle      — GPU_STATUS[0] (idle) set after reset
  test_launch_transitions — write CTRL[launch], poll STATUS[done] (fake kernel)
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

# AXI4-Lite offsets
GPU_CTRL       = 0x000
GPU_STATUS     = 0x004
GPU_KERNEL_PC  = 0x008
GPU_GRID_X     = 0x00C
GPU_GRID_Y     = 0x010
GPU_GRID_Z     = 0x014
GPU_BLOCK_X    = 0x018
GPU_BLOCK_Y    = 0x01C
GPU_BLOCK_Z    = 0x020
GPU_ARG_PTR    = 0x024
GPU_IRQ_CLR    = 0x028
GPU_PERFCNT0   = 0x030


async def _reset(dut):
    dut.rst_n.value           = 0
    dut.s_axil_awvalid.value  = 0
    dut.s_axil_wvalid.value   = 0
    dut.s_axil_bready.value   = 1
    dut.s_axil_arvalid.value  = 0
    dut.s_axil_rready.value   = 1
    dut.s_axil_awaddr.value   = 0
    dut.s_axil_wdata.value    = 0
    dut.s_axil_wstrb.value    = 0xF
    dut.s_axil_araddr.value   = 0
    dut.m_axil_if_arready.value = 0
    dut.m_axil_if_rdata.value   = 0
    dut.m_axil_if_rresp.value   = 0
    dut.m_axil_if_rvalid.value  = 0
    dut.m_axi_arready.value   = 0
    dut.m_axi_rdata.value     = 0
    dut.m_axi_rresp.value     = 0
    dut.m_axi_rvalid.value    = 0
    dut.m_axi_awready.value   = 0
    dut.m_axi_wready.value    = 0
    dut.m_axi_bresp.value     = 0
    dut.m_axi_bvalid.value    = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _axil_write(dut, addr: int, data: int):
    """Single AXI4-Lite register write (addr + data in same cycle)."""
    # Issue AW
    dut.s_axil_awaddr.value  = addr
    dut.s_axil_awvalid.value = 1
    while True:
        await RisingEdge(dut.clk)
        if dut.s_axil_awready.value:
            break
    dut.s_axil_awvalid.value = 0

    # Issue W
    dut.s_axil_wdata.value  = data
    dut.s_axil_wvalid.value = 1
    while True:
        await RisingEdge(dut.clk)
        if dut.s_axil_wready.value:
            break
    dut.s_axil_wvalid.value = 0

    # Wait for B
    while True:
        await RisingEdge(dut.clk)
        if dut.s_axil_bvalid.value:
            break
    await Timer(1, units="ns")


async def _axil_read(dut, addr: int) -> int:
    """Single AXI4-Lite register read."""
    dut.s_axil_araddr.value  = addr
    dut.s_axil_arvalid.value = 1
    while True:
        await RisingEdge(dut.clk)
        if dut.s_axil_arready.value:
            break
    dut.s_axil_arvalid.value = 0

    while True:
        await RisingEdge(dut.clk)
        if dut.s_axil_rvalid.value:
            rdata = int(dut.s_axil_rdata.value)
            break
    await Timer(1, units="ns")
    return rdata


# ---------------------------------------------------------------------------


@cocotb.test()
async def test_reg_write_read(dut):
    """Write kernel descriptor regs, read them back."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    await _axil_write(dut, GPU_KERNEL_PC, 0xDEAD_C0DE)
    await _axil_write(dut, GPU_GRID_X,    0x0000_0004)
    await _axil_write(dut, GPU_GRID_Y,    0x0000_0002)
    await _axil_write(dut, GPU_GRID_Z,    0x0000_0001)
    await _axil_write(dut, GPU_BLOCK_X,   0x0000_0008)
    await _axil_write(dut, GPU_ARG_PTR,   0x1234_5678)

    assert await _axil_read(dut, GPU_KERNEL_PC) == 0xDEAD_C0DE, "GPU_KERNEL_PC"
    assert await _axil_read(dut, GPU_GRID_X)    == 0x0000_0004, "GPU_GRID_X"
    assert await _axil_read(dut, GPU_GRID_Y)    == 0x0000_0002, "GPU_GRID_Y"
    assert await _axil_read(dut, GPU_GRID_Z)    == 0x0000_0001, "GPU_GRID_Z"
    assert await _axil_read(dut, GPU_BLOCK_X)   == 0x0000_0008, "GPU_BLOCK_X"
    assert await _axil_read(dut, GPU_ARG_PTR)   == 0x1234_5678, "GPU_ARG_PTR"


@cocotb.test()
async def test_status_idle(dut):
    """After reset GPU_STATUS[0] (idle) is set; done and error are clear."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    status = await _axil_read(dut, GPU_STATUS)
    assert status & 0x1, f"idle bit should be set after reset, STATUS=0x{status:08x}"
    assert not (status & 0x2), f"done bit should be clear after reset"
    assert not (status & 0x4), f"error bit should be clear after reset"


@cocotb.test()
async def test_irq_enable_readback(dut):
    """Write irq_enable=1 via GPU_CTRL[2]; read it back via GPU_CTRL."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    await _axil_write(dut, GPU_CTRL, 0x4)  # set irq_enable bit [2]
    ctrl = await _axil_read(dut, GPU_CTRL)
    assert ctrl & 0x4, f"irq_enable bit should read back as 1, CTRL=0x{ctrl:08x}"


@cocotb.test()
async def test_perf_counters_zero_after_reset(dut):
    """All performance counters read as 0 after reset (no kernel running)."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    for i in range(6):
        val = await _axil_read(dut, GPU_PERFCNT0 + i * 4)
        assert val == 0, f"PERFCNT[{i}] should be 0 after reset, got 0x{val:08x}"
