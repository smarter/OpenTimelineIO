"""
Tests for demo mode to ensure it executes scenarios correctly.

Tests that demo mode properly saves state between actions and that
the dashboard can display the changing state.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import time

from shots_dashboard.database import Database
from shots_dashboard.scenario_dsl import Scenario, CreateFile, ScanDirectory, CreateTimeline, UpdateFromTimeline
from shots_dashboard.scenario_interpreters import FileSystemInterpreter


class TestDemoMode(unittest.TestCase):
    """Tests for demo mode execution."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.media_dir = self.base_dir / "media"
        self.media_dir.mkdir()
        self.db_path = self.base_dir / "demo.json"

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_demo_mode_saves_state_after_each_action(self):
        """Test that demo mode saves state after each action for UI updates."""
        # Create a simple scenario
        scenario = Scenario(
            name="test_demo",
            description="Test demo scenario",
            actions=[
                CreateFile(self.media_dir / "clip1.mov"),
                CreateFile(self.media_dir / "clip2.mov"),
                ScanDirectory(self.media_dir),
                CreateTimeline(self.base_dir / "timeline.otio", ("clip1.mov",)),
                UpdateFromTimeline(self.base_dir / "timeline.otio"),
            ]
        )

        # Execute with filesystem interpreter
        interpreter = FileSystemInterpreter(self.db_path)

        # Execute actions one by one like demo mode does
        for action in scenario.actions:
            interpreter._execute_action(action)
            # Save state after each action (like demo mode)
            interpreter.db.save(interpreter.tracker.state)

            # Verify database was updated
            db = Database(self.db_path)
            loaded_state = db.load()

            # Check that state matches current interpreter state
            self.assertEqual(
                len(loaded_state.files),
                len(interpreter.tracker.state.files)
            )

    def test_demo_mode_timeline_history_updates(self):
        """Test that timeline history is tracked correctly during demo."""
        # Create scenario with multiple timeline updates
        scenario = Scenario(
            name="timeline_history_demo",
            description="Demo with timeline changes",
            actions=[
                CreateFile(self.media_dir / "clip1.mov"),
                CreateFile(self.media_dir / "clip2.mov"),
                CreateFile(self.media_dir / "clip3.mov"),
                ScanDirectory(self.media_dir),
                CreateTimeline(self.base_dir / "v1.otio", ("clip1.mov", "clip2.mov")),
                UpdateFromTimeline(self.base_dir / "v1.otio"),
                CreateTimeline(self.base_dir / "v2.otio", ("clip2.mov", "clip3.mov")),
                UpdateFromTimeline(self.base_dir / "v2.otio"),
            ]
        )

        interpreter = FileSystemInterpreter(self.db_path)

        # Execute with state saves
        for action in scenario.actions:
            interpreter._execute_action(action)
            interpreter.db.save(interpreter.tracker.state)

        # Check final state has timeline history
        db = Database(self.db_path)
        final_state = db.load()

        # Should have 2 snapshots (v1 and v2)
        self.assertEqual(len(final_state.timeline_history.snapshots), 2)

        # Current should be v2
        current = final_state.timeline_history.get_current()
        self.assertIsNotNone(current)
        self.assertEqual(len(current.clip_names), 2)
        self.assertIn("clip2.mov", current.clip_names)
        self.assertIn("clip3.mov", current.clip_names)

        # Historical should show clip1.mov (was in v1, not in v2)
        historical_clips = final_state.timeline_history.get_all_historical_clips()
        self.assertIn("clip1.mov", historical_clips)

    def test_demo_mode_state_transitions(self):
        """Test that state transitions work correctly in demo mode."""
        scenario = Scenario(
            name="state_transitions_demo",
            description="Demo showing state changes",
            actions=[
                CreateFile(self.media_dir / "test.mov"),
                ScanDirectory(self.media_dir),
                CreateTimeline(self.base_dir / "timeline.otio", ("test.mov",)),
                UpdateFromTimeline(self.base_dir / "timeline.otio"),
            ]
        )

        interpreter = FileSystemInterpreter(self.db_path)

        # After create + scan, file should be NEW
        interpreter._execute_action(scenario.actions[0])  # CreateFile
        interpreter._execute_action(scenario.actions[1])  # ScanDirectory
        interpreter.db.save(interpreter.tracker.state)

        db = Database(self.db_path)
        state_after_scan = db.load()
        self.assertEqual(len(state_after_scan.new_files), 1)
        self.assertEqual(len(state_after_scan.in_use_files), 0)

        # After timeline update, file should be IN_USE
        interpreter._execute_action(scenario.actions[2])  # CreateTimeline
        interpreter._execute_action(scenario.actions[3])  # UpdateFromTimeline
        interpreter.db.save(interpreter.tracker.state)

        state_after_update = db.load()
        self.assertEqual(len(state_after_update.new_files), 0)
        self.assertEqual(len(state_after_update.in_use_files), 1)


if __name__ == '__main__':
    unittest.main()
