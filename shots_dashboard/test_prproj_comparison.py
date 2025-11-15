#!/usr/bin/env python3
"""
Compare .prproj adapter output with FCP XML reference.

Tests the Premiere Pro adapter by comparing its output to the reference
FCP XML export to verify accuracy of parsing.
"""

import sys
from pathlib import Path
from typing import List, Dict, Any
import opentimelineio as otio

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

import otio_prproj_adapter


def get_timeline_stats(timeline: otio.schema.Timeline) -> Dict[str, Any]:
    """Extract statistics from a timeline for comparison."""
    stats = {
        'name': timeline.name,
        'num_tracks': len(timeline.tracks),
        'tracks': [],
        'total_clips': 0,
    }

    for track in timeline.tracks:
        track_info = {
            'name': track.name,
            'kind': track.kind.name if hasattr(track.kind, 'name') else str(track.kind),
            'num_clips': len(track),
            'clips': []
        }

        for clip in track:
            if isinstance(clip, otio.schema.Clip):
                clip_info = {
                    'name': clip.name,
                    'duration': None,
                    'has_media_ref': clip.media_reference is not None,
                    'media_path': None
                }

                if clip.source_range:
                    clip_info['duration'] = float(clip.source_range.duration.value) / float(clip.source_range.duration.rate)

                if clip.media_reference and hasattr(clip.media_reference, 'target_url'):
                    clip_info['media_path'] = clip.media_reference.target_url

                track_info['clips'].append(clip_info)

        stats['total_clips'] += track_info['num_clips']
        stats['tracks'].append(track_info)

    return stats


def print_timeline_comparison(prproj_stats: Dict, xml_stats: Dict):
    """Print detailed comparison of two timelines."""
    print(f"\n{'='*80}")
    print(f"TIMELINE COMPARISON")
    print(f"{'='*80}")

    print(f"\n📊 Overall Statistics:")
    print(f"  .prproj: {prproj_stats['name']}")
    print(f"           {prproj_stats['num_tracks']} tracks, {prproj_stats['total_clips']} total clips")
    print(f"  FCP XML: {xml_stats['name']}")
    print(f"           {xml_stats['num_tracks']} tracks, {xml_stats['total_clips']} total clips")

    # Compare track counts
    if prproj_stats['num_tracks'] == xml_stats['num_tracks']:
        print(f"\n✓ Track count matches: {prproj_stats['num_tracks']}")
    else:
        print(f"\n✗ Track count MISMATCH:")
        print(f"  .prproj: {prproj_stats['num_tracks']}")
        print(f"  FCP XML: {xml_stats['num_tracks']}")

    # Compare total clip counts
    if prproj_stats['total_clips'] == xml_stats['total_clips']:
        print(f"✓ Total clip count matches: {prproj_stats['total_clips']}")
    else:
        print(f"✗ Total clip count MISMATCH:")
        print(f"  .prproj: {prproj_stats['total_clips']}")
        print(f"  FCP XML: {xml_stats['total_clips']}")

    # Compare tracks in detail
    print(f"\n📋 Track-by-Track Comparison:")
    max_tracks = max(len(prproj_stats['tracks']), len(xml_stats['tracks']))

    for i in range(max_tracks):
        prproj_track = prproj_stats['tracks'][i] if i < len(prproj_stats['tracks']) else None
        xml_track = xml_stats['tracks'][i] if i < len(xml_stats['tracks']) else None

        print(f"\n  Track {i+1}:")

        if prproj_track and xml_track:
            # Both exist
            print(f"    Kind: {prproj_track['kind']} (.prproj) vs {xml_track['kind']} (XML)")

            if prproj_track['num_clips'] == xml_track['num_clips']:
                print(f"    ✓ Clip count: {prproj_track['num_clips']}")
            else:
                print(f"    ✗ Clip count MISMATCH: {prproj_track['num_clips']} (.prproj) vs {xml_track['num_clips']} (XML)")

            # Compare clip names (first 5)
            print(f"    Clips (showing first 5):")
            max_clips_to_show = 5
            max_prproj_clips = min(max_clips_to_show, prproj_track['num_clips'])
            max_xml_clips = min(max_clips_to_show, xml_track['num_clips'])
            max_clips = max(max_prproj_clips, max_xml_clips)

            for j in range(max_clips):
                prproj_clip = prproj_track['clips'][j] if j < len(prproj_track['clips']) else None
                xml_clip = xml_track['clips'][j] if j < len(xml_track['clips']) else None

                if prproj_clip and xml_clip:
                    match = "✓" if prproj_clip['name'] == xml_clip['name'] else "✗"
                    print(f"      {match} [{j+1}] .prproj: {prproj_clip['name']}")
                    if prproj_clip['name'] != xml_clip['name']:
                        print(f"           XML:    {xml_clip['name']}")
                elif prproj_clip:
                    print(f"      ✗ [{j+1}] .prproj: {prproj_clip['name']}")
                    print(f"           XML:    (no clip)")
                elif xml_clip:
                    print(f"      ✗ [{j+1}] .prproj: (no clip)")
                    print(f"           XML:    {xml_clip['name']}")

            if prproj_track['num_clips'] > 5:
                print(f"      ... and {prproj_track['num_clips'] - 5} more clips")

        elif prproj_track:
            print(f"    ✗ Only in .prproj: {prproj_track['kind']} track with {prproj_track['num_clips']} clips")
        elif xml_track:
            print(f"    ✗ Only in XML: {xml_track['kind']} track with {xml_track['num_clips']} clips")


def test_comparison():
    """Compare .prproj parsing with FCP XML reference."""
    prproj_path = Path.home() / "prox/Montage_48h_cannes.prproj"
    xml_path = Path.home() / "prox/Montage_48h_cannes_V2.xml"

    if not prproj_path.exists():
        print(f"✗ Error: .prproj file not found: {prproj_path}")
        return False

    if not xml_path.exists():
        print(f"✗ Error: XML file not found: {xml_path}")
        return False

    print(f"Reading files...")
    print(f"  .prproj: {prproj_path}")
    print(f"  FCP XML: {xml_path}")

    try:
        # Read .prproj file
        print(f"\nParsing .prproj...")
        prproj_result = otio_prproj_adapter.read_from_file(str(prproj_path))

        # Find V2 sequence
        prproj_timeline = None
        if isinstance(prproj_result, otio.schema.Timeline):
            if 'V2' in prproj_result.name:
                prproj_timeline = prproj_result
        else:
            # SerializableCollection - find V2
            for seq in prproj_result:
                if 'V2' in seq.name:
                    prproj_timeline = seq
                    break

        if not prproj_timeline:
            print("✗ Error: Could not find V2 sequence in .prproj")
            return False

        print(f"  Found sequence: {prproj_timeline.name}")

        # Read FCP XML file
        print(f"\nParsing FCP XML...")
        xml_timeline = otio.adapters.read_from_file(str(xml_path))

        if not isinstance(xml_timeline, otio.schema.Timeline):
            print(f"✗ Error: XML did not parse to Timeline (got {type(xml_timeline).__name__})")
            return False

        print(f"  Found timeline: {xml_timeline.name}")

        # Extract statistics
        print(f"\nExtracting statistics...")
        prproj_stats = get_timeline_stats(prproj_timeline)
        xml_stats = get_timeline_stats(xml_timeline)

        # Print comparison
        print_timeline_comparison(prproj_stats, xml_stats)

        # Calculate match percentage
        total_checks = 2  # track count, clip count
        matches = 0

        if prproj_stats['num_tracks'] == xml_stats['num_tracks']:
            matches += 1
        if prproj_stats['total_clips'] == xml_stats['total_clips']:
            matches += 1

        match_pct = (matches / total_checks) * 100

        print(f"\n{'='*80}")
        print(f"RESULT: {matches}/{total_checks} major criteria match ({match_pct:.0f}%)")
        print(f"{'='*80}\n")

        return matches == total_checks

    except Exception as e:
        print(f"\n✗ Error during comparison: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_comparison()
    sys.exit(0 if success else 1)
