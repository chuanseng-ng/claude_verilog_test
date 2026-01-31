# Legacy Cocotb Tests (Archived)

**Archive Date**: 2026-01-31
**Status**: DEPRECATED - Use pyuvm tests instead

## Purpose

This directory contains the original cocotb-based CPU verification tests that have been superseded by the pyuvm implementation. These tests are preserved for:

1. **Historical Reference**: Understanding the evolution of the verification infrastructure
2. **Comparison**: Validating that pyuvm tests produce equivalent results
3. **Fallback**: Emergency access to working tests if pyuvm issues arise

## Archived Tests

| File | Lines | Description | Replacement |
|------|-------|-------------|-------------|
| `test_smoke.py` | 631 | Basic CPU functionality tests (6 tests) | `test_smoke_uvm.py` (4 tests) |
| `test_isa_compliance.py` | 1875 | All 37 RV32I instruction tests | `test_isa_uvm.py` (TBD) |
| `test_random_instructions.py` | 243 | Random instruction generation tests | `test_random_uvm.py` (2 tests) |

**Total**: 2,749 lines of legacy test code

## Why Archived?

These tests were migrated to pyuvm (Phase A-G migration, completed 2026-01-31) to address:

1. **Code Duplication**: `APBDebugInterface` duplicated across 3+ test files
2. **No UVM Structure**: Raw `@cocotb.test()` decorators, no reusable infrastructure
3. **Background Task Leaks**: `SimpleAXIMemory` spawned handlers without cleanup
4. **Maintainability**: Direct DUT signal manipulation instead of agent-based approach

## Migration Status

| Original Test | pyuvm Equivalent | Status | Notes |
|---------------|------------------|--------|-------|
| `test_simple_addi` | `test_addi_uvm` | ✅ PASSING | Smoke test |
| `test_branch_taken` | `test_branch_taken_uvm` | ✅ PASSING | Smoke test |
| `test_branch_not_taken` | `test_branch_not_taken_uvm` | ✅ PASSING | Smoke test |
| `test_jal` | `test_jal_uvm` | ✅ PASSING | Smoke test |
| `test_random_100` | `test_random_single_uvm` | ✅ PASSING | 100 instructions, seed=42 |
| `test_random_multi_seed` | `test_random_multi_seed_uvm` | ✅ PASSING | 10 seeds × 100 instructions |
| All 37 ISA tests | `test_isa_uvm.py` | 🔄 PLANNED | Phase F/G migration |

## Using Legacy Tests (Not Recommended)

If you absolutely must run legacy tests:

```bash
cd tb/cocotb/cpu/legacy

# Run smoke tests (deprecated)
make MODULE=test_smoke smoke

# Run ISA compliance tests (deprecated)
make MODULE=test_isa_compliance isa

# Run random tests (deprecated)
make MODULE=test_random_instructions random
```

**WARNING**: These tests will not be maintained and may break with future RTL changes.

## Recommended: Use pyuvm Tests Instead

```bash
cd tb/cocotb/cpu

# Run pyuvm smoke tests (4 tests, ~2.5s)
make smoke_uvm

# Run pyuvm random tests (10 seeds × 100 instr, ~1 min)
make random_uvm

# Run all pyuvm tests
make all_uvm
```

See `../test_smoke_uvm.py` and `../test_random_uvm.py` for implementation details.

## Migration Documentation

Full migration documentation available at:
- **Migration Plan**: `docs/pyuvm_migration/MIGRATION_PLAN.md`
- **Migration Status**: `docs/pyuvm_migration/MIGRATION_STATUS.md`
- **Lessons Learned**: `docs/pyuvm_migration/LESSONS_LEARNED.md`
- **Phase Summaries**: `docs/pyuvm_migration/PHASES_A_E_SUMMARY.md`

## Removal Timeline

These tests will remain archived until:
1. All ISA compliance tests migrated to pyuvm (Phase G)
2. Regression testing confirms 100% parity
3. 6-month grace period after Phase G completion

**Target Removal Date**: Q3 2026

---

**For Questions**: See `docs/pyuvm_migration/` or `docs/verification/VERIFICATION_PLAN.md`
