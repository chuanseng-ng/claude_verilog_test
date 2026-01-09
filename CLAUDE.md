# CLAUDE.md - AI Assistant Guide for Bouldering Route Analysis

**Version**: 2026.01
**Last Updated**: 2026-01-05
**Last Reviewed**: 2026-01-05
**Review Cadence**: Quarterly (every 3 months)
**Repository**: bouldering-analysis
**Purpose**: Guide AI assistants working with this computer vision-based bouldering route grading application

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Codebase Structure](#codebase-structure)
3. [Technology Stack](#technology-stack)
4. [Development Workflows](#development-workflows)
5. [Code Conventions](#code-conventions)
6. [Testing Requirements](#testing-requirements)
7. [Database Schema](#database-schema)
8. [Common Tasks](#common-tasks)
9. [Configuration Management](#configuration-management)
10. [Quality Standards](#quality-standards)

---

## Project Overview

### What This Application Does

This is a Flask-based web application that uses YOLOv8 computer vision to analyze bouldering route images and predict difficulty grades. The system:

- Detects climbing holds in uploaded images using fine-tuned YOLOv8 models
- Classifies holds into 8 types (crimp, jug, sloper, pinch, pocket, foot-hold, start-hold, top-out-hold)
- Predicts bouldering route grades based on hold distribution and features
- Stores analysis results and user feedback in a relational database
- Manages ML model versions and training pipelines

### Key Technologies

- **Backend**: Flask 3.1.2 with SQLAlchemy 2.0.44
- **ML/CV**: PyTorch 2.9.1 + Ultralytics YOLOv8 8.3.233
- **Database**: SQLite (dev) / PostgreSQL (prod)
- **Testing**: pytest 9.0.1 with 99%+ coverage requirement
- **Quality**: mypy, ruff, pylint (9.9/10 minimum score)

---

## Codebase Structure

### Directory Layout

```text
bouldering-analysis/
├── src/                          # Main application code (~2,921 lines)
│   ├── cfg/                      # Configuration files
│   │   └── user_config.yaml      # App settings (model paths, thresholds)
│   ├── templates/                # HTML templates
│   │   └── index.html            # Web UI
│   ├── main.py                   # Flask app + routes (775 lines)
│   ├── config.py                 # Configuration loader with caching (323 lines)
│   ├── models.py                 # SQLAlchemy ORM models (265 lines)
│   ├── constants.py              # Shared constants (HOLD_TYPES)
│   ├── train_model.py            # YOLOv8 fine-tuning pipeline (752 lines)
│   ├── manage_models.py          # Model version management CLI (630 lines)
│   ├── setup.py                  # Database + directory initialization
│   └── setup_dev.py              # Dev environment setup script
│
├── tests/                        # Test suite (~4,567 lines)
│   ├── conftest.py               # pytest fixtures and configuration
│   ├── test_main.py              # Flask app + route tests
│   ├── test_config.py            # Configuration tests
│   ├── test_models.py            # Database model tests
│   ├── test_train_model.py       # Training pipeline tests
│   └── ...                       # Additional test modules
│
├── scripts/                      # Utility scripts
│   └── migrations/               # Database migration scripts
│
├── data/                         # Data directory
│   └── sample_hold/              # Sample YOLO dataset
│       └── data.yaml             # Dataset configuration
│
├── docs/                         # Documentation
│   ├── migrations.md             # Database migration guide
│   ├── week3-4_implementation.md # Implementation details
│   └── week3-4_validation.md     # Validation documentation
│
├── .github/workflows/            # CI/CD pipelines
│   ├── pylint.yml                # Main QA pipeline (mypy, ruff, pytest, pylint)
│   ├── python-code-cov.yml       # Coverage + testing
│   └── python-package-conda.yml  # Conda package build
│
├── run.sh                        # Start Flask dev server
├── run_setup_dev.sh              # Initialize dev environment
├── run_qa.csh                    # Comprehensive QA automation
├── requirements.txt              # Pip dependencies (pinned versions)
├── environment.yml               # Conda environment spec
├── pyproject.toml                # Test coverage config
├── mypy.ini                      # Type checking config
├── .pylintrc                     # Pylint config
└── .flake8                       # Flake8 config
```

### Critical Files to Know

| File | Purpose | Lines | Key Info |
| ------ | --------- | ------- | ---------- |
| `src/main.py` | Flask app + routes | 775 | Main entry point, all API endpoints |
| `src/models.py` | Database models | 265 | 6 SQLAlchemy models (Analysis, Feedback, HoldType, etc.) |
| `src/config.py` | Config management | 323 | Thread-safe YAML config loading |
| `src/train_model.py` | ML training pipeline | 752 | YOLOv8 fine-tuning, versioning |
| `src/manage_models.py` | Model version mgmt | 630 | CLI for model activation/deactivation |
| `tests/conftest.py` | pytest fixtures | - | 20+ fixtures for isolated testing |
| `run_qa.csh` | QA automation | 101 | Runs mypy, ruff, pytest, pylint |

---

## Technology Stack

### Core Dependencies

#### Web Framework

- **Flask 3.1.2** - Main web framework
- **Flask-SQLAlchemy 3.1.1** - ORM integration
- **Flask-RESTX 1.3.2** - REST API extensions
- **Werkzeug ProxyFix** - Reverse proxy support

#### Machine Learning & Computer Vision

- **PyTorch 2.9.1** - Deep learning framework
- **Torchvision 0.24.1** - CV models and transforms
- **Ultralytics 8.3.233** - YOLOv8 for hold detection
- **Pillow 10.4.0** - Image processing
- **OpenCV 4.12.0.88** - Image analysis

#### Database

- **SQLAlchemy 2.0.44** - ORM (core dependency)
- **psycopg2-binary 2.9.11** - PostgreSQL adapter
- **SQLite** - Default database for development

#### Data & Configuration

- **PyYAML 6.0.2** - YAML parsing for configs
- **NumPy 2.2.6** - Numerical computing
- **DVC 3.64.0** - Data version control

#### Development & Testing

- **pytest 9.0.1** - Testing framework
- **pytest-cov 7.0.0** - Coverage measurement (99% required)
- **ruff 0.14.7** - Fast linter + formatter
- **pylint 4.0.3** - Code quality (9.9/10 required)
- **mypy 1.18.2** - Static type checking

### Python Version Support

Tested on: **Python 3.10, 3.11, 3.12**

---

## Development Workflows

### Initial Setup

```bash
# Option 1: Using pip
./run_setup_dev.sh

# Option 2: Manual setup
pip install -r requirements.txt
python src/setup_dev.py

# Option 3: Using conda
conda env create -f environment.yml
conda activate bouldering-analysis
```

### Running the Application

```bash
# Start Flask development server
./run.sh

# Or manually
cd src && python main.py

# The app will be available at http://localhost:5000
```

### Quality Assurance Workflow

**CRITICAL**: All code changes must pass QA before merging.

```bash
# Run comprehensive QA suite (mypy, ruff, pytest, pylint)
./run_qa.csh

# This script enforces:
# - Type checking (mypy)
# - Code formatting (ruff format --check)
# - Linting (ruff check)
# - 99% test coverage (pytest-cov)
# - 9.9/10 pylint score
```

#### Individual QA Commands

```bash
# Type checking
mypy src/ tests/

# Format checking (do NOT auto-format without review)
ruff format --check .

# Linting
ruff check .

# Tests with coverage
pytest tests/ --cov-report=term-missing --cov=src/

# Code quality
pylint src/
```

### Model Training Workflow

```bash
# Fine-tune YOLOv8 on hold detection dataset
python src/train_model.py \
  --model-name hold_detection_v2 \
  --epochs 100 \
  --batch-size 16 \
  --learning-rate 0.001 \
  --data-yaml data/sample_hold/data.yaml \
  --base-weights yolov8n.pt \
  --activate

# Manage model versions
python src/manage_models.py list
python src/manage_models.py activate hold_detection 2
python src/manage_models.py deactivate hold_detection 1
```

### Database Migrations

```bash
# Run migration scripts from scripts/migrations/
python scripts/migrations/drop_holds_detected_column.py

# Always refer to docs/migrations.md for migration guides
```

---

## Code Conventions

### Naming Standards

#### Python Code

- **Modules**: snake_case (`train_model.py`, `manage_models.py`)
- **Classes**: PascalCase (`Analysis`, `HoldType`, `ModelVersion`)
- **Functions**: snake_case (`get_hold_types()`, `load_config()`)
- **Constants**: UPPER_SNAKE_CASE (`HOLD_TYPES`, `MAX_FILE_SIZE`)
- **Private/Internal**: Leading underscore (`_hold_types_cache`, `_process_box()`)

#### Database Naming Conventions

- **Tables**: plural snake_case (`analyses`, `feedback`, `hold_types`)
- **Columns**: snake_case (`image_filename`, `predicted_grade`, `bbox_x1`)
- **Foreign Keys**: `{entity}_id` pattern (`analysis_id`, `hold_type_id`)
- **Timestamps**: `created_at`, `updated_at` (UTC with timezone)
- **Indexes**: `idx_` prefix (`idx_analysis_predicted_grade`)

#### Configuration

- **Keys**: Nested dot notation (`model_defaults.hold_detection_confidence_threshold`)
- **Paths**: snake_case (`fine_tuned_models`, `hold_dataset`)

### Documentation Standards

**All modules, classes, and functions must have Google-style docstrings:**

```python
def analyze_image(image_path: str, confidence: float = 0.25) -> dict:
    """Analyze bouldering route image and detect holds.

    Processes the uploaded image using the active YOLOv8 model to detect
    climbing holds and classify them into hold types.

    Args:
        image_path: Absolute path to the image file to analyze
        confidence: Minimum confidence threshold for detections (0.0-1.0)

    Returns:
        Dictionary containing detected holds and analysis metadata:
        {
            'holds': List[dict],
            'predicted_grade': str,
            'confidence_score': float,
            'analysis_id': str
        }

    Raises:
        FileNotFoundError: If image_path does not exist
        ValueError: If confidence is not in valid range
        RuntimeError: If YOLO model fails to load or process image
    """
```

### Type Annotations

**Full type hints required on all functions:**

```python
from typing import Optional, Dict, List, Tuple
from pathlib import Path

def load_config(config_path: Optional[Path] = None) -> Dict[str, Any]:
    """Load configuration from YAML file."""
    ...

def get_active_model() -> Optional[ModelVersion]:
    """Retrieve the currently active hold detection model."""
    ...

def process_detections(results: List[Dict]) -> Tuple[List[Dict], float]:
    """Process YOLO detection results and calculate confidence."""
    ...
```

### Import Organization

```python
# 1. Future imports (if needed)
from __future__ import annotations

# 2. Standard library
import os
import logging
from pathlib import Path
from typing import Dict, List, Optional

# 3. Third-party
import numpy as np
from flask import Flask, request, jsonify
from sqlalchemy import create_engine

# 4. Local/project
from src.models import Analysis, HoldType
from src.config import load_config
```

### Code Style

- **Formatter**: Ruff format (Black-compatible)
- **Line Length**: Long lines allowed (E501 ignored) but keep reasonable
- **Quotes**: Double quotes preferred for strings
- **Indentation**: 4 spaces (no tabs)
- **Trailing Commas**: Required in multi-line collections
- **F-strings**: Preferred for string formatting (not % or .format())

### Exception Handling

```python
# Use specific exceptions
try:
    config = load_config(path)
except FileNotFoundError as e:
    logger.error("Config file not found: %s", path)
    raise ConfigurationError(f"Missing config: {path}") from e

# Custom exceptions for domain-specific errors
class ConfigurationError(Exception):
    """Raised when configuration is invalid or missing."""
```

### Logging

```python
# Configure at module level
import logging

logger = logging.getLogger(__name__)

# Use lazy % formatting (required by pylint)
logger.info("Processing image: %s", image_path)
logger.error("Failed to load model: %s", model_path, exc_info=True)
```

---

## Testing Requirements

### Testing Philosophy

**This project has STRICT testing requirements:**

- **Coverage Target**: 99% minimum (enforced by CI/CD)
- **Framework**: pytest with comprehensive fixtures
- **Isolation**: Each test uses fresh database via fixtures
- **Mock External Dependencies**: YOLO models, file I/O, etc.

### Running Tests

```bash
# Run all tests with coverage
pytest tests/ --cov-report=term-missing --cov=src/

# Run specific test file
pytest tests/test_main.py -v

# Run specific test function
pytest tests/test_main.py::test_analyze_endpoint -v

# Run with coverage report showing missing lines
pytest tests/ --cov=src/ --cov-report=html
# Open htmlcov/index.html in browser
```

### Key Test Fixtures (from conftest.py)

```python
# Available fixtures for tests:

@pytest.fixture
def test_app():
    """Isolated Flask app with temporary database."""

@pytest.fixture
def test_client(test_app):
    """Flask test client for making requests."""

@pytest.fixture
def sample_image_path():
    """Temporary test image file."""

@pytest.fixture
def sample_analysis_data():
    """Sample analysis record data."""

@pytest.fixture
def sample_yolo_dataset(tmp_path):
    """Complete YOLO dataset structure for testing."""

@pytest.fixture
def active_model_version():
    """Active hold detection model version."""
```

### Writing Tests

**Example test structure:**

```python
def test_analyze_endpoint_success(test_client, sample_image_path, mocker):
    """Test successful image analysis via /analyze endpoint.

    Verifies that uploading a valid image returns analysis results
    with detected holds and predicted grade.
    """
    # Arrange - Mock YOLO model
    mock_model = mocker.patch('src.main.load_active_hold_detection_model')
    mock_model.return_value.predict.return_value = [mock_detection_result]

    # Act - Upload image
    with open(sample_image_path, 'rb') as img:
        response = test_client.post(
            '/analyze',
            data={'file': (img, 'test.jpg')},
            content_type='multipart/form-data'
        )

    # Assert - Check response
    assert response.status_code == 200
    data = response.get_json()
    assert 'analysis_id' in data
    assert 'holds' in data
    assert len(data['holds']) > 0
```

### Testing Checklist for New Features

- [ ] Unit tests for all new functions
- [ ] Integration tests for API endpoints
- [ ] Database model tests (CRUD operations)
- [ ] Error handling and edge cases
- [ ] Mock external dependencies (YOLO, file I/O)
- [ ] Verify 99%+ coverage maintained
- [ ] All tests pass in CI/CD pipeline

---

## Database Schema

### Models Overview

The application uses SQLAlchemy ORM with 6 main models:

#### 1. Analysis

**Purpose**: Stores image analysis results

```python
class Analysis(Base):
    __tablename__ = 'analyses'

    id: UUID (PK)
    image_filename: str
    predicted_grade: str
    confidence_score: float
    features_extracted: JSON
    created_at: datetime
    updated_at: datetime

    # Relationships
    feedback: Feedback (1:1)
    detected_holds: List[DetectedHold] (1:many)
```

#### 2. DetectedHold

**Purpose**: Individual hold detections (relational schema)

```python
class DetectedHold(Base):
    __tablename__ = 'detected_holds'

    id: int (PK)
    analysis_id: UUID (FK -> Analysis)
    hold_type_id: int (FK -> HoldType)
    confidence: float
    bbox_x1: float
    bbox_y1: float
    bbox_x2: float
    bbox_y2: float
```

#### 3. HoldType

**Purpose**: Reference table for hold classifications

```python
class HoldType(Base):
    __tablename__ = 'hold_types'

    id: int (PK)
    name: str (unique)  # 'crimp', 'jug', 'sloper', etc.
    description: str
```

**8 Hold Types:**

1. crimp
2. jug
3. sloper
4. pinch
5. pocket
6. foot-hold
7. start-hold
8. top-out-hold

#### 4. Feedback

**Purpose**: User feedback on predictions

```python
class Feedback(Base):
    __tablename__ = 'feedback'

    id: UUID (PK)
    analysis_id: UUID (FK -> Analysis)
    user_grade: str
    is_accurate: bool
    comments: str (optional)
    created_at: datetime
```

#### 5. ModelVersion

**Purpose**: ML model tracking and versioning

```python
class ModelVersion(Base):
    __tablename__ = 'model_versions'

    id: int (PK)
    model_type: str  # 'hold_detection'
    version: int
    model_path: str
    accuracy: float (optional)
    is_active: bool
    created_at: datetime

    # Unique constraint: (model_type, version)
```

#### 6. UserSession

**Purpose**: Analytics and session tracking

```python
class UserSession(Base):
    __tablename__ = 'user_sessions'

    id: UUID (PK)
    session_id: str
    ip_address: str
    user_agent: str
    created_at: datetime
    last_activity: datetime
```

### Database Operations

```python
# Get hold types (cached)
hold_types = get_hold_types()

# Create analysis record
analysis = Analysis(
    image_filename='route.jpg',
    predicted_grade='V5',
    confidence_score=0.87
)
db.session.add(analysis)

# Add detected holds
hold = DetectedHold(
    analysis_id=analysis.id,
    hold_type_id=1,  # crimp
    confidence=0.92,
    bbox_x1=100, bbox_y1=50,
    bbox_x2=150, bbox_y2=100
)
db.session.add(hold)

db.session.commit()

# Query with relationships
analysis = Analysis.query.filter_by(id=uuid).first()
holds = analysis.detected_holds  # Automatic join
feedback = analysis.feedback  # 1:1 relationship
```

---

## Common Tasks

### Adding a New Flask Route

1. **Define route in src/main.py:**

```python
@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """Get application usage statistics.

    Returns aggregated statistics about analyses, feedback,
    and model performance.

    Returns:
        JSON response with statistics data
    """
    try:
        total_analyses = Analysis.query.count()
        avg_confidence = db.session.query(
            func.avg(Analysis.confidence_score)
        ).scalar()

        return jsonify({
            'total_analyses': total_analyses,
            'average_confidence': float(avg_confidence)
        }), 200

    except Exception as e:
        logger.error("Failed to get statistics: %s", str(e), exc_info=True)
        return jsonify({'error': 'Internal server error'}), 500
```

1. **Add tests in tests/test_main.py:**

```python
def test_get_statistics_endpoint(test_client, test_app):
    """Test /api/statistics endpoint returns correct data."""
    # Create test data
    analysis = Analysis(...)
    db.session.add(analysis)
    db.session.commit()

    # Make request
    response = test_client.get('/api/statistics')

    # Verify response
    assert response.status_code == 200
    data = response.get_json()
    assert 'total_analyses' in data
    assert data['total_analyses'] == 1
```

1. **Verify coverage remains 99%+**

### Adding a New Database Model

1. **Define model in src/models.py:**

```python
class RouteMetadata(Base):
    """Store additional route metadata."""

    __tablename__ = 'route_metadata'

    id = Column(Integer, primary_key=True)
    analysis_id = Column(UUID(as_uuid=True), ForeignKey('analyses.id'))
    wall_angle = Column(Float)  # degrees from vertical
    wall_type = Column(String(50))  # 'indoor', 'outdoor'
    setter_name = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=datetime.utcnow)

    # Relationship
    analysis = relationship('Analysis', back_populates='route_metadata')

    def to_dict(self) -> dict:
        """Convert model to dictionary."""
        return {
            'id': self.id,
            'analysis_id': str(self.analysis_id),
            'wall_angle': self.wall_angle,
            'wall_type': self.wall_type,
            'setter_name': self.setter_name,
            'created_at': self.created_at.isoformat()
        }
```

1. **Update Analysis model relationship:**

```python
# In Analysis class
route_metadata = relationship('RouteMetadata', back_populates='analysis', uselist=False)
```

1. **Create migration script in scripts/migrations/:**

```python
# scripts/migrations/add_route_metadata_table.py
def upgrade():
    """Add route_metadata table."""
    # Use SQLAlchemy to create table
    RouteMetadata.__table__.create(bind=engine)
```

1. **Add comprehensive tests in tests/test_models.py**

2. **Document migration in docs/migrations.md**

### Modifying Configuration

1. **Update src/cfg/user_config.yaml:**

```yaml
model_defaults:
  hold_detection_confidence_threshold: 0.25
  route_grading_confidence_threshold: 0.30  # NEW

model_paths:
  base_yolov8: 'yolov8n.pt'
  fine_tuned_models: 'models/hold_detection/'
  grade_classifier: 'models/grade_classifier/'  # NEW
```

1. **Access in code via src/config.py:**

```python
from src.config import get_config_value

grade_threshold = get_config_value(
    'model_defaults.route_grading_confidence_threshold',
    default=0.25
)

grade_model_path = get_config_value(
    'model_paths.grade_classifier'
)
```

1. **Update tests to use new config values**

### Training a New Model

```bash
# 1. Prepare dataset in YOLO format
# data/sample_hold/
#   ├── train/
#   │   ├── images/
#   │   └── labels/
#   ├── val/
#   │   ├── images/
#   │   └── labels/
#   └── data.yaml

# 2. Run training script
python src/train_model.py \
  --model-name hold_detection_v3 \
  --epochs 100 \
  --batch-size 16 \
  --learning-rate 0.001 \
  --data-yaml data/sample_hold/data.yaml \
  --base-weights yolov8n.pt \
  --activate

# 3. Model will be saved to models/hold_detection/
# 4. Database record created in model_versions table
# 5. Model automatically activated if --activate flag used
```

---

## Configuration Management

### Configuration Files

#### Primary Config: src/cfg/user_config.yaml

```yaml
model_defaults:
  hold_detection_confidence_threshold: 0.25

model_paths:
  base_yolov8: 'yolov8n.pt'
  fine_tuned_models: 'models/hold_detection/'

data_paths:
  hold_dataset: 'data/sample_hold/'
  uploads: 'data/uploads/'
```

#### Environment Variables

```bash
# Database configuration
DATABASE_URL=sqlite:///data/bouldering_analysis.db  # Default
DATABASE_URL=postgresql://user:pass@localhost/bouldering  # Production

# Flask configuration
FLASK_ENV=development
FLASK_DEBUG=1

# Upload settings
MAX_CONTENT_LENGTH=16777216  # 16MB in bytes
```

### Configuration Loading

```python
from src.config import load_config, get_config_value, get_model_path

# Load entire config (cached)
config = load_config()

# Get specific nested value
threshold = get_config_value(
    'model_defaults.hold_detection_confidence_threshold',
    default=0.25
)

# Resolve model path (handles relative/absolute)
model_path = get_model_path('fine_tuned_models', 'best.pt')
```

### Configuration Best Practices

1. **Never hardcode paths** - Use config.py functions
2. **Provide defaults** - All get_config_value calls should have defaults
3. **Cache configuration** - Config is cached automatically (thread-safe)
4. **Validate on load** - Check config values at startup
5. **Document new keys** - Update this guide when adding config keys

---

## Quality Standards

### Code Coverage

**Minimum Required**: 99%

```bash
# Check coverage
pytest tests/ --cov=src/ --cov-report=term-missing

# Generate HTML report
pytest tests/ --cov=src/ --cov-report=html
# View htmlcov/index.html
```

**Coverage exclusions** (pyproject.toml):

- Tests themselves
- `__init__.py` files
- `src/setup.py` (one-time setup script)
- Abstract methods
- Type checking blocks (`if TYPE_CHECKING:`)

### Type Checking

**Tool**: mypy 1.18.2

```bash
# Run type checking
mypy src/ tests/
```

**Configuration** (mypy.ini):

- Warning-level mode (not strict)
- Return type warnings enabled
- No implicit optional
- SQLAlchemy plugin enabled
- Ignores: flask_sqlalchemy, ultralytics, PIL, werkzeug

### Linting

**Primary Tool**: ruff 0.14.7 (fast Python linter)

```bash
# Check linting
ruff check .

# Auto-fix safe issues
ruff check --fix .
```

**Ignored Rules** (.flake8):

- E501: Line too long
- W503: Line break before binary operator

### Code Formatting

**Tool**: ruff format (Black-compatible)

```bash
# Check formatting (do NOT auto-format without review)
ruff format --check .

# Format code
ruff format .
```

### Code Quality

**Tool**: pylint 4.0.3
**Minimum Score**: 9.9/10 (enforced by CI/CD)

```bash
# Run pylint
pylint src/
```

**Configuration** (.pylintrc):

- Disabled: line-too-long

### Pre-Commit Checklist

Before committing code, ensure:

- [ ] All tests pass: `pytest tests/`
- [ ] Coverage ≥ 99%: `pytest tests/ --cov=src/`
- [ ] Type checking passes: `mypy src/ tests/`
- [ ] Linting passes: `ruff check .`
- [ ] Formatting passes: `ruff format --check .`
- [ ] Pylint score ≥ 9.9: `pylint src/`

**Or run comprehensive QA:**

```bash
./run_qa.csh
```

### CI/CD Enforcement

All pull requests must pass 3 GitHub Actions workflows:

1. **pylint.yml** - Main QA pipeline (Python 3.10, 3.11, 3.12)
2. **python-code-cov.yml** - Coverage + testing
3. **python-package-conda.yml** - Conda build

Failures block merging to main branch.

---

## API Endpoints Reference

### Flask Routes

| Endpoint | Method | Purpose | Request | Response |
| ---------- | -------- | ----------- | ----------- | ------------ |
| `/` | GET | Main UI page | - | HTML template |
| `/analyze` | POST | Analyze route image | multipart/form-data with image file | JSON with analysis results |
| `/feedback` | POST | Submit user feedback | JSON with analysis_id, user_grade, is_accurate, comments | JSON confirmation |
| `/stats` | GET | Usage statistics | - | JSON with aggregated stats |
| `/health` | GET | Health check | - | JSON with status |
| `/uploads/<filename>` | GET | Serve uploaded image | - | Image file |

### Example API Usage

#### Analyze Image

```bash
curl -X POST http://localhost:5000/analyze \
  -F "file=@route.jpg"
```

Response:

```json
{
  "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
  "predicted_grade": "V5",
  "confidence_score": 0.87,
  "holds": [
    {
      "hold_type": "crimp",
      "confidence": 0.92,
      "bbox": [100, 50, 150, 100]
    }
  ]
}
```

#### Submit Feedback

```bash
curl -X POST http://localhost:5000/feedback \
  -H "Content-Type: application/json" \
  -d '{
    "analysis_id": "550e8400-e29b-41d4-a716-446655440000",
    "user_grade": "V6",
    "is_accurate": false,
    "comments": "Felt harder than V5"
  }'
```

---

## AI Assistant Guidelines

### When Making Changes

1. **Read before modifying**: Always read files before editing
2. **Understand context**: Review related files and tests
3. **Follow conventions**: Match existing code style and patterns
4. **Write tests first**: Add tests for new functionality
5. **Maintain coverage**: Ensure 99%+ coverage after changes
6. **Run QA suite**: Execute `./run_qa.csh` before committing
7. **Update documentation**: Keep CLAUDE.md and docs/ current

### Code Review Checklist

- [ ] Type hints on all functions
- [ ] Google-style docstrings on all public functions
- [ ] Error handling for edge cases
- [ ] Logging with lazy % formatting
- [ ] No hardcoded paths (use config.py)
- [ ] Thread-safe if caching data
- [ ] Database sessions properly closed
- [ ] Tests added for new functionality
- [ ] Coverage remains ≥ 99%
- [ ] All QA checks pass

### Common Pitfalls to Avoid

1. **Don't bypass QA checks** - All code must pass run_qa.csh
2. **Don't auto-format without review** - Check diffs before ruff format
3. **Don't ignore type errors** - Fix mypy issues, don't add ignores
4. **Don't skip tests** - 99% coverage is mandatory
5. **Don't use print()** - Use logging module
6. **Don't commit .pt files** - Model weights are gitignored
7. **Don't hardcode database paths** - Use DATABASE_URL env var
8. **Don't forget pylint disables** - Use sparingly with comments

### Debugging Tips

```python
# Use logging, not print()
import logging
logger = logging.getLogger(__name__)
logger.debug("Processing image: %s", image_path)

# Test database queries in pytest
def test_query_holds(test_app):
    with test_app.app_context():
        holds = DetectedHold.query.all()
        assert len(holds) > 0

# Mock YOLO models in tests
def test_analyze(mocker):
    mock_model = mocker.patch('src.main.load_active_hold_detection_model')
    mock_model.return_value.predict.return_value = [...]
```

### Getting Help

- **Project Documentation**: See docs/ directory
- **Migration Guide**: docs/migrations.md
- **Implementation Details**: docs/week3-4_implementation.md
- **Validation Guide**: docs/week3-4_validation.md
- **Progress Tracker**: PROGRESS.md

---

## Quick Reference

### File Extensions

- `.py` - Python source files
- `.yaml` / `.yml` - Configuration files
- `.md` - Markdown documentation
- `.pt` - PyTorch model weights (gitignored)
- `.jpg` / `.png` - Image files (gitignored)

### Important Directories

- `src/` - Main application code
- `tests/` - Test suite
- `data/` - Datasets and uploads (mostly gitignored)
- `models/` - Trained model weights (gitignored)
- `docs/` - Project documentation
- `.github/workflows/` - CI/CD pipelines

### Key Commands

```bash
./run.sh                  # Start Flask app
./run_setup_dev.sh        # Setup dev environment
./run_qa.csh             # Run all QA checks
pytest tests/            # Run tests
mypy src/ tests/         # Type checking
ruff check .             # Linting
ruff format --check .    # Format checking
pylint src/              # Code quality
```

### Environment Setup

```bash
# Quick start
pip install -r requirements.txt
python src/setup_dev.py
./run.sh
```

---

**This guide is maintained for AI assistants working with the bouldering-analysis codebase. Keep it updated as the project evolves.**
