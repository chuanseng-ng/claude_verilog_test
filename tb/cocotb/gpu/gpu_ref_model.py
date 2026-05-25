"""
Lightweight reference interpreter for the Phase 4 GPU ISA — matches the actual
RTL/gpu_asm opcode encoding (gpu_pkg.sv), NOT tb/models/gpu_kernel_model.py
(which uses a different, RISC-V-style encoding and has no shared-mem ops).

Scope: single warp of N_LANES lanes, all lanes active, straight-line execution
(ALU R/I-type, VMOV_TID_X/BID_X, VLD/VST global, VLDS/VSTS shared, VSYNC no-op,
VRET terminate). Divergent branches are intentionally out of scope here — they
are covered by the directed kernel_divergence_basic test — so the random-kernel
generator only emits the modeled subset. A branch/jump opcode raises, which
surfaces a generator bug rather than silently desyncing from the RTL.

Semantics mirror vector_alu.sv exactly:
  VADD/VSUB/VMUL(lower32)/VAND/VOR/VXOR, VSLL/VSRL(logical)/VSRA(arith),
  VADDI/VANDI/VORI/VXORI with sign-extended 12-bit imm. r0 reads as 0.
"""
from gpu_asm import (
    N_LANES,
    VADD, VSUB, VMUL, VAND, VOR, VXOR, VSLL, VSRL, VSRA,
    VADDI, VANDI, VORI, VXORI, VLD, VST, VLDS, VSTS,
    VMOV_TID_X, VMOV_BID_X, VSYNC, VRET,
)

MASK32 = 0xFFFF_FFFF


def _sext12(imm: int) -> int:
    imm &= 0xFFF
    return imm - 0x1000 if (imm & 0x800) else imm


def _sext32(v: int) -> int:
    v &= MASK32
    return v - (1 << 32) if (v & 0x8000_0000) else v


class GpuRefModel:
    """Executes a {pc: word} kernel for one warp; records global/shared writes."""

    def __init__(self, n_lanes: int = N_LANES, warp_id: int = 0):
        self.n = n_lanes
        self.warp_id = warp_id
        self.regs = [[0] * n_lanes for _ in range(32)]   # regs[r][lane]
        self.gmem = {}    # byte addr -> 32-bit value (global)
        self.smem = {}    # byte addr -> 32-bit value (shared)

    def _wr(self, rd: int, lane_vals):
        if rd == 0:
            return  # r0 hardwired to zero
        self.regs[rd] = [v & MASK32 for v in lane_vals]

    def run(self, words: dict, max_steps: int = 10000) -> dict:
        """Execute straight-line from pc=0 until VRET. Returns global memory dict."""
        pc = 0
        for _ in range(max_steps):
            if pc not in words:
                break
            word = words[pc] & MASK32
            opcode = word & 0x7F
            rd  = (word >> 7)  & 0x1F
            rs1 = (word >> 15) & 0x1F
            rs2 = (word >> 20) & 0x1F   # = imm[4:0]
            imm12 = (word >> 20) & 0xFFF
            simm = _sext12(imm12)

            a = self.regs[rs1]
            b = self.regs[rs2]

            if opcode == VRET:
                break
            elif opcode == VSYNC:
                pass
            elif opcode == VADD:
                self._wr(rd, [a[l] + b[l] for l in range(self.n)])
            elif opcode == VSUB:
                self._wr(rd, [a[l] - b[l] for l in range(self.n)])
            elif opcode == VMUL:
                self._wr(rd, [a[l] * b[l] for l in range(self.n)])
            elif opcode == VAND:
                self._wr(rd, [a[l] & b[l] for l in range(self.n)])
            elif opcode == VOR:
                self._wr(rd, [a[l] | b[l] for l in range(self.n)])
            elif opcode == VXOR:
                self._wr(rd, [a[l] ^ b[l] for l in range(self.n)])
            elif opcode == VSLL:
                self._wr(rd, [(a[l] << (b[l] & 0x1F)) & MASK32 for l in range(self.n)])
            elif opcode == VSRL:
                self._wr(rd, [(a[l] & MASK32) >> (b[l] & 0x1F) for l in range(self.n)])
            elif opcode == VSRA:
                self._wr(rd, [_sext32(a[l]) >> (b[l] & 0x1F) for l in range(self.n)])
            elif opcode == VADDI:
                self._wr(rd, [a[l] + simm for l in range(self.n)])
            elif opcode == VANDI:
                self._wr(rd, [a[l] & (simm & MASK32) for l in range(self.n)])
            elif opcode == VORI:
                self._wr(rd, [a[l] | (simm & MASK32) for l in range(self.n)])
            elif opcode == VXORI:
                self._wr(rd, [a[l] ^ (simm & MASK32) for l in range(self.n)])
            elif opcode == VMOV_TID_X:
                self._wr(rd, [l for l in range(self.n)])
            elif opcode == VMOV_BID_X:
                self._wr(rd, [self.warp_id for _ in range(self.n)])
            elif opcode == VLD:
                addr = [(a[l] + simm) & MASK32 for l in range(self.n)]
                self._wr(rd, [self.gmem.get(addr[l], 0) for l in range(self.n)])
            elif opcode == VST:
                # data register index = imm[4:0] = rs2 field; addr = rs1 + sext(imm)
                data = self.regs[rs2]
                for l in range(self.n):
                    self.gmem[(a[l] + simm) & MASK32] = data[l] & MASK32
            elif opcode == VLDS:
                addr = [(a[l] + simm) & MASK32 for l in range(self.n)]
                self._wr(rd, [self.smem.get(addr[l], 0) for l in range(self.n)])
            elif opcode == VSTS:
                data = self.regs[rs2]
                for l in range(self.n):
                    self.smem[(a[l] + simm) & MASK32] = data[l] & MASK32
            else:
                raise ValueError(f"GpuRefModel: unsupported opcode 0x{opcode:02x} "
                                 f"at pc=0x{pc:x} (generator should not emit this)")
            pc += 4
        return self.gmem
