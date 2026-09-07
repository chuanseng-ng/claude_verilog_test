"""
Unit tests for vector_alu.sv

Packed 2D ports ([N_LANES-1:0][REG_WIDTH-1:0]) are a single integer in
Verilator+cocotb. Lane 0 occupies bits [31:0] (LSB).

Tests:
  1. All 9 R-type arithmetic/logic opcodes (all 8 lanes active)
  2. All 4 I-type immediate opcodes
  3. Partial active mask — inactive lanes produce 0
  4. VMUL lower-32-bit overflow
  5. VSRA arithmetic sign extension
  6. Negative immediate sign extension
  7. Branch conditions (VBEQ, VBNE, VBLT, VBGE) — per-lane taken bits

GH #119 bead `gg8` adds a second arm: a Bambu-HLS implementation behind a
wire-only shim, vector_alu_hls (hls/gpu/vector_alu/shim/vector_alu_hls.sv).
The reference block (rtl/gpu/vector_alu.sv) is purely combinational -- no
clock, no reset, no registers. Bambu cannot emit combinational logic: it
wraps every design in a clk/rst_n/start_i/done_o handshake, and this one is
an 81-state FSM with 11-21 cycles of latency.

This file branches on that protocol difference in exactly one place --
VectorAluDriver.setup() / .settle() -- detected at runtime via
hasattr(dut, "clk"), the same pattern used in
tb/cocotb/cpu/test_hazard_unit.py for rv32i_hazard_unit. Every vector,
every expected value, and every assertion after that point is identical
for both arms. The hand-RTL arm is NOT wrapped in a handshake -- the
interface difference is real and stays visible.
"""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ReadOnly, RisingEdge, Timer
import ctypes

N_LANES   = 8
REG_WIDTH = 32

# Opcode values (must match gpu_pkg::gpu_opcode_t)
OP = {
    "VADD":  0x01, "VSUB":  0x02, "VMUL":  0x03,
    "VAND":  0x04, "VOR":   0x05, "VXOR":  0x06,
    "VSLL":  0x07, "VSRL":  0x08, "VSRA":  0x09,
    "VADDI": 0x11, "VANDI": 0x12, "VORI":  0x13, "VXORI": 0x14,
    "VBEQ":  0x30, "VBNE":  0x31, "VBLT":  0x32, "VBGE":  0x33,
}


def _to_s32(v: int) -> int:
    return ctypes.c_int32(v).value


def _mask32(v: int) -> int:
    return v & 0xFFFF_FFFF


def _pack(data: list) -> int:
    """Pack N_LANES 32-bit ints → single integer (lane 0 at LSB)."""
    result = 0
    for lane in range(N_LANES - 1, -1, -1):
        result = (result << REG_WIDTH) | (_mask32(int(data[lane])))
    return result


def _unpack(val: int) -> list:
    """Unpack single integer → N_LANES 32-bit ints (lane 0 at LSB)."""
    result = []
    for _ in range(N_LANES):
        result.append(int(val) & 0xFFFF_FFFF)
        val >>= REG_WIDTH
    return result


# ---------------------------------------------------------------------------
# The one protocol branch (GH #119 decision: do not wrap the hand-RTL arm in
# a handshake). Same pattern as tb/cocotb/cpu/test_hazard_unit.py's
# HazardUnitDriver.
# ---------------------------------------------------------------------------


class VectorAluDriver:
    """Waits for the DUT's outputs to settle after inputs have been written
    (via _set_inputs, called by the test before drv.settle()), for either
    arm.

    Hand-RTL arm: purely combinational -- let the netlist settle (Timer,
    no clock), then sample.

    HLS arm: Bambu wraps the block in a clock/reset/start_port/done_port
    handshake (module vector_alu_hls, hls/gpu/vector_alu/shim/
    vector_alu_hls.sv). Detected via hasattr(dut, "clk").
    """

    def __init__(self, dut):
        self.dut = dut
        self.is_hls = hasattr(dut, "clk")
        self._clock_started = False

    async def setup(self):
        if not self.is_hls:
            return
        if not self._clock_started:
            cocotb.start_soon(Clock(self.dut.clk, 10, units="ns").start())
            self._clock_started = True
        # Async active-low reset, matching the repo's HLS-shim convention.
        self.dut.rst_n.value = 0
        self.dut.start_i.value = 0
        await RisingEdge(self.dut.clk)
        await RisingEdge(self.dut.clk)
        self.dut.rst_n.value = 1
        await RisingEdge(self.dut.clk)

    async def settle(self) -> dict:
        """Inputs must already be written (via _set_inputs) before this is
        called. Returns {"result_o": int, "branch_taken_o": int}."""
        dut = self.dut
        if not self.is_hls:
            # Purely combinational: let the netlist settle, then sample.
            await Timer(1, units="ns")
            return {
                "result_o": int(dut.result_o.value),
                "branch_taken_o": int(dut.branch_taken_o.value),
            }

        dut.start_i.value = 1
        await RisingEdge(dut.clk)
        dut.start_i.value = 0
        # Wait for the Bambu handshake to complete (bounded so a stuck
        # done_o fails the test instead of hanging the regression).
        for _ in range(50):
            await RisingEdge(dut.clk)
            if int(dut.done_o.value):
                break
        else:
            raise TimeoutError("HLS arm: done_o never asserted within 50 cycles")
        await ReadOnly()
        outputs = {
            "result_o": int(dut.result_o.value),
            "branch_taken_o": int(dut.branch_taken_o.value),
        }
        # Step past the read-only sync phase before returning: ReadOnly()
        # above leaves the scheduler unable to accept writes, and the very
        # next call to _set_inputs() writes input values with no intervening
        # await -- without this, that write raises "scheduled during a
        # read-only sync phase" (same fix as
        # test_hazard_unit.py's HazardUnitDriver.apply()).
        await RisingEdge(dut.clk)
        return outputs


async def make_driver(dut) -> VectorAluDriver:
    drv = VectorAluDriver(dut)
    await drv.setup()
    return drv


def _set_inputs(dut, opcode: int, rs1: list, rs2: list,
                imm: int = 0, mask: int = 0xFF):
    dut.opcode_i.value      = opcode
    dut.funct3_i.value      = 0
    dut.funct7_i.value      = 0
    dut.imm_i.value         = imm & 0xFFF
    dut.active_mask_i.value = mask
    dut.rs1_i.value         = _pack(rs1)
    dut.rs2_i.value         = _pack(rs2)


def _get_results(outputs: dict) -> list:
    return _unpack(outputs["result_o"])


def _get_taken(outputs: dict) -> list:
    raw = outputs["branch_taken_o"]
    return [(raw >> lane) & 1 for lane in range(N_LANES)]


@cocotb.test()
async def test_vadd(dut):
    """VADD rd = rs1 + rs2 (all lanes active)."""
    drv = await make_driver(dut)
    rs1 = [0x0000_0001 * (lane + 1) for lane in range(N_LANES)]
    rs2 = [0x0000_0010 * (lane + 1) for lane in range(N_LANES)]
    _set_inputs(dut, OP["VADD"], rs1, rs2)
    out = await drv.settle()
    got = _get_results(out)
    exp = [_mask32(rs1[l] + rs2[l]) for l in range(N_LANES)]
    assert got == exp, f"VADD: {[hex(v) for v in got]} != {[hex(v) for v in exp]}"


@cocotb.test()
async def test_vsub(dut):
    """VSUB rd = rs1 - rs2."""
    drv = await make_driver(dut)
    rs1 = [0x0000_0100 * (lane + 1) for lane in range(N_LANES)]
    rs2 = [0x0000_0001 * (lane + 1) for lane in range(N_LANES)]
    _set_inputs(dut, OP["VSUB"], rs1, rs2)
    out = await drv.settle()
    got = _get_results(out)
    exp = [_mask32(rs1[l] - rs2[l]) for l in range(N_LANES)]
    assert got == exp, f"VSUB: {[hex(v) for v in got]} != {[hex(v) for v in exp]}"


@cocotb.test()
async def test_vmul_lower32(dut):
    """VMUL: lower 32 bits of 64-bit product."""
    drv = await make_driver(dut)
    rs1 = [0x0001_0001 * (lane + 1) for lane in range(N_LANES)]
    rs2 = [0x0000_FFFF] * N_LANES
    _set_inputs(dut, OP["VMUL"], rs1, rs2)
    out = await drv.settle()
    got = _get_results(out)
    exp = [_mask32(rs1[l] * rs2[l]) for l in range(N_LANES)]
    assert got == exp, f"VMUL: {[hex(v) for v in got]} != {[hex(v) for v in exp]}"


@cocotb.test()
async def test_vand(dut):
    drv = await make_driver(dut)
    rs1 = [0xAAAA_AAAA] * N_LANES
    rs2 = [0x5555_5555] * N_LANES
    _set_inputs(dut, OP["VAND"], rs1, rs2)
    out = await drv.settle()
    assert _get_results(out) == [0x0000_0000] * N_LANES


@cocotb.test()
async def test_vor(dut):
    drv = await make_driver(dut)
    rs1 = [0xAAAA_AAAA] * N_LANES
    rs2 = [0x5555_5555] * N_LANES
    _set_inputs(dut, OP["VOR"], rs1, rs2)
    out = await drv.settle()
    assert _get_results(out) == [0xFFFF_FFFF] * N_LANES


@cocotb.test()
async def test_vxor(dut):
    drv = await make_driver(dut)
    rs1 = [0xFFFF_FFFF] * N_LANES
    rs2 = [0xAAAA_AAAA] * N_LANES
    _set_inputs(dut, OP["VXOR"], rs1, rs2)
    out = await drv.settle()
    assert _get_results(out) == [0x5555_5555] * N_LANES


@cocotb.test()
async def test_vsll(dut):
    drv = await make_driver(dut)
    rs1 = [1] * N_LANES
    rs2 = list(range(N_LANES))
    _set_inputs(dut, OP["VSLL"], rs1, rs2)
    out = await drv.settle()
    got = _get_results(out)
    exp = [_mask32(1 << lane) for lane in range(N_LANES)]
    assert got == exp, f"VSLL: {[hex(v) for v in got]} != {[hex(v) for v in exp]}"


@cocotb.test()
async def test_vsrl(dut):
    """Logical right shift — sign bit is NOT propagated."""
    drv = await make_driver(dut)
    rs1 = [0x8000_0000] * N_LANES
    rs2 = [1] * N_LANES
    _set_inputs(dut, OP["VSRL"], rs1, rs2)
    out = await drv.settle()
    assert _get_results(out) == [0x4000_0000] * N_LANES


@cocotb.test()
async def test_vsra(dut):
    """Arithmetic right shift — sign bit IS propagated."""
    drv = await make_driver(dut)
    rs1 = [0x8000_0000] * N_LANES
    rs2 = [4] * N_LANES
    _set_inputs(dut, OP["VSRA"], rs1, rs2)
    out = await drv.settle()
    assert _get_results(out) == [0xF800_0000] * N_LANES


@cocotb.test()
async def test_vaddi_negative_imm(dut):
    """VADDI with negative immediate (sign-extended from 12 bits to 32)."""
    drv = await make_driver(dut)
    rs1 = [0x0000_0010] * N_LANES
    imm = 0xFFF  # -1 in 12-bit two's complement
    _set_inputs(dut, OP["VADDI"], rs1, rs1, imm=imm)
    out = await drv.settle()
    exp = [_mask32(0x10 - 1)] * N_LANES
    assert _get_results(out) == exp, f"VADDI -1: {_get_results(out)} != {exp}"


@cocotb.test()
async def test_vandi(dut):
    drv = await make_driver(dut)
    rs1 = [0xFFFF_FFFF] * N_LANES
    imm = 0x0FF  # positive, lower 8 bits set
    _set_inputs(dut, OP["VANDI"], rs1, rs1, imm=imm)
    out = await drv.settle()
    assert _get_results(out) == [0x0000_00FF] * N_LANES


@cocotb.test()
async def test_partial_mask(dut):
    """Inactive lanes (mask bit=0) produce 0; active lanes compute normally."""
    drv = await make_driver(dut)
    rs1 = [0xDEAD_BEEF] * N_LANES
    rs2 = [0x1111_1111] * N_LANES
    mask = 0b0101_0101  # even lanes active
    _set_inputs(dut, OP["VADD"], rs1, rs2, mask=mask)
    out = await drv.settle()
    got = _get_results(out)
    for lane in range(N_LANES):
        if mask & (1 << lane):
            exp = _mask32(rs1[lane] + rs2[lane])
            assert got[lane] == exp, \
                f"Active lane {lane}: expected {exp:#010x}, got {got[lane]:#010x}"
        else:
            assert got[lane] == 0, \
                f"Inactive lane {lane} should be 0, got {got[lane]:#010x}"


@cocotb.test()
async def test_branch_vbeq(dut):
    """VBEQ: branch_taken_o[lane]=1 iff rs1[lane]==rs2[lane]."""
    drv = await make_driver(dut)
    rs1 = [lane * 10 for lane in range(N_LANES)]
    rs2 = [lane * 10 if lane % 2 == 0 else lane * 99 for lane in range(N_LANES)]
    _set_inputs(dut, OP["VBEQ"], rs1, rs2)
    out = await drv.settle()
    taken = _get_taken(out)
    for lane in range(N_LANES):
        exp = 1 if rs1[lane] == rs2[lane] else 0
        assert taken[lane] == exp, \
            f"VBEQ lane {lane}: expected {exp}, got {taken[lane]}"


@cocotb.test()
async def test_branch_vblt(dut):
    """VBLT: signed less-than per lane."""
    drv = await make_driver(dut)
    rs1 = [0x8000_0000, 0, 5, 0xFFFF_FFFF, 0, 100, 0, 0x7FFF_FFFF]
    rs2 = [0x7FFF_FFFF, 0, 3, 0,           1, 100, 0xFFFF_FFFF, 0x8000_0000]
    _set_inputs(dut, OP["VBLT"], rs1, rs2)
    out = await drv.settle()
    taken = _get_taken(out)
    for lane in range(N_LANES):
        exp = 1 if _to_s32(rs1[lane]) < _to_s32(rs2[lane]) else 0
        assert taken[lane] == exp, \
            f"VBLT lane {lane}: rs1={rs1[lane]:#010x} rs2={rs2[lane]:#010x} " \
            f"expected={exp}, got={taken[lane]}"
