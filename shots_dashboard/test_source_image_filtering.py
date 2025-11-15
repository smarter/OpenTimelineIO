"""
Tests for source image filtering when videos are in timeline.
"""

import tempfile
from pathlib import Path
from datetime import datetime

import pytest
import opentimelineio as otio

from timeline_tracker import TimelineTracker
from models import FileState, TrackerState


def create_test_timeline(path: Path, clip_names: list[str]) -> None:
    """Create a test OTIO timeline with specified clips."""
    timeline = otio.schema.Timeline(name="Test Timeline")
    track = otio.schema.Track(name="Video", kind=otio.schema.TrackKind.Video)

    for clip_name in clip_names:
        clip = otio.schema.Clip(
            name=clip_name,
            media_reference=otio.schema.ExternalReference(target_url=clip_name)
        )
        track.append(clip)

    timeline.tracks.append(track)
    otio.adapters.write_to_file(timeline, str(path))


def test_ignores_source_images_when_video_exists():
    """Test that source images are ignored when corresponding video exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create directory structure
        # shot001.mov (video file)
        # shot001/ (directory with source images)
        #   frame_001.png
        #   frame_002.png
        video_file = tmpdir / "shot001.mov"
        video_file.touch()

        source_dir = tmpdir / "shot001"
        source_dir.mkdir()
        (source_dir / "frame_001.png").touch()
        (source_dir / "frame_002.png").touch()

        # Create tracker and scan
        state = TrackerState()
        tracker = TimelineTracker(state)

        # Scan - video exists, so source images should be ignored
        tracker.scan_directory(tmpdir)

        # Check that only the video is tracked, not the images
        all_files = list(tracker.state.files.keys())
        assert len(all_files) == 1  # only video file

        # Video should be tracked (as NEW since no timeline)
        video_record = tracker.state.get_file(video_file)
        assert video_record is not None
        assert video_record.state == FileState.NEW

        # Images should not be tracked
        for img in source_dir.glob("*.png"):
            assert tracker.state.get_file(img) is None


def test_tracks_images_when_video_doesnt_exist():
    """Test that source images ARE tracked when video doesn't exist yet."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create only source images, no video yet
        source_dir = tmpdir / "shot001"
        source_dir.mkdir()
        (source_dir / "frame_001.png").touch()
        (source_dir / "frame_002.png").touch()

        # Create tracker and scan (no video file)
        state = TrackerState()
        tracker = TimelineTracker(state)
        tracker.scan_directory(tmpdir)

        # Images should be tracked since video doesn't exist
        all_files = list(tracker.state.files.keys())
        assert len(all_files) == 2  # 2 images

        # All should be NEW
        for record in tracker.state.files.values():
            assert record.state == FileState.NEW


def test_removes_tracked_images_when_video_created():
    """Test that previously tracked images are removed when video is created."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create directory structure with only images first
        source_dir = tmpdir / "shot001"
        source_dir.mkdir()
        img1 = source_dir / "frame_001.png"
        img2 = source_dir / "frame_002.png"
        img1.touch()
        img2.touch()

        # Create tracker and scan
        state = TrackerState()
        tracker = TimelineTracker(state)
        tracker.scan_directory(tmpdir)

        # Initially only images tracked
        assert len(tracker.state.files) == 2

        # Now create the video file (simulating render completion)
        video_file = tmpdir / "shot001.mov"
        video_file.touch()

        # Scan again - images should be removed
        tracker.scan_directory(tmpdir)

        # Only video should be tracked
        assert len(tracker.state.files) == 1
        assert tracker.state.get_file(video_file) is not None
        assert tracker.state.get_file(img1) is None
        assert tracker.state.get_file(img2) is None


def test_only_ignores_png_jpg_in_matching_directory():
    """Test that only PNG/JPG in the matching directory are ignored."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create directory structure
        video_file = tmpdir / "shot001.mov"
        video_file.touch()

        # Images in matching directory (should be ignored)
        source_dir = tmpdir / "shot001"
        source_dir.mkdir()
        (source_dir / "frame.png").touch()

        # Images in different directory (should NOT be ignored)
        other_dir = tmpdir / "other"
        other_dir.mkdir()
        other_img = other_dir / "frame.png"
        other_img.touch()

        # Images at root level (should NOT be ignored)
        root_img = tmpdir / "root.png"
        root_img.touch()

        # Create tracker and scan
        state = TrackerState()
        tracker = TimelineTracker(state)
        tracker.scan_directory(tmpdir)

        # Video should be tracked
        video_record = tracker.state.get_file(video_file)
        assert video_record is not None

        # Images in shot001/ should NOT be tracked (filtered out)
        for img in source_dir.glob("*.png"):
            assert tracker.state.get_file(img) is None

        # Images in other directories SHOULD be tracked
        assert tracker.state.get_file(other_img) is not None
        assert tracker.state.get_file(root_img) is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
