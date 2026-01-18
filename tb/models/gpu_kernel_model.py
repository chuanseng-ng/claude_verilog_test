"""
GPU SIMT Kernel Execution Model

Instruction-accurate model of GPU SIMT execution per PHASE4_GPU_ARCHITECTURE_SPEC.md.
Implements 8-lane warp execution with basic divergence handling.
"""

from typing import Optional
from .memory_model import MemoryModel


class GPUKernelModel:
    """
    GPU SIMT kernel execution model.

    Implements the execution model defined in PHASE4_GPU_ARCHITECTURE_SPEC.md
    with 8-lane warps, round-robin scheduling, and one-level divergence.
    """

    # GPU Instruction opcodes (simplified encoding)
    # Using similar encoding to RISC-V for simplicity
    OP_VADD = 0b0110011
    OP_VADDI = 0b0010011
    OP_VSUB = 0b0110011
    OP_VMUL = 0b0110011
    OP_VAND = 0b0110011
    OP_VANDI = 0b0010011
    OP_VOR = 0b0110011
    OP_VORI = 0b0010011
    OP_VXOR = 0b0110011
    OP_VXORI = 0b0010011
    OP_VSLL = 0b0110011
    OP_VSRL = 0b0110011
    OP_VSRA = 0b0110011
    OP_VLD = 0b0000011
    OP_VST = 0b0100011
    OP_VBEQ = 0b1100011
    OP_VBNE = 0b1100011
    OP_VBLT = 0b1100011
    OP_VBGE = 0b1100011
    OP_VJMP = 0b1101111
    OP_VRET = 0b1110011
    OP_VMOV_SPECIAL = 0b1110111  # Custom opcode for VMOV tid/bid
    OP_VSYNC = 0b0001111

    # funct3 values for disambiguation
    FUNCT3_ADD = 0b000
    FUNCT3_SUB = 0b000
    FUNCT3_MUL = 0b001
    FUNCT3_AND = 0b111
    FUNCT3_OR = 0b110
    FUNCT3_XOR = 0b100
    FUNCT3_SLL = 0b001
    FUNCT3_SRL = 0b101
    FUNCT3_SRA = 0b101
    FUNCT3_BEQ = 0b000
    FUNCT3_BNE = 0b001
    FUNCT3_BLT = 0b100
    FUNCT3_BGE = 0b101

    # funct7 values
    FUNCT7_ADD = 0b0000000
    FUNCT7_SUB = 0b0100000
    FUNCT7_MUL = 0b0000001
    FUNCT7_SRL = 0b0000000
    FUNCT7_SRA = 0b0100000

    # Special register indices (for VMOV_SPECIAL instruction, rs1 field)
    # These must fit in 5 bits (0-31) as they go in the rs1 field
    SREG_TID_X = 0
    SREG_TID_Y = 1
    SREG_TID_Z = 2
    SREG_BID_X = 3
    SREG_BID_Y = 4
    SREG_BID_Z = 5

    def __init__(self, warp_size: int = 8):
        """
        Initialize GPU model.

        Args:
            warp_size: Number of lanes per warp (default 8, fixed in Phase 4)
        """
        self.warp_size = warp_size
        self.memory = MemoryModel()
        self.reset()

    def reset(self):
        """Reset GPU to initial state."""
        # Grid/block configuration
        self.grid_dim = (1, 1, 1)
        self.block_dim = (1, 1, 1)

        # Kernel program
        self.kernel_addr = 0
        self.kernel_instructions = {}

        # Execution state
        self.warps = []  # List of warp states
        self.current_warp_idx = 0

        # Statistics
        self.cycle_count = 0
        self.completed_warps = 0

    def configure(self, grid_dim: tuple, block_dim: tuple, kernel_addr: int):
        """
        Configure kernel dimensions.

        Args:
            grid_dim: (grid_x, grid_y, grid_z)
            block_dim: (block_x, block_y, block_z)
            kernel_addr: Kernel instruction start address
        """
        self.grid_dim = grid_dim
        self.block_dim = block_dim
        self.kernel_addr = kernel_addr

        # Calculate total warps
        threads_per_block = block_dim[0] * block_dim[1] * block_dim[2]
        warps_per_block = (threads_per_block + self.warp_size - 1) // self.warp_size
        total_blocks = grid_dim[0] * grid_dim[1] * grid_dim[2]

        # Initialize warps
        self.warps = []
        warp_global_id = 0
        for bz in range(grid_dim[2]):
            for by in range(grid_dim[1]):
                for bx in range(grid_dim[0]):
                    block_id = (bx, by, bz)
                    for warp_id in range(warps_per_block):
                        warp = self._create_warp(block_id, warp_id, warp_global_id)
                        self.warps.append(warp)
                        warp_global_id += 1

    def _create_warp(self, block_id: tuple, warp_id: int, warp_global_id: int) -> dict:
        """Create a new warp state."""
        return {
            'warp_id': warp_global_id,
            'block_id': block_id,
            'warp_in_block': warp_id,
            'pc': self.kernel_addr,
            'active_mask': 0xFF,  # All 8 lanes active initially
            'done': False,
            'regs': [[0] * 32 for _ in range(self.warp_size)],  # 8 lanes x 32 regs
            'divergence_stack': []  # Stack for divergence: [(pc, mask), ...]
        }

    def _compute_thread_id(self, block_id: tuple, warp_in_block: int, lane: int) -> tuple:
        """
        Compute thread ID (tid.x, tid.y, tid.z) for a lane.

        Args:
            block_id: (bx, by, bz)
            warp_in_block: Warp index within block
            lane: Lane index (0-7)

        Returns:
            (tid_x, tid_y, tid_z)
        """
        # Compute global thread index within block
        thread_in_block = warp_in_block * self.warp_size + lane

        # Convert to 3D thread ID
        block_x, block_y, block_z = self.block_dim
        tid_x = thread_in_block % block_x
        tid_y = (thread_in_block // block_x) % block_y
        tid_z = thread_in_block // (block_x * block_y)

        return (tid_x, tid_y, tid_z)

    def load_kernel(self, instructions: dict[int, int]):
        """
        Load kernel instructions into memory.

        Args:
            instructions: Dictionary mapping {address: instruction_word}
        """
        self.kernel_instructions = instructions.copy()

    def execute_kernel(self) -> dict:
        """
        Execute kernel to completion.

        Returns:
            Dictionary with:
                - 'cycles': Total execution cycles
                - 'memory': Final memory state (reference to MemoryModel)
                - 'completed_warps': Number of warps completed
        """
        self.cycle_count = 0
        self.completed_warps = 0

        while not self._all_warps_done():
            # Schedule next warp (round-robin)
            warp = self._schedule_warp()

            if warp is not None and not warp['done']:
                # Execute one instruction for this warp
                self._execute_warp_instruction(warp)

            self.cycle_count += 1

            # Safety check to prevent infinite loops
            if self.cycle_count > 1000000:
                raise RuntimeError("Kernel exceeded maximum cycle count (possible infinite loop)")

        return {
            'cycles': self.cycle_count,
            'memory': self.memory,
            'completed_warps': self.completed_warps
        }

    def _all_warps_done(self) -> bool:
        """Check if all warps are done."""
        return all(warp['done'] for warp in self.warps)

    def _schedule_warp(self) -> Optional[dict]:
        """
        Schedule next warp using round-robin.

        Returns:
            Next warp to execute, or None if all done
        """
        if self._all_warps_done():
            return None

        # Round-robin scheduling
        for _ in range(len(self.warps)):
            warp = self.warps[self.current_warp_idx]
            self.current_warp_idx = (self.current_warp_idx + 1) % len(self.warps)

            if not warp['done']:
                return warp

        return None

    def _execute_warp_instruction(self, warp: dict):
        """
        Execute one instruction for a warp.

        Args:
            warp: Warp state dictionary
        """
        # Fetch instruction
        pc = warp['pc']
        if pc not in self.kernel_instructions:
            # No instruction, treat as VRET
            warp['done'] = True
            self.completed_warps += 1
            return

        insn = self.kernel_instructions[pc]

        # Decode instruction
        opcode = insn & 0x7F
        rd = (insn >> 7) & 0x1F
        funct3 = (insn >> 12) & 0x7
        rs1 = (insn >> 15) & 0x1F
        rs2 = (insn >> 20) & 0x1F
        funct7 = (insn >> 25) & 0x7F

        # Execute based on opcode
        if opcode == self.OP_VRET:
            # Warp completed
            warp['done'] = True
            self.completed_warps += 1
            return

        # Default: increment PC
        next_pc = pc + 4

        # Execute instruction type
        if opcode == self.OP_VADD or opcode == self.OP_VADDI:
            next_pc = self._execute_alu(warp, insn, opcode, rd, rs1, rs2, funct3, funct7)
        elif opcode == self.OP_VLD:
            next_pc = self._execute_load(warp, insn, rd, rs1, funct3)
        elif opcode == self.OP_VST:
            next_pc = self._execute_store(warp, insn, rs1, rs2, funct3)
        elif opcode in [self.OP_VBEQ, self.OP_VBNE, self.OP_VBLT, self.OP_VBGE]:
            next_pc = self._execute_branch(warp, insn, rs1, rs2, funct3)
        elif opcode == self.OP_VJMP:
            next_pc = self._execute_jump(warp, insn)
        elif opcode == self.OP_VMOV_SPECIAL:
            next_pc = self._execute_mov_special(warp, insn, rd, rs1)
        elif opcode == self.OP_VSYNC:
            # Barrier - all lanes in warp sync (no-op for single-warp execution)
            pass
        else:
            # Unknown instruction, skip
            pass

        warp['pc'] = next_pc

    def _execute_alu(self, warp: dict, insn: int, opcode: int, rd: int, rs1: int,
                     rs2: int, funct3: int, funct7: int) -> int:
        """Execute ALU instruction across all active lanes."""
        imm = None
        if opcode == self.OP_VADDI:
            # I-type immediate
            imm = (insn >> 20) & 0xFFF
            imm = self._sign_extend(imm, 12)

        for lane in range(self.warp_size):
            if warp['active_mask'] & (1 << lane):
                val1 = warp['regs'][lane][rs1]
                val2 = warp['regs'][lane][rs2] if imm is None else imm

                # Perform operation based on funct3/funct7
                if funct3 == self.FUNCT3_ADD:
                    if opcode == self.OP_VADDI or funct7 == self.FUNCT7_ADD:
                        result = (val1 + val2) & 0xFFFFFFFF
                    elif funct7 == self.FUNCT7_SUB:
                        result = (val1 - val2) & 0xFFFFFFFF
                    else:
                        result = (val1 + val2) & 0xFFFFFFFF
                elif funct3 == self.FUNCT3_MUL:
                    result = (val1 * val2) & 0xFFFFFFFF
                elif funct3 == self.FUNCT3_AND:
                    result = val1 & val2
                elif funct3 == self.FUNCT3_OR:
                    result = val1 | val2
                elif funct3 == self.FUNCT3_XOR:
                    result = val1 ^ val2
                elif funct3 == self.FUNCT3_SLL:
                    shamt = val2 & 0x1F
                    result = (val1 << shamt) & 0xFFFFFFFF
                elif funct3 == self.FUNCT3_SRL:
                    shamt = val2 & 0x1F
                    if funct7 == self.FUNCT7_SRL:
                        result = val1 >> shamt
                    else:  # SRA
                        if val1 & 0x80000000:
                            result = (val1 >> shamt) | (0xFFFFFFFF << (32 - shamt))
                        else:
                            result = val1 >> shamt
                        result &= 0xFFFFFFFF
                else:
                    result = 0

                # Write result
                if rd != 0:  # r0 hardwired to zero
                    warp['regs'][lane][rd] = result

        return warp['pc'] + 4

    def _execute_load(self, warp: dict, insn: int, rd: int, rs1: int, funct3: int) -> int:
        """Execute load instruction (may be coalesced or serialized)."""
        imm = (insn >> 20) & 0xFFF
        imm = self._sign_extend(imm, 12)

        # Simplified: serialize all loads
        for lane in range(self.warp_size):
            if warp['active_mask'] & (1 << lane):
                addr = (warp['regs'][lane][rs1] + imm) & 0xFFFFFFFF
                try:
                    data = self.memory.read(addr, 4)
                    if rd != 0:
                        warp['regs'][lane][rd] = data
                except:
                    # Memory access failed, write 0
                    if rd != 0:
                        warp['regs'][lane][rd] = 0

        return warp['pc'] + 4

    def _execute_store(self, warp: dict, insn: int, rs1: int, rs2: int, funct3: int) -> int:
        """Execute store instruction (may be coalesced or serialized)."""
        # Decode S-type immediate
        imm = (((insn >> 25) & 0x7F) << 5) | ((insn >> 7) & 0x1F)
        imm = self._sign_extend(imm, 12)

        # Simplified: serialize all stores
        for lane in range(self.warp_size):
            if warp['active_mask'] & (1 << lane):
                addr = (warp['regs'][lane][rs1] + imm) & 0xFFFFFFFF
                data = warp['regs'][lane][rs2]
                try:
                    self.memory.write(addr, data, 4)
                except:
                    # Memory access failed, ignore
                    pass

        return warp['pc'] + 4

    def _execute_branch(self, warp: dict, insn: int, rs1: int, rs2: int, funct3: int) -> int:
        """Execute branch with divergence handling (one level)."""
        # Decode B-type immediate
        imm = (
            ((insn >> 31) & 0x1) << 12 |
            ((insn >> 7) & 0x1) << 11 |
            ((insn >> 25) & 0x3F) << 5 |
            ((insn >> 8) & 0xF) << 1
        )
        imm = self._sign_extend(imm, 13)

        # Evaluate condition for each lane
        mask_taken = 0
        mask_not_taken = 0

        for lane in range(self.warp_size):
            if warp['active_mask'] & (1 << lane):
                val1 = warp['regs'][lane][rs1]
                val2 = warp['regs'][lane][rs2]

                # Convert to signed
                sval1 = val1 if val1 < 0x80000000 else val1 - 0x100000000
                sval2 = val2 if val2 < 0x80000000 else val2 - 0x100000000

                branch_taken = False
                if funct3 == self.FUNCT3_BEQ:
                    branch_taken = (val1 == val2)
                elif funct3 == self.FUNCT3_BNE:
                    branch_taken = (val1 != val2)
                elif funct3 == self.FUNCT3_BLT:
                    branch_taken = (sval1 < sval2)
                elif funct3 == self.FUNCT3_BGE:
                    branch_taken = (sval1 >= sval2)

                if branch_taken:
                    mask_taken |= (1 << lane)
                else:
                    mask_not_taken |= (1 << lane)

        # Handle divergence
        if mask_taken != 0 and mask_not_taken != 0:
            # Divergence: push not-taken path, execute taken path first
            not_taken_pc = warp['pc'] + 4
            warp['divergence_stack'].append((not_taken_pc, mask_not_taken))
            warp['active_mask'] = mask_taken
            return (warp['pc'] + imm) & 0xFFFFFFFF
        elif mask_taken != 0:
            # All active lanes take branch
            return (warp['pc'] + imm) & 0xFFFFFFFF
        else:
            # All active lanes don't take branch
            return warp['pc'] + 4

    def _execute_jump(self, warp: dict, insn: int) -> int:
        """Execute unconditional jump."""
        # Decode J-type immediate
        imm = (
            ((insn >> 31) & 0x1) << 20 |
            ((insn >> 12) & 0xFF) << 12 |
            ((insn >> 20) & 0x1) << 11 |
            ((insn >> 21) & 0x3FF) << 1
        )
        imm = self._sign_extend(imm, 21)
        return (warp['pc'] + imm) & 0xFFFFFFFF

    def _execute_mov_special(self, warp: dict, insn: int, rd: int, rs1: int) -> int:
        """Execute VMOV rd, tid.x/tid.y/tid.z/bid.x/bid.y/bid.z."""
        # rs1 encodes which special register to read
        special_reg = rs1

        for lane in range(self.warp_size):
            if warp['active_mask'] & (1 << lane):
                tid = self._compute_thread_id(
                    warp['block_id'],
                    warp['warp_in_block'],
                    lane
                )

                if special_reg == self.SREG_TID_X:
                    value = tid[0]
                elif special_reg == self.SREG_TID_Y:
                    value = tid[1]
                elif special_reg == self.SREG_TID_Z:
                    value = tid[2]
                elif special_reg == self.SREG_BID_X:
                    value = warp['block_id'][0]
                elif special_reg == self.SREG_BID_Y:
                    value = warp['block_id'][1]
                elif special_reg == self.SREG_BID_Z:
                    value = warp['block_id'][2]
                else:
                    value = 0

                if rd != 0:
                    warp['regs'][lane][rd] = value

        return warp['pc'] + 4

    def _sign_extend(self, value: int, bits: int) -> int:
        """Sign extend a value from bits to 32 bits."""
        sign_bit = 1 << (bits - 1)
        if value & sign_bit:
            return value | (~((1 << bits) - 1) & 0xFFFFFFFF)
        else:
            return value

    def mem_read(self, addr: int, size: int = 4) -> int:
        """Read from GPU memory (convenience wrapper)."""
        return self.memory.read(addr, size)

    def mem_write(self, addr: int, data: int, size: int = 4):
        """Write to GPU memory (convenience wrapper)."""
        self.memory.write(addr, data, size)
