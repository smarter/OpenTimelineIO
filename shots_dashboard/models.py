"""
Data models for the shots dashboard.

Uses modern Python practices:
- Dataclasses for structured data
- Enums for type-safe state representation
- Type hints for all parameters and return values
- Frozen dataclasses to make illegal state unrepresentable
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from pathlib import Path
from typing import Set


class FileState(Enum):
    """
    Represents the state of a file in relation to the timeline.

    State transitions:
    - NEW: File exists in directory but has never been in timeline
    - IN_USE: File is currently in the timeline
    - REMOVED: File was previously in timeline but is no longer present
    - NEWER_PROJECT: File is in a Premiere Pro project newer than current timeline
    """
    NEW = auto()
    IN_USE = auto()
    REMOVED = auto()
    NEWER_PROJECT = auto()

    def __str__(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class FileRecord:
    """
    Immutable record of a file and its timeline state.

    By making this frozen, we ensure state changes result in new objects,
    making the system more predictable and easier to test.
    """
    path: Path
    state: FileState
    last_updated: datetime

    def with_state(self, new_state: FileState) -> FileRecord:
        """Create a new FileRecord with updated state and timestamp."""
        return FileRecord(
            path=self.path,
            state=new_state,
            last_updated=datetime.now()
        )

    def is_audio(self) -> bool:
        """Check if this file is audio only (not video)."""
        audio_extensions = {'.wav', '.mp3', '.aac', '.flac', '.ogg', '.m4a', '.aif', '.aiff'}
        return self.path.suffix.lower() in audio_extensions

    def is_video(self) -> bool:
        """Check if this file is video (may include audio)."""
        video_extensions = {'.mov', '.mp4', '.avi', '.mkv', '.webm', '.m4v', '.mxf'}
        return self.path.suffix.lower() in video_extensions


@dataclass(frozen=True)
class TimelineSnapshot:
    """
    Immutable snapshot of which files were in a timeline at a specific point in time.

    This allows us to track timeline history and show users which files
    were previously in the timeline.
    """
    timestamp: datetime
    timeline_path: Path
    clip_names: tuple[str, ...]  # Immutable tuple of clip names in timeline

    def __str__(self) -> str:
        return f"Timeline '{self.timeline_path.name}' with {len(self.clip_names)} clips at {self.timestamp}"


@dataclass(frozen=True)
class TimelineHistory:
    """
    Immutable collection of timeline snapshots over time.

    Maintains a history of timeline states, keeping only the most recent
    snapshots up to max_snapshots limit. Being frozen ensures we create
    new instances rather than mutating existing ones.
    """
    snapshots: tuple[TimelineSnapshot, ...] = field(default_factory=tuple)
    max_snapshots: int = 50

    def add_snapshot(self, snapshot: TimelineSnapshot) -> TimelineHistory:
        """
        Create a new TimelineHistory with an additional snapshot.

        Keeps only the most recent max_snapshots entries. Most recent
        snapshot is always at index 0.

        Args:
            snapshot: The new snapshot to add

        Returns:
            New TimelineHistory instance with the snapshot added
        """
        all_snapshots = (snapshot,) + self.snapshots
        return TimelineHistory(
            snapshots=all_snapshots[:self.max_snapshots],
            max_snapshots=self.max_snapshots
        )

    def get_current(self) -> TimelineSnapshot | None:
        """Get the most recent timeline snapshot."""
        return self.snapshots[0] if self.snapshots else None

    def get_historical(self) -> tuple[TimelineSnapshot, ...]:
        """Get all historical snapshots (excluding the current one)."""
        return self.snapshots[1:] if len(self.snapshots) > 1 else ()

    def get_all_historical_clips(self) -> Set[str]:
        """
        Get set of all clip names that appeared in historical timelines.

        Excludes clips from the current timeline to show only what
        used to be in the timeline but isn't anymore.
        """
        current = self.get_current()
        current_clips = set(current.clip_names) if current else set()

        historical_clips = set()
        for snapshot in self.get_historical():
            historical_clips.update(snapshot.clip_names)

        # Return only clips that were in history but not in current
        return historical_clips - current_clips


@dataclass
class TrackerState:
    """
    Mutable collection representing the current state of all tracked files.

    This is the only mutable model, as it represents the current working state
    of the system.
    """
    files: dict[Path, FileRecord] = field(default_factory=dict)
    timeline_path: Path | None = None
    last_scan: datetime | None = None
    timeline_history: TimelineHistory = field(default_factory=TimelineHistory)

    def get_files_by_state(self, state: FileState) -> list[FileRecord]:
        """Get all files in a specific state, sorted by most recent first."""
        return sorted(
            [f for f in self.files.values() if f.state == state],
            key=lambda f: f.last_updated,
            reverse=True  # Most recent first
        )

    @property
    def new_files(self) -> list[FileRecord]:
        """Files that exist but haven't been used in timeline yet."""
        return self.get_files_by_state(FileState.NEW)

    @property
    def in_use_files(self) -> list[FileRecord]:
        """Files currently in the timeline."""
        return self.get_files_by_state(FileState.IN_USE)

    @property
    def removed_files(self) -> list[FileRecord]:
        """Files previously in timeline but now removed."""
        return self.get_files_by_state(FileState.REMOVED)

    @property
    def newer_project_files(self) -> list[FileRecord]:
        """Files in Premiere Pro projects newer than current timeline."""
        return self.get_files_by_state(FileState.NEWER_PROJECT)

    def update_file(self, file_record: FileRecord) -> None:
        """Update or add a file record."""
        self.files[file_record.path] = file_record

    def get_file(self, path: Path) -> FileRecord | None:
        """Get file record by path."""
        return self.files.get(path)

    def get_files_as_sequences(self, state: FileState) -> list[FileRecord]:
        """
        Get files grouped into sequences where appropriate.

        When an entire folder of images is in the same state, represent them
        as a single sequence (e.g., 'folder/*.png') instead of individual files.

        Args:
            state: The file state to filter by

        Returns:
            List of file records, with image folders collapsed into sequences
        """
        files_in_state = self.get_files_by_state(state)

        # Group image files by (parent directory, extension)
        from collections import defaultdict
        image_extensions = {'.png', '.jpg', '.jpeg'}

        image_groups: dict[tuple[Path, str], list[FileRecord]] = defaultdict(list)
        non_image_files: list[FileRecord] = []

        for record in files_in_state:
            if record.path.suffix.lower() in image_extensions:
                key = (record.path.parent, record.path.suffix.lower())
                image_groups[key].append(record)
            else:
                non_image_files.append(record)

        # Build result: sequences for image groups, individual files otherwise
        result = non_image_files.copy()

        for (parent_dir, ext), records in image_groups.items():
            if len(records) > 1:
                # Multiple images in same directory with same extension and state
                # Create a synthetic "sequence" record
                sequence_path = parent_dir / f"*{ext}"
                # Use the most recent timestamp
                most_recent = max(r.last_updated for r in records)
                sequence_record = FileRecord(
                    path=sequence_path,
                    state=state,
                    last_updated=most_recent
                )
                result.append(sequence_record)
            else:
                # Single image file, keep as-is
                result.extend(records)

        # Sort by most recent first
        return sorted(result, key=lambda f: f.last_updated, reverse=True)


@dataclass(frozen=True)
class StateTransition:
    """
    Represents a state transition for auditing/logging purposes.

    This immutable record allows us to track the history of changes.
    """
    path: Path
    old_state: FileState | None
    new_state: FileState
    timestamp: datetime = field(default_factory=datetime.now)

    def __str__(self) -> str:
        old = str(self.old_state) if self.old_state else "none"
        return f"{self.path.name}: {old} → {self.new_state}"
