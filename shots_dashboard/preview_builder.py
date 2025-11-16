"""
Build preview compositions from timeline data.

This module converts timeline clip information into the media algebra,
calculating overlaps and time mappings.
"""

from __future__ import annotations
import logging
from pathlib import Path
from typing import NamedTuple

from media_algebra import (
    TimeRange,
    VideoStream,
    AudioStream,
    AudioMix,
    AVComposition,
    Output,
    MediaFile,
    build_video_stream,
    build_audio_stream,
    mix_audio_streams,
)


logger = logging.getLogger(__name__)


# ============================================================================
# Timeline Data Structures
# ============================================================================

class TimelineClip(NamedTuple):
    """
    Represents a clip in a timeline.

    This is input data from the timeline analysis.
    """
    name: str
    source_path: Path
    # Timeline position (when it appears in the sequence)
    timeline_start: float
    timeline_duration: float
    # Source range (which part of the source media to use)
    source_start: float
    source_duration: float
    # Track info
    track_kind: str  # 'Video' or 'Audio'
    track_index: int  # Which track (0-indexed)


# ============================================================================
# Preview Builder
# ============================================================================

def build_clip_preview_with_audio(
    video_clip: TimelineClip,
    all_clips: list[TimelineClip],
    output_path: Path
) -> Output:
    """
    Build a preview composition for a video clip with audio from overlapping tracks.

    This is the main entry point for generating video previews that include
    audio from the timeline.

    Algorithm:
    1. Extract video from the video clip
    2. Find all audio clips that overlap with the video clip's timeline range
    3. For each overlapping audio clip:
       - Calculate the intersection
       - Map timeline coordinates to source coordinates
       - Create an AudioStream with appropriate offset
    4. Mix all audio streams
    5. Combine video and mixed audio

    Args:
        video_clip: The video clip to preview
        all_clips: All clips in the timeline (including audio)
        output_path: Where to save the preview

    Returns:
        An Output specification ready to be executed
    """
    # 1. Create video stream from the clip
    video_stream = build_video_stream(
        media_path=video_clip.source_path,
        source_start=video_clip.source_start,
        source_duration=video_clip.source_duration
    )

    # Define the video's timeline range
    video_timeline_range = TimeRange(
        start=video_clip.timeline_start,
        duration=video_clip.timeline_duration
    )

    # 2. Find overlapping audio clips and build audio streams
    audio_streams: list[AudioStream] = []

    logger.info(f"Checking audio clips for overlap with video timeline {video_timeline_range.start:.2f}-{video_timeline_range.end:.2f}s")

    for clip in all_clips:
        # Skip non-audio clips
        if clip.track_kind != 'Audio':
            continue

        # Define this clip's timeline range
        clip_timeline_range = TimeRange(
            start=clip.timeline_start,
            duration=clip.timeline_duration
        )

        # Check for overlap
        overlap = video_timeline_range.intersection(clip_timeline_range)
        if overlap is None:
            logger.info(f"  '{clip.name}' at {clip_timeline_range.start:.2f}-{clip_timeline_range.end:.2f}s: NO OVERLAP - excluding")
            continue

        logger.info(f"  '{clip.name}' at {clip_timeline_range.start:.2f}-{clip_timeline_range.end:.2f}s: OVERLAP {overlap.start:.2f}-{overlap.end:.2f}s - including")

        # 3. Calculate source range for this overlap
        # How far into the audio clip does the overlap start?
        offset_in_clip = overlap.start - clip.timeline_start

        # Map timeline offset to source offset
        # The audio source starts at clip.source_start, and we need to offset
        # by how far into the clip the overlap begins
        audio_source_start = clip.source_start + offset_in_clip
        audio_source_duration = overlap.duration

        # Calculate output offset (relative to video start)
        # This is where in the output this audio should start
        output_offset = overlap.start - video_timeline_range.start

        # Create audio stream
        audio_stream = build_audio_stream(
            media_path=clip.source_path,
            source_start=audio_source_start,
            source_duration=audio_source_duration,
            offset=output_offset,
            track_index=0  # Assume first audio track for now
        )
        audio_streams.append(audio_stream)

    # 4. Create audio mix (or single stream, or None)
    audio = mix_audio_streams(audio_streams)

    # 5. Create composition
    composition = AVComposition(
        video=video_stream,
        audio=audio
    )

    # 6. Create output specification
    # Use WebM codecs if output is .webm
    if output_path.suffix.lower() == '.webm':
        return Output(
            composition=composition,
            output_path=output_path,
            format='webm',
            codec_video='libvpx-vp9',
            codec_audio='libopus',
            preset='veryfast'  # Fast preview generation
        )
    else:
        return Output(
            composition=composition,
            output_path=output_path,
            preset='veryfast'  # Fast preview generation
        )


def build_simple_clip_preview(
    clip: TimelineClip,
    output_path: Path
) -> Output:
    """
    Build a simple preview for a clip using only its own audio.

    This is used for clips that don't need timeline audio mixing.

    Args:
        clip: The clip to preview
        output_path: Where to save the preview

    Returns:
        An Output specification
    """
    video_stream = build_video_stream(
        media_path=clip.source_path,
        source_start=clip.source_start,
        source_duration=clip.source_duration
    )

    # For video clips, include their own audio
    # For audio-only clips, this would need different handling
    if clip.track_kind == 'Video':
        audio_stream = build_audio_stream(
            media_path=clip.source_path,
            source_start=clip.source_start,
            source_duration=clip.source_duration,
            offset=0.0
        )
        audio = audio_stream
    else:
        audio = None

    composition = AVComposition(
        video=video_stream,
        audio=audio
    )

    # Use WebM codecs if output is .webm
    if output_path.suffix.lower() == '.webm':
        return Output(
            composition=composition,
            output_path=output_path,
            format='webm',
            codec_video='libvpx-vp9',
            codec_audio='libopus',
            preset='veryfast'
        )
    else:
        return Output(
            composition=composition,
            output_path=output_path,
            preset='veryfast'
        )


# ============================================================================
# Utilities
# ============================================================================

def calculate_overlap_params(
    target_range: TimeRange,
    clip_range: TimeRange,
    clip_source_start: float
) -> tuple[float, float, float] | None:
    """
    Calculate parameters for an overlapping clip.

    Returns:
        Tuple of (source_start, duration, output_offset) or None if no overlap
    """
    overlap = target_range.intersection(clip_range)
    if overlap is None:
        return None

    offset_in_clip = overlap.start - clip_range.start
    source_start = clip_source_start + offset_in_clip
    duration = overlap.duration
    output_offset = overlap.start - target_range.start

    return (source_start, duration, output_offset)
