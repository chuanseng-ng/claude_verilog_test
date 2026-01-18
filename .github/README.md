# GitHub Configuration

This directory contains GitHub-specific configuration files for CI/CD and project automation.

## Files

### Workflows

- `workflows/qa-checks.yml` - Comprehensive QA checks (ruff, mypy, pylint, pytest)
- `workflows/tests.yml` - Fast test-only workflow

### Documentation

- `BADGES.md` - GitHub Actions badge reference
- `CI_SETUP.md` - Complete CI/CD setup guide

## Quick Start

### For Repository Owners

1. Push these files to GitHub
2. Workflows will run automatically on push/PR
3. Update badge URLs in `README.md` with your username/repo
4. (Optional) Set up Codecov for coverage tracking

### For Contributors

1. Install dev dependencies: `pip install -r requirements-dev.txt`
2. Run QA checks locally before pushing (see `CI_SETUP.md`)
3. (Optional) Install pre-commit hooks: `pip install pre-commit && pre-commit install`

## Workflow Status

Once pushed to GitHub, view workflow runs at:

- https://github.com/USERNAME/REPO/actions

Replace USERNAME/REPO with your actual repository.

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Workflow Syntax Reference](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
