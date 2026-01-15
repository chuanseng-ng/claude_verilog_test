# CoCoTB Test Suite for RV32I CPU

This directory contains Python-based verification using [cocotb](https://www.cocotb.org/) - a coroutine-based cosimulation testbench environment for verifying VHDL and SystemVerilog RTL.

## Features

- **UVM-like Python Framework**: Modular verification components (drivers, monitors, agents)
- **Multi-Simulator Support**: Works with Verilator, ModelSim/Questa, and Vivado Xsim
- **Comprehensive Test Coverage**: Directed tests for ALU, memory, branches, and debug interface
- **Easy Switching**: Simple Makefile-based simulator selection
- **Waveform Support**: Integrated waveform generation for all simulators

## Directory Structure

```text
tests/cocotb/
├── Makefile                    # Main build file with simulator support
├── requirements.txt            # Python dependencies
├── README.md                   # This file
├── lib/                        # Verification library
│   ├── __init__.py
│   ├── rv32i_env.py           # Main test environment
│   ├── utils/                  # Utility classes
│   │   ├── __init__.py
│   │   └── base_components.py # UVM-like base classes
│   └── agents/                 # Protocol agents
│       ├── __init__.py
│       ├── axi4lite_agent.py  # AXI4-Lite memory agent
│       └── apb3_agent.py      # APB3 debug agent
├── tests/                      # Test files
│   ├── __init__.py
│   ├── test_rv32i_basic.py    # Basic functionality tests
│   └── test_rv32i_debug.py    # Debug interface tests
└── waves/                      # Waveform output directory

```

## Installation

### Prerequisites

- Python 3.7 or later
- One or more simulators:
  - **Verilator** (recommended for open-source, fast compilation)
  - **ModelSim/Questa** (commercial)
  - **Vivado Xsim** (Xilinx)

### Install Python Dependencies

```bash
cd tests/cocotb
pip install -r requirements.txt
```

Or use the Makefile:

```bash
make install
```

## Quick Start

### Run Tests with Verilator (Default)

```bash
# Run all basic tests
make test_basic

# Run all debug tests
make test_debug

# Run specific test
make test_simple_add

# Run with waveforms
make test_basic WAVES=1
```

### Run Tests with ModelSim/Questa

```bash
# Run all tests
make SIM=modelsim test_basic

# Run with GUI
make SIM=modelsim test_basic WAVES=1
```

### Run Tests with Vivado Xsim

```bash
# Run all tests
make SIM=xsim test_basic

# Run with waveform capture
make SIM=xsim test_basic WAVES=1
```

## Available Tests

### Basic Functionality Tests (`test_rv32i_basic.py`)

| Test | Description |
|------|-------------|
| `test_simple_add` | Tests basic ALU operations using simple_add.hex |
| `test_load_store` | Tests memory load/store operations |
| `test_branch` | Tests all branch instructions |
| `test_reset` | Verifies reset functionality |

### Debug Interface Tests (`test_rv32i_debug.py`)

| Test | Description |
|------|-------------|
| `test_halt_resume` | Tests CPU halt and resume via debug interface |
| `test_single_step` | Tests single-step execution |
| `test_register_access` | Tests reading/writing GPRs via debug |
| `test_pc_access` | Tests reading/writing PC via debug |
| `test_breakpoint` | Tests hardware breakpoint functionality |
| `test_full_debug_sequence` | Complete debug workflow test |

## Makefile Targets

### Test Execution

```bash
make all                 # Run all basic tests (default)
make test_basic          # Run basic functionality tests
make test_debug          # Run debug interface tests
make regression          # Run complete test suite
```

### Individual Tests

```bash
make test_simple_add     # ALU operations test
make test_load_store     # Memory operations test
make test_branch         # Branch instructions test
make test_reset          # Reset verification
make test_halt_resume    # Halt/resume test
make test_single_step    # Single-step test
make test_register_access # Register access test
make test_pc_access      # PC access test
make test_breakpoint     # Breakpoint test
make test_full_debug     # Full debug sequence
```

### Utilities

```bash
make clean               # Clean build artifacts
make waves               # View waveforms in GTKWave
make install             # Install Python dependencies
make help                # Show help message
```

## Simulator-Specific Usage

### Verilator

**Advantages:**
- Open-source and free
- Fast compilation
- Excellent for CI/CD

**Example:**
```bash
make SIM=verilator test_basic WAVES=1
make waves  # View with GTKWave
```

### ModelSim/Questa

**Advantages:**
- Industry-standard commercial simulator
- Excellent debug capabilities
- Full SystemVerilog support

**Example:**
```bash
make SIM=modelsim test_debug WAVES=1
# Waveforms saved to vsim.wlf
```

### Vivado Xsim

**Advantages:**
- Free with Vivado WebPACK
- Good integration with Xilinx tools
- Suitable for FPGA projects

**Example:**
```bash
make SIM=xsim test_basic WAVES=1
# Waveforms saved to xsim.wdb
```

## Architecture

### UVM-like Components

The verification framework uses a UVM-inspired architecture in Python:

#### Base Components (`lib/utils/base_components.py`)

- **BaseTransaction**: Base class for all transaction types
- **BaseDriver**: Base driver with standardized API
- **BaseMonitor**: Base monitor with callback support
- **BaseAgent**: Combines driver and monitor
- **TransactionQueue**: Thread-safe transaction queue

#### AXI4-Lite Agent (`lib/agents/axi4lite_agent.py`)

- **AXI4LiteSlaveDriver**: Memory model with configurable latency
- **AXI4LiteMonitor**: Transaction observation
- **AXI4LiteAgent**: Complete AXI4-Lite slave agent
- Features:
  - Byte-addressable memory (default 64KB)
  - Hex file loading
  - Configurable read/write latency
  - Full AXI4-Lite protocol support

#### APB3 Agent (`lib/agents/apb3_agent.py`)

- **APB3MasterDriver**: Debug interface master
- **APB3Monitor**: Transaction monitoring
- **APB3Agent**: Complete APB3 master agent
- Features:
  - CPU control (halt, resume, step, reset)
  - Register access (PC, GPRs, instruction)
  - Breakpoint management
  - Status monitoring

#### Environment (`lib/rv32i_env.py`)

- **RV32IEnvironment**: Main test environment
- Features:
  - Automatic clock generation
  - Reset sequencing
  - Program loading
  - Register verification
  - State dumping
  - Monitor management

### Test Structure

Tests are organized as Python async functions using cocotb decorators:

```python
@cocotb.test()
async def test_example(dut):
    # Create environment
    env = RV32IEnvironment(dut)
    env.build()

    # Reset
    await env.reset()

    # Load program
    env.load_program("program.hex")

    # Run test
    success = await env.run_program("program.hex", max_cycles=1000)

    # Verify results
    assert success, "Test failed"
```

## Creating New Tests

### Basic Test Template

```python
import cocotb
from rv32i_env import RV32IEnvironment

@cocotb.test()
async def test_my_feature(dut):
    # Setup
    env = RV32IEnvironment(dut)
    env.build()
    await env.reset()

    # Test body
    env.load_program("my_test.hex")
    success = await env.run_program("my_test.hex", max_cycles=5000)

    # Verification
    state = await env.dump_state()
    assert state['registers']['x5'] == 0x12345678, "Register check failed"

    # Cleanup
    env.stop_monitors()
```

### Debug Test Template

```python
@cocotb.test()
async def test_debug_feature(dut):
    env = RV32IEnvironment(dut)
    env.build()
    await env.reset()

    # Halt CPU
    await env.apb_agent.halt_cpu()

    # Read/modify state
    pc = await env.apb_agent.driver.read_pc()
    await env.apb_agent.write_gpr(5, 0xDEADBEEF)

    # Single step
    await env.apb_agent.step_cpu()

    # Resume
    await env.apb_agent.resume_cpu()
```

## Debugging Tests

### Enable Logging

Set cocotb log level:
```bash
export COCOTB_LOG_LEVEL=DEBUG
make test_basic
```

### View Waveforms

```bash
# Generate waveforms
make test_basic WAVES=1

# View in GTKWave
make waves
```

### Dump CPU State

Use the environment's dump functions:
```python
# Dump and print state
state = await env.dump_state()
env.print_state(state)
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SIM` | Simulator to use (verilator/modelsim/xsim) | verilator |
| `MODULE` | Python test module to run | tests.test_rv32i_basic |
| `WAVES` | Enable waveform dumping (0/1) | 0 |
| `COCOTB_LOG_LEVEL` | Logging level (INFO/DEBUG/WARNING) | INFO |

## Comparison: CoCoTB vs SystemVerilog UVM

| Feature | CoCoTB | SystemVerilog UVM |
|---------|--------|-------------------|
| Language | Python | SystemVerilog |
| Learning Curve | Gentle | Steep |
| Simulation Speed | Fast (Verilator) | Slower |
| Debug Tools | Python debugger | Simulator GUI |
| Reusability | High | High |
| Industry Adoption | Growing | Standard |
| Tool Cost | Free (Verilator) | Commercial simulators |

## Integration with Existing Tests

This cocotb framework **complements** the existing SystemVerilog testbenches:

- **SystemVerilog Unit Tests** (`sim/`): Low-level module testing with Verilator
- **SystemVerilog UVM** (`tb/uvm/`): Comprehensive randomized testing
- **CoCoTB** (`tests/cocotb/`): Directed tests, quick iteration, CI/CD

All three approaches are valuable and serve different purposes.

## Continuous Integration

Example GitHub Actions workflow:

```yaml
name: CoCoTB Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      - name: Install Verilator
        run: sudo apt-get install -y verilator
      - name: Install Python deps
        run: cd tests/cocotb && pip install -r requirements.txt
      - name: Run tests
        run: cd tests/cocotb && make regression
```

## Troubleshooting

### Import Errors

Make sure PYTHONPATH includes the lib directory:
```bash
export PYTHONPATH=$PWD/lib:$PYTHONPATH
```

### Simulator Not Found

Install the simulator and ensure it's in PATH:
```bash
which verilator  # Should show path
which vsim       # For ModelSim
which xsim       # For Vivado
```

### Waveform Not Generated

Ensure WAVES=1 is set:
```bash
make test_basic WAVES=1
ls -l dump.*
```

## Resources

- [CoCoTB Documentation](https://docs.cocotb.org/)
- [CoCoTB GitHub](https://github.com/cocotb/cocotb)
- [CoCoTB Examples](https://github.com/cocotb/cocotb/tree/master/examples)
- [Verilator Manual](https://verilator.org/guide/latest/)

## License

This test suite follows the same license as the main RV32I CPU project.

## Contributing

When adding new tests:
1. Follow the existing test structure
2. Add appropriate documentation
3. Ensure tests pass with all supported simulators
4. Update this README if adding new features
