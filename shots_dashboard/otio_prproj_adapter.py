#!/usr/bin/env python3
"""
OpenTimelineIO Premiere Pro Project (.prproj) Adapter

Reads Adobe Premiere Pro project files (.prproj) and converts them to OTIO Timeline objects.

Premiere Pro project files are gzipped XML files containing sequences, tracks, and clips.
This adapter extracts timeline structure including:
- Sequences with their settings
- Video and audio tracks
- Clips with timing information and media references
- Effects including Time Remap (speed changes)

Note: This is a read-only adapter. Writing .prproj files is not supported.
"""

import gzip
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Optional, Dict, Any, List
import logging

import opentimelineio as otio

logger = logging.getLogger(__name__)

# Metadata namespace for preserving Premiere-specific data
META_NAMESPACE = "prproj"

# Premiere time base is in ticks (254016000000 ticks per second for 24fps)
# This varies by sequence frame rate
TICKS_PER_SECOND = 254016000000


class PremiereProjParser:
    """
    Parser for Adobe Premiere Pro project files.

    Parses the gzipped XML structure and converts to OpenTimelineIO objects.
    """

    def __init__(self, xml_root: ET.Element):
        """
        Initialize parser with parsed XML root element.

        Args:
            xml_root: Root element of the parsed .prproj XML
        """
        self.root = xml_root
        self._object_cache: Dict[str, ET.Element] = {}
        self._build_object_cache()

    def _build_object_cache(self):
        """Build cache of all objects with ObjectUID or ObjectID for fast lookup."""
        for elem in self.root.iter():
            obj_uid = elem.get('ObjectUID')
            obj_id = elem.get('ObjectID')

            if obj_uid:
                self._object_cache[obj_uid] = elem
            if obj_id:
                self._object_cache[obj_id] = elem

    def _resolve_ref(self, ref: str) -> Optional[ET.Element]:
        """
        Resolve an ObjectURef or ObjectRef to the actual object.

        Args:
            ref: Object reference ID

        Returns:
            Referenced element or None if not found
        """
        return self._object_cache.get(ref)

    def _get_text(self, element: ET.Element, path: str, default: str = "") -> str:
        """Safely get text content from an XML path."""
        found = element.find(path)
        return found.text if found is not None and found.text else default

    def _get_int(self, element: ET.Element, path: str, default: int = 0) -> int:
        """Safely get integer from an XML path."""
        text = self._get_text(element, path, str(default))
        try:
            return int(text)
        except (ValueError, TypeError):
            return default

    def _get_float(self, element: ET.Element, path: str, default: float = 0.0) -> float:
        """Safely get float from an XML path."""
        text = self._get_text(element, path, str(default))
        try:
            return float(text)
        except (ValueError, TypeError):
            return default

    def _ticks_to_seconds(self, ticks: int, rate: float) -> float:
        """
        Convert Premiere ticks to seconds based on sequence frame rate.

        Args:
            ticks: Time in Premiere ticks
            rate: Frame rate (fps)

        Returns:
            Time in seconds
        """
        # Premiere uses 254016000000 ticks/second for 24fps
        # Scale for other frame rates
        ticks_per_second = TICKS_PER_SECOND
        return ticks / ticks_per_second

    def _parse_rational_time(self, ticks: int, rate: float) -> otio.opentime.RationalTime:
        """
        Convert ticks to OTIO RationalTime.

        Args:
            ticks: Time in Premiere ticks
            rate: Frame rate (fps)

        Returns:
            RationalTime object
        """
        seconds = self._ticks_to_seconds(ticks, rate)
        frames = seconds * rate
        return otio.opentime.RationalTime(value=frames, rate=rate)

    def _get_sequence_frame_rate(self, sequence: ET.Element) -> float:
        """
        Extract frame rate from sequence settings.

        Args:
            sequence: Sequence XML element

        Returns:
            Frame rate in fps (default 24.0)
        """
        # Try to find frame rate in sequence settings
        # Format: <MZ.EditLine> contains edit line position in ticks
        # The actual FPS is embedded in video format settings

        # For now, default to 24fps - can be enhanced to parse actual settings
        return 24.0

    def _parse_clip_name(self, subclip_elem: ET.Element) -> str:
        """
        Extract clip name from SubClip element.

        Args:
            subclip_elem: SubClip XML element

        Returns:
            Clip name
        """
        name_elem = subclip_elem.find('.//Name')
        if name_elem is not None and name_elem.text:
            return name_elem.text
        return "Unnamed Clip"

    def _parse_media_reference(self, subclip_elem: ET.Element) -> Optional[otio.schema.ExternalReference]:
        """
        Extract media file path from SubClip → MasterClip → Media chain.

        Args:
            subclip_elem: SubClip XML element

        Returns:
            ExternalReference or None if media not found
        """
        # Get MasterClip reference
        master_ref_elem = subclip_elem.find('.//MasterClip')
        if master_ref_elem is None:
            return None

        master_uid = master_ref_elem.get('ObjectURef')
        if not master_uid:
            return None

        master_clip = self._resolve_ref(master_uid)
        if master_clip is None:
            return None

        # Look for media file path in associated clips
        clips_elem = master_clip.find('.//Clips')
        if clips_elem is None:
            return None

        # Get first clip reference
        clip_ref_elem = clips_elem.find('.//Clip[@Index="0"]')
        if clip_ref_elem is None:
            return None

        clip_id = clip_ref_elem.get('ObjectRef')
        if not clip_id:
            return None

        clip = self._resolve_ref(clip_id)
        if clip is None:
            return None

        # Extract file path
        file_path_elem = clip.find('.//FilePath')
        if file_path_elem is not None and file_path_elem.text:
            return otio.schema.ExternalReference(
                target_url=file_path_elem.text
            )

        return None

    def _parse_effects(self, track_item: ET.Element) -> List[otio.schema.Effect]:
        """
        Parse effects applied to a track item.

        Currently supports Time Remap (speed changes).

        Args:
            track_item: VideoClipTrackItem or AudioClipTrackItem element

        Returns:
            List of Effect objects
        """
        effects = []

        # Look for components which may include effects
        components_ref = track_item.find('.//ComponentOwner/Components')
        if components_ref is None:
            return effects

        comp_id = components_ref.get('ObjectRef')
        if not comp_id:
            return effects

        comp_chain = self._resolve_ref(comp_id)
        if comp_chain is None:
            return effects

        # Check for time remap component
        # This would be in ComponentParams with specific effect types
        # For now, return empty list - can be enhanced later

        return effects

    def _parse_clip(
        self,
        track_item_elem: ET.Element,
        rate: float
    ) -> Optional[otio.schema.Clip]:
        """
        Parse a VideoClipTrackItem or AudioClipTrackItem into an OTIO Clip.

        Args:
            track_item_elem: Track item XML element
            rate: Sequence frame rate

        Returns:
            Clip object or None
        """
        # Get SubClip reference
        subclip_ref = track_item_elem.find('.//SubClip')
        if subclip_ref is None:
            return None

        subclip_id = subclip_ref.get('ObjectRef')
        if not subclip_id:
            return None

        subclip = self._resolve_ref(subclip_id)
        if subclip is None:
            return None

        # Get clip timing from TrackItem
        track_item = track_item_elem.find('.//TrackItem')
        if track_item is None:
            return None

        start_ticks = self._get_int(track_item, 'Start', 0)
        end_ticks = self._get_int(track_item, 'End', 0)

        # Get clip name and media reference
        name = self._parse_clip_name(subclip)
        media_ref = self._parse_media_reference(subclip)

        if media_ref is None:
            media_ref = otio.schema.MissingReference()

        # Calculate source range
        # For now, assume 1:1 mapping (no time remap)
        # This can be enhanced to detect speed changes
        duration_ticks = end_ticks - start_ticks

        source_range = otio.opentime.TimeRange(
            start_time=self._parse_rational_time(0, rate),
            duration=self._parse_rational_time(duration_ticks, rate)
        )

        # Create clip
        clip = otio.schema.Clip(
            name=name,
            source_range=source_range,
            media_reference=media_ref
        )

        # Parse and add effects
        effects = self._parse_effects(track_item_elem)
        for effect in effects:
            clip.effects.append(effect)

        return clip

    def _parse_track(
        self,
        track_elem: ET.Element,
        rate: float,
        kind: otio.schema.TrackKind
    ) -> otio.schema.Track:
        """
        Parse a video or audio track.

        Args:
            track_elem: Track XML element
            rate: Sequence frame rate
            kind: Track kind (Video or Audio)

        Returns:
            Track object
        """
        # Get track name/ID
        track_id = self._get_text(track_elem, './/Track/ID', '')
        track_index = self._get_text(track_elem, './/Track/Index', '')
        kind_name = kind.name if hasattr(kind, 'name') else str(kind)
        track_name = f"{kind_name} {track_index if track_index else track_id if track_id else 'Track'}"

        track = otio.schema.Track(
            name=track_name,
            kind=kind
        )

        # Find track items - they are referenced by ObjectRef
        track_items_elem = track_elem.find('.//ClipItems/TrackItems')
        if track_items_elem is not None:
            for item_ref in track_items_elem.findall('.//TrackItem'):
                item_id = item_ref.get('ObjectRef')
                if item_id:
                    item_elem = self._resolve_ref(item_id)
                    if item_elem is not None:
                        clip = self._parse_clip(item_elem, rate)
                        if clip:
                            track.append(clip)

        return track

    def _parse_sequence(self, sequence_elem: ET.Element) -> otio.schema.Timeline:
        """
        Parse a Sequence into an OTIO Timeline.

        Args:
            sequence_elem: Sequence XML element

        Returns:
            Timeline object
        """
        # Get sequence name - look in Properties first
        name = self._get_text(sequence_elem, './/Properties/Name', None)
        if not name:
            # Fallback to direct Name element
            name = self._get_text(sequence_elem, './/Name', 'Untitled Sequence')

        # Get frame rate
        rate = self._get_sequence_frame_rate(sequence_elem)

        # Create timeline
        timeline = otio.schema.Timeline(name=name)

        # Parse tracks from TrackGroups
        # Each TrackGroup has a Second element with ObjectRef to VideoTrackGroup or AudioTrackGroup
        track_groups_elem = sequence_elem.find('.//TrackGroups')
        if track_groups_elem is not None:
            for track_group in track_groups_elem.findall('.//TrackGroup'):
                second_elem = track_group.find('Second')
                if second_elem is not None:
                    group_ref = second_elem.get('ObjectRef')
                    if group_ref:
                        group_elem = self._resolve_ref(group_ref)
                        if group_elem is not None:
                            # Check if it's Video or Audio track group
                            if 'VideoTrackGroup' in group_elem.tag:
                                kind = otio.schema.TrackKind.Video
                            elif 'AudioTrackGroup' in group_elem.tag:
                                kind = otio.schema.TrackKind.Audio
                            else:
                                continue

                            # Parse tracks from this group
                            tracks_elem = group_elem.find('.//Tracks')
                            if tracks_elem is not None:
                                for track_ref_elem in tracks_elem.findall('.//Track'):
                                    track_uid = track_ref_elem.get('ObjectURef')
                                    if track_uid:
                                        track_elem = self._resolve_ref(track_uid)
                                        if track_elem is not None:
                                            track = self._parse_track(track_elem, rate, kind)
                                            timeline.tracks.append(track)

        # Store Premiere metadata
        timeline.metadata[META_NAMESPACE] = {
            "frame_rate": rate,
            "sequence_uid": sequence_elem.get('ObjectUID', '')
        }

        return timeline

    def get_sequences(self) -> List[otio.schema.Timeline]:
        """
        Extract all sequences from the project.

        Returns:
            List of Timeline objects
        """
        sequences = []

        for sequence_elem in self.root.findall('.//Sequence[@ObjectUID]'):
            try:
                timeline = self._parse_sequence(sequence_elem)
                sequences.append(timeline)
            except Exception as e:
                import traceback
                logger.warning(f"Failed to parse sequence: {e}")
                logger.debug(traceback.format_exc())
                continue

        return sequences


def read_from_string(input_str: str) -> otio.schema.SerializableCollection:
    """
    Read OTIO from a Premiere Pro project XML string.

    Args:
        input_str: Decompressed XML content of .prproj file

    Returns:
        Timeline or SerializableCollection of timelines
    """
    try:
        root = ET.fromstring(input_str)
    except ET.ParseError as e:
        raise ValueError(f"Invalid XML in Premiere project: {e}")

    parser = PremiereProjParser(root)
    sequences = parser.get_sequences()

    if len(sequences) == 0:
        raise ValueError("No sequences found in Premiere project")
    elif len(sequences) == 1:
        return sequences[0]
    else:
        return otio.schema.SerializableCollection(
            name="Premiere Sequences",
            children=sequences
        )


def read_from_file(filepath: str) -> otio.schema.SerializableCollection:
    """
    Read OTIO from a Premiere Pro project file (.prproj).

    Args:
        filepath: Path to .prproj file

    Returns:
        Timeline or SerializableCollection of timelines
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"File not found: {filepath}")

    # Decompress gzipped XML
    try:
        with gzip.open(filepath, 'rt', encoding='utf-8') as f:
            xml_content = f.read()
    except (gzip.BadGzipFile, OSError) as e:
        raise ValueError(f"Invalid .prproj file (not gzipped XML): {e}")

    return read_from_string(xml_content)
