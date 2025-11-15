#!/usr/bin/env python3
"""
Integration tests for clip preview generation with speed changes.

Tests the full flow: API request → preview generation → duration verification
"""

import pytest
import json
import tempfile
import subprocess
from pathlib import Path

# Add project to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from app import create_app
from clip_preview import ClipPreviewGenerator


@pytest.fixture
def test_video():
    """Create a test video file at 24fps."""
    test_file = Path(tempfile.mktemp(suffix='.mov'))
    subprocess.run([
        'ffmpeg', '-f', 'lavfi', '-i', 'color=c=blue:s=320x240:d=5:r=24',
        '-c:v', 'libx264', '-preset', 'ultrafast', '-y', str(test_file)
    ], check=True, capture_output=True)

    yield test_file

    # Cleanup
    if test_file.exists():
        test_file.unlink()


@pytest.fixture
def app_client(test_video):
    """Create Flask test client with a media directory."""
    # Use the test video's directory as media_dir
    media_dir = test_video.parent
    app, socketio = create_app(media_dir=media_dir)
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client


def get_video_duration(file_path: Path) -> float:
    """Get duration of a video file using ffprobe."""
    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(file_path)
    ], capture_output=True, text=True, check=True)
    return float(result.stdout.strip())


def test_clip_preview_with_speed_via_api(app_client, test_video):
    """Test that API correctly generates preview with speed changes."""
    # Request data with duration and speed (slow motion)
    request_data = {
        'path': test_video.name,
        'clip_data': {
            'source_start': 1.0,
            'source_end': 3.0,
            'duration': 4.0,      # Timeline duration
            'speed': 0.5          # 2x slower
        }
    }

    response = app_client.post(
        '/api/preview/clip',
        data=json.dumps(request_data),
        content_type='application/json'
    )

    assert response.status_code == 200, f"API returned {response.status_code}: {response.data}"
    assert response.content_type.startswith('video/'), f"Wrong content type: {response.content_type}"

    # Save response to temp file and check duration
    preview_file = Path(tempfile.mktemp(suffix='.mp4'))
    try:
        preview_file.write_bytes(response.data)
        duration = get_video_duration(preview_file)

        print(f"\nPreview duration: {duration:.3f}s (expected 4.0s)")
        assert abs(duration - 4.0) < 0.1, f"Duration {duration}s != 4.0s (speed not applied correctly)"
    finally:
        if preview_file.exists():
            preview_file.unlink()


def test_clip_preview_without_speed_defaults_to_normal(app_client, test_video):
    """Test that missing speed/duration falls back to source duration."""
    # Request data WITHOUT duration and speed (should use source duration)
    request_data = {
        'path': test_video.name,
        'clip_data': {
            'source_start': 1.0,
            'source_end': 3.0
            # No duration or speed - should default to 2.0s at normal speed
        }
    }

    response = app_client.post(
        '/api/preview/clip',
        data=json.dumps(request_data),
        content_type='application/json'
    )

    assert response.status_code == 200

    # Save and check duration
    preview_file = Path(tempfile.mktemp(suffix='.mp4'))
    try:
        preview_file.write_bytes(response.data)
        duration = get_video_duration(preview_file)

        print(f"\nPreview duration: {duration:.3f}s (expected 2.0s)")
        # Should be 2.0s (source duration) since no speed was specified
        assert abs(duration - 2.0) < 0.1, f"Duration {duration}s != 2.0s (should use source duration)"
    finally:
        if preview_file.exists():
            preview_file.unlink()


def test_clip_preview_extreme_slow_motion(app_client, test_video):
    """Test extreme slow motion (20x slower like BoiteAGant-001.mov)."""
    # Simulate BoiteAGant-001.mov: 0.417s source → 8.333s timeline
    request_data = {
        'path': test_video.name,
        'clip_data': {
            'source_start': 1.0,
            'source_end': 1.417,     # 0.417s of source
            'duration': 8.333,        # 8.333s in timeline
            'speed': 0.05             # 20x slower
        }
    }

    response = app_client.post(
        '/api/preview/clip',
        data=json.dumps(request_data),
        content_type='application/json'
    )

    assert response.status_code == 200

    # Save and check duration
    preview_file = Path(tempfile.mktemp(suffix='.mp4'))
    try:
        preview_file.write_bytes(response.data)
        duration = get_video_duration(preview_file)

        print(f"\nPreview duration: {duration:.3f}s (expected 8.333s)")
        # Should be 8.333s (20x slower) - frame-accurate, no tolerance
        assert abs(duration - 8.333) < 0.01, f"Duration {duration:.3f}s != 8.333s (frame accuracy required)"
    finally:
        if preview_file.exists():
            preview_file.unlink()


def test_clip_preview_fast_motion(app_client, test_video):
    """Test fast motion (2x faster)."""
    request_data = {
        'path': test_video.name,
        'clip_data': {
            'source_start': 1.0,
            'source_end': 3.0,       # 2.0s of source
            'duration': 1.0,          # 1.0s in timeline
            'speed': 2.0              # 2x faster
        }
    }

    response = app_client.post(
        '/api/preview/clip',
        data=json.dumps(request_data),
        content_type='application/json'
    )

    assert response.status_code == 200

    # Save and check duration
    preview_file = Path(tempfile.mktemp(suffix='.mp4'))
    try:
        preview_file.write_bytes(response.data)
        duration = get_video_duration(preview_file)

        print(f"\nPreview duration: {duration:.3f}s (expected 1.0s)")
        # Should be 1.0s (2x faster)
        assert abs(duration - 1.0) < 0.1, f"Duration {duration}s != 1.0s (fast motion not working)"
    finally:
        if preview_file.exists():
            preview_file.unlink()


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
