# GitHub Actions Badges

Replace `USERNAME/REPO` with your actual GitHub username and repository name.

## Badge Markdown

### QA Checks Badge

```markdown
[![QA Checks](https://github.com/USERNAME/REPO/actions/workflows/qa-checks.yml/badge.svg)](https://github.com/USERNAME/REPO/actions/workflows/qa-checks.yml)
```

### Tests Badge

```markdown
[![Tests](https://github.com/USERNAME/REPO/actions/workflows/tests.yml/badge.svg)](https://github.com/USERNAME/REPO/actions/workflows/tests.yml)
```

### Code Coverage Badge (if using Codecov)

```markdown
[![codecov](https://codecov.io/gh/USERNAME/REPO/branch/main/graph/badge.svg)](https://codecov.io/gh/USERNAME/REPO)
```

## Example Combined Badges

```markdown
[![QA Checks](https://github.com/USERNAME/REPO/actions/workflows/qa-checks.yml/badge.svg)](https://github.com/USERNAME/REPO/actions/workflows/qa-checks.yml)
[![Tests](https://github.com/USERNAME/REPO/actions/workflows/tests.yml/badge.svg)](https://github.com/USERNAME/REPO/actions/workflows/tests.yml)
[![codecov](https://codecov.io/gh/USERNAME/REPO/branch/main/graph/badge.svg)](https://codecov.io/gh/USERNAME/REPO)
```

## Workflow Details

### `qa-checks.yml`

- Runs on: Python 3.11 and 3.12
- Checks:
  - ruff format --check
  - ruff check
  - mypy type checking
  - pylint
  - pytest with coverage
- Uploads coverage to Codecov (Python 3.12 only)

### `tests.yml`

- Runs on: Python 3.12
- Lightweight workflow that only runs pytest
- Triggers only on changes to Python files or test configuration
