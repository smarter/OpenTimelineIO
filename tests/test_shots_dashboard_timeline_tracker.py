"""Tests for timeline tracker."""

from datetime import datetime
from pathlib import Path

import opentimelineio as otio
import pytest

from shots_dashboard.models import FileState, TrackerState
from shots_dashboard.timeline_tracker import TimelineTracker


@pytest.fixture
def temp_media_dir(tmp_path: Path) -> Path:
    """Create temporary media directory with test files."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()

    # Create test files
    (media_dir / "shot_001.mov").touch()
    (media_dir / "shot_002.mp4").touch()
    (media_dir / "shot_003.mov").touch()
    (media_dir / "audio.wav").touch()

    return media_dir


@pytest.fixture
def tracker() -> TimelineTracker:
    """Create a TimelineTracker instance."""
    state = TrackerState()
    return TimelineTracker(state)


@pytest.fixture
def timeline_file(tmp_path: Path) -> Path:
    """Create a test OTIO timeline."""
    timeline = otio.schema.Timeline(name="test_timeline")
    track = otio.schema.Track(name="video")

    # Add some clips
    clip1 = otio.schema.Clip(name="shot_001.mov")
    clip2 = otio.schema.Clip(name="shot_002.mp4")

    track.append(clip1)
    track.append(clip2)
    timeline.tracks.append(track)

    # Save to file
    timeline_path = tmp_path / "timeline.otio"
    otio.adapters.write_to_file(timeline, str(timeline_path))

    return timeline_path


class TestTimelineTracker:
    """Test TimelineTracker class."""

    def test_scan_directory(self, tracker: TimelineTracker, temp_media_dir: Path) -> None:
        """Test scanning directory for media files."""
        transitions = tracker.scan_directory(temp_media_dir)

        # Should find 4 files
        assert len(transitions) == 4
        assert len(tracker.state.files) == 4

        # All should be in NEW state
        assert len(tracker.state.new_files) == 4
        assert len(tracker.state.in_use_files) == 0
        assert len(tracker.state.removed_files) == 0

        # Check transitions
        for transition in transitions:
            assert transition.old_state is None
            assert transition.new_state == FileState.NEW

    def test_scan_with_extensions(self, tracker: TimelineTracker, temp_media_dir: Path) -> None:
        """Test scanning with specific extensions."""
        # Only scan for .mov files
        transitions = tracker.scan_directory(temp_media_dir, extensions={'.mov'})

        # Should find only 2 .mov files
        assert len(tracker.state.files) == 2

        for file_record in tracker.state.files.values():
            assert file_record.path.suffix == '.mov'

    def test_scan_nonexistent_directory(self, tracker: TimelineTracker) -> None:
        """Test scanning nonexistent directory."""
        with pytest.raises(ValueError, match="does not exist"):
            tracker.scan_directory(Path("/nonexistent/path"))

    def test_scan_updates_timestamp(self, tracker: TimelineTracker, temp_media_dir: Path) -> None:
        """Test that scan updates last_scan timestamp."""
        assert tracker.state.last_scan is None

        tracker.scan_directory(temp_media_dir)

        assert tracker.state.last_scan is not None
        assert isinstance(tracker.state.last_scan, datetime)

    def test_extract_clips_from_timeline(self, tracker: TimelineTracker, timeline_file: Path) -> None:
        """Test extracting clip names from timeline."""
        clip_names = tracker.extract_clips_from_timeline(timeline_file)

        assert len(clip_names) == 2
        assert "shot_001.mov" in clip_names
        assert "shot_002.mp4" in clip_names

    def test_extract_clips_nonexistent_file(self, tracker: TimelineTracker) -> None:
        """Test extracting from nonexistent timeline."""
        with pytest.raises(ValueError, match="does not exist"):
            tracker.extract_clips_from_timeline(Path("/nonexistent/timeline.otio"))

    def test_update_from_timeline_new_to_in_use(
        self,
        tracker: TimelineTracker,
        temp_media_dir: Path,
        timeline_file: Path
    ) -> None:
        """Test NEW → IN_USE transition."""
        # First scan directory
        tracker.scan_directory(temp_media_dir)
        assert len(tracker.state.new_files) == 4

        # Update from timeline
        transitions = tracker.update_from_timeline(timeline_file)

        # shot_001.mov and shot_002.mp4 should transition to IN_USE
        in_use_transitions = [
            t for t in transitions
            if t.new_state == FileState.IN_USE
        ]
        assert len(in_use_transitions) == 2

        # Check states
        assert len(tracker.state.in_use_files) == 2
        assert len(tracker.state.new_files) == 2  # shot_003.mov and audio.wav

    def test_update_from_timeline_in_use_stays_in_use(
        self,
        tracker: TimelineTracker,
        temp_media_dir: Path,
        timeline_file: Path
    ) -> None:
        """Test IN_USE → IN_USE (no change)."""
        # Scan and update
        tracker.scan_directory(temp_media_dir)
        tracker.update_from_timeline(timeline_file)

        # Update again with same timeline
        transitions = tracker.update_from_timeline(timeline_file)

        # No transitions should occur for files already IN_USE
        assert len(transitions) == 0
        assert len(tracker.state.in_use_files) == 2

    def test_update_from_timeline_in_use_to_removed(
        self,
        tracker: TimelineTracker,
        temp_media_dir: Path,
        timeline_file: Path,
        tmp_path: Path
    ) -> None:
        """Test IN_USE → REMOVED transition."""
        # Scan and update
        tracker.scan_directory(temp_media_dir)
        tracker.update_from_timeline(timeline_file)
        assert len(tracker.state.in_use_files) == 2

        # Create new timeline without shot_001.mov
        new_timeline = otio.schema.Timeline(name="updated_timeline")
        track = otio.schema.Track(name="video")
        clip = otio.schema.Clip(name="shot_002.mp4")
        track.append(clip)
        new_timeline.tracks.append(track)

        new_timeline_path = tmp_path / "timeline_updated.otio"
        otio.adapters.write_to_file(new_timeline, str(new_timeline_path))

        # Update from new timeline
        transitions = tracker.update_from_timeline(new_timeline_path)

        # shot_001.mov should transition to REMOVED
        removed_transitions = [
            t for t in transitions
            if t.new_state == FileState.REMOVED
        ]
        assert len(removed_transitions) == 1
        assert "shot_001.mov" in str(removed_transitions[0].path)

        assert len(tracker.state.in_use_files) == 1
        assert len(tracker.state.removed_files) == 1

    def test_update_from_timeline_removed_to_in_use(
        self,
        tracker: TimelineTracker,
        temp_media_dir: Path,
        timeline_file: Path,
        tmp_path: Path
    ) -> None:
        """Test REMOVED → IN_USE transition (file comes back)."""
        # Scan directory
        tracker.scan_directory(temp_media_dir)

        # Use timeline with shot_001.mov
        tracker.update_from_timeline(timeline_file)
        assert len(tracker.state.in_use_files) == 2

        # Create timeline without shot_001.mov
        timeline_without = otio.schema.Timeline(name="timeline_without")
        track = otio.schema.Track(name="video")
        clip = otio.schema.Clip(name="shot_002.mp4")
        track.append(clip)
        timeline_without.tracks.append(track)

        timeline_without_path = tmp_path / "timeline_without.otio"
        otio.adapters.write_to_file(timeline_without, str(timeline_without_path))

        tracker.update_from_timeline(timeline_without_path)
        assert len(tracker.state.removed_files) == 1

        # Now use original timeline again (shot_001.mov is back)
        transitions = tracker.update_from_timeline(timeline_file)

        # shot_001.mov should transition back to IN_USE
        back_in_use = [
            t for t in transitions
            if t.new_state == FileState.IN_USE and "shot_001" in str(t.path)
        ]
        assert len(back_in_use) == 1

        assert len(tracker.state.in_use_files) == 2
        assert len(tracker.state.removed_files) == 0

    def test_get_stats(self, tracker: TimelineTracker, temp_media_dir: Path, timeline_file: Path) -> None:
        """Test getting statistics."""
        # Initial state
        stats = tracker.get_stats()
        assert stats["total"] == 0
        assert stats["new"] == 0
        assert stats["in_use"] == 0
        assert stats["removed"] == 0

        # After scanning
        tracker.scan_directory(temp_media_dir)
        stats = tracker.get_stats()
        assert stats["total"] == 4
        assert stats["new"] == 4

        # After timeline update
        tracker.update_from_timeline(timeline_file)
        stats = tracker.get_stats()
        assert stats["total"] == 4
        assert stats["new"] == 2
        assert stats["in_use"] == 2
        assert stats["removed"] == 0

    def test_pattern_matching_all_transitions(
        self,
        tracker: TimelineTracker,
        temp_media_dir: Path,
        timeline_file: Path,
        tmp_path: Path
    ) -> None:
        """Test that all state transitions work correctly via pattern matching."""
        # Scan directory (all files → NEW)
        tracker.scan_directory(temp_media_dir)

        # Create timeline with shot_001
        timeline_with_001 = otio.schema.Timeline(name="with_001")
        track = otio.schema.Track(name="video")
        track.append(otio.schema.Clip(name="shot_001.mov"))
        timeline_with_001.tracks.append(track)
        timeline_001_path = tmp_path / "timeline_001.otio"
        otio.adapters.write_to_file(timeline_with_001, str(timeline_001_path))

        # NEW → IN_USE
        transitions = tracker.update_from_timeline(timeline_001_path)
        assert any(
            t.old_state == FileState.NEW and t.new_state == FileState.IN_USE
            for t in transitions
        )

        # IN_USE → IN_USE (update with same timeline)
        transitions = tracker.update_from_timeline(timeline_001_path)
        # No transitions for shot_001 since it stays IN_USE
        shot_001_transitions = [t for t in transitions if "shot_001" in str(t.path)]
        assert len(shot_001_transitions) == 0

        # Create empty timeline
        empty_timeline = otio.schema.Timeline(name="empty")
        empty_timeline.tracks.append(otio.schema.Track(name="video"))
        empty_timeline_path = tmp_path / "empty.otio"
        otio.adapters.write_to_file(empty_timeline, str(empty_timeline_path))

        # IN_USE → REMOVED
        transitions = tracker.update_from_timeline(empty_timeline_path)
        assert any(
            t.old_state == FileState.IN_USE and t.new_state == FileState.REMOVED
            for t in transitions
        )

        # REMOVED → REMOVED (update with same empty timeline)
        transitions = tracker.update_from_timeline(empty_timeline_path)
        assert len(transitions) == 0  # No changes

        # REMOVED → IN_USE (bring file back)
        transitions = tracker.update_from_timeline(timeline_001_path)
        assert any(
            t.old_state == FileState.REMOVED and t.new_state == FileState.IN_USE
            for t in transitions
        )

        # NEW → NEW (files never used stay NEW)
        # shot_003 should still be NEW
        shot_003 = tracker.state.get_file(temp_media_dir / "shot_003.mov")
        assert shot_003 is not None
        assert shot_003.state == FileState.NEW
