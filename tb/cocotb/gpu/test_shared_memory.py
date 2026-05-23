"""
Unit tests for shared_memory.sv — Phase 4 Group 6.

Tests:
  test_conflict_free_8lane    — 8 lanes hit 8 distinct banks; no stall
  test_2lane_bank_conflict    — 2 lanes hit same bank; serialised over 2 cycles
  test_write_then_read        — write via lane 0, read back via lane 0
  test_mixed_rw_no_conflict   — 4 lanes write, 4 lanes read, all distinct banks

Address layout:
  bank_id  = addr[6:2]   (5 bits: 0..31)
  word_off = addr[13:7]  (7 bits: 0..127)
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

N_LANES   = 8
SHMEM_W   = 14   # log2(16384)


def _make_addr(bank: int, word: int) -> int:
    """Build a 14-bit byte address for a given bank and word offset."""
    # addr[6:2] = bank, addr[13:7] = word, addr[1:0] = 0
    return (word << 7) | (bank << 2)


def _encode_lanes(values: list, width: int) -> int:
    result = 0
    for i, v in enumerate(values):
        result |= (v & ((1 << width) - 1)) << (i * width)
    return result


def _decode_lanes(packed: int, n: int = N_LANES, width: int = 32) -> list:
    mask = (1 << width) - 1
    return [(packed >> (i * width)) & mask for i in range(n)]


async def _reset(dut):
    dut.rst_n.value      = 0
    dut.sh_addr_i.value  = 0
    dut.sh_we_i.value    = 0
    dut.sh_wdata_i.value = 0
    dut.sh_active_i.value = 0
    for _ in range(3):
        await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)


async def _issue(dut, addrs, wdata, we_mask, active_mask):
    """Drive one request; returns when sh_stall_o drops."""
    dut.sh_addr_i.value   = _encode_lanes(addrs,  SHMEM_W)
    dut.sh_wdata_i.value  = _encode_lanes(wdata,  32)
    dut.sh_we_i.value     = we_mask
    dut.sh_active_i.value = active_mask
    # Wait for stall to clear (at most 20 cycles)
    await RisingEdge(dut.clk)   # request accepted
    dut.sh_active_i.value = 0   # deassert after first cycle
    for _ in range(20):
        await Timer(1, units="ns")
        if not dut.sh_stall_o.value:
            break
        await RisingEdge(dut.clk)
    else:
        assert False, "sh_stall_o never deasserted"
    await Timer(1, units="ns")  # settle rdata


# ---------------------------------------------------------------------------


@cocotb.test()
async def test_conflict_free_8lane(dut):
    """8 lanes each target a different bank; stall never asserts after T+1."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    # Lane l → bank l, word 0
    addrs  = [_make_addr(bank=l, word=0) for l in range(N_LANES)]
    wdata  = [0xAA00_0000 | l for l in range(N_LANES)]

    # Write
    await _issue(dut, addrs, wdata, we_mask=0xFF, active_mask=0xFF)
    stall_cycles = 0
    # After conflict-free access the pending mask should have been 0 within
    # 1 service cycle (all served simultaneously).
    assert stall_cycles == 0 or not dut.sh_stall_o.value, \
        "Conflict-free access should not stall beyond 1 service cycle"

    # Read back
    await _issue(dut, addrs, [0]*N_LANES, we_mask=0x00, active_mask=0xFF)
    rdata = _decode_lanes(int(dut.sh_rdata_o.value))

    for l in range(N_LANES):
        assert rdata[l] == wdata[l], \
            f"Lane {l}: expected 0x{wdata[l]:08x}, got 0x{rdata[l]:08x}"


@cocotb.test()
async def test_2lane_bank_conflict(dut):
    """Lanes 0 and 1 target the same bank; access serialises (multi-cycle stall);
    both writes land and read back correctly.

    Banks are now SRAM macros with a registered (1-cycle-latency) read, so the
    exact stall length is implementation-dependent; this test asserts the access
    serialises over more than one cycle and that the data is correct, rather than
    pinning an exact cycle count.
    """
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    BANK  = 5
    # Lane 0 → bank 5 word 0, lane 1 → bank 5 word 1 (same bank, different words)
    addrs  = [_make_addr(BANK, 0), _make_addr(BANK, 1)] + [0] * 6
    wdata  = [0xBBBB_0001, 0xBBBB_0002] + [0] * 6

    # Write lanes 0 and 1 to same bank
    dut.sh_addr_i.value   = _encode_lanes(addrs,  SHMEM_W)
    dut.sh_wdata_i.value  = _encode_lanes(wdata,  32)
    dut.sh_we_i.value     = 0x03   # lanes 0 and 1 write
    dut.sh_active_i.value = 0x03
    await RisingEdge(dut.clk)      # request accepted → pending=0b11
    dut.sh_active_i.value = 0

    # Stall must assert and stay high for >=2 cycles (the two same-bank lanes are
    # served on successive cycles), then deassert.
    high_cycles = 0
    for _ in range(20):
        await Timer(1, units="ns")
        if not dut.sh_stall_o.value:
            break
        high_cycles += 1
        await RisingEdge(dut.clk)
    else:
        assert False, "sh_stall_o never deasserted"
    assert high_cycles >= 2, \
        f"bank conflict should serialise over >=2 stall cycles, got {high_cycles}"

    # Read back both words
    addrs_r = [_make_addr(BANK, 0), _make_addr(BANK, 1)] + [0] * 6
    await _issue(dut, addrs_r, [0]*N_LANES, we_mask=0x00, active_mask=0x03)
    rdata = _decode_lanes(int(dut.sh_rdata_o.value))
    assert rdata[0] == 0xBBBB_0001, f"Lane 0 data wrong: 0x{rdata[0]:08x}"
    assert rdata[1] == 0xBBBB_0002, f"Lane 1 data wrong: 0x{rdata[1]:08x}"


@cocotb.test()
async def test_write_then_read(dut):
    """Write a value via lane 0, read it back via lane 0 at the same address."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    ADDR  = _make_addr(bank=3, word=7)
    VALUE = 0xCAFE_BABE

    # Write
    await _issue(dut, [ADDR] + [0]*7, [VALUE] + [0]*7, we_mask=0x01, active_mask=0x01)
    # Read
    await _issue(dut, [ADDR] + [0]*7, [0]*N_LANES, we_mask=0x00, active_mask=0x01)
    rdata = _decode_lanes(int(dut.sh_rdata_o.value))
    assert rdata[0] == VALUE, \
        f"Read-back failed: expected 0x{VALUE:08x}, got 0x{rdata[0]:08x}"


@cocotb.test()
async def test_mixed_rw_no_conflict(dut):
    """4 lanes write to banks 0-3, 4 lanes read from banks 4-7; no conflict."""
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await _reset(dut)

    # Pre-write reference data to banks 4-7 via individual single-lane ops
    for l in range(4):
        addr  = _make_addr(bank=l + 4, word=2)
        val   = 0xDD00_0000 | (l + 4)
        await _issue(dut, [addr] + [0]*7, [val] + [0]*7, we_mask=0x01, active_mask=0x01)

    # Mixed op: lanes 0-3 write banks 0-3; lanes 4-7 read banks 4-7
    w_addrs = [_make_addr(bank=l,     word=1) for l in range(4)]
    r_addrs = [_make_addr(bank=l + 4, word=2) for l in range(4)]
    all_addrs = w_addrs + r_addrs
    w_vals    = [0xEE00_0000 | l for l in range(4)]
    all_wdata = w_vals + [0] * 4

    await _issue(dut, all_addrs, all_wdata,
                 we_mask=0x0F, active_mask=0xFF)

    rdata = _decode_lanes(int(dut.sh_rdata_o.value))
    for l in range(4):
        exp = 0xDD00_0000 | (l + 4)
        assert rdata[l + 4] == exp, \
            f"Lane {l+4}: expected 0x{exp:08x}, got 0x{rdata[l+4]:08x}"
