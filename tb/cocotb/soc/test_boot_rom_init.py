"""Bead ej6j -- boot_rom with MEM_INIT_FILE set: the $readmemh arm (boot_rom.sv `if (MEM_INIT_FILE != "")`).

Every other suite backdoor-loads the array, so the parameterised pre-load branch had never been taken.
Built by `make boot_rom` as a second build point with -GMEM_INIT_FILE="boot_rom_init.hex".
"""

import cocotb
from axi4_fabric_bfm import OKAY, SLVERR, AxiMaster
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

ROM_BASE = 0x0000_1000
HEX_WORDS = 32


def _expected(i):
    return 0xB007_0000 + (i << 8) + i


async def _setup(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    master = AxiMaster(dut, "s_", dut.clk)
    dut.rst_n.value = 0
    for _ in range(4):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    for _ in range(2):
        await RisingEdge(dut.clk)
    return master


@cocotb.test()
async def test_rom_preloaded_from_hex_file(dut):
    m = await _setup(dut)
    t = await m.read(ROM_BASE, 16)
    assert t.data == [_expected(i) for i in range(16)], [hex(d) for d in t.data]
    t = await m.read(ROM_BASE + 16 * 4, 16, r_stalls=[0, 2] * 8)
    assert t.data == [_expected(16 + i) for i in range(16)]
    assert t.resps == [OKAY] * 16 and not t.viol
    assert [int(dut.mem[i].value) for i in range(HEX_WORDS)] == [_expected(i) for i in range(HEX_WORDS)]


@cocotb.test()
async def test_preloaded_rom_is_still_read_only(dut):
    m = await _setup(dut)
    t = await m.write(ROM_BASE, [0xDEAD_BEEF] * 4)
    assert t.bresp == SLVERR
    t = await m.read(ROM_BASE, 4)
    assert t.data == [_expected(i) for i in range(4)], "write corrupted the pre-loaded image"
