"""
JSON-based database for persisting tracker state.

Provides type-safe serialization/deserialization with proper error handling.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .models import FileRecord, FileState, TrackerState


class DatabaseError(Exception):
    """Base exception for database operations."""
    pass


class Database:
    """
    Type-safe JSON database for tracker state persistence.

    Uses proper error handling and validation to ensure data integrity.
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self._ensure_db_exists()

    def _ensure_db_exists(self) -> None:
        """Create database file if it doesn't exist."""
        if not self.db_path.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            self._write_raw({
                "files": {},
                "timeline_path": None,
                "last_scan": None
            })

    def _write_raw(self, data: dict[str, Any]) -> None:
        """Write raw data to JSON file."""
        try:
            with open(self.db_path, 'w') as f:
                json.dump(data, f, indent=2, default=str)
        except (IOError, OSError) as e:
            raise DatabaseError(f"Failed to write database: {e}") from e

    def _read_raw(self) -> dict[str, Any]:
        """Read raw data from JSON file."""
        try:
            with open(self.db_path, 'r') as f:
                return json.load(f)
        except (IOError, OSError, json.JSONDecodeError) as e:
            raise DatabaseError(f"Failed to read database: {e}") from e

    def save(self, state: TrackerState) -> None:
        """
        Save tracker state to database.

        Args:
            state: The tracker state to persist

        Raises:
            DatabaseError: If save operation fails
        """
        data: dict[str, Any] = {
            "files": {
                str(path): {
                    "path": str(record.path),
                    "state": record.state.name,
                    "last_updated": record.last_updated.isoformat()
                }
                for path, record in state.files.items()
            },
            "timeline_path": str(state.timeline_path) if state.timeline_path else None,
            "last_scan": state.last_scan.isoformat() if state.last_scan else None
        }
        self._write_raw(data)

    def load(self) -> TrackerState:
        """
        Load tracker state from database.

        Returns:
            The loaded tracker state

        Raises:
            DatabaseError: If load operation fails or data is invalid
        """
        try:
            data = self._read_raw()
            state = TrackerState()

            # Load files
            for path_str, file_data in data.get("files", {}).items():
                try:
                    path = Path(file_data["path"])
                    file_state = FileState[file_data["state"]]
                    last_updated = datetime.fromisoformat(file_data["last_updated"])

                    state.files[path] = FileRecord(
                        path=path,
                        state=file_state,
                        last_updated=last_updated
                    )
                except (KeyError, ValueError) as e:
                    # Skip invalid records but log warning
                    print(f"Warning: Skipping invalid file record: {e}")
                    continue

            # Load metadata
            if data.get("timeline_path"):
                state.timeline_path = Path(data["timeline_path"])

            if data.get("last_scan"):
                state.last_scan = datetime.fromisoformat(data["last_scan"])

            return state

        except Exception as e:
            raise DatabaseError(f"Failed to load state: {e}") from e

    def reset(self) -> None:
        """Reset database to initial empty state."""
        self._write_raw({
            "files": {},
            "timeline_path": None,
            "last_scan": None
        })
