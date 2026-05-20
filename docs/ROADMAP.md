# Project Roadmap

## Project Expectations

1. Create simple micro-processor with RV32I subset
2. Upgrade micro-processor to become pipelined CPU
3. Develop memory system & caches
4. Create a simple GPU compute engine
5. Integrate all IPs into SoC with some peripherals

## OpenROAD Back-End Integration Strategy

Starting from Phase 1, **every IP block** will go through the complete OpenROAD physical design flow to ensure silicon-readiness. This approach provides:

1. **Early timing validation**: Identify critical paths before tape-out
2. **Power budgeting**: Understand power consumption per block
3. **Area estimation**: Guide floorplanning decisions
4. **Reality check**: Ensure RTL is physically implementable

### Back-End Flow Overview

For each new IP (CPU core, cache, GPU, peripherals):

```text
RTL Design
    ↓
Synthesis (Yosys/OpenROAD)
    ↓
Floorplan (OpenROAD)
    ↓
Placement (OpenROAD)
    ↓
Clock Tree Synthesis (TritonCTS)
    ↓
Routing (TritonRoute)
    ↓
Parasitic Extraction (OpenRCX)
    ↓
Static Timing Analysis (OpenSTA)
    ↓
Power Analysis (OpenROAD)
    ↓
Physical Verification (KLayout/Magic)
    ↓
Gate-Level Simulation (Verilator + UPF)
```

### Power-Aware Verification

**UPF (Unified Power Format)** is used to specify power intent:

- Power domains and supply networks
- Isolation strategies for domain boundaries
- Retention strategies for state preservation
- Power state tables (PST) for mode transitions

**Power-aware simulation** validates:

- Isolation cell functionality
- Level shifter correctness
- Retention register behavior
- Power sequencing

### Timing Verification

**SDC (Synopsys Design Constraints)** specifies timing requirements:

- Clock definitions (period, uncertainty, jitter)
- Input/output delays relative to clock
- False paths (paths that don't need timing checks)
- Multi-cycle paths (paths with >1 cycle budget)
- Clock domain crossing constraints

**Static Timing Analysis (STA)** verifies:

- Setup timing (data arrives before clock edge)
- Hold timing (data stable after clock edge)
- Clock skew and latency
- Timing across all process corners (fast/slow)

### Target Technologies

- **Sky130**: Open-source 130nm PDK (SkyWater + Google)
- **ASAP7**: Predictive 7nm FinFET PDK (Arizona State University)

Both support the OpenROAD flow and are suitable for academic/research projects.

## Phase

### Phase 0 — Foundations ✅ COMPLETE (2026-01-18)

- Goals
  - Define what correctness means
  - Prevent architecture drift later
- Human-led (must)
  - Define RV32I subset (no CSR, no MMU, no compressed)
  - Define:
    - Reset behavior
    - Trap behavior
    - Memory ordering rules
  - Decide pipeline strategy (single-cycle vs multi-cycle)
- AI-assisted
  - Generate:
    - Project skeleton
    - Lint rules
    - Basic SV coding guidelines
  - Draft documentation templates

✅ Exit criteria MET

- ✅ Written ISA + microarchitecture spec (PHASE0_ARCHITECTURE_SPEC.md)
- ✅ No RTL (as planned)
- ✅ All 7 specifications approved
- ✅ Python reference models validated (66/66 tests passing)
- ✅ cocotb test infrastructure ready

### Phase 1 — Minimal RV32I core ✅ COMPLETE (2026-02-13)

- Architecture
  - Single-issue
  - In-order
  - Single-cycle with AXI stalls
  - Blocking loads/stores
  - **No interrupts** (deferred to Phase 2)
  - AXI4-Lite master (unified instruction/data bus)
  - APB3 slave (debug interface with halt/resume/step/breakpoints)

**RTL (SystemVerilog)** ✅ ALL COMPLETE

- ✅ 8 modules implemented (~1,900 lines)
  - ✅ ALU module (rv32i_alu.sv)
  - ✅ Register file (rv32i_regfile.sv)
  - ✅ Instruction decoder (rv32i_decode.sv)
  - ✅ Immediate generator (rv32i_imm_gen.sv)
  - ✅ Branch comparator (rv32i_branch_comp.sv)
  - ✅ Control FSM (rv32i_control.sv)
  - ✅ Core wrapper (rv32i_core.sv)
  - ✅ CPU top-level (rv32i_cpu_top.sv)

**Verification (Python-first)** ✅ ALL COMPLETE

- ✅ cocotb test infrastructure
  - ✅ AXI4-Lite memory models
  - ✅ APB3 debug interface drivers
  - ✅ Scoreboard validation
- ✅ Comprehensive test suites
  - ✅ 6/6 smoke tests passing
  - ✅ 37/37 ISA compliance tests
  - ✅ 10,000 random instructions (0 failures)
  - ✅ 11/11 AXI protocol tests
  - ✅ 6/6 debug interface tests
- ✅ Coverage
  - ✅ 37/37 instructions (100%)
  - ✅ 8/8 FSM states (100%)

**Physical Design & Power (Optional)**

- OpenROAD flow scripts ready
- Phase 1 constraints available (phase1_cpu.sdc, phase1_cpu.upf)
- Can be run for Phase 1 baseline metrics

✅ Exit criteria MET (9/9)

- ✅ Smoke tests passing (6/6 with scoreboard)
- ✅ Scoreboard mismatches: 0
- ✅ Instruction coverage: 37/37 RV32I instructions (100%)
- ✅ Random instruction tests: 10,000 instructions, 0 failures
- ✅ AXI protocol tests: 11/11 passing
- ✅ Debug interface tests: 6/6 passing (single-step, BP0, BP1, GPR/PC write)
- ✅ Code coverage: >95% (Verilator annotated reports)
- ✅ State coverage: 8/8 FSM states (100%)
- ✅ Failing random seeds: 0 (100/100 seeds pass)
- ✅ Archived to `micro_p/` directory

### Phase 2 — Pipelined CPU ✅ COMPLETE (2026-03-08)

- Architecture
  - 5-stage pipeline (IF/ID/EX/MEM/WB)
  - In-order execution
  - Hazard detection + stalling + forwarding
  - **Interrupt support added** (M-mode: timer + external)
  - **CSR instructions** (CSRRW/S/C/I variants)
  - Same AXI4-Lite and APB3 interfaces as Phase 1
  - AXI arbiter for IF/MEM priority
  - Achieved: 75 MHz on Sky130 130nm (200 MHz target not met due to PDK limitations)

**RTL** ✅ ALL COMPLETE

- ✅ 14 modules implemented (~3,000 lines)
  - ✅ 5 pipeline stage modules (IF, ID, EX, MEM, WB)
  - ✅ Pipeline package (rv32i_pipeline_pkg.sv)
  - ✅ Hazard detection unit (rv32i_hazard_unit.sv)
  - ✅ Forwarding unit (rv32i_forwarding_unit.sv)
  - ✅ CSR file (rv32i_csr_file.sv)
  - ✅ Interrupt controller (rv32i_interrupt_ctrl.sv)
  - ✅ AXI arbiter (rv32i_axi_arbiter.sv)
  - ✅ Updated decoder for CSR instructions
  - ✅ Reused: ALU, regfile, imm_gen, branch_comp

**Verification** ✅ ALL COMPLETE

- ✅ Pipeline hazard tests — 16/16 (RAW/WAR/WAW, forwarding)
- ✅ Interrupt and CSR tests — 12/12
- ✅ Debug interface tests — 6/6 (pipeline drain)
- ✅ Random instruction regression — 50,000 instructions, 0 failures
- ✅ AXI arbiter protocol tests — 12/12
- ✅ Fault injection tests — 7/7
- ✅ Total: 111/111 tests passing

**Physical Design & Power** ✅ COMPLETE

- ✅ Phase 2 constraints: `pnr/constraints/phase2_cpu.sdc`, `pnr/constraints/phase2_cpu.upf`
- ✅ Backend flow executed on Sky130 130nm
- ✅ **75 MHz achieved** (200 MHz target not met — Sky130 PDK limitation)

📉 AI contribution ~60%

✅ Exit criteria MET

- ✅ Zero false commits (scoreboard validation, 50k random instructions)
- ✅ Pipeline hazard tests passing (16/16)
- ✅ Interrupt tests passing (12/12)
- ✅ All 111/111 Phase 2 tests passing
- ✅ Timing closure at 75 MHz on Sky130

### Phase 3 — Memory system & caches 🔄 IN PROGRESS (started 2026-03-08)

- Architecture
  - I-Cache: 4 KB direct-mapped, 16-byte lines, 256 sets, read-only, FENCE.I invalidation
  - D-Cache: 4 KB direct-mapped, 16-byte lines, 256 sets, write-back + write-allocate
  - External interface: AXI4-Lite (4 separate transactions per refill — no burst)
  - Cache arbiter: D-cache priority over I-cache (replaces Phase 2 AXI arbiter)
  - Target: 75 MHz on Sky130 (matches Phase 2 achieved frequency)
  - Architecture spec: `docs/design/PHASE3_ARCHITECTURE_SPEC.md` — APPROVED (2026-03-08)

**RTL** 🔄 IN PROGRESS

- 🔄 New modules in `rtl/mem/`:
  - 🔄 `rv32i_cache_pkg.sv` — parameters, types (4 KB, 16-byte lines, direct-mapped)
  - 🔄 `rv32i_icache.sv` — I-cache with IDLE/REFILL FSM, FENCE.I
  - 🔄 `rv32i_dcache.sv` — D-cache with IDLE/WRITEBACK/REFILL FSM
  - 🔄 `rv32i_cache_arbiter.sv` — D$ priority AXI arbiter
- 🔄 Modified CPU modules:
  - 🔄 `rv32i_decode.sv` — FENCE.I decode (opcode=0x0F, funct3=001)
  - 🔄 `rv32i_pipeline_pkg.sv` — `fence_i` field added to `id_ex_reg_t`
  - 🔄 `rv32i_pipeline_if.sv` — cache interface (replaces AXI state machine)
  - 🔄 `rv32i_pipeline_mem.sv` — cache interface + FENCE.I (replaces AXI state machine)
  - 🔄 `rv32i_hazard_unit.sv` — rename stall signals (`if_cache_stall`, `mem_cache_stall`)
  - 🔄 `rv32i_core.sv` — cache + arbiter integration
- AI SHOULD
  - Generate cache FSMs per Section 3 of spec
  - Write tag/data array logic
  - Draft refill and writeback sequences
- Human MUST
  - Review all FSM transitions
  - Validate deadlock-freedom
  - Approve FENCE.I semantics implementation

**Verification** ⏸️ PENDING RTL

- Python cache reference model (`tb/models/cache_model.py`)
- Unit tests: `tb/cocotb/mem/test_icache.py`, `tb/cocotb/mem/test_dcache.py`
- Integration: `tb/cocotb/cpu/test_cache_integration.py`
- Phase 2 regression (all 111 tests must pass; FENCE.I now valid)
- Random regression: 50,000+ instructions with caches enabled, 0 failures
- AI SHOULD
  - Generate randomized cache stress tests
  - Build latency-injection models (randomize arready/rvalid)
- Human MUST
  - Debug livelock/deadlock scenarios
  - Validate FENCE.I ordering guarantees

**Physical Design & Power (OpenROAD back-end)** ⏸️ PENDING RTL

- SRAM macro integration (tag/data arrays)
- Power domain partitioning (caches vs core)
- Cache power gating strategies
- UPF updates for cache retention modes: `pnr/constraints/phase3_cache.upf`
- Timing constraints: `pnr/constraints/phase3_cache.sdc` (75 MHz, relaxed from Phase 2)
- Area: ~200k µm² on Sky130 (SRAM arrays dominate)

📉 AI contribution ~40%

✅ Exit criteria

- No deadlocks in cache FSMs
- Correct behavior under randomized memory latency
- **SRAM timing models integrated**
- **Cache power modes functional**
- **Physical layout achieves density targets**

### Phase 4 — "GPU-lite" compute engine (research-level)

🚨 This is not a CPU extension.

**Prerequisites**: Phase 3 complete (pipelined CPU with caches and interrupts)

**Scope (keep it sane)**

- Single compute unit
  - SIMD/SIMT lanes
  - No graphics
  - No preemption
  - **GPU interrupt output** to notify CPU of kernel completion (requires Phase 2+ CPU)

**RTL**

- AI SHOULD
  - Vector ALU blocks
  - Lane control logic
  - Simple warp scheduler templates
- Human MUST
  - Define execution model (SIMD vs SIMT)
  - Handle divergence
  - Define memory coalescing rules

**Verification**

- Python kernel model
  - Vector reference execution
  - Divergence checker
- AI SHOULD
  - Generate kernel tests
  - Build comparison harness
- Human MUST
  - Debug race conditions
  - Validate numerical correctness

**Physical Design & Power (OpenROAD back-end)**

- GPU compute unit as separate power domain
- UPF for GPU power gating (idle power savings)
- Vector ALU datapath optimization
- Register file (8-lane SIMT) physical design
- Warp scheduler timing constraints
- Power analysis for compute kernels
- Dynamic voltage/frequency scaling (DVFS) infrastructure
- Thermal analysis for sustained compute workloads
- GPU-CPU interface timing constraints

📉 AI contribution ~30–40%

✅ Exit criteria (updated)

- **GPU power domain functional**
- **Timing closure for compute datapath**
- **Power consumption validated per warp**

### Phase 5 — SoC integration (AI shines again)

- Components
  - CPU + GPU-lite
  - Interconnect
  - DMA
  - UART / SPI / Timer
  - Boot ROM

**RTL**

- AI SHOULD
  - Address maps
  - Interconnect glue
  - Peripheral controllers
- Human MUST
  - Define memory map
  - Decide arbitration rules
  - Own integration decisions

**Verification**

- cocotb system tests
  - Boot tests
  - Firmware execution
  - Peripheral stress tests
- AI SHOULD
  - Write firmware tests
  - Automate regressions
  - Generate fault injection

**Physical Design & Power (OpenROAD back-end - Full SoC)**

- Top-level SoC floorplan
- Multiple power domains (CPU, GPU, peripherals, always-on)
- UPF for system-level power management
  - Domain isolation cells
  - Level shifters for voltage domains
  - Retention strategies for low-power modes
- Hierarchical P&R (block-level then top-level)
- Clock distribution network (multiple clock domains)
- Power delivery network (PDN) analysis
- IR drop analysis and mitigation
- Electromigration (EM) analysis
- Sign-off timing analysis (multi-corner, multi-mode)
- Power estimation for system workloads
- Tape-out quality checks (DRC, LVS, antenna)

📈 AI contribution ~70%

✅ Exit criteria

- Boots software
- Passes long random regressions
- **Full SoC timing closure (all corners)**
- **Power delivery verified (IR drop < 5%)**
- **All power modes functional (active, idle, sleep)**
- **DRC/LVS clean**
- **Tape-out ready (if target technology selected)**

### Phase 6+ — IP Expansion & Technology Node Exploration (Planned)

**Prerequisites**: Phase 5 complete (full SoC validated)

#### 6a. Additional Peripherals (AXI4-Lite slaves on Phase 5 interconnect)

| IP | RTL file | Sky130 | FreePDK45 | ASAP7 |
|----|----------|--------|-----------|-------|
| GPIO controller | `rtl/periph/gpio_controller.sv` | ✅ 75 MHz | ✅ 400 MHz | ✅ 1 GHz |
| I2C controller | `rtl/periph/i2c_controller.sv` | ✅ 75 MHz | ✅ 400 MHz | ✅ 1 GHz |
| PWM controller | `rtl/periph/pwm_controller.sv` | ✅ 75 MHz | ✅ 400 MHz | ✅ 1 GHz |
| Watchdog timer | `rtl/periph/watchdog_timer.sv` | ✅ 75 MHz | ✅ 400 MHz | ✅ 1 GHz |
| TRNG | `rtl/periph/trng.sv` | ✅ Sky130 analog only | ❌ Not portable | ❌ Not portable |

Note: TRNG uses Sky130 ring-oscillator analog cells — **Sky130-exclusive** for tapeout.

#### 6b. AES-128 + SHA-256 Accelerator

- AXI4-Lite slave (control/status, key/IV/digest registers)
- AXI4 master/slave for bulk DMA
- AES-128 round function: ~6 LUT levels → fits 75 MHz on Sky130

| Node | AES throughput | Notes |
|------|---------------|-------|
| Sky130 (75 MHz) | ~75 MB/s | 100 cycles/block, tape-out viable |
| FreePDK45 (400 MHz) | ~400 MB/s | Same pipeline, 5× faster |
| ASAP7 (1 GHz) | ~1 GB/s | High-throughput secure element |

#### 6c. NPU — Minimal INT8 Inference Engine

- 4×4 INT8 systolic MAC array (16 MACs, 64 ops/cycle)
- 16 KB weight SRAM (one OpenRAM-compiled macro on FreePDK45/ASAP7; 8× stacked Sky130 macros)
- Target: keyword spotting / gesture detection class workloads

| Node | NPU clock | Peak throughput | INT4/sparsity |
|------|-----------|-----------------|---------------|
| Sky130 (50–60 MHz) | 50–60 MHz | 3.2–3.8 GOPS | ❌ Too slow |
| FreePDK45 (300–400 MHz) | 300–400 MHz | ~20 GOPS | ✅ Feasible |
| ASAP7 (800 MHz–1 GHz) | 800 MHz+ | ~50 GOPS | ✅ Preferred |

INT8 MAC critical path: ~10–13 logic levels. Full NPU (INT4/tiling/sparsity) requires FreePDK45 or ASAP7.

#### Technology Node Cross-Comparison (PD Results + Estimates)

| Phase | Sky130 (130nm) | FreePDK45 (45nm) | ASAP7 (7nm) |
|-------|---------------|------------------|-------------|
| Ph2 CPU | 75 MHz ✅ | 400 MHz ✅ (run 2026-03-23) | 1 GHz (planned) |
| Ph3 CPU+Cache | 75 MHz ✅ | **400 MHz ✅ WNS=0** (run 2026-03-23) | 500 MHz–1 GHz (planned) |
| Ph4 GPU-lite | 50–75 MHz (est.) | 300 MHz (est.) | 500 MHz (est.) |
| Ph5 SoC | 50–75 MHz (est.) | 250 MHz (est.) | 400 MHz (est.) |
| Ph6+ peripherals | 75 MHz | 400 MHz | 1 GHz |
| Ph6+ AES/SHA-256 | 75 MHz | 400 MHz | 1 GHz |
| Ph6+ NPU (min.) | 50 MHz | 300 MHz | 800 MHz |
| Ph6+ NPU (full) | ❌ | 300 MHz | 800 MHz |

**FreePDK45 Phase 3 PD results (run 2026-03-23)**:
- WNS = 0 ns, TNS = 0 ns @ 400 MHz (timing closed)
- Die: 760 × 480 µm = 364,800 µm² (15.8× smaller than Sky130)
- Power: 22.59 mW total (vs 59.86 mW Sky130 — 62% lower despite 5.3× faster clock)
- Cells: 26,038 standard cells, SRAM macros: 164,286 µm²
- PDN: SRAM macros not connected to grid (PDN_CONNECT_MACROS_TO_GRID=false) — known limitation for predictive PDK

**ASAP7 sign-off** ✅ (Run 43, 2026-05-20): 1418 MHz / 27.27 mW / 3 844 µm² stdcell, 0 DRC / 0 antenna / 0 setup-hold violations. RVT TT @ 0.7 V / 25 °C. SRAM via FF-array stub (`sram_1rw_256x32_asap7_stub.v` + Liberty/LEF). Config at `pnr/asap7/`. Full campaign history: `docs/ASAP7_RUN_HISTORY.md`.
