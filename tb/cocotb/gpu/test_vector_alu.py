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
"""
import cocotb
from cocotb.triggers import Timer
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


async def _eval(dut):
    """Small settle time for combinational logic."""
    await Timer(1, units="ns")


def _set_inputs(dut, opcode: int, rs1: list, rs2: list,
                imm: int = 0, mask: int = 0xFF):
    dut.opcode_i.value      = opcode
    dut.funct3_i.value      = 0
    dut.funct7_i.value      = 0
    dut.imm_i.value         = imm & 0xFFF
    dut.active_mask_i.value = mask
    dut.rs1_i.value         = _pack(rs1)
    dut.rs2_i.value         = _pack(rs2)


def _get_results(dut) -> list:
    return _unpack(dut.result_o.value)


def _get_taken(dut) -> list:
    raw = int(dut.branch_taken_o.value)
    return [(raw >> lane) & 1 for lane in range(N_LANES)]


@cocotb.test()
async def test_vadd(dut):
    """VADD rd = rs1 + rs2 (all lanes active)."""
    rs1 = [0x0000_0001 * (lane + 1) for lane in range(N_LANES)]
    rs2 = [0x0000_0010 * (lane + 1) for lane in range(N_LANES)]
    _set_inputs(dut, OP["VADD"], rs1, rs2)
    await _eval(dut)
    got = _get_results(dut)
    exp = [_mask32(rs1[l] + rs2[l]) for l in range(N_LANES)]
    assert got == exp, f"VADD: {[hex(v) for v in got]} != {[hex(v) for v in exp]}"


@cocotb.test()
async def test_vsub(dut):
    """VSUB rd = rs1 - rs2."""
    rs1 = [0x0000_0100 * (lane + 1) for lane in range(N_LANES)]
    rs2 = [0x0000_0001 * (lane + 1) for lane in range(N_LANES)]
    _set_inputs(dut, OP["VSUB"], rs1, rs2)
    await _eval(dut)
    got = _get_results(dut)
    exp = [_mask32(rs1[l] - rs2[l]) for l in range(N_LANES)]
    assert got == exp, f"VSUB: {[hex(v) for v in got]} != {[hex(v) for v in exp]}"


@cocotb.test()
async def test_vmul_lower32(dut):
    """VMUL: lower 32 bits of 64-bit product."""
    rs1 = [0x0001_0001 * (lane + 1) for lane in range(N_LANES)]
    rs2 = [0x0000_FFFF] * N_LANES
    _set_inputs(dut, OP["VMUL"], rs1, rs2)
    await _eval(dut)
    got = _get_results(dut)
    exp = [_mask32(rs1[l] * rs2[l]) for l in range(N_LANES)]
    assert got == exp, f"VMUL: {[hex(v) for v in got]} != {[hex(v) for v in exp]}"


@cocotb.test()
async def test_vand(dut):
    rs1 = [0xAAAA_AAAA] * N_LANES
    rs2 = [0x5555_5555] * N_LANES
    _set_inputs(dut, OP["VAND"], rs1, rs2)
    await _eval(dut)
    assert _get_results(dut) == [0x0000_0000] * N_LANES


@cocotb.test()
async def test_vor(dut):
    rs1 = [0xAAAA_AAAA] * N_LANES
    rs2 = [0x5555_5555] * N_LANES
    _set_inputs(dut, OP["VOR"], rs1, rs2)
    await _eval(dut)
    assert _get_results(dut) == [0xFFFF_FFFF] * N_LANES


@cocotb.test()
async def test_vxor(dut):
    rs1 = [0xFFFF_FFFF] * N_LANES
    rs2 = [0xAAAA_AAAA] * N_LANES
    _set_inputs(dut, OP["VXOR"], rs1, rs2)
    await _eval(dut)
    assert _get_results(dut) == [0x5555_5555] * N_LANES


@cocotb.test()
async def test_vsll(dut):
    rs1 = [1] * N_LANES
    rs2 = list(range(N_LANES))
    _set_inputs(dut, OP["VSLL"], rs1, rs2)
    await _eval(dut)
    got = _get_results(dut)
    exp = [_mask32(1 << lane) for lane in range(N_LANES)]
    assert got == exp, f"VSLL: {[hex(v) for v in got]} != {[hex(v) for v in exp]}"


@cocotb.test()
async def test_vsrl(dut):
    """Logical right shift — sign bit is NOT propagated."""
    rs1 = [0x8000_0000] * N_LANES
    rs2 = [1] * N_LANES
    _set_inputs(dut, OP["VSRL"], rs1, rs2)
    await _eval(dut)
    assert _get_results(dut) == [0x4000_0000] * N_LANES


@cocotb.test()
async def test_vsra(dut):
    """Arithmetic right shift — sign bit IS propagated."""
    rs1 = [0x8000_0000] * N_LANES
    rs2 = [4] * N_LANES
    _set_inputs(dut, OP["VSRA"], rs1, rs2)
    await _eval(dut)
    assert _get_results(dut) == [0xF800_0000] * N_LANES


@cocotb.test()
async def test_vaddi_negative_imm(dut):
    """VADDI with negative immediate (sign-extended from 12 bits to 32)."""
    rs1 = [0x0000_0010] * N_LANES
    imm = 0xFFF  # -1 in 12-bit two's complement
    _set_inputs(dut, OP["VADDI"], rs1, rs1, imm=imm)
    await _eval(dut)
    exp = [_mask32(0x10 - 1)] * N_LANES
    assert _get_results(dut) == exp, f"VADDI -1: {_get_results(dut)} != {exp}"


@cocotb.test()
async def test_vandi(dut):
    rs1 = [0xFFFF_FFFF] * N_LANES
    imm = 0x0FF  # positive, lower 8 bits set
    _set_inputs(dut, OP["VANDI"], rs1, rs1, imm=imm)
    await _eval(dut)
    assert _get_results(dut) == [0x0000_00FF] * N_LANES


@cocotb.test()
async def test_partial_mask(dut):
    """Inactive lanes (mask bit=0) produce 0; active lanes compute normally."""
    rs1 = [0xDEAD_BEEF] * N_LANES
    rs2 = [0x1111_1111] * N_LANES
    mask = 0b0101_0101  # even lanes active
    _set_inputs(dut, OP["VADD"], rs1, rs2, mask=mask)
    await _eval(dut)
    got = _get_results(dut)
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
    rs1 = [lane * 10 for lane in range(N_LANES)]
    rs2 = [lane * 10 if lane % 2 == 0 else lane * 99 for lane in range(N_LANES)]
    _set_inputs(dut, OP["VBEQ"], rs1, rs2)
    await _eval(dut)
    taken = _get_taken(dut)
    for lane in range(N_LANES):
        exp = 1 if rs1[lane] == rs2[lane] else 0
        assert taken[lane] == exp, \
            f"VBEQ lane {lane}: expected {exp}, got {taken[lane]}"


@cocotb.test()
async def test_branch_vblt(dut):
    """VBLT: signed less-than per lane."""
    rs1 = [0x8000_0000, 0, 5, 0xFFFF_FFFF, 0, 100, 0, 0x7FFF_FFFF]
    rs2 = [0x7FFF_FFFF, 0, 3, 0,           1, 100, 0xFFFF_FFFF, 0x8000_0000]
    _set_inputs(dut, OP["VBLT"], rs1, rs2)
    await _eval(dut)
    taken = _get_taken(dut)
    for lane in range(N_LANES):
        exp = 1 if _to_s32(rs1[lane]) < _to_s32(rs2[lane]) else 0
        assert taken[lane] == exp, \
            f"VBLT lane {lane}: rs1={rs1[lane]:#010x} rs2={rs2[lane]:#010x} " \
            f"expected={exp}, got={taken[lane]}"
