"""Pytest configuration and fixtures for E2E tests."""

import os
import subprocess
import threading
import time
from pathlib import Path

import opentimelineio as otio
import pytest
from playwright.sync_api import Browser, BrowserType
from werkzeug.serving import make_server

from shots_dashboard.app import create_app


def can_run_browser():
    """Check if browser tests can run in this environment."""
    # Check if we can launch a browser - test by checking kernel version
    # and if we're in a restricted environment
    try:
        result = subprocess.run(['uname', '-r'], capture_output=True, text=True)
        kernel = result.stdout.strip()
        # Old kernels (< 4.10) often have issues with modern Chromium
        major, minor = map(int, kernel.split('.')[:2])
        if major < 4 or (major == 4 and minor < 10):
            return False
    except:
        pass

    # If $DISPLAY is not set and not in CI with proper setup, skip
    if not os.environ.get('DISPLAY') and not os.environ.get('CI'):
        # Try to detect if we can run headless browsers
        # This is a heuristic - if we're root and in a container, probably can't run
        if os.getuid() == 0 and os.path.exists('/.dockerenv'):
            return False

    return True


# Skip E2E tests if browsers can't run in this environment
pytestmark = pytest.mark.skipif(
    not can_run_browser(),
    reason="Browser tests not supported in this environment (old kernel or restricted container)"
)


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args):
    """Override Playwright browser launch args for restricted environments."""
    return {
        **browser_type_launch_args,
        "args": [
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            "--disable-features=VizDisplayCompositor",
            "--disable-ipc-flooding-protection",
            "--disable-renderer-backgrounding",
            "--disable-backgrounding-occluded-windows",
            "--disable-blink-features=AutomationControlled",
            "--ignore-certificate-errors",
        ],
        "ignore_default_args": ["--enable-automation"],
    }


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
    server = make_server('127.0.0.1', 5555, flask_app, threaded=True)

    # Start server in background thread
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # Wait for server to be ready
    time.sleep(1)

    yield 'http://127.0.0.1:5555'

    # Cleanup
    server.shutdown()
