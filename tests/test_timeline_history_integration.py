"""
Integration tests for timeline history feature.

Tests the complete workflow from timeline updates through API endpoints
to ensure timeline history tracking works end-to-end.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import opentimelineio as otio

from shots_dashboard.app import create_app
from shots_dashboard.database import Database


class TestTimelineHistoryIntegration(unittest.TestCase):
    """Integration tests for timeline history tracking."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "test.json"
        self.media_dir = Path(self.temp_dir.name) / "media"
        self.media_dir.mkdir()

        # Create test media files
        self.files = [
            self.media_dir / "shot_001.mov",
            self.media_dir / "shot_002.mov",
            self.media_dir / "shot_003.mov",
            self.media_dir / "shot_004.mov",
        ]
        for f in self.files:
            f.touch()

        # Create Flask app
        self.app, self.socketio = create_app(self.db_path)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def create_timeline(self, name: str, clips: list[str]) -> Path:
        """Helper to create a timeline with specific clips."""
        timeline = otio.schema.Timeline(name=name)
        track = otio.schema.Track(name="video")

        for clip_name in clips:
            clip = otio.schema.Clip(
                name=clip_name,
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, 24),
                    duration=otio.opentime.RationalTime(100, 24)
                )
            )
            track.append(clip)

        timeline.tracks.append(track)

        timeline_path = Path(self.temp_dir.name) / f"{name}.otio"
        otio.adapters.write_to_file(timeline, str(timeline_path))
        return timeline_path

    def test_timeline_history_tracks_changes(self):
        """Test that timeline history tracks changes over multiple updates."""
        # Scan directory
        response = self.client.post('/api/scan', json={'directory': str(self.media_dir)})
        self.assertEqual(response.status_code, 200)

        # Create and update from timeline v1
        timeline_v1 = self.create_timeline("v1", ["shot_001.mov", "shot_002.mov"])
        response = self.client.post('/api/update_timeline', json={'timeline_path': str(timeline_v1)})
        self.assertEqual(response.status_code, 200)

        # Check timeline history
        response = self.client.get('/api/timeline_history')
        self.assertEqual(response.status_code, 200)
        data = response.get_json()

        self.assertTrue(data['success'])
        self.assertIsNotNone(data['current'])
        self.assertEqual(len(data['current']['clips']), 2)
        self.assertIn("shot_001.mov", data['current']['clips'])
        self.assertIn("shot_002.mov", data['current']['clips'])
        self.assertEqual(len(data['historical_clips']), 0)  # No historical yet

        # Create and update from timeline v2
        timeline_v2 = self.create_timeline("v2", ["shot_002.mov", "shot_003.mov"])
        response = self.client.post('/api/update_timeline', json={'timeline_path': str(timeline_v2)})
        self.assertEqual(response.status_code, 200)

        # Check timeline history again
        response = self.client.get('/api/timeline_history')
        data = response.get_json()

        self.assertTrue(data['success'])
        self.assertIsNotNone(data['current'])
        self.assertEqual(len(data['current']['clips']), 2)
        self.assertIn("shot_002.mov", data['current']['clips'])
        self.assertIn("shot_003.mov", data['current']['clips'])

        # shot_001.mov should be in historical (was in v1 but not in v2)
        self.assertEqual(len(data['historical_clips']), 1)
        self.assertIn("shot_001.mov", data['historical_clips'])

    def test_timeline_history_persistence(self):
        """Test that timeline history persists across database reloads."""
        # Scan and update timeline
        self.client.post('/api/scan', json={'directory': str(self.media_dir)})

        timeline_v1 = self.create_timeline("v1", ["shot_001.mov", "shot_002.mov"])
        self.client.post('/api/update_timeline', json={'timeline_path': str(timeline_v1)})

        timeline_v2 = self.create_timeline("v2", ["shot_003.mov", "shot_004.mov"])
        self.client.post('/api/update_timeline', json={'timeline_path': str(timeline_v2)})

        # Verify history is loaded
        response = self.client.get('/api/timeline_history')
        data1 = response.get_json()
        self.assertEqual(len(data1['snapshots']), 1)  # v1 in historical

        # Create new app instance (simulates restart)
        new_app, new_socketio = create_app(self.db_path)
        new_app.config['TESTING'] = True
        new_client = new_app.test_client()

        # Check history is still there
        response = self.client.get('/api/timeline_history')
        data2 = response.get_json()

        self.assertTrue(data2['success'])
        self.assertEqual(len(data2['historical_clips']), 2)
        self.assertIn("shot_001.mov", data2['historical_clips'])
        self.assertIn("shot_002.mov", data2['historical_clips'])

    def test_multiple_timeline_updates_track_all_history(self):
        """Test tracking history through many timeline updates."""
        self.client.post('/api/scan', json={'directory': str(self.media_dir)})

        # Create sequence of timelines
        timelines = [
            ("v1", ["shot_001.mov"]),
            ("v2", ["shot_001.mov", "shot_002.mov"]),
            ("v3", ["shot_002.mov", "shot_003.mov"]),
            ("v4", ["shot_003.mov", "shot_004.mov"]),
            ("v5", ["shot_004.mov"]),
        ]

        for name, clips in timelines:
            timeline = self.create_timeline(name, clips)
            response = self.client.post('/api/update_timeline', json={'timeline_path': str(timeline)})
            self.assertEqual(response.status_code, 200)

        # Check final history
        response = self.client.get('/api/timeline_history')
        data = response.get_json()

        self.assertTrue(data['success'])

        # Current timeline should have shot_004.mov
        self.assertEqual(len(data['current']['clips']), 1)
        self.assertIn("shot_004.mov", data['current']['clips'])

        # Historical should have shot_001, shot_002, shot_003 (not in current)
        self.assertEqual(len(data['historical_clips']), 3)
        self.assertIn("shot_001.mov", data['historical_clips'])
        self.assertIn("shot_002.mov", data['historical_clips'])
        self.assertIn("shot_003.mov", data['historical_clips'])

        # Should have 4 historical snapshots (v1-v4, v5 is current)
        self.assertEqual(len(data['snapshots']), 4)

    def test_empty_timeline_history(self):
        """Test timeline history when no timeline has been loaded."""
        response = self.client.get('/api/timeline_history')
        data = response.get_json()

        self.assertTrue(data['success'])
        self.assertIsNone(data['current'])
        self.assertEqual(len(data['historical_clips']), 0)
        self.assertEqual(len(data['snapshots']), 0)


if __name__ == '__main__':
    unittest.main()
