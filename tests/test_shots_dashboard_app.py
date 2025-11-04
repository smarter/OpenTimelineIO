"""Integration tests for Flask application."""

import json
from pathlib import Path

import opentimelineio as otio
import pytest
from flask import Flask
from flask.testing import FlaskClient

from shots_dashboard.app import create_app


@pytest.fixture
def app(tmp_path: Path) -> Flask:
    """Create Flask app for testing."""
    db_path = tmp_path / "test_db.json"
    app, socketio = create_app(db_path)
    return app


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    """Create test client."""
    return app.test_client()


@pytest.fixture
def temp_media_dir(tmp_path: Path) -> Path:
    """Create temporary media directory."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "shot_001.mov").touch()
    (media_dir / "shot_002.mp4").touch()
    return media_dir


@pytest.fixture
def timeline_file(tmp_path: Path) -> Path:
    """Create test timeline."""
    timeline = otio.schema.Timeline(name="test")
    track = otio.schema.Track(name="video")
    track.append(otio.schema.Clip(name="shot_001.mov"))
    timeline.tracks.append(track)

    timeline_path = tmp_path / "timeline.otio"
    otio.adapters.write_to_file(timeline, str(timeline_path))
    return timeline_path


class TestRoutes:
    """Test Flask routes."""

    def test_index_route(self, client: FlaskClient) -> None:
        """Test index page loads."""
        response = client.get('/')
        assert response.status_code == 200
        assert b"Shots Dashboard" in response.data

    def test_api_status_initial(self, client: FlaskClient) -> None:
        """Test initial status."""
        response = client.get('/api/status')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert data["stats"]["total"] == 0
        assert data["timeline_path"] is None
        assert data["last_scan"] is None

    def test_api_files_initial(self, client: FlaskClient) -> None:
        """Test initial files list."""
        response = client.get('/api/files')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert len(data["files"]["new"]) == 0
        assert len(data["files"]["in_use"]) == 0
        assert len(data["files"]["removed"]) == 0

    def test_api_scan(self, client: FlaskClient, temp_media_dir: Path) -> None:
        """Test scanning directory."""
        response = client.post(
            '/api/scan',
            json={"directory": str(temp_media_dir)}
        )
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert data["stats"]["total"] == 2
        assert data["stats"]["new"] == 2
        assert len(data["transitions"]) == 2

    def test_api_scan_missing_directory(self, client: FlaskClient) -> None:
        """Test scan without directory parameter."""
        response = client.post('/api/scan', json={})
        assert response.status_code == 400

        data = json.loads(response.data)
        assert data["success"] is False
        assert "directory" in data["error"].lower()

    def test_api_scan_nonexistent_directory(self, client: FlaskClient) -> None:
        """Test scan with nonexistent directory."""
        response = client.post(
            '/api/scan',
            json={"directory": "/nonexistent/path"}
        )
        assert response.status_code == 400

        data = json.loads(response.data)
        assert data["success"] is False

    def test_api_update_timeline(
        self,
        client: FlaskClient,
        temp_media_dir: Path,
        timeline_file: Path
    ) -> None:
        """Test updating from timeline."""
        # First scan directory
        client.post('/api/scan', json={"directory": str(temp_media_dir)})

        # Then update from timeline
        response = client.post(
            '/api/update_timeline',
            json={"timeline_path": str(timeline_file)}
        )
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True
        assert len(data["transitions"]) > 0

        # Verify state changed
        status_response = client.get('/api/status')
        status_data = json.loads(status_response.data)
        assert status_data["stats"]["in_use"] > 0

    def test_api_update_timeline_missing_path(self, client: FlaskClient) -> None:
        """Test update without timeline_path parameter."""
        response = client.post('/api/update_timeline', json={})
        assert response.status_code == 400

        data = json.loads(response.data)
        assert data["success"] is False
        assert "timeline_path" in data["error"].lower()

    def test_api_update_timeline_nonexistent_file(self, client: FlaskClient) -> None:
        """Test update with nonexistent timeline."""
        response = client.post(
            '/api/update_timeline',
            json={"timeline_path": "/nonexistent/timeline.otio"}
        )
        assert response.status_code == 400

        data = json.loads(response.data)
        assert data["success"] is False

    def test_api_reset(self, client: FlaskClient, temp_media_dir: Path) -> None:
        """Test resetting state."""
        # Add some data
        client.post('/api/scan', json={"directory": str(temp_media_dir)})

        # Verify data exists
        response = client.get('/api/status')
        data = json.loads(response.data)
        assert data["stats"]["total"] > 0

        # Reset
        response = client.post('/api/reset')
        assert response.status_code == 200

        data = json.loads(response.data)
        assert data["success"] is True

        # Verify data cleared
        response = client.get('/api/status')
        data = json.loads(response.data)
        assert data["stats"]["total"] == 0

    def test_404_handler(self, client: FlaskClient) -> None:
        """Test 404 error handler."""
        response = client.get('/nonexistent')
        assert response.status_code == 404

    def test_api_404_returns_json(self, client: FlaskClient) -> None:
        """Test 404 on API routes returns JSON."""
        response = client.get('/api/nonexistent')
        assert response.status_code == 404
        assert response.content_type == 'application/json'

        data = json.loads(response.data)
        assert data["success"] is False


class TestWorkflow:
    """Test complete workflows."""

    def test_full_workflow(
        self,
        client: FlaskClient,
        temp_media_dir: Path,
        timeline_file: Path,
        tmp_path: Path
    ) -> None:
        """Test complete workflow: scan → update → modify → update."""
        # 1. Scan directory
        response = client.post('/api/scan', json={"directory": str(temp_media_dir)})
        assert response.status_code == 200

        # Verify all files are NEW
        response = client.get('/api/files')
        files = json.loads(response.data)
        assert len(files["files"]["new"]) == 2

        # 2. Update from timeline (shot_001 in timeline)
        response = client.post(
            '/api/update_timeline',
            json={"timeline_path": str(timeline_file)}
        )
        assert response.status_code == 200

        # Verify shot_001 is IN_USE, shot_002 is NEW
        response = client.get('/api/files')
        files = json.loads(response.data)
        assert len(files["files"]["in_use"]) == 1
        assert len(files["files"]["new"]) == 1

        # 3. Create new timeline without shot_001
        new_timeline = otio.schema.Timeline(name="updated")
        new_timeline.tracks.append(otio.schema.Track(name="video"))
        new_timeline_path = tmp_path / "timeline_updated.otio"
        otio.adapters.write_to_file(new_timeline, str(new_timeline_path))

        response = client.post(
            '/api/update_timeline',
            json={"timeline_path": str(new_timeline_path)}
        )
        assert response.status_code == 200

        # Verify shot_001 is REMOVED
        response = client.get('/api/files')
        files = json.loads(response.data)
        assert len(files["files"]["removed"]) == 1
        assert len(files["files"]["in_use"]) == 0

    def test_persistence(
        self,
        tmp_path: Path,
        temp_media_dir: Path
    ) -> None:
        """Test that state persists across app instances."""
        db_path = tmp_path / "persistent_db.json"

        # Create first app instance and add data
        app1, socketio1 = create_app(db_path)
        client1 = app1.test_client()
        client1.post('/api/scan', json={"directory": str(temp_media_dir)})

        response = client1.get('/api/status')
        data1 = json.loads(response.data)
        assert data1["stats"]["total"] == 2

        # Create second app instance with same database
        app2, socketio2 = create_app(db_path)
        client2 = app2.test_client()

        response = client2.get('/api/status')
        data2 = json.loads(response.data)
        assert data2["stats"]["total"] == 2

        # Verify files are the same
        files1 = json.loads(client1.get('/api/files').data)
        files2 = json.loads(client2.get('/api/files').data)
        assert len(files1["files"]["new"]) == len(files2["files"]["new"])
