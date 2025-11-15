"""
Clip-accurate preview generation for timeline clips.

Generates preview files that match exactly what will be rendered in the timeline,
including proper trimming and handling of multi-segment merged clips.

For maximum precision:
- Uses accurate seeking (-ss after -i)
- Uses trim filters for frame-accurate cutting
- Re-encodes to ensure clean cuts at exact positions
"""

from __future__ import annotations

import hashlib
import json
import logging
import subprocess
import tempfile
from pathlib import Path
from typing import Optional
import shutil

logger = logging.getLogger(__name__)


class PreviewGenerationError(Exception):
    """Error during preview generation."""
    pass


class ClipPreviewGenerator:
    """
    Generates preview files for timeline clips.

    Handles:
    - Simple clips (single source range)
    - Merged clips with continuous segments
    - Merged clips with discontinuous segments (gaps, loops)
    - Audio-only clips
    """

    def __init__(self, cache_dir: Optional[Path] = None):
        """
        Initialize preview generator.

        Args:
            cache_dir: Directory for caching generated previews.
                      Defaults to ~/.shots_dashboard/preview_cache/
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".shots_dashboard" / "preview_cache"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def generate_preview(
        self,
        clip_data: dict,
        source_path: Path,
        timeout: int = 300
    ) -> Path:
        """
        Generate preview file for a timeline clip.

        Args:
            clip_data: Clip data containing source_start, source_end, and/or segments
            source_path: Path to source media file
            timeout: FFmpeg timeout in seconds

        Returns:
            Path to generated preview file

        Raises:
            FileNotFoundError: If source file doesn't exist
            PreviewGenerationError: If preview generation fails
            TimeoutError: If FFmpeg exceeds timeout
        """
        if not source_path.exists():
            raise FileNotFoundError(f"Source file not found: {source_path}")

        # Check cache first
        cache_key = self._get_cache_key(clip_data, source_path)
        cache_path = self._get_cache_path(cache_key, source_path)

        if cache_path.exists():
            logger.debug(f"Cache hit for clip preview: {cache_key}")
            return cache_path

        logger.info(f"Generating preview for {source_path.name}")

        # Classify clip type
        clip_type = self._classify_clip(clip_data)
        logger.debug(f"Clip type: {clip_type}")

        # Generate appropriate preview
        try:
            if clip_type == "simple":
                self._generate_simple_preview(clip_data, source_path, cache_path, timeout)
            elif clip_type == "continuous":
                self._generate_simple_preview(clip_data, source_path, cache_path, timeout)
            else:  # discontinuous
                self._generate_multi_segment_preview(clip_data, source_path, cache_path, timeout)

            if not cache_path.exists():
                raise PreviewGenerationError("FFmpeg did not create output file")

            logger.info(f"Preview generated: {cache_path}")
            return cache_path

        except subprocess.TimeoutExpired:
            raise TimeoutError(f"Preview generation exceeded {timeout}s timeout")
        except subprocess.CalledProcessError as e:
            raise PreviewGenerationError(f"FFmpeg error: {e.stderr.decode() if e.stderr else str(e)}")

    def _classify_clip(self, clip_data: dict) -> str:
        """
        Classify clip type for optimization.

        Returns:
            "simple": Single source range or no segments
            "continuous": Multiple segments but continuous source
            "discontinuous": Segments with gaps, jumps, or loops
        """
        segments = clip_data.get("segments")

        # No segments means simple clip
        if not segments:
            return "simple"

        # Single segment is simple
        if len(segments) == 1:
            return "simple"

        # Check if all segments are continuous
        # Continuous means end of segment N = start of segment N+1
        for i in range(len(segments) - 1):
            current_end = segments[i].get("source_end")
            next_start = segments[i + 1].get("source_start")

            if current_end is None or next_start is None:
                continue

            # Allow 0.01s tolerance for floating point comparison
            if abs(current_end - next_start) > 0.01:
                return "discontinuous"

        return "continuous"

    def _generate_simple_preview(
        self,
        clip_data: dict,
        source_path: Path,
        output_path: Path,
        timeout: int
    ) -> None:
        """
        Generate preview for simple or continuous clip using accurate seeking.

        For maximum precision, uses -ss after -i (accurate seeking).
        Applies speed changes if present.
        """
        # Determine start, duration, and speed
        if "segments" in clip_data and clip_data["segments"]:
            # Continuous segments: use first start and last end
            segments = clip_data["segments"]
            start = segments[0].get("source_start", 0)
            end = segments[-1].get("source_end")
            if end is not None:
                duration = end - start
            else:
                duration = None
            # Use speed from first segment (should be same for continuous)
            speed = segments[0].get("speed", 1.0)
        else:
            # Simple clip
            start = clip_data.get("source_start", 0)
            end = clip_data.get("source_end")
            if end is not None:
                duration = end - start
            else:
                duration = None
            speed = clip_data.get("speed", 1.0)

        # Check if we need to apply speed changes
        # Consider speeds within 1% of 1.0 as normal (no speed change needed)
        needs_speed_change = speed is not None and abs(speed - 1.0) > 0.01

        # Build FFmpeg command for accurate seeking
        # For maximum precision: input first, then -ss (accurate but slower)
        cmd = ["ffmpeg", "-y"]

        # Input file
        cmd.extend(["-i", str(source_path)])

        # Accurate seeking after input
        cmd.extend(["-ss", str(start)])

        if duration is not None:
            cmd.extend(["-t", str(duration)])

        # Check if source has audio
        has_audio = self._has_audio_stream(source_path)

        if needs_speed_change:
            # Use filter for speed changes
            filter_parts = []

            # Video speed: setpts=PTS/speed
            filter_parts.append(f"[0:v]setpts=PTS/{speed}[v]")

            if has_audio:
                # Audio speed: atempo (limited to 0.5-2.0, chain if needed)
                audio_filter = self._build_atempo_filter(speed, "[0:a]", "[a]")
                filter_parts.append(audio_filter)

            cmd.extend(["-filter_complex", ";".join(filter_parts)])
            cmd.extend(["-map", "[v]"])
            if has_audio:
                cmd.extend(["-map", "[a]"])
        else:
            # No speed change, use regular stream copy
            pass

        # Re-encode for accuracy (don't use -c copy)
        # Use reasonable quality settings
        cmd.extend([
            "-c:v", "libx264",
            "-preset", "fast",
            "-crf", "23"
        ])

        if has_audio:
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "128k"
            ])

        cmd.append(str(output_path))

        logger.debug(f"FFmpeg command: {' '.join(cmd)}")

        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=timeout
        )

    def _generate_multi_segment_preview(
        self,
        clip_data: dict,
        source_path: Path,
        output_path: Path,
        timeout: int
    ) -> None:
        """
        Generate preview for discontinuous multi-segment clip.

        Uses filter_complex for frame-accurate trimming and concatenation.
        Handles gaps, jumps, and loops.
        """
        segments = clip_data.get("segments", [])
        if not segments:
            raise PreviewGenerationError("No segments in clip data")

        # Detect media type
        is_audio_only = self._is_audio_only(source_path)
        has_audio = is_audio_only or self._has_audio_stream(source_path)

        # Build filter_complex for precise segment extraction
        filter_parts = []
        concat_inputs = []

        for i, segment in enumerate(segments):
            start = segment.get("source_start", 0)
            end = segment.get("source_end")
            speed = segment.get("speed", 1.0)

            if end is None:
                raise PreviewGenerationError(f"Segment {i} missing source_end")

            # Check if we need speed changes (consider within 1% of 1.0 as normal)
            needs_speed = speed is not None and abs(speed - 1.0) > 0.01

            if is_audio_only:
                # Audio-only file
                if needs_speed:
                    # Trim, reset PTS, then apply speed
                    atempo_chain = self._build_atempo_chain(speed)
                    filter_parts.append(
                        f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,{atempo_chain}[a{i}]"
                    )
                else:
                    filter_parts.append(
                        f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
                    )
                concat_inputs.append(f"[a{i}]")

            elif has_audio:
                # Video with audio
                if needs_speed:
                    # Video: trim, reset PTS, then apply speed via setpts
                    filter_parts.append(
                        f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,setpts=PTS/{speed}[v{i}]"
                    )
                    # Audio: trim, reset PTS, then apply speed via atempo
                    atempo_chain = self._build_atempo_chain(speed)
                    filter_parts.append(
                        f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS,{atempo_chain}[a{i}]"
                    )
                else:
                    filter_parts.append(
                        f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]"
                    )
                    filter_parts.append(
                        f"[0:a]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
                    )
                # Concat expects interleaved: [v0][a0][v1][a1]...
                concat_inputs.extend([f"[v{i}]", f"[a{i}]"])

            else:
                # Video without audio
                if needs_speed:
                    # Video: trim, reset PTS, then apply speed via setpts
                    filter_parts.append(
                        f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS,setpts=PTS/{speed}[v{i}]"
                    )
                else:
                    filter_parts.append(
                        f"[0:v]trim=start={start}:end={end},setpts=PTS-STARTPTS[v{i}]"
                    )
                concat_inputs.append(f"[v{i}]")

        # Concatenate all segments
        n = len(segments)
        if is_audio_only:
            concat_filter = f"{''.join(concat_inputs)}concat=n={n}:v=0:a=1[outa]"
        elif has_audio:
            concat_filter = f"{''.join(concat_inputs)}concat=n={n}:v=1:a=1[outv][outa]"
        else:
            # Video only, no audio
            concat_filter = f"{''.join(concat_inputs)}concat=n={n}:v=1:a=0[outv]"

        filter_parts.append(concat_filter)
        filter_complex = ";".join(filter_parts)

        # Build FFmpeg command
        cmd = [
            "ffmpeg", "-y",
            "-i", str(source_path),
            "-filter_complex", filter_complex
        ]

        # Map outputs
        if is_audio_only:
            cmd.extend(["-map", "[outa]"])
        elif has_audio:
            cmd.extend(["-map", "[outv]", "-map", "[outa]"])
        else:
            cmd.extend(["-map", "[outv]"])

        # Encoding settings
        if is_audio_only:
            cmd.extend([
                "-c:a", "aac",
                "-b:a", "128k"
            ])
        elif has_audio:
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23",
                "-c:a", "aac",
                "-b:a", "128k"
            ])
        else:
            # Video only, no audio
            cmd.extend([
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "23"
            ])

        cmd.append(str(output_path))

        logger.debug(f"FFmpeg filter_complex: {filter_complex}")
        logger.debug(f"FFmpeg command: {' '.join(cmd)}")

        subprocess.run(
            cmd,
            check=True,
            capture_output=True,
            timeout=timeout
        )

    def _is_audio_only(self, source_path: Path) -> bool:
        """
        Check if source file is audio-only.

        Uses ffprobe to detect streams.
        """
        audio_extensions = {'.wav', '.mp3', '.aac', '.flac', '.ogg', '.m4a', '.aif', '.aiff'}
        if source_path.suffix.lower() in audio_extensions:
            return True

        # Use ffprobe to check for video stream
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-select_streams", "v:0",
                    "-show_entries", "stream=codec_type",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(source_path)
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() != "video"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # If ffprobe fails, guess from extension
            return False

    def _build_atempo_chain(self, speed: float) -> str:
        """
        Build atempo filter chain for audio speed changes.

        FFmpeg's atempo filter is limited to 0.5-2.0 range.
        For values outside this, we chain multiple atempo filters.

        Examples:
            speed=2.0  → "atempo=2.0"
            speed=4.0  → "atempo=2.0,atempo=2.0"
            speed=0.25 → "atempo=0.5,atempo=0.5"
            speed=3.0  → "atempo=2.0,atempo=1.5"
        """
        if speed <= 0:
            raise PreviewGenerationError(f"Invalid speed: {speed} (must be > 0)")

        filters = []
        remaining_speed = speed

        # Handle speeds > 2.0 by chaining 2.0x filters
        while remaining_speed > 2.0:
            filters.append("atempo=2.0")
            remaining_speed /= 2.0

        # Handle speeds < 0.5 by chaining 0.5x filters
        while remaining_speed < 0.5:
            filters.append("atempo=0.5")
            remaining_speed /= 0.5

        # Add the final filter for the remaining speed
        if abs(remaining_speed - 1.0) > 0.01:  # Only add if not 1.0
            # Use clean format for exact values
            if abs(remaining_speed - round(remaining_speed, 1)) < 0.001:
                filters.append(f"atempo={remaining_speed:.1f}")
            else:
                filters.append(f"atempo={remaining_speed:.6f}")

        if not filters:
            # No speed change needed
            return "atempo=1.0"

        return ",".join(filters)

    def _build_atempo_filter(self, speed: float, input_label: str, output_label: str) -> str:
        """
        Build complete atempo filter with input/output labels.

        Args:
            speed: Speed factor (source_duration / timeline_duration)
            input_label: Input stream label (e.g., "[0:a]")
            output_label: Output stream label (e.g., "[a]")

        Returns:
            Complete filter string (e.g., "[0:a]atempo=2.0[a]")
        """
        atempo_chain = self._build_atempo_chain(speed)
        return f"{input_label}{atempo_chain}{output_label}"

    def _has_audio_stream(self, source_path: Path) -> bool:
        """
        Check if source file has an audio stream.

        Returns True if file has at least one audio stream, False otherwise.
        """
        # Audio-only files obviously have audio
        audio_extensions = {'.wav', '.mp3', '.aac', '.flac', '.ogg', '.m4a', '.aif', '.aiff'}
        if source_path.suffix.lower() in audio_extensions:
            return True

        # Use ffprobe to check for audio stream
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "error",
                    "-select_streams", "a:0",
                    "-show_entries", "stream=codec_type",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    str(source_path)
                ],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.stdout.strip() == "audio"
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            # If ffprobe fails, assume video files have audio
            return True

    def _get_cache_key(self, clip_data: dict, source_path: Path) -> str:
        """
        Generate cache key for clip preview.

        Based on source file path, modification time, and segment data.
        """
        try:
            mtime = source_path.stat().st_mtime
        except OSError:
            mtime = 0

        key_data = {
            "source": str(source_path.resolve()),
            "mtime": mtime,
            "segments": clip_data.get("segments"),
            "source_start": clip_data.get("source_start"),
            "source_end": clip_data.get("source_end"),
        }

        key_json = json.dumps(key_data, sort_keys=True)
        return hashlib.sha256(key_json.encode()).hexdigest()

    def _get_cache_path(self, cache_key: str, source_path: Path) -> Path:
        """
        Get cache file path for given cache key.

        Uses same extension as source file.
        """
        # Use source extension, but default to .mp4 for videos
        ext = source_path.suffix.lower()
        audio_extensions = {'.wav', '.mp3', '.aac', '.flac', '.ogg', '.m4a', '.aif', '.aiff'}

        if ext in audio_extensions:
            # Keep audio extension
            cache_ext = ext
        else:
            # Use .mp4 for videos
            cache_ext = '.mp4'

        return self.cache_dir / f"{cache_key}{cache_ext}"

    def cleanup_cache(self, max_size_mb: int = 1000, max_age_days: int = 7) -> None:
        """
        Clean up old or excessive cached previews.

        Args:
            max_size_mb: Maximum cache size in megabytes
            max_age_days: Maximum age of cached files in days
        """
        import time

        total_size = 0
        files_by_mtime = []

        for cache_file in self.cache_dir.iterdir():
            if cache_file.is_file():
                stat = cache_file.stat()
                total_size += stat.st_size
                files_by_mtime.append((stat.st_mtime, stat.st_size, cache_file))

        # Sort by modification time (oldest first)
        files_by_mtime.sort()

        max_size_bytes = max_size_mb * 1024 * 1024
        max_age_seconds = max_age_days * 24 * 60 * 60
        current_time = time.time()

        removed_count = 0
        removed_size = 0

        for mtime, size, cache_file in files_by_mtime:
            should_remove = False

            # Remove if too old
            if current_time - mtime > max_age_seconds:
                should_remove = True
                logger.debug(f"Removing old cache file: {cache_file.name}")

            # Remove oldest if cache too large
            elif total_size > max_size_bytes:
                should_remove = True
                logger.debug(f"Removing cache file to reduce size: {cache_file.name}")

            if should_remove:
                try:
                    cache_file.unlink()
                    total_size -= size
                    removed_count += 1
                    removed_size += size
                except OSError as e:
                    logger.warning(f"Failed to remove cache file {cache_file}: {e}")

        if removed_count > 0:
            logger.info(
                f"Cleaned up {removed_count} cache files "
                f"({removed_size / 1024 / 1024:.1f} MB)"
            )


# Convenience function
def generate_clip_preview(
    clip_data: dict,
    source_path: Path,
    cache_dir: Optional[Path] = None,
    timeout: int = 300
) -> Path:
    """
    Generate preview file for a timeline clip.

    Convenience function that creates a generator and generates preview.

    Args:
        clip_data: Clip data containing source_start, source_end, and/or segments
        source_path: Path to source media file
        cache_dir: Optional cache directory
        timeout: FFmpeg timeout in seconds

    Returns:
        Path to generated preview file
    """
    generator = ClipPreviewGenerator(cache_dir)
    return generator.generate_preview(clip_data, source_path, timeout)
