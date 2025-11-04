#!/usr/bin/env python
"""
Example usage of the shots dashboard programmatically.

This demonstrates how to use the dashboard components without the web UI.
"""

import sys
from pathlib import Path
from datetime import datetime
import tempfile

# Add OpenTimelineIO to path if needed
# sys.path.insert(0, str(Path(__file__).parent.parent / 'src' / 'py-opentimelineio'))

import opentimelineio as otio

from shots_dashboard.database import Database
from shots_dashboard.models import TrackerState
from shots_dashboard.timeline_tracker import TimelineTracker


def create_sample_timeline(output_path: Path, clip_names: list[str]) -> None:
    """Create a sample OTIO timeline with given clip names."""
    timeline = otio.schema.Timeline(name="sample_timeline")
    track = otio.schema.Track(name="video")

    for clip_name in clip_names:
        clip = otio.schema.Clip(
            name=clip_name,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, 24),
                duration=otio.opentime.RationalTime(100, 24)
            )
        )
        track.append(clip)

    timeline.tracks.append(track)
    otio.adapters.write_to_file(timeline, str(output_path))
    print(f"Created timeline: {output_path}")


def main() -> None:
    """Demonstrate dashboard usage."""
    print("=" * 70)
    print("Shots Dashboard - Example Usage")
    print("=" * 70)

    # Create temporary workspace
    with tempfile.TemporaryDirectory() as tmpdir:
        workspace = Path(tmpdir)
        media_dir = workspace / "media"
        media_dir.mkdir()

        # Create sample media files
        print("\n1. Creating sample media files...")
        media_files = [
            "shot_001_anim_v001.mov",
            "shot_002_anim_v001.mov",
            "shot_003_anim_v001.mov",
            "shot_004_anim_v001.mov",
        ]

        for filename in media_files:
            (media_dir / filename).touch()
            print(f"   Created: {filename}")

        # Initialize database and tracker
        print("\n2. Initializing tracker...")
        db_path = workspace / "dashboard.json"
        db = Database(db_path)
        state = TrackerState()
        tracker = TimelineTracker(state)

        # Scan directory
        print(f"\n3. Scanning directory: {media_dir}")
        transitions = tracker.scan_directory(media_dir)
        print(f"   Found {len(transitions)} files")
        for t in transitions:
            print(f"   - {t}")

        # Save state
        db.save(tracker.state)

        # Show stats
        stats = tracker.get_stats()
        print(f"\n4. Initial statistics:")
        print(f"   Total files: {stats['total']}")
        print(f"   New: {stats['new']}")
        print(f"   In use: {stats['in_use']}")
        print(f"   Removed: {stats['removed']}")

        # Create first timeline with some shots
        print("\n5. Creating first timeline (v1)...")
        timeline_v1 = workspace / "timeline_v1.otio"
        create_sample_timeline(
            timeline_v1,
            ["shot_001_anim_v001.mov", "shot_002_anim_v001.mov"]
        )

        # Update from timeline
        print("\n6. Updating from timeline v1...")
        transitions = tracker.update_from_timeline(timeline_v1)
        print(f"   {len(transitions)} state changes:")
        for t in transitions:
            print(f"   - {t}")

        db.save(tracker.state)

        # Show updated stats
        stats = tracker.get_stats()
        print(f"\n7. After timeline v1:")
        print(f"   New: {stats['new']}")
        print(f"   In use: {stats['in_use']}")
        print(f"   Removed: {stats['removed']}")

        # Show files in each state
        print("\n   Files in use:")
        for f in tracker.state.in_use_files:
            print(f"   - {f.path.name}")

        print("\n   Files not yet used:")
        for f in tracker.state.new_files:
            print(f"   - {f.path.name}")

        # Create updated timeline (removed shot_001, added shot_003)
        print("\n8. Creating updated timeline (v2)...")
        timeline_v2 = workspace / "timeline_v2.otio"
        create_sample_timeline(
            timeline_v2,
            ["shot_002_anim_v001.mov", "shot_003_anim_v001.mov"]
        )

        # Update from new timeline
        print("\n9. Updating from timeline v2...")
        transitions = tracker.update_from_timeline(timeline_v2)
        print(f"   {len(transitions)} state changes:")
        for t in transitions:
            print(f"   - {t}")

        db.save(tracker.state)

        # Final stats
        stats = tracker.get_stats()
        print(f"\n10. Final state after timeline v2:")
        print(f"    New: {stats['new']}")
        print(f"    In use: {stats['in_use']}")
        print(f"    Removed: {stats['removed']}")

        print("\n    Files in use:")
        for f in tracker.state.in_use_files:
            print(f"    - {f.path.name}")

        print("\n    Files removed from timeline:")
        for f in tracker.state.removed_files:
            print(f"    - {f.path.name}")

        print("\n    Files not yet used:")
        for f in tracker.state.new_files:
            print(f"    - {f.path.name}")

        # Demonstrate persistence
        print("\n11. Demonstrating persistence...")
        print(f"    Database saved to: {db_path}")

        # Create new tracker instance with same database
        new_db = Database(db_path)
        new_state = new_db.load()
        new_tracker = TimelineTracker(new_state)

        print(f"    Loaded {len(new_state.files)} files from database")
        print(f"    Last scan: {new_state.last_scan}")
        print(f"    Timeline: {new_state.timeline_path}")

        print("\n" + "=" * 70)
        print("Example completed successfully!")
        print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
