# Reference Model Specification

Python Golden Reference Models for CPU and GPU

Document status: Frozen
Last updated: 2026-01-17

## Overview

This specification defines the Python reference models used as golden references for verifying
RTL correctness. Reference models must match the architectural specifications exactly.

**Purpose**:

- Provide cycle-accurate or instruction-accurate reference behavior
- Enable testbench scoreboards to compare RTL against known-good implementation
- Serve as executable specification
- Facilitate debugging (simpler to understand than RTL)

**Language**: Python 3.10+

**Location**: `tb/models/`

## Design Principles

1. **Simplicity over performance**: Readable code is more important than fast execution
2. **Exact architectural match**: Must implement specifications precisely
3. **Deterministic**: Same inputs always produce same outputs
4. **Stateful**: Models maintain architectural state across steps
5. **Well-tested**: Reference models themselves must be tested

## CPU Reference Model

### Module: `tb/models/rv32i_model.py`

### Class: `RV32IModel`

**Purpose**: Instruction-accurate model of RV32I CPU core

#### Constructor

```python
class RV32IModel:
    """
    RV32I CPU reference model

    Implements the exact instruction set and behavior defined in
    PHASE0_ARCHITECTURE_SPEC.md
    """

    def __init__(self, reset_pc: int = 0x0000_0000, trap_vector: int = 0x0000_0100):
        """
        Initialize CPU model

        Args:
            reset_pc: Initial PC value after reset (default 0x0000_0000)
            trap_vector: Address to jump on traps (default 0x0000_0100)
        """
        self.reset_pc = reset_pc
        self.trap_vector = trap_vector
        self.reset()
```

#### State representation

```python
def reset(self):
    """Reset CPU to initial state per PHASE0_ARCHITECTURE_SPEC.md"""
    self.pc = self.reset_pc
    self.regs = [0] * 32            # x0-x31, all initialized to 0
    self.regs[0] = 0                # x0 hardwired to zero
    self.memory = {}                # Sparse memory: {addr: value}
    self.trap_pending = False
    self.trap_cause = 0
    self.halted = False
    self.cycle_count = 0
```

#### Core API

```python
def step(self, instruction: int) -> dict:
    """
    Execute one instruction

    Args:
        instruction: 32-bit instruction word

    Returns:
        Dictionary with:
            - 'pc': PC before execution
            - 'insn': Instruction word
            - 'rd': Destination register (or None)
            - 'rd_value': Value written to rd (or None)
            - 'mem_addr': Memory address accessed (or None)
            - 'mem_data': Memory data read/written (or None)
            - 'mem_write': True if write, False if read
            - 'trap': True if trap occurred
            - 'trap_cause': Trap cause code
            - 'next_pc': PC after execution

    Raises:
        IllegalInstructionError: If instruction is illegal
    """
    # Implementation details...
```

```python
def mem_read(self, addr: int, size: int) -> int:
    """
    Read memory (used by load instructions)

    Args:
        addr: Address to read (must be naturally aligned)
        size: Access size (1, 2, or 4 bytes)

    Returns:
        Data value

    Raises:
        MisalignedAccessError: If addr not aligned
    """
    # Implementation details...

def mem_write(self, addr: int, data: int, size: int):
    """
    Write memory (used by store instructions)

    Args:
        addr: Address to write (must be naturally aligned)
        data: Data to write
        size: Access size (1, 2, or 4 bytes)

    Raises:
        MisalignedAccessError: If addr not aligned
    """
    # Implementation details...
```

```python
def get_state(self) -> dict:
    """
    Get current architectural state

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
    Load program into memory

    Args:
        program: Dictionary mapping {address: instruction_word}
    """
    for addr, value in program.items():
        self.memory[addr] = value
```

#### Instruction implementation

Each instruction must be implemented per PHASE0_ARCHITECTURE_SPEC.md:

```python
def _execute_add(self, rd: int, rs1: int, rs2: int):
    """ADD: rd = rs1 + rs2"""
    result = (self.regs[rs1] + self.regs[rs2]) & 0xFFFF_FFFF
    if rd != 0:  # x0 is hardwired to zero
        self.regs[rd] = result

def _execute_sub(self, rd: int, rs1: int, rs2: int):
    """SUB: rd = rs1 - rs2"""
    result = (self.regs[rs1] - self.regs[rs2]) & 0xFFFF_FFFF
    if rd != 0:
        self.regs[rd] = result

# ... implement all 37 RV32I instructions
```

**Human responsibility**: Implement all 37 RV32I instructions correctly.

**AI may assist**: Generate boilerplate, but human must verify semantics.

### Usage Example

```python
from tb.models.rv32i_model import RV32IModel

# Create model
cpu = RV32IModel()

# Load program
program = {
    0x0000_0000: 0x00000093,  # addi x1, x0, 0
    0x0000_0004: 0x00100113,  # addi x2, x0, 1
    0x0000_0008: 0x002081b3,  # add x3, x1, x2
}
cpu.load_program(program)

# Execute instructions
for i in range(3):
    insn = cpu.memory[cpu.pc]
    result = cpu.step(insn)
    print(f"PC: 0x{result['pc']:08x}, Insn: 0x{result['insn']:08x}")

# Check final state
state = cpu.get_state()
assert state['regs'][3] == 1  # x3 should be 1
```

### Integration with cocotb Testbench

```python
import cocotb
from cocotb.triggers import RisingEdge
from tb.models.rv32i_model import RV32IModel

@cocotb.test()
async def test_cpu(dut):
    # Create reference model
    model = RV32IModel()

    # Clock and reset
    await reset_dut(dut)

    # Run test
    for cycle in range(1000):
        await RisingEdge(dut.clk)

        # Check commit
        if dut.commit_valid.value == 1:
            # Get RTL commit info
            rtl_pc = dut.commit_pc.value
            rtl_insn = dut.commit_insn.value

            # Step reference model
            ref_result = model.step(rtl_insn)

            # Compare
            assert ref_result['pc'] == rtl_pc, \
                f"PC mismatch: RTL={rtl_pc:08x}, Model={ref_result['pc']:08x}"

            # Compare register file if rd was written
            if ref_result['rd'] is not None:
                rtl_rd_value = dut.regfile.regs[ref_result['rd']].value
                assert rtl_rd_value == ref_result['rd_value'], \
                    f"Register x{ref_result['rd']} mismatch"
```

## GPU Reference Model

### Module: `tb/models/gpu_kernel_model.py`

### Class: `GPUKernelModel`

**Purpose**: Instruction-accurate model of GPU SIMT execution

#### Constructor

```python
class GPUKernelModel:
    """
    GPU SIMT kernel execution model

    Implements the execution model defined in PHASE4_GPU_ARCHITECTURE_SPEC.md
    """

    def __init__(self, warp_size: int = 8):
        """
        Initialize GPU model

        Args:
            warp_size: Number of lanes per warp (default 8)
        """
        self.warp_size = warp_size
        self.reset()
```

#### State representation

```python
def reset(self):
    """Reset GPU to initial state"""
    # Grid/block configuration
    self.grid_dim = (1, 1, 1)
    self.block_dim = (1, 1, 1)

    # Kernel program
    self.kernel_addr = 0
    self.kernel_instructions = {}

    # Execution state
    self.warps = []  # List of warp states
    self.memory = {}  # Shared memory model

    # Statistics
    self.cycle_count = 0
    self.completed_warps = 0
```

#### Core API

```python
def configure(self, grid_dim: tuple, block_dim: tuple, kernel_addr: int):
    """
    Configure kernel dimensions

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
    for block_id in range(total_blocks):
        for warp_id in range(warps_per_block):
            warp = self._create_warp(block_id, warp_id)
            self.warps.append(warp)

def execute_kernel(self) -> dict:
    """
    Execute kernel to completion

    Returns:
        Dictionary with:
            - 'cycles': Total execution cycles
            - 'memory': Final memory state
            - 'completed_warps': Number of warps completed
    """
    while not self._all_warps_done():
        # Schedule next warp (round-robin)
        warp = self._schedule_warp()

        # Execute one instruction for this warp
        self._execute_warp_instruction(warp)

        self.cycle_count += 1

    return {
        'cycles': self.cycle_count,
        'memory': self.memory.copy(),
        'completed_warps': self.completed_warps
    }
```

#### Warp execution

```python
def _execute_warp_instruction(self, warp: dict):
    """
    Execute one instruction for a warp

    Args:
        warp: Warp state dictionary
    """
    # Fetch instruction
    insn = self.kernel_instructions[warp['pc']]

    # Decode
    opcode, rd, rs1, rs2, imm = self._decode(insn)

    # Execute for all active lanes
    for lane in range(self.warp_size):
        if warp['active_mask'] & (1 << lane):
            # Execute instruction for this lane
            self._execute_lane(warp, lane, opcode, rd, rs1, rs2, imm)

    # Update PC
    warp['pc'] += 4
```

**Human responsibility**: Implement SIMT execution semantics and divergence handling.

**AI may assist**: Generate lane execution loops, but human must verify correctness.

### Usage Example

```python
from tb.models.gpu_kernel_model import GPUKernelModel

# Create model
gpu = GPUKernelModel(warp_size=8)

# Configure kernel
gpu.configure(
    grid_dim=(2, 1, 1),   # 2 blocks
    block_dim=(8, 1, 1),  # 8 threads per block
    kernel_addr=0x1000
)

# Load kernel program
gpu.load_kernel({
    0x1000: 0x...,  # VMOV r1, tid.x
    0x1004: 0x...,  # VADD r2, r1, r1
    # ...
})

# Load input data
for i in range(16):
    gpu.mem_write(0x2000 + i*4, i)

# Execute
result = gpu.execute_kernel()

# Verify output
for i in range(16):
    expected = i * 2
    actual = gpu.mem_read(0x3000 + i*4)
    assert actual == expected
```

## Memory Model

### Module: `tb/models/memory_model.py`

### Class: `MemoryModel`

**Purpose**: Simple memory model for use by CPU and GPU reference models

```python
class MemoryModel:
    """Sparse memory model with alignment checking"""

    def __init__(self):
        self.mem = {}  # Sparse storage

    def read(self, addr: int, size: int = 4) -> int:
        """Read size bytes from addr (must be aligned)"""
        if addr % size != 0:
            raise MisalignedAccessError(f"Address 0x{addr:08x} not aligned to {size}")

        # Read bytes from sparse memory
        value = 0
        for i in range(size):
            byte_val = self.mem.get(addr + i, 0)
            value |= (byte_val << (i * 8))

        return value

    def write(self, addr: int, data: int, size: int = 4):
        """Write size bytes to addr (must be aligned)"""
        if addr % size != 0:
            raise MisalignedAccessError(f"Address 0x{addr:08x} not aligned to {size}")

        # Write bytes to sparse memory
        for i in range(size):
            byte_val = (data >> (i * 8)) & 0xFF
            self.mem[addr + i] = byte_val
```

## Testing the Reference Models

**Critical requirement**: Reference models must themselves be tested to ensure correctness.

### Test strategy

1. **Unit tests**: Test each instruction in isolation
2. **Directed sequences**: Test instruction combinations
3. **Known-good programs**: Test against hand-verified results
4. **Cross-check**: Compare against RISC-V ISA simulator (spike, QEMU)

### Example unit test

```python
# tb/tests/test_rv32i_model.py
import pytest
from tb.models.rv32i_model import RV32IModel

def test_add_instruction():
    cpu = RV32IModel()
    cpu.regs[1] = 10
    cpu.regs[2] = 20

    # ADD x3, x1, x2
    insn = 0x002081b3
    result = cpu.step(insn)

    assert cpu.regs[3] == 30, "ADD failed"
    assert result['rd'] == 3
    assert result['rd_value'] == 30

def test_x0_hardwired():
    cpu = RV32IModel()

    # Try to write to x0: ADDI x0, x0, 1
    insn = 0x00100013
    cpu.step(insn)

    assert cpu.regs[0] == 0, "x0 must remain zero"
```

## File Organization

```text
tb/
├── models/
│   ├── __init__.py
│   ├── rv32i_model.py          # CPU reference model
│   ├── gpu_kernel_model.py     # GPU reference model
│   ├── memory_model.py         # Shared memory model
│   └── common.py               # Shared utilities
└── tests/
    ├── test_rv32i_model.py     # CPU model unit tests
    ├── test_gpu_model.py       # GPU model unit tests
    └── test_memory_model.py    # Memory model unit tests
```

## AI/Human Responsibility

### AI MAY assist with

- Boilerplate class structure
- Simple instruction implementations (after human verification)
- Memory model read/write logic
- Utility functions (sign extension, bit manipulation)
- Test case generation

### Human MUST

- Verify all instruction semantics match specification
- Implement complex instructions (branches, loads, stores)
- Design divergence handling algorithm (GPU)
- Write thorough unit tests
- Cross-verify against known-good implementations

## Dependencies

**Required Python packages**:

```text
pytest>=7.0
numpy>=1.24  # For numerical operations in GPU model
```

**Optional**:

```text
riscv-isa-sim  # For cross-verification (spike simulator)
```

## Integration with Verification Plan

The reference models are the **source of truth** for verification:

1. **Scoreboard comparison**: Every RTL commit must match reference model step
2. **Coverage tracking**: Reference model tracks which instructions/scenarios executed
3. **Debug**: When mismatch occurs, reference model state aids debugging

## Performance Considerations

Reference models do NOT need to be fast:

- Clarity and correctness are paramount
- Even 1000x slower than RTL is acceptable
- Optimize only if simulation time becomes prohibitive

## Documentation Requirements

Each reference model must include:

- Docstrings for all public methods
- Examples in docstrings
- References to specification sections
- Known limitations or assumptions

## Version Control

Reference models should be versioned alongside specifications:

- Update model when specification changes
- Tag model versions with phase milestones
- Document model changes in commit messages

## References

- PHASE0_ARCHITECTURE_SPEC.md: CPU architectural requirements
- PHASE4_GPU_ARCHITECTURE_SPEC.md: GPU architectural requirements
- VERIFICATION_PLAN.md: How models integrate with verification
- RISC-V ISA Manual: Instruction semantics reference
