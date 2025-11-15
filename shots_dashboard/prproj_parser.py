"""
Parser for Adobe Premiere Pro project files (.prproj).

Premiere Pro project files are gzipped XML files. This module
extracts media filenames from the project structure.
"""

from __future__ import annotations

import gzip
import logging
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Set

logger = logging.getLogger(__name__)


def extract_media_filenames(prproj_path: Path) -> Set[str]:
    """
    Extract media filenames from a Premiere Pro project file.

    The .prproj file is a gzipped XML file. We look for <Title> tags
    inside <Media> tags to find referenced media filenames.

    Args:
        prproj_path: Path to the .prproj file

    Returns:
        Set of media filenames found in the project
    """
    filenames: Set[str] = set()

    try:
        # Read and decompress the gzipped XML
        with gzip.open(prproj_path, 'rt', encoding='utf-8') as f:
            content = f.read()

        # Parse XML
        root = ET.fromstring(content)

        # Find all Media elements
        # We need to search recursively since we don't know the exact structure
        for media in root.iter('Media'):
            # Look for Title elements within this Media element
            for title in media.iter('Title'):
                if title.text:
                    # Extract just the filename (no path)
                    filename = Path(title.text).name
                    if filename:
                        filenames.add(filename)

        logger.debug(f"Extracted {len(filenames)} media files from {prproj_path.name}")

    except gzip.BadGzipFile:
        logger.warning(f"Failed to decompress {prproj_path.name} - not a valid gzip file")
    except ET.ParseError as e:
        logger.warning(f"Failed to parse XML in {prproj_path.name}: {e}")
    except Exception as e:
        logger.warning(f"Error reading {prproj_path.name}: {e}")

    return filenames


def scan_prproj_files(directory: Path) -> dict[Path, Set[str]]:
    """
    Scan a directory recursively for .prproj files and extract media filenames.

    Args:
        directory: Directory to scan for .prproj files

    Returns:
        Dictionary mapping prproj file paths to sets of media filenames
    """
    prproj_media: dict[Path, Set[str]] = {}

    if not directory.exists():
        logger.warning(f"Directory does not exist: {directory}")
        return prproj_media

    # Find all .prproj files recursively
    for prproj_file in directory.rglob('*.prproj'):
        logger.debug(f"Processing {prproj_file.name}")
        filenames = extract_media_filenames(prproj_file)
        if filenames:
            prproj_media[prproj_file] = filenames

    logger.info(f"Found {len(prproj_media)} .prproj files with media references")
    return prproj_media


def was_in_older_project(
    filename: str,
    prproj_media: dict[Path, Set[str]],
    timeline_path: Path | None
) -> bool:
    """
    Check if a filename was used in a Premiere Pro project older than the current timeline.

    Args:
        filename: The filename to check
        prproj_media: Dictionary mapping prproj paths to media filenames
        timeline_path: Current timeline path (for date comparison)

    Returns:
        True if the file appears in a .prproj older than the timeline
    """
    if not timeline_path or not timeline_path.exists():
        return False

    timeline_mtime = timeline_path.stat().st_mtime

    for prproj_path, media_files in prproj_media.items():
        if filename in media_files:
            prproj_mtime = prproj_path.stat().st_mtime
            if prproj_mtime < timeline_mtime:
                logger.debug(
                    f"{filename} found in older project {prproj_path.name} "
                    f"(project: {prproj_mtime}, timeline: {timeline_mtime})"
                )
                return True

    return False


def is_in_newer_project(
    filename: str,
    prproj_media: dict[Path, Set[str]],
    timeline_path: Path | None
) -> bool:
    """
    Check if a filename is used in a Premiere Pro project newer than the current timeline.

    Args:
        filename: The filename to check
        prproj_media: Dictionary mapping prproj paths to media filenames
        timeline_path: Current timeline path (for date comparison)

    Returns:
        True if the file appears in a .prproj newer than the timeline
    """
    if not timeline_path or not timeline_path.exists():
        # If no timeline exists, check if file is in any prproj
        for media_files in prproj_media.values():
            if filename in media_files:
                logger.debug(f"{filename} found in project (no timeline to compare)")
                return True
        return False

    timeline_mtime = timeline_path.stat().st_mtime

    for prproj_path, media_files in prproj_media.items():
        if filename in media_files:
            prproj_mtime = prproj_path.stat().st_mtime
            if prproj_mtime > timeline_mtime:
                logger.debug(
                    f"{filename} found in newer project {prproj_path.name} "
                    f"(project: {prproj_mtime}, timeline: {timeline_mtime})"
                )
                return True

    return False
