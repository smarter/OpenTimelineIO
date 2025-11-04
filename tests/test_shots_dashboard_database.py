"""Tests for database module."""

import json
from datetime import datetime
from pathlib import Path

import pytest

from shots_dashboard.database import Database, DatabaseError
from shots_dashboard.models import FileRecord, FileState, TrackerState


@pytest.fixture
def temp_db(tmp_path: Path) -> Path:
    """Create a temporary database path."""
    return tmp_path / "test_db.json"


@pytest.fixture
def db(temp_db: Path) -> Database:
    """Create a Database instance."""
    return Database(temp_db)


class TestDatabase:
    """Test Database class."""

    def test_creation_creates_file(self, temp_db: Path) -> None:
        """Test that creating database creates file."""
        assert not temp_db.exists()
        db = Database(temp_db)
        assert temp_db.exists()

    def test_initial_state(self, db: Database) -> None:
        """Test initial state is empty."""
        state = db.load()
        assert len(state.files) == 0
        assert state.timeline_path is None
        assert state.last_scan is None

    def test_save_and_load(self, db: Database) -> None:
        """Test saving and loading state."""
        # Create state
        state = TrackerState()
        record = FileRecord(
            path=Path("/test/file.mov"),
            state=FileState.IN_USE,
            last_updated=datetime(2024, 1, 1, 12, 0, 0)
        )
        state.update_file(record)
        state.timeline_path = Path("/test/timeline.otio")
        state.last_scan = datetime(2024, 1, 1, 12, 0, 0)

        # Save
        db.save(state)

        # Load
        loaded_state = db.load()

        assert len(loaded_state.files) == 1
        loaded_record = loaded_state.get_file(Path("/test/file.mov"))
        assert loaded_record is not None
        assert loaded_record.state == FileState.IN_USE
        assert loaded_record.last_updated == datetime(2024, 1, 1, 12, 0, 0)
        assert loaded_state.timeline_path == Path("/test/timeline.otio")
        assert loaded_state.last_scan == datetime(2024, 1, 1, 12, 0, 0)

    def test_save_multiple_files(self, db: Database) -> None:
        """Test saving multiple files."""
        state = TrackerState()

        for i in range(5):
            record = FileRecord(
                path=Path(f"/test/file{i}.mov"),
                state=FileState.IN_USE,
                last_updated=datetime.now()
            )
            state.update_file(record)

        db.save(state)
        loaded_state = db.load()

        assert len(loaded_state.files) == 5

    def test_update_existing_file(self, db: Database) -> None:
        """Test updating an existing file's state."""
        state = TrackerState()
        path = Path("/test/file.mov")

        # Initial save
        record1 = FileRecord(
            path=path,
            state=FileState.NEW,
            last_updated=datetime(2024, 1, 1)
        )
        state.update_file(record1)
        db.save(state)

        # Update
        record2 = record1.with_state(FileState.IN_USE)
        state.update_file(record2)
        db.save(state)

        # Load and verify
        loaded_state = db.load()
        loaded_record = loaded_state.get_file(path)
        assert loaded_record is not None
        assert loaded_record.state == FileState.IN_USE

    def test_reset(self, db: Database) -> None:
        """Test resetting database."""
        # Add some data
        state = TrackerState()
        record = FileRecord(
            path=Path("/test/file.mov"),
            state=FileState.IN_USE,
            last_updated=datetime.now()
        )
        state.update_file(record)
        db.save(state)

        # Reset
        db.reset()

        # Verify empty
        loaded_state = db.load()
        assert len(loaded_state.files) == 0
        assert loaded_state.timeline_path is None
        assert loaded_state.last_scan is None

    def test_load_corrupted_file(self, temp_db: Path) -> None:
        """Test loading corrupted database file."""
        # Create corrupted JSON
        temp_db.parent.mkdir(parents=True, exist_ok=True)
        temp_db.write_text("{ invalid json }")

        db = Database(temp_db)
        with pytest.raises(DatabaseError):
            db.load()

    def test_load_invalid_record(self, temp_db: Path) -> None:
        """Test loading database with invalid record (should skip it)."""
        temp_db.parent.mkdir(parents=True, exist_ok=True)

        # Write data with one valid and one invalid record
        data = {
            "files": {
                "/test/good.mov": {
                    "path": "/test/good.mov",
                    "state": "IN_USE",
                    "last_updated": "2024-01-01T12:00:00"
                },
                "/test/bad.mov": {
                    "path": "/test/bad.mov",
                    "state": "INVALID_STATE",  # Invalid state
                    "last_updated": "2024-01-01T12:00:00"
                }
            },
            "timeline_path": None,
            "last_scan": None
        }

        temp_db.write_text(json.dumps(data))

        db = Database(temp_db)
        state = db.load()

        # Should have loaded only the valid record
        assert len(state.files) == 1
        assert state.get_file(Path("/test/good.mov")) is not None
        assert state.get_file(Path("/test/bad.mov")) is None

    def test_save_all_states(self, db: Database) -> None:
        """Test saving files in all states."""
        state = TrackerState()

        record_new = FileRecord(Path("/test/new.mov"), FileState.NEW, datetime.now())
        record_in_use = FileRecord(Path("/test/used.mov"), FileState.IN_USE, datetime.now())
        record_removed = FileRecord(Path("/test/removed.mov"), FileState.REMOVED, datetime.now())

        state.update_file(record_new)
        state.update_file(record_in_use)
        state.update_file(record_removed)

        db.save(state)
        loaded_state = db.load()

        assert len(loaded_state.new_files) == 1
        assert len(loaded_state.in_use_files) == 1
        assert len(loaded_state.removed_files) == 1
