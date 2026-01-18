# Workflow Trigger Summary

This document explains when each GitHub Actions workflow will run.

## Trigger Configuration

Both workflows now **only run for the main branch**:

### QA Checks Workflow (`qa-checks.yml`)

**✅ Will Run:**

- When code is pushed to `main` branch
- When a pull request targets `main` branch
- When manually triggered via GitHub UI

**❌ Will NOT Run:**

- Push to feature branches (e.g., `feature/new-feature`)
- Pull requests to other branches (e.g., PR from `feature-a` → `feature-b`)
- Push to any branch other than `main`

### Tests Workflow (`tests.yml`)

**✅ Will Run:**

- When code is pushed to `main` branch AND Python files changed
- When a pull request targets `main` branch AND Python files changed
- When manually triggered via GitHub UI

**❌ Will NOT Run:**

- Push to feature branches
- Pull requests to other branches
- Changes that don't affect Python files (e.g., only docs updated)

## Workflow Diagram

```text
Feature Branch                Main Branch
     │                             │
     │                             │
     ├─ Push to feature      ✅ Push to main
     │  ❌ No CI runs            → QA Checks + Tests run
     │                             │
     ├─ PR: feature → main   ✅ PR targeting main
     │  ✅ CI runs!               → QA Checks + Tests run
     │                             │
     ├─ PR: feature → other  ❌ PR targeting other branch
     │  ❌ No CI runs            → No CI runs
     │                             │
```

## Common Scenarios

### Scenario 1: Working on a Feature Branch

```bash
# You're on feature/add-gpu-model
git checkout -b feature/add-gpu-model
git add .
git commit -m "Add GPU model"
git push origin feature/add-gpu-model

# ❌ CI does NOT run (not targeting main)
```

### Scenario 2: Creating a Pull Request to Main

```bash
# Create PR: feature/add-gpu-model → main
# Using GitHub UI or gh CLI

# ✅ CI RUNS! Both qa-checks and tests workflows execute
# Must pass before merging to main
```

### Scenario 3: Merging to Main

```bash
# After PR is approved and merged
# Merge button clicked on GitHub

# ✅ CI RUNS! Post-merge validation on main branch
```

### Scenario 4: Manual Trigger

```bash
# On GitHub:
# Actions → Select workflow → Run workflow → Select branch

# ✅ CI RUNS! Can run on any branch when manually triggered
```

## Why This Configuration?

This setup ensures:

1. **Protected Main Branch**: Only code that passes QA checks can be merged to `main`
2. **Reduced CI Usage**: Doesn't waste CI minutes on feature branch development
3. **Fast Iteration**: Developers can push to feature branches frequently without waiting for CI
4. **Quality Gate**: Every PR to `main` must pass all checks
5. **Manual Override**: Can still run CI on any branch via manual trigger

## Path Filtering (Tests Workflow Only)

The `tests.yml` workflow only runs when these files change:

- `tb/**/*.py` - Any Python file in tb/ directory
- `requirements.txt` - Development dependencies
- `.github/workflows/tests.yml` - The workflow itself

This means:

- ✅ Python code changes → Tests run
- ❌ Documentation changes → Tests skipped
- ❌ RTL changes (*.sv, *.v) → Tests skipped
- ✅ Test infrastructure changes → Tests run

## Development Workflow Recommendation

### Option A: Always Use PRs (Recommended)

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Develop and commit
git add .
git commit -m "Implement feature"
git push origin feature/my-feature

# 3. Create PR to main
gh pr create --base main --title "Add my feature"

# 4. CI runs automatically
# 5. Review, fix any issues, merge
```

### Option B: Local QA Before PR

```bash
# 1. Run QA locally before creating PR
ruff format --check tb/models tb/tests
ruff check tb/models tb/tests
mypy tb/models tb/tests
pylint tb/models tb/tests
pytest tb/tests/ -v

# 2. Fix any issues locally
# 3. Then create PR with confidence CI will pass
```

### Option C: Pre-commit Hooks

```bash
# Install pre-commit hooks (one-time setup)
pip install pre-commit
pre-commit install

# Now checks run automatically before each commit
git add .
git commit -m "Add feature"
# → Pre-commit hooks run automatically
# → If they pass, commit succeeds
# → If they fail, fix issues and try again
```

## Modifying Trigger Behavior

### To run CI on all branches

```yaml
on:
  push:
    branches: [ "**" ]  # All branches
  pull_request:
    branches: [ "**" ]  # All PRs
```

### To run CI only on specific branches

```yaml
on:
  push:
    branches: [ "main", "develop", "release/*" ]
  pull_request:
    branches: [ "main", "develop" ]
```

### To run CI on all PRs but push to main only

```yaml
on:
  push:
    branches: [ "main" ]
  pull_request:
    branches: [ "**" ]
```

## See Also

- `.github/CI_SETUP.md` - Complete CI setup documentation
- `.github/workflows/qa-checks.yml` - QA workflow file
- `.github/workflows/tests.yml` - Tests workflow file
