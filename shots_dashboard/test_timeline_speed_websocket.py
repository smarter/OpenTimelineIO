#!/usr/bin/env python3
"""
Test that WebSocket emission includes speed field for clips with Time Remap effects.

This test verifies that the fix for WebSocket timeline data emission correctly
includes speed, source_duration, and other fields needed for accurate preview generation.
"""

import pytest
import tempfile
from pathlib import Path
import opentimelineio as otio

# Add project to path
import sys
sys.path.insert(0, str(Path(__file__).parent))

from app import create_app


def create_timeline_with_speed_effect(timeline_path: Path) -> None:
    """
    Create an OTIO timeline with a clip that has Time Remap effect (slow motion).

    Simulates BoiteAGant-001.mov:
    - Source: 0.417s of media
    - Timeline: 8.333s duration
    - Speed: 0.05 (20x slower)
    """
    timeline = otio.schema.Timeline(name="Test Timeline")
    track = otio.schema.Track(name="Video 1", kind=otio.schema.TrackKind.Video)

    # Create clip with source range of 10 frames at 24fps (0.417s)
    clip = otio.schema.Clip(
        name="SlowMotionClip.mov",
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, 24),
            duration=otio.opentime.RationalTime(200, 24)  # 8.333s in timeline
        )
    )

    # Add Time Remap effect with keyframes
    # First keyframe: timeline 0 → source frame 0
    # Last keyframe: timeline 200 frames → source frame 10
    time_remap_effect = otio.schema.Effect(
        effect_name="Time Remap",
        metadata={
            "fcp_xml": {
                "effectid": "timeremap",
                "parameter": [
                    {
                        "parameterid": "graphdict",
                        "keyframe": [
                            {"time": "0s", "value": "0"},      # Start at source frame 0
                            {"time": "200/24s", "value": "10"}  # End at source frame 10
                        ]
                    }
                ]
            }
        }
    )

    clip.effects.append(time_remap_effect)
    track.append(clip)
    timeline.tracks.append(track)

    # Write to file
    otio.adapters.write_to_file(timeline, str(timeline_path))


@pytest.fixture
def test_timeline():
    """Create a test timeline with Time Remap effect."""
    with tempfile.TemporaryDirectory() as tmpdir:
        timeline_path = Path(tmpdir) / "test_timeline.otio"
        create_timeline_with_speed_effect(timeline_path)
        yield timeline_path


@pytest.fixture
def test_watch_dir(test_timeline):
    """Create a watch directory with the test timeline."""
    # The test timeline is already in a temp directory
    # Just return its parent directory as the watch dir
    yield test_timeline.parent


def get_websocket_timeline_data(watch_dir):
    """
    Get the timeline data that is actually emitted via WebSocket.

    Uses Flask-SocketIO test client to capture real emissions.
    """
    from app import create_app

    # Create app with watch_dir so it loads the timeline
    app, socketio = create_app(watch_dir=watch_dir)

    # Use SocketIO test client to capture emissions
    client = socketio.test_client(app)

    # Trigger state update which emits timeline data
    # The connection itself triggers initial state emission
    received = client.get_received()

    # Find the initial_state or state_update event
    for emission in received:
        if emission['name'] in ('initial_state', 'state_update'):
            data = emission['args'][0]
            if 'timeline_visual' in data and data['timeline_visual']:
                return data['timeline_visual'].get('tracks', [])

    return None


def test_websocket_includes_speed_field(test_watch_dir):
    """Test that WebSocket timeline data includes speed field."""
    tracks = get_websocket_timeline_data(test_watch_dir)

    assert tracks is not None, "Timeline data should not be None"
    assert len(tracks) > 0, "Should have at least one track"
    assert len(tracks[0]["clips"]) > 0, "Should have at least one clip"

    clip = tracks[0]["clips"][0]

    # Check that all required fields are present
    required_fields = ["name", "start", "duration", "end", "source_start", "source_end", "source_duration", "speed"]
    for field in required_fields:
        assert field in clip, f"Clip should have '{field}' field"

    # Check that speed field is not None
    assert clip["speed"] is not None, "Speed field should not be None for clip with Time Remap effect"


def test_websocket_speed_value_correct(test_watch_dir):
    """Test that WebSocket speed value is correctly calculated."""
    tracks = get_websocket_timeline_data(test_watch_dir)

    clip = tracks[0]["clips"][0]

    # Expected values based on our test timeline:
    # - Source: 10 frames at 24fps = 0.417s
    # - Timeline: 200 frames at 24fps = 8.333s
    # - Speed: 0.417 / 8.333 ≈ 0.05

    assert clip["source_duration"] is not None, "Source duration should not be None"
    assert clip["duration"] is not None, "Duration should not be None"
    assert clip["speed"] is not None, "Speed should not be None"

    # Verify source duration is approximately 0.417s (10 frames at 24fps)
    expected_source_duration = 10 / 24.0
    assert abs(clip["source_duration"] - expected_source_duration) < 0.01, \
        f"Source duration {clip['source_duration']:.3f}s should be ~{expected_source_duration:.3f}s"

    # Verify timeline duration is approximately 8.333s (200 frames at 24fps)
    expected_timeline_duration = 200 / 24.0
    assert abs(clip["duration"] - expected_timeline_duration) < 0.01, \
        f"Timeline duration {clip['duration']:.3f}s should be ~{expected_timeline_duration:.3f}s"

    # Verify speed is correctly calculated (source_duration / timeline_duration)
    expected_speed = expected_source_duration / expected_timeline_duration
    assert abs(clip["speed"] - expected_speed) < 0.001, \
        f"Speed {clip['speed']:.3f} should be ~{expected_speed:.3f} (20x slower)"

    # Verify it's approximately 0.05 (20x slower)
    assert abs(clip["speed"] - 0.05) < 0.001, \
        f"Speed {clip['speed']:.3f} should be ~0.05 (20x slower)"


def test_websocket_preserves_source_fields(test_watch_dir):
    """Test that WebSocket preserves source fields after merging logic."""
    tracks = get_websocket_timeline_data(test_watch_dir)

    clip = tracks[0]["clips"][0]

    # These fields must be preserved (not removed by cleanup)
    # They are needed by the frontend for preview generation
    assert "source_start" in clip, "source_start should be preserved"
    assert "source_end" in clip, "source_end should be preserved"
    assert "source_duration" in clip, "source_duration should be preserved"
    assert "speed" in clip, "speed should be preserved"

    # Values should not be None
    assert clip["source_start"] is not None, "source_start should not be None"
    assert clip["source_end"] is not None, "source_end should not be None"


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
