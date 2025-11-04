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
    - MP4 with H.264/AAC or H.264/MP3
    - WebM with VP8 or VP9/Vorbis or Opus
    - OGG with Theora/Vorbis

    This function checks the actual video and audio codecs using ffprobe,
    not just the file extension, to ensure true compatibility.

    Args:
        file_path: Path to video file

    Returns:
        True if file is web-compatible
    """
    # Quick check: non-web extensions are definitely not compatible
    ext = file_path.suffix.lower()
    non_web_formats = {'.mov', '.avi', '.mxf', '.mkv', '.m4v', '.mpg', '.mpeg', '.wmv', '.flv'}
    if ext in non_web_formats:
        return False

    # For potentially compatible formats, check the actual codecs
    web_formats = {'.mp4', '.webm', '.ogg', '.ogv'}
    if ext not in web_formats:
        return False

    # Check codecs using ffprobe
    try:
        if not check_ffmpeg_available():
            # If ffprobe unavailable, assume web-compatible based on extension
            return True

        info = get_video_codec_info(file_path)
        video_codec = info.get('video_codec', '').lower()
        audio_codec = info.get('audio_codec', '').lower()

        # Check if video codec is browser-compatible
        web_video_codecs = {'h264', 'vp8', 'vp9', 'av1', 'theora'}
        web_audio_codecs = {'aac', 'mp3', 'vorbis', 'opus', 'flac'}

        video_compatible = any(codec in video_codec for codec in web_video_codecs)
        audio_compatible = (not audio_codec) or any(codec in audio_codec for codec in web_audio_codecs)

        return video_compatible and audio_compatible

    except Exception:
        # If codec detection fails, assume compatible based on extension
        return True


def check_ffmpeg_available() -> bool:
    """
    Check if ffmpeg is available on the system.

    Returns:
        True if ffmpeg is available
    """
    import os

    # Add ~/.local/bin to PATH if not already there
    local_bin = os.path.expanduser('~/.local/bin')
    if local_bin not in os.environ.get('PATH', ''):
        os.environ['PATH'] = f"{local_bin}:{os.environ.get('PATH', '')}"

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


def get_video_codec_info(file_path: Path) -> dict[str, str]:
    """
    Get video and audio codec information using ffprobe.

    Args:
        file_path: Path to video file

    Returns:
        Dictionary with 'video_codec' and 'audio_codec' keys

    Raises:
        TranscodingError: If ffprobe fails
    """
    if not file_path.exists():
        raise TranscodingError(f"File does not exist: {file_path}")

    # Get video codec
    video_command = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'v:0',
        '-show_entries', 'stream=codec_name',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(file_path)
    ]

    # Get audio codec
    audio_command = [
        'ffprobe',
        '-v', 'error',
        '-select_streams', 'a:0',
        '-show_entries', 'stream=codec_name',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(file_path)
    ]

    try:
        video_result = subprocess.run(
            video_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
            text=True
        )
        video_codec = video_result.stdout.strip()

        audio_result = subprocess.run(
            audio_command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,  # Audio stream might not exist
            text=True
        )
        audio_codec = audio_result.stdout.strip() if audio_result.returncode == 0 else ''

        return {
            'video_codec': video_codec,
            'audio_codec': audio_codec
        }

    except subprocess.CalledProcessError as e:
        raise TranscodingError(f"ffprobe failed: {e}") from e


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


def generate_test_video(
    output_path: Path,
    duration: int = 5,
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    pattern: str = "testsrc"
) -> None:
    """
    Generate a test video file with synthetic content.

    Creates a video with test pattern and sine wave audio for demo/testing purposes.

    Args:
        output_path: Path for output video file
        duration: Video duration in seconds
        width: Video width in pixels
        height: Video height in pixels
        fps: Framerate
        pattern: Test pattern type (testsrc, smptebars, rgbtestsrc, etc.)

    Raises:
        TranscodingError: If video generation fails
    """
    if not check_ffmpeg_available():
        raise TranscodingError("ffmpeg is not available on the system")

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Determine codec based on file extension
    ext = output_path.suffix.lower()

    if ext == '.mp4':
        video_codec = 'libx264'
        audio_codec = 'aac'
        pixel_format = 'yuv420p'
    elif ext == '.webm':
        video_codec = 'libvpx'
        audio_codec = 'libvorbis'
        pixel_format = 'yuv420p'
    elif ext == '.mov':
        video_codec = 'libx264'
        audio_codec = 'aac'
        pixel_format = 'yuv420p'
    else:
        # Default to WebM for unknown formats
        video_codec = 'libvpx'
        audio_codec = 'libvorbis'
        pixel_format = 'yuv420p'

    # Build ffmpeg command
    command = [
        'ffmpeg',
        # Video input: test pattern
        '-f', 'lavfi',
        '-i', f'{pattern}=duration={duration}:size={width}x{height}:rate={fps}',
        # Audio input: sine wave at 1000 Hz
        '-f', 'lavfi',
        '-i', f'sine=frequency=1000:duration={duration}',
        # Video codec
        '-c:v', video_codec,
        '-pix_fmt', pixel_format,
        # Audio codec
        '-c:a', audio_codec,
        '-b:a', '128k',
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
            raise TranscodingError("Video generation completed but output file not found")

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='ignore') if e.stderr else "Unknown error"
        raise TranscodingError(f"ffmpeg failed to generate test video: {error_msg}") from e
