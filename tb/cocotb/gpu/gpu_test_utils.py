"""Shared cocotb helpers for gpu_top tests."""
from cocotb.triggers import RisingEdge, Timer

# AXI4-Lite register offsets
GPU_CTRL      = 0x000
GPU_STATUS    = 0x004
GPU_KERNEL_PC = 0x008
GPU_GRID_X    = 0x00C
GPU_GRID_Y    = 0x010
GPU_GRID_Z    = 0x014
GPU_BLOCK_X   = 0x018
GPU_BLOCK_Y   = 0x01C
GPU_BLOCK_Z   = 0x020
GPU_ARG_PTR   = 0x024
GPU_IRQ_CLR   = 0x028
GPU_PERFCNT0  = 0x030


async def gpu_reset(dut):
    dut.rst_n.value             = 0
    dut.s_axil_awvalid.value    = 0
    dut.s_axil_wvalid.value     = 0
    dut.s_axil_bready.value     = 1
    dut.s_axil_arvalid.value    = 0
    dut.s_axil_rready.value     = 1
    dut.s_axil_awaddr.value     = 0
    dut.s_axil_wdata.value      = 0
    dut.s_axil_wstrb.value      = 0xF
    dut.s_axil_araddr.value     = 0
    dut.m_axil_if_arready.value = 0
    dut.m_axil_if_rdata.value   = 0
    dut.m_axil_if_rresp.value   = 0
    dut.m_axil_if_rvalid.value  = 0
    dut.m_axi_arready.value     = 0
    dut.m_axi_rdata.value       = 0
    dut.m_axi_rresp.value       = 0
    dut.m_axi_rvalid.value      = 0
    dut.m_axi_awready.value     = 0
    dut.m_axi_wready.value      = 0
    dut.m_axi_bresp.value       = 0
    dut.m_axi_bvalid.value      = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def axil_write(dut, addr: int, data: int):
    dut.s_axil_awaddr.value  = addr
    dut.s_axil_awvalid.value = 1
    while True:
        await RisingEdge(dut.clk)
        if dut.s_axil_awready.value:
            break
    dut.s_axil_awvalid.value = 0
    dut.s_axil_wdata.value   = data
    dut.s_axil_wvalid.value  = 1
    while True:
        await RisingEdge(dut.clk)
        if dut.s_axil_wready.value:
            break
    dut.s_axil_wvalid.value = 0
    while True:
        await RisingEdge(dut.clk)
        if dut.s_axil_bvalid.value:
            break
    await Timer(1, units="ns")


async def axil_read(dut, addr: int) -> int:
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


async def gpu_launch(dut, *, kernel_pc: int, grid_x: int = 1, grid_y: int = 1,
                     grid_z: int = 1, block_x: int = 8,
                     block_y: int = 1, block_z: int = 1):
    """Write kernel descriptor and pulse the launch bit."""
    await axil_write(dut, GPU_KERNEL_PC, kernel_pc)
    await axil_write(dut, GPU_GRID_X,    grid_x)
    await axil_write(dut, GPU_GRID_Y,    grid_y)
    await axil_write(dut, GPU_GRID_Z,    grid_z)
    await axil_write(dut, GPU_BLOCK_X,   block_x)
    await axil_write(dut, GPU_BLOCK_Y,   block_y)
    await axil_write(dut, GPU_BLOCK_Z,   block_z)
    await axil_write(dut, GPU_CTRL,      0x1)   # W1S launch bit


async def gpu_wait_done(dut, timeout: int = 10_000) -> bool:
    """Poll STATUS[done] until set. Returns True on success, False on timeout."""
    for _ in range(timeout):
        await RisingEdge(dut.clk)
        status = await axil_read(dut, GPU_STATUS)
        if status & 0x2:
            return True
    return False
