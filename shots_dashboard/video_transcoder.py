"""
Video transcoding module for on-the-fly conversion to web-compatible formats.

Converts video files to VP8/Vorbis (WebM) format for browser playback using ffmpeg.
Uses real-time settings optimized for fast transcoding.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Generator


class TranscodingError(Exception):
    """Error during video transcoding."""
    pass


def is_web_compatible(file_path: Path) -> bool:
    """
    Check if file is already in a web-compatible format.

    Web browsers natively support:
    - MP4 with H.264/AAC
    - WebM with VP8 or VP9/Vorbis or Opus
    - OGG with Theora/Vorbis

    Args:
        file_path: Path to video file

    Returns:
        True if file is web-compatible
    """
    # Common web-compatible extensions
    web_formats = {'.mp4', '.webm', '.ogg'}
    return file_path.suffix.lower() in web_formats


def check_ffmpeg_available() -> bool:
    """
    Check if ffmpeg is available on the system.

    Returns:
        True if ffmpeg is available
    """
    try:
        subprocess.run(
            ['ffmpeg', '-version'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def transcode_to_webm(
    input_path: Path,
    output_path: Path | None = None,
    width: int = 480,
    fps: int = 15,
    bitrate: str = "500k",
    audio_bitrate: str = "64k"
) -> Path:
    """
    Transcode video to WebM format (VP8/Vorbis) optimized for web preview.

    Uses real-time settings for fast transcoding:
    - VP8 video codec with fast encoding preset
    - Vorbis audio codec
    - Reduced resolution (default 480p width)
    - Lower framerate (default 15 fps)
    - Moderate bitrate for quick streaming

    Args:
        input_path: Path to input video file
        output_path: Path for output file (default: input_path with .webm extension)
        width: Target width in pixels (height calculated to maintain aspect ratio)
        fps: Target framerate
        bitrate: Video bitrate
        audio_bitrate: Audio bitrate

    Returns:
        Path to transcoded WebM file

    Raises:
        TranscodingError: If transcoding fails
    """
    if not input_path.exists():
        raise TranscodingError(f"Input file does not exist: {input_path}")

    if not check_ffmpeg_available():
        raise TranscodingError("ffmpeg is not available on the system")

    # Default output path
    if output_path is None:
        output_path = input_path.with_suffix('.webm')

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ffmpeg command for fast real-time transcoding
    command = [
        'ffmpeg',
        '-i', str(input_path),

        # Video encoding settings (VP8)
        '-c:v', 'libvpx',           # VP8 codec
        '-quality', 'realtime',      # Real-time mode for speed
        '-cpu-used', '5',            # Fast encoding (0-16, higher = faster)
        '-deadline', 'realtime',     # Real-time deadline
        '-b:v', bitrate,             # Video bitrate
        '-vf', f'scale={width}:-2',  # Scale to target width, maintain aspect ratio
        '-r', str(fps),              # Framerate

        # Audio encoding settings (Vorbis)
        '-c:a', 'libvorbis',         # Vorbis codec
        '-b:a', audio_bitrate,       # Audio bitrate
        '-ac', '2',                  # Stereo audio

        # Container settings
        '-f', 'webm',                # WebM container

        # Overwrite output file
        '-y',

        str(output_path)
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )

        if not output_path.exists():
            raise TranscodingError("Transcoding completed but output file not found")

        return output_path

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "Unknown error"
        raise TranscodingError(f"ffmpeg failed: {error_msg}") from e


def stream_transcode_webm(
    input_path: Path,
    width: int = 480,
    fps: int = 15,
    bitrate: str = "500k",
    audio_bitrate: str = "64k"
) -> subprocess.Popen:
    """
    Start streaming transcode to WebM format for progressive streaming.

    Returns a Popen object that outputs WebM data to stdout.
    Useful for streaming video while transcoding.

    Args:
        input_path: Path to input video file
        width: Target width in pixels
        fps: Target framerate
        bitrate: Video bitrate
        audio_bitrate: Audio bitrate

    Returns:
        subprocess.Popen object with WebM output on stdout

    Raises:
        TranscodingError: If transcoding cannot start
    """
    if not input_path.exists():
        raise TranscodingError(f"Input file does not exist: {input_path}")

    if not check_ffmpeg_available():
        raise TranscodingError("ffmpeg is not available on the system")

    # ffmpeg command for streaming output
    command = [
        'ffmpeg',
        '-i', str(input_path),

        # Video encoding settings (VP8)
        '-c:v', 'libvpx',
        '-quality', 'realtime',
        '-cpu-used', '5',
        '-deadline', 'realtime',
        '-b:v', bitrate,
        '-vf', f'scale={width}:-2',
        '-r', str(fps),

        # Audio encoding settings (Vorbis)
        '-c:a', 'libvorbis',
        '-b:a', audio_bitrate,
        '-ac', '2',

        # Container settings for streaming
        '-f', 'webm',
        '-cluster_size_limit', '2M',    # Small clusters for progressive streaming
        '-cluster_time_limit', '5100',  # Cluster every 5.1 seconds

        # Output to stdout (pipe)
        'pipe:1'
    ]

    try:
        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return process

    except Exception as e:
        raise TranscodingError(f"Failed to start streaming transcode: {e}") from e


def get_video_info(file_path: Path) -> dict[str, str | int]:
    """
    Get basic video file information using ffprobe.

    Args:
        file_path: Path to video file

    Returns:
        Dictionary with video info (duration, width, height, codec)

    Raises:
        TranscodingError: If ffprobe fails
    """
    if not file_path.exists():
        raise TranscodingError(f"File does not exist: {file_path}")

    command = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=width,height,codec_name,duration',
        '-of', 'default=noprint_wrappers=1',
        str(file_path)
    ]

    try:
        result = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )

        # Parse output
        info = {}
        for line in result.stdout.strip().split('\n'):
            if '=' in line:
                key, value = line.split('=', 1)
                # Try to convert to int if possible
                try:
                    info[key] = int(value)
                except ValueError:
                    info[key] = value

        return info

    except subprocess.CalledProcessError as e:
        raise TranscodingError(f"ffprobe failed: {e}") from e
