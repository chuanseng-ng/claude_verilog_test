# Testbench and Reference Models

This directory contains Python reference models and unit tests for the RV32I CPU and GPU verification.

## Directory Structure

```
tb/
├── models/                  # Python reference models
│   ├── __init__.py
│   ├── memory_model.py      # Sparse memory model with alignment checking
│   ├── rv32i_model.py       # RV32I CPU instruction-accurate model
│   └── gpu_kernel_model.py  # GPU SIMT kernel execution model
├── tests/                   # Unit tests for reference models
│   ├── __init__.py
│   ├── test_memory_model.py
│   ├── test_rv32i_model.py
│   └── test_gpu_model.py
└── README.md                # This file
```

## Reference Models

### Memory Model (`memory_model.py`)

Sparse memory implementation with alignment checking per REFERENCE_MODEL_SPEC.md.

**Features:**
- Sparse storage (dictionary-based, only stores written bytes)
- Natural alignment checking (word: 4-byte, halfword: 2-byte, byte: any)
- Little-endian byte ordering
- Support for 1, 2, and 4-byte accesses

**Usage:**
```python
from tb.models import MemoryModel

mem = MemoryModel()
mem.write(0x1000, 0x12345678, 4)  # Write word
data = mem.read(0x1000, 4)         # Read word
```

### RV32I CPU Model (`rv32i_model.py`)

Instruction-accurate model implementing all 37 RV32I base instructions per PHASE0_ARCHITECTURE_SPEC.md.

**Features:**
- All 37 RV32I instructions (arithmetic, logical, shift, load/store, branch, jump)
- x0 hardwired to zero
- Trap handling (illegal instruction, misaligned access)
- Step-by-step execution with detailed result tracking
- Memory interface using MemoryModel

**Usage:**
```python
from tb.models import RV32IModel

cpu = RV32IModel()
cpu.load_program({
    0x0000: 0x00000093,  # addi x1, x0, 0
    0x0004: 0x00100113,  # addi x2, x0, 1
    0x0008: 0x002081b3,  # add x3, x1, x2
})

# Execute instructions
for i in range(3):
    insn = cpu.memory.read(cpu.pc, 4)
    result = cpu.step(insn)
    print(f"PC: 0x{result['pc']:08x}, rd={result['rd']}, value={result['rd_value']}")

# Check final state
state = cpu.get_state()
print(f"x3 = {state['regs'][3]}")  # Should be 1
```

### GPU Kernel Model (`gpu_kernel_model.py`)

SIMT execution model per PHASE4_GPU_ARCHITECTURE_SPEC.md with 8-lane warps.

**Features:**
- 8-lane SIMT execution (single instruction, multiple threads)
- Grid/block/warp configuration
- Round-robin warp scheduling
- Basic divergence handling (one level)
- Special registers (tid.x/y/z, bid.x/y/z)
- Memory coalescing (simplified)

**Usage:**
```python
from tb.models import GPUKernelModel

gpu = GPUKernelModel(warp_size=8)

# Configure kernel dimensions
gpu.configure(
    grid_dim=(2, 1, 1),   # 2 blocks
    block_dim=(8, 1, 1),  # 8 threads per block
    kernel_addr=0x1000
)

# Load kernel instructions
gpu.load_kernel({
    0x1000: 0x...,  # VMOV r1, tid.x
    0x1004: 0x...,  # VADD r2, r1, r1
    0x1008: 0x00000073,  # VRET
})

# Execute kernel
result = gpu.execute_kernel()
print(f"Completed in {result['cycles']} cycles")
```

## Running Tests

### Run all tests:
```bash
cd C:\Users\waele\Documents\Github\claude_verilog_test
python -m pytest tb/tests/ -v
```

### Run specific test file:
```bash
python -m pytest tb/tests/test_memory_model.py -v
python -m pytest tb/tests/test_rv32i_model.py -v
python -m pytest tb/tests/test_gpu_model.py -v
```

### Run specific test:
```bash
python -m pytest tb/tests/test_rv32i_model.py::TestRV32IModel::test_add_instruction -v
```

### Run with coverage:
```bash
python -m pytest tb/tests/ --cov=tb.models --cov-report=html
```

## Test Statistics

Current test coverage:
- **Memory Model**: 15 tests - All passing ✅
- **RV32I CPU Model**: 31 tests - All passing ✅
- **GPU Kernel Model**: 20 tests - All passing ✅
- **Total**: 66 tests - All passing ✅

## Implementation Notes

### RV32I Model

**Implemented Instructions (37 total):**

1. **Arithmetic**: ADD, SUB, ADDI
2. **Logical**: AND, OR, XOR, ANDI, ORI, XORI
3. **Shift**: SLL, SRL, SRA, SLLI, SRLI, SRAI
4. **Comparison**: SLT, SLTU, SLTI, SLTIU
5. **Upper Immediate**: LUI, AUIPC
6. **Branch**: BEQ, BNE, BLT, BGE, BLTU, BGEU
7. **Jump**: JAL, JALR
8. **Load**: LB, LH, LW, LBU, LHU
9. **Store**: SB, SH, SW

**Key Design Decisions:**
- Instruction-accurate (not cycle-accurate)
- Sequential consistency for single core
- Traps on illegal instructions and misaligned accesses
- Simple memory interface (no caching)

### GPU Model

**Implemented Features:**
- 8-lane SIMT execution
- Round-robin warp scheduling
- Thread ID computation (tid.x/y/z)
- Block ID tracking (bid.x/y/z)
- Basic ALU operations (add, sub, mul, logical, shifts)
- Memory load/store (simplified, serialized)
- Branch with divergence (one level)

**Limitations (per Phase 4 spec):**
- Single compute unit
- No shared local memory
- No atomic operations
- One-level divergence only
- No cache coherence with CPU

## Integration with Verification

These reference models serve as golden references for RTL verification:

1. **Scoreboard comparison**: RTL commits compared against model steps
2. **Coverage tracking**: Models track which instructions/scenarios executed
3. **Debug aid**: Model state helps debug RTL mismatches

See `docs/verification/VERIFICATION_PLAN.md` for complete verification strategy.

## Dependencies

Required Python packages:
- Python 3.10+
- pytest >= 7.0
- numpy >= 1.24 (for GPU model numerical operations)

Install dependencies:
```bash
pip install pytest numpy
```

## References

- `docs/design/REFERENCE_MODEL_SPEC.md` - Reference model specification
- `docs/design/PHASE0_ARCHITECTURE_SPEC.md` - CPU architecture
- `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md` - GPU architecture
- `docs/verification/VERIFICATION_PLAN.md` - Verification strategy
