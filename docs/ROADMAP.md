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

### Phase 0 — Foundations (non-negotiable)

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

✅ Exit criteria

- Written ISA + microarchitecture spec (10–15 pages max)
  - Refer to PHASE0_ARCHITECTURE_SPEC.md
- No RTL yet

### Phase 1 — Minimal RV32I core (AI sweet spot)

- Architecture
  - Single-issue
  - In-order
  - No pipeline (or 2-stage max)
  - Blocking loads/stores
  - **No interrupts** (deferred to Phase 2+)
  - AXI4-Lite master (unified instruction/data bus)
  - APB3 slave (debug interface with halt/resume/step/breakpoints)

**RTL (SystemVerilog)**

- AI SHOULD help with
  - ALU module
  - Register file
  - Instruction decoder
  - Immediate generator
  - Simple LSU FSM
  - Clean SV interfaces
  - AXI4-Lite master boilerplate
  - APB3 slave register interface
- Human MUST
  - Approve decoder truth tables
  - Validate instruction semantics
  - Review state machine completeness
  - Design debug halt/resume logic
  - Approve AXI transaction ordering
  - Verify APB3 protocol compliance

**Verification (Python-first)**

- cocotb
  - Clock/reset drivers
  - Instruction memory model
  - Data memory model
- pyuvm
  - Sequences:
  - Directed instruction tests
  - Random legal instruction streams
- Scoreboard:
  - Compare RTL vs Python reference

- AI SHOULD
  - Write cocotb drivers/monitors
  - Write pyuvm sequences
  - Auto-generate random instruction generators
- Human MUST
  - Write golden ISA model in Python
  - Validate corner cases (sign-ext, overflow, misaligned access)

**Physical Design & Power (OpenROAD back-end)**

- Synthesis
  - Synthesize RTL to gate-level netlist
  - Target technology: Sky130 or ASAP7
  - Area and timing reports
- Floorplan & Place & Route
  - Automated P&R using OpenROAD
  - Power grid generation
  - Clock tree synthesis
  - Global and detailed routing
- Power-aware simulation
  - UPF (Unified Power Format) for power intent
  - Define power domains (CPU core, debug interface)
  - Power state tables and isolation strategies
  - Gate-level simulation with power-aware testbenches
- Timing verification
  - SDC (Synopsys Design Constraints) for timing constraints
  - Clock definitions (period, uncertainty, latency)
  - Input/output delays
  - False path and multicycle path exceptions
  - Static timing analysis (STA) with OpenSTA

- AI SHOULD
  - Generate initial UPF templates
  - Create basic SDC constraint files
  - Setup OpenROAD flow scripts
  - Generate power domain declarations
- Human MUST
  - Define power architecture and domains
  - Approve clock constraints and timing budgets
  - Review power state tables
  - Validate timing closure strategies
  - Approve final physical design

✅ Exit criteria

- Passes random tests
- Passes RISC-V ISA tests (subset)
- **Synthesis completes with no critical warnings**
- **Place & route achieves timing closure**
- **Gate-level simulation matches RTL behavior**
- **Power-aware simulation shows correct isolation**

### Phase 2 — Pipelined CPU (AI becomes assistive)

- Architecture
  - 5-stage pipeline
  - No speculation
  - Static hazard handling
  - **Interrupt support added** (timer + external interrupts)
  - Same AXI4-Lite and APB3 interfaces as Phase 1
  - Additional interrupt input signals

**RTL**

- AI SHOULD
  - Generate pipeline registers
  - Forwarding mux logic
  - Boilerplate hazard detection
  - SVA assertions
  - Interrupt input signal routing
- Human MUST
  - Define hazard rules
  - Control stall/flush priority
  - Ensure architectural state correctness
  - **Design interrupt handling logic**
  - **Define interrupt priority and masking**
  - Verify interrupt latency and precision

**Verification**

- New test focus
  - RAW/WAR/WAW hazards
  - Load-use stalls
  - Flush on branch
- AI SHOULD
  - Generate stress tests
  - Add pipeline assertions
  - Write coverage collectors
- Human MUST
  - Analyze waveform failures
  - Confirm pipeline invariants

**Physical Design & Power (OpenROAD back-end)**

- Incremental synthesis with pipeline stages
- UPF updates for pipeline power domains
- Clock gating opportunities
- Critical path analysis and optimization
- Multi-cycle path constraints for slow paths
- Setup/hold time validation
- Power analysis (dynamic + leakage)
- Gate-level simulation with back-annotated delays (SDF)

📉 AI contribution ~60%

✅ Exit criteria

- Zero false commits
- Pipeline invariants proven (simulation + assertions)
- **Timing closure at target frequency**
- **Power consumption within budget**
- **Gate-level simulation matches RTL**

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
