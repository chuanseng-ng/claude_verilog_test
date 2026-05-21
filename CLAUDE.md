# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Multi-phase RV32I RISC-V microprocessor + GPU-lite SoC project

**Current Phase**: Phase 4 (GPU-Lite SIMT Compute Engine) — ⏸️ NOT STARTED

**Status**: Phase 3 complete (2026-05-21, 20 cache tests, 139/139 total, ASAP7 1418 MHz sign-off); Phase 2 complete (2026-03-08, 75 MHz on Sky130)

**Target**: Build a complete SoC with CPU, GPU, caches, and peripherals through incremental phases

## Project Phases

See `docs/ROADMAP.md` for complete phase plan and `docs/PHASE_STATUS.md` for current status.

### Phase 0: Foundations ✅ COMPLETE

- **Status**: ✅ Complete and approved (2026-01-18)
- **Goal**: Finalize all specifications and reference models
- **Deliverables**: Architecture specs (✅ complete), Python reference models (✅ 66/66 tests passing), test infrastructure (✅ complete)
- **No RTL** (as planned)
- **Exit Criteria Met**: All 7 specifications approved, Python reference models tested and validated, cocotb infrastructure ready

### Phase 1: Minimal RV32I Core ✅ COMPLETE

- **Status**: ✅ Complete (2026-02-13)
- **ISA**: RISC-V RV32I (37 base integer instructions)
- **Architecture**: Single-cycle (stalls on memory operations)
- **Memory Interface**: AXI4-Lite Master (unified instruction/data)
- **Debug Interface**: APB3 Slave (halt/resume/step/breakpoints)
- **Verification**: 9/9 exit criteria met, archived to `micro_p/`

### Phase 2: Pipelined CPU ✅ COMPLETE

- **Status**: ✅ Complete (2026-03-08) — 75 MHz on Sky130 130nm
- **ISA**: RV32I + Zicsr (CSR instructions)
- **Architecture**: 5-stage in-order pipeline (IF/ID/EX/MEM/WB)
- **Interrupt Support**: M-mode (timer + external interrupts)
- **Hazard Handling**: Detection, stalling, forwarding
- **Achieved Frequency**: 75 MHz on Sky130 130nm (200 MHz target not met due to PDK limitations)
- **Verification**: 111/111 tests passing, 50,000 random instructions, 0 failures

### Phase 3: Memory System & Caches ✅ COMPLETE (2026-05-21)

- **Status**: ✅ Complete — 20/20 cache tests, 139/139 full regression, ASAP7 PPA sign-off at **1418 MHz / 27.27 mW / 3,844 µm²** (Run 43, 2026-05-20)
- **Architecture**: L1 I-Cache (4 KB, direct-mapped) + L1 D-Cache (4 KB, direct-mapped, write-back + write-allocate)
- **Cache Line**: 16 bytes (4 words); 256 sets; 4 AXI4-Lite transactions per refill
- **FENCE.I**: Supported — invalidates I-cache in 1 cycle
- **Achieved Frequency**: 75 MHz on Sky130 (PDK ceiling); 1418 MHz on ASAP7 7nm (Run 43)

### Phase 3-5: Future Phases

- **Phase 3**: Memory system with I-cache + D-cache (write-back, no coherence) ✅ COMPLETE
- **Phase 4**: GPU-lite SIMT compute engine (8-lane warps, single compute unit, no graphics)
- **Phase 5**: SoC integration (CPU + GPU + DMA + AXI4 crossbar + UART + SPI + Timer + behavioral SRAM)

**Note**: GPU in Phase 4 requires Phase 2+ CPU for interrupt support (kernel completion notifications)

### Phase 6+: IP Expansion and Tech Node Exploration (Future)

**Additional peripheral IPs** — GPIO through TRNG attach as pure AXI4-Lite slaves on the Phase 5 peripheral ring; the AES/SHA-256 accelerator splits control and data planes:
- **GPIO controller** — general I/O pad ring; needed by virtually every embedded SoC
- **I2C controller** — sensor/EEPROM interface; complements Phase 5 SPI
- **PWM controller** — counter + compare registers; motor/LED control
- **Watchdog timer** — counter with AON-domain reset output; embedded safety
- **TRNG** — ring-oscillator entropy source; Sky130 analog oscillators usable
- **AES/SHA-256 accelerator** — AXI4-Lite slave for control/status and key/IV/digest registers; AXI4 master+slave for bulk plaintext/ciphertext DMA; AES-128 round function fits ~6 LUT levels at 75 MHz on Sky130

**NPU (Neural Processing Unit)** — attach as AXI4 master+slave on the Phase 5 crossbar:
- Minimal viable config: 4×4 INT8 MAC array (16 MACs, 64 ops/cycle), 16 KB weight SRAM
- Sufficient for keyword spotting / gesture detection class workloads (~3.2 GOPS at 50 MHz)
- Sky130 estimate: ~5,000 cells, ~20–30 µm², ~5–10 mW; Phase 6 IP
- Full NPU (INT4, tiling, sparsity) benefits from FreePDK45 or ASAP7 node

**Tech node progression**: Sky130 → FreePDK45/NanGate45 → ASAP7 (see Technology Node Strategy below)

### Phase 4: GPU-Lite SIMT Engine (Planned)

- **ISA**: Custom 32-bit vector encoding — VADD, VSUB, VMUL, VAND, VOR, VSLL, VLD, VST, VBEQ, VBNE, VJMP, VRET, VSYNC
- **Execution**: Single compute unit; 8 SIMD lanes; 8 warps max; 64 total threads
- **Register file**: 32 registers × 8 threads per warp (1 KB total)
- **Divergence**: Single-level SIMT stack with per-lane active mask
- **Scheduler**: Round-robin warp selection
- **Shared memory**: 16 KB scratchpad, 32 banks
- **Memory**: AXI4 master (burst-capable) + memory coalescer (8-lane requests → fewer AXI4 burst transactions)
- **Control interface**: AXI-Lite slave (kernel launch via command queue)
- **CPU notification**: Interrupt output on kernel completion
- **Coherency**: Software-managed — CPU flushes D-cache before kernel launch; CPU invalidates D-cache after kernel completion. No hardware coherence protocol.
- **Spec**: `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md`

### Phase 5: SoC Integration (Planned)

- **Interconnect**: AXI4 crossbar (data fabric) + AXI-Lite bus (control/config)
  - AXI4 masters: CPU D-cache (upgraded to burst mode), GPU, DMA engine
  - AXI4 slave: behavioral SRAM controller (no DRAM refresh)
  - AXI-Lite slaves: GPU config registers, DMA control registers, UART, SPI, timer, IRQ controller
- **Cache upgrade**: Phase 3 refill FSMs upgraded from 4 sequential AXI4-Lite beats to AXI4 burst transactions
- **DMA engine**: Descriptor queue, AXI4 master, interrupt output to CPU
- **Peripherals**: UART, SPI, timer, interrupt controller (routed to CPU M-mode external interrupt)
- **Memory model**: Behavioral AXI4-slave SRAM (no DRAM refresh logic)
- **Power domains**: PD_CPU, PD_GPU, PD_SRAM, PD_PERIPH (clock gating + power gating per `UPF_POWER_SPEC.md`)
- **Performance counters**: CSR-mapped — cycle count, instructions retired, branch mispredictions, I$/D$ miss counts, active warps, warp stall cycles, divergence events
- **Benchmarks**: CPU (vector add, dot product, memcpy, branch loop); GPU (vector add, parallel reduction, matrix multiply, prefix scan, divergence test)

## Key Documentation

**Always refer to these specifications** (do not rely on non-existent RTL):

### Architecture & Design

| Document | Purpose |
| :------- | :------ |
| `docs/ROADMAP.md` | High-level project plan and phases |
| `docs/PHASE_STATUS.md` | Current project status and next steps |
| `docs/design/PHASE0_ARCHITECTURE_SPEC.md` | CPU architectural requirements (Phase 0) |
| `docs/design/PHASE1_ARCHITECTURE_SPEC.md` | CPU implementation spec (Phase 1) - ✅ Complete |
| `docs/design/PHASE2_ARCHITECTURE_SPEC.md` | Pipelined CPU spec (Phase 2) - ✅ Complete |
| `docs/design/PHASE3_ARCHITECTURE_SPEC.md` | Cache architecture spec (Phase 3) - ✅ Approved |
| `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md` | GPU architecture spec (Phase 4) — frozen ISA/execution model |
| `docs/PHASE3_CLOSURE_AND_PHASE4_PLAN.md` | Phase 3 closure + Phase 4 implementation plan (golden spec) |
| `docs/design/RTL_DEFINITION.md` | Interface signal definitions |
| `docs/design/MEMORY_MAP.md` | Address space and register map |
| `docs/design/REFERENCE_MODEL_SPEC.md` | Python reference model API |

### Physical Design (NEW)

| Document | Purpose |
| :------- | :------ |
| `docs/design/OPENROAD_FLOW_SPEC.md` | Complete OpenROAD flow documentation |
| `docs/design/UPF_POWER_SPEC.md` | Power intent and UPF specification |
| `docs/design/SDC_TIMING_SPEC.md` | Timing constraints and STA guidelines |
| `pnr/README.md` | Physical design directory structure |
| `pnr/constraints/phase1_cpu.sdc` | Phase 1 timing constraints |
| `pnr/constraints/phase1_cpu.upf` | Phase 1 power intent |

### Knowledge Graph

A graphify knowledge graph of `rtl/`, `docs/`, and `fixes/` is available in `graphify-out/`:

| File | Purpose |
| :--- | :------ |
| `graphify-out/graph.html` | Interactive navigable graph — open in browser |
| `graphify-out/graph.json` | Raw graph data (261 nodes, 324 edges, 32 communities) |
| `graphify-out/GRAPH_REPORT.md` | God nodes, surprising connections, suggested questions |

**Key findings from the graph:**
- **God nodes**: `rv32i_core` (22 edges), `rv32i_control` (16 edges) — central integration hubs
- `rv32i_control` bridges Pipeline Control, Cache Protocol, and AXI Bug Fix communities
- The hazard unit is simultaneously touched by Phase 2 spec and Phase 3 status — hidden cross-phase dependency
- `SDC Timing Constraints Specification` is a surprising cross-cutting hub linking RTL decisions to PD targets

**To update the graph** after adding RTL or docs:
```bash
/graphify rtl docs fixes --update
```

## Technology Node Strategy

Three nodes are supported by the existing `pnr/Makefile`. Use the right node for the right goal:

| Node | Makefile target | Config status | Realistic CPU freq | Fabricatable | Best use |
|------|----------------|---------------|-------------------|--------------|----------|
| **Sky130 130nm** | `librelane-sky130`, `docker-run` | ✅ Complete | 75–100 MHz | ✅ Yes (SkyWater MPW) | Functional sign-off; tape-out candidate |
| **FreePDK45 / NanGate45 45nm** | `librelane-nangate45` | ✅ Complete (`pnr/freepdk45/`) | 150–250 MHz | No (predictive) | First non-Sky130 exploration; SRAM macros available |
| **ASAP7 7nm FinFET** | `librelane-asap7` | ✅ Complete (`pnr/asap7/`); Run 43 signoff 2026-05-20 | **1418 MHz achieved (Run 43)** | No (predictive) | Phase 2+3 RTL PPA sign-off completed at 1418 MHz / 27.27 mW / 3 844 µm² |

### Sky130 PPA ceiling (assessed 2026-03-28)
Sky130 130nm is frequency-limited by cell drive strength and clock tree skew. The realistic ceiling for this pipeline topology is **~100–120 MHz** with all optimisations applied — not the 200–500 MHz originally targeted.

| Technique | Gain | Effort |
|-----------|------|--------|
| Switch to `sky130_fd_sc_hs` (high-speed cell library) | +10–30 MHz | Low — Makefile config change |
| EX-stage retiming (split ALU + branch-compare) | +15–25 MHz | Medium — re-verify forwarding paths |
| SDC multi-cycle exemptions for CSR/debug paths | +5–10 MHz | Low — SDC annotation only |
| Floorplan: place forwarding mux adjacent to ALU | +5–10 MHz | Medium — P&R iteration |
| **Combined ceiling** | **~100–120 MHz** | |

### FreePDK45/NanGate45 (ready to run)
`pnr/freepdk45/` is fully configured: `config.json` (2.5 ns / 400 MHz target), SRAM macros (`sram_1rw_256x32_freepdk45` with LEF/LIB/GDS), `macro_placement.cfg`, `pdn.tcl`, `freepdk45.sdc`, `freepdk45.upf`. Run with `make librelane-nangate45`. Expected Phase 2 result: 150–250 MHz, ~8–10× logic density vs Sky130.

### ASAP7 (Phase 2+3 sign-off achieved at Run 43, 2026-05-20)
`pnr/asap7/` is fully configured and signed off: `config.json` (705 ps / 1418 MHz, CTS clustering 8/10, density 50 %), `constraints/asap7.sdc` (single-period clock, hold/setup uncertainty 10/15 ps, SRAM ICG `gclk_sram` generated clock + false-paths), `macro_placement.cfg`, `pdn.tcl`, `sram_1rw_256x32_asap7_TT_0p7V_25C.lib` (RVT TT 0.7 V / 25 °C). Run with `make librelane-asap7`. Final achieved PPA: **1418 MHz fmax, 27.27 mW power, 3 844 µm² stdcell, 0 DRC, 0 antenna, +5.97 ps setup slack, +22.54 ps hold slack** at run `pnr/asap7/runs/RUN_2026-05-20_06-27-10/`. See `docs/ASAP7_RUN_HISTORY.md` for the full 44-run campaign history.

### Verification

| Document | Purpose |
| :------- | :------ |
| `docs/verification/VERIFICATION_PLAN.md` | Verification strategy (RTL + physical design) |
| `TODO_PHASE1_VERIFICATION.md` | Phase 1 verification progress tracking |
| `docs/RANDOM_TESTS_STATUS.md` | Random instruction test results and guide |

### RTL Fixes & Debugging

| Document | Purpose |
| :------- | :------ |
| `fixes/FIXES_INDEX.md` | ⭐ **Central reference for all RTL bug fixes** |
| `fixes/README.md` | Fixes directory guide and navigation |
| `fixes/CRITICAL_FIXES.md` | Critical AXI protocol fixes (2026-01-19) |
| `fixes/RTL_BUG_FIXES.md` | Branch/jump/memory fixes (2026-01-24) |
| `CLEANUP_SUMMARY.md` | Documentation organization summary |

**Note**: All RTL bugs discovered during development are documented in `fixes/` with full analysis, impact assessment, and validation. Start with `fixes/FIXES_INDEX.md` for quick reference.

## Frequently Used Commands

### Phase 0 (Complete): Reference Model and Tests

```bash
# Run reference model unit tests
cd tb/tests
pytest test_rv32i_model.py -v

# Run reference model with coverage
pytest --cov=tb.models --cov-report=html

# Test memory model
pytest test_memory_model.py -v
```

### Phase 1: OpenROAD Back-End Flow (NEW)

```bash
# Navigate to physical design directory
cd pnr

# Run full flow (synthesis through power analysis)
make all

# Run individual stages
make synth        # RTL synthesis
make floorplan    # Floorplanning
make place        # Placement
make cts          # Clock tree synthesis
make route        # Routing
make parasitics   # RC extraction
make sta          # Static timing analysis
make power        # Power analysis

# Generate reports
make report_timing   # Show timing summary
make report_power    # Show power summary
make report_area     # Show area summary
make report_summary  # Show all reports

# Clean build artifacts
make clean
```

### Phase 1+: Simulation Commands (When RTL exists)

#### WSL Commands (Windows Environment)

```bash
# Build and run simulation
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make sim"
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make run"

# Clean and rebuild
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make clean && make run"

# Run with waveform generation
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make waves"

# Run cocotb tests
wsl bash -c "cd /mnt/c/Users/waele/Documents/Github/claude_verilog_test/sim && make test"
```

#### Native Linux/WSL Commands

```bash
# Navigate to simulation directory
cd sim

# Build and run cocotb tests
make test

# Run specific test
make test TEST=test_simple_add

# Run with waveforms
make waves

# Clean build artifacts
make clean
```

### Git Commands

```bash
# Check status
git status

# View recent commits
git log --oneline -5

# Create feature branch
git checkout -b feature/branch-name

# Commit with co-author
git commit -m "$(cat <<'EOF'
[Category] Commit message

Description here.

Co-Authored-By: Claude Sonnet 4.5 <noreply@anthropic.com>
EOF
)"
```

## Planned Architecture (Phase 1)

**Note**: This architecture will be implemented in Phase 1. No RTL currently exists.

```text
rtl/
└── cpu/
    ├── rv32i_cpu_top.sv          # Top-level (AXI + APB)
    └── core/
        ├── rv32i_core.sv         # CPU core wrapper
        ├── rv32i_control.sv      # Control FSM
        ├── rv32i_decode.sv       # Instruction decoder
        ├── rv32i_alu.sv          # ALU (all RV32I ops)
        ├── rv32i_regfile.sv      # 32x32-bit registers
        └── rv32i_imm_gen.sv      # Immediate generator
```

See `docs/design/PHASE1_ARCHITECTURE_SPEC.md` for complete module specifications.

## Planned Debug Interface (APB3)

**Note**: To be implemented in Phase 1. Specification ready in `docs/design/MEMORY_MAP.md`.

| Address | Register | Description |
| :-----: | :------: | :---------: |
| 0x000 | DBG_CTRL | [0]=halt, [1]=resume, [2]=step, [3]=reset |
| 0x004 | DBG_STATUS | [0]=halted, [1]=running, [7:4]=halt_cause |
| 0x008 | DBG_PC | Program Counter (RW when halted) |
| 0x00C | DBG_INSTR | Current instruction (RO) |
| 0x010-0x08C | DBG_GPR[0:31] | General purpose registers (RW when halted) |
| 0x100 | DBG_BP0_ADDR | Breakpoint 0 address |
| 0x104 | DBG_BP0_CTRL | [0]=enable |
| 0x108 | DBG_BP1_ADDR | Breakpoint 1 address |
| 0x10C | DBG_BP1_CTRL | [0]=enable |

Complete register map in `docs/design/MEMORY_MAP.md`.

## Key Design Decisions (From Specifications)

**Phase 1 CPU**:

- Single-cycle execution with AXI stalls for memory operations
- Unified AXI4-Lite bus for instruction fetch and data access
- x0 register hardwired to zero (per RV32I spec)
- EBREAK instruction triggers CPU halt
- Debug writes only allowed when CPU is halted
- Only illegal instruction traps supported (no interrupts in Phase 1)
- Naturally aligned memory accesses only (misaligned = trap)

**Phase 4 GPU**:

- SIMT execution model (8 lanes per warp)
- Single compute unit
- Round-robin warp scheduling
- One-level divergence handling
- No cache coherence with CPU
- Memory coalescing when possible

**Sky130 frequency ceiling**: ~100–120 MHz maximum for this CPU pipeline topology (see Technology Node Strategy). PDK limitation — not an RTL issue. For higher frequencies, target FreePDK45/NanGate45 (150–250 MHz) or ASAP7 (**1418 MHz demonstrated** at Run 43, 2026-05-20).

**Phase 5 SoC — Locked Architecture Decisions** (confirmed 2026-03-28):

1. **Cache line size**: 16 bytes locked for Phase 3. Revisit 32-byte lines only if/when an L2 cache is added.
2. **Cache associativity**: Direct-mapped locked for Phase 3. Upgrade to 2-way I-cache / 1-4 way D-cache only if Phase 5 benchmarks prove measurable conflict-miss impact.
3. **AXI4 burst upgrade**: Phase 3 refill FSMs use 4 sequential AXI4-Lite transactions. These are upgraded to AXI4 burst mode during Phase 5 SoC integration — do not change Phase 3 FSMs before then.
4. **L2 cache**: Not in base Phase 5 scope. Add only if Phase 5 benchmarking shows L1 miss rates are a bottleneck.
5. **DRAM controller**: Use behavioral AXI4-slave SRAM model for Phase 5. Real DRAM controller (with refresh) is a Phase 6+ stretch goal only if tape-out is targeted.

## Reference Model (Python)

**Phase 0 deliverable**: Python reference models for CPU and GPU

**Location**: `tb/models/`

**Key files**:

- `rv32i_model.py` - CPU instruction-accurate model
- `gpu_kernel_model.py` - GPU SIMT execution model
- `memory_model.py` - Shared memory model

**Usage**:

```python
from tb.models.rv32i_model import RV32IModel

cpu = RV32IModel()
cpu.load_program({0x0000: 0x00000093})  # addi x1, x0, 0
result = cpu.step(0x00000093)
assert result['rd'] == 1
```

See `docs/design/REFERENCE_MODEL_SPEC.md` for complete API.

## Verification Strategy

**Phase 0 focus**:

1. Implement Python reference models
2. Unit test reference models (pytest)
3. Cross-validate CPU model vs RISC-V spike simulator
4. Setup cocotb infrastructure

**Phase 1+ focus**:

1. cocotb for interface drivers
2. pyuvm for test sequences and scoreboards
3. Compare RTL commits against reference model
4. Random instruction testing (10k+ instructions)

See `docs/verification/VERIFICATION_PLAN.md` for phase-by-phase verification plan.

## Common Workflow

### Phase 0 Workflow ✅ Complete

1. ✅ **Read specifications**: All docs in `docs/design/` reviewed
2. ✅ **Implement reference model**: Python models per `REFERENCE_MODEL_SPEC.md` complete
3. ✅ **Test reference model**: pytest passing (66/66 tests), cross-validated
4. ✅ **Setup testbench**: cocotb infrastructure ready
5. ✅ **Review**: All specs approved, ready for Phase 1

### Phase 1 Workflow ✅ Complete

1. ✅ **Write RTL**: All 8 modules implemented
2. ✅ **Lint**: Verilator lint checks passing
3. ✅ **Write tests**: Comprehensive cocotb test suite
4. ✅ **Run tests**: All tests passing (9/9 exit criteria met)
5. ✅ **Debug**: Major bugs fixed (branch/jump, load data, regfile)
6. ✅ **Complete**: Phase 1 archived to `micro_p/`, ready for Phase 2

### Phase 2 Workflow ✅ Complete

1. ✅ **Architecture approved**: All design decisions finalized
2. ✅ **Write RTL**: All 14 pipeline modules implemented
3. ✅ **Initial testing**: 115/115 regression tests passing
4. ✅ **Comprehensive verification**: 111/111 tests passing (all 7 suites)
5. ✅ **Random regression**: 50,000 instructions, 0 failures
6. ✅ **Backend flow**: 75 MHz achieved on Sky130 130nm
7. ✅ **Sign-off**: Phase 2 complete (2026-03-08)

### Phase 3 Workflow ✅ Complete (2026-05-21)

1. ✅ **Architecture approved**: All 6 design decisions finalized (2026-03-08)
2. ✅ **Write RTL**: Cache package, I-cache, D-cache, arbiter + modified pipeline stages (~1,424 lines)
3. ✅ **Unit tests**: I-cache 7/7, D-cache 8/8 passing
4. ✅ **Integration tests**: 5/5 cache integration tests passing; FENCE.I verified
5. ✅ **Phase 2 regression**: 139/139 total (119 Phase 2 + 20 Phase 3 cache tests)
6. ✅ **Random regression**: 50,000+ instructions with caches enabled, 0 failures
7. ✅ **Backend flow**: ASAP7 sign-off at **1418 MHz / 27.27 mW / 3,844 µm²** (Run 43, 2026-05-20); Sky130 ceiling 75 MHz
8. ✅ **Sign-off**: Phase 3 complete (2026-05-21)

### Phase 4 Workflow (Planned — GPU-Lite)

1. ⏸️ **Architecture review**: Confirm `docs/design/PHASE4_GPU_ARCHITECTURE_SPEC.md` covers all open questions
2. ⏸️ **Write GPU RTL**: 9 modules in `rtl/gpu/` (see Project Structure above)
3. ⏸️ **Unit tests**: Warp scheduling, SIMT divergence, memory coalescing, shared memory
4. ⏸️ **GPU kernel tests**: Vector add, parallel reduction, divergence test kernels
5. ⏸️ **Phase 3 regression**: All cache + Phase 2 tests must still pass
6. ⏸️ **Backend flow**: Synthesis + P&R + STA for GPU block
7. ⏸️ **Sign-off**: GPU verified standalone; ready for SoC integration

### Phase 5 Workflow (Planned — SoC Integration)

1. ⏸️ **AXI4 interconnect**: Build `axi4_crossbar.sv`, `axi_lite_interconnect.sv`; upgrade Phase 3 cache refill FSMs to AXI4 burst mode
2. ⏸️ **Peripherals**: UART, SPI, timer, interrupt controller, DMA engine in `rtl/periph/`
3. ⏸️ **SRAM controller**: Behavioral AXI4-slave in `rtl/soc/sram_controller.sv`
4. ⏸️ **SoC top integration**: Wire CPU + GPU + DMA + peripherals in `rtl/soc/soc_top.sv`
5. ⏸️ **Performance counters**: Add CSR-mapped counters (cache misses, branch mispredictions, warp stalls, divergence events)
6. ⏸️ **CPU-GPU integration tests**: Kernel launch → interrupt → result read; DMA transfers; software coherency sequence
7. ⏸️ **Full regression**: All prior tests; CPU + GPU benchmarks
8. ⏸️ **L2 cache evaluation**: Review L1 miss rates from benchmarks; add `rtl/mem/l2_cache.sv` only if justified
9. ⏸️ **Backend flow**: Full SoC synthesis + P&R + STA; `pnr/constraints/phase5_soc.sdc`, `phase5_soc.upf`
10. ⏸️ **Sign-off**: Coverage, power analysis, final review

## Project Structure

```text
.
├── docs/                     # All specifications
│   ├── ROADMAP.md
│   ├── PHASE_STATUS.md
│   ├── design/
│   │   ├── PHASE0_ARCHITECTURE_SPEC.md
│   │   ├── PHASE1_ARCHITECTURE_SPEC.md
│   │   ├── PHASE4_GPU_ARCHITECTURE_SPEC.md
│   │   ├── RTL_DEFINITION.md
│   │   ├── MEMORY_MAP.md
│   │   ├── REFERENCE_MODEL_SPEC.md
│   │   ├── OPENROAD_FLOW_SPEC.md    # NEW: Physical design flow
│   │   ├── UPF_POWER_SPEC.md        # NEW: Power intent
│   │   └── SDC_TIMING_SPEC.md       # NEW: Timing constraints
│   └── verification/
│       └── VERIFICATION_PLAN.md
├── rtl/
│   ├── cpu/
│   │   ├── rv32i_cpu_top.sv           # Top-level (AXI4-Lite + APB3)
│   │   ├── rv32i_axi_arbiter.sv       # Phase 2 arbiter (replaced by cache arbiter in Phase 3)
│   │   └── core/
│   │       ├── rv32i_core.sv          # Core wrapper (MODIFIED in Phase 3: adds caches)
│   │       ├── rv32i_pipeline_pkg.sv  # Pipeline structs (MODIFIED: fence_i added)
│   │       ├── rv32i_hazard_unit.sv   # Hazard unit (MODIFIED: renamed stall signals)
│   │       ├── rv32i_decode.sv        # Decoder (MODIFIED: FENCE.I added)
│   │       └── pipeline/
│   │           ├── rv32i_pipeline_if.sv   # IF stage (MODIFIED: cache interface)
│   │           ├── rv32i_pipeline_id.sv   # ID stage
│   │           ├── rv32i_pipeline_ex.sv   # EX stage
│   │           ├── rv32i_pipeline_mem.sv  # MEM stage (MODIFIED: cache + FENCE.I)
│   │           └── rv32i_pipeline_wb.sv   # WB stage
│   ├── mem/                           # NEW in Phase 3: cache RTL
│   │   ├── rv32i_cache_pkg.sv         # Cache parameters and types
│   │   ├── rv32i_icache.sv            # I-cache (4 KB, direct-mapped)
│   │   ├── rv32i_dcache.sv            # D-cache (4 KB, write-back)
│   │   └── rv32i_cache_arbiter.sv     # D$ priority AXI arbiter
│   ├── gpu/                           # NEW in Phase 4: GPU-Lite RTL
│   │   ├── gpu_top.sv                 # GPU top (AXI4-Lite ctrl + AXI4 mem + IRQ)
│   │   ├── gpu_command_queue.sv       # Kernel descriptor queue (PC, grid, block, args)
│   │   ├── warp_scheduler.sv          # Round-robin scheduler (warp_id, PC, active_mask, ready)
│   │   ├── gpu_compute_unit.sv        # Vector ALU + register file + SIMT divergence stack
│   │   ├── vector_register_file.sv    # 32 regs × 8 threads per warp
│   │   ├── vector_alu.sv              # VADD/VSUB/VMUL/VAND/VOR/VSLL per lane
│   │   ├── gpu_memory_unit.sv         # Global load/store with AXI burst generation
│   │   ├── memory_coalescer.sv        # 8-lane requests → fewer AXI bursts
│   │   └── shared_memory.sv           # 16 KB scratchpad, 32 banks
│   ├── periph/                        # NEW in Phase 5: peripheral RTL
│   │   ├── uart_controller.sv
│   │   ├── spi_controller.sv
│   │   ├── timer.sv
│   │   ├── interrupt_controller.sv
│   │   └── dma_engine.sv              # Descriptor queue + AXI4 master + IRQ
│   └── soc/                           # NEW in Phase 5: SoC integration RTL
│       ├── soc_top.sv                 # Top-level: CPU + GPU + DMA + peripherals
│       ├── axi4_crossbar.sv           # N-master M-slave AXI4 data fabric
│       ├── axi_lite_interconnect.sv   # AXI-Lite control bus
│       ├── axi_lite_register_bank.sv  # GPU/DMA config registers
│       └── sram_controller.sv         # Behavioral AXI4-slave SRAM (no DRAM refresh)
├── tb/                       # Testbench
│   ├── models/               # Python reference models
│   │   ├── rv32i_model.py
│   │   ├── cache_model.py             # NEW in Phase 3: DirectMappedCache
│   │   ├── gpu_kernel_model.py
│   │   └── memory_model.py
│   ├── tests/                # Unit tests for models
│   │   ├── test_rv32i_model.py
│   │   └── test_gpu_model.py
│   └── cocotb/               # cocotb testbenches
│       ├── cpu/              # CPU tests (Phase 1+)
│       └── mem/              # Cache tests (Phase 3+)
├── sim/                      # Simulation scripts
├── pnr/                      # Physical design (NEW in Phase 1)
│   ├── Makefile              # Flow automation
│   ├── config/               # PDK configuration
│   ├── constraints/          # SDC + UPF files
│   ├── scripts/              # TCL flow scripts
│   ├── logs/                 # Flow logs (gitignored)
│   ├── reports/              # Reports (gitignored)
│   └── results/              # Netlist, DEF, GDS (gitignored)
└── CLAUDE.md                 # This file
```

## AI/Human Boundaries

### AI MAY assist with

- Python boilerplate (class structure, imports)
- Simple instruction implementations (after human verification)
- cocotb driver scaffolding
- Test case generation
- Documentation formatting

### Human MUST

- Write and approve all specifications
- Implement complex instructions (branches, loads, stores)
- Design control FSMs
- Define verification strategy
- Review all AI-generated code
- Make architectural decisions

See each phase in `docs/verification/VERIFICATION_PLAN.md` for detailed AI/Human responsibilities.

## Commit Message Convention

Use the format: `[Category] Brief description`

Categories:

- `[Fix]` - Bug fixes
- `[Feature]` - New features
- `[Code]` - Code changes/refactoring
- `[Env]` - Environment/build changes
- `[Doc]` - Documentation updates
- `[Test]` - Test additions/changes
- `[Spec]` - Specification updates

## Next Steps

See `docs/PHASE_STATUS.md` for current status and immediate next steps.

**Current priorities** (Phase 4 - GPU-Lite SIMT — not started):

**Phase 0 Complete** ✅:

- ✅ All 7 specifications approved (2026-01-18)
- ✅ Python reference models validated (66/66 tests passing)
- ✅ cocotb test infrastructure ready

**Phase 1 Complete** ✅ (2026-02-13):

- ✅ All 8 RTL modules implemented (~1,900 lines)
- ✅ All 9/9 verification exit criteria met
- ✅ ISA compliance: 37/37 instructions passing
- ✅ Random testing: 10,000 instructions, 0 failures
- ✅ Archived to `micro_p/` directory

**Phase 2 Complete** ✅ (2026-03-08):

- ✅ Architecture specification approved (2026-02-14)
- ✅ All 14 pipeline modules implemented
- ✅ Comprehensive verification: 111/111 tests passing
- ✅ Random regression: 50,000 instructions, 0 failures
- ✅ Backend: 75 MHz achieved on Sky130 130nm
- ✅ Constraints: `pnr/constraints/phase2_cpu.sdc`, `pnr/constraints/phase2_cpu.upf`

**Phase 3 Complete** ✅ (2026-05-21):

1. **RTL Implementation** ✅ (~1,424 lines)
   - ✅ `rtl/mem/rv32i_cache_pkg.sv` — cache parameters and types
   - ✅ `rtl/mem/rv32i_icache.sv` — I-cache (4 KB, direct-mapped, FENCE.I)
   - ✅ `rtl/mem/rv32i_dcache.sv` — D-cache (4 KB, write-back + write-allocate)
   - ✅ `rtl/mem/rv32i_cache_arbiter.sv` — D$ priority AXI arbiter
   - ✅ Modified pipeline stages: `rv32i_pipeline_if.sv`, `rv32i_pipeline_mem.sv`
   - ✅ Modified support: `rv32i_decode.sv` (FENCE.I), `rv32i_hazard_unit.sv` (stall rename)
   - ✅ Modified core: `rv32i_core.sv` (cache instantiation)

2. **Reference Model** ✅
   - ✅ `tb/models/cache_model.py` — `DirectMappedCache` class

3. **Verification** ✅
   - ✅ Unit tests: `tb/cocotb/mem/test_icache.py` (7/7), `test_dcache.py` (8/8)
   - ✅ Integration: `tb/cocotb/cpu/test_cache_integration.py` (5/5)
   - ✅ Full regression: 139/139 (119 Phase 2 + 20 Phase 3); 50,000+ random instructions, 0 failures

4. **Physical Design** ✅
   - ✅ ASAP7 sign-off: **1418 MHz / 27.27 mW / 3,844 µm²**, 0 DRC, 0 antenna (Run 43, 2026-05-20)
   - ✅ Sky130 ceiling: 75 MHz (PDK-limited; matches Phase 2)

**Phase 4 Tasks** (follows Phase 3 sign-off):

1. **RTL Implementation**
   - ⏸️ `rtl/gpu/gpu_top.sv` — top-level with AXI4-Lite control + AXI4 memory + IRQ
   - ⏸️ `rtl/gpu/gpu_command_queue.sv` — kernel descriptor: PC, grid size, block size, arg pointer
   - ⏸️ `rtl/gpu/warp_scheduler.sv` — round-robin; warp state: warp_id, PC, active_mask, ready
   - ⏸️ `rtl/gpu/gpu_compute_unit.sv` — vector ALU + register file + SIMT divergence stack
   - ⏸️ `rtl/gpu/vector_register_file.sv` — 32 regs × 8 threads per warp
   - ⏸️ `rtl/gpu/vector_alu.sv` — VADD, VSUB, VMUL, VAND, VOR, VSLL per lane
   - ⏸️ `rtl/gpu/gpu_memory_unit.sv` — global load/store with AXI burst generation
   - ⏸️ `rtl/gpu/memory_coalescer.sv` — coalesces 8-lane requests into fewer AXI bursts
   - ⏸️ `rtl/gpu/shared_memory.sv` — 16 KB scratchpad, 32 banks

2. **Verification**
   - ⏸️ Unit tests: `tb/cocotb/gpu/test_warp_scheduler.py`, `test_compute_unit.py`, `test_memory_unit.py`
   - ⏸️ Kernel tests: vector add, parallel reduction, divergence test
   - ⏸️ Phase 3 full regression (111+ tests must still pass)

3. **Physical Design**
   - ⏸️ GPU block synthesis + P&R + STA
   - ⏸️ `pnr/constraints/phase4_gpu.sdc`, `phase4_gpu.upf`

**Phase 5 Tasks** (follows Phase 4 sign-off):

1. **AXI4 Interconnect** (build first — prerequisite for integration)
   - ⏸️ `rtl/soc/axi4_crossbar.sv` — N-master M-slave data fabric
   - ⏸️ `rtl/soc/axi_lite_interconnect.sv` — control bus
   - ⏸️ `rtl/soc/axi_lite_register_bank.sv` — GPU + DMA config registers
   - ⏸️ Upgrade Phase 3 refill FSMs to AXI4 burst mode

2. **Peripherals + DMA**
   - ⏸️ `rtl/periph/dma_engine.sv`, `uart_controller.sv`, `spi_controller.sv`, `timer.sv`, `interrupt_controller.sv`

3. **SoC Integration**
   - ⏸️ `rtl/soc/sram_controller.sv` — behavioral AXI4-slave SRAM
   - ⏸️ `rtl/soc/soc_top.sv` — full SoC top-level
   - ⏸️ Performance counters added as CSR-mapped registers

4. **Verification**
   - ⏸️ CPU-GPU integration: kernel launch → interrupt → result read
   - ⏸️ Software coherency: CPU D-cache flush → GPU kernel → CPU D-cache invalidate
   - ⏸️ DMA transfer tests; full benchmark suite (CPU + GPU kernels)
   - ⏸️ L2 cache decision: add `rtl/mem/l2_cache.sv` only if L1 miss rates justify it

5. **Physical Design**
   - ⏸️ Full SoC synthesis + P&R + STA
   - ⏸️ `pnr/constraints/phase5_soc.sdc`, `phase5_soc.upf`
   - ⏸️ Power domain validation (PD_CPU, PD_GPU, PD_SRAM, PD_PERIPH)

**Phase 6+ Tasks** (follows Phase 5 sign-off):

1. **Additional Peripherals** (AXI4-Lite slaves on existing Phase 5 interconnect)
   - ⏸️ `rtl/periph/gpio_controller.sv` — pad ring, direction control, interrupt on edge
   - ⏸️ `rtl/periph/i2c_controller.sv` — multi-master I2C, SCL/SDA open-drain
   - ⏸️ `rtl/periph/pwm_controller.sv` — configurable counter + compare, N channels
   - ⏸️ `rtl/periph/watchdog_timer.sv` — AON-domain counter, system reset output
   - ⏸️ `rtl/periph/trng.sv` — ring-oscillator entropy source (Sky130 analog cells)
   - ⏸️ `rtl/periph/aes_sha_accel.sv` — AXI4-Lite slave (control/status, key/IV/digest registers) + AXI4 master/slave (bulk data DMA); AES-128 + SHA-256 pipeline

2. **NPU (Minimal INT8 Inference Engine)**
   - ⏸️ `rtl/npu/npu_top.sv` — AXI4 master (activations) + AXI4-Lite slave (config) + IRQ
   - ⏸️ `rtl/npu/mac_array.sv` — 4×4 INT8 systolic MAC array (16 MACs, 64 ops/cycle)
   - ⏸️ `rtl/npu/weight_buffer.sv` — 16 KB SRAM-backed weight store (DMA-loaded)
   - ⏸️ `rtl/npu/activation_unit.sv` — ReLU; LUT-based sigmoid/tanh optional
   - ⏸️ Phase 6 only if Phase 5 benchmarks reveal CPU/GPU bottleneck on ML workloads

3. **Tech Node Exploration** (independent of RTL — P&R only)
   - ⏸️ FreePDK45/NanGate45: run `make librelane-nangate45` (config already complete)
   - ✅ ASAP7: `pnr/asap7/` complete; Phase 2+3 RTL signed off at Run 43 (1418 MHz / 27.27 mW / 3 844 µm², 2026-05-20)

## Questions?

Refer to specifications in `docs/` - they are the source of truth.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
