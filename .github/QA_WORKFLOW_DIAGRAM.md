# QA Workflow Diagram

Visual representation of the complete QA workflow from local development to CI.

## Complete QA Flow

```text
┌─────────────────────────────────────────────────────────────────────┐
│                         DEVELOPER WORKFLOW                          │
└─────────────────────────────────────────────────────────────────────┘

    ┌──────────────────┐
    │  Write Code      │
    │  tb/models/      │
    │  tb/tests/       │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────┐
    │  git add .       │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────────────────────────────────────────────┐
    │                    git commit -m "..."                   │
    │                                                          │
    │  PRE-COMMIT HOOKS RUN AUTOMATICALLY (if installed)       │
    │  ┌────────────────────────────────────────────────┐    │
    │  │ 1. Basic checks (whitespace, YAML, etc.)       │    │
    │  │ 2. Ruff lint --fix (auto-fix issues)           │    │
    │  │ 3. Ruff format (auto-format code)              │    │
    │  │ 4. MyPy (type checking)                        │    │
    │  │ 5. Pylint (code quality ≥9.5/10)               │    │
    │  │ 6. Pytest quick (smoke test)                   │    │
    │  └────────────────────────────────────────────────┘    │
    │                                                          │
    │  ✓ All pass → Commit created                            │
    │  ✗ Any fail → Fix issues, try again                     │
    └────────┬─────────────────────────────────────────────────┘
             │
             │ ✓ Commit successful
             ▼
    ┌──────────────────┐
    │  git push        │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────────────────────────────────────────────┐
    │              PRE-PUSH HOOK (if installed)                │
    │  ┌────────────────────────────────────────────────┐    │
    │  │ pytest tb/tests/ -v (full test suite)          │    │
    │  └────────────────────────────────────────────────┘    │
    │                                                          │
    │  ✓ Tests pass → Push to GitHub                          │
    │  ✗ Tests fail → Fix tests, commit, try again            │
    └────────┬─────────────────────────────────────────────────┘
             │
             │ ✓ Push successful
             ▼

┌─────────────────────────────────────────────────────────────────────┐
│                          GITHUB WORKFLOW                            │
└─────────────────────────────────────────────────────────────────────┘

             │
             ▼
    ┌──────────────────────────────────────┐
    │  Feature Branch on GitHub            │
    │  (origin/feature/my-feature)         │
    └────────┬─────────────────────────────┘
             │
             │ ❌ No CI runs on feature branches
             ▼
    ┌──────────────────────────────────────────────────────────┐
    │          Create Pull Request → main                      │
    │                                                          │
    │  ✅ TRIGGERS CI WORKFLOWS                                │
    └────────┬─────────────────────────────────────────────────┘
             │
             ├──────────────────┬──────────────────────┐
             ▼                  ▼                      ▼
    ┌────────────────┐  ┌────────────────┐  ┌────────────────┐
    │ QA Checks      │  │ QA Checks      │  │ Tests          │
    │ (Python 3.11)  │  │ (Python 3.12)  │  │ (Python 3.12)  │
    └────────┬───────┘  └────────┬───────┘  └────────┬───────┘
             │                   │                    │
             ▼                   ▼                    ▼
    ┌─────────────────────────────────────────────────────────┐
    │                   PARALLEL EXECUTION                    │
    │ ┌──────────────────────────────────────────────────┐   │
    │ │ 1. ruff format --check                           │   │
    │ │ 2. ruff check                                    │   │
    │ │ 3. mypy tb/models tb/tests                       │   │
    │ │ 4. pylint tb/models tb/tests                     │   │
    │ │ 5. pytest --cov (with coverage report)           │   │
    │ │ 6. Upload coverage to Codecov (3.12 only)        │   │
    │ └──────────────────────────────────────────────────┘   │
    └─────────┬───────────────────────────────────────────────┘
              │
              ▼
    ┌──────────────────┐
    │  ✓ All pass?     │
    └────────┬─────────┘
             │
      ┌──────┴──────┐
      │             │
      ▼             ▼
   ✓ YES         ✗ NO
      │             │
      │             ▼
      │    ┌──────────────────┐
      │    │  PR blocked      │
      │    │  Must fix issues │
      │    │  Push fixes      │
      │    │  CI re-runs      │
      │    └────────┬─────────┘
      │             │
      │             └──────┐
      │                    │
      ▼                    ▼
    ┌──────────────────────────────┐
    │  ✅ Ready to Merge           │
    │  All checks passed           │
    └────────┬─────────────────────┘
             │
             ▼
    ┌──────────────────┐
    │  Merge PR        │
    │  → main branch   │
    └────────┬─────────┘
             │
             ▼
    ┌──────────────────────────────────────┐
    │  CI runs again on main branch        │
    │  (post-merge validation)             │
    └────────┬─────────────────────────────┘
             │
             ▼
    ┌──────────────────┐
    │  ✓ Code on main  │
    │  Fully validated │
    └──────────────────┘
```

## Three Layers of Protection

### Layer 1: Pre-commit Hooks (Local, Optional)

- **When**: Before every commit
- **Speed**: Fast (local, cached)
- **Auto-fix**: Yes (ruff, formatting)
- **Can skip**: Yes (`git commit --no-verify`)
- **Purpose**: Immediate feedback, catch issues early

### Layer 2: Pre-push Hook (Local, Optional)

- **When**: Before every push
- **Speed**: Medium (runs full tests)
- **Auto-fix**: No
- **Can skip**: Yes (`git push --no-verify`)
- **Purpose**: Validate all tests pass before pushing

### Layer 3: GitHub Actions CI (Remote, Mandatory)

- **When**: On PR to main, push to main
- **Speed**: Slower (cold start)
- **Auto-fix**: No
- **Can skip**: No (enforced)
- **Purpose**: Final quality gate before merge

## Recommended Setup

```bash
# Enable all three layers for maximum quality:

# 1. Install pre-commit hooks (Layer 1 & 2)
pip install -r requirements.txt
pre-commit install
pre-commit install --hook-type pre-push

# 2. GitHub Actions CI is already configured (Layer 3)
#    Just push to GitHub and it runs automatically on PRs to main
```

## Time Investment vs. Savings

```text
Time Spent                          Time Saved
──────────────────────────────────────────────────────────
Setup (one-time): 2 min            ↓

Per commit (pre-commit): 5-10 sec  → Catch formatting/lint issues early
                                   → No manual formatting needed
                                   → Fix issues in seconds, not minutes

Per push (pre-push): 1-5 sec       → Catch test failures before CI
                                   → No waiting for CI to fail
                                   → Save 2-5 min per failed CI run

Per PR (CI): 2-3 min               → Final validation
                                   → Prevent bad code reaching main
                                   → Save hours debugging production issues

TOTAL: 2 min setup + 15 sec/commit → SAVES: Hours per week
```

## Workflow Optimization Tips

### Fast Iteration During Development

```bash
# Option 1: Skip quick test during commit, run on push
SKIP=pytest-quick git commit -m "WIP"
git push  # Full tests run here

# Option 2: Disable hooks temporarily
git commit --no-verify -m "WIP: testing"
# Re-enable before creating PR!

# Option 3: Run hooks manually when ready
git commit -m "WIP" --no-verify
# ... more work ...
pre-commit run --all-files  # Run all checks manually
```

### Before Creating PR

```bash
# Ensure everything passes
pre-commit run --all-files

# Run full test suite
pytest tb/tests/ -v

# Create PR with confidence
gh pr create --base main --title "Add feature"
```

### Emergency Hotfix

```bash
# Make critical fix
vim tb/models/critical_fix.py

# Commit (hooks run, ensure quality)
git add .
git commit -m "Fix critical bug"

# Push directly to main (if you have permission)
git push origin main
# CI validates post-merge
```

## See Also

- `QUICKSTART_PRECOMMIT.md` - Quick setup guide
- `.github/PRE_COMMIT_SETUP.md` - Detailed pre-commit docs
- `.github/CI_SETUP.md` - CI workflow documentation
- `.github/WORKFLOW_TRIGGERS.md` - When CI runs
