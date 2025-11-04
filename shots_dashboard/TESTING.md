## Testing Guide

Comprehensive testing guide for the Shots Dashboard.

## Test Suite Overview

The dashboard has three levels of testing:

1. **Unit Tests**: Fast, isolated tests of individual components
2. **Integration Tests**: Test Flask API endpoints and database integration
3. **End-to-End Tests**: Test complete workflows through the web UI using Playwright

## Running Tests

### Install Test Dependencies

```bash
uv pip install -r shots_dashboard_requirements-dev.txt

# Install Playwright browsers (first time only)
playwright install
```

### Run All Tests

```bash
# Run all tests
pytest

# Run with coverage report
pytest --cov=shots_dashboard --cov-report=html

# Run only unit tests
pytest -m unit

# Run only integration tests
pytest -m integration

# Run only E2E tests
pytest -m e2e

# Run E2E tests in headed mode (see the browser)
PLAYWRIGHT_HEADLESS=0 pytest -m e2e
```

### Run Specific Test Files

```bash
# Unit tests
pytest tests/test_shots_dashboard_models.py -v
pytest tests/test_shots_dashboard_database.py -v

# Integration tests
pytest tests/test_shots_dashboard_app.py -v

# E2E tests
pytest tests/test_e2e_dashboard.py -v
```

### Run Specific Test Functions

```bash
pytest tests/test_e2e_dashboard.py::test_dashboard_loads -v
pytest tests/test_e2e_dashboard.py::test_scan_directory_workflow -v
pytest tests/test_e2e_dashboard.py::test_state_transitions_workflow -v
```

## E2E Test Scenarios

The E2E test suite covers these scenarios:

### Basic Functionality
- **test_dashboard_loads**: Dashboard loads and displays correctly
- **test_initial_state_is_empty**: Starts with zero files
- **test_refresh_button**: Refresh updates the display

### Directory Scanning
- **test_scan_directory_workflow**: Complete scan workflow
- **test_keyboard_navigation**: Enter key works in inputs

### Timeline Updates
- **test_update_from_timeline_workflow**: Update from timeline file
- **test_state_transitions_workflow**: Full state transition cycle
  - NEW → IN_USE (files added to timeline)
  - IN_USE → REMOVED (files removed from timeline)
  - REMOVED → IN_USE (files brought back)

### State Management
- **test_reset_workflow**: Reset clears all data
- **test_persistence_across_sessions**: Data persists after reload

### Error Handling
- **test_error_handling_invalid_directory**: Invalid directory paths
- **test_error_handling_invalid_timeline**: Invalid timeline files

### Transitions
- **test_multiple_updates_show_transitions**: Transitions list accumulates

## Demo Mode

The dashboard includes a demo mode that automatically generates sample data and runs through realistic scenarios.

### Running Demo Mode

```bash
# Run demo mode (creates sample data and shows scenarios)
python -m shots_dashboard --demo

# Demo with custom port
python -m shots_dashboard --demo --port 8000
```

### What Demo Mode Does

The demo runs through 4 scenarios:

1. **Initial Scan**: Scans directory with 11 sample media files
2. **First Timeline**: Updates with initial_cut.otio (3 shots)
3. **Revised Cut**: Updates with revised_cut.otio (5 shots, 2 added)
4. **Final Cut**: Updates with final_cut.otio (5 shots, some replaced/removed)

Demo data is created in: `~/.shots_dashboard/demo/`

After the demo completes, the web interface starts and you can:
- Click "Refresh" to load the demo data
- Experiment with scanning and updating
- See the realistic production workflow

### Running Demo Programmatically

```python
from pathlib import Path
from shots_dashboard.demo import run_demo

demo_dir = Path("/tmp/my_demo")
db_path = demo_dir / "demo.json"

run_demo(demo_dir, db_path)
```

## Writing New Tests

### Unit Test Example

```python
def test_my_feature():
    """Test description."""
    from shots_dashboard.models import FileRecord, FileState
    from datetime import datetime
    from pathlib import Path

    record = FileRecord(
        path=Path("/test/file.mov"),
        state=FileState.NEW,
        last_updated=datetime.now()
    )

    assert record.state == FileState.NEW
```

### E2E Test Example

```python
import pytest
from playwright.sync_api import Page, expect

@pytest.mark.e2e
def test_my_workflow(page: Page, live_server: str, test_media_dir: Path) -> None:
    """Test my workflow."""
    page.goto(live_server)

    # Fill form
    page.locator("#scan-directory").fill(str(test_media_dir))
    page.locator("#scan-btn").click()

    # Check results
    expect(page.locator("#stat-total")).to_have_text("5")
```

## Test Fixtures

Available pytest fixtures:

### Data Fixtures
- `test_media_dir`: Temporary directory with sample media files
- `test_timeline_v1`: Timeline with shots 1 and 2
- `test_timeline_v2`: Timeline with shots 2 and 3
- `test_timeline_empty`: Empty timeline
- `test_db_path`: Temporary database path

### App Fixtures
- `flask_app`: Flask application instance
- `live_server`: Running Flask server for E2E tests

## Continuous Integration

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.10'

      - name: Install dependencies
        run: |
          pip install -r shots_dashboard_requirements.txt
          pip install -r shots_dashboard_requirements-dev.txt
          playwright install --with-deps

      - name: Run tests
        run: pytest --cov=shots_dashboard --cov-report=xml

      - name: Upload coverage
        uses: codecov/codecov-action@v3
```

## Type Checking

Run type checker with basedpyright:

```bash
basedpyright shots_dashboard
```

## Performance Testing

For performance testing of the API:

```bash
# Install locust
pip install locust

# Create locustfile.py with API tests
# Run load test
locust -f locustfile.py --host http://localhost:5000
```

## Test Coverage Goals

- Unit tests: 95%+ coverage
- Integration tests: All API endpoints
- E2E tests: All critical user workflows

Current coverage:
```bash
pytest --cov=shots_dashboard --cov-report=term-missing
```

## Debugging Tests

### Debug E2E Tests Visually

```bash
# Run in headed mode with slow motion
PLAYWRIGHT_HEADLESS=0 pytest -m e2e --slowmo 1000
```

### Debug with pdb

```python
def test_my_feature():
    import pdb; pdb.set_trace()
    # Your test code
```

### Playwright Inspector

```bash
PWDEBUG=1 pytest tests/test_e2e_dashboard.py::test_my_workflow
```

## Common Issues

### Playwright Installation
If Playwright browsers aren't installed:
```bash
playwright install chromium
```

### Port Already in Use
The live_server fixture uses port 5555. If it's in use:
```bash
lsof -ti:5555 | xargs kill
```

### Slow Tests
Mark slow tests and skip them during development:
```bash
pytest -m "not slow"
```

## Best Practices

1. **Isolation**: Each test should be independent
2. **Fixtures**: Use fixtures for common setup
3. **Markers**: Mark tests by type (unit, integration, e2e)
4. **Names**: Use descriptive test names
5. **Comments**: Document complex test scenarios
6. **Speed**: Keep unit tests fast, mark slow tests
7. **Coverage**: Aim for high coverage but test behavior, not lines

## Resources

- [Pytest Documentation](https://docs.pytest.org/)
- [Playwright Python Documentation](https://playwright.dev/python/)
- [Flask Testing](https://flask.palletsprojects.com/en/latest/testing/)
