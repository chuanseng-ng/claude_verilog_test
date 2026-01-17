# Phase 4 GPU Architecture Specification

GPU-Lite SIMT Compute Engine

Document status: Frozen (Phase-4)
Target audience: RTL implementation, verification, GPU kernel developers
Compliance reference: None (custom design)

**Prerequisites**: Phases 0-3 must be complete (CPU operational with caches)

## Overview

Phase 4 implements a minimal but functional SIMT (Single Instruction Multiple Thread) compute
engine suitable for simple parallel workloads. The design prioritizes simplicity and verifiability
over performance.

**Design philosophy**: Keep it simple enough to verify thoroughly, but real enough to be useful.

## Scope and non-goals

### Scope

This specification defines:

- SIMT execution model (warps and lanes)
- GPU instruction set architecture (ISA)
- Memory access patterns
- Divergence handling (basic)
- Kernel launch mechanism
- Register file organization
- APB3 control interface
- AXI4-Lite memory interface

### Explicit non-goals (Phase 4 exclusions)

The following are NOT implemented in Phase 4:

- Graphics rendering pipeline
- Texture units
- Multiple compute units
- Shared local memory (scratchpad)
- Warp scheduling beyond round-robin
- Preemption
- Out-of-order execution
- Cache coherence with CPU
- Atomic memory operations
- Multi-level divergence (nested branches)
- Dynamic parallelism (kernel launching kernels)

Any excluded feature will be added in later phases or not supported.

## Execution Model

### Thread hierarchy

```text
Grid (entire kernel execution)
  └─ Blocks (independent groups of threads)
      └─ Warps (groups of threads executing same instruction)
          └─ Lanes (individual threads within a warp)
```

**Phase 4 constraints**:

- Grid dimensions: Up to 64x64x64 blocks (configurable via registers)
- Block dimensions: Up to 16x16x1 threads (max 256 threads per block)
- Warp size: **8 lanes** (fixed in Phase 4)
- Warps per block: Block size / warp size (up to 32 warps per block)
- Total threads: Grid size × Block size (maximum ~1M threads)

### SIMT execution

**Single Instruction Multiple Thread (SIMT)**:

- All lanes in a warp execute the same instruction
- Each lane has its own register file and program counter
- Divergence handled via per-lane predicate masks (see Divergence section)

**Warp scheduler**:

- Round-robin scheduling among ready warps
- No scoreboarding across warps (simple design)
- Warp stalls on memory access until all lanes complete

### Pipeline organization

**4-stage pipeline** (simpler than CPU):

```text
FETCH → DECODE → EXECUTE → WRITEBACK
```

**Stage details**:

1. **FETCH**: Fetch instruction from kernel address
   - Shared instruction for all lanes in warp
   - PC per warp, not per lane

2. **DECODE**: Decode instruction, read registers
   - Per-lane register reads
   - Predicate mask applied

3. **EXECUTE**: ALU or memory operation
   - Vector ALU (8 lanes)
   - Memory operations serialized or coalesced

4. **WRITEBACK**: Write results to register file
   - Per-lane register writes
   - Masked lanes do not write

**No memory stage**: Memory operations complete in EXECUTE stage (may take multiple cycles).

## GPU Instruction Set Architecture (ISA)

### Instruction format

**32-bit instruction encoding** (similar to RISC-V for simplicity):

```text
31        25 24     20 19     15 14  12 11      7 6       0
+----------+---------+---------+------+---------+---------+
|  funct7  |   rs2   |   rs1   |funct3|   rd    | opcode  |  R-type
+----------+---------+---------+------+---------+---------+
|      imm[11:0]     |   rs1   |funct3|   rd    | opcode  |  I-type
+----------+---------+---------+------+---------+---------+
```

**Register naming**:

- r0-r31: General purpose registers (per lane)
- tid.x, tid.y, tid.z: Thread ID within block (special registers)
- bid.x, bid.y, bid.z: Block ID within grid (special registers)

### Arithmetic and Logic Instructions

| Instruction        | Encoding | Description                    |
|:------------------:|:--------:|:------------------------------:|
| VADD rd, rs1, rs2  | R-type   | rd = rs1 + rs2                 |
| VSUB rd, rs1, rs2  | R-type   | rd = rs1 - rs2                 |
| VMUL rd, rs1, rs2  | R-type   | rd = rs1 * rs2                 |
| VAND rd, rs1, rs2  | R-type   | rd = rs1 & rs2                 |
| VOR rd, rs1, rs2   | R-type   | rd = rs1 \| rs2                |
| VXOR rd, rs1, rs2  | R-type   | rd = rs1 ^ rs2                 |
| VSLL rd, rs1, rs2  | R-type   | rd = rs1 << rs2                |
| VSRL rd, rs1, rs2  | R-type   | rd = rs1 >> rs2 (logical)      |
| VSRA rd, rs1, rs2  | R-type   | rd = rs1 >> rs2 (arithmetic)   |
| VADDI rd, rs1, imm | I-type   | rd = rs1 + imm                 |
| VANDI rd, rs1, imm | I-type   | rd = rs1 & imm                 |
| VORI rd, rs1, imm  | I-type   | rd = rs1 \| imm                |
| VXORI rd, rs1, imm | I-type   | rd = rs1 ^ imm                 |

**Behavior**: All lanes execute in parallel, each using its own register values.

### Memory Instructions

| Instruction          | Encoding | Description                    |
|:--------------------:|:--------:|:------------------------------:|
| VLD rd, offset(rs1)  | I-type   | rd = mem[rs1 + offset]         |
| VST rs2, offset(rs1) | I-type   | mem[rs1 + offset] = rs2        |

**Memory access patterns**:

1. **Coalesced access**: If all lanes access consecutive addresses in the same cache line,
   issue a single wide transaction.

2. **Serialized access**: If lanes access scattered addresses, serialize transactions
   (one per lane, slower but simpler).

**Phase 4 limitation**: No atomic operations, no synchronization beyond kernel boundaries.

### Control Flow Instructions

| Instruction           | Encoding | Description                    |
|:---------------------:|:--------:|:------------------------------:|
| VBEQ rs1, rs2, offset | B-type   | if (rs1 == rs2) branch         |
| VBNE rs1, rs2, offset | B-type   | if (rs1 != rs2) branch         |
| VBLT rs1, rs2, offset | B-type   | if (rs1 < rs2) branch          |
| VBGE rs1, rs2, offset | B-type   | if (rs1 >= rs2) branch         |
| VJMP offset           | J-type   | Unconditional jump             |
| VRET                  | -        | Return (end kernel)            |

**Divergence handling**: See Divergence section below.

### Special Instructions

| Instruction    | Encoding | Description                        |
|:--------------:|:--------:|:----------------------------------:|
| VMOV rd, tid.x | -        | rd = thread ID X                   |
| VMOV rd, tid.y | -        | rd = thread ID Y                   |
| VMOV rd, tid.z | -        | rd = thread ID Z                   |
| VMOV rd, bid.x | -        | rd = block ID X                    |
| VMOV rd, bid.y | -        | rd = block ID Y                    |
| VMOV rd, bid.z | -        | rd = block ID Z                    |
| VSYNC          | -        | Warp synchronization (barrier)     |

**VSYNC behavior**:

- All lanes in warp wait until all reach VSYNC
- Phase 4: Only intra-warp sync (no inter-warp sync)

## Register File Organization

### Per-lane registers

Each of the 8 lanes has:

- 32 general-purpose registers (r0-r31), 32 bits each
- r0 hardwired to 0 (like RISC-V)

**Total register file size**: 8 lanes × 32 registers × 32 bits = 8192 bits = 1 KB

### Special registers (read-only, computed per lane)

| Register | Description                      | Example (lane 3, block (2,1,0)) |
|:--------:|:--------------------------------:|:-------------------------------:|
| tid.x    | Thread ID X within block         | Lane index % block_dim_x        |
| tid.y    | Thread ID Y within block         | Computed from warp/lane         |
| tid.z    | Thread ID Z within block         | Computed from warp/lane         |
| bid.x    | Block ID X within grid           | 2                               |
| bid.y    | Block ID Y within grid           | 1                               |
| bid.z    | Block ID Z within grid           | 0                               |

**Computation**: tid and bid values computed by hardware based on current warp and block indices.

## Divergence Handling

### Divergence model

When lanes in a warp take different branches, execution **serializes**:

```text
if (tid.x < 4) {
    A;  // Executed with mask [11110000]
} else {
    B;  // Executed with mask [00001111]
}
C;      // Executed with mask [11111111]
```

### Predicate mask

Each warp has an 8-bit **active lane mask**:

- Bit N = 1: Lane N executes the instruction
- Bit N = 0: Lane N does not execute (no register writes, no memory access)

### Divergence stack (simplified)

**Phase 4 limitation**: Only **one level of divergence** supported.

**Divergence sequence**:

1. Evaluate branch condition per lane → compute mask_true and mask_false
2. Push return PC and mask_false onto stack
3. Set active_mask = mask_true, execute true path
4. Pop stack: set active_mask = mask_false, set PC to else branch
5. Execute false path
6. Reconverge: set active_mask = all lanes

**Multi-level divergence**: Nested branches NOT supported in Phase 4 (kernel must avoid).

## Memory Access Model

### Address generation

Each lane computes its own address:

```text
address[lane] = base_register[lane] + offset
```

### Coalescing

**Coalesced transaction** (efficient):

- All active lanes access addresses within the same 32-byte cache line
- Single AXI transaction fetches all data
- Example: `VLD r1, 0(r0)` where r0 = [0, 4, 8, 12, 16, 20, 24, 28] (consecutive)

**Serialized transactions** (slow):

- Active lanes access scattered addresses
- One AXI transaction per active lane
- Example: `VLD r1, 0(r0)` where r0 = [0, 100, 200, ...] (non-consecutive)

### Memory ordering

**Relaxed memory model**:

- No ordering guarantees between threads
- No coherence with CPU (CPU must flush caches before launching GPU kernel)
- Synchronization only at kernel boundaries

**Phase 4 limitation**: No atomics, no memory fences.

## Kernel Launch Mechanism

### Launch sequence (from CPU)

1. **CPU writes GPU registers**:

   ```text
   GPU_KERNEL_ADDR  = kernel_instruction_address;
   GPU_GRID_DIM_X   = grid_x;
   GPU_GRID_DIM_Y   = grid_y;
   GPU_GRID_DIM_Z   = grid_z;
   GPU_BLOCK_DIM_X  = block_x;
   GPU_BLOCK_DIM_Y  = block_y;
   GPU_BLOCK_DIM_Z  = block_z;
   GPU_CTRL         = START;
   ```

2. **GPU executes kernel**:
   - Iterates through all blocks in grid
   - For each block, schedules warps round-robin
   - Each warp executes until VRET

3. **GPU signals completion**:
   - Sets `GPU_STATUS[DONE] = 1`
   - Asserts `gpu_irq` interrupt (if enabled)

4. **CPU reads results**:
   - Poll `GPU_STATUS` or handle interrupt
   - Read result data from memory

### Kernel termination

- **VRET instruction**: Signals warp completion
- When all warps in all blocks complete, kernel done

## RTL Module Hierarchy

```text
gpu_compute_top                 # Top-level integration
├── gpu_core                    # GPU core wrapper
│   ├── gpu_control             # FSM and warp scheduler
│   ├── gpu_fetch               # Instruction fetch
│   ├── gpu_decode              # Instruction decode
│   ├── gpu_execute             # Execution stage
│   │   ├── gpu_vector_alu      # 8-lane ALU
│   │   └── gpu_mem_unit        # Memory coalescing logic
│   ├── gpu_regfile             # 8 lanes × 32 registers
│   └── gpu_diverge             # Divergence stack
├── axi4lite_master             # AXI4-Lite master (memory)
└── apb3_slave                  # APB3 slave (control)
```

## Control Interface (APB3)

See MEMORY_MAP.md for complete register map.

**Key registers**:

- GPU_CTRL: Start kernel, reset
- GPU_STATUS: Idle, done, error
- GPU_KERNEL_ADDR: Kernel PC
- GPU_GRID_DIM_X/Y/Z: Grid dimensions
- GPU_BLOCK_DIM_X/Y/Z: Block dimensions

## Memory Interface (AXI4-Lite)

**Configuration**:

- Address width: 32 bits
- Data width: 32 bits (Phase 4), may widen in later phases
- Outstanding transactions: 1 (simple design)

**Usage**:

- Instruction fetch from kernel address
- Load/store from lanes
- No coherence with CPU caches

## AI/Human Responsibility Boundaries

### AI MAY assist with

- Vector ALU module (8-lane parallel ALU)
- Register file arrays (8 × 32 registers)
- Warp scheduler boilerplate (round-robin FSM)
- AXI4-Lite memory transaction logic
- APB3 register interface
- Testbench infrastructure (cocotb)

### AI MUST NOT decide

- Divergence handling algorithm (human must design)
- Memory coalescing heuristics (human must specify)
- Warp scheduling policy (beyond simple round-robin)
- Thread/block/grid dimension limits
- ISA encoding and semantics

### Human MUST review

- Divergence stack correctness
- Memory coalescing logic
- Warp scheduler state machine
- Kernel launch FSM
- All control flow handling

## Verification Requirements (Phase 4)

### Testbench architecture

- cocotb for interface drivers
- pyuvm for sequence generation
- Python GPU kernel reference model

### Required tests

1. **Simple kernels**:
   - Vector addition: `C[i] = A[i] + B[i]`
   - Scalar multiplication: `B[i] = A[i] * k`

2. **Divergence tests**:
   - Single if/else with different paths
   - Verify mask handling

3. **Memory tests**:
   - Coalesced loads/stores
   - Scattered loads/stores

4. **Grid/block tests**:
   - Various grid/block dimensions
   - tid/bid correctness

### Exit criteria

- All directed kernel tests pass
- Random kernel test passes (simple random ops)
- Divergence correctness proven (mask verification)
- No deadlocks in 100k+ cycle stress runs
- Memory correctness verified vs reference model

## Known Limitations (Phase 4)

1. **Single compute unit**: Only one warp executes at a time (very limited parallelism)
2. **No shared memory**: All communication through global memory
3. **No atomics**: Cannot safely update shared counters
4. **One-level divergence**: Nested branches not supported
5. **No inter-warp sync**: Cannot synchronize between warps
6. **No preemption**: Kernel runs to completion
7. **No coherence**: CPU must flush caches before GPU access

## File Organization

```text
rtl/
└── gpu/
    ├── gpu_compute_top.sv      # Top-level
    └── core/
        ├── gpu_core.sv         # Core wrapper
        ├── gpu_control.sv      # FSM and scheduler
        ├── gpu_fetch.sv        # Instruction fetch
        ├── gpu_decode.sv       # Decoder
        ├── gpu_execute.sv      # Execution stage
        ├── gpu_vector_alu.sv   # 8-lane ALU
        ├── gpu_mem_unit.sv     # Memory coalescing
        ├── gpu_regfile.sv      # Register file
        └── gpu_diverge.sv      # Divergence handling

tb/
└── gpu/
    ├── tb_gpu_compute_top.py   # Top-level testbench
    ├── gpu_kernel_model.py     # Python reference model
    └── test_kernels/
        ├── vec_add.asm         # Vector addition kernel
        ├── diverge_test.asm    # Divergence test
        └── mem_test.asm        # Memory coalescing test
```

## Example Kernel (Vector Addition)

```assembly
# Vector addition: C[i] = A[i] + B[i]
# Inputs: r1 = A_base, r2 = B_base, r3 = C_base, r4 = N

    VMOV r5, tid.x          # r5 = thread ID
    VMOV r6, bid.x          # r6 = block ID
    VADDI r7, r0, 8         # r7 = block size (8 threads per block)
    VMUL r8, r6, r7         # r8 = bid * block_size
    VADD r9, r8, r5         # r9 = global thread index

    VBGE r9, r4, end        # if (index >= N) goto end

    VLD r10, 0(r1)          # r10 = A[index] (assume r1 pre-offset)
    VLD r11, 0(r2)          # r11 = B[index]
    VADD r12, r10, r11      # r12 = A[index] + B[index]
    VST r12, 0(r3)          # C[index] = r12

end:
    VRET                    # Return (end kernel)
```

## Integration with CPU (Phase 4)

**CPU responsibilities**:

1. Allocate memory for kernel inputs/outputs
2. Write input data to memory
3. Flush CPU caches (ensure GPU sees latest data)
4. Configure GPU registers (kernel address, grid/block dims)
5. Start GPU via GPU_CTRL
6. Wait for completion (poll or interrupt)
7. Invalidate CPU caches (ensure CPU sees GPU results)
8. Read output data

**GPU responsibilities**:

1. Execute kernel to completion
2. Signal done via GPU_STATUS and interrupt

## References

- PHASE0_ARCHITECTURE_SPEC.md: General architectural principles
- PHASE1_ARCHITECTURE_SPEC.md: CPU reference for comparison
- RTL_DEFINITION.md: Interface signal definitions
- MEMORY_MAP.md: GPU register map
- GPU_MODEL.md: High-level execution model overview
- REFERENCE_MODEL_SPEC.md: Python GPU model API
