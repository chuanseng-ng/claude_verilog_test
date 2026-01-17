# Project Roadmap

## Project Expectations

1. Create simple micro-processor with RV32I subset
2. Upgrade micro-processor to become pipelined CPU
3. Develop memory system & caches
4. Create a simple GPU compute engine
5. Integrate all IPs into SoC with some peripherals

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

**RTL (SystemVerilog)**

- AI SHOULD help with
  - ALU module
  - Register file
  - Instruction decoder
  - Immediate generator
  - Simple LSU FSM
  - Clean SV interfaces
- Human MUST
  - Approve decoder truth tables
  - Validate instruction semantics
  - Review state machine completeness

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

✅ Exit criteria

- Passes random tests
- Passes RISC-V ISA tests (subset)

### Phase 2 — Pipelined CPU (AI becomes assistive)

- Architecture
  - 5-stage pipeline
  - No speculation
  - Static hazard handling

**RTL**

- AI SHOULD
  - Generate pipeline registers
  - Forwarding mux logic
  - Boilerplate hazard detection
  - SVA assertions
- Human MUST
  - Define hazard rules
  - Control stall/flush priority
  - Ensure architectural state correctness

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

📉 AI contribution ~60%

✅ Exit criteria

- Zero false commits
- Pipeline invariants proven (simulation + assertions)

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

📉 AI contribution ~40%

✅ Exit criteria

- No deadlocks
- Correct under randomized latency

### Phase 4 — “GPU-lite” compute engine (research-level)

🚨 This is not a CPU extension.

**Scope (keep it sane)**

- Single compute unit
  - SIMD/SIMT lanes
  - No graphics
  - No preemption

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

📉 AI contribution ~30–40%

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

📈 AI contribution ~70%

✅ Exit criteria

- Boots software
- Passes long random regressions
