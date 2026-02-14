# cocotb Testbench Infrastructure

cocotb-based verification environment for RV32I CPU and GPU RTL.

## Overview

This directory contains the cocotb testbench infrastructure for verifying the CPU and GPU RTL implementations. cocotb allows writing testbenches in Python while simulating Verilog/SystemVerilog RTL.

**Current Status**: Infrastructure ready, waiting for Phase 1 RTL implementation.

## Directory Structure

```text
tb/cocotb/
├── bfm/                        # Bus Functional Models
│   ├── axi4lite_master.py      # AXI4-Lite master BFM
│   └── apb3_master.py          # APB3 master BFM + debug interface
├── common/                     # Common utilities
│   ├── clock_reset.py          # Clock and reset helpers
│   └── scoreboard.py           # Reference model comparison
├── cpu/                        # CPU testbenches
│   ├── test_smoke.py           # Smoke tests (6 tests, Phase 1)
│   ├── test_isa_compliance.py  # ISA compliance tests (37 tests, Phase 1)
│   ├── test_example_counter.py # Example test (works now)
│   ├── example_counter.sv      # Example RTL module
│   ├── Makefile                # CPU test makefile (Phase 1+)
│   └── Makefile.example        # Example test makefile
├── gpu/                        # GPU testbenches (Phase 4+)
└── README.md                   # This file
```

## Quick Start

### Prerequisites

```bash
# Install cocotb and simulator
pip install cocotb cocotb-bus

# Install Icarus Verilog (easiest option for Windows)
# Download from: https://bleyer.org/icarus/
# Or use Chocolatey: choco install iverilog

# Alternatively, install Verilator (more performant)
# WSL: sudo apt-get install verilator
```

### Run Example Test (Available Now)

Test the cocotb infrastructure with a simple counter:

```bash
cd tb/cocotb/cpu

# Run with Icarus Verilog
make -f Makefile.example SIM=icarus

# Or with Verilator (if installed)
make -f Makefile.example SIM=verilator
```

Expected output:

```text
TEST PASSED: test_counter_basic
TEST PASSED: test_counter_disable
TEST PASSED: test_counter_reset
```

### Run CPU Tests (Phase 1+)

Once Phase 1 RTL is implemented:

```bash
cd tb/cocotb/cpu

# Run all tests
make

# Run specific test module
make MODULE=test_smoke

# Run specific test within a module
make MODULE=test_isa_compliance TESTCASE=test_isa_add

# Generate waveforms
make WAVES=1
```

## Bus Functional Models (BFMs)

### AXI4-Lite Master

Initiates read/write transactions on AXI4-Lite bus.

**Usage:**

```python
from tb.cocotb.bfm.axi4lite_master import AXI4LiteMaster

# Initialize
axi = AXI4LiteMaster(dut, "axi_", dut.clk, dut.rst_n)

# Write transaction
resp = await axi.write(addr=0x1000, data=0xDEADBEEF)
assert resp == 0, "Write failed"  # 0 = OKAY

# Read transaction
data, resp = await axi.read(addr=0x1000)
assert data == 0xDEADBEEF
```

**Signals expected** (prefix with `name` parameter):

- Write address: `awvalid`, `awready`, `awaddr`, `awprot`
- Write data: `wvalid`, `wready`, `wdata`, `wstrb`
- Write response: `bvalid`, `bready`, `bresp`
- Read address: `arvalid`, `arready`, `araddr`, `arprot`
- Read data: `rvalid`, `rready`, `rdata`, `rresp`

### APB3 Master

Accesses APB3 slave devices (debug interface, peripherals).

**Usage:**

```python
from tb.cocotb.bfm.apb3_master import APB3Master, APB3DebugInterface

# Initialize
apb = APB3Master(dut, "apb_", dut.clk, dut.rst_n)

# Write transaction
success = await apb.write(addr=0x100, data=0x12345678)

# Read transaction
data, success = await apb.read(addr=0x100)
```

**Debug Interface Helper:**

```python
# High-level debug interface
debug = APB3DebugInterface(apb)

# Halt CPU
await debug.halt_cpu()

# Read/write registers
await debug.write_gpr(1, 42)  # x1 = 42
value = await debug.read_gpr(1)

# Set breakpoint
await debug.set_breakpoint(0, addr=0x1000, enable=True)

# Resume CPU
await debug.resume_cpu()
```

## Scoreboard

Compares RTL behavior against Python reference model.

**Usage:**

```python
from tb.cocotb.common.scoreboard import CPUScoreboard
from tb.models.rv32i_model import RV32IModel

# Initialize
ref_model = RV32IModel()
scoreboard = CPUScoreboard(ref_model, log)

# Check each committed instruction
rtl_commit = {
    'pc': int(dut.commit_pc.value),
    'insn': int(dut.commit_insn.value),
    'rd': int(dut.commit_rd.value),
    'rd_value': int(dut.commit_rd_data.value),
}

scoreboard.check_commit(rtl_commit)

# Generate final report
passed = scoreboard.report()
assert passed, "Scoreboard detected mismatches"
```

## Common Utilities

### Clock and Reset

```python
from tb.cocotb.common.clock_reset import setup_clock, reset_dut, wait_cycles

# Setup 100MHz clock
await setup_clock(dut, clock_period_ns=10)

# Apply reset (10 cycles)
await reset_dut(dut, duration_cycles=10)

# Wait 100 cycles
await wait_cycles(dut, 100)

# Wait for signal
await wait_for_signal(dut, "commit_valid", 1, timeout_cycles=1000)
```

## Writing Tests

### Basic Test Structure

```python
import cocotb
from cocotb.triggers import RisingEdge
from tb.cocotb.common.clock_reset import setup_clock, reset_dut

@cocotb.test()
async def my_test(dut):
    """Test description."""
    log = cocotb.logging.getLogger("my_test")

    # Setup
    await setup_clock(dut)
    await reset_dut(dut)

    # Test body
    log.info("Test starting")

    # ... test code ...

    # Assertions
    assert condition, "Error message"

    log.info("Test completed")
```

### Using Reference Model

```python
from tb.models.rv32i_model import RV32IModel

@cocotb.test()
async def test_with_model(dut):
    # Initialize model
    ref_model = RV32IModel()

    # Load program
    ref_model.load_program({
        0x0000: 0x00000093,  # addi x1, x0, 0
        0x0004: 0x00100113,  # addi x2, x0, 1
    })

    # Execute and compare
    for _ in range(2):
        # Wait for commit
        while not dut.commit_valid.value:
            await RisingEdge(dut.clk)

        # Get RTL state
        rtl_pc = int(dut.commit_pc.value)
        rtl_insn = int(dut.commit_insn.value)

        # Step reference model
        ref_result = ref_model.step(rtl_insn)

        # Compare
        assert ref_result['pc'] == rtl_pc
```

## Simulation Options

### Icarus Verilog (Recommended for Windows)

```bash
make SIM=icarus
```

**Pros:**

- Easy to install on Windows
- Fast compilation
- Good waveform support

**Cons:**

- Slower simulation than Verilator
- Less strict about SystemVerilog compliance

### Verilator (Recommended for Performance)

```bash
make SIM=verilator WAVES=1
```

**Pros:**

- Very fast simulation
- Excellent for large designs
- Strict linting

**Cons:**

- Harder to install on Windows (use WSL)
- Limited waveform support

### Running in WSL (Windows)

```bash
# From Windows PowerShell/CMD
wsl bash -c "cd /mnt/c/Users/.../claude_verilog_test/tb/cocotb/cpu && make"
```

## Waveform Viewing

### Generate Waveforms

```bash
# Icarus generates .vcd
make SIM=icarus

# Verilator generates .fst (with WAVES=1)
make SIM=verilator WAVES=1
```

### View Waveforms

**GTKWave** (recommended):

```bash
# Install
# Windows: Download from https://sourceforge.net/projects/gtkwave/
# Linux: sudo apt-get install gtkwave

# View
gtkwave dump.vcd
```

## Integration with Reference Models

The cocotb testbenches integrate with Python reference models:

```text
┌─────────────┐
│ RTL (DUT)   │
│  - CPU Core │
│  - Signals  │
└──────┬──────┘
       │
       │ Commits
       │
┌──────▼──────┐      ┌──────────────────┐
│ cocotb TB   │◄────►│ Python Ref Model │
│  - Monitor  │      │  - RV32IModel    │
│  - BFMs     │      │  - Execute insns │
└──────┬──────┘      └──────────────────┘
       │                      │
       │                      │
       └──────►Scoreboard◄────┘
                Compare &
                 Report
```

## Verification Strategy (Per VERIFICATION_PLAN.md)

### Phase 0 (Current)

- ✅ cocotb infrastructure setup
- ✅ BFMs implemented (AXI4-Lite, APB3)
- ✅ Scoreboard implemented
- ✅ Example test working

### Phase 1 (Next)

- Test all 37 RV32I instructions
- Test debug interface (halt/resume/step/breakpoints)
- Test AXI4-Lite interface
- Random instruction sequences (10k+ instructions)
- Compare against reference model

### Phase 2-3

- Pipeline hazard testing
- Cache coherence testing
- Interrupt testing

### Phase 4

- GPU kernel testing
- SIMT execution verification
- Divergence testing

## Troubleshooting

### cocotb not found

```bash
pip install --upgrade cocotb cocotb-bus
```

### Simulator not found

```bash
# Check simulator is in PATH
which iverilog  # or verilator

# Install if missing
# Windows: choco install iverilog
# Linux: sudo apt-get install iverilog
```

### Import errors in tests

```bash
# Ensure project root is in PYTHONPATH
export PYTHONPATH=$PYTHONPATH:/path/to/claude_verilog_test
```

### Test timeout

```bash
# Increase timeout in test
@cocotb.test(timeout_time=1000, timeout_unit="us")
```

## Next Steps

1. ✅ **Phase 0 Complete**: Infrastructure ready
2. ✅ **Phase 1 RTL**: CPU RTL implemented (8/8 modules)
3. ✅ **Phase 1 Tests**: Smoke tests (6/6 passing), ISA tests (33/37 passing)
4. **Run verification**: Execute tests with `make`
5. **Debug**: Use waveforms and scoreboard for debugging

## References

- cocotb documentation: https://docs.cocotb.org/
- VERIFICATION_PLAN.md: Complete verification strategy
- REFERENCE_MODEL_SPEC.md: Python model API
- PHASE1_ARCHITECTURE_SPEC.md: CPU RTL requirements
