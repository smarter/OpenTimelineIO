"""
File system watcher for OTIO timeline files and media files.

Monitors directories for new/modified files and automatically
updates the tracker state when changes are detected.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Callable, Set

from watchdog.events import FileSystemEventHandler, FileSystemEvent
from watchdog.observers import Observer

logger = logging.getLogger(__name__)


class FileWatcherHandler(FileSystemEventHandler):
    """Handler for file system events with extension filtering."""

    def __init__(
        self,
        callback: Callable[[Path], None],
        extensions: Set[str],
        debounce_seconds: float = 1.0
    ):
        """
        Initialize handler.

        Args:
            callback: Function to call when a matching file is created/modified
            extensions: Set of file extensions to watch (e.g., {'.otio', '.mov', '.mp4'})
            debounce_seconds: Minimum time between processing the same file
        """
        self.callback = callback
        self.extensions = extensions
        self.debounce_seconds = debounce_seconds
        self.last_processed: dict[Path, float] = {}

    def on_created(self, event: FileSystemEvent) -> None:
        """Handle file creation events."""
        if not event.is_directory:
            filepath = Path(event.src_path)
            if filepath.suffix.lower() in self.extensions:
                self._process_file(filepath)

    def on_modified(self, event: FileSystemEvent) -> None:
        """Handle file modification events."""
        if not event.is_directory:
            filepath = Path(event.src_path)
            if filepath.suffix.lower() in self.extensions:
                self._process_file(filepath)

    def _process_file(self, filepath: Path) -> None:
        """Process a file with debouncing."""
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
            watch_dir: Directory to watch for .otio and .xml files
            callback: Function to call when a timeline file is created/modified
        """
        self.watch_dir = watch_dir
        self.callback = callback
        self.observer = Observer()
        self.handler = FileWatcherHandler(callback, {'.otio', '.xml'})

    def start(self) -> None:
        """Start watching the directory."""
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(self.handler, str(self.watch_dir), recursive=False)
        self.observer.start()
        logger.info(f"📁 Watching for timeline files in: {self.watch_dir}")

    def stop(self) -> None:
        """Stop watching the directory."""
        self.observer.stop()
        self.observer.join()

    def is_alive(self) -> bool:
        """Check if watcher is running."""
        return self.observer.is_alive()


class MediaWatcher:
    """
    Watches a directory for media files.

    Automatically tracks new media files when they appear.
    """

    # Common media file extensions
    MEDIA_EXTENSIONS = {
        '.mov', '.mp4', '.avi', '.mkv', '.webm', '.m4v', '.mxf',  # Video
        '.wav', '.mp3', '.aac', '.flac', '.ogg', '.m4a',  # Audio
    }

    def __init__(self, watch_dir: Path, callback: Callable[[Path], None]):
        """
        Initialize watcher.

        Args:
            watch_dir: Directory to watch for media files
            callback: Function to call when a media file is created
        """
        self.watch_dir = watch_dir
        self.callback = callback
        self.observer = Observer()
        self.handler = FileWatcherHandler(callback, self.MEDIA_EXTENSIONS)

    def start(self) -> None:
        """Start watching the directory recursively."""
        self.watch_dir.mkdir(parents=True, exist_ok=True)
        self.observer.schedule(self.handler, str(self.watch_dir), recursive=True)
        self.observer.start()
        logger.info(f"📁 Watching for media files in: {self.watch_dir} (recursive)")

    def stop(self) -> None:
        """Stop watching the directory."""
        self.observer.stop()
        self.observer.join()

    def is_alive(self) -> bool:
        """Check if watcher is running."""
        return self.observer.is_alive()
