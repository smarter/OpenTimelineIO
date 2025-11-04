#!/usr/bin/env python
"""Core tests for shots dashboard (no OTIO dependency)."""

from pathlib import Path
from datetime import datetime
import tempfile

from shots_dashboard.models import FileState, FileRecord, TrackerState, StateTransition
from shots_dashboard.database import Database


def test_models():
    """Test data models."""
    print("Testing models...")

    # Test FileState
    assert FileState.NEW
    assert str(FileState.IN_USE) == "in_use"
    print("  ✓ FileState enum works")

    # Test FileRecord
    record = FileRecord(
        path=Path("/test/file.mov"),
        state=FileState.NEW,
        last_updated=datetime.now()
    )
    assert record.state == FileState.NEW
    print("  ✓ FileRecord creation works")

    # Test immutability
    try:
        record.state = FileState.IN_USE  # Should fail
        assert False, "Should not allow mutation"
    except AttributeError:
        print("  ✓ FileRecord immutability enforced")

    # Test with_state
    new_record = record.with_state(FileState.IN_USE)
    assert record.state == FileState.NEW
    assert new_record.state == FileState.IN_USE
    print("  ✓ FileRecord.with_state() works")

    # Test TrackerState
    state = TrackerState()
    state.update_file(record)
    assert len(state.files) == 1
    assert len(state.new_files) == 1
    print("  ✓ TrackerState works")

    # Test file grouping
    record2 = FileRecord(Path("/test/file2.mov"), FileState.IN_USE, datetime.now())
    record3 = FileRecord(Path("/test/file3.mov"), FileState.REMOVED, datetime.now())
    state.update_file(record2)
    state.update_file(record3)

    assert len(state.new_files) == 1
    assert len(state.in_use_files) == 1
    assert len(state.removed_files) == 1
    print("  ✓ File grouping by state works")

    # Test StateTransition
    transition = StateTransition(
        path=Path("/test/file.mov"),
        old_state=FileState.NEW,
        new_state=FileState.IN_USE
    )
    assert "new" in str(transition)
    assert "in_use" in str(transition)
    print("  ✓ StateTransition works")

    # Test transition immutability
    try:
        transition.new_state = FileState.REMOVED  # Should fail
        assert False, "Should not allow mutation"
    except AttributeError:
        print("  ✓ StateTransition immutability enforced")


def test_database():
    """Test database operations."""
    print("\nTesting database...")

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.json"
        db = Database(db_path)
        print("  ✓ Database creation works")

        # Verify file was created
        assert db_path.exists()
        print("  ✓ Database file created")

        # Test load initial state
        state = db.load()
        assert len(state.files) == 0
        print("  ✓ Database load works")

        # Test save and load
        record = FileRecord(
            path=Path("/test/file.mov"),
            state=FileState.IN_USE,
            last_updated=datetime(2024, 1, 1, 12, 0, 0)
        )
        state.update_file(record)
        state.timeline_path = Path("/test/timeline.otio")
        state.last_scan = datetime(2024, 1, 1, 13, 0, 0)

        db.save(state)
        print("  ✓ Database save works")

        loaded_state = db.load()
        assert len(loaded_state.files) == 1
        loaded_record = loaded_state.get_file(Path("/test/file.mov"))
        assert loaded_record is not None
        assert loaded_record.state == FileState.IN_USE
        assert loaded_record.last_updated == datetime(2024, 1, 1, 12, 0, 0)
        assert loaded_state.timeline_path == Path("/test/timeline.otio")
        assert loaded_state.last_scan == datetime(2024, 1, 1, 13, 0, 0)
        print("  ✓ Database persistence works")

        # Test saving multiple states
        for i in range(5):
            rec = FileRecord(
                path=Path(f"/test/file{i}.mov"),
                state=FileState.NEW,
                last_updated=datetime.now()
            )
            state.update_file(rec)

        db.save(state)
        loaded_state = db.load()
        assert len(loaded_state.files) == 6  # 1 original + 5 new
        print("  ✓ Multiple file persistence works")

        # Test reset
        db.reset()
        loaded_state = db.load()
        assert len(loaded_state.files) == 0
        assert loaded_state.timeline_path is None
        print("  ✓ Database reset works")


def test_state_transitions():
    """Test all valid state transitions."""
    print("\nTesting state transitions...")

    # Create records in each state
    new_record = FileRecord(Path("/new.mov"), FileState.NEW, datetime.now())
    in_use_record = FileRecord(Path("/used.mov"), FileState.IN_USE, datetime.now())
    removed_record = FileRecord(Path("/removed.mov"), FileState.REMOVED, datetime.now())

    # Test NEW → IN_USE
    updated = new_record.with_state(FileState.IN_USE)
    assert updated.state == FileState.IN_USE
    print("  ✓ NEW → IN_USE transition works")

    # Test IN_USE → REMOVED
    updated = in_use_record.with_state(FileState.REMOVED)
    assert updated.state == FileState.REMOVED
    print("  ✓ IN_USE → REMOVED transition works")

    # Test REMOVED → IN_USE
    updated = removed_record.with_state(FileState.IN_USE)
    assert updated.state == FileState.IN_USE
    print("  ✓ REMOVED → IN_USE transition works")

    # Test that timestamp is updated
    import time
    time.sleep(0.01)
    updated = new_record.with_state(FileState.IN_USE)
    assert updated.last_updated > new_record.last_updated
    print("  ✓ Timestamp updated on state change")


def test_sorting():
    """Test that files are sorted correctly."""
    print("\nTesting sorting...")

    state = TrackerState()

    # Add files in random order
    files = [
        FileRecord(Path("/z_file.mov"), FileState.NEW, datetime.now()),
        FileRecord(Path("/a_file.mov"), FileState.NEW, datetime.now()),
        FileRecord(Path("/m_file.mov"), FileState.NEW, datetime.now()),
    ]

    for f in files:
        state.update_file(f)

    new_files = state.new_files
    assert new_files[0].path.name == "a_file.mov"
    assert new_files[1].path.name == "m_file.mov"
    assert new_files[2].path.name == "z_file.mov"
    print("  ✓ Files sorted by path")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Shots Dashboard Core Tests")
    print("=" * 60)

    try:
        test_models()
        test_database()
        test_state_transitions()
        test_sorting()

        print("\n" + "=" * 60)
        print("✅ All core tests passed!")
        print("=" * 60)
        print("\nNote: Full tests with timeline tracking require OpenTimelineIO")
        print("to be built. Run 'python setup.py install' first, then use pytest")
        print("to run the complete test suite.")
        return 0

    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit(main())
