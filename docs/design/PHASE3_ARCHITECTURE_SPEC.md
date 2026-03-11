# Phase 3 Architecture Specification

RV32I Memory System with L1 Instruction and Data Caches

Document status: APPROVED — All open questions resolved (2026-03-08). RTL implementation may begin.
Target audience: RTL Designer, Verification Engineer, Backend Engineer
Compliance reference: Phase 2 Architecture Specification, RISC-V ISA Volume I (RV32I + Zicsr), RISC-V Privileged Architecture Specification (FENCE.I)

**Prerequisites**: Phase 2 exit criteria must be met (all verification complete, 75 MHz achieved on Sky130)

---

## 1. Overview

Phase 3 adds a two-level memory hierarchy between the CPU pipeline and external AXI4-Lite memory. The primary goals are:

- **Throughput**: Eliminate the per-instruction AXI round-trip penalty for back-to-back cache hits
- **Realistic performance**: Cache hit latency is 1 cycle vs 2+ cycles for uncached AXI; reduces effective CPI on typical code
- **FENCE.I support**: Software-initiated instruction cache invalidation for self-modifying code scenarios
- **Write-back policy**: Reduces write traffic to external memory; dirty lines are only written back on eviction
- **Backward compatibility**: External AXI4-Lite and APB3 interfaces unchanged; cache is transparent to software

### 1.1 What Changes from Phase 2

| Aspect | Phase 2 | Phase 3 |
|--------|---------|---------|
| Instruction fetch | Direct AXI4-Lite read per instruction | I-cache hit: 1 cycle; miss: 4 AXI reads |
| Data access | Direct AXI4-Lite read/write per access | D-cache hit: 1 cycle; miss: optional writeback + 4 AXI reads |
| AXI transactions | One per instruction fetch or data access | Only on cache miss or dirty eviction |
| Memory latency | Every access is AXI-latency bound | Hit-rate bound; AXI only on miss |
| FENCE.I | Illegal instruction (trap) | Fully implemented (invalidate I-cache) |
| Write policy | Write-through (store drives AXI directly) | Write-back + write-allocate |
| Stall source | AXI ready/valid handshake | Cache miss FSM |
| AXI arbitration | rv32i_axi_arbiter (IF vs MEM) | rv32i_cache_arbiter (D$ vs I$) |

### 1.2 What Does NOT Change from Phase 2

- External port names and signal widths on `rv32i_cpu_top` (AXI4-Lite + APB3 + commit interface)
- Active-low synchronous reset (`rst_n_i`)
- Single clock domain
- RISC-V RV32I + Zicsr instruction set semantics
- x0 hardwired to zero
- Debug register map (MEMORY_MAP.md) — same APB3 address space
- Interrupt subsystem (M-mode, timer + external)
- CSR register set
- Pipeline stage structure (IF/ID/EX/MEM/WB remains 5 stages)

---

## 2. Cache Architecture

### 2.1 Cache Parameters

Both I-cache and D-cache use identical sizing parameters. Parameters are centralized in `rtl/mem/rv32i_cache_pkg.sv`.

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| Cache size | 4 KB | Per MEMORY_MAP.md Phase 2-3 specification |
| Cache line size | 16 bytes (4 words) | Balanced: 4 AXI transactions per refill, good spatial locality |
| Associativity | Direct-mapped (1-way) | Simpler miss handling FSM; sufficient for initial implementation |
| Sets | 256 | 4096 / 16 = 256 sets |
| Write policy (D-cache) | Write-back + write-allocate | Reduces AXI write traffic; standard policy |
| Write policy (I-cache) | Read-only (no writes from CPU) | I-cache never receives store requests |
| FENCE.I support | Yes (I-cache invalidation) | Required for self-modifying code and instruction patching |

### 2.2 Address Breakdown

For a 32-bit byte address with 4 KB, direct-mapped, 16-byte line cache:

```
Bit 31                12 11            4 3          0
  [ tag[31:12] (20 bits) | index[11:4] (8 bits) | byte_offset[3:0] (4 bits) ]
```

| Field | Bits | Width | Encoding |
|-------|------|-------|----------|
| `byte_offset` | [3:0] | 4 bits | Byte position within 16-byte cache line |
| `word_offset` | [3:2] | 2 bits | Word index within cache line (0-3) |
| `index` | [11:4] | 8 bits | Cache set selector (0-255) |
| `tag` | [31:12] | 20 bits | Address tag for hit/miss comparison |

**Tag storage**: Each set stores a 20-bit tag, a 1-bit valid flag, and (D-cache only) a 1-bit dirty flag.

### 2.3 Cache Line Structure

```
I-Cache Line (per set):
  [ valid (1) | tag (20) | data[127:0] (128 bits) ]
  Total: 149 bits per set × 256 sets = 38,144 bits ≈ 4.7 KB (including overhead)

D-Cache Line (per set):
  [ valid (1) | dirty (1) | tag (20) | data[127:0] (128 bits) ]
  Total: 150 bits per set × 256 sets = 38,400 bits ≈ 4.7 KB (including overhead)
```

### 2.4 Hit/Miss Detection (Combinational)

```
hit = valid[index] AND (tag[index] == address[31:12])
```

The hit/miss decision is purely combinational. On a hit, read data is available within the same cycle the request is presented (1-cycle latency from CPU perspective, no stall).

### 2.5 D-Cache Write-Back + Write-Allocate Policy

**Write hit**: Update the data in the cache line; set dirty bit. Do NOT write to external memory.

**Write miss (write-allocate)**:
1. If the evicted line is dirty: write back the dirty line to external memory (4 AXI writes)
2. Fetch the new line from external memory (4 AXI reads) — write-allocate
3. Update the fetched line with the new store data; set dirty bit

**Read miss**:
1. If the evicted line is dirty: write back the dirty line to external memory (4 AXI writes)
2. Fetch the new line from external memory (4 AXI reads)
3. Serve the read from the newly fetched line

### 2.6 I-Cache Write Policy and FENCE.I

The I-cache is read-only from the CPU's perspective. The CPU issues only instruction fetch requests (reads). The I-cache never receives store requests.

**FENCE.I** invalidates the entire I-cache by clearing all valid bits simultaneously. This is implemented as a single-cycle operation (all valid bits = 0 in one clock edge). After FENCE.I, the next instruction fetch will always miss and refill from external memory, picking up any stores that may have been written to the instruction region.

**FENCE.I implementation in the pipeline**:
- The `rv32i_pipeline_mem.sv` MEM stage detects the FENCE.I instruction and asserts `ic_invalidate_o` to the I-cache for one cycle
- The pipeline stalls (via `mem_cache_stall`) until the I-cache acknowledges the invalidation
- Since invalidation is single-cycle (all valid bits cleared combinationally), the stall is 1 cycle

---

## 3. Cache FSM Specifications

### 3.1 I-Cache FSM

The I-cache has a simple two-state FSM (blocking on miss):

```
States:
  IC_IDLE   — Check for hit; serve data on hit; initiate refill on miss
  IC_REFILL — Issue 4 sequential AXI read transactions; fill cache line

Transitions:
  IC_IDLE → IC_REFILL  : hit=0 (cache miss)
  IC_REFILL → IC_IDLE  : refill_done (4th AXI read complete, cache line written)
  IC_IDLE → IC_IDLE    : hit=1 (serve data, no state change)
```

**Stall behavior**:
- `ic_stall_o = 1` whenever `state == IC_REFILL` (pipeline stalled during refill)
- `ic_stall_o = 0` when hit (data available combinationally)

**Refill sequence** (4 AXI4-Lite read transactions, sequential):
```
Word 0: AR addr = {tag, index, 4'b0000}; R data → line[31:0]
Word 1: AR addr = {tag, index, 4'b0100}; R data → line[63:32]
Word 2: AR addr = {tag, index, 4'b1000}; R data → line[95:64]
Word 3: AR addr = {tag, index, 4'b1100}; R data → line[127:96]
After word 3: valid ← 1; tag ← address[31:12]; state → IC_IDLE
```

Note: AXI4-Lite does not support burst transactions. Each word requires a separate AR/R channel handshake. A refill counter (2-bit, 0-3) tracks progress.

### 3.2 D-Cache FSM

The D-Cache has a three-state FSM to handle the optional writeback before refill:

```
States:
  DC_IDLE       — Check for hit; serve data on hit; decide miss action on miss
  DC_WRITEBACK  — Write dirty evicted line to external memory (4 AXI writes)
  DC_REFILL     — Fetch new line from external memory (4 AXI reads)

Transitions:
  DC_IDLE → DC_WRITEBACK : hit=0 AND dirty[index]=1 (miss + dirty eviction)
  DC_IDLE → DC_REFILL    : hit=0 AND dirty[index]=0 (miss + clean eviction)
  DC_WRITEBACK → DC_REFILL : writeback_done (4th AXI write acknowledged)
  DC_REFILL → DC_IDLE      : refill_done (4th AXI read complete, cache line written)
  DC_IDLE → DC_IDLE        : hit=1 (serve data or write to cache, no state change)
```

**Stall behavior**:
- `dc_stall_o = 1` whenever `state == DC_WRITEBACK OR state == DC_REFILL`
- `dc_stall_o = 0` when hit (data available combinationally)

**Writeback sequence** (4 AXI4-Lite write transactions, sequential):
```
Word 0: AW addr = {evict_tag, index, 4'b0000}; W data = line[31:0]
Word 1: AW addr = {evict_tag, index, 4'b0100}; W data = line[63:32]
Word 2: AW addr = {evict_tag, index, 4'b1000}; W data = line[95:64]
Word 3: AW addr = {evict_tag, index, 4'b1100}; W data = line[127:96]
After word 3 B response received: dirty ← 0; state → DC_REFILL
```

The evicted tag must be saved on DC_IDLE → DC_WRITEBACK transition (since the tag array will be overwritten during refill).

**Refill sequence** (same as I-cache; see Section 3.1 but for D-cache base address).

**Write-allocate on store miss**: After refill completes, the MEM stage applies the pending store: `data[byte_offset] ← store_data; dirty ← 1`.

### 3.3 Stall Propagation

Cache misses stall the pipeline via the hazard unit:

| Stall Signal | Source | Effect |
|-------------|--------|--------|
| `if_cache_stall` | `ic_stall_o` from I-cache | Freeze PC, freeze IF/ID register |
| `mem_cache_stall` | `dc_stall_o` from D-cache | Freeze PC, IF/ID, ID/EX, EX/MEM, MEM stage |

`mem_cache_stall` causes a global pipeline freeze (same as Phase 2's AXI stall for loads/stores).

---

## 4. External Memory Interface

### 4.1 AXI4-Lite Transactions Per Cache Line

Cache misses generate up to 8 AXI4-Lite transactions (4 writes for dirty writeback + 4 reads for refill). All transactions are single-beat (no burst) because AXI4-Lite does not support burst mode.

| Operation | AXI Channels | Transactions | Notes |
|-----------|-------------|-------------|-------|
| I-cache refill | AR + R | 4 reads | Sequential, word-aligned addresses |
| D-cache refill | AR + R | 4 reads | Sequential, word-aligned addresses |
| D-cache writeback | AW + W + B | 4 writes | Sequential, word-aligned addresses |
| D-cache miss (dirty) | AW+W+B then AR+R | 4+4 = 8 | Writeback first, then refill |

**wstrb on writeback**: Full word writes use `4'b1111`. The D-cache does not track dirty bytes within a line — the entire line is written back on eviction.

### 4.2 Cache Arbiter

The Phase 2 `rv32i_axi_arbiter.sv` (which arbitrated between IF and MEM pipeline stages directly) is replaced by `rv32i_cache_arbiter.sv`, which arbitrates between the I-cache FSM and the D-cache FSM.

**Arbitration policy**: D-cache has priority over I-cache (same rationale as Phase 2: memory operations are on the critical path; IF can be stalled).

**Arbiter interface**:
- Two AXI4-Lite master ports (one from I-cache, one from D-cache)
- One AXI4-Lite master port to external memory
- When D-cache requests: grant D-cache; assert `ic_bus_stall` to I-cache
- When only I-cache requests: grant I-cache
- Mutual exclusion: only one outstanding transaction at a time (same Phase 2 constraint)

---

## 5. RTL Module Hierarchy

### 5.1 Module Hierarchy Diagram

```
rv32i_cpu_top                           # Unchanged external interface
├── rv32i_core                          # MODIFIED: instantiates caches, removes AXI arbiter
│   ├── rv32i_pipeline_if               # MODIFIED: cache interface instead of AXI
│   ├── rv32i_pipeline_id               # UNCHANGED
│   ├── rv32i_pipeline_ex               # UNCHANGED
│   ├── rv32i_pipeline_mem              # MODIFIED: cache interface + FENCE.I
│   ├── rv32i_pipeline_wb               # UNCHANGED
│   ├── rv32i_hazard_unit               # MODIFIED: rename stall signals, add cache stalls
│   ├── rv32i_forwarding_unit           # UNCHANGED
│   ├── rv32i_csr_file                  # UNCHANGED
│   ├── rv32i_interrupt_ctrl            # UNCHANGED
│   ├── rv32i_icache                    # NEW: I-cache with AXI refill FSM
│   └── rv32i_dcache                    # NEW: D-cache with AXI refill/writeback FSM
└── rv32i_cache_arbiter                 # NEW: D$ priority arbiter (replaces rv32i_axi_arbiter)
```

### 5.2 New Modules

| Module | File | Description |
|--------|------|-------------|
| `rv32i_cache_pkg` | `rtl/mem/rv32i_cache_pkg.sv` | Cache parameters, types, and shared structs |
| `rv32i_icache` | `rtl/mem/rv32i_icache.sv` | I-cache: 4KB direct-mapped, AXI refill FSM, FENCE.I |
| `rv32i_dcache` | `rtl/mem/rv32i_dcache.sv` | D-cache: 4KB direct-mapped, write-back, AXI refill/writeback FSM |
| `rv32i_cache_arbiter` | `rtl/mem/rv32i_cache_arbiter.sv` | D$ priority AXI arbiter (replaces rv32i_axi_arbiter) |

### 5.3 Modified Modules

| Module | File | Modifications |
|--------|------|--------------|
| `rv32i_pipeline_if` | `rtl/cpu/core/pipeline/rv32i_pipeline_if.sv` | Replace AXI read interface with I-cache CPU interface (`ic_addr_o`, `ic_valid_o`, `ic_rdata_i`, `ic_stall_i`); remove AXI state machine; stall now driven by `ic_stall_i` |
| `rv32i_pipeline_mem` | `rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv` | Replace AXI read/write with D-cache CPU interface; add FENCE.I detection and `ic_invalidate_o` assertion; stall driven by `dc_stall_i` |
| `rv32i_hazard_unit` | `rtl/cpu/core/rv32i_hazard_unit.sv` | Rename `if_axi_stall` → `if_cache_stall`; rename `mem_axi_stall` → `mem_cache_stall`; logic unchanged |
| `rv32i_core` | `rtl/cpu/core/rv32i_core.sv` | Instantiate `rv32i_icache` and `rv32i_dcache`; remove `rv32i_axi_arbiter` instantiation; route cache interfaces; expose combined AXI port from `rv32i_cache_arbiter` |
| `rv32i_pipeline_pkg` | `rtl/cpu/core/rv32i_pipeline_pkg.sv` | Add `fence_i` bit to `id_ex_reg_t` |
| `rv32i_decode` | `rtl/cpu/core/rv32i_decode.sv` | Add FENCE.I decode (opcode=0x0F, funct3=3'b001); output `fence_i` signal |

### 5.4 Unchanged Modules

| Module | File | Notes |
|--------|------|-------|
| `rv32i_cpu_top` | `rtl/cpu/rv32i_cpu_top.sv` | External interface unchanged; cache is transparent |
| `rv32i_pipeline_id` | `rtl/cpu/core/pipeline/rv32i_pipeline_id.sv` | Propagates `fence_i` from decoder |
| `rv32i_pipeline_ex` | `rtl/cpu/core/pipeline/rv32i_pipeline_ex.sv` | Propagates `fence_i` to EX/MEM register |
| `rv32i_pipeline_wb` | `rtl/cpu/core/pipeline/rv32i_pipeline_wb.sv` | Unchanged |
| `rv32i_forwarding_unit` | `rtl/cpu/core/rv32i_forwarding_unit.sv` | Unchanged |
| `rv32i_csr_file` | `rtl/cpu/core/rv32i_csr_file.sv` | Unchanged |
| `rv32i_interrupt_ctrl` | `rtl/cpu/core/rv32i_interrupt_ctrl.sv` | Unchanged |
| `rv32i_alu` | `rtl/cpu/core/rv32i_alu.sv` | Unchanged |
| `rv32i_regfile` | `rtl/cpu/core/rv32i_regfile.sv` | Unchanged |
| `rv32i_imm_gen` | `rtl/cpu/core/rv32i_imm_gen.sv` | Unchanged |
| `rv32i_branch_comp` | `rtl/cpu/core/rv32i_branch_comp.sv` | Unchanged |

### 5.5 New File Organization

```
rtl/
├── cpu/
│   ├── rv32i_cpu_top.sv               # UNCHANGED
│   └── core/
│       ├── rv32i_core.sv              # MODIFIED: add cache instantiation
│       ├── rv32i_hazard_unit.sv       # MODIFIED: rename stall signals
│       ├── rv32i_forwarding_unit.sv   # UNCHANGED
│       ├── rv32i_csr_file.sv          # UNCHANGED
│       ├── rv32i_interrupt_ctrl.sv    # UNCHANGED
│       ├── rv32i_decode.sv            # MODIFIED: add FENCE.I
│       ├── rv32i_pipeline_pkg.sv      # MODIFIED: add fence_i to id_ex_reg_t
│       ├── rv32i_alu.sv               # UNCHANGED
│       ├── rv32i_regfile.sv           # UNCHANGED
│       ├── rv32i_imm_gen.sv           # UNCHANGED
│       ├── rv32i_branch_comp.sv       # UNCHANGED
│       └── pipeline/
│           ├── rv32i_pipeline_if.sv   # MODIFIED: cache interface
│           ├── rv32i_pipeline_id.sv   # UNCHANGED (propagates fence_i)
│           ├── rv32i_pipeline_ex.sv   # UNCHANGED (propagates fence_i)
│           ├── rv32i_pipeline_mem.sv  # MODIFIED: cache interface + FENCE.I
│           └── rv32i_pipeline_wb.sv   # UNCHANGED
└── mem/
    ├── rv32i_cache_pkg.sv             # NEW: shared parameters and types
    ├── rv32i_icache.sv                # NEW: I-cache module
    ├── rv32i_dcache.sv                # NEW: D-cache module
    └── rv32i_cache_arbiter.sv         # NEW: D$ priority AXI arbiter
```

---

## 6. Interface Definitions

### 6.1 I-Cache CPU-Side Interface

The IF pipeline stage communicates with the I-cache through a simple request/response interface. No AXI signaling visible to the pipeline.

```systemverilog
// I-Cache CPU-side ports (within rv32i_icache module)
input  logic [31:0] ic_addr_i,       // Byte address of instruction to fetch (word-aligned)
input  logic        ic_valid_i,       // 1 = fetch request valid (CPU wants an instruction)
output logic [31:0] ic_rdata_o,       // 32-bit instruction word (valid when ic_stall_o=0)
output logic        ic_stall_o,       // 1 = cache miss in progress; pipeline must stall
input  logic        ic_invalidate_i,  // 1 = invalidate entire I-cache (FENCE.I)
```

**Protocol**:
- `ic_valid_i` is asserted when the IF stage needs a new instruction (not stalled by downstream)
- `ic_stall_o` is asserted on a cache miss; the IF stage must hold its PC and request
- `ic_rdata_o` is valid combinationally on a cache hit (when `ic_stall_o=0`)
- `ic_invalidate_i` is asserted for exactly 1 cycle by the MEM stage during FENCE.I execution

### 6.2 D-Cache CPU-Side Interface

The MEM pipeline stage communicates with the D-cache:

```systemverilog
// D-Cache CPU-side ports (within rv32i_dcache module)
input  logic [31:0] dc_addr_i,       // Byte address of memory access (word-aligned for word; may be byte-aligned for byte/half)
input  logic        dc_valid_i,       // 1 = access request valid
input  logic        dc_we_i,          // 1 = write, 0 = read
input  logic [31:0] dc_wdata_i,       // Write data (for stores; byte lane selected by dc_wstrb_i)
input  logic [3:0]  dc_wstrb_i,       // Byte write strobe (for stores: 4'b0001/0011/1111 for byte/half/word)
output logic [31:0] dc_rdata_o,       // Read data (full 32-bit word; MEM stage performs byte extraction)
output logic        dc_stall_o,       // 1 = cache miss in progress; pipeline must stall
```

**Protocol**:
- `dc_valid_i` is asserted when the MEM stage has a load or store to service
- `dc_stall_o` is asserted during miss handling; MEM stage freezes
- `dc_rdata_o` is the full 32-bit cache line word; the MEM stage applies sign extension and byte extraction (same as Phase 2 AXI path)
- For stores on a hit: cache line is updated immediately; `dc_stall_o=0` for the same cycle

### 6.3 Updated Hazard Unit Interface

The hazard unit port names are updated. Internal logic is unchanged.

```systemverilog
// Renamed from Phase 2:
input  logic        if_cache_stall,    // (was: if_axi_stall)  I-cache miss stall
input  logic        mem_cache_stall,   // (was: mem_axi_stall) D-cache miss stall
```

### 6.4 FENCE.I Decoder Output and Pipeline Propagation

```systemverilog
// New output in rv32i_decode.sv:
output logic        fence_i_o,         // 1 = FENCE.I instruction (opcode=0x0F, funct3=001)

// New field in id_ex_reg_t (rv32i_pipeline_pkg.sv):
logic               fence_i;           // Propagated to MEM stage via EX/MEM register

// In rv32i_pipeline_mem.sv:
// When ex_mem_reg_i.fence_i == 1 and stage is valid:
//   Assert ic_invalidate_o for 1 cycle
//   Assert dc_stall_o equivalent via mem_cache_stall
//   Instruction completes after 1 cycle (no AXI needed)
```

**FENCE.I encoding**: opcode=7'b0001111 (0x0F), funct3=3'b001. The `rs1`, `rd`, and upper immediate bits are ignored per the RISC-V specification.

### 6.5 Cache Arbiter Interface

```systemverilog
module rv32i_cache_arbiter (
    input  logic        clk_i,
    input  logic        rst_n_i,

    // I-Cache AXI master port (read-only; I-cache never writes)
    input  logic [31:0] ic_araddr_i,
    input  logic        ic_arvalid_i,
    output logic        ic_arready_o,
    output logic [31:0] ic_rdata_o,
    output logic [1:0]  ic_rresp_o,
    output logic        ic_rvalid_o,
    input  logic        ic_rready_i,

    // D-Cache AXI master port (read + write)
    input  logic [31:0] dc_araddr_i,
    input  logic        dc_arvalid_i,
    output logic        dc_arready_o,
    output logic [31:0] dc_rdata_o,
    output logic [1:0]  dc_rresp_o,
    output logic        dc_rvalid_o,
    input  logic        dc_rready_i,

    input  logic [31:0] dc_awaddr_i,
    input  logic        dc_awvalid_i,
    output logic        dc_awready_o,
    input  logic [31:0] dc_wdata_i,
    input  logic [3:0]  dc_wstrb_i,
    input  logic        dc_wvalid_i,
    output logic        dc_wready_o,
    output logic [1:0]  dc_bresp_o,
    output logic        dc_bvalid_o,
    input  logic        dc_bready_i,

    // External AXI4-Lite master port (to memory)
    output logic [31:0] axi_araddr_o,
    output logic        axi_arvalid_o,
    input  logic        axi_arready_i,
    input  logic [31:0] axi_rdata_i,
    input  logic [1:0]  axi_rresp_i,
    input  logic        axi_rvalid_i,
    output logic        axi_rready_o,

    output logic [31:0] axi_awaddr_o,
    output logic        axi_awvalid_o,
    input  logic        axi_awready_i,
    output logic [31:0] axi_wdata_o,
    output logic [3:0]  axi_wstrb_o,
    output logic        axi_wvalid_o,
    input  logic        axi_wready_i,
    input  logic [1:0]  axi_bresp_i,
    input  logic        axi_bvalid_i,
    output logic        axi_bready_o
);
```

---

## 7. Pipeline Integration Changes

### 7.1 IF Stage Changes

Phase 2 `rv32i_pipeline_if` contained an AXI read state machine (IDLE → FETCH → WAIT_RVALID). In Phase 3, this is replaced by a simple cache request:

```
Phase 2 (simplified):
  AR channel → wait arready → wait rvalid → latch instruction

Phase 3:
  Assert ic_addr_o = pc; ic_valid_o = 1
  If ic_stall_i == 0: latch ic_rdata_i → IF/ID register; advance PC
  If ic_stall_i == 1: hold PC; hold IF/ID; stall upstream
```

The AXI state machine (`ar_issued`, `fetch_pending_q`, etc.) is removed. The `ic_stall_i` input directly drives the pipeline freeze.

### 7.2 MEM Stage Changes

Phase 2 `rv32i_pipeline_mem` contained an AXI read/write state machine for loads and stores. In Phase 3:

**Load path**:
```
Assert dc_addr_o = alu_result; dc_valid_o = 1; dc_we_o = 0
If dc_stall_i == 0: latch dc_rdata_i; apply byte extraction → MEM/WB register
If dc_stall_i == 1: hold all pipeline registers
```

**Store path**:
```
Assert dc_addr_o = alu_result; dc_valid_o = 1; dc_we_o = 1; dc_wdata_o = rs2_data; dc_wstrb_o = strobe
If dc_stall_i == 0: store acknowledged; continue (no writeback needed)
If dc_stall_i == 1: hold all pipeline registers
```

**FENCE.I path**:
```
Detect ex_mem_reg_i.fence_i == 1 and ex_mem_reg_i.valid == 1
Assert ic_invalidate_o for 1 cycle
The stall lasts 1 cycle (dc_stall_o used to freeze pipeline via mem_cache_stall)
After 1 cycle: instruction retires normally; pipeline resumes
```

### 7.3 Pipeline Package Update

Add `fence_i` to `id_ex_reg_t` (already propagated through EX/MEM as part of `ex_mem_reg_t`):

```systemverilog
// In rv32i_pipeline_pkg.sv, id_ex_reg_t struct:
typedef struct packed {
    // ... all existing Phase 2 fields ...
    logic        fence_i;      // NEW: FENCE.I instruction (invalidate I-cache)
} id_ex_reg_t;
```

---

## 8. FENCE.I Execution Semantics

FENCE.I is specified in the RISC-V base ISA as an ordering fence between instruction stream and data writes. The minimal compliant implementation clears the I-cache, ensuring subsequent instruction fetches see the latest store data.

**Software use case**:
```assembly
# Write new code to memory
sw  t0, 0(a0)      # Store instruction word to code region
sw  t1, 4(a0)      # Store next instruction word
fence.i             # Flush I-cache so CPU sees the new instructions
jalr ra, a0, 0     # Jump to and execute the new code
```

**Hardware behavior**:
1. FENCE.I reaches MEM stage with `fence_i=1`
2. MEM stage asserts `ic_invalidate_i` to I-cache for 1 cycle
3. I-cache clears all 256 valid bits in one clock edge
4. MEM stage asserts `mem_cache_stall` for 1 cycle to drain
5. FENCE.I retires normally (no register write, no memory access)
6. Next instruction fetch after the jump will miss the now-empty I-cache and refill from memory

**FENCE (without .I)**: The plain FENCE instruction (opcode=0x0F, funct3=0x000) is treated as a NOP in Phase 3. Hardware coherence is not required for single-CPU systems.

---

## 9. Verification Strategy

### 9.1 Reference Model

A new Python cache model must be created: `tb/models/cache_model.py`

```python
class DirectMappedCache:
    """
    Direct-mapped write-back write-allocate cache model.
    Parameterizable: size, line_size, read_only (for I-cache).
    """
    def __init__(self, size=4096, line_size=16, read_only=False):
        ...
    def read(self, addr: int) -> int: ...           # Returns word; models stall count
    def write(self, addr: int, data: int, strobe: int) -> None: ...
    def invalidate(self) -> None: ...               # FENCE.I
    def get_stats(self) -> dict: ...                # hits, misses, writebacks
```

The existing `RV32IModel` must be updated to route instruction fetches through the `DirectMappedCache` instance. Memory access statistics are tracked for verification.

### 9.2 Test Plan

#### Group 1: I-Cache Unit Tests (`test_icache.py`)

| Test | Description | Check |
|------|-------------|-------|
| Cold start miss | Fresh cache, fetch instruction | Miss; 4 AXI reads; rdata correct |
| Sequential hit | Fetch 4 words from same cache line | First miss; words 2-4 hit (1-cycle) |
| Compulsory miss | 257 sequential cache sets accessed | Every access is a miss |
| Conflict miss | Two addresses mapping to same index | Second access evicts first |
| FENCE.I | Fetch; write to same addr; FENCE.I; re-fetch | After FENCE.I, re-fetch is a miss |
| AXI back-pressure | Randomize arready; icache still refills | Correct data; no hang |

#### Group 2: D-Cache Unit Tests (`test_dcache.py`)

| Test | Description | Check |
|------|-------------|-------|
| Read cold miss | Load from uncached address | 4 AXI reads; correct word returned |
| Write hit | Store to cached address | No AXI; dirty bit set |
| Write miss (clean) | Store to uncached (clean) address | 4 reads (allocate); then store applied |
| Write miss (dirty) | Store to address with dirty eviction | 4 writes (writeback) + 4 reads (refill) |
| Read miss (dirty) | Load from address with dirty eviction | 4 writes + 4 reads |
| Write-back on miss | Dirty line evicted; data verified in memory | AXI write data matches dirty line content |
| Byte/half-word store | SW strobe=4'b0001 and 4'b0011 | Correct byte lane updated in cache |
| AXI write back-pressure | Randomize bvalid | Writeback completes correctly |

#### Group 3: Cache Integration Tests (`test_cache_integration.py`)

| Test | Description | Check |
|------|-------------|-------|
| Full CPU + I-cache | Run smoke test with I-cache | Same commit sequence as Phase 2 |
| Full CPU + D-cache | Run load/store program with D-cache | Correct data; scoreboard match |
| Mixed I+D cache | Code with data segment; concurrent accesses | Arbiter prioritizes D$; I$ stalled |
| D$ arbiter priority | D-cache miss during I-cache refill | D$ wins; I$ waits; both complete |
| FENCE.I in program | Store to code region; FENCE.I; execute | New code executes correctly |
| Cache miss + interrupt | IRQ arrives during cache miss | IRQ taken after miss completes |
| Cache miss + debug halt | Halt during cache miss | Pipeline drains after miss; halts cleanly |
| Randomized latency | AXI arready/rvalid randomized | No deadlock; all accesses complete |
| Dirty eviction stress | Fill all 256 sets; then sequential scan | 256 writebacks + 256 refills; no corruption |

#### Group 4: Regression (Phase 2 Tests)

All Phase 2 tests must pass unchanged:
- smoke_uvm (4/4)
- isa_uvm (54/54) — including FENCE.I now as a valid instruction (not a trap)
- pipeline_hazards (16/16)
- interrupts (12/12)
- debug (6/6)
- axi_protocol (12/12)
- fault_injection (7/7)

**Note**: Phase 2 ISA compliance tests must be updated to expect FENCE.I to execute as a NOP (not trap as illegal instruction). This is the only behavioral change visible to existing tests.

### 9.3 Coverage Goals

| Coverage Metric | Target | Notes |
|----------------|--------|-------|
| I-cache hit | ≥ 80% of fetches | On any non-trivial program |
| I-cache miss | ≥ 100 occurrences | Cold start + compulsory misses |
| D-cache read hit | ≥ 50% of loads | After warm-up |
| D-cache read miss | ≥ 100 occurrences | Cold start + conflict |
| D-cache write hit | ≥ 50% of stores | After warm-up |
| D-cache write miss (clean) | ≥ 50 occurrences | Write-allocate path |
| D-cache dirty writeback | ≥ 50 occurrences | Write-back eviction path |
| FENCE.I executed | ≥ 10 occurrences | Invalidation correctness |
| AXI back-pressure during miss | ≥ 50% of miss transactions | Stall protocol correctness |
| D$ arbiter win over I$ | ≥ 20 occurrences | Priority correctness |

### 9.4 Deadlock and Livelock Checks

The following scenarios must be explicitly tested to verify no deadlock:

1. **I-cache miss while D-cache in writeback**: I-cache waits; D-cache completes writeback + refill; I-cache then refills
2. **D-cache miss while I-cache refilling**: D-cache gets priority; I-cache waits; D-cache refills; I-cache resumes
3. **AXI arready held low indefinitely**: FSM must not hang; arready will eventually be asserted by testbench
4. **FENCE.I during cache miss**: FENCE.I should not be issued while a miss is in progress (the MEM stage stalls until the miss resolves before FENCE.I reaches MEM)

---

## 10. Physical Design Targets

### 10.1 Frequency and Timing

| Parameter | Value | Notes |
|-----------|-------|-------|
| Target clock frequency | 75 MHz | Realistic for Sky130 130nm with SRAM macros; matches Phase 2 achieved frequency |
| Clock period | 13.33 ns | |
| Clock uncertainty | 0.5 ns | Larger than Phase 2 due to SRAM macro clock tree |
| Input delay (AXI) | 2.0 ns max, 0.5 ns min | Relaxed for 75 MHz target |
| Output delay (AXI) | 2.0 ns max, 0.5 ns min | |
| Setup margin target | ≥ 0.1 ns WNS | Sign-off criterion |
| Hold margin target | ≥ 0.0 ns TNS | Sign-off criterion |

**Rationale for 75 MHz**: Phase 2 achieved 75 MHz on Sky130 130nm (200 MHz target was not met due to PDK limitations). Phase 3 adds SRAM macro access paths on the critical path; 75 MHz is the realistic achievable frequency on Sky130.

### 10.2 Area Target

| Technology | Phase 2 (pipeline, no cache) | Phase 3 (pipeline + cache) | Notes |
|-----------|------------------------------|---------------------------|-------|
| Sky130 (130nm) | ~90k µm² | ~200k µm² | SRAM arrays dominate; 2x+ area increase |
| ASAP7 (7nm) | ~9k µm² | ~20k µm² | Same ratio |

Cache tag/data arrays are the dominant area contributors. Implementation uses register-based SRAM models (for simulation); physical design uses SRAM macros (where available).

### 10.3 Power Budget

| Parameter | Phase 2 | Phase 3 Target | Notes |
|-----------|---------|---------------|-------|
| Total power | < 10 mW @ 75 MHz | < 15 mW @ 75 MHz | Cache adds switching in data arrays |
| Cache dynamic power | N/A | < 5 mW | Dominated by SRAM array reads on hits |
| Clock tree | < 25% of total | < 20% of total | Lower frequency reduces clock power |

### 10.4 Critical Paths

| Critical Path | Estimated Depth | Notes |
|--------------|----------------|-------|
| Cache hit detection → data output (I-cache) | 4-6 logic levels | Tag compare + valid check + data mux |
| Cache hit detection → data output (D-cache) | 4-6 logic levels | Same as I-cache |
| Dirty bit check → DC_WRITEBACK → AXI AW | 2-3 logic levels | FSM transition |
| Arbiter decision → external AXI output | 2-3 logic levels | Combinational priority mux |

### 10.5 SDC Changes from Phase 2

The Phase 3 SDC file (`pnr/constraints/phase3_cache.sdc`) changes from Phase 2:

```
# Phase 3 clock - relaxed to 75 MHz (realistic for Sky130 + SRAM)
create_clock -name clk -period 13.33 [get_ports clk_i]

# Uncertainty increased for SRAM macro clock tree
set_clock_uncertainty 0.5 [get_clocks clk]

# AXI delays relaxed for 75 MHz
set_input_delay  -clock clk -max 2.0 [get_ports axi_*_i]
set_input_delay  -clock clk -min 0.5 [get_ports axi_*_i]
set_output_delay -clock clk -max 2.0 [get_ports axi_*_o]
set_output_delay -clock clk -min 0.5 [get_ports axi_*_o]

# Interrupt inputs
set_input_delay -clock clk -max 2.0 [get_ports {ext_irq_i timer_irq_i}]
set_input_delay -clock clk -min 0.5 [get_ports {ext_irq_i timer_irq_i}]

# APB3 debug (unchanged multi-cycle path)
set_multicycle_path -setup 2 -from [get_ports apb_*_i]
set_multicycle_path -hold  1 -from [get_ports apb_*_i]

# Commit interface (verification only)
set_false_path -from [get_ports {commit_valid_o commit_pc_o commit_insn_o}]
```

---

## 11. Implementation Roadmap

### Sub-task 1: Write rv32i_cache_pkg.sv
**Agent**: RTL Designer
**Priority**: P0 (blocks all cache modules)
**Objective**: Define cache parameters, types, and shared constants in a SystemVerilog package
**Deliverables**: `rtl/mem/rv32i_cache_pkg.sv`
**Key contents**: `CACHE_SIZE`, `LINE_SIZE`, `NUM_SETS`, `TAG_WIDTH`, `INDEX_WIDTH`, `OFFSET_WIDTH`; typedef for cache line entry (valid, dirty, tag, data)

### Sub-task 2: Write Python Cache Reference Model [depends: none]
**Agent**: Verification Engineer
**Priority**: P0 (blocks all cache integration tests)
**Objective**: Implement `DirectMappedCache` class in `tb/models/cache_model.py`
**Deliverables**: `tb/models/cache_model.py` with pytest tests; integrated into `RV32IModel` for instruction fetch

### Sub-task 3: Implement rv32i_icache.sv [depends: 1]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: 4 KB direct-mapped I-cache with AXI refill FSM and FENCE.I support
**Inputs**: Section 2 (cache parameters), Section 3.1 (I-cache FSM), Section 6.1 (CPU interface)
**Deliverables**: `rtl/mem/rv32i_icache.sv`
**Constraints**: Blocking on miss; 4 sequential AXI reads per refill; all valid bits cleared in 1 cycle on FENCE.I

### Sub-task 4: Implement rv32i_dcache.sv [depends: 1]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: 4 KB direct-mapped D-cache with write-back, write-allocate, AXI refill and writeback FSM
**Inputs**: Section 2 (cache parameters), Section 3.2 (D-cache FSM), Section 6.2 (CPU interface)
**Deliverables**: `rtl/mem/rv32i_dcache.sv`
**Constraints**: Writeback before refill when dirty; save evicted tag at DC_IDLE → DC_WRITEBACK transition

### Sub-task 5: Implement rv32i_cache_arbiter.sv [depends: 1]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Replace rv32i_axi_arbiter with D$ priority cache arbiter
**Inputs**: Section 4.2 (arbiter), Section 6.5 (interface)
**Deliverables**: `rtl/mem/rv32i_cache_arbiter.sv`
**Constraints**: D-cache has priority over I-cache; one outstanding transaction at a time

### Sub-task 6: Update rv32i_decode.sv (FENCE.I) [depends: none]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Add FENCE.I instruction decode; add `fence_i_o` output
**Inputs**: Section 6.4; RISC-V ISA encoding
**Deliverables**: Updated `rtl/cpu/core/rv32i_decode.sv`
**Constraints**: All Phase 2 decode outputs unchanged; FENCE (funct3=0) treated as NOP

### Sub-task 7: Update rv32i_pipeline_pkg.sv [depends: 6]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Add `fence_i` field to `id_ex_reg_t`
**Deliverables**: Updated `rtl/cpu/core/rv32i_pipeline_pkg.sv`

### Sub-task 8: Update rv32i_pipeline_if.sv [depends: 3]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Replace AXI state machine with I-cache CPU interface
**Inputs**: Section 7.1 (IF stage changes), Section 6.1 (cache interface)
**Deliverables**: Updated `rtl/cpu/core/pipeline/rv32i_pipeline_if.sv`

### Sub-task 9: Update rv32i_pipeline_mem.sv [depends: 4, 6, 7]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Replace AXI state machine with D-cache CPU interface; add FENCE.I handling
**Inputs**: Section 7.2 (MEM stage changes), Section 6.2 (cache interface), Section 8 (FENCE.I semantics)
**Deliverables**: Updated `rtl/cpu/core/pipeline/rv32i_pipeline_mem.sv`

### Sub-task 10: Update rv32i_hazard_unit.sv [depends: none]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Rename stall signal ports (`if_axi_stall` → `if_cache_stall`, `mem_axi_stall` → `mem_cache_stall`)
**Deliverables**: Updated `rtl/cpu/core/rv32i_hazard_unit.sv`
**Constraints**: Logic is unchanged; only port names change

### Sub-task 11: Update rv32i_core.sv [depends: 3, 4, 5, 8, 9, 10]
**Agent**: RTL Designer
**Priority**: P0
**Objective**: Wire I-cache and D-cache into core; route to arbiter; remove old AXI arbiter instantiation
**Deliverables**: Updated `rtl/cpu/core/rv32i_core.sv`

### Sub-task 12: I-Cache Unit Tests [depends: 3, 2]
**Agent**: Verification Engineer
**Priority**: P0
**Objective**: Directed tests for I-cache FSM correctness
**Inputs**: Section 9.2 Group 1
**Deliverables**: `tb/cocotb/mem/test_icache.py`

### Sub-task 13: D-Cache Unit Tests [depends: 4, 2]
**Agent**: Verification Engineer
**Priority**: P0
**Objective**: Directed tests for D-cache FSM correctness, write-back and write-allocate paths
**Inputs**: Section 9.2 Group 2
**Deliverables**: `tb/cocotb/mem/test_dcache.py`

### Sub-task 14: Cache Integration Tests [depends: 11, 12, 13]
**Agent**: Verification Engineer
**Priority**: P0
**Objective**: Full CPU + cache integration; regression; FENCE.I correctness
**Inputs**: Section 9.2 Groups 3 and 4
**Deliverables**: `tb/cocotb/mem/test_cache_integration.py`

### Sub-task 15: Random Instruction Regression [depends: 14]
**Agent**: Verification Engineer
**Priority**: P0
**Objective**: Run 50,000+ random instructions with cache enabled; target 0 failures
**Deliverables**: Updated `tb/generators/rv32i_instr_gen.py` (add FENCE.I to instruction mix); test results

### Sub-task 16: Physical Design — Phase 3 Backend [depends: all RTL sub-tasks]
**Agent**: Backend Engineer
**Priority**: P1
**Objective**: Synthesis + P&R + STA at 75 MHz target with SRAM models
**Inputs**: Section 10 (physical design targets), Section 10.5 (SDC)
**Deliverables**: `pnr/constraints/phase3_cache.sdc`; `pnr/constraints/phase3_cache.upf`; timing and area reports

---

## 12. Open Questions — Human Approval Required

All open questions for Phase 3 have been resolved prior to RTL implementation authorization.

### OQ-1: Cache Associativity

**Decision (2026-03-08)**: ✅ **Direct-mapped (1-way).**

Direct-mapped is simpler to implement, has lower area overhead, and is sufficient for an initial cache implementation. Higher associativity is deferred to Phase 5 if performance profiling shows conflict miss rates are problematic.

### OQ-2: Cache Line Size

**Decision (2026-03-08)**: ✅ **16 bytes (4 words).**

16 bytes balances spatial locality benefit with refill cost. A 4-word refill requires 4 AXI4-Lite transactions, which is acceptable. Larger lines (8 words) would reduce miss rate but increase refill latency per miss and area for the line buffers.

### OQ-3: Write Policy

**Decision (2026-03-08)**: ✅ **Write-back + write-allocate for D-cache.**

Write-back reduces AXI bus traffic (stores only write to external memory on eviction). Write-allocate is the standard complement to write-back. Write-through was rejected because it generates one AXI write per store, eliminating the bandwidth benefit of the cache.

### OQ-4: AXI Burst Support

**Decision (2026-03-08)**: ✅ **No burst — 4 separate AXI4-Lite transactions per refill.**

AXI4-Lite does not support bursts (it lacks the ARLEN/ARSIZE signals of full AXI4). Each word requires a separate AR + R channel handshake. This is consistent with Phase 1 and Phase 2 AXI4-Lite usage and requires no change to the external memory interface.

### OQ-5: Target Frequency

**Decision (2026-03-08)**: ✅ **75 MHz on Sky130.**

Phase 2 achieved 75 MHz on Sky130 130nm (the 200 MHz target was not met due to PDK limitations). Phase 3 adds SRAM access paths which are not faster than the Phase 2 critical paths. 75 MHz is the realistic and achievable target for this PDK.

### OQ-6: Blocking vs Non-Blocking Cache

**Decision (2026-03-08)**: ✅ **Blocking (stall pipeline on every miss).**

A non-blocking (lockup-free) cache would allow the pipeline to continue executing non-dependent instructions during a miss. This requires a Miss Status Holding Register (MSHR) and significantly more complex design. Blocking is correct, simpler, and sufficient for Phase 3. Non-blocking is deferred to a potential Phase 3.5 or later.

---

## 13. Appendix: FENCE.I Instruction Encoding

```
31                  20 19    15 14  12 11    7 6      0
[ imm[11:0] (ignored)  | rs1    | 001 | rd     | 0001111 ]  FENCE.I
```

- opcode: `7'b0001111` (0x0F)
- funct3: `3'b001`
- `imm`, `rs1`, `rd` are ignored by hardware (per RISC-V spec; software sets them to 0)

**FENCE (not FENCE.I)**:
```
[ imm[11:0] (ignored)  | rs1    | 000 | rd     | 0001111 ]  FENCE
```
- funct3: `3'b000`
- Treated as NOP in Phase 3 (single CPU, no coherence required)

---

## 14. References

- PHASE2_ARCHITECTURE_SPEC.md: Phase 2 pipelined CPU specification (prerequisite)
- PHASE0_ARCHITECTURE_SPEC.md: Architectural requirements (ISA, reset, traps)
- RTL_DEFINITION.md: Interface signal definitions
- MEMORY_MAP.md: Address space — Phase 2-3 cache configuration (Section: Phase 2-3)
- REFERENCE_MODEL_SPEC.md: Python reference model API
- VERIFICATION_PLAN.md: Phase-aligned verification strategy
- RISC-V ISA Volume I: RV32I Base Integer Instruction Set — Chapter on FENCE.I
- RISC-V ISA Volume II: Privileged Architecture Specification
- AMBA AXI4-Lite Protocol Specification (ARM IHI 0022E)
- docs/design/OPENROAD_FLOW_SPEC.md: Physical design flow
- docs/design/SDC_TIMING_SPEC.md: Timing constraint guidelines
- pnr/constraints/phase2_cpu.sdc: Phase 2 SDC (baseline for Phase 3)
- pnr/constraints/phase2_cpu.upf: Phase 2 UPF (baseline for Phase 3)
