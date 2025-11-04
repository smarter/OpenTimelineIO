"""Pytest configuration and fixtures for E2E tests."""

import multiprocessing
import time
from pathlib import Path

import opentimelineio as otio
import pytest

from shots_dashboard.app import create_app


@pytest.fixture
def test_media_dir(tmp_path: Path) -> Path:
    """Create temporary media directory with sample files."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()

    # Create sample media files
    files = [
        "shot_001_anim_v001.mov",
        "shot_002_anim_v001.mov",
        "shot_003_anim_v001.mov",
        "shot_004_anim_v001.mov",
        "shot_005_comp_v001.mov",
    ]

    for filename in files:
        (media_dir / filename).touch()

    return media_dir


@pytest.fixture
def test_timeline_v1(tmp_path: Path) -> Path:
    """Create first version of test timeline."""
    timeline = otio.schema.Timeline(name="test_timeline_v1")
    track = otio.schema.Track(name="video")

    # Add clips for shots 1 and 2
    for shot_name in ["shot_001_anim_v001.mov", "shot_002_anim_v001.mov"]:
        clip = otio.schema.Clip(
            name=shot_name,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, 24),
                duration=otio.opentime.RationalTime(100, 24)
            )
        )
        track.append(clip)

    timeline.tracks.append(track)

    timeline_path = tmp_path / "timeline_v1.otio"
    otio.adapters.write_to_file(timeline, str(timeline_path))
    return timeline_path


@pytest.fixture
def test_timeline_v2(tmp_path: Path) -> Path:
    """Create second version of test timeline (different shots)."""
    timeline = otio.schema.Timeline(name="test_timeline_v2")
    track = otio.schema.Track(name="video")

    # Keep shot 2, add shot 3, remove shot 1
    for shot_name in ["shot_002_anim_v001.mov", "shot_003_anim_v001.mov"]:
        clip = otio.schema.Clip(
            name=shot_name,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, 24),
                duration=otio.opentime.RationalTime(100, 24)
            )
        )
        track.append(clip)

    timeline.tracks.append(track)

    timeline_path = tmp_path / "timeline_v2.otio"
    otio.adapters.write_to_file(timeline, str(timeline_path))
    return timeline_path


@pytest.fixture
def test_timeline_empty(tmp_path: Path) -> Path:
    """Create empty timeline."""
    timeline = otio.schema.Timeline(name="empty_timeline")
    timeline.tracks.append(otio.schema.Track(name="video"))

    timeline_path = tmp_path / "timeline_empty.otio"
    otio.adapters.write_to_file(timeline, str(timeline_path))
    return timeline_path


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Create temporary database path."""
    return tmp_path / "test_db.json"


@pytest.fixture
def flask_app(test_db_path: Path):
    """Create Flask app for testing."""
    app = create_app(test_db_path)
    app.config['TESTING'] = True
    return app


@pytest.fixture
def live_server(flask_app, test_db_path):
    """Start Flask server in background for E2E tests."""
    def run_server():
        flask_app.run(host='127.0.0.1', port=5555, debug=False, use_reloader=False)

    # Start server in background
    server_process = multiprocessing.Process(target=run_server, daemon=True)
    server_process.start()

    # Wait for server to be ready
    time.sleep(2)

    yield 'http://127.0.0.1:5555'

    # Cleanup
    server_process.terminate()
    server_process.join(timeout=5)
    if server_process.is_alive():
        server_process.kill()
