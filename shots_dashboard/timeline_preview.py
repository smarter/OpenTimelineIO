"""
Timeline-aware preview generation using the media algebra.

This module integrates the media algebra with the timeline data to generate
previews that include audio from overlapping tracks.
"""

from __future__ import annotations
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from media_algebra import TimeRange, AVComposition, Output
from preview_builder import TimelineClip, build_clip_preview_with_audio
from ffmpeg_interpreter import to_ffmpeg_command, validate_output


logger = logging.getLogger(__name__)


class TimelinePreviewError(Exception):
    """Error during timeline preview generation"""
    pass


def generate_timeline_preview(
    video_clip_data: dict[str, Any],
    video_clip_path: Path,
    timeline_data: dict[str, Any] | None,
    output_dir: Path | None = None
) -> Path:
    """
    Generate a preview for a video clip with audio from overlapping timeline tracks.

    Args:
        video_clip_data: Clip data from frontend (source_start, duration, etc.)
        video_clip_path: Path to the video file
        timeline_data: Timeline visual data including all tracks and clips
        output_dir: Directory for output file (defaults to temp)

    Returns:
        Path to generated preview file

    Raises:
        TimelinePreviewError: If preview generation fails
    """
    try:
        # Create output directory if needed
        if output_dir is None:
            output_dir = Path(tempfile.gettempdir()) / "timeline_previews"
            output_dir.mkdir(parents=True, exist_ok=True)

        # Generate unique output filename based on video path and clip data
        import hashlib
        import json

        clip_hash = hashlib.md5(
            json.dumps({
                'path': str(video_clip_path),
                'data': video_clip_data
            }, sort_keys=True).encode()
        ).hexdigest()[:12]

        output_path = output_dir / f"{video_clip_path.stem}_{clip_hash}.webm"

        # Check if preview already exists
        if output_path.exists():
            logger.info(f"Using cached preview: {output_path.name}")
            return output_path

        # If no timeline data, generate simple preview
        if not timeline_data or 'tracks' not in timeline_data:
            logger.info("No timeline data, generating simple preview")
            return _generate_simple_preview(
                video_clip_data,
                video_clip_path,
                output_path
            )

        # Build TimelineClip objects from the data
        try:
            video_clip, all_clips = _build_timeline_clips(
                video_clip_data,
                video_clip_path,
                timeline_data
            )
        except Exception as e:
            logger.warning(f"Failed to build timeline clips: {e}, falling back to simple preview")
            return _generate_simple_preview(
                video_clip_data,
                video_clip_path,
                output_path
            )

        # Build composition using the algebra
        output = build_clip_preview_with_audio(
            video_clip=video_clip,
            all_clips=all_clips,
            output_path=output_path
        )

        # Validate composition
        errors = validate_output(output)
        if errors:
            logger.error(f"Invalid composition: {errors}")
            raise TimelinePreviewError(f"Invalid composition: {', '.join(errors)}")

        # Convert to ffmpeg command
        cmd = to_ffmpeg_command(output)

        logger.info(f"Generating timeline preview: {output_path.name}")
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")

        # Execute ffmpeg
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg failed: {result.stderr}")
            raise TimelinePreviewError(f"FFmpeg error: {result.stderr[:200]}")

        if not output_path.exists():
            raise TimelinePreviewError("Preview file was not created")

        logger.info(f"Preview generated successfully: {output_path.name}")
        return output_path

    except subprocess.TimeoutExpired:
        raise TimelinePreviewError("Preview generation timed out")
    except Exception as e:
        logger.error(f"Preview generation failed: {e}", exc_info=True)
        raise TimelinePreviewError(str(e)) from e


def _generate_simple_preview(
    clip_data: dict[str, Any],
    source_path: Path,
    output_path: Path
) -> Path:
    """Generate a simple preview without timeline audio mixing"""
    from clip_preview import ClipPreviewGenerator

    generator = ClipPreviewGenerator()
    return generator.generate_preview(clip_data, source_path)


def _build_timeline_clips(
    video_clip_data: dict[str, Any],
    video_clip_path: Path,
    timeline_data: dict[str, Any]
) -> tuple[TimelineClip, list[TimelineClip]]:
    """
    Build TimelineClip objects from frontend data.

    Args:
        video_clip_data: The video clip being previewed
        video_clip_path: Path to video file
        timeline_data: Full timeline data with all tracks

    Returns:
        Tuple of (video_clip, all_clips)
    """
    # Extract video clip info
    source_start = video_clip_data.get('source_start', 0.0)
    source_duration = video_clip_data.get('source_duration')

    if source_duration is None:
        # Calculate from source_end if available
        source_end = video_clip_data.get('source_end')
        if source_end is not None:
            source_duration = source_end - source_start
        else:
            # Use clip duration if available
            source_duration = video_clip_data.get('duration', 10.0)

    # Get timeline position - this should be in the clip data
    timeline_start = video_clip_data.get('timeline_start', video_clip_data.get('start', 0.0))
    timeline_duration = video_clip_data.get('timeline_duration', video_clip_data.get('duration', source_duration))

    # Create the video clip
    video_clip = TimelineClip(
        name=video_clip_path.name,
        source_path=video_clip_path,
        timeline_start=timeline_start,
        timeline_duration=timeline_duration,
        source_start=source_start,
        source_duration=source_duration,
        track_kind='Video',
        track_index=0
    )

    # Extract all clips from timeline
    all_clips = [video_clip]

    for track in timeline_data.get('tracks', []):
        track_kind = track.get('kind', 'Video')

        # Only interested in audio tracks for mixing
        if track_kind != 'Audio':
            continue

        for clip_info in track.get('clips', []):
            # Skip clips without proper timing info
            if 'start' not in clip_info or 'duration' not in clip_info:
                continue

            # Get source path - need to resolve the clip name to a full path
            clip_name = clip_info['name']
            # TODO: Resolve clip name to full path using tracker
            # For now, assume clip_name is the filename
            clip_path = video_clip_path.parent / clip_name

            clip = TimelineClip(
                name=clip_name,
                source_path=clip_path,
                timeline_start=clip_info['start'],
                timeline_duration=clip_info['duration'],
                source_start=clip_info.get('source_start', 0.0),
                source_duration=clip_info.get('source_duration', clip_info['duration']),
                track_kind='Audio',
                track_index=int(track.get('name', 'Track 0').split()[-1]) if 'name' in track else 0
            )
            all_clips.append(clip)

    logger.info(f"Built {len(all_clips)} timeline clips ({len([c for c in all_clips if c.track_kind == 'Audio'])} audio)")

    return video_clip, all_clips
