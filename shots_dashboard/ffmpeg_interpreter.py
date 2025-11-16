"""
Interpret media algebra into ffmpeg commands.

This module is the "compiler" that converts our high-level media algebra
into concrete ffmpeg command-line arguments.
"""

from __future__ import annotations
from typing import Literal

from media_algebra import (
    Output,
    AVComposition,
    VideoStream,
    VideoSegment,
    AudioStream,
    AudioMix,
)


# ============================================================================
# FFmpeg Command Generation
# ============================================================================

def to_ffmpeg_command(output: Output) -> list[str]:
    """
    Convert an Output specification to ffmpeg command line arguments.

    This is the main interpreter for our algebra. It handles:
    - Video extraction with trimming
    - Audio extraction with trimming
    - Audio mixing with time offsets
    - Output encoding

    Args:
        output: The output specification to execute

    Returns:
        List of command-line arguments for ffmpeg
    """
    comp = output.composition
    cmd = ['ffmpeg', '-y']  # -y to overwrite output file

    # ========================================================================
    # Input Stage: Add all input files
    # ========================================================================

    # Check if video has segments (requires different handling)
    has_video_segments = comp.video.segments is not None and len(comp.video.segments) > 1

    if has_video_segments:
        # For segmented video, add input without seeking (we'll use filter_complex)
        cmd.extend(['-i', str(comp.video.media.path)])
        video_input_index = 0
    else:
        # For simple video, add input with seek and duration
        cmd.extend([
            '-ss', _format_time(comp.video.source_range.start),
            '-t', _format_time(comp.video.source_range.duration),
            '-i', str(comp.video.media.path)
        ])
        video_input_index = 0

    # Add audio inputs
    audio_input_indices = []
    if isinstance(comp.audio, AudioStream):
        # Single audio stream
        cmd.extend([
            '-ss', _format_time(comp.audio.source_range.start),
            '-t', _format_time(comp.audio.source_range.duration),
            '-i', str(comp.audio.media.path)
        ])
        audio_input_indices.append(1)

    elif isinstance(comp.audio, AudioMix):
        # Multiple audio streams to mix
        for i, stream in enumerate(comp.audio.streams):
            cmd.extend([
                '-ss', _format_time(stream.source_range.start),
                '-t', _format_time(stream.source_range.duration),
                '-i', str(stream.media.path)
            ])
            audio_input_indices.append(i + 1)

    # ========================================================================
    # Filter Stage: Build filter_complex for video and audio processing
    # ========================================================================

    filter_parts = []
    video_output_label = f'{video_input_index}:v'  # Default: direct video mapping

    # Handle segmented video first (if needed)
    if has_video_segments:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"Building video concat filter for {len(comp.video.segments)} segments")

        # Build video concat filter
        video_concat_parts = []

        for i, segment in enumerate(comp.video.segments):
            logger.info(f"  Segment {i}: source {segment.source_start:.6f}s, duration {segment.source_duration:.6f}s")

            # Use trim filter to extract each segment, then setpts to reset timestamps
            video_concat_parts.append(
                f"[{video_input_index}:v]trim=start={segment.source_start:.6f}:duration={segment.source_duration:.6f},setpts=PTS-STARTPTS[v{i}]"
            )

        # Concatenate all video segments
        segment_inputs = ''.join(f'[v{i}]' for i in range(len(comp.video.segments)))
        video_concat_parts.append(
            f"{segment_inputs}concat=n={len(comp.video.segments)}:v=1:a=0[vout]"
        )

        filter_parts.extend(video_concat_parts)
        video_output_label = '[vout]'  # Use concat output

    # Handle audio processing
    audio_output_label = None

    if isinstance(comp.audio, AudioMix) and len(comp.audio.streams) > 1:
        # Need to mix multiple audio streams with offsets
        audio_filter_parts = _build_audio_mix_filter_parts(comp.audio)
        filter_parts.extend(audio_filter_parts)
        audio_output_label = '[aout]'

    elif isinstance(comp.audio, AudioStream):
        # Single audio stream - check if it needs delay/offset or volume
        if comp.audio.offset > 0 or comp.audio.volume_db != 0.0:
            # Need to apply filters using filter_complex
            audio_filter_parts = _build_single_audio_filter_parts(comp.audio)
            filter_parts.extend(audio_filter_parts)
            audio_output_label = '[aout]'
        else:
            # No offset or volume adjustment, just map directly
            audio_output_label = '1:a'

    elif isinstance(comp.audio, AudioMix) and len(comp.audio.streams) == 1:
        # AudioMix with single stream - treat as single stream
        stream = comp.audio.streams[0]
        if stream.offset > 0 or stream.volume_db != 0.0:
            audio_filter_parts = _build_single_audio_filter_parts(stream)
            filter_parts.extend(audio_filter_parts)
            audio_output_label = '[aout]'
        else:
            audio_output_label = '1:a'

    # Build final filter_complex if needed
    if filter_parts:
        filter_complex = ';'.join(filter_parts)
        cmd.extend(['-filter_complex', filter_complex])

    # Map outputs
    cmd.extend(['-map', video_output_label])

    if audio_output_label:
        cmd.extend(['-map', audio_output_label])
    elif comp.audio is None:
        cmd.extend(['-an'])  # No audio
    else:
        cmd.extend(['-an'])  # Fallback

    # ========================================================================
    # Output Stage: Encoding options and output file
    # ========================================================================

    cmd.extend([
        '-c:v', output.codec_video,
        '-preset', output.preset,
    ])

    if comp.audio is not None:
        cmd.extend(['-c:a', output.codec_audio])

    cmd.append(str(output.output_path))

    return cmd


def _build_single_audio_filter_parts(audio_stream: AudioStream) -> list[str]:
    """
    Build filter parts for a single audio stream.

    Applies volume adjustment and/or delay as needed.

    Args:
        audio_stream: The AudioStream to process

    Returns:
        List of filter parts for filter_complex
    """
    filters = []

    # Apply volume adjustment if needed
    if audio_stream.volume_db != 0.0:
        filters.append(f"volume={audio_stream.volume_db}dB")

    # Apply delay if needed
    if audio_stream.offset > 0:
        delay_ms = int(audio_stream.offset * 1000)
        filters.append(f"adelay={delay_ms}:all=1")

    # Normalize format
    filters.append("aformat=sample_fmts=fltp")

    filter_chain = ','.join(filters)
    return [f"[1:a]{filter_chain}[aout]"]


def _build_single_audio_filter(audio_stream: AudioStream) -> str:
    """
    Build a filter_complex string for a single audio stream (legacy).

    Args:
        audio_stream: The AudioStream to process

    Returns:
        filter_complex string for ffmpeg
    """
    return ';'.join(_build_single_audio_filter_parts(audio_stream))


def _build_audio_mix_filter_parts(audio_mix: AudioMix) -> list[str]:
    """
    Build filter parts for mixing audio with offsets.

    This creates filter parts that:
    1. Delay each stream by its offset
    2. Mix all delayed streams together

    Args:
        audio_mix: The AudioMix to process

    Returns:
        List of filter parts for filter_complex
    """
    import logging
    logger = logging.getLogger(__name__)

    filter_parts = []

    # Process each stream
    for i, stream in enumerate(audio_mix.streams):
        input_idx = i + 1  # Input 0 is video, audio starts at 1

        logger.info(f"  Processing audio stream {i}: source {stream.source_range.start:.6f}s, offset {stream.offset:.6f}s, volume {stream.volume_db:.2f}dB")

        # Build filter chain for this stream
        filters = []

        # 1. Apply volume adjustment if needed
        if stream.volume_db != 0.0:
            filters.append(f"volume={stream.volume_db}dB")

        # 2. Apply delay if needed
        if stream.offset > 0:
            # Add silence padding at the beginning
            # adelay uses milliseconds, all=1 applies to all channels
            delay_ms = int(stream.offset * 1000)
            filters.append(f"adelay={delay_ms}:all=1")
            logger.info(f"    Applying adelay: {delay_ms}ms ({stream.offset:.6f}s)")

        # 3. Normalize audio format
        filters.append("aformat=sample_fmts=fltp")

        # Combine filters for this stream
        filter_chain = ','.join(filters)
        filter_parts.append(f"[{input_idx}:a]{filter_chain}[a{i}]")

    # Mix all processed streams
    # Use simple defaults: no artificial transitions, play until all streams end
    mix_inputs = ''.join(f'[a{i}]' for i in range(len(audio_mix.streams)))
    num_inputs = len(audio_mix.streams)

    filter_parts.append(
        f"{mix_inputs}amix=inputs={num_inputs}:duration=longest:dropout_transition=0[aout]"
    )

    return filter_parts


def _build_audio_mix_filter(audio_mix: AudioMix) -> str:
    """
    Build a filter_complex string for mixing audio with offsets (legacy).

    Args:
        audio_mix: The AudioMix to process

    Returns:
        filter_complex string for ffmpeg
    """
    return ';'.join(_build_audio_mix_filter_parts(audio_mix))


def _format_time(seconds: float) -> str:
    """
    Format time in seconds to ffmpeg's preferred format.

    Args:
        seconds: Time in seconds

    Returns:
        Formatted time string (HH:MM:SS.mmm)
    """
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = seconds % 60

    return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"


# ============================================================================
# Validation and Optimization
# ============================================================================

def validate_output(output: Output) -> list[str]:
    """
    Validate an Output specification.

    Returns:
        List of validation errors (empty if valid)
    """
    errors = []

    # Check video stream
    if output.composition.video.source_range.duration <= 0:
        errors.append("Video duration must be positive")

    if output.composition.video.source_range.start < 0:
        errors.append("Video start time must be non-negative")

    # Check audio streams
    audio = output.composition.audio
    if isinstance(audio, AudioStream):
        if audio.source_range.duration <= 0:
            errors.append("Audio duration must be positive")
        if audio.offset < 0:
            errors.append("Audio offset must be non-negative")

    elif isinstance(audio, AudioMix):
        for i, stream in enumerate(audio.streams):
            if stream.source_range.duration <= 0:
                errors.append(f"Audio stream {i} duration must be positive")
            if stream.offset < 0:
                errors.append(f"Audio stream {i} offset must be non-negative")

    # Check output path
    if not output.output_path.parent.exists():
        errors.append(f"Output directory does not exist: {output.output_path.parent}")

    return errors


def optimize_output(output: Output) -> Output:
    """
    Optimize an Output specification.

    This could perform optimizations like:
    - Removing silent audio streams
    - Merging adjacent clips
    - Simplifying filter graphs
    - etc.

    For now, this is a placeholder for future optimizations.

    Args:
        output: The output to optimize

    Returns:
        Optimized output (may be the same object)
    """
    # Future: Add optimizations here
    return output
