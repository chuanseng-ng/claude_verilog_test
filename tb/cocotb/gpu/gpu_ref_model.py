"""
Lightweight reference interpreter for the Phase 4 GPU ISA — matches the actual
RTL/gpu_asm opcode encoding (gpu_pkg.sv), NOT tb/models/gpu_kernel_model.py
(which uses a different, RISC-V-style encoding and has no shared-mem ops).

Scope: single warp of N_LANES lanes, straight-line and single-level-divergent
execution (ALU R/I-type, VMOV_TID_X/BID_X, VLD/VST global, VLDS/VSTS shared,
VSYNC barrier, VRET terminate, and VBLT/VBGE/VBEQ/VBNE/VJMP branch opcodes for
single-level SIMT divergence).

SIMT divergence semantics (single-level stack, matches gpu_compute_unit.sv):
  - Branch: split lanes into taken/not-taken masks.
    * If both masks non-zero: divergent → push (reconverge_pc=fall_through_pc+branch,
      false_mask=not_taken) onto stack; execute true-path lanes (taken mask).
    * If only taken: converging taken → next_pc = branch_target, same mask.
    * If only not-taken: converging not-taken → next_pc = fall-through (pc+4).
  - VRET with non-empty stack → pop stack; continue at (return_pc, return_mask)
    (implements false-path execution after true-path VRET).
  - VRET with empty stack → terminate.
  - VJMP: unconditional PC-relative jump (all active lanes).

Random generator only emits guaranteed-reconverging single-level diamond patterns
and modeled subset ops, so any mismatch is a real datapath bug.
"""
from gpu_asm import (
    N_LANES,
    VADD, VSUB, VMUL, VAND, VOR, VXOR, VSLL, VSRL, VSRA,
    VADDI, VANDI, VORI, VXORI, VLD, VST, VLDS, VSTS,
    VMOV_TID_X, VMOV_BID_X, VSYNC, VRET,
    VBEQ, VBNE, VBLT, VBGE, VJMP,
)

MASK32 = 0xFFFF_FFFF


def _sext12(imm: int) -> int:
    imm &= 0xFFF
    return imm - 0x1000 if (imm & 0x800) else imm


def _sext32(v: int) -> int:
    v &= MASK32
    return v - (1 << 32) if (v & 0x8000_0000) else v


class GpuRefModel:
    """Executes a {pc: word} kernel for one warp; records global/shared writes.

    Args:
        n_lanes:      number of SIMD lanes (default N_LANES=8).
        warp_id:      warp identifier used by VMOV_BID_X (default 0).
        initial_gmem: optional dict {addr: value} pre-seeding global memory
                      before execution (e.g. for VLD input regions). The dict
                      is shallow-copied; the model does not mutate the caller's
                      original.
    """

    def __init__(self, n_lanes: int = N_LANES, warp_id: int = 0,
                 initial_gmem: dict = None):
        self.n = n_lanes
        self.warp_id = warp_id
        self._seed_gmem = dict(initial_gmem) if initial_gmem else {}
        self.regs = [[0] * n_lanes for _ in range(32)]   # regs[r][lane]
        self._initial_addrs = set(self._seed_gmem)
        self.gmem = dict(self._seed_gmem)
        self.smem = {}    # byte addr -> 32-bit value (shared)
        self.gmem_writes = {}  # only VST destinations (no pre-seeded reads)

    def _wr(self, rd: int, lane_vals):
        if rd == 0:
            return  # r0 hardwired to zero
        self.regs[rd] = [v & MASK32 for v in lane_vals]

    def _branch_taken(self, opcode: int, a_lane: int, b_lane: int) -> bool:
        """Return True if the branch condition holds for a single lane."""
        sa = _sext32(a_lane)
        sb = _sext32(b_lane)
        if opcode == VBEQ:
            return (a_lane & MASK32) == (b_lane & MASK32)
        elif opcode == VBNE:
            return (a_lane & MASK32) != (b_lane & MASK32)
        elif opcode == VBLT:
            return sa < sb
        elif opcode == VBGE:
            return sa >= sb
        return False

    def run(self, words: dict, max_steps: int = 50000,
            initial_gmem: dict = None) -> dict:
        """Execute from pc=0 until VRET (empty stack) or max_steps.

        Args:
            words:        {pc: word} instruction dict (from Kernel.instructions()).
            max_steps:    safety limit to prevent infinite loops.
            initial_gmem: alternative way to pass initial global memory when
                          constructing GpuRefModel without the constructor arg.
                          If given here, it overrides the constructor seed for
                          this and subsequent runs.

        Returns:
            self.gmem_writes — only the addresses written by VST during execution.
            Pre-seeded initial_gmem (read-only VLD inputs) is deliberately excluded
            so the scoreboard compares against RTL stores, not seeded reads.
        """
        # Reset per-run state so a reused instance behaves as if freshly built.
        if initial_gmem is not None:
            self._seed_gmem = dict(initial_gmem)
            self._initial_addrs = set(self._seed_gmem)
        self.regs = [[0] * self.n for _ in range(32)]
        self.gmem = dict(self._seed_gmem)
        self.smem = {}
        self.gmem_writes = {}

        # Single-level SIMT divergence stack: list of (return_pc, return_mask)
        # Each entry is the reconvergence context (false-path) to resume after
        # the true-path hits VRET.
        div_stack = []

        # Active mask: set of lane indices currently executing.
        # Start with all lanes active (mirrors warp_mask_i = 0xFF for 8 lanes).
        active_mask = list(range(self.n))  # list of active lane indices

        pc = 0
        for _ in range(max_steps):
            if pc not in words:
                break
            word = words[pc] & MASK32
            opcode = word & 0x7F
            rd  = (word >> 7)  & 0x1F
            rs1 = (word >> 15) & 0x1F
            rs2 = (word >> 20) & 0x1F
            imm12 = (word >> 20) & 0xFFF
            simm = _sext12(imm12)

            # Only active lanes contribute to reads/writes.
            a = self.regs[rs1]
            b = self.regs[rs2]

            if opcode == VRET:
                if div_stack:
                    # Pop: resume false-path (not-taken lanes)
                    return_pc, return_mask_bits = div_stack.pop()
                    # Restore active mask from the bitmask stored on stack
                    active_mask = [lane for lane in range(self.n)
                                   if (return_mask_bits >> lane) & 1]
                    pc = return_pc
                    continue
                else:
                    # Empty stack: warp complete
                    break
            elif opcode == VSYNC:
                pass  # single-warp: barrier is a no-op
            elif opcode in (VBEQ, VBNE, VBLT, VBGE):
                branch_target = (pc + simm) & MASK32
                fall_through  = (pc + 4) & MASK32

                taken_lanes     = [lane for lane in active_mask
                                   if self._branch_taken(opcode, a[lane], b[lane])]
                not_taken_lanes = [lane for lane in active_mask
                                   if not self._branch_taken(opcode, a[lane], b[lane])]

                if taken_lanes and not_taken_lanes:
                    # Divergent: push false-path (not-taken) state, execute true-path
                    false_mask_bits = sum(1 << lane for lane in not_taken_lanes)
                    div_stack.append((fall_through, false_mask_bits))
                    active_mask = taken_lanes
                    pc = branch_target
                    continue
                elif taken_lanes:
                    # All active lanes taken (converging)
                    active_mask = taken_lanes
                    pc = branch_target
                    continue
                else:
                    # All active lanes not taken (converging)
                    active_mask = not_taken_lanes
                    pc = fall_through
                    continue
            elif opcode == VJMP:
                branch_target = (pc + simm) & MASK32
                pc = branch_target
                continue
            elif opcode == VADD:
                vals = [a[lane] + b[lane] for lane in range(self.n)]
                # Only update active lanes; preserve inactive lane values
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VSUB:
                vals = [a[lane] - b[lane] for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VMUL:
                vals = [a[lane] * b[lane] for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VAND:
                vals = [a[lane] & b[lane] for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VOR:
                vals = [a[lane] | b[lane] for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VXOR:
                vals = [a[lane] ^ b[lane] for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VSLL:
                vals = [(a[lane] << (b[lane] & 0x1F)) & MASK32 for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VSRL:
                vals = [(a[lane] & MASK32) >> (b[lane] & 0x1F) for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VSRA:
                vals = [_sext32(a[lane]) >> (b[lane] & 0x1F) for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VADDI:
                vals = [a[lane] + simm for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VANDI:
                vals = [a[lane] & (simm & MASK32) for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VORI:
                vals = [a[lane] | (simm & MASK32) for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VXORI:
                vals = [a[lane] ^ (simm & MASK32) for lane in range(self.n)]
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = vals[lane]
                self._wr(rd, result)
            elif opcode == VMOV_TID_X:
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = lane
                self._wr(rd, result)
            elif opcode == VMOV_BID_X:
                result = list(self.regs[rd])
                for lane in active_mask:
                    result[lane] = self.warp_id
                self._wr(rd, result)
            elif opcode == VLD:
                result = list(self.regs[rd])
                for lane in active_mask:
                    addr = (a[lane] + simm) & MASK32
                    result[lane] = self.gmem.get(addr, 0)
                self._wr(rd, result)
            elif opcode == VST:
                # data register index = imm[4:0] = rs2 field; addr = rs1 + sext(imm)
                data = self.regs[rs2]
                for lane in active_mask:
                    addr = (a[lane] + simm) & MASK32
                    self.gmem[addr] = data[lane] & MASK32
                    self.gmem_writes[addr] = data[lane] & MASK32
            elif opcode == VLDS:
                result = list(self.regs[rd])
                for lane in active_mask:
                    addr = (a[lane] + simm) & MASK32
                    result[lane] = self.smem.get(addr, 0)
                self._wr(rd, result)
            elif opcode == VSTS:
                data = self.regs[rs2]
                for lane in active_mask:
                    self.smem[(a[lane] + simm) & MASK32] = data[lane] & MASK32
            else:
                raise ValueError(f"GpuRefModel: unsupported opcode 0x{opcode:02x} "
                                 f"at pc=0x{pc:x} (generator should not emit this)")
            pc += 4
        return self.gmem_writes
