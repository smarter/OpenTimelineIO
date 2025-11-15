#!/usr/bin/env python3
"""
Test the Premiere Pro project adapter.
"""

import sys
import logging
from pathlib import Path

# Enable debug logging
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s: %(message)s')

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

import otio_prproj_adapter

def test_read_prproj():
    """Test reading a .prproj file."""
    prproj_path = Path.home() / "prox/Montage_48h_cannes.prproj"

    if not prproj_path.exists():
        print(f"Error: Test file not found: {prproj_path}")
        return False

    print(f"Reading {prproj_path}...")

    try:
        result = otio_prproj_adapter.read_from_file(str(prproj_path))
        print(f"\n✓ Successfully parsed {prproj_path}")
        print(f"  Type: {type(result).__name__}")

        if hasattr(result, 'name'):
            print(f"  Name: {result.name}")

        print(f"  Has tracks: {hasattr(result, 'tracks')}")
        print(f"  Has children: {hasattr(result, 'children')}")
        if hasattr(result, 'children'):
            print(f"  Children type: {type(result.children)}")
            print(f"  Children len: {len(result.children) if result.children else 0}")

        if hasattr(result, 'tracks'):
            print(f"  Tracks: {len(result.tracks)}")
            for i, track in enumerate(result.tracks):
                print(f"    Track {i+1}: {track.name} ({track.kind.name})")
                print(f"      Clips: {len(track)}")
                for j, clip in enumerate(track):
                    if j < 3:  # Show first 3 clips
                        print(f"        - {clip.name}")
                if len(track) > 3:
                    print(f"        ... and {len(track) - 3} more clips")

        else:
            # SerializableCollection is iterable
            sequences = list(result)
            print(f"  Sequences: {len(sequences)}")
            for i, seq in enumerate(sequences):
                print(f"\n  Sequence {i+1}: {seq.name}")
                if hasattr(seq, 'tracks'):
                    print(f"    Tracks: {len(seq.tracks)}")
                    for j, track in enumerate(seq.tracks):
                        kind_name = track.kind.name if hasattr(track.kind, 'name') else str(track.kind)
                        print(f"      Track {j+1}: {track.name} ({kind_name}) - {len(track)} clips")
                        for k, clip in enumerate(track):
                            if k < 3:
                                print(f"        - {clip.name}")
                        if len(track) > 3:
                            print(f"        ... and {len(track) - 3} more clips")

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = test_read_prproj()
    sys.exit(0 if success else 1)
