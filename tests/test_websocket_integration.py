"""
Tests for WebSocket integration in shots dashboard.

Verifies real-time updates via WebSocket instead of polling.
"""

import json
import tempfile
from pathlib import Path

import pytest
from flask_socketio import SocketIOTestClient

from shots_dashboard.app import create_app
from shots_dashboard.models import TrackerState


class TestWebSocketConnection:
    """Test WebSocket connection and basic events."""

    def test_client_connect_receives_initial_state(self):
        """Test that connecting client receives initial state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.json"
            app, socketio = create_app(db_path)
            app.config['TESTING'] = True

            client = socketio.test_client(app)
            assert client.is_connected()

            # Should receive initial_state event on connection
            received = client.get_received()
            assert len(received) > 0

            # Find initial_state event
            initial_events = [r for r in received if r['name'] == 'initial_state']
            assert len(initial_events) > 0

            event_data = initial_events[0]['args'][0]
            assert 'stats' in event_data
            assert 'files' in event_data
            assert 'timeline_history' in event_data

            client.disconnect()

    def test_client_can_request_state(self):
        """Test that client can request current state."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.json"
            app, socketio = create_app(db_path)
            app.config['TESTING'] = True

            client = socketio.test_client(app)
            client.get_received()  # Clear initial messages

            # Request state
            client.emit('request_state')

            # Should receive state_update event
            received = client.get_received()
            state_events = [r for r in received if r['name'] == 'state_update']
            assert len(state_events) > 0

            client.disconnect()

    def test_disconnect_handling(self):
        """Test that disconnection is handled properly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.json"
            app, socketio = create_app(db_path)
            app.config['TESTING'] = True

            client = socketio.test_client(app)
            assert client.is_connected()

            client.disconnect()
            assert not client.is_connected()


class TestWebSocketStateUpdates:
    """Test WebSocket state update events."""

    def test_scan_triggers_state_update(self):
        """Test that scanning triggers WebSocket update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.json"
            media_dir = Path(tmpdir) / "media"
            media_dir.mkdir()

            # Create test file
            (media_dir / "test.mov").touch()

            app, socketio = create_app(db_path)
            app.config['TESTING'] = True

            # Connect WebSocket client
            ws_client = socketio.test_client(app)
            ws_client.get_received()  # Clear initial messages

            # Make HTTP request to scan
            http_client = app.test_client()
            response = http_client.post('/api/scan', json={'directory': str(media_dir)})
            assert response.status_code == 200

            # Should receive scan_complete event via WebSocket
            received = ws_client.get_received()
            scan_events = [r for r in received if r['name'] == 'scan_complete']
            assert len(scan_events) > 0

            event_data = scan_events[0]['args'][0]
            assert event_data['stats']['total'] == 1
            assert event_data['stats']['new'] == 1

            ws_client.disconnect()

    def test_timeline_update_triggers_state_update(self):
        """Test that timeline update triggers WebSocket update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.json"
            media_dir = Path(tmpdir) / "media"
            media_dir.mkdir()

            # Create test file
            (media_dir / "clip1.mov").touch()

            # Create timeline
            import opentimelineio as otio
            timeline = otio.schema.Timeline(name="test")
            track = otio.schema.Track(name="video")
            clip = otio.schema.Clip(
                name="clip1.mov",
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, 24),
                    duration=otio.opentime.RationalTime(100, 24)
                )
            )
            track.append(clip)
            timeline.tracks.append(track)

            timeline_path = Path(tmpdir) / "timeline.otio"
            otio.adapters.write_to_file(timeline, str(timeline_path))

            app, socketio = create_app(db_path)
            app.config['TESTING'] = True

            # Setup
            http_client = app.test_client()
            http_client.post('/api/scan', json={'directory': str(media_dir)})

            # Connect WebSocket client
            ws_client = socketio.test_client(app)
            ws_client.get_received()  # Clear initial messages

            # Update from timeline
            response = http_client.post('/api/update_timeline',
                                        json={'timeline_path': str(timeline_path)})
            assert response.status_code == 200

            # Should receive timeline_update_complete event via WebSocket
            received = ws_client.get_received()
            timeline_events = [r for r in received if r['name'] == 'timeline_update_complete']
            assert len(timeline_events) > 0

            event_data = timeline_events[0]['args'][0]
            assert event_data['stats']['in_use'] == 1
            assert event_data['timeline_history']['current'] is not None

            ws_client.disconnect()

    def test_reset_triggers_state_update(self):
        """Test that reset triggers WebSocket update."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.json"
            app, socketio = create_app(db_path)
            app.config['TESTING'] = True

            # Connect WebSocket client
            ws_client = socketio.test_client(app)
            ws_client.get_received()  # Clear initial messages

            # Reset
            http_client = app.test_client()
            response = http_client.post('/api/reset')
            assert response.status_code == 200

            # Should receive reset_complete event via WebSocket
            received = ws_client.get_received()
            reset_events = [r for r in received if r['name'] == 'reset_complete']
            assert len(reset_events) > 0

            event_data = reset_events[0]['args'][0]
            assert event_data['stats']['total'] == 0

            ws_client.disconnect()


class TestWebSocketMultipleClients:
    """Test multiple WebSocket clients."""

    def test_multiple_clients_receive_updates(self):
        """Test that all connected clients receive updates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.json"
            media_dir = Path(tmpdir) / "media"
            media_dir.mkdir()
            (media_dir / "test.mov").touch()

            app, socketio = create_app(db_path)
            app.config['TESTING'] = True

            # Connect two WebSocket clients
            client1 = socketio.test_client(app)
            client2 = socketio.test_client(app)

            client1.get_received()  # Clear initial messages
            client2.get_received()  # Clear initial messages

            # Make HTTP request to scan
            http_client = app.test_client()
            response = http_client.post('/api/scan', json={'directory': str(media_dir)})
            assert response.status_code == 200

            # Both clients should receive scan_complete event
            received1 = client1.get_received()
            received2 = client2.get_received()

            scan_events1 = [r for r in received1 if r['name'] == 'scan_complete']
            scan_events2 = [r for r in received2 if r['name'] == 'scan_complete']

            assert len(scan_events1) > 0
            assert len(scan_events2) > 0

            # Verify same data
            data1 = scan_events1[0]['args'][0]
            data2 = scan_events2[0]['args'][0]
            assert data1['stats'] == data2['stats']

            client1.disconnect()
            client2.disconnect()


class TestWebSocketDataFormat:
    """Test WebSocket data format."""

    def test_state_update_has_all_fields(self):
        """Test that state update events have all required fields."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "test.json"
            app, socketio = create_app(db_path)
            app.config['TESTING'] = True

            client = socketio.test_client(app)
            received = client.get_received()

            initial_events = [r for r in received if r['name'] == 'initial_state']
            assert len(initial_events) > 0

            data = initial_events[0]['args'][0]

            # Verify all required fields are present
            required_fields = ['stats', 'files', 'timeline_history', 'timeline_path',
                             'last_scan', 'timestamp']
            for field in required_fields:
                assert field in data, f"Missing field: {field}"

            # Verify stats structure
            assert 'total' in data['stats']
            assert 'new' in data['stats']
            assert 'in_use' in data['stats']
            assert 'removed' in data['stats']

            # Verify files structure
            assert 'new' in data['files']
            assert 'in_use' in data['files']
            assert 'removed' in data['files']

            # Verify timeline_history structure
            assert 'current' in data['timeline_history']
            assert 'historical_clips' in data['timeline_history']
            assert 'snapshots' in data['timeline_history']

            client.disconnect()
