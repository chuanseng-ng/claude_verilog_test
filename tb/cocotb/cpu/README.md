# CPU Cocotb Tests

This directory contains cocotb-based tests for the RV32I CPU.

## Directory Structure

```
tb/cocotb/cpu/
├── README.md                    # This file
├── Makefile                     # Test execution (use this!)
├── test_smoke_uvm.py           # ✅ Wrapper for pyuvm smoke tests
├── test_random_uvm.py          # ✅ Wrapper for pyuvm random tests
├── test_ebreak.py              # ✅ Standalone EBREAK test (uses pyuvm infrastructure)
└── legacy/                      # ⚠️  Archived legacy tests (deprecated)
    ├── README.md               # Migration history
    ├── test_smoke.py           # Original smoke tests (2,749 lines archived)
    ├── test_isa_compliance.py  # Original ISA tests
    └── test_random_instructions.py # Original random tests
```

---

## Test Categories

### Active Tests (Use These!)

| Test | Description | Command | Status |
|------|-------------|---------|--------|
| **pyuvm Smoke Tests** | 4 basic functionality tests | `make smoke_uvm` | ✅ 4/4 PASSING |
| **pyuvm Random Tests** | Random instruction testing | `make random_uvm` | ✅ 2/2 PASSING |
| **EBREAK Test** | Minimal EBREAK halt test | `make ebreak` | ✅ 1/1 PASSING |

### Archived Tests (Legacy)

| Test | Status | Replacement |
|------|--------|-------------|
| `legacy/test_smoke.py` | ⚠️ DEPRECATED | `test_smoke_uvm.py` |
| `legacy/test_isa_compliance.py` | ⚠️ DEPRECATED | TBD (Phase G+) |
| `legacy/test_random_instructions.py` | ⚠️ DEPRECATED | `test_random_uvm.py` |

See `legacy/README.md` for migration details.

---

## Quick Start

```bash
# Navigate here
cd tb/cocotb/cpu

# Run pyuvm tests (recommended)
make smoke_uvm      # 4 smoke tests (~2.5s)
make random_uvm     # Random tests (~1 min)
make all_uvm        # All pyuvm tests

# Run standalone tests
make ebreak         # EBREAK halt test

# Get help
make usage          # Show all available targets
```

---

## Test Organization

### Test Wrappers vs Implementation

The test files in this directory are **wrappers** that enable cocotb test discovery. The actual test implementation lives in `tb/cpu_uvm/`:

```
test_smoke_uvm.py (wrapper)
  ↓ imports from
tb/cpu_uvm/tests/test_smoke_uvm.py (implementation)
  ↓ uses
tb/cpu_uvm/env/cpu_env.py (environment)
tb/cpu_uvm/agents/*/  (agents & drivers)
tb/cpu_uvm/sequences/ (test sequences)
```

**Why This Structure?**
- **Cocotb Discovery**: Cocotb finds tests in `tb/cocotb/cpu/*.py`
- **Clean Organization**: Implementation stays in `tb/cpu_uvm/` hierarchy
- **Makefile Integration**: Tests run via `make MODULE=test_smoke_uvm`

---

## Running Tests

### Using Makefile Targets (Recommended)

```bash
# pyuvm tests
make smoke_uvm      # Run pyuvm smoke tests (4 tests)
make random_uvm     # Run pyuvm random tests (10 seeds)
make all_uvm        # Run all pyuvm test suites

# Standalone tests
make ebreak         # Run EBREAK halt test

# Legacy tests (not recommended - see legacy/README.md)
cd legacy && make MODULE=test_smoke smoke

# Utility
make usage          # Show all targets
make clean          # Remove build artifacts
```

### Expected Output

**Smoke Tests** (`make smoke_uvm`):
```
========================================
Running All pyuvm Test Suites
========================================

[1/2] Running pyuvm smoke tests...
** TESTS=4 PASS=4 FAIL=0 SKIP=0 **
✓ pyuvm smoke tests PASSED

[2/2] Running pyuvm random tests...
** TESTS=2 PASS=2 FAIL=0 SKIP=0 **
✓ pyuvm random tests PASSED

========================================
OVERALL RESULT: ✓ ALL PYUVM TESTS PASSED
========================================
```

---

## Test Details

### pyuvm Smoke Tests (`test_smoke_uvm.py`)

**Tests** (4 total):
1. `test_addi_uvm` - ADDI instruction (x1=42, x2=50)
2. `test_branch_taken_uvm` - BEQ branch taken (x3=2)
3. `test_branch_not_taken_uvm` - BEQ branch not taken (x3=1)
4. `test_jal_uvm` - JAL jump (x1=return addr, x2=2)

**Implementation**: `tb/cpu_uvm/tests/test_smoke_uvm.py`
**Sequences**: `tb/cpu_uvm/sequences/directed_sequences.py`

**Usage**:
```bash
make smoke_uvm  # Run all 4 tests

# Run specific test
export COCOTB_TEST_FILTER='test_addi_uvm'
make MODULE=test_smoke_uvm
```

### pyuvm Random Tests (`test_random_uvm.py`)

**Tests** (2 total):
1. `test_random_single_uvm` - 100 instructions, seed=42
2. `test_random_multi_seed_uvm` - 10 seeds × 100 instructions each

**Implementation**: `tb/cpu_uvm/tests/test_random_uvm.py`
**Sequence**: `tb/cpu_uvm/sequences/random_instr_sequence.py`
**Generator**: `tb/generators/rv32i_instr_gen.py`

**Usage**:
```bash
make random_uvm  # Run both tests (~1 minute)

# Run only single-seed test
export COCOTB_TEST_FILTER='test_random_single_uvm'
make MODULE=test_random_uvm
```

### EBREAK Test (`test_ebreak.py`)

**Purpose**: Minimal test that EBREAK instruction halts CPU

**Implementation**: Standalone test using pyuvm infrastructure components
**Key Feature**: Updated to use `AXIMemoryDriver` and `APBDebugDriver` instead of duplicate classes

**Usage**:
```bash
make ebreak
```

---

## Verification Infrastructure

Tests use the pyuvm-based UVM infrastructure:

```
Test
 └─ CPUEnvironment
      ├─ AXIAgent (memory transactions)
      ├─ APBAgent (debug access)
      ├─ CommitMonitor (observes commits)
      └─ CPUScoreboard (validates vs reference model)
```

**See**: `tb/cpu_uvm/README.md` for detailed infrastructure documentation

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'test_smoke_uvm'"

**Cause**: Test wrapper not found

**Fix**: Ensure you're in `tb/cocotb/cpu/` directory:
```bash
cd tb/cocotb/cpu
make smoke_uvm
```

### "No module named 'tb'"

**Cause**: PYTHONPATH not set

**Fix**: Use Makefile targets (automatic) or set manually:
```bash
export PYTHONPATH=/path/to/project/root
make MODULE=test_smoke_uvm
```

### "cocotb-config: command not found"

**Cause**: cocotb not in PATH (WSL environment)

**Fix**: Use login shell:
```bash
wsl bash -l -c "cd /mnt/c/.../tb/cocotb/cpu && make smoke_uvm"
```

Or add to `~/.bashrc`:
```bash
export PATH=$HOME/.local/bin:$PATH
```

### Tests Timeout

**Symptom**: Tests hang for 1000+ cycles

**Cause**: Background tasks not started (common issue)

**Fix**: See `tb/cpu_uvm/README.md` troubleshooting section

---

## Migration History

- **2026-01-30**: Phase A-E migration (infrastructure built)
- **2026-01-31**: Phase F-G migration (integration + cleanup)
  - Legacy tests archived to `legacy/`
  - Duplicate helper classes removed
  - All active tests use pyuvm infrastructure

**Documentation**: `docs/pyuvm_migration/` for complete migration history

---

## What's Next?

1. ✅ Smoke tests migrated (4/4 PASSING)
2. ✅ Random tests migrated (2/2 PASSING)
3. 🔄 **ISA compliance tests** - TBD (37 RV32I instructions)
   - Plan: Migrate `legacy/test_isa_compliance.py` to pyuvm
   - Target: Phase G+ (post-initial migration)

---

## References

- **pyuvm Infrastructure**: `tb/cpu_uvm/README.md`
- **Verification Plan**: `docs/verification/VERIFICATION_PLAN.md`
- **Migration Documentation**: `docs/pyuvm_migration/`
- **Legacy Tests**: `legacy/README.md`
- **Makefile Help**: `make usage`

---

**Questions?** See `tb/cpu_uvm/README.md` or migration documentation for detailed methodology.
