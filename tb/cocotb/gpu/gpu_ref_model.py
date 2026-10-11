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

Launch contract (bead 6hy6, user decision 2026-10-11) -- block-level helpers below the class:
  - GPU_BLOCK_X must be 1..MAX_BLOCK_THREADS (64 = N_WARPS x N_LANES).  0 or > 64 is a launch
    ERROR (GPU_STATUS reads ERROR, no kernel instruction executes): ``launch_is_error``.
  - A block of BLOCK_X threads runs ceil(BLOCK_X / N_LANES) warps; the last warp starts with
    ONLY its valid lanes active (BLOCK_X=9: warp 0 all 8 lanes, warp 1 lane 0 only):
    ``warp_lane_mask`` -> ``GpuRefModel(init_mask=...)``.  Invalid lanes never write registers,
    shared memory or global memory.
"""
from gpu_asm import (
    N_LANES,
    VADD, VSUB, VMUL, VAND, VOR, VXOR, VSLL, VSRL, VSRA,
    VADDI, VANDI, VORI, VXORI, VLD, VST, VLDS, VSTS,
    VMOV_TID_X, VMOV_BID_X, VSYNC, VRET,
    VBEQ, VBNE, VBLT, VBGE, VJMP,
)

MASK32 = 0xFFFF_FFFF

N_WARPS = 8
MAX_BLOCK_THREADS = N_WARPS * N_LANES   # 64: the frozen Phase 4 limit (8 warps x 8 lanes)


class GpuLaunchError(ValueError):
    """The launch the DUT reports as GPU_STATUS.ERROR (BLOCK_X == 0 or > MAX_BLOCK_THREADS)."""


def launch_is_error(block_x: int) -> bool:
    """True when a launch with this GPU_BLOCK_X raises the GPU ERROR condition."""
    return not 1 <= block_x <= MAX_BLOCK_THREADS


def warps_for_block(block_x: int) -> int:
    """Number of warps a legal block of ``block_x`` threads runs: ceil(block_x / N_LANES)."""
    if launch_is_error(block_x):
        raise GpuLaunchError(f"BLOCK_X={block_x}: legal range is 1..{MAX_BLOCK_THREADS}")
    return -(-block_x // N_LANES)


def warp_lane_mask(block_x: int, warp_id: int, n_lanes: int = N_LANES) -> int:
    """Initial active-lane bitmask of ``warp_id``: lane l is valid iff warp_id*n_lanes + l < block_x."""
    warps_for_block(block_x)   # raises GpuLaunchError on an illegal block size
    return sum(1 << lane for lane in range(n_lanes) if warp_id * n_lanes + lane < block_x)


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
        init_mask:    initial active-lane bitmask (bit l = lane l); default all
                      n_lanes.  Use ``warp_lane_mask`` for a partially filled
                      last warp (bead 6hy6).
    """

    def __init__(self, n_lanes: int = N_LANES, warp_id: int = 0,
                 initial_gmem: dict = None, init_mask: int = None):
        self.n = n_lanes
        self.warp_id = warp_id
        full = (1 << n_lanes) - 1
        self.init_mask = full if init_mask is None else init_mask & full
        self.div_pushes = 0   # divergent branches taken in the last run (mirrors perf_cnt[3])
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

        # Active mask: set of lane indices currently executing.  Starts at init_mask: all lanes
        # for a full warp (0xFF), only the valid lanes for a partially filled last warp.
        active_mask = [lane for lane in range(self.n) if (self.init_mask >> lane) & 1]
        self.div_pushes = 0

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
                    self.div_pushes += 1
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


def run_block(words: dict, block_x: int, initial_gmem: dict = None) -> dict:
    """Reference stores of a whole block: the union of one GpuRefModel run per warp, each with
    its own initial lane mask.  Raises GpuLaunchError where the DUT raises ERROR."""
    stores: dict = {}
    for w in range(warps_for_block(block_x)):
        model = GpuRefModel(warp_id=w, initial_gmem=initial_gmem,
                            init_mask=warp_lane_mask(block_x, w))
        stores.update(model.run(words))
    return stores
