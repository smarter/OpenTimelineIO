"""
Tests for re-evaluating existing NEW files for NEWER_PROJECT state.

When .prproj files are scanned, existing NEW files should be promoted
to NEWER_PROJECT if they appear in a .prproj file that's newer than
the current timeline.
"""

import gzip
import tempfile
from datetime import datetime
from pathlib import Path

import pytest

from models import FileRecord, FileState, TrackerState
from timeline_tracker import TimelineTracker


def create_test_prproj(path: Path, media_files: list[str]) -> None:
    """Create a test .prproj file with media references."""
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<PremiereData>\n'

    for media_file in media_files:
        xml_content += f'  <Media>\n    <Title>{media_file}</Title>\n  </Media>\n'

    xml_content += '</PremiereData>'

    # Write as gzipped content
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        f.write(xml_content)


def test_reevaluate_new_files_to_newer_project():
    """Test that existing NEW files are promoted to NEWER_PROJECT when found in newer .prproj."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create media directory with a video file
        media_dir = tmpdir / "media"
        media_dir.mkdir()
        video_file = media_dir / "test_clip.mov"
        video_file.touch()

        # Create watch directory with timeline and .prproj
        watch_dir = tmpdir / "watch"
        watch_dir.mkdir()

        # Create timeline file (older)
        timeline = watch_dir / "timeline.otio"
        timeline.touch()

        # Wait a bit to ensure different mtimes
        import time
        time.sleep(0.01)

        # Create .prproj file (newer than timeline, contains the video)
        newer_prproj = watch_dir / "newer_project.prproj"
        create_test_prproj(newer_prproj, ["test_clip.mov"])

        # Create initial state with the file as NEW
        state = TrackerState(timeline_path=timeline)
        state.files[video_file] = FileRecord(
            path=video_file,
            state=FileState.NEW,
            last_updated=datetime.now()
        )

        # Create tracker and scan
        tracker = TimelineTracker(state)
        transitions = tracker.scan_directory(media_dir, watch_dir=watch_dir)

        # Should have one transition: NEW -> NEWER_PROJECT
        assert len(transitions) == 1
        assert transitions[0].path == video_file
        assert transitions[0].old_state == FileState.NEW
        assert transitions[0].new_state == FileState.NEWER_PROJECT

        # File should now be NEWER_PROJECT in state
        assert state.files[video_file].state == FileState.NEWER_PROJECT


def test_reevaluate_only_new_files():
    """Test that only NEW files are re-evaluated, not IN_USE or REMOVED."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create media directory with multiple files
        media_dir = tmpdir / "media"
        media_dir.mkdir()
        new_file = media_dir / "new_clip.mov"
        in_use_file = media_dir / "in_use_clip.mov"
        removed_file = media_dir / "removed_clip.mov"

        for f in [new_file, in_use_file, removed_file]:
            f.touch()

        # Create watch directory with .prproj containing all files
        watch_dir = tmpdir / "watch"
        watch_dir.mkdir()

        timeline = watch_dir / "timeline.otio"
        timeline.touch()

        import time
        time.sleep(0.01)

        newer_prproj = watch_dir / "newer_project.prproj"
        create_test_prproj(newer_prproj, [
            "new_clip.mov",
            "in_use_clip.mov",
            "removed_clip.mov"
        ])

        # Create state with files in different states
        state = TrackerState(timeline_path=timeline)
        state.files[new_file] = FileRecord(
            path=new_file,
            state=FileState.NEW,
            last_updated=datetime.now()
        )
        state.files[in_use_file] = FileRecord(
            path=in_use_file,
            state=FileState.IN_USE,
            last_updated=datetime.now()
        )
        state.files[removed_file] = FileRecord(
            path=removed_file,
            state=FileState.REMOVED,
            last_updated=datetime.now()
        )

        # Scan
        tracker = TimelineTracker(state)
        transitions = tracker.scan_directory(media_dir, watch_dir=watch_dir)

        # Only NEW file should transition to NEWER_PROJECT
        assert len(transitions) == 1
        assert transitions[0].path == new_file
        assert transitions[0].new_state == FileState.NEWER_PROJECT

        # Other files should remain unchanged
        assert state.files[in_use_file].state == FileState.IN_USE
        assert state.files[removed_file].state == FileState.REMOVED


def test_no_reevaluate_without_prproj():
    """Test that files are not re-evaluated when no .prproj data is available."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create media directory with a file
        media_dir = tmpdir / "media"
        media_dir.mkdir()
        video_file = media_dir / "test_clip.mov"
        video_file.touch()

        # Create state with file as NEW
        state = TrackerState()
        state.files[video_file] = FileRecord(
            path=video_file,
            state=FileState.NEW,
            last_updated=datetime.now()
        )

        # Scan without watch_dir (no .prproj data)
        tracker = TimelineTracker(state)
        transitions = tracker.scan_directory(media_dir, watch_dir=None)

        # Should have no transitions
        assert len(transitions) == 0

        # File should remain NEW
        assert state.files[video_file].state == FileState.NEW


def test_reevaluate_file_not_in_newer_project():
    """Test that NEW files not in newer .prproj remain as NEW."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create media directory with a file
        media_dir = tmpdir / "media"
        media_dir.mkdir()
        video_file = media_dir / "test_clip.mov"
        video_file.touch()

        # Create watch directory with .prproj NOT containing the file
        watch_dir = tmpdir / "watch"
        watch_dir.mkdir()

        timeline = watch_dir / "timeline.otio"
        timeline.touch()

        import time
        time.sleep(0.01)

        newer_prproj = watch_dir / "newer_project.prproj"
        create_test_prproj(newer_prproj, ["other_clip.mov"])  # Different file

        # Create state with file as NEW
        state = TrackerState(timeline_path=timeline)
        state.files[video_file] = FileRecord(
            path=video_file,
            state=FileState.NEW,
            last_updated=datetime.now()
        )

        # Scan
        tracker = TimelineTracker(state)
        transitions = tracker.scan_directory(media_dir, watch_dir=watch_dir)

        # Should have no transitions
        assert len(transitions) == 0

        # File should remain NEW
        assert state.files[video_file].state == FileState.NEW


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
