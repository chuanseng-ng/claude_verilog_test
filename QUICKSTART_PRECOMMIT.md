# Pre-commit Hooks - Quick Start

Automatically run QA checks before every commit to catch issues early!

## Installation (One-Time Setup)

```bash
# 1. Install dependencies (includes pre-commit)
pip install -r requirements-dev.txt

# 2. Install git hooks
pre-commit install
pre-commit install --hook-type pre-push

# 3. Done! Hooks will now run automatically
```

## What You Get

### On Every Commit ✓

- Auto-fix code formatting (ruff format)
- Auto-fix linting issues (ruff lint)
- Type checking (mypy)
- Code quality checks (pylint)
- Quick test smoke test

### On Every Push ✓

- Full test suite (pytest)

## Usage

Just commit normally - hooks run automatically:

```bash
git add .
git commit -m "Add new feature"

# Hooks run automatically here ⚡
# If all pass → commit succeeds
# If any fail → fix issues and try again
```

## Example Workflow

```bash
# Make changes
vim tb/models/my_model.py

# Stage changes
git add tb/models/my_model.py

# Commit (hooks run automatically)
git commit -m "Add new model"

✓ Trim trailing whitespace........................Passed
✓ Fix end of files..................................Passed
✓ Check YAML........................................Passed
✓ Check for large files.............................Passed
✓ ruff lint (auto-fix)..............................Passed
✓ ruff format.......................................Passed
✓ mypy type checking................................Passed
✓ pylint (code quality).............................Passed
✓ pytest (quick check)..............................Passed

[main abc1234] Add new model
 1 file changed, 10 insertions(+)
```

## If a Hook Fails

Hooks will auto-fix when possible:

```bash
git commit -m "Add feature"

ruff format.........................................Failed
- hook id: ruff-format
- files were modified by this hook

# Files were auto-formatted!
# Just stage the changes and commit again:

git add .
git commit -m "Add feature"
# ✓ Now it passes!
```

If manual fixes are needed:

```bash
git commit -m "Add feature"

pylint (code quality)...............................Failed
- hook id: pylint
- exit code: 1

tb/models/my_model.py:42:0: C0116: Missing function docstring

# Fix the issue
vim tb/models/my_model.py  # Add docstring

# Stage and commit again
git add tb/models/my_model.py
git commit -m "Add feature"
# ✓ Passes!
```

## Manual Hook Execution

Run all hooks without committing:

```bash
# Run on all files
pre-commit run --all-files

# Run on staged files only
pre-commit run

# Run specific hook
pre-commit run ruff --all-files
pre-commit run pytest-check --hook-stage push
```

## Skipping Hooks (Emergency Only)

```bash
# Skip all hooks (not recommended!)
git commit --no-verify -m "Emergency fix"

# Skip specific hook
SKIP=pytest-quick git commit -m "Skip test"
```

⚠️ **Warning**: Skipped hooks may cause CI failures!

## Benefits

- ✅ **Catch issues early** - Before they reach CI
- ✅ **Auto-fix formatting** - No manual formatting needed
- ✅ **Save time** - Fix issues locally instead of in CI
- ✅ **Consistent quality** - Every commit meets standards
- ✅ **Faster PRs** - CI passes on first try

## Comparison: Local vs CI

| Check | Pre-commit Hooks | GitHub CI |
| :---: | :--------------: | :-------: |
| **When** | Every commit/push (local) | PR to main only |
| **Speed** | Fast (cached) | Slower (cold start) |
| **Auto-fix** | Yes | No |
| **Can skip** | Yes (--no-verify) | No |
| **Purpose** | Early feedback | Final quality gate |

**Recommendation**: Use both for best results!

## Uninstalling

To remove hooks:

```bash
pre-commit uninstall
pre-commit uninstall --hook-type pre-push
```

## Troubleshooting

### "pre-commit: command not found"

```bash
pip install pre-commit
```

### "pylint: command not found"

```bash
pip install -r requirements-dev.txt
```

### Hooks are too slow

First run is slower (sets up cache). Subsequent runs are fast.

To skip tests during commit:

```bash
SKIP=pytest-quick git commit -m "Fast commit"
# Tests still run on push
```

## Full Documentation

See `.github/PRE_COMMIT_SETUP.md` for complete documentation.

## Summary

**Install once:**

```bash
pip install -r requirements-dev.txt
pre-commit install
pre-commit install --hook-type pre-push
```

**Benefit forever:**

- Auto-formatting
- Auto-linting
- Type checking
- Code quality
- Test validation

**Happy coding!** 🚀
