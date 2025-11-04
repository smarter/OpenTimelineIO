"""
File system watcher for OTIO timeline files.

Monitors a directory for new or modified .otio files and automatically
updates the tracker state when changes are detected.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer


class TimelineFileHandler(FileSystemEventHandler):
    """Handler for timeline file system events."""

    def __init__(self, callback: Callable[[Path], None], debounce_seconds: float = 1.0):
        """
        Initialize handler.

        Args:
            callback: Function to call when a timeline file is created/modified
            debounce_seconds: Minimum time between processing the same file
        """
        self.callback = callback
        self.debounce_seconds = debounce_seconds
        self.last_processed: dict[Path, float] = {}

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if not event.is_directory and event.src_path.endswith('.otio'):
            self._process_file(Path(event.src_path))

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if not event.is_directory and event.src_path.endswith('.otio'):
            self._process_file(Path(event.src_path))

    def _process_file(self, filepath: Path) -> None:
        """Process a timeline file with debouncing."""
        now = time.time()
        last_time = self.last_processed.get(filepath, 0)

        if now - last_time >= self.debounce_seconds:
            self.last_processed[filepath] = now
            # Small delay to ensure file is fully written
            time.sleep(0.1)
            self.callback(filepath)


class TimelineWatcher:
    """
    Watches a directory for OTIO timeline files.

    Automatically triggers updates when new or modified timelines are detected.
    """

    def __init__(self, watch_dir: Path, callback: Callable[[Path], None]):
        """
        Initialize watcher.

        Args:
            watch_dir: Directory to watch for .otio files
            callback: Function to call when a timeline file is created/modified
        """
        self.watch_dir = watch_dir
        self.callback = callback
        self.observer = Observer()
        self.handler = TimelineFileHandler(callback)

    def start(self) -> None:
        """Start watching the directory."""
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(self.handler, str(self.watch_dir), recursive=False)
        self.observer.start()
        print(f"📁 Watching for timeline files in: {self.watch_dir}")

    def stop(self) -> None:
        """Stop watching the directory."""
        self.observer.stop()
        self.observer.join()

    def is_alive(self) -> bool:
        """Check if watcher is running."""
        return self.observer.is_alive()
