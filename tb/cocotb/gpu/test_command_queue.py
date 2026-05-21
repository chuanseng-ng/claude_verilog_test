"""
Unit tests for gpu_command_queue.sv — Phase 4 Group 4.

Tests:
  test_descriptor_stored        — launch latches all descriptor fields; desc_valid_o asserts
  test_launch_while_busy_dropped — second launch while busy is silently ignored
  test_ack_clears_valid         — desc_ack_i clears desc_valid_o; queue accepts new launch

kernel_desc_t packed layout (142 bits total, MSB first):
  [141:110] kernel_pc  32b
  [109: 94] grid_x     16b
  [ 93: 78] grid_y     16b
  [ 77: 62] grid_z     16b
  [ 61: 52] block_x    10b
  [ 51: 42] block_y    10b
  [ 41: 32] block_z    10b
  [ 31:  0] arg_ptr    32b
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


def _decode_desc(val: int) -> dict:
    """Extract fields from the packed kernel_desc_t integer (142 bits)."""
    return {
        "kernel_pc": (val >> 110) & 0xFFFF_FFFF,
        "grid_x":    (val >>  94) & 0xFFFF,
        "grid_y":    (val >>  78) & 0xFFFF,
        "grid_z":    (val >>  62) & 0xFFFF,
        "block_x":   (val >>  52) & 0x3FF,
        "block_y":   (val >>  42) & 0x3FF,
        "block_z":   (val >>  32) & 0x3FF,
        "arg_ptr":    val         & 0xFFFF_FFFF,
    }


async def _reset(dut):
    dut.rst_n.value        = 0
    dut.launch_i.value     = 0
    dut.kernel_pc_i.value  = 0
    dut.grid_x_i.value     = 0
    dut.grid_y_i.value     = 0
    dut.grid_z_i.value     = 0
    dut.block_x_i.value    = 0
    dut.block_y_i.value    = 0
    dut.block_z_i.value    = 0
    dut.arg_ptr_i.value    = 0
    dut.irq_enable_i.value = 0
    dut.desc_ack_i.value   = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _launch(dut, kernel_pc=0x1000, grid_x=4, grid_y=1, grid_z=1,
                  block_x=8, block_y=1, block_z=1, arg_ptr=0xDEAD_BEEF,
                  irq_enable=0):
    dut.launch_i.value     = 1
    dut.kernel_pc_i.value  = kernel_pc
    dut.grid_x_i.value     = grid_x
    dut.grid_y_i.value     = grid_y
    dut.grid_z_i.value     = grid_z
    dut.block_x_i.value    = block_x
    dut.block_y_i.value    = block_y
    dut.block_z_i.value    = block_z
    dut.arg_ptr_i.value    = arg_ptr
    dut.irq_enable_i.value = irq_enable
    await RisingEdge(dut.clk)
    dut.launch_i.value = 0


# ---------------------------------------------------------------------------


@cocotb.test()
async def test_descriptor_stored(dut):
    """Launch pulse latches all descriptor fields and asserts desc_valid_o."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    assert dut.desc_valid_o.value == 0, "Should start invalid"
    assert dut.busy_o.value       == 0

    await _launch(dut,
                  kernel_pc  = 0xCAFE_0000,
                  grid_x     = 8,  grid_y  = 4,  grid_z  = 2,
                  block_x    = 16, block_y = 8,  block_z = 4,
                  arg_ptr    = 0xABCD_1234,
                  irq_enable = 1)

    await Timer(1, units="ns")
    assert dut.desc_valid_o.value == 1, "desc_valid should assert after launch"
    assert dut.busy_o.value       == 1, "busy should assert after launch"
    assert dut.irq_enable_o.value == 1, "irq_enable_o should reflect irq_enable_i"

    d = _decode_desc(int(dut.desc_o.value))
    assert d["kernel_pc"] == 0xCAFE_0000, f"kernel_pc mismatch: 0x{d['kernel_pc']:08x}"
    assert d["grid_x"]    == 8,           f"grid_x mismatch: {d['grid_x']}"
    assert d["grid_y"]    == 4,           f"grid_y mismatch: {d['grid_y']}"
    assert d["grid_z"]    == 2,           f"grid_z mismatch: {d['grid_z']}"
    assert d["block_x"]   == 16,          f"block_x mismatch: {d['block_x']}"
    assert d["block_y"]   == 8,           f"block_y mismatch: {d['block_y']}"
    assert d["block_z"]   == 4,           f"block_z mismatch: {d['block_z']}"
    assert d["arg_ptr"]   == 0xABCD_1234, f"arg_ptr mismatch: 0x{d['arg_ptr']:08x}"


@cocotb.test()
async def test_launch_while_busy_dropped(dut):
    """A second launch while busy_o=1 is silently dropped; first descriptor preserved."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    await _launch(dut, kernel_pc=0x1000, arg_ptr=0xAAAA_AAAA)
    await Timer(1, units="ns")
    assert dut.desc_valid_o.value == 1

    # Attempt second launch while still busy
    await _launch(dut, kernel_pc=0x9999, arg_ptr=0xBBBB_BBBB)
    await Timer(1, units="ns")

    # First descriptor must be unchanged
    assert dut.desc_valid_o.value == 1, "valid should remain asserted"
    d = _decode_desc(int(dut.desc_o.value))
    assert d["kernel_pc"] == 0x1000,        f"First kernel_pc overwritten: 0x{d['kernel_pc']:08x}"
    assert d["arg_ptr"]   == 0xAAAA_AAAA,   f"First arg_ptr overwritten: 0x{d['arg_ptr']:08x}"


@cocotb.test()
async def test_ack_clears_valid(dut):
    """desc_ack_i clears desc_valid_o; queue immediately accepts a new launch."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    await _launch(dut, kernel_pc=0x2000, arg_ptr=0x1111_1111)
    await Timer(1, units="ns")
    assert dut.desc_valid_o.value == 1

    # Acknowledge (warp scheduler accepted the descriptor)
    dut.desc_ack_i.value = 1
    await RisingEdge(dut.clk)   # valid_q ← 0
    dut.desc_ack_i.value = 0
    await Timer(1, units="ns")
    assert dut.desc_valid_o.value == 0, "desc_valid should deassert after ack"
    assert dut.busy_o.value       == 0, "busy_o should deassert after ack"

    # Now a new launch should be accepted
    await _launch(dut, kernel_pc=0x3000, arg_ptr=0x2222_2222)
    await Timer(1, units="ns")
    assert dut.desc_valid_o.value == 1, "New launch should be accepted after ack"
    d = _decode_desc(int(dut.desc_o.value))
    assert d["kernel_pc"] == 0x3000,      f"New kernel_pc mismatch: 0x{d['kernel_pc']:08x}"
    assert d["arg_ptr"]   == 0x2222_2222, f"New arg_ptr mismatch: 0x{d['arg_ptr']:08x}"
