"""
Unit tests for timeline history models and functionality.

Tests the TimelineSnapshot and TimelineHistory models to ensure
proper tracking of timeline changes over time.
"""

import unittest
from datetime import datetime
from pathlib import Path

from shots_dashboard.models import TimelineHistory, TimelineSnapshot


class TestTimelineSnapshot(unittest.TestCase):
    """Tests for TimelineSnapshot model."""

    def test_creation(self):
        """Test creating a timeline snapshot."""
        timestamp = datetime.now()
        path = Path("/test/timeline.otio")
        clips = ("clip1.mov", "clip2.mov")

        snapshot = TimelineSnapshot(
            timestamp=timestamp,
            timeline_path=path,
            clip_names=clips
        )

        self.assertEqual(snapshot.timestamp, timestamp)
        self.assertEqual(snapshot.timeline_path, path)
        self.assertEqual(snapshot.clip_names, clips)
        self.assertEqual(len(snapshot.clip_names), 2)

    def test_immutability(self):
        """Test that snapshots are immutable."""
        snapshot = TimelineSnapshot(
            timestamp=datetime.now(),
            timeline_path=Path("/test/timeline.otio"),
            clip_names=("clip1.mov",)
        )

        with self.assertRaises(AttributeError):
            snapshot.timestamp = datetime.now()

        with self.assertRaises(AttributeError):
            snapshot.clip_names = ("clip2.mov",)

    def test_empty_clips(self):
        """Test snapshot with no clips."""
        snapshot = TimelineSnapshot(
            timestamp=datetime.now(),
            timeline_path=Path("/test/empty.otio"),
            clip_names=()
        )

        self.assertEqual(len(snapshot.clip_names), 0)
        self.assertIsInstance(snapshot.clip_names, tuple)

    def test_string_representation(self):
        """Test string representation of snapshot."""
        snapshot = TimelineSnapshot(
            timestamp=datetime.now(),
            timeline_path=Path("/test/timeline.otio"),
            clip_names=("clip1.mov", "clip2.mov", "clip3.mov")
        )

        str_repr = str(snapshot)
        self.assertIn("timeline.otio", str_repr)
        self.assertIn("3 clips", str_repr)


class TestTimelineHistory(unittest.TestCase):
    """Tests for TimelineHistory model."""

    def test_empty_history(self):
        """Test creating an empty history."""
        history = TimelineHistory()

        self.assertEqual(len(history.snapshots), 0)
        self.assertEqual(history.max_snapshots, 50)
        self.assertIsNone(history.get_current())
        self.assertEqual(len(history.get_historical()), 0)

    def test_add_snapshot(self):
        """Test adding a snapshot to history."""
        history = TimelineHistory()
        snapshot = TimelineSnapshot(
            timestamp=datetime.now(),
            timeline_path=Path("/test/timeline.otio"),
            clip_names=("clip1.mov",)
        )

        new_history = history.add_snapshot(snapshot)

        # Original history unchanged (immutability)
        self.assertEqual(len(history.snapshots), 0)

        # New history has the snapshot
        self.assertEqual(len(new_history.snapshots), 1)
        self.assertEqual(new_history.get_current(), snapshot)

    def test_multiple_snapshots(self):
        """Test adding multiple snapshots."""
        history = TimelineHistory()

        snapshot1 = TimelineSnapshot(
            timestamp=datetime(2024, 1, 1),
            timeline_path=Path("/test/v1.otio"),
            clip_names=("clip1.mov",)
        )

        snapshot2 = TimelineSnapshot(
            timestamp=datetime(2024, 1, 2),
            timeline_path=Path("/test/v2.otio"),
            clip_names=("clip1.mov", "clip2.mov")
        )

        snapshot3 = TimelineSnapshot(
            timestamp=datetime(2024, 1, 3),
            timeline_path=Path("/test/v3.otio"),
            clip_names=("clip2.mov", "clip3.mov")
        )

        history = history.add_snapshot(snapshot1)
        history = history.add_snapshot(snapshot2)
        history = history.add_snapshot(snapshot3)

        # Most recent is current
        self.assertEqual(history.get_current(), snapshot3)

        # Historical snapshots are in order (most recent first, excluding current)
        historical = history.get_historical()
        self.assertEqual(len(historical), 2)
        self.assertEqual(historical[0], snapshot2)
        self.assertEqual(historical[1], snapshot1)

    def test_max_snapshots_limit(self):
        """Test that history respects max_snapshots limit."""
        history = TimelineHistory(max_snapshots=3)

        for i in range(5):
            snapshot = TimelineSnapshot(
                timestamp=datetime(2024, 1, i+1),
                timeline_path=Path(f"/test/v{i}.otio"),
                clip_names=(f"clip{i}.mov",)
            )
            history = history.add_snapshot(snapshot)

        # Should only keep 3 most recent
        self.assertEqual(len(history.snapshots), 3)

        # Current should be the most recent (index 4)
        current = history.get_current()
        self.assertIn("v4.otio", str(current.timeline_path))

    def test_get_all_historical_clips(self):
        """Test getting all clips that appeared in history but not current."""
        history = TimelineHistory()

        snapshot1 = TimelineSnapshot(
            timestamp=datetime(2024, 1, 1),
            timeline_path=Path("/test/v1.otio"),
            clip_names=("clip1.mov", "clip2.mov")
        )

        snapshot2 = TimelineSnapshot(
            timestamp=datetime(2024, 1, 2),
            timeline_path=Path("/test/v2.otio"),
            clip_names=("clip2.mov", "clip3.mov")
        )

        snapshot3 = TimelineSnapshot(
            timestamp=datetime(2024, 1, 3),
            timeline_path=Path("/test/v3.otio"),
            clip_names=("clip3.mov", "clip4.mov")
        )

        history = history.add_snapshot(snapshot1)
        history = history.add_snapshot(snapshot2)
        history = history.add_snapshot(snapshot3)

        # Current has clip3 and clip4
        # Historical has clip1, clip2, clip3
        # Should return clip1, clip2 (in historical but not in current)
        historical_clips = history.get_all_historical_clips()

        self.assertEqual(len(historical_clips), 2)
        self.assertIn("clip1.mov", historical_clips)
        self.assertIn("clip2.mov", historical_clips)
        self.assertNotIn("clip3.mov", historical_clips)  # In current
        self.assertNotIn("clip4.mov", historical_clips)  # In current

    def test_get_all_historical_clips_empty(self):
        """Test historical clips when no history."""
        history = TimelineHistory()

        snapshot = TimelineSnapshot(
            timestamp=datetime.now(),
            timeline_path=Path("/test/v1.otio"),
            clip_names=("clip1.mov",)
        )

        history = history.add_snapshot(snapshot)

        # Only one snapshot, no historical clips
        historical_clips = history.get_all_historical_clips()
        self.assertEqual(len(historical_clips), 0)

    def test_get_all_historical_clips_no_current(self):
        """Test historical clips when no current snapshot."""
        history = TimelineHistory()

        # Empty history should return empty set
        historical_clips = history.get_all_historical_clips()
        self.assertEqual(len(historical_clips), 0)


if __name__ == '__main__':
    unittest.main()
