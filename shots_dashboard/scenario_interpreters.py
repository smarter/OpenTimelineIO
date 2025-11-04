"""
Interpreters for the scenario DSL.

Provides two implementations:
1. SimulatedInterpreter: In-memory simulation for fast testing
2. FileSystemInterpreter: Actual file system operations for demos
"""

from __future__ import annotations

import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

import opentimelineio as otio

try:
    from .database import Database
    from .models import FileRecord, FileState, TrackerState
    from .scenario_dsl import (
        ActionType, AssertFileCount, AssertFileState, CreateFile,
        CreateTimeline, Scenario, ScanDirectory, UpdateFromTimeline, Wait
    )
    from .timeline_tracker import TimelineTracker
    from .video_transcoder import generate_test_video, check_ffmpeg_available
except ImportError:
    from database import Database
    from models import FileRecord, FileState, TrackerState
    from scenario_dsl import (
        ActionType, AssertFileCount, AssertFileState, CreateFile,
        CreateTimeline, Scenario, ScanDirectory, UpdateFromTimeline, Wait
    )
    from timeline_tracker import TimelineTracker
    from video_transcoder import generate_test_video, check_ffmpeg_available


class AssertionError(Exception):
    """Raised when an assertion in a scenario fails."""
    pass


class SimulatedInterpreter:
    """
    In-memory simulation of file operations and tracker behavior.

    Fast, deterministic, no disk I/O. Perfect for property-based testing.
    """

    def __init__(self):
        # Simulated file system: path -> exists
        self.files: set[Path] = set()

        # Simulated timelines: path -> list of clip names
        self.timelines: dict[Path, list[str]] = {}

        # Tracker state (in-memory)
        self.state = TrackerState()
        self.tracker = TimelineTracker(self.state)

        # Execution log
        self.log: list[str] = []

    def execute(self, scenario: Scenario) -> dict[str, Any]:
        """Execute scenario in simulation."""
        self.log.append(f"Executing scenario: {scenario.name}")

        for action in scenario.actions:
            self._execute_action(action)

        return {
            "success": True,
            "log": self.log.copy(),
            "final_state": self.get_state()
        }

    def _execute_action(self, action: Any) -> None:
        """Execute a single action."""
        match action.action_type:
            case ActionType.CREATE_FILE:
                self._create_file(action)
            case ActionType.CREATE_TIMELINE:
                self._create_timeline(action)
            case ActionType.SCAN_DIRECTORY:
                self._scan_directory(action)
            case ActionType.UPDATE_FROM_TIMELINE:
                self._update_from_timeline(action)
            case ActionType.WAIT:
                self._wait(action)
            case ActionType.ASSERT_FILE_STATE:
                self._assert_file_state(action)
            case ActionType.ASSERT_FILE_COUNT:
                self._assert_file_count(action)

    def _create_file(self, action: CreateFile) -> None:
        """Simulate creating a file."""
        self.files.add(action.path)
        self.log.append(f"Created file: {action.path}")

    def _create_timeline(self, action: CreateTimeline) -> None:
        """Simulate creating a timeline."""
        self.timelines[action.path] = list(action.clip_names)
        self.log.append(f"Created timeline: {action.path} with {len(action.clip_names)} clips")

    def _scan_directory(self, action: ScanDirectory) -> None:
        """Simulate scanning a directory."""
        # Find files in this directory
        dir_files = [f for f in self.files if f.parent == action.path]

        # Add them to tracker state
        for file_path in dir_files:
            if file_path not in self.state.files:
                record = FileRecord(
                    path=file_path,
                    state=FileState.NEW,
                    last_updated=datetime.now()
                )
                self.state.update_file(record)

        self.state.last_scan = datetime.now()
        self.log.append(f"Scanned directory: {action.path} ({len(dir_files)} files)")

    def _update_from_timeline(self, action: UpdateFromTimeline) -> None:
        """Simulate updating from timeline."""
        if action.path not in self.timelines:
            raise ValueError(f"Timeline not found: {action.path}")

        clip_names = set(self.timelines[action.path])

        # Match files by name
        clips_in_use: set[Path] = set()
        for file_path in self.state.files.keys():
            if file_path.name in clip_names:
                clips_in_use.add(file_path)

        # Update states using pattern matching logic
        transitions = 0
        for file_path, record in list(self.state.files.items()):
            is_in_timeline = file_path in clips_in_use
            old_state = record.state

            match (record.state, is_in_timeline):
                case (FileState.NEW, True):
                    new_state = FileState.IN_USE
                case (FileState.IN_USE, True):
                    new_state = FileState.IN_USE
                case (FileState.IN_USE, False):
                    new_state = FileState.REMOVED
                case (FileState.REMOVED, True):
                    new_state = FileState.IN_USE
                case (FileState.REMOVED, False):
                    new_state = FileState.REMOVED
                case (FileState.NEW, False):
                    new_state = FileState.NEW
                case _:
                    raise RuntimeError(f"Unexpected state: {record.state}, {is_in_timeline}")

            if new_state != old_state:
                new_record = record.with_state(new_state)
                self.state.update_file(new_record)
                transitions += 1

        self.state.timeline_path = action.path
        self.log.append(f"Updated from timeline: {action.path} ({transitions} transitions)")

    def _wait(self, action: Wait) -> None:
        """Simulate waiting (no-op in simulation)."""
        self.log.append(f"Wait: {action.seconds}s (skipped in simulation)")

    def _assert_file_state(self, action: AssertFileState) -> None:
        """Assert file is in expected state."""
        record = self.state.get_file(action.path)
        if record is None:
            raise AssertionError(f"File not tracked: {action.path}")

        expected = FileState[action.expected_state]
        if record.state != expected:
            raise AssertionError(
                f"File {action.path}: expected {expected}, got {record.state}"
            )

        self.log.append(f"Assert OK: {action.path} is {action.expected_state}")

    def _assert_file_count(self, action: AssertFileCount) -> None:
        """Assert count of files in a state."""
        if action.state == "TOTAL":
            actual = len(self.state.files)
        else:
            state_enum = FileState[action.state]
            actual = len(self.state.get_files_by_state(state_enum))

        if actual != action.expected_count:
            raise AssertionError(
                f"{action.state} files: expected {action.expected_count}, got {actual}"
            )

        self.log.append(f"Assert OK: {action.state} count = {action.expected_count}")

    def get_state(self) -> dict[str, Any]:
        """Get current state."""
        stats = {
            "total": len(self.state.files),
            "new": len(self.state.new_files),
            "in_use": len(self.state.in_use_files),
            "removed": len(self.state.removed_files)
        }

        files_by_state = {
            "new": [str(f.path) for f in self.state.new_files],
            "in_use": [str(f.path) for f in self.state.in_use_files],
            "removed": [str(f.path) for f in self.state.removed_files]
        }

        return {
            "stats": stats,
            "files": files_by_state,
            "timeline_path": str(self.state.timeline_path) if self.state.timeline_path else None
        }


class FileSystemInterpreter:
    """
    Real file system operations for demos and integration testing.

    Actually creates files, writes timelines, and runs the tracker.
    """

    def __init__(self, db_path: Path):
        self.db = Database(db_path)
        self.state = self.db.load()
        self.tracker = TimelineTracker(self.state)
        self.log: list[str] = []

    def execute(self, scenario: Scenario) -> dict[str, Any]:
        """Execute scenario with real file operations."""
        self.log.append(f"Executing scenario: {scenario.name}")

        for action in scenario.actions:
            self._execute_action(action)

        # Save final state
        self.db.save(self.tracker.state)

        return {
            "success": True,
            "log": self.log.copy(),
            "final_state": self.get_state()
        }

    def _execute_action(self, action: Any) -> None:
        """Execute a single action."""
        match action.action_type:
            case ActionType.CREATE_FILE:
                self._create_file(action)
            case ActionType.CREATE_TIMELINE:
                self._create_timeline(action)
            case ActionType.SCAN_DIRECTORY:
                self._scan_directory(action)
            case ActionType.UPDATE_FROM_TIMELINE:
                self._update_from_timeline(action)
            case ActionType.WAIT:
                self._wait(action)
            case ActionType.ASSERT_FILE_STATE:
                self._assert_file_state(action)
            case ActionType.ASSERT_FILE_COUNT:
                self._assert_file_count(action)

    def _create_file(self, action: CreateFile) -> None:
        """Actually create a file."""
        action.path.parent.mkdir(parents=True, exist_ok=True)

        # Check if this is a video/audio file
        video_extensions = {'.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v', '.mxf'}
        audio_extensions = {'.wav', '.mp3', '.aac', '.flac', '.ogg', '.m4a'}

        ext = action.path.suffix.lower()

        if ext in video_extensions and check_ffmpeg_available():
            # Generate actual video content
            try:
                generate_test_video(action.path, duration=5)
                self.log.append(f"Created video file: {action.path}")
            except Exception as e:
                # Fallback to empty file if video generation fails
                action.path.touch()
                self.log.append(f"Created file (video generation failed): {action.path}")
        elif ext in audio_extensions and check_ffmpeg_available():
            # Generate actual audio content
            try:
                # Generate audio-only file with sine wave
                import subprocess
                command = [
                    'ffmpeg',
                    '-f', 'lavfi',
                    '-i', 'sine=frequency=440:duration=5',
                    '-c:a', 'aac' if ext in {'.mp4', '.m4a', '.aac'} else 'libvorbis',
                    '-y',
                    str(action.path)
                ]
                subprocess.run(command, check=True, capture_output=True)
                self.log.append(f"Created audio file: {action.path}")
            except Exception as e:
                # Fallback to empty file if audio generation fails
                action.path.touch()
                self.log.append(f"Created file (audio generation failed): {action.path}")
        else:
            # Create empty file for non-media files or if ffmpeg unavailable
            action.path.touch()
            self.log.append(f"Created file: {action.path}")

    def _create_timeline(self, action: CreateTimeline) -> None:
        """Actually create an OTIO timeline."""
        timeline = otio.schema.Timeline(name=action.path.stem)
        track = otio.schema.Track(name="video")

        for clip_name in action.clip_names:
            clip = otio.schema.Clip(
                name=clip_name,
                source_range=otio.opentime.TimeRange(
                    start_time=otio.opentime.RationalTime(0, 24),
                    duration=otio.opentime.RationalTime(100, 24)
                )
            )
            track.append(clip)

        timeline.tracks.append(track)

        action.path.parent.mkdir(parents=True, exist_ok=True)
        otio.adapters.write_to_file(timeline, str(action.path))
        self.log.append(f"Created timeline: {action.path} with {len(action.clip_names)} clips")

    def _scan_directory(self, action: ScanDirectory) -> None:
        """Actually scan directory."""
        transitions = self.tracker.scan_directory(action.path)
        self.db.save(self.tracker.state)
        self.log.append(f"Scanned directory: {action.path} ({len(transitions)} new files)")

    def _update_from_timeline(self, action: UpdateFromTimeline) -> None:
        """Actually update from timeline."""
        transitions = self.tracker.update_from_timeline(action.path)
        self.db.save(self.tracker.state)
        self.log.append(f"Updated from timeline: {action.path} ({len(transitions)} transitions)")

    def _wait(self, action: Wait) -> None:
        """Actually wait."""
        time.sleep(action.seconds)
        self.log.append(f"Waited: {action.seconds}s")

    def _assert_file_state(self, action: AssertFileState) -> None:
        """Assert file is in expected state."""
        record = self.tracker.state.get_file(action.path)
        if record is None:
            raise AssertionError(f"File not tracked: {action.path}")

        expected = FileState[action.expected_state]
        if record.state != expected:
            raise AssertionError(
                f"File {action.path}: expected {expected}, got {record.state}"
            )

        self.log.append(f"Assert OK: {action.path} is {action.expected_state}")

    def _assert_file_count(self, action: AssertFileCount) -> None:
        """Assert count of files in a state."""
        stats = self.tracker.get_stats()

        if action.state == "TOTAL":
            actual = stats["total"]
        else:
            actual = stats[action.state.lower()]

        if actual != action.expected_count:
            raise AssertionError(
                f"{action.state} files: expected {action.expected_count}, got {actual}"
            )

        self.log.append(f"Assert OK: {action.state} count = {action.expected_count}")

    def get_state(self) -> dict[str, Any]:
        """Get current state."""
        stats = self.tracker.get_stats()

        files_by_state = {
            "new": [str(f.path) for f in self.tracker.state.new_files],
            "in_use": [str(f.path) for f in self.tracker.state.in_use_files],
            "removed": [str(f.path) for f in self.tracker.state.removed_files]
        }

        return {
            "stats": stats,
            "files": files_by_state,
            "timeline_path": str(self.tracker.state.timeline_path) if self.tracker.state.timeline_path else None
        }
