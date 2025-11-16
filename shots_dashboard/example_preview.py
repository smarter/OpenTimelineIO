"""
Example usage of the media algebra for generating previews.

This demonstrates how to use the composable algebra to build and execute
video previews with timeline audio.
"""

from pathlib import Path
from preview_builder import TimelineClip, build_clip_preview_with_audio
from ffmpeg_interpreter import to_ffmpeg_command, validate_output
import subprocess


def example_preview_with_timeline_audio():
    """
    Example: Generate a preview for a video clip with audio from overlapping tracks.
    """
    # Define the video clip we want to preview
    video_clip = TimelineClip(
        name='scene_01.mp4',
        source_path=Path('/path/to/video/scene_01.mp4'),
        timeline_start=0.0,
        timeline_duration=10.0,
        source_start=5.0,
        source_duration=10.0,
        track_kind='Video',
        track_index=0
    )

    # Define all clips in the timeline (including audio tracks)
    all_clips = [
        video_clip,
        # Audio track 1: Dialog
        TimelineClip(
            name='dialog_track.wav',
            source_path=Path('/path/to/audio/dialog_track.wav'),
            timeline_start=0.0,
            timeline_duration=15.0,
            source_start=0.0,
            source_duration=15.0,
            track_kind='Audio',
            track_index=0
        ),
        # Audio track 2: Music (partially overlapping)
        TimelineClip(
            name='music.mp3',
            source_path=Path('/path/to/audio/music.mp3'),
            timeline_start=5.0,
            timeline_duration=20.0,
            source_start=10.0,
            source_duration=20.0,
            track_kind='Audio',
            track_index=1
        ),
    ]

    # Build the composition using our algebra
    output = build_clip_preview_with_audio(
        video_clip=video_clip,
        all_clips=all_clips,
        output_path=Path('/tmp/preview.mp4')
    )

    # Validate the composition
    errors = validate_output(output)
    if errors:
        print("Validation errors:")
        for error in errors:
            print(f"  - {error}")
        return

    # Convert to ffmpeg command
    cmd = to_ffmpeg_command(output)

    print("Generated ffmpeg command:")
    print(" ".join(cmd))

    # Execute (commented out for safety)
    # result = subprocess.run(cmd, capture_output=True, text=True)
    # if result.returncode != 0:
    #     print(f"Error: {result.stderr}")
    # else:
    #     print(f"Success! Preview saved to {output.output_path}")


def explain_composition():
    """
    Explain what happens in the composition.
    """
    print("""
    How the algebra works:

    1. ALGEBRA LAYER (Immutable Data Structures):
       - TimeRange: Represents time intervals
       - MediaFile: References to source files
       - VideoStream: Video extraction specification
       - AudioStream: Audio extraction with offset
       - AudioMix: Combines multiple audio streams
       - AVComposition: Video + Audio combination
       - Output: Final specification with encoding params

    2. BUILDER LAYER (Timeline → Algebra):
       - Takes timeline clip data
       - Calculates overlaps using time range algebra
       - Maps timeline coordinates to source coordinates
       - Builds AudioStream objects with correct offsets
       - Composes into AVComposition

    3. INTERPRETER LAYER (Algebra → FFmpeg):
       - Converts algebra to ffmpeg commands
       - Handles:
         * Input seeking and duration
         * Filter graphs for audio mixing
         * Audio delay/offset using adelay filter
         * Stream mapping
         * Encoding options

    Benefits:
    - Composable: Operations can be combined
    - Testable: Each layer can be tested independently
    - Optimizable: Can analyze and optimize before execution
    - Backend-agnostic: Could target different tools
    - Type-safe: Clear data structures with validation
    - Immutable: No hidden state changes
    """)


if __name__ == '__main__':
    explain_composition()
    print("\n" + "="*70 + "\n")
    example_preview_with_timeline_audio()
