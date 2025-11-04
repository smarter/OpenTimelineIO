# Timeline Widget Feature

## Overview

The timeline widget provides users with a comprehensive view of which files are currently in the timeline and which files were previously in the timeline but have since been removed. This helps editors keep track of the full history of their timeline edits.

## Features

### Current Timeline View
- Shows all clips currently in the most recent timeline
- Displays timeline filename and last update timestamp
- Shows clip count at a glance
- Auto-refreshes every 2 seconds to stay in sync

### Historical Timeline View
- Toggle to show/hide historical clips
- Shows clips that appeared in previous timeline versions but not in current
- Visual differentiation with red-themed badges
- Helps identify clips that were removed from the timeline

### Timeline History Tracking
- Automatically records timeline snapshots on every `update_from_timeline` operation
- Maintains up to 50 snapshots in history
- Persists across application restarts
- Immutable data structures prevent accidental modifications

## Architecture

### Model Layer (`shots_dashboard/models.py`)

**TimelineSnapshot** - Immutable snapshot of timeline state
```python
@dataclass(frozen=True)
class TimelineSnapshot:
    timestamp: datetime
    timeline_path: Path
    clip_names: tuple[str, ...]  # Immutable
```

**TimelineHistory** - Immutable collection of snapshots
```python
@dataclass(frozen=True)
class TimelineHistory:
    snapshots: tuple[TimelineSnapshot, ...]
    max_snapshots: int = 50

    def add_snapshot(self, snapshot) -> TimelineHistory
    def get_current() -> TimelineSnapshot | None
    def get_historical() -> tuple[TimelineSnapshot, ...]
    def get_all_historical_clips() -> Set[str]
```

### Database Layer (`shots_dashboard/database.py`)

- Serializes timeline history to JSON
- Handles loading/saving of snapshots
- Gracefully handles corrupted data

```json
{
  "timeline_history": {
    "snapshots": [
      {
        "timestamp": "2024-11-04T12:00:00",
        "timeline_path": "/path/to/timeline.otio",
        "clip_names": ["clip1.mov", "clip2.mov"]
      }
    ],
    "max_snapshots": 50
  }
}
```

### Timeline Tracker (`shots_dashboard/timeline_tracker.py`)

Automatically creates snapshots when `update_from_timeline()` is called:

```python
def update_from_timeline(self, timeline_path: Path):
    # ... update file states ...

    # Record timeline snapshot
    snapshot = TimelineSnapshot(
        timestamp=datetime.now(),
        timeline_path=timeline_path,
        clip_names=tuple(sorted(clip_names))
    )
    self.state.timeline_history = self.state.timeline_history.add_snapshot(snapshot)
```

### API Layer (`shots_dashboard/app.py`)

**GET /api/timeline_history**

Returns:
```json
{
  "success": true,
  "current": {
    "timeline_path": "/path/to/timeline.otio",
    "timestamp": "2024-11-04T12:00:00",
    "clips": ["clip1.mov", "clip2.mov"]
  },
  "historical_clips": ["clip3.mov", "clip4.mov"],
  "snapshots": [
    {
      "timeline_path": "/path/to/old_timeline.otio",
      "timestamp": "2024-11-04T11:00:00",
      "clips": ["clip3.mov", "clip4.mov"],
      "clip_count": 2
    }
  ]
}
```

### View Layer

**HTML** (`shots_dashboard/templates/index.html`)
- Timeline widget section with header
- Toggle switch for showing historical clips
- Current timeline info display
- Clip badge containers

**CSS** (`shots_dashboard/static/css/style.css`)
- Custom toggle switch styling
- Clip badge styling with hover effects
- Historical clip badges (red theme)
- Responsive layout

**JavaScript** (`shots_dashboard/static/js/dashboard.js`)
- Loads timeline history from API
- Updates UI with current and historical clips
- Handles toggle switch for showing/hiding historical clips
- Integrates with auto-refresh system (2-second polling)

```javascript
updateTimelineHistory(history) {
    // Update current timeline display
    // Update historical clips display
}

toggleHistoricalTimeline(show) {
    // Show/hide historical section
}
```

## User Workflow

1. **Scan Directory** - Discover media files
2. **Update from Timeline** - Load timeline and update file states
   - Timeline snapshot is automatically recorded
   - Widget shows current timeline contents
3. **Update Again** - Load a different timeline version
   - New snapshot is recorded
   - Widget updates to show new current timeline
   - Historical clips section shows clips from previous timeline that aren't in current
4. **Toggle Historical** - Click toggle to show/hide historical clips

## Testing

### Unit Tests (11 tests) - `tests/test_timeline_history.py`
- TimelineSnapshot creation and immutability
- TimelineHistory snapshot management
- Historical clip calculation
- Max snapshots limit enforcement

### Integration Tests (4 tests) - `tests/test_timeline_history_integration.py`
- Timeline history tracking through multiple updates
- Persistence across database reloads
- API endpoint functionality
- Empty state handling

### Test Results
```
74 tests passing (59 existing + 15 new)
- 11 timeline history unit tests
- 4 timeline history integration tests
- All existing tests still passing
```

## Design Principles

### Separation of Concerns
- **Model**: Pure data structures, no I/O
- **Database**: Persistence logic only
- **Tracker**: Business logic for snapshots
- **API**: HTTP endpoints and JSON serialization
- **View**: UI rendering and user interaction

### Immutability
- All timeline history structures are frozen dataclasses
- Modifications create new instances rather than mutating
- Makes state changes predictable and testable
- Prevents accidental modifications

### Type Safety
- Full type hints throughout
- Enums for states
- Frozen dataclasses for data integrity
- Pattern matching for exhaustive handling

## Future Enhancements

Potential improvements for future versions:

1. **Snapshot Details View**
   - Click on historical snapshot to see full details
   - Compare snapshots side-by-side

2. **Timeline Diff View**
   - Visual diff between timeline versions
   - Highlight added/removed clips

3. **Export Timeline History**
   - Export history to CSV or JSON
   - Generate timeline change report

4. **Configurable History Limit**
   - Allow users to configure max_snapshots
   - Add UI setting for history retention

5. **Search and Filter**
   - Search clips within timeline history
   - Filter by date range or timeline name

## API Documentation

### GET /api/timeline_history

Get timeline history including current and historical clips.

**Response:**
- `success` (boolean): Operation success status
- `current` (object | null): Current timeline snapshot
  - `timeline_path` (string): Path to timeline file
  - `timestamp` (string): ISO timestamp of last update
  - `clips` (array): List of clip names in current timeline
- `historical_clips` (array): Clips that were in history but not in current
- `snapshots` (array): Historical timeline snapshots (excluding current)
  - `timeline_path` (string): Path to timeline file
  - `timestamp` (string): ISO timestamp
  - `clips` (array): Clip names in this snapshot
  - `clip_count` (number): Number of clips

**Example:**
```bash
curl http://localhost:5000/api/timeline_history
```

## Summary

The timeline widget successfully tracks and displays timeline history with:
- ✅ Proper model/view separation
- ✅ Immutable data structures
- ✅ Automatic snapshot recording
- ✅ Database persistence
- ✅ Clean REST API
- ✅ Interactive UI with toggle
- ✅ Comprehensive test coverage (15 new tests)
- ✅ Auto-refresh integration

All 74 tests passing, including the new timeline history feature!
