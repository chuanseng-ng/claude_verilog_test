"""
RV32I CPU Reference Model

Instruction-accurate model of RV32I CPU core per PHASE0_ARCHITECTURE_SPEC.md.
Implements all 37 base integer instructions.
"""

from typing import Optional
from .memory_model import MemoryModel, MisalignedAccessError


class IllegalInstructionError(Exception):
    """Exception raised when encountering an illegal instruction."""
    pass


class TrapError(Exception):
    """Exception raised when a trap occurs."""
    def __init__(self, cause: int, message: str):
        self.cause = cause
        super().__init__(message)


class RV32IModel:
    """
    RV32I CPU reference model.

    Implements the exact instruction set and behavior defined in
    PHASE0_ARCHITECTURE_SPEC.md.
    """

    # Trap causes
    TRAP_ILLEGAL_INSTRUCTION = 2

    # Opcodes
    OP_LUI = 0b0110111
    OP_AUIPC = 0b0010111
    OP_JAL = 0b1101111
    OP_JALR = 0b1100111
    OP_BRANCH = 0b1100011
    OP_LOAD = 0b0000011
    OP_STORE = 0b0100011
    OP_OP_IMM = 0b0010011
    OP_OP = 0b0110011

    def __init__(self, reset_pc: int = 0x0000_0000, trap_vector: int = 0x0000_0100):
        """
        Initialize CPU model.

        Args:
            reset_pc: Initial PC value after reset (default 0x0000_0000)
            trap_vector: Address to jump on traps (default 0x0000_0100)
        """
        self.reset_pc = reset_pc
        self.trap_vector = trap_vector
        self.memory = MemoryModel()
        self.reset()

    def reset(self):
        """Reset CPU to initial state per PHASE0_ARCHITECTURE_SPEC.md."""
        self.pc = self.reset_pc
        self.regs = [0] * 32  # x0-x31, all initialized to 0
        self.trap_pending = False
        self.trap_cause = 0
        self.halted = False
        self.cycle_count = 0

    def step(self, instruction: Optional[int] = None) -> dict:
        """
        Execute one instruction.

        Args:
            instruction: 32-bit instruction word. If None, fetch from memory at PC.

        Returns:
            Dictionary with:
                - 'pc': PC before execution
                - 'insn': Instruction word
                - 'rd': Destination register (or None)
                - 'rd_value': Value written to rd (or None)
                - 'mem_addr': Memory address accessed (or None)
                - 'mem_data': Memory data read/written (or None)
                - 'mem_write': True if write, False if read, None if no mem access
                - 'trap': True if trap occurred
                - 'trap_cause': Trap cause code
                - 'next_pc': PC after execution

        Raises:
            IllegalInstructionError: If instruction is illegal
        """
        if self.halted:
            return {
                'pc': self.pc,
                'insn': 0,
                'rd': None,
                'rd_value': None,
                'mem_addr': None,
                'mem_data': None,
                'mem_write': None,
                'trap': False,
                'trap_cause': 0,
                'next_pc': self.pc
            }

        # Fetch instruction
        if instruction is None:
            instruction = self.memory.read(self.pc, 4)

        insn = instruction
        old_pc = self.pc
        result = {
            'pc': old_pc,
            'insn': insn,
            'rd': None,
            'rd_value': None,
            'mem_addr': None,
            'mem_data': None,
            'mem_write': None,
            'trap': False,
            'trap_cause': 0,
            'next_pc': self.pc + 4
        }

        try:
            # Decode and execute
            self._decode_and_execute(insn, result)

            # Update PC
            self.pc = result['next_pc']
            self.cycle_count += 1

        except (IllegalInstructionError, MisalignedAccessError) as e:
            # Trap handling
            result['trap'] = True
            result['trap_cause'] = self.TRAP_ILLEGAL_INSTRUCTION
            result['next_pc'] = self.trap_vector
            self.pc = self.trap_vector
            self.trap_pending = True
            self.trap_cause = self.TRAP_ILLEGAL_INSTRUCTION

        return result

    def _decode_and_execute(self, insn: int, result: dict):
        """Decode and execute instruction, updating result dictionary."""
        # Extract opcode
        opcode = insn & 0x7F

        # Decode based on opcode
        if opcode == self.OP_LUI:
            self._execute_lui(insn, result)
        elif opcode == self.OP_AUIPC:
            self._execute_auipc(insn, result)
        elif opcode == self.OP_JAL:
            self._execute_jal(insn, result)
        elif opcode == self.OP_JALR:
            self._execute_jalr(insn, result)
        elif opcode == self.OP_BRANCH:
            self._execute_branch(insn, result)
        elif opcode == self.OP_LOAD:
            self._execute_load(insn, result)
        elif opcode == self.OP_STORE:
            self._execute_store(insn, result)
        elif opcode == self.OP_OP_IMM:
            self._execute_op_imm(insn, result)
        elif opcode == self.OP_OP:
            self._execute_op(insn, result)
        else:
            raise IllegalInstructionError(f"Unknown opcode: 0x{opcode:02x}")

    def _sign_extend(self, value: int, bits: int) -> int:
        """Sign extend a value from bits to 32 bits."""
        sign_bit = 1 << (bits - 1)
        if value & sign_bit:
            # Negative: extend with 1s
            return value | (~((1 << bits) - 1) & 0xFFFFFFFF)
        else:
            # Positive: already extended with 0s
            return value

    def _write_reg(self, rd: int, value: int):
        """Write to register, enforcing x0 = 0."""
        if rd != 0:
            self.regs[rd] = value & 0xFFFFFFFF

    # U-type instructions
    def _execute_lui(self, insn: int, result: dict):
        """LUI: Load Upper Immediate."""
        rd = (insn >> 7) & 0x1F
        imm = insn & 0xFFFFF000
        self._write_reg(rd, imm)
        result['rd'] = rd
        result['rd_value'] = self.regs[rd]

    def _execute_auipc(self, insn: int, result: dict):
        """AUIPC: Add Upper Immediate to PC."""
        rd = (insn >> 7) & 0x1F
        imm = insn & 0xFFFFF000
        value = (result['pc'] + imm) & 0xFFFFFFFF
        self._write_reg(rd, value)
        result['rd'] = rd
        result['rd_value'] = self.regs[rd]

    # J-type instructions
    def _execute_jal(self, insn: int, result: dict):
        """JAL: Jump and Link."""
        rd = (insn >> 7) & 0x1F

        # Decode J-type immediate
        imm = (
            ((insn >> 31) & 0x1) << 20 |  # imm[20]
            ((insn >> 12) & 0xFF) << 12 |  # imm[19:12]
            ((insn >> 20) & 0x1) << 11 |   # imm[11]
            ((insn >> 21) & 0x3FF) << 1    # imm[10:1]
        )
        imm = self._sign_extend(imm, 21)

        # Save return address
        self._write_reg(rd, (result['pc'] + 4) & 0xFFFFFFFF)
        result['rd'] = rd
        result['rd_value'] = self.regs[rd]

        # Jump
        result['next_pc'] = (result['pc'] + imm) & 0xFFFFFFFF

    def _execute_jalr(self, insn: int, result: dict):
        """JALR: Jump and Link Register."""
        rd = (insn >> 7) & 0x1F
        rs1 = (insn >> 15) & 0x1F
        imm = (insn >> 20) & 0xFFF
        imm = self._sign_extend(imm, 12)

        # Compute target address (set LSB to 0)
        target = (self.regs[rs1] + imm) & 0xFFFFFFFE

        # Save return address
        self._write_reg(rd, (result['pc'] + 4) & 0xFFFFFFFF)
        result['rd'] = rd
        result['rd_value'] = self.regs[rd]

        # Jump
        result['next_pc'] = target

    # B-type instructions
    def _execute_branch(self, insn: int, result: dict):
        """Branch instructions."""
        funct3 = (insn >> 12) & 0x7
        rs1 = (insn >> 15) & 0x1F
        rs2 = (insn >> 20) & 0x1F

        # Decode B-type immediate
        imm = (
            ((insn >> 31) & 0x1) << 12 |   # imm[12]
            ((insn >> 7) & 0x1) << 11 |    # imm[11]
            ((insn >> 25) & 0x3F) << 5 |   # imm[10:5]
            ((insn >> 8) & 0xF) << 1       # imm[4:1]
        )
        imm = self._sign_extend(imm, 13)

        val1 = self.regs[rs1]
        val2 = self.regs[rs2]

        # Convert to signed for comparison
        sval1 = val1 if val1 < 0x80000000 else val1 - 0x100000000
        sval2 = val2 if val2 < 0x80000000 else val2 - 0x100000000

        branch_taken = False
        if funct3 == 0b000:  # BEQ
            branch_taken = (val1 == val2)
        elif funct3 == 0b001:  # BNE
            branch_taken = (val1 != val2)
        elif funct3 == 0b100:  # BLT
            branch_taken = (sval1 < sval2)
        elif funct3 == 0b101:  # BGE
            branch_taken = (sval1 >= sval2)
        elif funct3 == 0b110:  # BLTU
            branch_taken = (val1 < val2)
        elif funct3 == 0b111:  # BGEU
            branch_taken = (val1 >= val2)
        else:
            raise IllegalInstructionError(f"Invalid branch funct3: 0x{funct3:x}")

        if branch_taken:
            result['next_pc'] = (result['pc'] + imm) & 0xFFFFFFFF

    # Load instructions
    def _execute_load(self, insn: int, result: dict):
        """Load instructions."""
        funct3 = (insn >> 12) & 0x7
        rd = (insn >> 7) & 0x1F
        rs1 = (insn >> 15) & 0x1F
        imm = (insn >> 20) & 0xFFF
        imm = self._sign_extend(imm, 12)

        addr = (self.regs[rs1] + imm) & 0xFFFFFFFF
        result['mem_addr'] = addr
        result['mem_write'] = False

        if funct3 == 0b000:  # LB
            data = self.memory.read(addr, 1)
            data = self._sign_extend(data, 8)
        elif funct3 == 0b001:  # LH
            data = self.memory.read(addr, 2)
            data = self._sign_extend(data, 16)
        elif funct3 == 0b010:  # LW
            data = self.memory.read(addr, 4)
        elif funct3 == 0b100:  # LBU
            data = self.memory.read(addr, 1)
        elif funct3 == 0b101:  # LHU
            data = self.memory.read(addr, 2)
        else:
            raise IllegalInstructionError(f"Invalid load funct3: 0x{funct3:x}")

        self._write_reg(rd, data)
        result['rd'] = rd
        result['rd_value'] = self.regs[rd]
        result['mem_data'] = data

    # Store instructions
    def _execute_store(self, insn: int, result: dict):
        """Store instructions."""
        funct3 = (insn >> 12) & 0x7
        rs1 = (insn >> 15) & 0x1F
        rs2 = (insn >> 20) & 0x1F

        # Decode S-type immediate
        imm = (
            ((insn >> 25) & 0x7F) << 5 |   # imm[11:5]
            ((insn >> 7) & 0x1F)           # imm[4:0]
        )
        imm = self._sign_extend(imm, 12)

        addr = (self.regs[rs1] + imm) & 0xFFFFFFFF
        data = self.regs[rs2]

        result['mem_addr'] = addr
        result['mem_data'] = data
        result['mem_write'] = True

        if funct3 == 0b000:  # SB
            self.memory.write(addr, data & 0xFF, 1)
        elif funct3 == 0b001:  # SH
            self.memory.write(addr, data & 0xFFFF, 2)
        elif funct3 == 0b010:  # SW
            self.memory.write(addr, data, 4)
        else:
            raise IllegalInstructionError(f"Invalid store funct3: 0x{funct3:x}")

    # I-type ALU instructions
    def _execute_op_imm(self, insn: int, result: dict):
        """Immediate ALU instructions."""
        funct3 = (insn >> 12) & 0x7
        rd = (insn >> 7) & 0x1F
        rs1 = (insn >> 15) & 0x1F
        imm = (insn >> 20) & 0xFFF

        # Special handling for shifts
        if funct3 in [0b001, 0b101]:  # SLLI, SRLI, SRAI
            shamt = imm & 0x1F
            funct7 = (imm >> 5) & 0x7F
            if funct3 == 0b001:  # SLLI
                if funct7 != 0:
                    raise IllegalInstructionError("Invalid SLLI funct7")
                value = (self.regs[rs1] << shamt) & 0xFFFFFFFF
            elif funct3 == 0b101:
                if funct7 == 0b0000000:  # SRLI
                    value = self.regs[rs1] >> shamt
                elif funct7 == 0b0100000:  # SRAI
                    val = self.regs[rs1]
                    if val & 0x80000000:  # Sign bit set
                        value = (val >> shamt) | (0xFFFFFFFF << (32 - shamt))
                    else:
                        value = val >> shamt
                    value &= 0xFFFFFFFF
                else:
                    raise IllegalInstructionError(f"Invalid shift funct7: 0x{funct7:x}")
        else:
            imm = self._sign_extend(imm, 12)
            val1 = self.regs[rs1]

            # Convert to signed for comparison
            sval1 = val1 if val1 < 0x80000000 else val1 - 0x100000000
            simm = imm if imm < 0x80000000 else imm - 0x100000000

            if funct3 == 0b000:  # ADDI
                value = (val1 + imm) & 0xFFFFFFFF
            elif funct3 == 0b010:  # SLTI
                value = 1 if sval1 < simm else 0
            elif funct3 == 0b011:  # SLTIU
                value = 1 if val1 < imm else 0
            elif funct3 == 0b100:  # XORI
                value = val1 ^ imm
            elif funct3 == 0b110:  # ORI
                value = val1 | imm
            elif funct3 == 0b111:  # ANDI
                value = val1 & imm
            else:
                raise IllegalInstructionError(f"Invalid op-imm funct3: 0x{funct3:x}")

        self._write_reg(rd, value)
        result['rd'] = rd
        result['rd_value'] = self.regs[rd]

    # R-type ALU instructions
    def _execute_op(self, insn: int, result: dict):
        """Register-register ALU instructions."""
        funct3 = (insn >> 12) & 0x7
        funct7 = (insn >> 25) & 0x7F
        rd = (insn >> 7) & 0x1F
        rs1 = (insn >> 15) & 0x1F
        rs2 = (insn >> 20) & 0x1F

        val1 = self.regs[rs1]
        val2 = self.regs[rs2]

        # Convert to signed for comparison
        sval1 = val1 if val1 < 0x80000000 else val1 - 0x100000000
        sval2 = val2 if val2 < 0x80000000 else val2 - 0x100000000

        if funct3 == 0b000:
            if funct7 == 0b0000000:  # ADD
                value = (val1 + val2) & 0xFFFFFFFF
            elif funct7 == 0b0100000:  # SUB
                value = (val1 - val2) & 0xFFFFFFFF
            else:
                raise IllegalInstructionError(f"Invalid ADD/SUB funct7: 0x{funct7:x}")
        elif funct3 == 0b001:  # SLL
            if funct7 != 0b0000000:
                raise IllegalInstructionError("Invalid SLL funct7")
            shamt = val2 & 0x1F
            value = (val1 << shamt) & 0xFFFFFFFF
        elif funct3 == 0b010:  # SLT
            if funct7 != 0b0000000:
                raise IllegalInstructionError("Invalid SLT funct7")
            value = 1 if sval1 < sval2 else 0
        elif funct3 == 0b011:  # SLTU
            if funct7 != 0b0000000:
                raise IllegalInstructionError("Invalid SLTU funct7")
            value = 1 if val1 < val2 else 0
        elif funct3 == 0b100:  # XOR
            if funct7 != 0b0000000:
                raise IllegalInstructionError("Invalid XOR funct7")
            value = val1 ^ val2
        elif funct3 == 0b101:
            shamt = val2 & 0x1F
            if funct7 == 0b0000000:  # SRL
                value = val1 >> shamt
            elif funct7 == 0b0100000:  # SRA
                if val1 & 0x80000000:  # Sign bit set
                    value = (val1 >> shamt) | (0xFFFFFFFF << (32 - shamt))
                else:
                    value = val1 >> shamt
                value &= 0xFFFFFFFF
            else:
                raise IllegalInstructionError(f"Invalid SRL/SRA funct7: 0x{funct7:x}")
        elif funct3 == 0b110:  # OR
            if funct7 != 0b0000000:
                raise IllegalInstructionError("Invalid OR funct7")
            value = val1 | val2
        elif funct3 == 0b111:  # AND
            if funct7 != 0b0000000:
                raise IllegalInstructionError("Invalid AND funct7")
            value = val1 & val2
        else:
            raise IllegalInstructionError(f"Invalid op funct3: 0x{funct3:x}")

        self._write_reg(rd, value)
        result['rd'] = rd
        result['rd_value'] = self.regs[rd]

    def get_state(self) -> dict:
        """
        Get current architectural state.

        Returns:
            Dictionary with:
                - 'pc': Current PC
                - 'regs': List of 32 register values
                - 'cycle_count': Number of instructions executed
        """
        return {
            'pc': self.pc,
            'regs': self.regs.copy(),
            'cycle_count': self.cycle_count
        }

    def load_program(self, program: dict[int, int]):
        """
        Load program into memory.

        Args:
            program: Dictionary mapping {address: instruction_word}
        """
        self.memory.load_program(program, word_size=4)
