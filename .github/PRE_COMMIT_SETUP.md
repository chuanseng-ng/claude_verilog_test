# Pre-commit Hooks Setup Guide

This guide explains how to set up and use pre-commit hooks to automatically run QA checks before committing code.

## What Are Pre-commit Hooks?

Pre-commit hooks are scripts that run automatically before you commit code. They:
- ✅ Catch issues early, before they reach CI
- ✅ Auto-fix formatting and simple linting issues
- ✅ Save time by preventing failed CI builds
- ✅ Ensure consistent code quality across all commits

## Installation

### Step 1: Install pre-commit

```bash
pip install pre-commit
```

### Step 2: Install the hooks

```bash
# From the project root directory
pre-commit install

# Also install for git push (runs tests before push)
pre-commit install --hook-type pre-push
```

You should see:
```
pre-commit installed at .git/hooks/pre-commit
pre-commit installed at .git/hooks/pre-push
```

### Step 3: Verify installation

```bash
pre-commit --version
```

## What Hooks Are Configured?

The `.pre-commit-config.yaml` file configures these checks:

### On Every Commit

1. **Basic Git Checks**
   - Trim trailing whitespace
   - Fix end of files
   - Check YAML syntax
   - Check for large files (>500KB)
   - Check for merge conflicts
   - Check line endings

2. **Ruff Linter** (with auto-fix)
   - Finds and fixes code quality issues
   - Only runs on `tb/models/` and `tb/tests/`

3. **Ruff Formatter**
   - Auto-formats Python code
   - Ensures consistent style

4. **MyPy Type Checking**
   - Validates type hints
   - Catches type errors early

5. **Pylint Code Quality**
   - Additional code quality checks
   - Must score ≥9.5/10
   - Only runs on `tb/models/` and `tb/tests/`

6. **Pytest Quick Check**
   - Runs last failed tests OR initialization tests
   - Fast smoke test
   - Stops at first failure

### On Git Push Only

7. **Pytest Full Test Suite**
   - Runs all tests before pushing
   - Stops at first failure
   - Ensures you don't push broken code

## Usage

### Normal Workflow

Just commit as usual - hooks run automatically:

```bash
git add tb/models/my_model.py
git commit -m "Add new model"

# Hooks run automatically:
# ✓ Trimming whitespace...
# ✓ Fixing end of files...
# ✓ Ruff lint (auto-fix)...
# ✓ Ruff format...
# ✓ MyPy type checking...
# ✓ Pylint (code quality)...
# ✓ Pytest (quick check)...
#
# If all pass: Commit succeeds!
# If any fail: Commit is blocked, fix issues and try again
```

### When Hooks Fail

If a hook fails, you'll see the error output:

```bash
git commit -m "Add feature"

Ruff lint (auto-fix)................................Failed
- hook id: ruff
- exit code: 1

tb/models/my_model.py:10:5: F841 Local variable `x` is assigned to but never used

# Fix the issue
vim tb/models/my_model.py

# Stage the fixes
git add tb/models/my_model.py

# Try again
git commit -m "Add feature"
# ✓ All hooks pass!
```

### Auto-fixes

Some hooks (ruff, ruff-format) auto-fix issues:

```bash
git add tb/models/my_model.py
git commit -m "Add feature"

Ruff format.........................................Failed
- hook id: ruff-format
- files were modified by this hook

# Files were automatically formatted!
# Just stage the changes and commit again

git add tb/models/my_model.py
git commit -m "Add feature"
# ✓ Now it passes!
```

### Skipping Hooks (Not Recommended)

In rare cases, you can skip hooks:

```bash
# Skip all hooks (use sparingly!)
git commit --no-verify -m "Emergency fix"

# Or set SKIP environment variable
SKIP=pylint git commit -m "Skip only pylint"
```

⚠️ **Warning**: Skipping hooks means your code may fail CI!

## Running Hooks Manually

### Run all hooks on all files

```bash
pre-commit run --all-files
```

### Run specific hook

```bash
# Run only ruff
pre-commit run ruff --all-files

# Run only mypy
pre-commit run mypy --all-files

# Run only tests
pre-commit run pytest-check --hook-stage push --all-files
```

### Run hooks on specific files

```bash
pre-commit run --files tb/models/rv32i_model.py
```

## Updating Hooks

Pre-commit hooks are versioned. To update to latest versions:

```bash
# Update to latest versions
pre-commit autoupdate

# This updates .pre-commit-config.yaml with latest versions
```

## Uninstalling

To remove pre-commit hooks:

```bash
# Remove hooks
pre-commit uninstall
pre-commit uninstall --hook-type pre-push

# Hooks are removed from .git/hooks/
```

## Troubleshooting

### "pre-commit: command not found"

```bash
# Make sure pre-commit is installed
pip install pre-commit

# Or install in a virtualenv
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install pre-commit
```

### "pylint: command not found" or "pytest: command not found"

Install development dependencies:

```bash
pip install -r requirements-dev.txt
```

### Hooks are slow

The first run is slower because tools cache data. Subsequent runs are much faster.

To skip slow hooks during commit:

```bash
# Skip tests during commit (they still run on push)
SKIP=pytest-quick git commit -m "Fast commit"
```

### MyPy fails with import errors

This is expected for external dependencies. The hook has `--ignore-missing-imports` configured.

If it's a project import, ensure the module is properly structured.

## Configuration Files

- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `.pylintrc` - Pylint settings (fail threshold, disabled checks)
- `requirements-dev.txt` - Development dependencies

## Comparison: Pre-commit vs CI

| Aspect | Pre-commit Hooks | GitHub Actions CI |
|--------|------------------|-------------------|
| **When** | Before every commit/push | On PR to main |
| **Speed** | Fast (local, cached) | Slower (cold start) |
| **Scope** | Changed files only | All files |
| **Required** | Optional (can skip) | Mandatory (blocks merge) |
| **Purpose** | Early feedback | Quality gate |

**Best Practice**: Use both!
- Pre-commit hooks: Catch issues early during development
- CI: Final quality gate before merging to main

## Advanced Configuration

### Run hooks on specific file patterns

Edit `.pre-commit-config.yaml`:

```yaml
- id: pylint
  files: ^tb/models/.*\.py$  # Only model files
  exclude: ^tb/tests/  # Exclude tests
```

### Change hook stages

```yaml
- id: mypy
  stages: [commit, push]  # Run on both commit and push
```

### Add custom hooks

```yaml
- repo: local
  hooks:
    - id: my-custom-check
      name: My custom check
      entry: python scripts/my_check.py
      language: system
      files: \.py$
```

## Summary

Pre-commit hooks provide:
- ✅ Immediate feedback during development
- ✅ Auto-fix common issues (formatting, imports)
- ✅ Prevent committing broken code
- ✅ Reduce CI failures
- ✅ Consistent code quality

Install once, benefit forever:
```bash
pip install pre-commit
pre-commit install
pre-commit install --hook-type pre-push
```

## See Also

- [Pre-commit Official Documentation](https://pre-commit.com/)
- `.github/CI_SETUP.md` - CI/CD setup
- `.github/WORKFLOW_TRIGGERS.md` - When CI runs
- `.pylintrc` - Pylint configuration
