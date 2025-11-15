"""
Core logic for tracking timeline changes using OpenTimelineIO.

Uses pattern matching (Python 3.10+) for state transition logic,
making state changes explicit and type-safe.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Set

import opentimelineio as otio

try:
    from .models import FileRecord, FileState, StateTransition, TrackerState, TimelineSnapshot
    from .prproj_parser import scan_prproj_files, was_in_older_project, is_in_newer_project
except ImportError:
    from models import FileRecord, FileState, StateTransition, TrackerState, TimelineSnapshot
    from prproj_parser import scan_prproj_files, was_in_older_project, is_in_newer_project


class TimelineTracker:
    """
    Tracks files in a directory and their usage in OTIO timelines.

    State transitions are handled via pattern matching to make
    all valid transitions explicit and invalid ones impossible.
    """

    def __init__(self, state: TrackerState):
        self.state = state
        self._prproj_cache: dict[Path, Set[str]] | None = None
        self._prproj_cache_dir: Path | None = None

    def _should_ignore_source_images(self, file_path: Path) -> bool:
        """
        Check if this file is a source image for a video that exists.

        If foo.mov exists (in any state), ignore foo/*.png and foo/*.jpg files.

        Args:
            file_path: Path to check

        Returns:
            True if this file should be ignored as a source image
        """
        # Only check image files
        if file_path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
            return False

        # Get video stems from ALL tracked files (not just in_use)
        video_extensions = {'.mov', '.mp4', '.mxf', '.avi', '.mkv', '.m4v', '.webm'}
        video_stems = set()

        for record in self.state.files.values():
            if record.path.suffix.lower() in video_extensions:
                video_stems.add(record.path.stem)

        # Check if this image is in a directory matching a video stem
        # e.g., foo.mov → foo/*.png
        parent = file_path.parent
        if parent.name in video_stems:
            return True

        return False

    def scan_directory(
        self,
        directory: Path,
        extensions: Set[str] | None = None,
        watch_dir: Path | None = None
    ) -> list[StateTransition]:
        """
        Scan a directory for media files and update state.

        Args:
            directory: Directory to scan
            extensions: Set of file extensions to include (e.g., {'.mov', '.mp4'})
                       If None, includes common video formats
            watch_dir: Optional directory to scan for .prproj files to determine
                      if newly found files should be marked as REMOVED instead of NEW

        Returns:
            List of state transitions that occurred
        """
        if extensions is None:
            extensions = {'.mov', '.mp4', '.mxf', '.avi', '.mkv', '.m4v', '.wav', '.aif', '.aiff',
                         '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg'}

        if not directory.exists():
            raise ValueError(f"Directory does not exist: {directory}")

        # Scan for .prproj files if watch_dir is provided (cache results)
        prproj_media: dict[Path, Set[str]] = {}
        if watch_dir and watch_dir.exists():
            if self._prproj_cache is None or self._prproj_cache_dir != watch_dir:
                self._prproj_cache = scan_prproj_files(watch_dir)
                self._prproj_cache_dir = watch_dir
            prproj_media = self._prproj_cache

        # Find all media files
        found_files: Set[Path] = set()
        for ext in extensions:
            found_files.update(directory.rglob(f"*{ext}"))
            found_files.update(directory.rglob(f"*{ext.upper()}"))

        # Build set of video stems from newly found files
        video_extensions = {'.mov', '.mp4', '.mxf', '.avi', '.mkv', '.m4v', '.webm'}
        newly_found_video_stems = {
            f.stem for f in found_files
            if f.suffix.lower() in video_extensions
        }

        # Filter out source images based on newly found videos
        def should_filter_image(file_path: Path) -> bool:
            if file_path.suffix.lower() not in {'.png', '.jpg', '.jpeg'}:
                return False
            # Check against newly found videos
            if file_path.parent.name in newly_found_video_stems:
                return True
            # Also check against existing tracked videos
            return self._should_ignore_source_images(file_path)

        found_files = {f for f in found_files if not should_filter_image(f)}

        transitions: list[StateTransition] = []

        # Remove previously tracked files that should now be ignored
        for file_path in list(self.state.files.keys()):
            if should_filter_image(file_path):
                del self.state.files[file_path]
                # Note: We don't add a transition here since the file isn't truly changing state,
                # it's just being filtered out from tracking

        # Re-evaluate existing NEW files to see if they should be NEWER_PROJECT
        if prproj_media:
            for file_path, record in list(self.state.files.items()):
                if record.state == FileState.NEW:
                    # Check if this file should actually be NEWER_PROJECT
                    if is_in_newer_project(file_path.name, prproj_media, self.state.timeline_path):
                        old_state = record.state
                        record.state = FileState.NEWER_PROJECT
                        record.last_updated = datetime.now()
                        self.state.update_file(record)
                        transitions.append(StateTransition(
                            path=file_path,
                            old_state=old_state,
                            new_state=FileState.NEWER_PROJECT
                        ))

        # Add new files
        for file_path in found_files:
            if file_path not in self.state.files:
                # Determine initial state based on .prproj history
                initial_state = FileState.NEW

                # Check if this file is in a newer Premiere Pro project (highest priority)
                if prproj_media and is_in_newer_project(
                    file_path.name,
                    prproj_media,
                    self.state.timeline_path
                ):
                    initial_state = FileState.NEWER_PROJECT
                # Check if this file was in an older Premiere Pro project
                elif prproj_media and was_in_older_project(
                    file_path.name,
                    prproj_media,
                    self.state.timeline_path
                ):
                    initial_state = FileState.REMOVED

                record = FileRecord(
                    path=file_path,
                    state=initial_state,
                    last_updated=datetime.now()
                )
                self.state.update_file(record)
                transitions.append(StateTransition(
                    path=file_path,
                    old_state=None,
                    new_state=initial_state
                ))

        self.state.last_scan = datetime.now()
        return transitions

    def extract_clips_from_timeline(self, timeline_path: Path) -> Set[str]:
        """
        Extract clip names from an OTIO timeline.

        Args:
            timeline_path: Path to OTIO file (JSON, EDL, etc.)

        Returns:
            Set of clip/media reference names found in timeline

        Raises:
            ValueError: If timeline cannot be read
        """
        if not timeline_path.exists():
            raise ValueError(f"Timeline file does not exist: {timeline_path}")

        try:
            timeline = otio.adapters.read_from_file(str(timeline_path))
        except Exception as e:
            raise ValueError(f"Failed to read timeline: {e}") from e

        clip_names: Set[str] = set()

        # Iterate through all clips in all tracks
        if isinstance(timeline, otio.schema.Timeline):
            for track in timeline.tracks:
                for item in track:
                    if isinstance(item, otio.schema.Clip):
                        # Get clip name
                        if item.name:
                            clip_names.add(item.name)

                        # Also check media reference
                        if item.media_reference and hasattr(item.media_reference, 'target_url'):
                            ref_url = item.media_reference.target_url
                            if ref_url:
                                # Extract filename from URL
                                ref_path = Path(ref_url)
                                clip_names.add(ref_path.name)

        return clip_names

    def update_from_timeline(self, timeline_path: Path) -> list[StateTransition]:
        """
        Update file states based on current timeline.

        Uses pattern matching to handle all valid state transitions:
        - NEW → IN_USE: File is now used in timeline
        - IN_USE → IN_USE: File continues to be used (no change)
        - IN_USE → REMOVED: File is no longer in timeline
        - REMOVED → IN_USE: Previously removed file is back in timeline
        - NEW → NEW: File still not in timeline (no change)
        - REMOVED → REMOVED: File still not in timeline (no change)
        - NEWER_PROJECT → IN_USE: File from newer project is now used in timeline
        - NEWER_PROJECT → NEWER_PROJECT: File remains in newer project only (no change)

        Args:
            timeline_path: Path to OTIO timeline file

        Returns:
            List of state transitions that occurred
        """
        clip_names = self.extract_clips_from_timeline(timeline_path)
        transitions: list[StateTransition] = []

        # Match files to clips by filename
        clips_in_use: Set[Path] = set()
        for file_path in self.state.files.keys():
            if file_path.name in clip_names:
                clips_in_use.add(file_path)

        # Process each tracked file
        for file_path, record in list(self.state.files.items()):
            is_in_timeline = file_path in clips_in_use
            old_state = record.state

            # Pattern match on (current_state, is_in_timeline) to determine new state
            match (record.state, is_in_timeline):
                case (FileState.NEW, True):
                    # File is now used for the first time
                    new_state = FileState.IN_USE

                case (FileState.IN_USE, True):
                    # File continues to be used
                    new_state = FileState.IN_USE

                case (FileState.IN_USE, False):
                    # File has been removed from timeline
                    new_state = FileState.REMOVED

                case (FileState.REMOVED, True):
                    # Previously removed file is back
                    new_state = FileState.IN_USE

                case (FileState.REMOVED, False):
                    # File remains removed
                    new_state = FileState.REMOVED

                case (FileState.NEW, False):
                    # File still not used
                    new_state = FileState.NEW

                case (FileState.NEWER_PROJECT, True):
                    # File from newer project is now in timeline
                    new_state = FileState.IN_USE

                case (FileState.NEWER_PROJECT, False):
                    # File remains in newer project only
                    new_state = FileState.NEWER_PROJECT

                case _:
                    # This should be unreachable due to exhaustive matching
                    raise RuntimeError(f"Unexpected state combination: {record.state}, {is_in_timeline}")

            # Update state if changed
            if new_state != old_state:
                new_record = record.with_state(new_state)
                self.state.update_file(new_record)
                transitions.append(StateTransition(
                    path=file_path,
                    old_state=old_state,
                    new_state=new_state
                ))

        self.state.timeline_path = timeline_path

        # Record timeline snapshot for history tracking
        snapshot = TimelineSnapshot(
            timestamp=datetime.now(),
            timeline_path=timeline_path,
            clip_names=tuple(sorted(clip_names))  # Sorted for consistent ordering
        )
        self.state.timeline_history = self.state.timeline_history.add_snapshot(snapshot)

        return transitions

    def get_stats(self) -> dict[str, int]:
        """Get summary statistics."""
        return {
            "total": len(self.state.files),
            "new": len(self.state.new_files),
            "in_use": len(self.state.in_use_files),
            "removed": len(self.state.removed_files),
            "newer_project": len(self.state.newer_project_files)
        }
