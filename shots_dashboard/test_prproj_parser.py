"""
Tests for Adobe Premiere Pro project file parsing.
"""

import gzip
import tempfile
from pathlib import Path

import pytest

from prproj_parser import extract_media_filenames, scan_prproj_files, was_in_older_project, is_in_newer_project


def create_test_prproj(path: Path, media_files: list[str]) -> None:
    """Create a test .prproj file with media references."""
    xml_content = '<?xml version="1.0" encoding="UTF-8"?>\n<PremiereData>\n'

    for media_file in media_files:
        xml_content += f'  <Media>\n    <Title>{media_file}</Title>\n  </Media>\n'

    xml_content += '</PremiereData>'

    # Write as gzipped content
    with gzip.open(path, 'wt', encoding='utf-8') as f:
        f.write(xml_content)


def test_extract_media_filenames():
    """Test extracting media filenames from a .prproj file."""
    with tempfile.TemporaryDirectory() as tmpdir:
        prproj_path = Path(tmpdir) / "test.prproj"

        # Create test project with media files
        create_test_prproj(prproj_path, [
            "clip1.mov",
            "clip2.mp4",
            "/absolute/path/to/clip3.wav"
        ])

        # Extract filenames
        filenames = extract_media_filenames(prproj_path)

        # Should extract just the filename, not the path
        assert "clip1.mov" in filenames
        assert "clip2.mp4" in filenames
        assert "clip3.wav" in filenames
        assert len(filenames) == 3


def test_scan_prproj_files():
    """Test scanning a directory for .prproj files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create multiple project files
        proj1 = tmpdir / "project1.prproj"
        proj2 = tmpdir / "subdir" / "project2.prproj"
        proj2.parent.mkdir(parents=True)

        create_test_prproj(proj1, ["clip1.mov", "clip2.mp4"])
        create_test_prproj(proj2, ["clip3.wav"])

        # Scan directory
        prproj_media = scan_prproj_files(tmpdir)

        # Should find both projects
        assert len(prproj_media) == 2
        assert proj1 in prproj_media
        assert proj2 in prproj_media

        # Check extracted files
        assert "clip1.mov" in prproj_media[proj1]
        assert "clip2.mp4" in prproj_media[proj1]
        assert "clip3.wav" in prproj_media[proj2]


def test_was_in_older_project():
    """Test checking if a file was in an older project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create old project file
        old_proj = tmpdir / "old.prproj"
        create_test_prproj(old_proj, ["old_clip.mov"])

        # Create newer timeline file
        timeline = tmpdir / "timeline.otio"
        timeline.touch()

        # Make sure old project is actually older
        import time
        time.sleep(0.01)
        timeline.touch()  # Update mtime to be newer

        prproj_media = {old_proj: {"old_clip.mov"}}

        # File in old project should be marked as removed
        assert was_in_older_project("old_clip.mov", prproj_media, timeline)

        # File not in any project should not be marked as removed
        assert not was_in_older_project("new_clip.mov", prproj_media, timeline)


def test_is_in_newer_project():
    """Test checking if a file is in a newer project."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create timeline file
        timeline = tmpdir / "timeline.otio"
        timeline.touch()

        # Make sure timeline is older
        import time
        time.sleep(0.01)

        # Create newer project file
        new_proj = tmpdir / "new.prproj"
        create_test_prproj(new_proj, ["new_clip.mov"])

        prproj_media = {new_proj: {"new_clip.mov"}}

        # File in newer project should be detected
        assert is_in_newer_project("new_clip.mov", prproj_media, timeline)

        # File not in any project should not be detected
        assert not is_in_newer_project("other_clip.mov", prproj_media, timeline)


def test_is_in_newer_project_no_timeline():
    """Test that files in prproj are detected as newer when no timeline exists."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create project file
        proj = tmpdir / "project.prproj"
        create_test_prproj(proj, ["clip.mov"])

        prproj_media = {proj: {"clip.mov"}}

        # With no timeline, any file in prproj should be considered "newer"
        assert is_in_newer_project("clip.mov", prproj_media, None)


def test_extract_from_invalid_file():
    """Test that invalid files don't crash the parser."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Create non-gzip file
        invalid_file = tmpdir / "invalid.prproj"
        invalid_file.write_text("not gzipped")

        # Should return empty set, not crash
        filenames = extract_media_filenames(invalid_file)
        assert len(filenames) == 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
