"""
Composable algebra for media operations.

This module defines an immutable, composable algebra for describing media operations
without being tied to any specific execution backend (ffmpeg, etc.).

Design principles:
- Immutable data structures (frozen dataclasses)
- Composable operations (functions that return new values)
- Separation of specification from execution
- Type-safe with clear semantics
"""

from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


# ============================================================================
# Time Algebra
# ============================================================================

@dataclass(frozen=True)
class TimeRange:
    """
    Represents a time range in seconds.

    Immutable and provides operations for working with time ranges.
    """
    start: float  # Start time in seconds
    duration: float  # Duration in seconds

    @property
    def end(self) -> float:
        """End time (start + duration)"""
        return self.start + self.duration

    def overlaps(self, other: TimeRange) -> bool:
        """Check if this range overlaps with another"""
        return self.start < other.end and other.start < self.end

    def intersection(self, other: TimeRange) -> TimeRange | None:
        """
        Get the intersection of two ranges.

        Returns None if ranges don't overlap.
        """
        start = max(self.start, other.start)
        end = min(self.end, other.end)
        if start >= end:
            return None
        return TimeRange(start, end - start)

    def offset_by(self, offset: float) -> TimeRange:
        """Return a new TimeRange offset by the given amount"""
        return TimeRange(self.start + offset, self.duration)


# ============================================================================
# Media References
# ============================================================================

@dataclass(frozen=True)
class MediaFile:
    """
    Reference to a media file on disk.

    This is just a reference - no I/O is performed.
    """
    path: Path

    def __str__(self) -> str:
        return str(self.path)


# ============================================================================
# Stream Algebra
# ============================================================================

@dataclass(frozen=True)
class VideoStream:
    """
    A video stream (video only, no audio).

    Represents extracting video from a source file within a specific time range.
    """
    media: MediaFile
    source_range: TimeRange

    def trim(self, time_range: TimeRange) -> VideoStream:
        """Trim this stream to a new time range"""
        return VideoStream(self.media, time_range)


@dataclass(frozen=True)
class AudioStream:
    """
    A single audio stream.

    Represents extracting audio from a source file within a specific time range,
    optionally offset in the output timeline.
    """
    media: MediaFile
    source_range: TimeRange
    track_index: int = 0  # Which audio track from the source file
    offset: float = 0.0  # Offset in output timeline (seconds)

    def trim(self, time_range: TimeRange) -> AudioStream:
        """Trim this stream to a new time range"""
        return AudioStream(
            self.media,
            time_range,
            self.track_index,
            self.offset
        )

    def with_offset(self, offset: float) -> AudioStream:
        """Return a new stream with a different output offset"""
        return AudioStream(
            self.media,
            self.source_range,
            self.track_index,
            offset
        )


@dataclass(frozen=True)
class AudioMix:
    """
    Mix multiple audio streams together.

    All streams are mixed with equal weight. Use offset on individual
    streams to align them in time.
    """
    streams: tuple[AudioStream, ...]

    def __post_init__(self) -> None:
        """Validate that we have at least one stream"""
        if len(self.streams) == 0:
            raise ValueError("AudioMix requires at least one stream")

    def add_stream(self, stream: AudioStream) -> AudioMix:
        """Add a stream to the mix (returns new AudioMix)"""
        return AudioMix(self.streams + (stream,))

    @staticmethod
    def from_streams(streams: list[AudioStream]) -> AudioStream | AudioMix | None:
        """
        Convenience method to create the appropriate audio type.

        Returns:
            - None if streams is empty
            - AudioStream if only one stream
            - AudioMix if multiple streams
        """
        if len(streams) == 0:
            return None
        elif len(streams) == 1:
            return streams[0]
        else:
            return AudioMix(tuple(streams))


# ============================================================================
# Composition Algebra
# ============================================================================

@dataclass(frozen=True)
class AVComposition:
    """
    A composition combining video and audio.

    This is the core composable unit - video with optional audio.
    """
    video: VideoStream
    audio: AudioStream | AudioMix | None

    def replace_audio(self, audio: AudioStream | AudioMix | None) -> AVComposition:
        """Return a new composition with different audio"""
        return AVComposition(self.video, audio)

    def trim_video(self, time_range: TimeRange) -> AVComposition:
        """Return a new composition with trimmed video"""
        return AVComposition(self.video.trim(time_range), self.audio)


@dataclass(frozen=True)
class Output:
    """
    Final output specification.

    Describes what to render and where to save it.
    """
    composition: AVComposition
    output_path: Path
    format: str = 'mp4'
    codec_video: str = 'libx264'
    codec_audio: str = 'aac'
    preset: str = 'veryfast'  # For faster preview generation

    def with_path(self, path: Path) -> Output:
        """Return a new output with a different path"""
        return Output(
            self.composition,
            path,
            self.format,
            self.codec_video,
            self.codec_audio,
            self.preset
        )


# ============================================================================
# Builder Functions
# ============================================================================

def build_video_stream(
    media_path: Path,
    source_start: float,
    source_duration: float
) -> VideoStream:
    """Build a video stream from basic parameters"""
    return VideoStream(
        media=MediaFile(media_path),
        source_range=TimeRange(source_start, source_duration)
    )


def build_audio_stream(
    media_path: Path,
    source_start: float,
    source_duration: float,
    offset: float = 0.0,
    track_index: int = 0
) -> AudioStream:
    """Build an audio stream from basic parameters"""
    return AudioStream(
        media=MediaFile(media_path),
        source_range=TimeRange(source_start, source_duration),
        track_index=track_index,
        offset=offset
    )


def mix_audio_streams(streams: list[AudioStream]) -> AudioStream | AudioMix | None:
    """Convenience function to mix audio streams"""
    return AudioMix.from_streams(streams)
