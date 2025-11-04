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
    """
    NEW = auto()
    IN_USE = auto()
    REMOVED = auto()

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

    def get_files_by_state(self, state: FileState) -> list[FileRecord]:
        """Get all files in a specific state, sorted by path."""
        return sorted(
            [f for f in self.files.values() if f.state == state],
            key=lambda f: str(f.path)
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

    def update_file(self, file_record: FileRecord) -> None:
        """Update or add a file record."""
        self.files[file_record.path] = file_record

    def get_file(self, path: Path) -> FileRecord | None:
        """Get file record by path."""
        return self.files.get(path)


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
