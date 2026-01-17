# Verification Plan

Phase-Aligned Verification Strategy with AI/Human Responsibilities

Document status: Active
Last updated: 2026-01-17

## Overview

This document defines the verification strategy for all project phases, detailing what to verify,
how to verify it, and clear AI vs Human responsibilities for verification tasks.

### Core Principles

1. **Python is the golden reference**: Reference models define correctness
2. **Scoreboards decide truth**: RTL behavior compared against reference models
3. **Randomized stress > Directed tests**: After smoke tests pass, emphasize random testing
4. **Verification precedes optimization**: Never optimize unverified RTL
5. **Specification-driven**: All verification derives from architectural specs

### Verification Stack

**Tools**:
- **cocotb**: Signal-level drivers, monitors, clocking, resets
- **pyuvm**: Structure, sequences, agents, scoreboards
- **Python reference models**: Golden behavioral models (see REFERENCE_MODEL_SPEC.md)
- **pytest**: Unit testing for reference models and testbench components

**Simulation**:
- **Verilator**: Fast, free, linting
- **Questa/Xcelium**: Full featured (if available)

## Phase 0 Verification

**Status**: Specification and model development (no RTL)

### Objectives

1. Validate that specifications are complete and unambiguous
2. Implement Python reference models
3. Develop testbench infrastructure
4. Create initial test sequences

### Deliverables

| Deliverable | Description | AI/Human Responsibility |
|:-----------:|:-----------:|:-----------------------:|
| CPU reference model | RV32IModel class implementing all 37 instructions | **Human writes**, AI assists with boilerplate |
| GPU reference model | GPUKernelModel class (skeleton only) | **Human designs**, AI assists |
| Memory model | MemoryModel class for sparse memory | AI may generate, **Human reviews** |
| cocotb infrastructure | Clock, reset, basic drivers | AI may generate, **Human reviews** |
| Model unit tests | pytest tests for reference models | **Human writes critical tests**, AI assists |

### AI Responsibilities (Phase 0)

AI MAY assist with:
- Generating Python class boilerplate
- Simple instruction implementations (ADD, SUB, AND, OR, etc.)
- Memory model read/write functions
- cocotb clock and reset utilities
- Test case scaffolding

AI MUST NOT:
- Decide instruction semantics (must follow spec exactly)
- Design verification architecture
- Define what "correct" means

### Human Responsibilities (Phase 0)

Human MUST:
- Write and verify all branch instruction implementations
- Write and verify all load/store instructions
- Implement sign extension correctly
- Design scoreboard comparison strategy
- Cross-verify reference model against RISC-V ISA simulator (spike/QEMU)
- Review all AI-generated code

### Exit Criteria (Phase 0)

- ✅ CPU reference model implements all 37 RV32I instructions
- ✅ Reference model passes 100+ unit tests
- ✅ Reference model cross-validated against spike (10k+ instructions)
- ✅ cocotb infrastructure can drive reset and clock
- ✅ Memory model tested with various access patterns
- ✅ All team members agree specifications are complete

### Test Metrics (Phase 0)

| Metric | Target |
|:------:|:------:|
| Reference model instruction coverage | 37/37 (100%) |
| Reference model unit test pass rate | 100% |
| Cross-validation vs spike agreement | 100% |

---

## Phase 1 Verification

**Status**: Single-cycle CPU with interfaces

### Objectives

1. Verify RV32I instruction correctness
2. Verify AXI4-Lite protocol compliance
3. Verify APB3 debug interface
4. Verify commit interface correctness
5. Prove RTL matches reference model

### Test Architecture

```
pyuvm Test
    └── pyuvm Environment
        ├── AXI4-Lite Agent (memory)
        │   ├── Driver (memory slave model)
        │   ├── Monitor (transaction logging)
        │   └── Sequencer (back-pressure randomization)
        ├── APB3 Agent (debug master)
        │   ├── Driver (debug commands)
        │   ├── Monitor (response checking)
        │   └── Sequencer (halt/resume/step sequences)
        ├── Commit Monitor
        │   └── Captures commit_valid, commit_pc, commit_insn
        └── Scoreboard
            ├── RV32IModel instance
            ├── Compare commits against model
            └── Flag mismatches
```

### Test Categories

#### 1. Smoke Tests (Directed)

**Purpose**: Verify basic functionality before random testing

| Test Name | Description | AI/Human |
|:---------:|:-----------:|:--------:|
| `test_reset` | Verify PC = 0x0000_0000, all regs = 0 | AI may write, **Human reviews** |
| `test_simple_add` | Execute ADD, verify result | AI may write, **Human reviews** |
| `test_branch_taken` | Execute BEQ with true condition | **Human writes** |
| `test_load_store` | LW then SW to same address | **Human writes** |
| `test_halt_resume` | Debug halt and resume sequence | **Human writes** |

**AI assistance**: AI may generate test structure, human must verify logic.

**Human responsibility**: Review and approve all smoke tests.

**Exit criteria**: All smoke tests pass.

#### 2. ISA Compliance Tests (Directed)

**Purpose**: Test every instruction in isolation

**Test generation**:
```python
# Example: Test all arithmetic instructions
@cocotb.test()
async def test_isa_arithmetic(dut):
    instructions = [
        ("ADD",  0x002081b3, x1=10, x2=20, expect_x3=30),
        ("SUB",  0x402081b3, x1=30, x2=10, expect_x3=20),
        # ... all 37 instructions
    ]
```

**AI may assist**: Generating instruction encodings and test loops

**Human must**: Verify expected values, edge cases (overflow, signed, etc.)

**Coverage target**: 37/37 instructions executed at least once

#### 3. Random Instruction Tests (Constrained Random)

**Purpose**: Stress test with random legal instruction sequences

**Strategy**:
```python
class RandomInstructionSequence(uvm_sequence):
    def body(self):
        for _ in range(10000):
            insn = self.generate_random_instruction()
            self.start_item(insn)
```

**Constraints**:
- Only generate legal RV32I instructions
- Ensure memory addresses are in valid range
- Avoid infinite loops (use instruction count limit)

**AI may**: Generate random instruction generator framework

**Human must**: Define constraints, verify randomization quality

**Coverage target**: 10,000+ random instructions, zero failures

#### 4. AXI4-Lite Protocol Tests

**Purpose**: Verify AXI4-Lite master compliance

| Test Name | Description | AI/Human |
|:---------:|:-----------:|:--------:|
| `test_axi_read_basic` | Simple read transaction | AI may write |
| `test_axi_write_basic` | Simple write transaction | AI may write |
| `test_axi_backpressure` | Randomize READY signals | **Human writes** |
| `test_axi_error_response` | SLVERR/DECERR handling | **Human writes** |

**Protocol checker**: Use cocotb AXI monitor to check protocol violations

**AI may**: Generate basic transaction tests

**Human must**: Test error cases, back-pressure, edge conditions

#### 5. Debug Interface Tests

**Purpose**: Verify APB3 debug functionality

| Test Name | Description | AI/Human |
|:---------:|:-----------:|:--------:|
| `test_debug_halt` | Halt CPU via DBG_CTRL | **Human writes** |
| `test_debug_resume` | Resume execution | **Human writes** |
| `test_debug_single_step` | Execute one instruction | **Human writes** |
| `test_debug_breakpoint` | Breakpoint triggers halt | **Human writes** |
| `test_debug_reg_read` | Read GPRs when halted | AI may write, **Human reviews** |
| `test_debug_reg_write` | Write GPRs when halted | **Human writes** |

**Human responsibility**: All debug tests due to complexity

### Scoreboard Implementation

```python
class CPUScoreboard(uvm_component):
    def __init__(self, name, parent):
        super().__init__(name, parent)
        self.model = RV32IModel()  # Reference model
        self.mismatches = 0

    def write_commit(self, txn):
        """Called when RTL commits an instruction"""
        # Step reference model with same instruction
        ref_result = self.model.step(txn.insn)

        # Compare PC
        if txn.pc != ref_result['pc']:
            self.log.error(f"PC mismatch: RTL={txn.pc:08x}, Model={ref_result['pc']:08x}")
            self.mismatches += 1

        # Compare register writes
        if ref_result['rd'] is not None:
            rtl_rd_val = self.get_rtl_register(ref_result['rd'])
            if rtl_rd_val != ref_result['rd_value']:
                self.log.error(f"Register x{ref_result['rd']} mismatch")
                self.mismatches += 1

        # Compare memory writes
        if ref_result['mem_write']:
            # Check memory write matches
            pass  # Implementation details

    def report_phase(self):
        if self.mismatches == 0:
            self.log.info("PASS: No mismatches detected")
        else:
            self.log.error(f"FAIL: {self.mismatches} mismatches")
```

**Human responsibility**: Design and implement scoreboard logic

**AI may assist**: Boilerplate pyuvm structure

### AI/Human Responsibilities (Phase 1)

#### AI MAY assist with:

- cocotb drivers for AXI4-Lite and APB3
- Simple directed test generation
- Random instruction generator framework
- pyuvm agent boilerplate
- Monitor transaction capture
- Coverage collection setup

#### Human MUST:

- Design scoreboard comparison algorithm
- Implement complex test scenarios (debug, errors, back-pressure)
- Verify all test results
- Analyze failures and waveforms
- Decide when verification is "complete"
- Write assertions for critical properties

### Assertions (SystemVerilog)

**Note**: SVA assertions in separate files, not in RTL

**Critical assertions**:

```systemverilog
// No double write-back in same cycle
assert property (@(posedge clk) disable iff (!rst_n)
    commit_valid |-> ##1 !commit_valid || (commit_pc != $past(commit_pc))
);

// x0 always zero
assert property (@(posedge clk) disable iff (!rst_n)
    regfile.regs[0] == 0
);

// AXI4-Lite protocol: valid must not deassert after assert until ready
assert property (@(posedge clk) disable iff (!rst_n)
    $rose(axi_arvalid) |-> axi_arvalid throughout axi_arready[->1]
);
```

**AI may**: Generate assertion templates

**Human must**: Define critical properties to assert

### Coverage

**Instruction coverage**:
- Track which instructions executed
- Target: 100% of 37 RV32I instructions

**State coverage**:
- CPU states visited (FETCH, DECODE, EXECUTE, etc.)
- Debug states (HALTED, RUNNING)

**Edge coverage**:
- Transitions between states
- Halt while in different CPU states

**Cross coverage**:
- Instruction × CPU state
- Memory access × alignment

**AI may**: Generate coverage bins

**Human must**: Define coverage goals and analyze coverage gaps

### Exit Criteria (Phase 1)

| Criterion | Target |
|:---------:|:------:|
| Instruction coverage | 37/37 (100%) |
| Smoke tests | 100% pass |
| Random instruction tests | 10,000+ instructions, 0 failures |
| AXI4-Lite protocol tests | 100% pass |
| Debug interface tests | 100% pass |
| Scoreboard mismatches | 0 |
| Known failing seeds | 0 |
| Code coverage | >95% (RTL lines) |
| State coverage | 100% (all states visited) |

### Debugging Strategy

When failures occur:

1. **Check scoreboard logs**: Identify first mismatch
2. **Dump waveforms**: Examine cycle-by-cycle behavior
3. **Compare with reference model**: Step through both RTL and model
4. **Simplify test case**: Minimize failing sequence
5. **Add targeted assertions**: Catch bug earlier

**AI may**: Help analyze logs, suggest debugging approaches

**Human must**: Root-cause failures, fix RTL or model

---

## Phase 2 Verification

**Status**: Pipelined CPU (5-stage)

### New Verification Challenges

- Hazard detection and forwarding
- Pipeline stalls and flushes
- Speculative execution (if added)
- Branch misprediction recovery

### Test Additions

| Test Category | Description | AI/Human |
|:-------------:|:-----------:|:--------:|
| Hazard tests | RAW, WAR, WAW dependencies | **Human designs**, AI generates variants |
| Pipeline stress | Back-to-back dependent instructions | AI may generate, **Human reviews** |
| Flush tests | Branch taken/not-taken sequences | **Human writes** |
| Forwarding tests | Data forwarding paths | **Human writes** |

### Assertions (Phase 2)

```systemverilog
// No architectural state change on flush
assert property (@(posedge clk) disable iff (!rst_n)
    flush |-> (regfile_state == $past(regfile_state))
);

// Forwarding correctness
assert property (@(posedge clk) disable iff (!rst_n)
    (ex_rs1 == mem_rd) && mem_reg_write |-> (ex_rs1_value == mem_alu_result)
);
```

**Human must**: Define all pipeline invariants

### Exit Criteria (Phase 2)

- All Phase 1 criteria still met
- Zero false commits (wrong register writes)
- Zero pipeline deadlocks
- Hazard scenarios: 1000+ tests, 0 failures

---

## Phase 3 Verification

**Status**: Caches added (I-cache, D-cache)

### New Verification Challenges

- Cache hit/miss behavior
- Cache refill logic
- Write-back correctness
- Memory ordering preservation

### Reference Model Enhancement

**Cache model**:
```python
class CacheModel:
    def read(self, addr):
        if addr in self.cache:
            return self.cache[addr]  # Hit
        else:
            data = self.memory.read(addr)
            self.cache[addr] = data  # Refill
            return data
```

**Human must**: Implement cache model matching RTL behavior

### Test Additions

| Test Category | Description | AI/Human |
|:-------------:|:-----------:|:--------:|
| Cache hit tests | Repeated access to same address | AI may generate |
| Cache miss tests | Access to uncached addresses | AI may generate |
| Thrashing tests | Access pattern causing evictions | **Human designs** |
| Write-back tests | Verify dirty line write-back | **Human writes** |

### Exit Criteria (Phase 3)

- All Phase 2 criteria still met
- No cache coherence violations (scoreboard verified)
- No lost writes (write-back verified)
- 100k+ cache stress test cycles, 0 failures

---

## Phase 4 Verification

**Status**: GPU added

### GPU-Specific Verification

**Reference model**: `GPUKernelModel` (see REFERENCE_MODEL_SPEC.md)

### Test Categories

| Test Category | Description | AI/Human |
|:-------------:|:-----------:|:--------:|
| Vector kernels | Simple SIMT kernels (vec add, scalar mul) | AI may write, **Human reviews** |
| Divergence tests | if/else with different paths | **Human writes** |
| Memory coalescing | Verify coalesced vs serialized access | **Human writes** |
| Grid/block sweep | Various grid/block dimensions | AI may generate, **Human reviews** |

### Scoreboard

```python
class GPUScoreboard(uvm_component):
    def __init__(self, name, parent):
        super().__init__(name, parent)
        self.model = GPUKernelModel(warp_size=8)

    def write_kernel_done(self, txn):
        # Compare RTL memory output with model
        model_result = self.model.execute_kernel()

        for addr in model_result['memory']:
            rtl_val = self.read_rtl_memory(addr)
            model_val = model_result['memory'][addr]
            if rtl_val != model_val:
                self.log.error(f"Memory mismatch at 0x{addr:08x}")
```

**Human must**: Implement GPU scoreboard and divergence verification

### Exit Criteria (Phase 4)

- All directed GPU kernels pass
- Divergence tests pass (mask correctness verified)
- No GPU deadlocks in 100k+ cycle runs
- CPU-GPU integration tests pass

---

## Phase 5 Verification

**Status**: SoC integration

### System-Level Verification

- Boot sequence
- Peripheral access (UART, SPI, Timer)
- Interrupt handling (requires Phase 2+ CPU with interrupts)
- DMA transfers

### Test Additions

| Test Category | Description | AI/Human |
|:-------------:|:-----------:|:--------:|
| Boot tests | Verify boot from ROM | **Human writes** |
| Firmware tests | Run simple firmware | **Human provides firmware** |
| Peripheral tests | UART TX/RX, SPI transfer | AI may write, **Human reviews** |
| Stress tests | Long random regressions | AI may generate, **Human reviews** |

### Exit Criteria (Phase 5)

- Boots firmware reliably (100/100 attempts)
- Sustains 1M+ cycle random tests, 0 failures
- All peripherals functional
- System-level assertions pass

---

## Regression Testing

### Continuous Integration

**On every commit**:
- Run smoke tests (< 1 minute)
- Run ISA tests (< 5 minutes)
- Check for new lint warnings

**Nightly**:
- Run full random regression (10k+ instructions)
- Run cache stress tests
- Generate coverage reports

**Weekly**:
- Run extended random tests (100k+ instructions)
- Cross-validate reference model vs spike

### Seed Management

- Log random seeds for reproducibility
- Archive failing seeds
- Regression suite includes all previously failing seeds

---

## Tools and Infrastructure

### cocotb Setup

```bash
# Install cocotb
pip install cocotb cocotb-bus pytest

# Run simulation
make -C sim sim
make -C sim test TEST=test_simple_add
```

### Waveform Viewing

```bash
# Generate waveforms
make -C sim waves

# View with GTKWave
gtkwave sim/dump.vcd
```

### Coverage Collection

```bash
# Run with coverage
make -C sim coverage

# View coverage report
firefox sim/coverage/index.html
```

---

## Summary: AI vs Human Responsibilities

### AI Responsibilities (Across All Phases)

AI MAY assist with:
- ✅ cocotb driver boilerplate
- ✅ Simple directed test generation
- ✅ Random instruction generator frameworks
- ✅ pyuvm agent/monitor scaffolding
- ✅ Coverage bin generation
- ✅ Waveform analysis suggestions
- ✅ Log parsing and pattern detection

### Human Responsibilities (Across All Phases)

Human MUST:
- ❗ Design verification architecture
- ❗ Implement reference models
- ❗ Define "correctness" (scoreboard logic)
- ❗ Write complex tests (debug, hazards, divergence, caches)
- ❗ Analyze failures and debug
- ❗ Define coverage goals
- ❗ Decide when verification is complete
- ❗ Review all AI-generated code
- ❗ Define critical assertions
- ❗ Cross-validate reference models

---

## References

- PHASE0_ARCHITECTURE_SPEC.md: CPU architectural requirements
- PHASE1_ARCHITECTURE_SPEC.md: CPU implementation details
- PHASE4_GPU_ARCHITECTURE_SPEC.md: GPU architecture
- REFERENCE_MODEL_SPEC.md: Python reference model API
- MEMORY_MAP.md: Address space and register definitions
- ROADMAP.md: Project phase plan
