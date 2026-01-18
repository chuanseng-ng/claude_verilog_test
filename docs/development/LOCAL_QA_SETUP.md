# Local QA Setup Guide

Complete guide to setting up quality assurance tools for local development.

## Quick Start

```bash
# 1. Install all dependencies
pip install -r requirements.txt

# 2. Install pre-commit hooks (recommended)
pre-commit install
pre-commit install --hook-type pre-push

# 3. Start coding - hooks run automatically!
```

## What Gets Checked

### Automatically (Pre-commit Hooks)

When you run `git commit`, these checks run automatically:

1. **Basic Checks**
   - Trim trailing whitespace
   - Fix end of files
   - Check YAML syntax
   - Check for large files
   - Check for merge conflicts

2. **Ruff Linter** (with auto-fix)
   - Finds and fixes code quality issues
   - Removes unused imports
   - Fixes common Python mistakes

3. **Ruff Formatter**
   - Auto-formats code to consistent style
   - No manual formatting needed

4. **MyPy Type Checker**
   - Validates type hints
   - Catches type-related bugs

5. **Pylint Code Quality**
   - Enforces coding standards
   - Requires score ≥9.5/10

6. **Pytest Quick Test**
   - Runs smoke tests
   - Fast validation

When you run `git push`, full tests run:

7. **Pytest Full Suite**
   - Runs all tests
   - Ensures nothing is broken

### Manually (CI on GitHub)

When you create a PR to main, GitHub Actions runs:

- All of the above on Python 3.11 and 3.12
- Generates coverage reports
- Uploads coverage to Codecov

## Running Checks Manually

### All Checks

```bash
# Run everything pre-commit would run
pre-commit run --all-files
```

### Individual Checks

```bash
# Format code
ruff format tb/models tb/tests

# Check formatting
ruff format --check tb/models tb/tests

# Lint code
ruff check tb/models tb/tests

# Lint with auto-fix
ruff check --fix tb/models tb/tests

# Type check
mypy tb/models tb/tests

# Code quality
pylint tb/models tb/tests

# Tests
pytest tb/tests/ -v

# Tests with coverage
pytest tb/tests/ -v --cov=tb.models --cov-report=html
# Open htmlcov/index.html to view coverage
```

### Quick Test During Development

```bash
# Run only last failed tests
pytest tb/tests/ --lf -v

# Run only tests matching a pattern
pytest tb/tests/ -k "test_gpu" -v

# Stop at first failure
pytest tb/tests/ -x -v

# Run specific test file
pytest tb/tests/test_rv32i_model.py -v
```

## Development Workflow

### Recommended Workflow

```bash
# 1. Create feature branch
git checkout -b feature/my-feature

# 2. Make changes
vim tb/models/my_model.py

# 3. Run quick check
ruff check --fix tb/models/
pytest tb/tests/test_my_model.py -v

# 4. Commit (hooks run automatically)
git add .
git commit -m "Add my feature"

# 5. Push (full tests run)
git push origin feature/my-feature

# 6. Create PR to main
gh pr create --base main --title "Add my feature"

# 7. CI runs automatically, merge when green!
```

### Fast Iteration Workflow

During rapid development, you might want to skip some checks:

```bash
# Skip quick test during commit
SKIP=pytest-quick git commit -m "WIP: still testing"

# Skip all hooks (use sparingly!)
git commit --no-verify -m "WIP"

# Before creating PR, run all checks
pre-commit run --all-files
pytest tb/tests/ -v
```

## Configuration Files

- `.pre-commit-config.yaml` - Pre-commit hook configuration
- `.pylintrc` - Pylint settings
- `requirements.txt` - Development dependencies
- `.github/workflows/qa-checks.yml` - CI workflow
- `.github/workflows/tests.yml` - Test workflow

## IDE Integration

### VSCode

Install extensions:

- Python (Microsoft)
- Pylint
- Mypy Type Checker
- Ruff

Settings (`.vscode/settings.json`):

```json
{
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.fixAll": true,
      "source.organizeImports": true
    }
  },
  "python.linting.enabled": true,
  "python.linting.pylintEnabled": true,
  "python.testing.pytestEnabled": true
}
```

### PyCharm

1. Go to Settings → Tools → External Tools
2. Add tools for ruff, mypy, pylint
3. Enable "Run on save" for ruff format
4. Configure pytest as test runner

## Troubleshooting

### Pre-commit is slow

First run downloads and caches tools. Subsequent runs are fast.

If still slow, skip heavy checks during commit:

```bash
SKIP=pytest-quick,pylint git commit -m "Fast commit"
```

### Import errors in MyPy

MyPy is configured with `--ignore-missing-imports` for external packages.

For project imports, ensure proper module structure:

```python
# tb/__init__.py should exist
# tb/models/__init__.py should exist
# tb/tests/__init__.py should exist
```

### Pylint score too low

Check `.pylintrc` for disabled checks and thresholds.

Current threshold: 9.5/10

Acceptable reasons for lower score:

- Complex instruction execution logic (inherent)
- Many function parameters (instruction fields)

Fix common issues:

```bash
# See detailed report
pylint tb/models/my_model.py

# Common fixes:
# - Add docstrings
# - Break up long functions
# - Use constants for magic numbers
```

### Tests failing locally but pass in CI

Ensure same dependencies:

```bash
pip install -r requirements.txt --upgrade
```

Check Python version:

```bash
python --version
# Should be 3.11 or 3.12
```

## Coverage Reports

### Generate HTML Coverage Report

```bash
pytest tb/tests/ --cov=tb.models --cov-report=html
# Open htmlcov/index.html in browser
```

### Check Coverage Percentage

```bash
pytest tb/tests/ --cov=tb.models --cov-report=term-missing
# Shows coverage % and missing lines
```

### Coverage on Specific Module

```bash
pytest tb/tests/ --cov=tb.models.rv32i_model --cov-report=term
```

## Performance Tips

### Speed Up Tests

```bash
# Run tests in parallel (requires pytest-xdist)
pip install pytest-xdist
pytest tb/tests/ -n auto

# Run only changed tests
pytest tb/tests/ --lf

# Skip slow tests
pytest tb/tests/ -m "not slow"
```

### Speed Up Pre-commit

```bash
# Update to latest versions (may be faster)
pre-commit autoupdate

# Clean cache and rebuild
pre-commit clean
pre-commit gc
```

## See Also

- `../QUICKSTART_PRECOMMIT.md` - Quick pre-commit setup
- `.github/PRE_COMMIT_SETUP.md` - Detailed pre-commit guide
- `.github/CI_SETUP.md` - CI/CD documentation
- `.github/QA_WORKFLOW_DIAGRAM.md` - Visual workflow
- `.github/WORKFLOW_TRIGGERS.md` - When CI runs

## Getting Help

- Pre-commit: https://pre-commit.com/
- Ruff: https://docs.astral.sh/ruff/
- MyPy: https://mypy.readthedocs.io/
- Pylint: https://pylint.pycqa.org/
- Pytest: https://docs.pytest.org/
