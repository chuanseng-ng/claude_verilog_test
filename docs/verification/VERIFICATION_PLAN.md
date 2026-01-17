# Verification Plan

## Objectives

### Primary goals

1. Prove functional correctness of
   - RV32I CPU core
   - GPU compute engine
   - SoC-level integration
2. Detect
   - ISA violations
   - Ordering bugs
   - Deadlocks/livelocks
   - Incorrect corner-case behavior
3. Enable incremental verification as features are added

### Key principles

- Python is the golden reference
- Scoreboards decide truth
- Randomized stress > Directed tests
- Verification precedes optimization

## Verification Stack

Tools

- cocotb — signal-level drivers, monitors, clocking
- py-uvm — structure, sequences, scoreboards
- Python reference models (ISA, memory, GPU kernel)

Simulation targets

- RTL simulators (Questa/Verilator/Xcelium)
- Both cycle-accurate and timing-abstract modes where applicable

## Verification Architecture Overview

### Testbench layering

```text
+------------------------------------------------+
|                py-uvm Tests                    |
+--------------------+---------------------------+
|     Sequences      |        Scoreboards        |
+--------------------+---------------------------+
|   Agents (drivers / monitors / analysis ports) |
+------------------------------------------------+
|              cocotb infrastructure             |
+------------------------------------------------+
|               SystemVerilog DUT                |
+------------------------------------------------+
```

#### Responsibility split

| Layer            | Responsibility                      |
| :--------------: | :---------------------------------: |
| cocotb           | Clock, reset, pin-level interaction |
| py-uvm agents    | Protocol correctness                |
| Sequences        | Stimulus generation                 |
| Scoreboards      | Functional correctness              |
| Reference models | Golden behavior                     |

## py-uvm Verification Architecture

### py-uvm testbench layering

```text
pyuvm/
 ├── env.py
 ├── agents/
 │    ├── imem_agent.py
 │    ├── dmem_agent.py
 │    ├── cfg_agent.py
 ├── sequences/
 │    ├── riscv_random_seq.py
 │    ├── gpu_kernel_seq.py
 ├── scoreboard/
 │    ├── cpu_scoreboard.py
 │    ├── gpu_scoreboard.py
 ├── tests/
 │    ├── test_cpu_smoke.py
 │    ├── test_cpu_random.py
 │    ├── test_gpu_basic.py
```

### Environment (env.py)

```python
from pyuvm import *
from agents.imem_agent import ImemAgent
from agents.dmem_agent import DmemAgent
from scoreboard.cpu_scoreboard import CpuScoreboard

class CpuEnv(uvm_env):
    def build_phase(self):
        self.imem = ImemAgent("imem", self)
        self.dmem = DmemAgent("dmem", self)
        self.scoreboard = CpuScoreboard("scoreboard", self)

    def connect_phase(self):
        self.imem.ap.connect(self.scoreboard.imem_export)
        self.dmem.ap.connect(self.scoreboard.dmem_export)
```

**AI SHOULD**

- Generate agents
- Generate monitors
- Boilerplate connections

**Human MUST**

- Define scoreboard semantics
- Decide what "correct" means

### CPU scoreboard (Python golden model)

```python
class CpuScoreboard(uvm_component):
    def build_phase(self):
        self.ref = RiscVReferenceModel()

    def write_commit(self, txn):
        ref_state = self.ref.step(txn.insn)
        assert txn.pc == ref_state.pc
```

**Human MUST**

- Write reference ISA model
- Handle corner cases

**AI SHOULD**

- Wrap comparisons
- Add logging and coverage

### cocotb glue

```python
@cocotb.test()
async def cpu_random_test(dut):
    env = CpuEnv("env", None)
    await run_test()

```

**Can let AI handle this**

## Checkers & Scoreboards

### CPU scoreboard

- Step-accurate ISA model
- Commit-based comparison
- Architectural state comparison

### GPU scoreboard

- Kernel-level reference execution
- End-of-kernel memory comparison
- Optional per-instruction tracing (debug mode)

## Assertions (SVA + Python)

### SVA (RTL)

- No double write-back
- No illegal state transitions
- Forward-progress guarantees

### Python assertions

- No unexpected memory writes
- No missing commits
- Kernel completion within bounds

## Regression Strategy

### Test tiers

1. Smoke (seconds)
2. Directed (minutes)
3. Random short (minutes)
4. Random long (hours)

### Automation

- CI-friendly
- Seed-based reproducibility
- Automatic failure minimization

## Exit criteria (Definition of 'Done')

### CPU

- 100% RV32I opcode coverage (implemented subset)
- Passes >= 10k random instruction tests
- Zero known failing seeds

### GPU

- Passes all directed kernels
- Divergence correctness proven
- No deadlocks in stress runs

### SoC

- Boots firmware reliably
- Sustains long-run random tests
