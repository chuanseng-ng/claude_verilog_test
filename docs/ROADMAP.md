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

- ✅ Passes random tests (10,000 instructions, 0 failures)
- ✅ Passes RISC-V ISA tests (37/37 instructions)
- ✅ All verification exit criteria met
- ✅ Archived to `micro_p/` directory
- ✅ Ready for Phase 2

### Phase 2 — Pipelined CPU 🔄 RTL COMPLETE (2026-02-16)

- Architecture
  - 5-stage pipeline (IF/ID/EX/MEM/WB)
  - In-order execution
  - Hazard detection + stalling + forwarding
  - **Interrupt support added** (M-mode: timer + external)
  - **CSR instructions** (CSRRW/S/C/I variants)
  - Same AXI4-Lite and APB3 interfaces as Phase 1
  - AXI arbiter for IF/MEM priority
  - Target: 200 MHz, 1 IPC

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
- ✅ Initial testing: 115/115 regression tests passing

**Verification** 🔄 IN PROGRESS

- 🔄 Pipeline hazard tests (RAW/WAR/WAW)
- 🔄 Interrupt and CSR tests
- 🔄 Debug interface tests (pipeline drain)
- 🔄 Random instruction regression (target: 50k+)
- 🔄 AXI arbiter protocol tests
- 🔄 Coverage collection
- 🔄 Performance validation (IPC, frequency)

**Physical Design & Power** ⏸️ READY TO RUN

- ✅ Phase 2 constraints ready (phase2_cpu.sdc, phase2_cpu.upf)
- ⏸️ Synthesis at 200 MHz target
- ⏸️ P&R with pipeline optimizations
- ⏸️ STA multi-corner analysis
- ⏸️ Power analysis with clock gating
- ⏸️ Gate-level simulation with SDF

📉 AI contribution ~60%

✅ Exit criteria (in progress)

- 🔄 Zero false commits (scoreboard validation)
- 🔄 Pipeline hazard tests passing
- 🔄 Interrupt tests passing
- 🔄 Coverage >95% (instruction, state, branch)
- 🔄 Performance: >0.9 IPC on typical code
- ⏸️ Timing closure at 200 MHz
- ⏸️ Power consumption within budget
- ⏸️ Gate-level simulation matches RTL

### Phase 3 — Memory system & caches (human-led)

- Architecture
  - I-cache + D-cache
  - Write-back, no coherence
  - AXI-like interface

**RTL**

- AI SHOULD
  - Generate cache FSMs
  - Write tag/data arrays
  - Draft refill logic
- Human MUST
  - Design:
    - Cache states
    - Miss handling
    - Fence semantics
  - Review every transition

**Verification**

- Python models
  - Cache reference model
  - Memory ordering checker
- AI SHOULD
  - Generate randomized cache stress tests
  - Build latency-injection models
- Human MUST
  - Debug livelock/deadlock
  - Validate ordering guarantees

**Physical Design & Power (OpenROAD back-end)**

- SRAM macro integration (tag/data arrays)
- Memory compiler interface
- Power domain partitioning (caches vs core)
- Cache power gating strategies
- UPF updates for cache retention modes
- Clock domain crossing (if async interfaces)
- Physical hierarchy (separate cache blocks)
- Area optimization for SRAM placement
- Timing constraints for cache access paths

📉 AI contribution ~40%

✅ Exit criteria

- No deadlocks
- Correct under randomized latency
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
