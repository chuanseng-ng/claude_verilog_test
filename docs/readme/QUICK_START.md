# Quick Start

Build and run commands per phase. For environment requirements see the root
[`README.md`](../../README.md#requirements).

## Nix dev shell (simulation + lint)

A pinned nix flake at the repo root provides the deterministic EDA toolchain for
simulation and lint — **Verilator 5.048**, iverilog, gcc, make — so local and CI
toolchains match. Enter it before running any `sim/` make target:

```bash
nix develop          # primary entry point (flakes)
# or, without flakes enabled:
nix-shell            # same shell via shell.nix flake-compat wrapper

cd sim && make test  # Verilator + cocotb now use the pinned toolchain
```

The Python/cocotb stack (cocotb, pyuvm, cocotbext-axi, cocotb-bus) stays on the
system Python + pip — install once with
`pip install -r requirements.txt cocotb-bus cocotbext-axi`. Synthesis / PnR is
**not** covered by this shell; it uses the external librelane nix env via
`pnr/Makefile`.

## Phase 0: Reference Model Testing (Complete ✅)

```bash
# Navigate to test directory
cd tb/tests

# Run all reference model unit tests (66 tests)
pytest -v

# Run specific model tests
pytest test_rv32i_model.py -v      # CPU model (33 tests)
pytest test_gpu_model.py -v        # GPU model (12 tests)
pytest test_memory_model.py -v     # Memory model (21 tests)

# Run with coverage
pytest --cov=tb.models --cov-report=html
```

## Phase 1: RTL Simulation ✅ Complete (Archived to `micro_p/`)

Phase 1 single-cycle CPU has been completed and archived. All verification passed.

## Phase 2: RTL Simulation ✅ Complete

```bash
# Navigate to cocotb test directory (WSL)
cd tb/cocotb/cpu

# Run all Phase 2 test suites (111 tests)
make phase2_all

# Run individual suites
make smoke_uvm          # 4 smoke tests
make isa_uvm            # 54 ISA compliance tests
make pipeline_hazards   # 16 pipeline hazard tests
make interrupts         # 12 interrupt/CSR tests
make debug              # 6 debug interface tests
make axi_protocol       # 12 AXI protocol tests
make fault_injection    # 7 fault injection tests

# Run random regression (500 seeds × 100 instructions)
RANDOM_TEST_SEEDS=500 RANDOM_TEST_INSTRS=100 make random_uvm

# Clean build artifacts
make clean
```

## Phase 3: Cache Simulation ✅ Complete

```bash
# Navigate to sim directory
cd sim

# Run all Phase 3 cache tests (20 tests)
make phase3_all

# Run individual cache test suites
make icache             # I-cache unit tests (7 tests)
make dcache             # D-cache unit tests (8 tests)
make cache_integration  # CPU + cache integration tests (5 tests)

# Clean build artifacts
make clean
```
