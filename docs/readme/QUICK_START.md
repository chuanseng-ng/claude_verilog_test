# Quick Start

Build and run commands per phase. For environment requirements see the root
[`README.md`](../../README.md#requirements).

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
make interrupts         # 13 interrupt/CSR tests (incl. concurrent-IRQ priority)
make debug              # 6 debug interface tests
make axi_protocol       # 12 AXI protocol tests
make fault_injection    # 7 fault injection tests

# Run random regression (500 seeds × 100 instructions)
RANDOM_TEST_SEEDS=500 RANDOM_TEST_INSTRS=100 make random_uvm

# Replay a single failing seed (per-seed outcomes are logged to
# results/random_seed_log.txt by every multi-seed run)
make random_uvm SEED=1042 INSTRS=100

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

## RTL Linting & Formatting

Two complementary tools, both run from `sim/`:

- **Verilator** (`make lint`) — semantic/structural lint (widths, latches, unused signals).
- **Verible** (`make verible`) — SystemVerilog *style* lint + *formatting* consistency.
  Install a prebuilt binary from
  [Verible releases](https://github.com/chipsalliance/verible/releases) (no build needed).

```bash
cd sim

make lint                  # Verilator semantic lint (CPU top + soc_top)

make lint-verible          # Verible style lint (curated ruleset, whole tree)
make format-verible-check  # Report formatting deviations (non-mutating)
make format-verible-fix    # Rewrite files in place to canonical format
make verible               # lint-verible + format-verible-check

# Check/format a subset (used by CI for changed files only):
make format-verible-check VERIBLE_CHECK_FILES="rtl/cpu/core/rv32i_alu.sv"
```

Style rules live in [`.rules.verible_lint`](../../.rules.verible_lint). CI runs Verible via the
[`rtl-checks.yml`](../../.github/workflows/rtl-checks.yml) workflow — currently **non-blocking**
during initial adoption (the format check covers only RTL files changed in a PR).
