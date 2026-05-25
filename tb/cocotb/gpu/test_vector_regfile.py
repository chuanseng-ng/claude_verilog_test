"""
Unit tests for vector_register_file.sv

Packed 2D arrays ([N_LANES-1:0][REG_WIDTH-1:0]) are flattened to a single
integer in Verilator+cocotb. Lane 0 occupies bits [31:0] (LSB).

Tests:
  1. Write then read per lane per warp
  2. r0 always returns 0 after a write attempt
  3. Concurrent read A + read B (same warp, different regs)
  4. Write mask — only asserted lanes update
  5. Multi-warp isolation (writes to warp N do not affect warp M)
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge, Timer

N_LANES    = 8
REG_WIDTH  = 32


def _pack(data: list) -> int:
    """Pack list of N_LANES 32-bit ints → single integer (lane 0 at LSB)."""
    result = 0
    for lane in range(N_LANES - 1, -1, -1):
        result = (result << REG_WIDTH) | (int(data[lane]) & 0xFFFF_FFFF)
    return result


def _unpack(val: int) -> list:
    """Unpack single integer → list of N_LANES 32-bit ints (lane 0 at LSB)."""
    result = []
    for _ in range(N_LANES):
        result.append(int(val) & 0xFFFF_FFFF)
        val >>= REG_WIDTH
    return result


async def _reset(dut, cycles: int = 4):
    dut.rst_n.value      = 0
    dut.wr_en_i.value    = 0
    dut.wr_mask_i.value  = 0
    dut.wr_warp_i.value  = 0
    dut.wr_reg_i.value   = 0
    dut.wr_data_i.value  = 0
    dut.rda_warp_i.value = 0
    dut.rda_reg_i.value  = 0
    dut.rdb_warp_i.value = 0
    dut.rdb_reg_i.value  = 0
    await ClockCycles(dut.clk, cycles)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _write(dut, warp: int, reg: int, data: list, mask: int = 0xFF):
    """Write one register to a warp. data is list of N_LANES ints."""
    dut.wr_en_i.value    = 1
    dut.wr_warp_i.value  = warp
    dut.wr_reg_i.value   = reg
    dut.wr_mask_i.value  = mask
    dut.wr_data_i.value  = _pack(data)
    await RisingEdge(dut.clk)
    dut.wr_en_i.value = 0


async def _read_a(dut, warp: int, reg: int) -> list:
    dut.rda_warp_i.value = warp
    dut.rda_reg_i.value  = reg
    await Timer(1, units="ns")   # let always_comb settle after address change
    return _unpack(dut.rda_data_o.value)


async def _read_b(dut, warp: int, reg: int) -> list:
    dut.rdb_warp_i.value = warp
    dut.rdb_reg_i.value  = reg
    await Timer(1, units="ns")
    return _unpack(dut.rdb_data_o.value)


@cocotb.test()
async def test_write_then_read(dut):
    """Write all 8 lanes of r1 in warp 0, verify read-back."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    expected = [0xDEAD_0000 + lane for lane in range(N_LANES)]
    await _write(dut, warp=0, reg=1, data=expected)

    got = await _read_a(dut, warp=0, reg=1)
    assert got == expected, f"Expected {[hex(v) for v in expected]}, got {[hex(v) for v in got]}"


@cocotb.test()
async def test_r0_always_zero(dut):
    """Writes to r0 must be discarded; reads always return 0."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    await _write(dut, warp=0, reg=0, data=[0xDEAD_BEEF] * N_LANES)

    got_a = await _read_a(dut, warp=0, reg=0)
    got_b = await _read_b(dut, warp=0, reg=0)
    assert got_a == [0] * N_LANES, f"r0 port A not zero: {[hex(v) for v in got_a]}"
    assert got_b == [0] * N_LANES, f"r0 port B not zero: {[hex(v) for v in got_b]}"


@cocotb.test()
async def test_concurrent_read_ab(dut):
    """Read port A (r2) and port B (r3) simultaneously, same warp."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    data_r2 = [0xAAAA_0000 + lane for lane in range(N_LANES)]
    data_r3 = [0xBBBB_0000 + lane for lane in range(N_LANES)]
    await _write(dut, warp=1, reg=2, data=data_r2)
    await _write(dut, warp=1, reg=3, data=data_r3)

    # Point both ports simultaneously, settle, then read combinational outputs
    dut.rda_warp_i.value = 1
    dut.rda_reg_i.value  = 2
    dut.rdb_warp_i.value = 1
    dut.rdb_reg_i.value  = 3
    await Timer(1, units="ns")

    got_a = _unpack(dut.rda_data_o.value)
    got_b = _unpack(dut.rdb_data_o.value)

    assert got_a == data_r2, f"Port A wrong: {[hex(v) for v in got_a]}"
    assert got_b == data_r3, f"Port B wrong: {[hex(v) for v in got_b]}"


@cocotb.test()
async def test_write_mask(dut):
    """Only lanes with mask bit asserted should be updated."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    baseline = [0xBEEF_0000 + lane for lane in range(N_LANES)]
    await _write(dut, warp=2, reg=5, data=baseline, mask=0xFF)

    # Write only even lanes (mask = 0b01010101 = 0x55)
    new_vals = [0xCAFE_0000 + lane for lane in range(N_LANES)]
    await _write(dut, warp=2, reg=5, data=new_vals, mask=0x55)

    got = await _read_a(dut, warp=2, reg=5)
    for lane in range(N_LANES):
        if lane % 2 == 0:
            assert got[lane] == new_vals[lane], \
                f"Active lane {lane}: expected {new_vals[lane]:#010x}, got {got[lane]:#010x}"
        else:
            assert got[lane] == baseline[lane], \
                f"Inactive lane {lane}: expected {baseline[lane]:#010x}, got {got[lane]:#010x}"


@cocotb.test()
async def test_warp_isolation(dut):
    """Writes to warp 3 must not corrupt warp 5 registers."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    data_w3 = [0xC3C3_0000 + lane for lane in range(N_LANES)]
    data_w5 = [0xC5C5_0000 + lane for lane in range(N_LANES)]
    await _write(dut, warp=3, reg=7, data=data_w3)
    await _write(dut, warp=5, reg=7, data=data_w5)

    got_w3 = await _read_a(dut, warp=3, reg=7)
    got_w5 = await _read_a(dut, warp=5, reg=7)

    assert got_w3 == data_w3, f"Warp 3 corrupted: {[hex(v) for v in got_w3]}"
    assert got_w5 == data_w5, f"Warp 5 corrupted: {[hex(v) for v in got_w5]}"
