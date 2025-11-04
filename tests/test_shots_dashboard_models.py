"""Tests for data models."""

from datetime import datetime
from pathlib import Path

import pytest

from shots_dashboard.models import (
    FileRecord,
    FileState,
    StateTransition,
    TrackerState,
)


class TestFileState:
    """Test FileState enum."""

    def test_all_states_exist(self) -> None:
        """Ensure all expected states are defined."""
        assert FileState.NEW
        assert FileState.IN_USE
        assert FileState.REMOVED

    def test_string_representation(self) -> None:
        """Test string conversion."""
        assert str(FileState.NEW) == "new"
        assert str(FileState.IN_USE) == "in_use"
        assert str(FileState.REMOVED) == "removed"


class TestFileRecord:
    """Test FileRecord dataclass."""

    def test_creation(self) -> None:
        """Test creating a file record."""
        path = Path("/test/file.mov")
        now = datetime.now()
        record = FileRecord(path=path, state=FileState.NEW, last_updated=now)

        assert record.path == path
        assert record.state == FileState.NEW
        assert record.last_updated == now

    def test_immutability(self) -> None:
        """Test that FileRecord is frozen (immutable)."""
        record = FileRecord(
            path=Path("/test/file.mov"),
            state=FileState.NEW,
            last_updated=datetime.now()
        )

        with pytest.raises(AttributeError):
            record.state = FileState.IN_USE  # type: ignore

    def test_with_state(self) -> None:
        """Test creating new record with updated state."""
        original = FileRecord(
            path=Path("/test/file.mov"),
            state=FileState.NEW,
            last_updated=datetime(2024, 1, 1)
        )

        updated = original.with_state(FileState.IN_USE)

        # Original unchanged
        assert original.state == FileState.NEW
        assert original.last_updated == datetime(2024, 1, 1)

        # New record has updated state and time
        assert updated.state == FileState.IN_USE
        assert updated.last_updated > original.last_updated
        assert updated.path == original.path


class TestTrackerState:
    """Test TrackerState."""

    def test_creation(self) -> None:
        """Test creating tracker state."""
        state = TrackerState()
        assert len(state.files) == 0
        assert state.timeline_path is None
        assert state.last_scan is None

    def test_update_file(self) -> None:
        """Test adding/updating files."""
        state = TrackerState()
        record = FileRecord(
            path=Path("/test/file.mov"),
            state=FileState.NEW,
            last_updated=datetime.now()
        )

        state.update_file(record)
        assert len(state.files) == 1
        assert state.get_file(Path("/test/file.mov")) == record

    def test_get_files_by_state(self) -> None:
        """Test filtering files by state."""
        state = TrackerState()

        file1 = FileRecord(Path("/test/new.mov"), FileState.NEW, datetime.now())
        file2 = FileRecord(Path("/test/used.mov"), FileState.IN_USE, datetime.now())
        file3 = FileRecord(Path("/test/removed.mov"), FileState.REMOVED, datetime.now())

        state.update_file(file1)
        state.update_file(file2)
        state.update_file(file3)

        assert state.get_files_by_state(FileState.NEW) == [file1]
        assert state.get_files_by_state(FileState.IN_USE) == [file2]
        assert state.get_files_by_state(FileState.REMOVED) == [file3]

    def test_property_shortcuts(self) -> None:
        """Test property shortcuts for file lists."""
        state = TrackerState()

        file1 = FileRecord(Path("/test/new.mov"), FileState.NEW, datetime.now())
        file2 = FileRecord(Path("/test/used.mov"), FileState.IN_USE, datetime.now())
        file3 = FileRecord(Path("/test/removed.mov"), FileState.REMOVED, datetime.now())

        state.update_file(file1)
        state.update_file(file2)
        state.update_file(file3)

        assert state.new_files == [file1]
        assert state.in_use_files == [file2]
        assert state.removed_files == [file3]

    def test_sorting(self) -> None:
        """Test that files are sorted by path."""
        state = TrackerState()

        file_z = FileRecord(Path("/test/z.mov"), FileState.NEW, datetime.now())
        file_a = FileRecord(Path("/test/a.mov"), FileState.NEW, datetime.now())
        file_m = FileRecord(Path("/test/m.mov"), FileState.NEW, datetime.now())

        state.update_file(file_z)
        state.update_file(file_a)
        state.update_file(file_m)

        files = state.new_files
        assert files[0].path.name == "a.mov"
        assert files[1].path.name == "m.mov"
        assert files[2].path.name == "z.mov"


class TestStateTransition:
    """Test StateTransition."""

    def test_creation(self) -> None:
        """Test creating a transition."""
        path = Path("/test/file.mov")
        transition = StateTransition(
            path=path,
            old_state=FileState.NEW,
            new_state=FileState.IN_USE
        )

        assert transition.path == path
        assert transition.old_state == FileState.NEW
        assert transition.new_state == FileState.IN_USE
        assert isinstance(transition.timestamp, datetime)

    def test_creation_from_none(self) -> None:
        """Test transition from no previous state."""
        transition = StateTransition(
            path=Path("/test/file.mov"),
            old_state=None,
            new_state=FileState.NEW
        )

        assert transition.old_state is None
        assert transition.new_state == FileState.NEW

    def test_immutability(self) -> None:
        """Test that StateTransition is frozen."""
        transition = StateTransition(
            path=Path("/test/file.mov"),
            old_state=FileState.NEW,
            new_state=FileState.IN_USE
        )

        with pytest.raises(AttributeError):
            transition.new_state = FileState.REMOVED  # type: ignore

    def test_string_representation(self) -> None:
        """Test string conversion."""
        transition = StateTransition(
            path=Path("/test/file.mov"),
            old_state=FileState.NEW,
            new_state=FileState.IN_USE
        )

        assert "file.mov" in str(transition)
        assert "new" in str(transition)
        assert "in_use" in str(transition)
        assert "→" in str(transition)
