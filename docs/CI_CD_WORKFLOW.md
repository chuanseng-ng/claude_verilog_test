# CI/CD Workflow Documentation

**Phase**: Phase 1 (COMPLETE) - Archived reference

## Overview

This document describes the GitHub Actions CI/CD workflow for the Phase 1 random test infrastructure. The workflow provides tiered testing strategy with automatic validation, artifact capture, and reporting.

> **Note**: This document describes Phase 1 CI/CD workflows. Phase 1 is now complete and archived to `micro_p/`. Phase 2 may use updated CI/CD workflows with pipeline-specific testing.

**Workflow File**: `.github/workflows/random_tests.yml`

## Workflow Triggers

The workflow runs automatically on:

1. **Push Events**:
   - `main` branch
   - `phase-1/**` branches

2. **Pull Request Events**:
   - PRs targeting `main` branch

3. **Scheduled Events**:
   - Daily at midnight UTC (nightly extended tests)

4. **Manual Dispatch**:
   - Can be triggered manually via GitHub Actions UI
   - Allows selection of test mode (smoke/full-random/extended)

## Tiered Testing Strategy

### Tier 1: Smoke Tests (PR Validation)

**Trigger**: Pull requests to `main`
**Duration**: ~2-3 minutes
**Purpose**: Fast validation before code review

**Test Configuration**:
```
Random Tests:  10 seeds × 50 instructions     = 500 instructions
Stress Tests:  10 seeds × 100 instr × 4 prof  = 4,000 instructions
Total:                                          4,500 instructions
```

**Environment Variables**:
- `RANDOM_TEST_SMOKE=1`
- `STRESS_TEST_SMOKE=1`

**Make Targets**:
- `make random_uvm_smoke`
- `make stress_uvm_smoke`

**Success Criteria**:
- All seeds pass scoreboard validation
- No mismatches detected
- Basic functionality verified

### Tier 2: Full Random Tests (Main Branch)

**Trigger**: Push to `main` branch
**Duration**: ~15-20 minutes
**Purpose**: Comprehensive random instruction coverage

**Test Configuration**:
```
Random Tests:  1,000 seeds × 100 instructions = 100,000 instructions
```

**Environment Variables**:
- `RANDOM_TEST_SEEDS=1000`
- `RANDOM_TEST_INSTRS=100`

**Make Targets**:
- `make random_uvm`

**Success Criteria**:
- All 1,000 seeds pass validation
- >50% instruction pair coverage (220+ unique pairs)
- IPC ~1.00 (single-cycle CPU baseline)
- No scoreboard mismatches

### Tier 3: Extended Tests (Nightly)

**Trigger**: Daily at midnight UTC (schedule)
**Duration**: ~30-45 minutes
**Purpose**: Comprehensive suite including random + stress tests

**Test Configuration**:
```
Random Tests:  1,000 seeds × 100 instructions = 100,000 instructions
Stress Tests:  100 seeds × 500 instr × 4 prof = 200,000 instructions
Total:                                          300,000 instructions
```

**Stress Test Profiles**:
1. **ALU-Intensive**: 90% ALU operations (tests ALU corner cases)
2. **Jump-Heavy**: 40% jump instructions (tests control flow)
3. **Shift-Intensive**: Heavy shift operations (tests shifter)
4. **Immediate-Heavy**: Tests immediate generation logic

**Success Criteria**:
- All random seeds pass (1,000 seeds)
- All stress profiles pass (4 × 100 seeds)
- >90% combined instruction pair coverage (400+ unique pairs)
- Performance metrics within expected ranges
- No failures across 300,000 instructions

## Job Structure

### Job 1: `smoke-test`

**Runs on**: `ubuntu-latest`
**Condition**: PR events or manual dispatch (smoke mode)

**Steps**:
1. Checkout repository
2. Set up Python 3.10
3. Install Verilator and GTKWave
4. Install Python dependencies (cocotb, pyuvm, etc.)
5. Create results directories
6. Run random smoke tests
7. Run stress smoke tests
8. Generate test summary
9. Upload artifacts (summary, waveforms, performance, coverage, logs)
10. Comment on PR with results

**Artifacts**:
- `smoke-test-summary` (7 days)
- `smoke-test-waveforms` (14 days, on failure)
- `smoke-test-performance` (30 days)
- `smoke-test-coverage` (30 days)
- `smoke-test-logs` (7 days)

### Job 2: `full-random-test`

**Runs on**: `ubuntu-latest`
**Condition**: Push to `main` or manual dispatch (full-random mode)

**Steps**:
1. Checkout repository
2. Set up Python 3.10
3. Install system dependencies
4. Install Python dependencies
5. Create results directories
6. Run full random tests (1,000 seeds)
7. Generate test summary
8. Upload artifacts

**Artifacts**:
- `full-random-summary` (30 days)
- `full-random-waveforms` (14 days, on failure)
- `full-random-performance` (30 days)
- `full-random-coverage` (30 days)
- `full-random-logs` (7 days)

### Job 3: `extended-test`

**Runs on**: `ubuntu-latest`
**Condition**: Scheduled (nightly) or manual dispatch (extended mode)

**Steps**:
1. Checkout repository
2. Set up Python 3.10
3. Install system dependencies
4. Install Python dependencies
5. Create results directories
6. Run random tests (1,000 seeds)
7. Backup random test results
8. Run stress tests (4 profiles × 100 seeds)
9. Backup stress test results
10. Generate comprehensive summary
11. Upload all artifacts
12. Create GitHub issue on failure

**Artifacts**:
- `extended-test-summary` (30 days)
- `extended-test-waveforms` (14 days, on failure)
- `extended-performance-random` (30 days)
- `extended-performance-stress` (30 days)
- `extended-coverage-random` (30 days)
- `extended-coverage-stress` (30 days)
- `extended-test-logs` (7 days)

**Failure Handling**:
- Auto-creates GitHub issue with:
  - Failure date and workflow run link
  - Test configuration details
  - List of available artifacts
  - Labels: `bug`, `ci-failure`, `verification`

### Job 4: `summary-report`

**Runs on**: `ubuntu-latest`
**Condition**: Always runs after all test jobs complete
**Dependencies**: Needs `[smoke-test, full-random-test, extended-test]`

**Steps**:
1. Generate overall summary with job status
2. Upload summary report

**Artifacts**:
- `ci-summary-report` (30 days)

## Artifact Retention Policy

| Artifact Type | Retention Period | Rationale |
|--------------|------------------|-----------|
| Test summaries | 30 days | Long-term tracking |
| Performance reports | 30 days | Trend analysis |
| Coverage reports | 30 days | Coverage tracking |
| Failure waveforms | 14 days | Debug recent issues |
| Test logs | 7 days | Short-term debugging |

## PR Comment Bot

The smoke test job includes automatic PR commenting that posts:

- Job status (success/failure)
- Commit SHA
- Link to workflow run
- Test summary
- Available artifacts
- Note about full tests on merge

**Example Comment**:
```
## ✅ Random Test Infrastructure - Smoke Test Results

**Job Status:** success
**Commit:** abc1234
**Workflow:** [View Run](https://github.com/...)

<details>
<summary>Test Summary</summary>

# Smoke Test Results
...

</details>

### Artifacts Available
- 🌊 Failure waveforms (if any failures occurred)
- 📊 Performance metrics (IPC/CPI analysis)
- 📈 Coverage reports (instruction pair coverage)
- 📝 Test logs

**Note:** Full random tests (100,000 instructions) will run after merge to main.
```

## Environment Setup

All jobs use the following environment:

**OS**: Ubuntu latest
**Python**: 3.10
**System Dependencies**:
- `verilator` (RTL simulator)
- `gtkwave` (waveform viewer utilities)

**Python Dependencies**:
- `cocotb` (testbench framework)
- `cocotb-bus` (bus models)
- `cocotbext-axi` (AXI protocol models)
- `pyuvm` (UVM framework)
- `pytest` (testing framework)
- `pytest-cov` (coverage plugin)

**Environment Variables**:
- `PYTHONPATH=${{ github.workspace }}` (set for all test runs)
- Test-specific variables (see each tier configuration)

## Directory Structure

```
results/
├── waveforms/           # VCD files for failed seeds
│   ├── seed_1000_failure.vcd
│   └── ...
├── performance.csv      # Performance metrics (IPC/CPI)
├── coverage_pairs.txt   # Instruction pair coverage
└── test_summary.txt     # Test execution summary
```

## Usage Examples

### Manual Workflow Dispatch

1. Go to GitHub repository
2. Click "Actions" tab
3. Select "Random Test Infrastructure" workflow
4. Click "Run workflow"
5. Select test mode:
   - `smoke`: Quick validation (4,500 instructions)
   - `full-random`: Full random tests (100,000 instructions)
   - `extended`: Full suite (300,000 instructions)
6. Click "Run workflow" button

### Viewing Results

**For PRs**:
1. Check automated PR comment for summary
2. Click workflow run link for details
3. Download artifacts if needed

**For main branch pushes**:
1. Go to "Actions" tab
2. Find the workflow run
3. Check job status and logs
4. Download artifacts from "Artifacts" section

**For nightly runs**:
1. Check for auto-created GitHub issues (on failure)
2. Review workflow run in "Actions" tab
3. Compare performance/coverage trends over time

### Downloading Artifacts

```bash
# Using GitHub CLI
gh run list --workflow=random_tests.yml
gh run view <run-id>
gh run download <run-id>

# Extract specific artifact
gh run download <run-id> -n full-random-performance
```

## Coverage Goals (Phase 1)

### Random Tests
- **Target**: 100,000 instructions
- **Pair Coverage**: >50% (220+ unique pairs out of 441 possible)
- **IPC**: ~1.00 (single-cycle CPU)
- **CPI**: ~1.00 (single-cycle CPU)

### Stress Tests
- **Target**: 200,000 instructions (4 profiles)
- **Pair Coverage**: >80% per profile (350+ unique pairs)
- **Purpose**: Exercise corner cases and specific instruction patterns

### Combined Coverage
- **Total Instructions**: 300,000 (nightly extended)
- **Pair Coverage**: >90% (400+ unique pairs)
- **Goal**: Comprehensive state space exploration

## Performance Metrics

The workflow tracks and reports:

1. **IPC (Instructions Per Cycle)**:
   - Expected: ~1.00 for Phase 1 single-cycle CPU
   - Deviations indicate stalls or timing issues

2. **CPI (Cycles Per Instruction)**:
   - Expected: ~1.00 for Phase 1
   - Will increase in pipelined phases

3. **Per-Instruction-Type CPI**:
   - Breakdown by instruction class
   - Identifies performance anomalies

4. **Instruction Distribution**:
   - Percentage of each instruction type
   - Validates generator distribution

## Coverage Metrics

The workflow tracks instruction pair coverage:

1. **Pair Coverage Percentage**:
   - Total unique pairs / 441 possible pairs
   - Indicates state space exploration

2. **Top Instruction Pairs**:
   - Most common transitions
   - Validates realistic code patterns

3. **Missing Pairs**:
   - Uncovered transitions
   - Targets for future directed tests

4. **Distribution Analysis**:
   - Pairs by first instruction type
   - Identifies coverage gaps

## Debugging Failures

### PR Smoke Test Failure

1. Check PR comment for summary
2. Review workflow logs for error messages
3. Download `smoke-test-waveforms` artifact
4. Open VCD in GTKWave: `gtkwave seed_*_failure.vcd`
5. Correlate with scoreboard mismatch logs
6. Create bug report in `fixes/` directory

### Main Branch Random Test Failure

1. Review workflow logs
2. Download `full-random-waveforms` artifact
3. Check performance/coverage reports for anomalies
4. Identify failing seed(s)
5. Reproduce locally:
   ```bash
   cd tb/cocotb/cpu
   export RANDOM_TEST_SEEDS=1
   export RANDOM_TEST_INSTRS=100
   make random_uvm  # Will use seed 1000
   ```

### Nightly Extended Test Failure

1. Check auto-created GitHub issue
2. Review workflow run link in issue
3. Download all artifacts (waveforms, performance, coverage)
4. Compare performance metrics to previous runs
5. Analyze coverage gaps
6. Create targeted directed tests for gaps

## Integration with Project Workflow

The CI/CD workflow integrates with the overall project workflow:

1. **Development** (feature branch):
   - No automatic tests (developer runs locally)

2. **Pull Request** (to main):
   - Automatic smoke tests (4,500 instructions)
   - PR comment with results
   - Blocks merge if tests fail

3. **Merge to Main**:
   - Automatic full random tests (100,000 instructions)
   - Comprehensive validation
   - Performance/coverage baseline

4. **Nightly Builds**:
   - Extended suite (300,000 instructions)
   - Trend analysis
   - Auto-issue creation on failure

## Customizing the Workflow

### Changing Test Parameters

Edit `.github/workflows/random_tests.yml`:

```yaml
# Example: Increase random test coverage
- name: Run full random tests
  env:
    RANDOM_TEST_SEEDS: '2000'  # Changed from 1000
    RANDOM_TEST_INSTRS: '100'
```

### Adding New Test Jobs

Add new job to workflow:

```yaml
jobs:
  custom-test:
    name: Custom Test Suite
    runs-on: ubuntu-latest
    if: github.event_name == 'push'
    steps:
      - name: Run custom tests
        working-directory: tb/cocotb/cpu
        run: make custom_target
```

### Modifying Artifact Retention

Change retention period in upload step:

```yaml
- name: Upload artifacts
  uses: actions/upload-artifact@v4
  with:
    retention-days: 60  # Changed from 30
```

## Monitoring and Maintenance

### Regular Monitoring

- **Weekly**: Check nightly test results for trends
- **Monthly**: Review coverage metrics and identify gaps
- **Quarterly**: Analyze performance trends and update baselines

### Maintenance Tasks

1. **Update dependencies** (as needed):
   - Verilator version
   - Python packages
   - GitHub Actions versions

2. **Adjust test parameters** (based on project phase):
   - Increase seed counts for more coverage
   - Add new stress profiles
   - Update coverage goals

3. **Cleanup artifacts** (manual):
   - Old workflow runs auto-deleted per retention policy
   - Can manually delete older runs to save storage

## Troubleshooting

### Common Issues

**Issue**: YAML syntax error
**Solution**: Validate locally with `python -c "import yaml; yaml.safe_load(open('.github/workflows/random_tests.yml', encoding='utf-8'))"`

**Issue**: Tests timeout
**Solution**: Increase timeout in test configuration or reduce test count

**Issue**: Out of disk space
**Solution**: Reduce artifact retention or clean up old workflow runs

**Issue**: Verilator compilation fails
**Solution**: Check RTL syntax, review Verilator warnings in logs

**Issue**: Python import errors
**Solution**: Verify PYTHONPATH is set correctly in workflow

## Future Enhancements

Potential workflow improvements:

1. **Matrix Testing**:
   - Test across multiple Python versions
   - Test with different simulators (Verilator, Icarus)

2. **Parallel Job Execution**:
   - Split stress tests into separate parallel jobs
   - Run random tests in chunks

3. **Coverage Trend Dashboard**:
   - Visualize coverage over time
   - Track regression in coverage

4. **Performance Benchmarking**:
   - Compare IPC/CPI across commits
   - Alert on performance regression

5. **Automatic Bug Report Creation**:
   - Parse failure logs
   - Create structured bug reports in `fixes/`

## References

- **Workflow Spec**: `.github/workflows/random_tests.yml`
- **Random Tests**: `tb/cpu_uvm/tests/test_random_uvm.py`
- **Stress Tests**: `tb/cpu_uvm/tests/test_stress_uvm.py`
- **Makefile**: `tb/cocotb/cpu/Makefile`
- **Verification Plan**: `docs/verification/VERIFICATION_PLAN.md`
- **Random Tests Status**: `docs/RANDOM_TESTS_STATUS.md`

## Contact and Support

For workflow issues or questions:
1. Check this documentation
2. Review workflow logs in GitHub Actions
3. Consult verification team
4. Create GitHub issue with `ci-workflow` label
