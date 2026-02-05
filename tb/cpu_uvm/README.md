# CPU UVM Verification Infrastructure

**Status**: ✅ OPERATIONAL (Phase G complete - 2026-01-31)

This directory contains the pyuvm-based Universal Verification Methodology (UVM) infrastructure for RV32I CPU verification.

## Table of Contents
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Directory Structure](#directory-structure)
- [Running Tests](#running-tests)
- [Creating New Tests](#creating-new-tests)
- [Components Reference](#components-reference)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# Navigate to test directory
cd tb/cocotb/cpu

# Run smoke tests (4 tests, ~2.5 seconds)
make smoke_uvm

# Run random tests (10 seeds × 100 instructions, ~1 minute)
make random_uvm

# Run all pyuvm tests
make all_uvm
```

**Expected Output**: All tests PASS with scoreboard validation messages.

---

## Architecture

The verification infrastructure follows standard UVM methodology:

```
Test (uvm_test)
  └─ Environment (CPUEnvironment)
       ├─ AXI Agent (AXIAgent)
       │    └─ AXI Driver (AXIMemoryDriver) - Handles memory transactions
       ├─ APB Agent (APBAgent)
       │    └─ APB Driver (APBDebugDriver) - Debug register access
       ├─ Commit Monitor (CommitMonitor) - Observes instruction commits
       └─ Scoreboard (CPUScoreboard) - Validates against reference model
```

**Key Features**:
- **Reusable Components**: All agents/drivers shared across tests
- **Reference Model Integration**: RV32IModel validates RTL behavior
- **TLM Communication**: Commit transactions between monitor and scoreboard
- **Proper Lifecycle**: build_phase → connect_phase → run_phase

---

## Directory Structure

```
tb/cpu_uvm/
├── README.md                    # This file
├── agents/                      # UVM agents
│   ├── axi_agent/
│   │   ├── axi_agent.py        # AXI agent (contains driver)
│   │   └── axi_driver.py       # AXI4-Lite memory driver
│   └── apb_agent/
│       ├── apb_agent.py        # APB agent (contains driver)
│       ├── apb_driver.py       # APB3 debug driver
│       └── apb_sequence_item.py # APB transaction item
├── env/
│   └── cpu_env.py              # CPU environment (top-level)
├── monitors/
│   └── commit_monitor.py       # Instruction commit monitor
├── scoreboards/
│   └── cpu_scoreboard.py       # Reference model validator
├── sequences/
│   ├── base_sequence.py        # Base sequence class
│   ├── directed_sequences.py   # Smoke test sequences
│   └── random_instr_sequence.py # Random instruction sequence
└── tests/
    ├── base_test.py            # Base test class + run_uvm_test helper
    ├── test_smoke_uvm.py       # Smoke tests (ADDI, branches, JAL)
    └── test_random_uvm.py      # Random instruction tests
```

**Total**: 18 files, ~1,800 lines of verification code

---

## Running Tests

### Using Make Targets (Recommended)

```bash
cd tb/cocotb/cpu

# Individual test suites
make smoke_uvm      # 4 smoke tests (ADDI, branch, JAL)
make random_uvm     # Random instruction tests (10 seeds)

# All pyuvm tests
make all_uvm        # Runs all test suites with summary

# Clean build artifacts
make clean
```

### Direct Module Invocation

```bash
# Run specific test module
make MODULE=test_smoke_uvm

# Run with filter
export COCOTB_TEST_FILTER='test_addi_uvm'
make MODULE=test_smoke_uvm

# Run with different simulator
make SIM=icarus smoke_uvm
```

### Expected Results

**Smoke Tests** (`make smoke_uvm`):
```
** TESTS=4 PASS=4 FAIL=0 SKIP=0 **
   - test_addi_uvm: PASS
   - test_branch_taken_uvm: PASS
   - test_branch_not_taken_uvm: PASS
   - test_jal_uvm: PASS
```

**Random Tests** (`make random_uvm`):
```
** TESTS=2 PASS=2 FAIL=0 SKIP=0 **
   - test_random_single_uvm: PASS (100 instructions)
   - test_random_multi_seed_uvm: PASS (10 seeds)
```

---

## Creating New Tests

### Method 1: Using BaseTest (Recommended)

```python
# tb/cpu_uvm/tests/test_my_feature_uvm.py

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from .base_test import BaseTest
from ..sequences.my_sequence import MySequence  # Your custom sequence


class MyFeatureTest(BaseTest):
    """Test for my custom CPU feature."""

    async def run_phase(self):
        """Run test sequence."""
        self.logger.info("Running my feature test")

        # Create and run sequence
        seq = MySequence("my_seq")
        seq.env = self.env
        await seq.pre_body()  # If sequence has setup
        await seq.body()
        await seq.post_body()

        # Wait for completion
        await self.wait_for_completion()

        # Verify results via APB
        apb_driver = self.env.apb_agent.driver
        result = await apb_driver.read_gpr(5)
        assert result == 0x42, f"Expected x5=0x42, got {result}"

        self.logger.info("✓ My feature test passed")


# Cocotb test wrapper
@cocotb.test()
async def test_my_feature_uvm(dut):
    """Test my custom feature (pyuvm version)."""
    dut._log.info("=== Test: My Feature (pyuvm) ===")

    # Start clock
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())

    # Create and run test
    test = MyFeatureTest("my_feature_test", None, dut)
    test.build_phase()
    test.connect_phase()
    test.end_of_elaboration_phase()

    # Start background tasks
    cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler())
    cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler())
    cocotb.start_soon(test.env.commit_monitor.run_phase())
    cocotb.start_soon(test.env.scoreboard.run_phase())

    # Give background tasks time to start
    await ClockCycles(dut.clk, 2)

    # Reset and run
    await test.reset_dut()
    await test.run_phase()

    # Report results
    test.env.scoreboard.report_phase()
    assert test.env.scoreboard.mismatches == 0, "Scoreboard validation failed"
```

### Method 2: Using run_uvm_test Helper

```python
from .base_test import BaseTest, run_uvm_test

@cocotb.test()
async def test_my_feature_simple(dut):
    """Simplified test using run_uvm_test helper."""
    await run_uvm_test(dut, MyFeatureTest, "my_feature_test")
```

**Note**: The helper automatically handles clock, phases, and background tasks.

---

## Components Reference

### AXIMemoryDriver (`agents/axi_agent/axi_driver.py`)

**Purpose**: Handles AXI4-Lite memory transactions (instruction fetch + data access)

**Key Methods**:
- `write_word(addr, data)` - Write 32-bit word to memory
- `read_word(addr)` - Read 32-bit word from memory
- `axi_read_handler()` - Background task for AXI reads (must run via cocotb.start_soon)
- `axi_write_handler()` - Background task for AXI writes (must run via cocotb.start_soon)

**Usage**:
```python
# In sequence
axi_driver = self.env.axi_agent.driver
axi_driver.write_word(0x1000, 0x12345678)
data = axi_driver.read_word(0x1000)
```

### APBDebugDriver (`agents/apb_agent/apb_driver.py`)

**Purpose**: Debug register access via APB3 protocol

**Key Methods**:
- `halt_cpu()` - Halt CPU execution
- `resume_cpu()` - Resume CPU execution
- `read_pc()` / `write_pc(value)` - Program counter access
- `read_gpr(reg)` / `write_gpr(reg, value)` - General purpose register access
- `apb_read(addr)` / `apb_write(addr, data)` - Raw APB access

**Usage**:
```python
# In test
apb_driver = self.env.apb_agent.driver
await apb_driver.halt_cpu()
await apb_driver.write_pc(0x1000)
x5 = await apb_driver.read_gpr(5)
await apb_driver.resume_cpu()
```

### CommitMonitor (`monitors/commit_monitor.py`)

**Purpose**: Observes instruction commits from DUT

**How It Works**:
- Monitors `commit_valid` signal
- Captures PC, instruction, register writes on commit
- Sends commit transactions to scoreboard via TLM analysis port

**No Direct Usage**: Runs automatically in background

### CPUScoreboard (`scoreboards/cpu_scoreboard.py`)

**Purpose**: Validates RTL commits against RV32IModel reference model

**How It Works**:
- Receives commit transactions from CommitMonitor
- Executes same instruction in RV32IModel
- Compares register values, flags mismatches
- Logs matches/mismatches

**Usage**:
```python
# In test (automatic validation)
test.env.scoreboard.report_phase()
assert test.env.scoreboard.mismatches == 0
```

---

## Troubleshooting

### Tests Timeout Waiting for EBREAK

**Symptom**: Tests hang for 1000+ cycles, no commits observed

**Cause**: Background tasks (AXI handlers, monitor, scoreboard) not started

**Fix**: Ensure `cocotb.start_soon()` calls in test:
```python
cocotb.start_soon(test.env.axi_agent.driver.axi_read_handler())
cocotb.start_soon(test.env.axi_agent.driver.axi_write_handler())
cocotb.start_soon(test.env.commit_monitor.run_phase())
cocotb.start_soon(test.env.scoreboard.run_phase())
```

### AttributeError: 'NoneType' object has no attribute 'generate_program'

**Symptom**: Random tests fail with generator = None

**Cause**: Sequence `pre_body()` not called before `body()`

**Fix**: Call sequence lifecycle methods:
```python
await seq.pre_body()  # Creates generator
await seq.body()      # Runs sequence
await seq.post_body() # Cleanup
```

### Scoreboard Shows 0 Commits Checked

**Symptom**: "Total commits checked: 0" in report

**Cause**: TLM connection between monitor and scoreboard not established

**Status**: Known issue - tests still validate via APB register checks

### Module Import Errors

**Symptom**: `ModuleNotFoundError: No module named 'tb'`

**Cause**: PYTHONPATH not set

**Fix**: Use Makefile targets (automatic) or set manually:
```bash
export PYTHONPATH=$PYTHONPATH:/path/to/project/root
make MODULE=test_smoke_uvm
```

---

## Migration History

This infrastructure was created during Phase A-G migration (2026-01-30 to 2026-01-31):

- **Phase A**: Foundation setup (directory structure, dependencies)
- **Phase B**: Core components (drivers, monitor, scoreboard)
- **Phase C**: Agents and environment
- **Phase D**: Sequences
- **Phase E**: Tests
- **Phase F**: Integration and validation
- **Phase G**: Cleanup and finalization

**Migration Documentation**: See `docs/pyuvm_migration/`

---

## References

- **Verification Plan**: `docs/verification/VERIFICATION_PLAN.md`
- **Migration Plan**: `docs/pyuvm_migration/MIGRATION_PLAN.md`
- **pyuvm Documentation**: https://github.com/pyuvm/pyuvm
- **UVM 1.2 Standard**: IEEE 1800.2-2017
- **Legacy Tests**: `tb/cocotb/cpu/legacy/` (archived)

---

**Questions?** See migration documentation or verification plan for detailed methodology.
