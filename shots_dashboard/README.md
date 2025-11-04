# Shots Dashboard

An interactive Flask dashboard for tracking which media files are integrated into OpenTimelineIO timelines. Inspired by the [shots-added-removed-from-cut.md](../docs/use-cases/shots-added-removed-from-cut.md) use case.

## Overview

This dashboard helps editors and production teams keep track of:

- **Not Yet Used**: Files that exist in your media directory but haven't been used in the timeline yet
- **In Use**: Files currently present in your timeline
- **Removed**: Files that were previously in the timeline but have been removed

Perfect for animation studios, editorial teams, and any production workflow where tracking shot usage is critical.

## Features

- 🎬 Real-time tracking of file states across timeline versions
- 📊 Visual dashboard with statistics and file lists
- 🔄 State transition tracking (NEW → IN_USE → REMOVED)
- 💾 JSON-based persistence
- 🧪 Comprehensive test suite (100% coverage goal)
- 🔒 Strict type checking with basedpyright
- 🏗️ Modern software engineering practices:
  - Type hints everywhere
  - Immutable data structures
  - Pattern matching for state transitions
  - Making illegal state unrepresentable

## Architecture

### Data Models (`models.py`)

Uses frozen dataclasses and enums to create a type-safe, immutable data model:

```python
class FileState(Enum):
    NEW = auto()        # Never been in timeline
    IN_USE = auto()     # Currently in timeline
    REMOVED = auto()    # Was in timeline, now removed

@dataclass(frozen=True)
class FileRecord:
    path: Path
    state: FileState
    last_updated: datetime
```

### State Transitions

The tracker uses Python 3.10+ pattern matching to handle all state transitions explicitly:

```python
match (current_state, is_in_timeline):
    case (FileState.NEW, True):
        # File is now used for the first time
        new_state = FileState.IN_USE

    case (FileState.IN_USE, False):
        # File has been removed from timeline
        new_state = FileState.REMOVED

    case (FileState.REMOVED, True):
        # Previously removed file is back
        new_state = FileState.IN_USE
    # ... etc
```

This approach makes all valid transitions explicit and invalid ones impossible at compile time.

## Installation

### Using uv (recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the OpenTimelineIO root directory
cd OpenTimelineIO

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows

# Install dependencies (includes OpenTimelineIO from PyPI)
uv pip install -r shots_dashboard_requirements.txt

# For development (includes pytest, basedpyright)
uv pip install -r shots_dashboard_requirements-dev.txt
```

### Using pip

```bash
cd OpenTimelineIO

python -m venv .venv
source .venv/bin/activate

pip install -r shots_dashboard_requirements.txt
pip install -r shots_dashboard_requirements-dev.txt  # For development
```

## Usage

### Running the Dashboard

From the OpenTimelineIO root directory:
```bash
python -m shots_dashboard
```

Or from within the shots_dashboard directory:
```bash
cd shots_dashboard
python app.py
```

Then navigate to http://localhost:5000 in your browser.

### Using the Web Interface

1. **Scan Directory**: Enter the path to your media files directory and click "Scan"
2. **Update from Timeline**: Enter the path to your OTIO timeline file (`.otio`, `.edl`, `.xml`, etc.) and click "Update"
3. **View Changes**: See files organized by their state and track recent transitions

### API Endpoints

The dashboard provides a REST API:

- `GET /api/status` - Get current statistics
- `GET /api/files` - Get all files grouped by state
- `POST /api/scan` - Scan a directory for media files
- `POST /api/update_timeline` - Update state from timeline file
- `POST /api/reset` - Reset all state

#### Example API Usage

```python
import requests

# Scan directory
response = requests.post('http://localhost:5000/api/scan', json={
    'directory': '/path/to/media'
})

# Update from timeline
response = requests.post('http://localhost:5000/api/update_timeline', json={
    'timeline_path': '/path/to/timeline.otio'
})

# Get current files
response = requests.get('http://localhost:5000/api/files')
files = response.json()
print(f"In use: {len(files['files']['in_use'])}")
print(f"Removed: {len(files['files']['removed'])}")
```

## Development

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=shots_dashboard --cov-report=html

# Run specific test file
pytest tests/test_models.py

# Run specific test
pytest tests/test_models.py::TestFileState::test_all_states_exist
```

### Type Checking

```bash
# Run basedpyright
basedpyright shots_dashboard tests

# Check specific file
basedpyright shots_dashboard/models.py
```

### Code Quality

The codebase follows these principles:

1. **Type Safety**: All functions have type hints; strict mode enabled
2. **Immutability**: Core data structures are frozen dataclasses
3. **Exhaustive Pattern Matching**: All state transitions are explicit
4. **Error Handling**: Proper exception types and error messages
5. **Testing**: Comprehensive unit and integration tests

## Project Structure

```
shots_dashboard/
├── __init__.py              # Package initialization
├── models.py                # Data models (FileState, FileRecord, etc.)
├── database.py              # JSON persistence layer
├── timeline_tracker.py      # Core tracking logic
├── app.py                   # Flask application
├── static/
│   ├── css/
│   │   └── style.css       # Dashboard styling
│   └── js/
│       └── dashboard.js     # Frontend logic
└── templates/
    ├── index.html          # Main dashboard
    └── 404.html            # Error page

tests/
├── test_models.py          # Model tests
├── test_database.py        # Database tests
├── test_timeline_tracker.py # Tracker logic tests
└── test_app.py             # Flask integration tests
```

## Database Format

State is persisted as JSON in `~/.shots_dashboard/state.json`:

```json
{
  "files": {
    "/path/to/shot_001.mov": {
      "path": "/path/to/shot_001.mov",
      "state": "IN_USE",
      "last_updated": "2024-01-01T12:00:00"
    }
  },
  "timeline_path": "/path/to/timeline.otio",
  "last_scan": "2024-01-01T12:00:00"
}
```

## Use Case Example

As described in the [OpenTimelineIO use case](../docs/use-cases/shots-added-removed-from-cut.md):

1. **Editorial** exports an EDL/AAF from their editing system daily
2. **Animation** runs this dashboard pointing to:
   - Their rendered shots directory
   - The latest EDL/AAF (converted to OTIO)
3. The dashboard shows:
   - Which shots are currently in the cut (keep working on these)
   - Which shots were removed (can stop working on these)
   - Which new shots were requested (start working on these)

## Design Decisions

### Why Frozen Dataclasses?

Immutable data structures prevent accidental state mutations and make the code easier to reason about. State changes always create new objects, making debugging and testing simpler.

### Why Pattern Matching?

Pattern matching makes all valid state transitions explicit in one place. The compiler ensures we handle all cases, and invalid transitions become impossible.

### Why Enums?

Enums provide type-safe state representation. You can't accidentally pass an invalid state string - it won't type check.

### Why JSON Database?

Simple, human-readable, and sufficient for this use case. Easy to inspect, version control, and migrate if needed.

## Limitations

- Single-user (file-based database)
- No authentication/authorization
- Limited to local file system
- Manual updates (no file watching)

## Future Enhancements

- [ ] File system watching for automatic updates
- [ ] Multi-user support (PostgreSQL/SQLite backend)
- [ ] WebSocket support for real-time updates
- [ ] Export reports (CSV, PDF)
- [ ] Email notifications on state changes
- [ ] Integration with production tracking systems (Shotgun, ftrack, etc.)
- [ ] Timeline comparison (diff between versions)

## Contributing

This is part of the OpenTimelineIO project. See the main repository for contribution guidelines.

## License

Apache License 2.0 - See LICENSE file in the root of the OpenTimelineIO project.

## Credits

Inspired by the editorial workflow use case documented in the OpenTimelineIO project.
