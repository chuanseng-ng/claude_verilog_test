# Phase 1 Verification To-Do List

**Last Updated**: 2026-01-29 (Updated after Random Instruction Test completion)

**Current Status**: Scoreboard integration complete ✅, ISA compliance tests complete ✅ (37/37 passing, 100%), Random instruction tests complete ✅ (10,000 instructions, 0 failures)

---

## ✅ COMPLETED TASKS

### Task 1: Scoreboard Integration (COMPLETE)

**Status**: ✅ **DONE** - All 6 smoke tests now validate against reference model

**What was completed**:
- Modified `tb/cocotb/common/scoreboard.py` to handle partial RTL signal availability
- Enhanced `SimpleAXIMemory` in test_smoke.py to sync with reference model
- Updated `monitor_commits()` to validate every instruction against reference model
- Integrated scoreboard into all 5 smoke tests with instruction commits

**Test Results**:
```
TEST                        STATUS  COMMITS  MISMATCHES
test_reset                  PASS    N/A      N/A
test_fetch_nop              PASS    3        0
test_simple_addi            PASS    8        0
test_branch_not_taken       PASS    5        0
test_branch_taken           PASS    4        0
test_jal                    PASS    3        0
```

**Key Achievement**: First systematic RTL-vs-reference validation! Previously only checked final register values, now validates every instruction execution.

**Current Validation Level**:
- ✅ PC progression validated
- ✅ Instruction execution validated
- ⚠️ Register writes not yet validated (needs additional RTL signals)
- ⚠️ Memory accesses not yet validated (needs additional RTL signals)

**Files Modified**:
- `tb/cocotb/common/scoreboard.py` - Made lenient for partial RTL signals
- `tb/cocotb/cpu/test_smoke.py` - Added scoreboard to all tests

---

## 🔄 IN PROGRESS TASKS

(None - Task 3 completed! Moving to Task 4)

---

## ✅ COMPLETED TASKS (CONTINUED)

### Task 2: ISA Compliance Tests ✅ COMPLETE

**Status**: ✅ **COMPLETE** - All 37/37 tests passing (100%)! 🎉

**File**: `tb/cocotb/cpu/test_isa_compliance.py` (1783 lines)

**Test Results**: ✅ **37/37 PASSING (100%)**

**Major Achievements** (2026-01-24 to 2026-01-26):

1. ✅ **All 37 RV32I instructions implemented and tested**
2. ✅ **Major RTL bugs fixed** (see commits `87207ef` and earlier):
   - Fixed branch/jump timing (registered decision flag)
   - Fixed load data latching (added mem_rdata_raw register)
   - Fixed register file reads (changed to combinational)
3. ✅ **Test infrastructure fixed**:
   - Created `reset_dut_halted()` for proper CPU initialization
   - Fixed instruction encodings
   - Fixed test timing issues

**Passing Tests** (33/37) ✅:

✅ **All Arithmetic** (7/7):
- [x] ADD, SUB, ADDI, LUI, AUIPC (and 2 more in other categories)

✅ **All Logical** (6/6):
- [x] AND, OR, XOR, ANDI, ORI, XORI

✅ **All Shift** (6/6):
- [x] SLL, SRL, SRA, SLLI, SRLI, SRAI

✅ **All Comparison** (4/4):
- [x] SLT, SLTU, SLTI, SLTIU

✅ **Upper Immediate** (2/2):
- [x] LUI, AUIPC

✅ **All Branch Instructions** (6/6) - FIXED! 🎉:
- [x] BEQ - Branch if equal
- [x] BNE - Branch if not equal
- [x] BLT - Branch if less than (signed)
- [x] BGE - Branch if greater or equal (signed)
- [x] BLTU - Branch if less than (unsigned)
- [x] BGEU - Branch if greater or equal (unsigned)

✅ **All Jump Instructions** (2/2) - BOTH FIXED! 🎉:
- [x] JAL - Jump and link (both forward and backward jumps)
- [x] JALR - Jump and link register

✅ **All Load Instructions** (5/5) - FIXED! 🎉:
- [x] LW - Load word
- [x] LH - Load halfword (sign-extended)
- [x] LHU - Load halfword (unsigned)
- [x] LB - Load byte (sign-extended)
- [x] LBU - Load byte (unsigned)

✅ **All Store Instructions** (3/3) - FIXED! 🎉:
- [x] SW - Store word
- [x] SH - Store halfword
- [x] SB - Store byte

**Final Test Results** (Latest run: 2026-01-26 06:39 AM):
```
Total:    37/37 tests
Passing:  37 (100%)
Failing:  0 (0%)
Errors:   0
```

**What Fixed The Last 4 Failures**:

The RTL bug fixes from commits `87207ef` and earlier resolved all issues:

1. **Branch/Jump timing fix** (rv32i_control.sv):
   - Registered branch/jump decision flag at end of EXECUTE state
   - Fixed JAL backward jump test ✅

2. **Load data latching** (rv32i_core.sv):
   - Added mem_rdata_raw register to latch AXI read data
   - Fixed all 5 load instruction tests ✅

3. **Register file combinational reads** (rv32i_regfile.sv):
   - Changed from synchronous to combinational reads
   - Fixed store instructions by ensuring register values available immediately ✅

**Task 2 Complete** - Ready to move to Task 3 (Random instruction generator)

---

### Task 3: Random Instruction Generator ✅ COMPLETE

**Status**: ✅ **COMPLETE** - 10,000 random instructions passing (100%)! 🎉

**Files Created**:
- `tb/generators/rv32i_instr_gen.py` (251 lines)
- `tb/cocotb/cpu/test_random_instructions.py` (218 lines)

**Test Results**: ✅ **100/100 seeds PASSING (100%)**

```
Total seeds:     100
Passing seeds:   100 (100.0%)
Failing seeds:   0 (0.0%)
Total instructions: 10,000
Scoreboard mismatches: 0
```

**Major Achievements** (2026-01-27 to 2026-01-28):

1. ✅ **Random instruction generator implemented**:
   - Generates all 37 RV32I instructions with proper constraints
   - Seeded random generation for reproducibility
   - Configurable instruction distribution and memory ranges
   - Auto-terminates with EBREAK instruction

2. ✅ **Comprehensive random testing**:
   - 100 seeds × 100 instructions = 10,000 total instructions
   - Now updated to use random seed selection (0 to 1,000,000 range)
   - All tests pass with 0 scoreboard mismatches
   - Execution time: ~94 seconds

3. ✅ **Test infrastructure enhancements**:
   - Single-seed debug mode for reproducing failures
   - Automatic failing seed logging to `failing_seeds.txt`
   - Makefile integration with `make random` target
   - Clean commit monitoring (orphaned tasks fixed)

**Instruction Coverage**: All 37 RV32I instructions tested via random generation:
- Arithmetic (10): ADD, ADDI, SUB, LUI, AUIPC, SLT, SLTI, SLTU, SLTIU
- Logical (9): AND, ANDI, OR, ORI, XOR, XORI, SLL, SLLI, SRL, SRLI, SRA, SRAI
- Memory (8): LB, LBU, LH, LHU, LW, SB, SH, SW
- Branch (6): BEQ, BNE, BLT, BGE, BLTU, BGEU
- Jump (2): JAL, JALR
- Control (1): EBREAK

**What Was Implemented**:

1. **Instruction Generator** (`tb/generators/rv32i_instr_gen.py`):
   - Random R-type, I-type, and upper immediate instructions
   - Constrained operand generation (valid register numbers, immediate ranges)
   - Deterministic register initialization based on seed
   - Memory address constraints (separate instruction/data regions)

2. **Random Test Suite** (`tb/cocotb/cpu/test_random_instructions.py`):
   - Multi-seed test (100 seeds × 100 instructions)
   - Single-seed debug test (environment variable controlled)
   - Scoreboard validation for every instruction commit
   - Comprehensive test reporting with pass/fail statistics

3. **Makefile Integration**:
   - New targets: `make random`, `make isa`, `make ebreak`, `make all_tests`
   - Easy execution from Windows WSL environment
   - Documented in `RANDOM_TESTS_STATUS.md`

**Task 3 Complete** - Ready to move to Task 4 (AXI protocol tests)

**Test Pattern for Remaining Instructions**:

```python
@cocotb.test()
async def test_isa_beq(dut):
    """Test BEQ instruction (B-type)."""
    # Standard setup
    clock = Clock(dut.clk, 10, unit="ns")
    cocotb.start_soon(clock.start())
    ref_model = RV32IModel()
    scoreboard = CPUScoreboard(ref_model, log=dut._log)
    mem = SimpleAXIMemory(dut, ref_model=ref_model)
    dbg = APBDebugInterface(dut)
    commit_count = [0]
    cocotb.start_soon(monitor_commits(dut, scoreboard=scoreboard, count=commit_count))
    await reset_dut(dut)

    # Test 1: Branch taken (x1 == x2)
    # Load multi-instruction sequence:
    # 0x000: BEQ x1, x2, 8      (branch to 0x008 if equal)
    # 0x004: ADDI x3, x0, 99    (should be skipped)
    # 0x008: ADDI x4, x0, 1     (branch target, should execute)
    # ... test logic ...

    # Test 2: Branch not taken (x1 != x2)
    # ... test logic ...

    passed = scoreboard.report()
    assert passed, "Scoreboard validation failed"
    dut._log.info("BEQ instruction test passed")
```

---

## 📋 REMAINING TASKS

### Task 3: Random Instruction Generator ✅ COMPLETE (See "COMPLETED TASKS" section above)

**Priority**: ✅ **COMPLETED**

**Goal**: Execute 10,000+ random instructions with 0 failures ✅ ACHIEVED

**What was implemented**:

1. ✅ **Instruction generator** (`tb/generators/rv32i_instr_gen.py`):
   - Generates all 37 legal RV32I instructions
   - Constrains memory addresses to valid ranges
   - Deterministic seeded random generation for reproducibility
   - Configurable instruction distribution

2. ✅ **Random test file** (`tb/cocotb/cpu/test_random_instructions.py`):
   - Multi-seed test: 100 random seeds × 100 instructions = 10,000 total
   - Single-seed debug mode for failure reproduction
   - Scoreboard validation for every commit
   - Failing seed logging to `failing_seeds.txt`
   - Updated to use random seed selection (0 to 1,000,000 range)

3. ✅ **Makefile integration**:
   - New target: `make random` for easy execution
   - Additional targets: `make isa`, `make ebreak`, `make all_tests`
   - Documented in `RANDOM_TESTS_STATUS.md`

4. ✅ **Exit criterion achieved**: 10,000 instructions, 0 scoreboard mismatches, 0 failing seeds

**Completion Date**: 2026-01-28
**Actual Effort**: 2 sessions (generator + testing)

---

### Task 3.5: Random Test Enhancements (NOT STARTED - OPTIONAL)

**Priority**: 🟡 OPTIONAL - Improves test coverage and infrastructure

**Goal**: Enhance random instruction testing with additional coverage and infrastructure improvements

**What to implement**:

#### Potential Enhancements (from RANDOM_TESTS_STATUS.md)

1. **Increase test coverage**:
   - Current: 100 seeds × 100 instructions = 10,000 total
   - Target: 1,000 seeds × 100 instructions = 100,000 total
   - Or: 100 seeds × 1,000 instructions = 100,000 total
   - Benefit: 10× increase in instruction coverage

2. **Add stress tests**:
   - Memory-intensive programs (many loads/stores)
   - Deep branch nesting (nested if-else chains)
   - Jump-heavy sequences (function call simulation)
   - Register pressure tests (use all 31 registers)
   - Benefit: Tests corner cases and complex scenarios

3. **Performance benchmarks**:
   - Measure IPC (instructions per cycle)
   - Measure CPI (cycles per instruction) for each instruction type
   - Track execution statistics
   - Generate performance reports
   - Benefit: Quantify CPU performance characteristics

4. **Coverage analysis**:
   - Track which instruction combinations are tested
   - Track instruction pair frequencies (e.g., ADD→BEQ)
   - Identify untested combinations
   - Generate coverage reports
   - Benefit: Ensure comprehensive instruction interaction testing

5. **Directed random tests**:
   - Bias toward specific instruction types (e.g., 50% branches)
   - Create load/store focused test sequences
   - Create ALU-intensive test sequences
   - Configurable instruction distribution
   - Benefit: Targeted testing of specific subsystems

#### Test Infrastructure Improvements

1. **Parallel execution**:
   - Run multiple seeds in parallel using Python multiprocessing
   - Reduce test time from ~95s to ~20s (assuming 5 parallel workers)
   - File: `tb/cocotb/cpu/test_random_parallel.py`
   - Benefit: Faster test execution

2. **Test result database**:
   - Track historical pass/fail rates per seed
   - Store test results in SQLite database
   - Generate trend reports
   - File: `tb/common/test_database.py`
   - Benefit: Track test stability over time

3. **Automatic regression**:
   - Integrate into CI/CD pipeline (GitHub Actions)
   - Run on every commit to main branch
   - Automatic failure notifications
   - File: `.github/workflows/random_tests.yml`
   - Benefit: Catch regressions immediately

4. **Waveform capture**:
   - Automatically save VCD for failing seeds
   - Upload waveforms to artifacts
   - Easy debugging of failures
   - Modification to: `tb/cocotb/cpu/test_random_instructions.py`
   - Benefit: Faster failure debugging

#### Next Steps (from RANDOM_TESTS_STATUS.md)

1. ✅ Integrate into CI/CD pipeline (optional)
2. ✅ Add to regular regression suite (optional)
3. ✅ Document in verification plan (optional)
4. ⚠️ **Consider increasing to 100,000+ instructions** (recommended)

#### Implementation Priority

**High Priority** (Recommended):
- Increase test coverage to 100,000 instructions (1 hour implementation)
- Add waveform capture for failing seeds (30 mins)

**Medium Priority** (Nice to have):
- Directed random tests (2 hours)
- Stress tests (2 hours)

**Low Priority** (Optional enhancements):
- Performance benchmarks (3 hours)
- Coverage analysis (4 hours)
- Parallel execution (2 hours)
- Test result database (3 hours)
- CI/CD integration (2 hours)

#### Files to Create/Modify

**New Files**:
- `tb/generators/stress_test_gen.py` - Stress test generator
- `tb/generators/directed_random_gen.py` - Directed random generator
- `tb/cocotb/cpu/test_random_parallel.py` - Parallel test runner
- `tb/common/test_database.py` - Result tracking database
- `tb/common/coverage_tracker.py` - Instruction combination tracker
- `.github/workflows/random_tests.yml` - CI/CD integration

**Modified Files**:
- `tb/cocotb/cpu/test_random_instructions.py` - Add waveform capture, increase seeds
- `tb/generators/rv32i_instr_gen.py` - Add directed random support
- `sim/Makefile` - Add targets for parallel/stress tests

#### Success Criteria

**Minimum** (Quick wins):
- ✅ 100,000 instructions tested, 0 failures
- ✅ Waveform capture on failures working

**Full Implementation**:
- ✅ All enhancements implemented
- ✅ All infrastructure improvements working
- ✅ CI/CD integrated
- ✅ Performance reports generated

**Estimated Effort**: 1-2 weeks (optional, not blocking Phase 1)

**Note**: This task is **OPTIONAL** and not required for Phase 1 completion. Task 3 (10,000 instructions, 0 failures) already meets the Phase 1 exit criterion. These enhancements improve robustness but are not blocking.

---

### Task 4: AXI4-Lite Protocol Tests (NOT STARTED - NEXT PRIORITY)

**Priority**: HIGH - Phase 1 Exit Criterion #5

**Goal**: Validate AXI4-Lite master protocol compliance

**What to implement**:

1. **File**: `tb/cocotb/cpu/test_axi_protocol.py`

2. **Test categories**:

   a. **Back-pressure tests**:
      - Random delays on `axi_arready`
      - Random delays on `axi_rvalid`
      - Verify CPU stalls correctly
      - Verify `arvalid` held high until handshake

   b. **Error response tests**:
      - Return `SLVERR` (0b10) on read
      - Return `DECERR` (0b11) on unmapped address
      - Verify CPU traps on errors

   c. **Protocol compliance**:
      - Valid-before-ready rule
      - Signal stability during handshake
      - No protocol violations

3. **Implementation approach**:
   - Enhance `SimpleAXIMemory` or create new configurable memory model
   - Add back-pressure injection capability
   - Add error injection capability
   - Use AXI protocol assertions/checkers

**Estimated Effort**: 1-2 sessions

---

### Task 5: Debug Interface Tests (PARTIALLY STARTED)

**Priority**: MEDIUM

**Goal**: Test all APB3 debug features beyond basic halt/resume

**Current Status**: Basic halt/resume tested in smoke tests

**What remains**:

1. **Single-step execution** (NOT TESTED):
   - Halt CPU
   - Write single-step bit in DBG_CTRL
   - Verify exactly 1 instruction executes
   - Verify CPU returns to halted state

2. **Breakpoints** (NOT TESTED):
   - Write breakpoint address to DBG_BP0_ADDR
   - Enable breakpoint via DBG_BP0_CTRL[0]
   - Run CPU
   - Verify CPU halts when PC == breakpoint address
   - Check DBG_STATUS halt_cause bits
   - Test both BP0 and BP1

3. **Register write when halted** (NOT TESTED):
   - Halt CPU
   - Write GPRs via DBG_GPR[n]
   - Resume CPU
   - Verify register values persist and affect execution

4. **PC write when halted** (NOT TESTED):
   - Halt CPU
   - Write new PC via DBG_PC
   - Resume CPU
   - Verify execution continues from new PC

**Implementation**:
- Add to `tb/cocotb/cpu/test_smoke.py` or create `test_debug_interface.py`
- Use existing `APBDebugInterface` class
- Reference memory map in `docs/design/MEMORY_MAP.md`

**Estimated Effort**: 1 session

---

### Task 6: Coverage Collection (NOT STARTED)

**Priority**: MEDIUM (Needed to prove Phase 1 completion)

**Goal**: Track and report instruction, state, and code coverage

**What to implement**:

1. **Instruction coverage** (target: 37/37 = 100%):
   - Track which RV32I instructions were executed
   - Report at end of test suite
   - Current: ~3-4/37 (smoke tests only)
   - After ISA compliance tests: Should reach 37/37

2. **State coverage** (target: 8/8 = 100%):
   - Track which FSM states were visited:
     - RESET, FETCH, DECODE, EXECUTE, MEM_WAIT, WRITEBACK, TRAP, HALTED
   - Report at end of test suite

3. **Code coverage** (target: >95%, optional):
   - Enable Verilator `--coverage` flag in `sim/Makefile`
   - Run all tests
   - Generate coverage report (line/branch coverage)
   - Identify untested RTL paths

**Implementation**:
- Modify `sim/Makefile` to add coverage flags
- Create coverage tracking in Python tests (instruction/state)
- Generate coverage reports automatically after test runs
- Create `reports/coverage_summary.txt` or similar

**Estimated Effort**: 1 session

---

### Task 7: Documentation Updates (NOT STARTED)

**Priority**: LOW (But important for record-keeping)

**Goal**: Update project docs to reflect Phase 1 progress

**Files to update**:

1. **`docs/PHASE_STATUS.md`**:
   - Change Phase 1 status from "READY TO START" to "IN PROGRESS"
   - Document completed RTL modules (8/8)
   - Document scoreboard integration (complete)
   - Track Phase 1 exit criteria (currently 2/9 met)
   - Document test results and instruction coverage progress

2. **`CLAUDE.md`**:
   - Update "Next Steps" section with completed items
   - Document scoreboard integration in verification workflow
   - Update test results in project status

**Content to add**:

```markdown
## Phase 1 Status (IN PROGRESS)

### RTL Implementation: ✅ COMPLETE (8/8 modules)
- rv32i_cpu_top.sv (350+ lines)
- rv32i_core.sv (500+ lines, with debug outputs)
- rv32i_control.sv (370+ lines, branch/jump timing fixed)
- rv32i_decode.sv (400+ lines)
- rv32i_alu.sv (100+ lines)
- rv32i_regfile.sv (60 lines, combinational reads)
- rv32i_imm_gen.sv (100 lines)
- rv32i_branch_comp.sv (60 lines)

### Verification Progress:

**Scoreboard Integration**: ✅ COMPLETE
- All 6 smoke tests now validate against reference model
- 0 mismatches on 23 instruction commits
- PC and instruction execution validated

**ISA Compliance Tests**: ✅ COMPLETE (37/37 passing, 100%) 🎉
- Arithmetic: 7/7 passing ✅
- Logical: 6/6 passing ✅
- Shift: 6/6 passing ✅
- Comparison: 4/4 passing ✅
- Upper Immediate: 2/2 passing ✅
- Branch: 6/6 passing ✅
- Jump: 2/2 passing ✅ (JAL fixed!)
- Load: 5/5 passing ✅
- Store: 3/3 passing ✅ (SW, SH, SB all fixed!)

**Random Instruction Tests**: ✅ COMPLETE (10,000 instructions, 100%) 🎉
- Total seeds: 100/100 passing ✅
- Instructions per seed: 100
- Total instructions: 10,000
- Scoreboard mismatches: 0 ✅
- Failing seeds: 0 ✅

**Major RTL Fixes Applied**:
- Branch/jump timing fix (registered decision flag)
- Load data latching fix (mem_rdata_raw register)
- Register file combinational reads

**Phase 1 Exit Criteria Progress**: 5/9 met (56%)
- ✅ Smoke tests: 6/6 pass
- ✅ Scoreboard mismatches: 0
- ✅ Instruction coverage: 37/37 (100%) 🎉 **COMPLETE!**
- ✅ Random tests: 10,000 instructions with 0 failures 🎉 **COMPLETE!**
- ❌ AXI protocol tests: Not started ⚠️ **NEXT PRIORITY**
- ⚠️ Debug tests: Partial - Basic halt/resume only
- ❌ Code coverage: Not tracked - Target: >95%
- ❌ State coverage: Not tracked - Target: 100%
- ✅ Failing seeds: 0 (100/100 seeds pass) 🎉 **COMPLETE!**
```

**Estimated Effort**: 30 minutes

---

## 📊 PHASE 1 EXIT CRITERIA TRACKING

| # | Criterion | Target | Current Status | Progress |
|---|-----------|--------|----------------|----------|
| 1 | Smoke tests passing | 6/6 (100%) | ✅ **MET** | 6/6 with scoreboard |
| 2 | Scoreboard mismatches | 0 | ✅ **MET** | 0 mismatches |
| 3 | Instruction coverage | 37/37 (100%) | ✅ **MET** 🎉 | 37/37 all passing! |
| 4 | Random instruction tests | 10,000+, 0 fail | ✅ **MET** 🎉 | 10,000 instructions, 0 failures |
| 5 | AXI protocol tests | 100% pass | ❌ **Not started** | Task 4 - NEXT |
| 6 | Debug interface tests | 100% pass | ⚠️ **Partial** | Task 5 |
| 7 | Code coverage | >95% | ❌ **Not tracked** | Task 6 |
| 8 | State coverage | 8/8 (100%) | ❌ **Not tracked** | Task 6 |
| 9 | Failing random seeds | 0 | ✅ **MET** 🎉 | 0 failing seeds (100/100 pass) |

**Current**: ✅ **5/9 criteria met (56%)**
**After AXI protocol tests complete**: 6/9 criteria met (67%)
**Full Phase 1 completion**: 9/9 criteria met (100%)

**Recent Progress** (2026-01-24 to 2026-01-29):
- ✅ Instruction coverage improved from 57% (21/37) → 89% (33/37) → **100% (37/37)** 🎉
- ✅ Major RTL bugs fixed (branch/jump timing, load data latching, regfile reads)
- ✅ **ALL ISA compliance tests now passing** (branches, jumps, loads, stores)
- ✅ **Task 2 COMPLETE** (2026-01-26) - ISA compliance tests
- ✅ **Task 3 COMPLETE** (2026-01-28) - Random instruction generator (10,000 instructions, 0 failures) 🎉

---

## 🎯 RECOMMENDED EXECUTION ORDER

### Week 1: Foundation ✅ COMPLETE
1. ✅ **Task 1** - Scoreboard integration (COMPLETE - 2026-01-24)
2. ✅ **Task 2** - ISA compliance tests (COMPLETE - 2026-01-26, 37/37 passing) 🎉

### Week 2: Comprehensive Testing ✅ MOSTLY COMPLETE
3. ✅ **Task 3** - Random instruction generator (COMPLETE - 2026-01-28, 10k+ instructions) 🎉
3.5. ⏸️ **Task 3.5** - Random test enhancements (OPTIONAL - Not blocking Phase 1)
4. ⏳ **Task 4** - AXI protocol tests **← START HERE**

### Week 3: Completion (CURRENT FOCUS)
5. ⏳ **Task 5** - Complete debug tests
6. ⏳ **Task 6** - Coverage collection
7. ⏳ **Task 7** - Documentation updates

**Total Estimated Effort**: ~1 week remaining (4-6 sessions)
**Optional Enhancements**: Task 3.5 (1-2 weeks, not blocking)

---

## 🚀 QUICK START FOR NEXT SESSION

### ✅ Task 3 Complete!

**Recommended**: Start Task 4 (AXI4-Lite Protocol Tests) - Required for Phase 1
**Optional**: Task 3.5 (Random Test Enhancements) - Improves coverage but not blocking

---

### Task 4: AXI4-Lite Protocol Tests (RECOMMENDED - START HERE)

**Goal**: Validate AXI4-Lite master protocol compliance

**What to implement**:

1. **Create protocol test file** (`tb/cocotb/cpu/test_axi_protocol.py`):
   - Test back-pressure handling (random delays on axi_arready/axi_rvalid)
   - Test error responses (SLVERR, DECERR)
   - Validate protocol compliance (valid-before-ready, signal stability)

2. **Enhance memory model** or create configurable AXI slave:
   - Add back-pressure injection capability
   - Add error injection capability
   - Option 1: Enhance `SimpleAXIMemory` in `test_smoke.py`
   - Option 2: Create new `ConfigurableAXIMemory` class

3. **Test categories**:
   ```python
   # a. Back-pressure tests
   async def test_axi_arready_backpressure(dut):
       # Randomly delay axi_arready, verify CPU stalls correctly

   async def test_axi_rvalid_backpressure(dut):
       # Randomly delay axi_rvalid, verify CPU waits for data

   # b. Error response tests
   async def test_axi_slverr(dut):
       # Return SLVERR (0b10), verify CPU traps

   async def test_axi_decerr(dut):
       # Return DECERR (0b11) on unmapped address

   # c. Protocol compliance
   async def test_axi_valid_before_ready(dut):
       # Verify valid held high until handshake completes
   ```

4. **Run tests**:
   ```bash
   cd sim
   make test TEST_MODULE=tb.cocotb.cpu.test_axi_protocol
   ```

5. **Exit criterion**: All AXI protocol tests pass with 0 violations

**Estimated Effort**: 1-2 sessions

### To Start Task 4 (AXI Protocol Tests):

1. **Review AXI4-Lite protocol**: Check `docs/design/RTL_DEFINITION.md` for signal definitions
2. **Read implementation plan**: `TASK4_AXI_PROTOCOL_TESTS_PLAN.md` (comprehensive guide)
3. **Create test file**: `tb/cocotb/cpu/test_axi_protocol.py`
4. **Implement configurable memory model** with back-pressure and error injection
5. **Write protocol compliance tests**

---

### Task 3.5: Random Test Enhancements (OPTIONAL - NOT BLOCKING)

**Status**: Optional enhancements to improve test coverage beyond Phase 1 requirements

**Quick Wins** (Recommended if time permits):
1. **Increase to 100,000 instructions** (1 hour):
   ```python
   # In test_random_instructions.py
   NUM_SEEDS = 1000  # or 100 with 1000 instructions each
   ```

2. **Add waveform capture for failures** (30 mins):
   ```python
   # Save VCD when seed fails
   if not passed:
       dut._log.info(f"Saving waveform for seed {seed}")
       # VCD capture logic
   ```

**Full Enhancements** (See Task 3.5 details above):
- Stress tests (memory-intensive, deep branches)
- Performance benchmarks (IPC, CPI measurement)
- Coverage analysis (instruction pair tracking)
- Directed random tests (biased instruction distribution)
- Parallel execution
- CI/CD integration

**Note**: These are **OPTIONAL**. Task 3 (10,000 instructions) already meets Phase 1 exit criteria.

---

## 📝 NOTES

### Key Files:
- **Tests**: `tb/cocotb/cpu/test_smoke.py`, `tb/cocotb/cpu/test_isa_compliance.py`
- **Scoreboard**: `tb/cocotb/common/scoreboard.py`
- **Reference Model**: `tb/models/rv32i_model.py`
- **RTL Top**: `rtl/cpu/rv32i_cpu_top.sv`
- **Makefile**: `sim/Makefile`

### Test Execution:
```bash
# All smoke tests
cd sim && make test

# Specific test module
cd sim && make test TEST_MODULE=tb.cocotb.cpu.test_isa_compliance

# Specific test function
cd sim && make test TEST_MODULE=tb.cocotb.cpu.test_isa_compliance TEST=test_isa_add

# Clean build
cd sim && make clean && make test
```

### Important: RTL Signal Limitation
Current scoreboard only validates PC and instruction due to missing RTL signals:
- Missing: `commit_rd`, `commit_rd_we`, `commit_rd_data`
- Impact: Cannot validate register writes at commit time
- Workaround: Read registers via APB debug after execution
- Future: Add commit signals to RTL for full validation

### Coverage Tool Reference:
- Verilator coverage: `--coverage --coverage-line --coverage-toggle`
- Coverage output: `coverage.dat`
- View with: `verilator_coverage coverage.dat`

---

**END OF TODO LIST**
