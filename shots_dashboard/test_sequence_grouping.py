"""
Tests for image sequence grouping functionality.
"""

import tempfile
from pathlib import Path
from datetime import datetime

import pytest

from models import FileRecord, FileState, TrackerState


def test_groups_multiple_images_into_sequence():
    """Test that multiple images in same directory are grouped as a sequence."""
    state = TrackerState()

    # Add multiple PNG files in same directory
    dir_path = Path("/test/shot001")
    state.update_file(FileRecord(
        path=dir_path / "frame_001.png",
        state=FileState.NEW,
        last_updated=datetime(2025, 1, 1, 10, 0, 0)
    ))
    state.update_file(FileRecord(
        path=dir_path / "frame_002.png",
        state=FileState.NEW,
        last_updated=datetime(2025, 1, 1, 10, 0, 1)
    ))
    state.update_file(FileRecord(
        path=dir_path / "frame_003.png",
        state=FileState.NEW,
        last_updated=datetime(2025, 1, 1, 10, 0, 2)
    ))

    # Get files as sequences
    sequences = state.get_files_as_sequences(FileState.NEW)

    # Should return single sequence
    assert len(sequences) == 1
    assert sequences[0].path == dir_path / "*.png"
    assert sequences[0].state == FileState.NEW
    # Should use most recent timestamp
    assert sequences[0].last_updated == datetime(2025, 1, 1, 10, 0, 2)


def test_keeps_single_image_as_individual_file():
    """Test that a single image file is not grouped."""
    state = TrackerState()

    # Add single PNG file
    single_file = Path("/test/single.png")
    state.update_file(FileRecord(
        path=single_file,
        state=FileState.NEW,
        last_updated=datetime(2025, 1, 1, 10, 0, 0)
    ))

    # Get files as sequences
    sequences = state.get_files_as_sequences(FileState.NEW)

    # Should keep as individual file
    assert len(sequences) == 1
    assert sequences[0].path == single_file


def test_groups_by_extension():
    """Test that images are grouped separately by extension."""
    state = TrackerState()

    # Add PNG and JPG files in same directory
    dir_path = Path("/test/mixed")
    state.update_file(FileRecord(
        path=dir_path / "frame_001.png",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))
    state.update_file(FileRecord(
        path=dir_path / "frame_002.png",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))
    state.update_file(FileRecord(
        path=dir_path / "thumb_001.jpg",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))
    state.update_file(FileRecord(
        path=dir_path / "thumb_002.jpg",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))

    # Get files as sequences
    sequences = state.get_files_as_sequences(FileState.NEW)

    # Should have two sequences (one for PNG, one for JPG)
    assert len(sequences) == 2
    sequence_paths = {s.path for s in sequences}
    assert dir_path / "*.png" in sequence_paths
    assert dir_path / "*.jpg" in sequence_paths


def test_groups_by_directory():
    """Test that images in different directories are grouped separately."""
    state = TrackerState()

    # Add images in different directories
    dir1 = Path("/test/shot001")
    dir2 = Path("/test/shot002")

    for i in range(3):
        state.update_file(FileRecord(
            path=dir1 / f"frame_{i:03d}.png",
            state=FileState.NEW,
            last_updated=datetime.now()
        ))
        state.update_file(FileRecord(
            path=dir2 / f"frame_{i:03d}.png",
            state=FileState.NEW,
            last_updated=datetime.now()
        ))

    # Get files as sequences
    sequences = state.get_files_as_sequences(FileState.NEW)

    # Should have two sequences (one per directory)
    assert len(sequences) == 2
    sequence_paths = {s.path for s in sequences}
    assert dir1 / "*.png" in sequence_paths
    assert dir2 / "*.png" in sequence_paths


def test_does_not_group_non_images():
    """Test that non-image files are not grouped."""
    state = TrackerState()

    # Add video files
    dir_path = Path("/test/videos")
    state.update_file(FileRecord(
        path=dir_path / "clip_001.mov",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))
    state.update_file(FileRecord(
        path=dir_path / "clip_002.mov",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))

    # Get files as sequences
    sequences = state.get_files_as_sequences(FileState.NEW)

    # Should keep as individual files (videos are not grouped)
    assert len(sequences) == 2
    assert all(s.path.suffix == '.mov' for s in sequences)


def test_mixed_images_and_videos():
    """Test that images are grouped but videos remain individual."""
    state = TrackerState()

    # Add images and videos
    dir_path = Path("/test/mixed")
    state.update_file(FileRecord(
        path=dir_path / "frame_001.png",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))
    state.update_file(FileRecord(
        path=dir_path / "frame_002.png",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))
    state.update_file(FileRecord(
        path=dir_path / "final.mov",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))

    # Get files as sequences
    sequences = state.get_files_as_sequences(FileState.NEW)

    # Should have 2 items: 1 sequence for PNGs, 1 individual MOV
    assert len(sequences) == 2

    png_sequence = next((s for s in sequences if s.path.name == "*.png"), None)
    mov_file = next((s for s in sequences if s.path.suffix == ".mov"), None)

    assert png_sequence is not None
    assert mov_file is not None
    assert mov_file.path.name == "final.mov"


def test_only_groups_files_in_same_state():
    """Test that only files in the requested state are grouped."""
    state = TrackerState()

    # Add images in different states
    dir_path = Path("/test/shot001")
    state.update_file(FileRecord(
        path=dir_path / "frame_001.png",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))
    state.update_file(FileRecord(
        path=dir_path / "frame_002.png",
        state=FileState.NEW,
        last_updated=datetime.now()
    ))
    state.update_file(FileRecord(
        path=dir_path / "frame_003.png",
        state=FileState.IN_USE,
        last_updated=datetime.now()
    ))

    # Get NEW files as sequences
    new_sequences = state.get_files_as_sequences(FileState.NEW)

    # Should group the 2 NEW files
    assert len(new_sequences) == 1
    assert new_sequences[0].path == dir_path / "*.png"

    # Get IN_USE files as sequences
    in_use_sequences = state.get_files_as_sequences(FileState.IN_USE)

    # Should keep single IN_USE file as individual
    assert len(in_use_sequences) == 1
    assert in_use_sequences[0].path == dir_path / "frame_003.png"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
