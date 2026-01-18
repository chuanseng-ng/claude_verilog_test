# CI/CD Setup Guide

This document explains the GitHub Actions CI setup for this project.

## Overview

Two GitHub Actions workflows have been configured:

1. **QA Checks** (`qa-checks.yml`) - Comprehensive quality checks
2. **Tests** (`tests.yml`) - Fast test execution only

## QA Checks Workflow

**File**: `.github/workflows/qa-checks.yml`

**Triggers**:

- Push to `main` branch
- Pull requests targeting `main` branch
- Manual workflow dispatch

**Matrix**:

- Python versions: 3.11, 3.12

**Steps**:
1. **Ruff Format Check** - Verifies code formatting

   ```bash
   ruff format --check tb/models tb/tests
   ```

2. **Ruff Linter** - Checks for code quality issues

   ```bash
   ruff check tb/models tb/tests
   ```

3. **MyPy Type Checking** - Validates type hints

   ```bash
   mypy tb/models tb/tests
   ```

4. **Pylint** - Additional code quality analysis

   ```bash
   pylint tb/models tb/tests
   ```

5. **Pytest** - Runs test suite with coverage

   ```bash
   pytest tb/tests/ -v --cov=tb.models --cov-report=term-missing --cov-report=xml
   ```

6. **Coverage Upload** - Uploads to Codecov (Python 3.12 only)

## Tests Workflow

**File**: `.github/workflows/tests.yml`

**Triggers**:

- Push to `main` branch (only when Python files change)
- Pull requests targeting `main` (only when Python files change)
- Manual workflow dispatch

**Python Version**: 3.12 only

**Steps**:

1. **Run Tests** - Fast test execution without coverage

   ```bash
   pytest tb/tests/ -v --tb=short
   ```

## Local Development

### Install Dependencies

```bash
pip install -r requirements-dev.txt
```

### Run QA Checks Locally

```bash
# Format check
ruff format --check tb/models tb/tests

# Linting
ruff check tb/models tb/tests

# Type checking
mypy tb/models tb/tests

# Code quality
pylint tb/models tb/tests

# Tests with coverage
pytest tb/tests/ -v --cov=tb.models --cov-report=term-missing
```

### Auto-fix Issues

```bash
# Auto-format code
ruff format tb/models tb/tests

# Auto-fix linting issues
ruff check --fix tb/models tb/tests
```

## Dependencies

All QA tools and testing dependencies are listed in `requirements-dev.txt`:

- `pytest` - Testing framework
- `pytest-cov` - Coverage plugin
- `mypy` - Static type checker
- `pylint` - Code quality checker
- `ruff` - Fast Python linter and formatter

## CI Badge Status

Add these badges to your README.md (replace USERNAME/REPO):

```markdown
[![QA Checks](https://github.com/USERNAME/REPO/actions/workflows/qa-checks.yml/badge.svg)](https://github.com/USERNAME/REPO/actions/workflows/qa-checks.yml)
[![Tests](https://github.com/USERNAME/REPO/actions/workflows/tests.yml/badge.svg)](https://github.com/USERNAME/REPO/actions/workflows/tests.yml)
```

See `.github/BADGES.md` for more badge options.

## Troubleshooting

### Workflow Fails on First Run

The first time you push, you may need to:

1. Go to repository Settings → Actions → General
2. Set "Workflow permissions" to "Read and write permissions"
3. Re-run the failed workflow

### Coverage Upload Fails

If Codecov upload fails:

- This is expected if you haven't set up Codecov yet
- The workflow has `fail_ci_if_error: false` so it won't block CI
- To enable: Sign up at https://codecov.io and link your repository

### Python Version Not Available

If a Python version is unavailable on GitHub runners:

- Update the matrix in `qa-checks.yml` to use available versions
- Check https://github.com/actions/python-versions/releases for supported versions

## Configuration Files

- `.github/workflows/qa-checks.yml` - Main QA workflow
- `.github/workflows/tests.yml` - Fast test workflow
- `requirements-dev.txt` - Development dependencies
- `.github/BADGES.md` - Badge reference
- `.github/CI_SETUP.md` - This file

## Future Enhancements

Possible additions to consider:

1. **Pre-commit hooks** - Run checks before commits
2. **Coverage enforcement** - Fail if coverage drops below threshold
3. **Dependency caching** - Speed up CI with pip caching (already enabled)
4. **Matrix expansion** - Test on Windows/macOS runners
5. **Scheduled runs** - Weekly dependency security checks
