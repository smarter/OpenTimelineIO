#!/usr/bin/env python3
"""Test segmented video support for VAUTOUR clip."""

import sys
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s: %(message)s'
)

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from media_algebra import build_video_stream, build_audio_stream, AVComposition, Output, mix_audio_streams
from ffmpeg_interpreter import to_ffmpeg_command

# VAUTOUR segments from V10 sequence
# Merged timeline: 44.291667s - 46.054167s (duration: 1.762500s)
VAUTOUR_SEGMENTS = [
    {
        'timeline_start': 44.291667,
        'timeline_duration': 0.393750,
        'source_start': 1.068750,
        'source_duration': 0.393750
    },
    {
        'timeline_start': 44.685417,
        'timeline_duration': 1.068750,
        'source_start': 0.000000,
        'source_duration': 1.068750
    },
    {
        'timeline_start': 45.754167,
        'timeline_duration': 0.300000,
        'source_start': 1.462500,
        'source_duration': 0.300000
    }
]

# Vulture audio overlaps with VAUTOUR
# Timeline: 45.458333s - 47.041667s (duration: 1.583334s)
# Source: 10.875000s - 12.458333s
VULTURE_AUDIO = {
    'timeline_start': 45.458333,
    'timeline_end': 47.041667,
    'source_start': 10.875000,
    'source_duration': 1.583333
}

print("=" * 80)
print("TESTING SEGMENTED VIDEO SUPPORT")
print("=" * 80)
print()

# Test 1: Simple video stream (no segments) for comparison
print("TEST 1: Simple video stream (no segments)")
print("-" * 80)

simple_video = build_video_stream(
    media_path=Path('/home/smarter/Nextcloud4/render/VAUTOUR_REGARDE/VAUTOUR_REGARDE_003/VAUTOUR_REGARDE_003.mp4'),
    source_start=0.0,
    source_duration=1.762500
)

simple_comp = AVComposition(video=simple_video, audio=None)
simple_output = Output(
    composition=simple_comp,
    output_path=Path('/tmp/test_simple.webm'),
    format='webm',
    codec_video='libvpx-vp9',
    codec_audio='libopus'
)

simple_cmd = to_ffmpeg_command(simple_output)
print("FFmpeg command (simple):")
print(' '.join(simple_cmd))
print()

# Test 2: Segmented video stream
print("TEST 2: Segmented video stream (3 segments)")
print("-" * 80)

segmented_video = build_video_stream(
    media_path=Path('/home/smarter/Nextcloud4/render/VAUTOUR_REGARDE/VAUTOUR_REGARDE_003/VAUTOUR_REGARDE_003.mp4'),
    source_start=1.068750,  # First segment source start (used as fallback)
    source_duration=1.762500,  # Total duration (used as fallback)
    segments=VAUTOUR_SEGMENTS
)

segmented_comp = AVComposition(video=segmented_video, audio=None)
segmented_output = Output(
    composition=segmented_comp,
    output_path=Path('/tmp/test_segmented.webm'),
    format='webm',
    codec_video='libvpx-vp9',
    codec_audio='libopus'
)

segmented_cmd = to_ffmpeg_command(segmented_output)
print("FFmpeg command (segmented):")
print(' '.join(segmented_cmd))
print()

# Test 3: Segmented video with audio
print("TEST 3: Segmented video with audio overlap")
print("-" * 80)

# Calculate Vulture audio offset relative to VAUTOUR start
vautour_timeline_start = VAUTOUR_SEGMENTS[0]['timeline_start']
vulture_timeline_start = VULTURE_AUDIO['timeline_start']
audio_offset = vulture_timeline_start - vautour_timeline_start

print(f"VAUTOUR starts at timeline: {vautour_timeline_start:.6f}s")
print(f"Vulture starts at timeline: {vulture_timeline_start:.6f}s")
print(f"Audio offset in output: {audio_offset:.6f}s ({int(audio_offset * 1000)}ms)")
print()

vulture_audio = build_audio_stream(
    media_path=Path('/home/smarter/Nextcloud4/render/VAUTOUR_REGARDE/VAUTOUR_REGARDE_003/Vulture Sound Effects.wav'),
    source_start=VULTURE_AUDIO['source_start'],
    source_duration=VULTURE_AUDIO['source_duration'],
    offset=audio_offset
)

audio_comp = AVComposition(video=segmented_video, audio=vulture_audio)
audio_output = Output(
    composition=audio_comp,
    output_path=Path('/tmp/test_segmented_audio.webm'),
    format='webm',
    codec_video='libvpx-vp9',
    codec_audio='libopus'
)

audio_cmd = to_ffmpeg_command(audio_output)
print("FFmpeg command (segmented video + audio):")
print(' '.join(audio_cmd))
print()

print("=" * 80)
print("EXPECTED BEHAVIOR:")
print("=" * 80)
print("1. Simple video: Extracts 1.76s starting from source 0.0s")
print("2. Segmented video: Extracts 3 segments and concatenates them:")
print("   - Segment 0: 1.069s for 0.394s")
print("   - Segment 1: 0.000s for 1.069s")
print("   - Segment 2: 1.463s for 0.300s")
print("3. With audio: Vulture audio delayed by 1.167s (1167ms)")
print()
print("The segmented video should produce the CORRECT video content,")
print("which will then sync properly with the Vulture audio.")
