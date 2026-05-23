"""
GPU instruction assembler for Phase 4 RTL tests.

Instruction format (all instructions use same field layout):
  [31:25] imm[11:5]  [24:20] rs2/imm[4:0]  [19:15] rs1
  [14:12] funct3(0)  [11:7]  rd              [6:0]  opcode

Key encoding constraint for VST and branch instructions:
  dec_rs2  = dec_instr[24:20] = imm[4:0]
  dec_imm  = dec_instr[31:20] (12-bit signed offset)

For VST: rs2 (data register) index appears as the low 5 bits of the
address offset imm. Use vst_at() which computes the needed imm.

For branches: rs2 (compare register) index = imm[4:0]. Use a register
whose index equals offset & 0x1F, OR use choose_branch_rs2() to find
a valid rs2 for a given offset.
"""

# -------------------------------------------------------------------
# Opcode constants (from gpu_pkg.sv)
# -------------------------------------------------------------------
VADD        = 0x01
VSUB        = 0x02
VMUL        = 0x03
VAND        = 0x04
VOR         = 0x05
VXOR        = 0x06
VSLL        = 0x07
VSRL        = 0x08
VSRA        = 0x09
VADDI       = 0x11
VANDI       = 0x12
VORI        = 0x13
VXORI       = 0x14
VLD         = 0x20
VST         = 0x21
VLDS        = 0x22
VSTS        = 0x23
VBEQ        = 0x30
VBNE        = 0x31
VBLT        = 0x32
VBGE        = 0x33
VJMP        = 0x38
VRET        = 0x3F
VMOV_TID_X  = 0x40
VMOV_TID_Y  = 0x41
VMOV_TID_Z  = 0x42
VMOV_BID_X  = 0x46
VMOV_BID_Y  = 0x47
VMOV_BID_Z  = 0x48
VSYNC       = 0x50

N_LANES = 8

# -------------------------------------------------------------------
# Instruction encoders
# -------------------------------------------------------------------

def _imm12(v: int) -> int:
    """Clamp v to 12-bit two's-complement (returns the 12-bit pattern)."""
    v &= 0xFFF
    return v


def r_instr(opcode: int, rd: int, rs1: int, rs2: int) -> int:
    """R-type: result = op(rs1[l], rs2[l]) → rd[l]."""
    return ((rs2 & 0x1F) << 20) | ((rs1 & 0x1F) << 15) | ((rd & 0x1F) << 7) | (opcode & 0x7F)


def i_instr(opcode: int, rd: int, rs1: int, imm: int) -> int:
    """I-type: result = op(rs1[l], sign_extend(imm)) → rd[l]."""
    return (_imm12(imm) << 20) | ((rs1 & 0x1F) << 15) | ((rd & 0x1F) << 7) | (opcode & 0x7F)


# Convenience wrappers
def vadd(rd, rs1, rs2):   return r_instr(VADD, rd, rs1, rs2)
def vsub(rd, rs1, rs2):   return r_instr(VSUB, rd, rs1, rs2)
def vmul(rd, rs1, rs2):   return r_instr(VMUL, rd, rs1, rs2)
def vand(rd, rs1, rs2):   return r_instr(VAND, rd, rs1, rs2)
def vor(rd, rs1, rs2):    return r_instr(VOR,  rd, rs1, rs2)
def vxor(rd, rs1, rs2):   return r_instr(VXOR, rd, rs1, rs2)
def vsll(rd, rs1, rs2):   return r_instr(VSLL, rd, rs1, rs2)
def vsrl(rd, rs1, rs2):   return r_instr(VSRL, rd, rs1, rs2)
def vsra(rd, rs1, rs2):   return r_instr(VSRA, rd, rs1, rs2)

def vaddi(rd, rs1, imm):  return i_instr(VADDI, rd, rs1, imm)
def vandi(rd, rs1, imm):  return i_instr(VANDI, rd, rs1, imm)
def vori(rd, rs1, imm):   return i_instr(VORI,  rd, rs1, imm)
def vxori(rd, rs1, imm):  return i_instr(VXORI, rd, rs1, imm)


def vld(rd: int, rs1: int, offset: int = 0) -> int:
    """VLD rd, [rs1+offset]: load word.  rs2 field encodes offset[4:0] (harmless)."""
    return i_instr(VLD, rd, rs1, offset)


def vst(rs2_data: int, rs1_base: int, base_offset: int = 0) -> int:
    """VST [rs1_base + eff_offset], rs2_data.

    CRITICAL ENCODING: dec_rs2 = imm[4:0] = rs2_data index.  The effective
    address offset = sign_extend({imm[11:5], rs2_data_index}).  This function
    bakes rs2_data's index into the low 5 bits of the imm, so the actual byte
    address used is:

        addr[lane] = rs1_base[lane] + base_offset_aligned + rs2_data_index

    where base_offset_aligned must be a multiple of 32.  Caller should plan
    base addresses accordingly (use vst_offset_for() to get the needed
    rs1 base value).
    """
    imm = (_imm12(base_offset) & ~0x1F) | (rs2_data & 0x1F)
    return (imm << 20) | ((rs1_base & 0x1F) << 15) | (0x21)


def vlds(rd: int, rs1: int, offset: int = 0) -> int:
    """VLDS rd, [rs1+offset]: load word from shared memory.  Encoding mirrors VLD."""
    return i_instr(VLDS, rd, rs1, offset)


def vsts(rs2_data: int, rs1_base: int, base_offset: int = 0) -> int:
    """VSTS [rs1_base + eff_offset], rs2_data: store word to shared memory.

    Encoding mirrors VST: rs2 index baked into imm[4:0]; base_offset must be
    a multiple of 32.  eff_offset = base_offset + rs2_data_index.
    """
    imm = (_imm12(base_offset) & ~0x1F) | (rs2_data & 0x1F)
    return (imm << 20) | ((rs1_base & 0x1F) << 15) | (VSTS & 0x7F)


def vst_effective_offset(rs2_data: int, base_offset_hi_mult32: int = 0) -> int:
    """Return the effective byte offset that vst() will apply.

    eff_offset = base_offset_hi_mult32 (a multiple of 32) + rs2_data_index
    """
    return base_offset_hi_mult32 + (rs2_data & 0x1F)


def vmov_tid_x(rd):
    """VMOV_TID_X rd: rd[l] = l (0..N_LANES-1)."""
    return (0 << 20) | (0 << 15) | ((rd & 0x1F) << 7) | VMOV_TID_X


def vmov_bid_x(rd):
    """VMOV_BID_X rd: rd[l] = warp_id."""
    return (0 << 20) | (0 << 15) | ((rd & 0x1F) << 7) | VMOV_BID_X


def vret():
    return VRET


def vsync():
    return VSYNC


def vjmp(offset: int) -> int:
    """VJMP offset: unconditional PC-relative jump.  Offset in bytes."""
    return (_imm12(offset) << 20) | VJMP


def vbranch(opcode: int, rs1: int, rs2: int, pc_of_instr: int, target_pc: int) -> int:
    """Branch instruction.

    ENCODING: rs2 index appears in imm[4:0], so target_pc offset[4:0] must
    equal rs2 index for consistent encoding.  Use branch_rs2_for() to find
    a compatible rs2 register for a given offset.

    offset = target_pc - pc_of_instr  (must fit in 12-bit signed, in bytes)
    """
    offset = target_pc - pc_of_instr
    imm = (_imm12(offset) & ~0x1F) | (rs2 & 0x1F)
    # Verify consistency
    assert (imm & 0x1F) == (rs2 & 0x1F), f"offset[4:0]={offset&0x1F} != rs2={rs2}"
    return (imm << 20) | ((rs1 & 0x1F) << 15) | (opcode & 0x7F)


def branch_rs2_for(offset_bytes: int) -> int:
    """Return the register index that encodes rs2 for a given branch offset."""
    return offset_bytes & 0x1F


def vbeq(rs1, rs2, pc_of_instr, target_pc):
    return vbranch(VBEQ, rs1, rs2, pc_of_instr, target_pc)

def vbne(rs1, rs2, pc_of_instr, target_pc):
    return vbranch(VBNE, rs1, rs2, pc_of_instr, target_pc)

def vblt(rs1, rs2, pc_of_instr, target_pc):
    return vbranch(VBLT, rs1, rs2, pc_of_instr, target_pc)

def vbge(rs1, rs2, pc_of_instr, target_pc):
    return vbranch(VBGE, rs1, rs2, pc_of_instr, target_pc)


# -------------------------------------------------------------------
# Kernel assembler helper
# -------------------------------------------------------------------

class Kernel:
    """Build an instruction dict for gpu_top tests."""

    def __init__(self, base_pc: int = 0):
        self._base   = base_pc
        self._words  = []   # instruction words in program order

    def emit(self, word: int) -> int:
        """Append one instruction; return its PC."""
        pc = self._base + len(self._words) * 4
        self._words.append(word & 0xFFFF_FFFF)
        return pc

    def pc(self) -> int:
        """PC of the next instruction to be emitted."""
        return self._base + len(self._words) * 4

    def patch(self, instr_pc: int, word: int):
        """Overwrite an already-emitted instruction (for forward references)."""
        idx = (instr_pc - self._base) // 4
        self._words[idx] = word & 0xFFFF_FFFF

    def instructions(self) -> dict:
        """Return {pc: word} dict suitable for instr_responder()."""
        return {self._base + i * 4: w for i, w in enumerate(self._words)}


# -------------------------------------------------------------------
# AXI4-Lite / AXI4 memory responders (for use in cocotb tests)
# -------------------------------------------------------------------

async def instr_responder(dut, instrs: dict, latency: int = 0):
    """Serve instruction fetches on m_axil_if_*.

    arready is held high permanently so the AR handshake completes in the
    same cycle arvalid is asserted.  gpu_compute_unit only holds arvalid for
    one cycle (it drops when the scheduler marks the warp busy), so a
    delayed-arready responder would miss the handshake entirely.
    """
    from cocotb.triggers import RisingEdge
    dut.m_axil_if_arready.value = 1   # always-ready
    dut.m_axil_if_rdata.value   = 0
    dut.m_axil_if_rresp.value   = 0
    dut.m_axil_if_rvalid.value  = 0
    while True:
        await RisingEdge(dut.clk)
        if not int(dut.m_axil_if_arvalid.value):
            continue
        # AR handshake completed this cycle; capture address
        addr = int(dut.m_axil_if_araddr.value)
        for _ in range(latency):
            await RisingEdge(dut.clk)
        word = instrs.get(addr, 0x0000003F)   # default: VRET
        dut.m_axil_if_rdata.value  = word
        dut.m_axil_if_rresp.value  = 0
        dut.m_axil_if_rvalid.value = 1
        await RisingEdge(dut.clk)
        dut.m_axil_if_rvalid.value = 0


async def data_responder(dut, mem: dict, ar_latency: int = 0, r_latency: int = 0,
                         aw_latency: int = 0, w_latency: int = 0):
    """Serve AXI4 data reads/writes on m_axi_*.

    Both arready and awready start high so AXI handshakes complete in the
    same cycle the master asserts arvalid/awvalid.  memory_coalescer only
    holds arvalid/awvalid for one cycle (serial FSM), so delayed-ready
    responses would miss the handshake.
    """
    from cocotb.triggers import RisingEdge
    dut.m_axi_arready.value = 1   # always-ready
    dut.m_axi_rdata.value   = 0
    dut.m_axi_rresp.value   = 0
    dut.m_axi_rvalid.value  = 0
    dut.m_axi_awready.value = 1   # always-ready
    dut.m_axi_wready.value  = 0
    dut.m_axi_bresp.value   = 0
    dut.m_axi_bvalid.value  = 0
    while True:
        await RisingEdge(dut.clk)
        # Handle read request (AR handshake completed this cycle)
        if int(dut.m_axi_arvalid.value):
            addr = int(dut.m_axi_araddr.value)
            dut.m_axi_arready.value = 0   # busy while serving
            for _ in range(ar_latency + r_latency):
                await RisingEdge(dut.clk)
            dut.m_axi_rdata.value  = mem.get(addr, 0)
            dut.m_axi_rresp.value  = 0
            dut.m_axi_rvalid.value = 1
            await RisingEdge(dut.clk)
            dut.m_axi_rvalid.value  = 0
            dut.m_axi_arready.value = 1   # ready again
        # Handle write request (AW handshake completed this cycle)
        elif int(dut.m_axi_awvalid.value):
            addr = int(dut.m_axi_awaddr.value)
            dut.m_axi_awready.value = 0   # busy while serving
            for _ in range(aw_latency):
                await RisingEdge(dut.clk)
            while not int(dut.m_axi_wvalid.value):
                await RisingEdge(dut.clk)
            for _ in range(w_latency):
                await RisingEdge(dut.clk)
            mem[addr] = int(dut.m_axi_wdata.value)
            dut.m_axi_wready.value = 1
            await RisingEdge(dut.clk)
            dut.m_axi_wready.value  = 0
            dut.m_axi_bvalid.value  = 1
            dut.m_axi_bresp.value   = 0
            await RisingEdge(dut.clk)
            dut.m_axi_bvalid.value  = 0
            dut.m_axi_awready.value = 1   # ready again
