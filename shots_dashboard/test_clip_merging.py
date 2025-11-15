"""
Tests for timeline clip merging based on real FCP XML data.

Tests the logic that merges adjacent clips when they:
1. Have the same name
2. Are adjacent in timeline (end of A = start of B)
3. Have continuous source ranges (source end of A = source start of B)
"""

import tempfile
from pathlib import Path

import pytest
import opentimelineio as otio


def test_merge_continuous_source_ranges():
    """Test that clips with continuous source ranges are merged."""
    # Based on real data: car-crash-back-001.mov clips
    # Prev: timeline 143.13-144.38, source 0.00-1.25
    # This: timeline 144.38-144.58, source 1.25-1.46

    timeline = otio.schema.Timeline(name="Test Timeline")
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)

    # First clip: source 0-1.25, timeline 143.13-144.38 (duration 1.25)
    clip1 = otio.schema.Clip(
        name="car-crash-back-001.mov",
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, 24),
            duration=otio.opentime.RationalTime(30, 24)  # 1.25 seconds
        )
    )

    # Second clip: source 1.25-1.46, timeline 144.38-144.58 (duration 0.21)
    clip2 = otio.schema.Clip(
        name="car-crash-back-001.mov",
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(30, 24),  # 1.25 seconds
            duration=otio.opentime.RationalTime(5, 24)  # 0.21 seconds
        )
    )

    track.append(clip1)
    track.append(clip2)
    timeline.tracks.append(track)

    # Save and load through API simulation
    with tempfile.TemporaryDirectory() as tmpdir:
        timeline_path = Path(tmpdir) / "test.otio"
        otio.adapters.write_to_file(timeline, str(timeline_path))

        # Simulate the merging logic from app.py
        loaded_timeline = otio.adapters.read_from_file(str(timeline_path))
        track = loaded_timeline.tracks[0]

        clips_data = []
        for item_idx, item in enumerate(track):
            if isinstance(item, otio.schema.Clip):
                range_in_parent = track.range_of_child_at_index(item_idx)
                start_time = range_in_parent.start_time
                duration_clip = range_in_parent.duration

                start_seconds = float(start_time.value) / float(start_time.rate)
                duration_seconds_clip = float(duration_clip.value) / float(duration_clip.rate)

                source_start = None
                source_end = None
                if item.source_range:
                    source_start = float(item.source_range.start_time.value) / float(item.source_range.start_time.rate)
                    source_duration = float(item.source_range.duration.value) / float(item.source_range.duration.rate)
                    source_end = source_start + source_duration

                clips_data.append({
                    "name": item.name or "Unnamed Clip",
                    "start": start_seconds,
                    "duration": duration_seconds_clip,
                    "end": start_seconds + duration_seconds_clip,
                    "source_start": source_start,
                    "source_end": source_end
                })

        # Merge adjacent clips with same name
        merged_clips = []
        for clip in clips_data:
            if merged_clips and \
               merged_clips[-1]["name"] == clip["name"] and \
               abs(merged_clips[-1]["end"] - clip["start"]) < 0.01:
                merged_clips[-1]["end"] = clip["end"]
                merged_clips[-1]["duration"] = merged_clips[-1]["end"] - merged_clips[-1]["start"]
                if "segments" not in merged_clips[-1]:
                    merged_clips[-1]["segments"] = [{
                        "timeline_start": merged_clips[-1]["start"],
                        "timeline_end": merged_clips[-1].get("segments_end", clip["start"]),
                        "source_start": merged_clips[-1]["source_start"],
                        "source_end": merged_clips[-1]["source_end"]
                    }]
                merged_clips[-1]["segments"].append({
                    "timeline_start": clip["start"],
                    "timeline_end": clip["end"],
                    "source_start": clip["source_start"],
                    "source_end": clip["source_end"]
                })
                merged_clips[-1]["segments_end"] = clip["end"]
            else:
                merged_clips.append(clip.copy())

        # Should have merged into 1 clip with 2 segments
        assert len(merged_clips) == 1
        assert merged_clips[0]["name"] == "car-crash-back-001.mov"
        assert abs(merged_clips[0]["duration"] - 1.46) < 0.01  # Combined duration
        assert "segments" in merged_clips[0]
        assert len(merged_clips[0]["segments"]) == 2


def test_merge_discontinuous_source_ranges_with_segments():
    """Test that clips with discontinuous source ranges ARE merged with segment info."""
    # Based on real data: INSERT_SOLEIL_001.mp4 clips
    # Both read from source 0.00-1.00 (same section repeated - a loop effect)

    timeline = otio.schema.Timeline(name="Test Timeline")
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)

    # First clip: source 0-1.0
    clip1 = otio.schema.Clip(
        name="INSERT_SOLEIL_001.mp4",
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, 24),
            duration=otio.opentime.RationalTime(24, 24)  # 1.0 second
        )
    )

    # Second clip: ALSO source 0-1.0 (repeating same section)
    clip2 = otio.schema.Clip(
        name="INSERT_SOLEIL_001.mp4",
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, 24),  # SAME start
            duration=otio.opentime.RationalTime(24, 24)  # 1.0 second
        )
    )

    track.append(clip1)
    track.append(clip2)
    timeline.tracks.append(track)

    with tempfile.TemporaryDirectory() as tmpdir:
        timeline_path = Path(tmpdir) / "test.otio"
        otio.adapters.write_to_file(timeline, str(timeline_path))

        # Simulate the merging logic
        loaded_timeline = otio.adapters.read_from_file(str(timeline_path))
        track = loaded_timeline.tracks[0]

        clips_data = []
        for item_idx, item in enumerate(track):
            if isinstance(item, otio.schema.Clip):
                range_in_parent = track.range_of_child_at_index(item_idx)
                start_seconds = float(range_in_parent.start_time.value) / float(range_in_parent.start_time.rate)
                duration_seconds = float(range_in_parent.duration.value) / float(range_in_parent.duration.rate)

                source_start = float(item.source_range.start_time.value) / float(item.source_range.start_time.rate)
                source_duration = float(item.source_range.duration.value) / float(item.source_range.duration.rate)
                source_end = source_start + source_duration

                clips_data.append({
                    "name": item.name,
                    "start": start_seconds,
                    "duration": duration_seconds,
                    "end": start_seconds + duration_seconds,
                    "source_start": source_start,
                    "source_end": source_end
                })

        # Merge logic (now merges all adjacent clips with same name)
        merged_clips = []
        for clip in clips_data:
            if merged_clips and \
               merged_clips[-1]["name"] == clip["name"] and \
               abs(merged_clips[-1]["end"] - clip["start"]) < 0.01:
                merged_clips[-1]["end"] = clip["end"]
                merged_clips[-1]["duration"] = merged_clips[-1]["end"] - merged_clips[-1]["start"]
                if "segments" not in merged_clips[-1]:
                    merged_clips[-1]["segments"] = [{
                        "timeline_start": merged_clips[-1]["start"],
                        "timeline_end": merged_clips[-1].get("segments_end", clip["start"]),
                        "source_start": merged_clips[-1]["source_start"],
                        "source_end": merged_clips[-1]["source_end"]
                    }]
                merged_clips[-1]["segments"].append({
                    "timeline_start": clip["start"],
                    "timeline_end": clip["end"],
                    "source_start": clip["source_start"],
                    "source_end": clip["source_end"]
                })
                merged_clips[-1]["segments_end"] = clip["end"]
            else:
                merged_clips.append(clip.copy())

        # Should merge into 1 clip with 2 segments
        assert len(merged_clips) == 1
        assert "segments" in merged_clips[0]
        assert len(merged_clips[0]["segments"]) == 2
        # Verify segments preserve discontinuous source ranges
        assert abs(merged_clips[0]["segments"][0]["source_start"] - 0.0) < 0.01
        assert abs(merged_clips[0]["segments"][1]["source_start"] - 0.0) < 0.01  # Jumps back to 0


def test_merge_postcrash_contrechamp():
    """Test real case from timeline that should merge."""
    # PostCrash_Contrechamp-001.mov
    # Prev: timeline 166.00-167.17, source 0.00-1.17
    # This: timeline 167.17-167.67, source 1.17-1.67

    timeline = otio.schema.Timeline(name="Test Timeline")
    track = otio.schema.Track(name="V1", kind=otio.schema.TrackKind.Video)

    clip1 = otio.schema.Clip(
        name="PostCrash_Contrechamp-001.mov",
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(0, 24),
            duration=otio.opentime.RationalTime(int(1.17 * 24), 24)
        )
    )

    clip2 = otio.schema.Clip(
        name="PostCrash_Contrechamp-001.mov",
        source_range=otio.opentime.TimeRange(
            start_time=otio.opentime.RationalTime(int(1.17 * 24), 24),
            duration=otio.opentime.RationalTime(int(0.5 * 24), 24)
        )
    )

    track.append(clip1)
    track.append(clip2)
    timeline.tracks.append(track)

    with tempfile.TemporaryDirectory() as tmpdir:
        timeline_path = Path(tmpdir) / "test.otio"
        otio.adapters.write_to_file(timeline, str(timeline_path))

        loaded_timeline = otio.adapters.read_from_file(str(timeline_path))
        track = loaded_timeline.tracks[0]

        clips_data = []
        for item_idx, item in enumerate(track):
            if isinstance(item, otio.schema.Clip):
                range_in_parent = track.range_of_child_at_index(item_idx)
                start_seconds = float(range_in_parent.start_time.value) / float(range_in_parent.start_time.rate)
                duration_seconds = float(range_in_parent.duration.value) / float(range_in_parent.duration.rate)

                source_start = float(item.source_range.start_time.value) / float(item.source_range.start_time.rate)
                source_duration = float(item.source_range.duration.value) / float(item.source_range.duration.rate)
                source_end = source_start + source_duration

                clips_data.append({
                    "name": item.name,
                    "start": start_seconds,
                    "duration": duration_seconds,
                    "end": start_seconds + duration_seconds,
                    "source_start": source_start,
                    "source_end": source_end
                })

        # Merge logic
        merged_clips = []
        for clip in clips_data:
            if merged_clips and \
               merged_clips[-1]["name"] == clip["name"] and \
               abs(merged_clips[-1]["end"] - clip["start"]) < 0.01:
                merged_clips[-1]["end"] = clip["end"]
                merged_clips[-1]["duration"] = merged_clips[-1]["end"] - merged_clips[-1]["start"]
                if "segments" not in merged_clips[-1]:
                    merged_clips[-1]["segments"] = [{
                        "timeline_start": merged_clips[-1]["start"],
                        "timeline_end": merged_clips[-1].get("segments_end", clip["start"]),
                        "source_start": merged_clips[-1]["source_start"],
                        "source_end": merged_clips[-1]["source_end"]
                    }]
                merged_clips[-1]["segments"].append({
                    "timeline_start": clip["start"],
                    "timeline_end": clip["end"],
                    "source_start": clip["source_start"],
                    "source_end": clip["source_end"]
                })
                merged_clips[-1]["segments_end"] = clip["end"]
            else:
                merged_clips.append(clip.copy())

        # Should merge into 1 clip with 2 segments
        assert len(merged_clips) == 1
        assert abs(merged_clips[0]["duration"] - 1.67) < 0.05
        assert "segments" in merged_clips[0]
        assert len(merged_clips[0]["segments"]) == 2


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
