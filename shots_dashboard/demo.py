"""
Demo mode for shots dashboard.

Creates sample data and runs through scenarios automatically to showcase features.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

import opentimelineio as otio

from shots_dashboard.database import Database
from shots_dashboard.models import TrackerState
from shots_dashboard.timeline_tracker import TimelineTracker


@dataclass
class DemoScenario:
    """Represents a demo scenario."""
    name: str
    description: str
    action: Callable[[], None]
    delay: float = 2.0


class DemoDataGenerator:
    """Generates demo data for showcasing the dashboard."""

    def __init__(self, demo_dir: Path):
        self.demo_dir = demo_dir
        self.media_dir = demo_dir / "media"
        self.timelines_dir = demo_dir / "timelines"

        # Create directories
        self.media_dir.mkdir(parents=True, exist_ok=True)
        self.timelines_dir.mkdir(parents=True, exist_ok=True)

    def create_media_files(self) -> list[Path]:
        """Create sample media files for demo."""
        print("Creating demo media files...")

        files = [
            # Animation files
            "shot_010_anim_v001.mov",
            "shot_020_anim_v001.mov",
            "shot_030_anim_v001.mov",
            "shot_040_anim_v001.mov",
            "shot_050_anim_v001.mov",
            # Compositing files
            "shot_010_comp_v001.mov",
            "shot_020_comp_v001.mov",
            # Background plates
            "bg_forest_001.mov",
            "bg_city_001.mov",
            # Audio files
            "dialogue_take_01.wav",
            "dialogue_take_02.wav",
        ]

        created_files = []
        for filename in files:
            file_path = self.media_dir / filename
            file_path.touch()
            created_files.append(file_path)
            print(f"  Created: {filename}")

        return created_files

    def create_timeline(
        self,
        name: str,
        clip_names: list[str]
    ) -> Path:
        """Create a timeline with specified clips."""
        timeline = otio.schema.Timeline(name=name)
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

        timeline_path = self.timelines_dir / f"{name}.otio"
        otio.adapters.write_to_file(timeline, str(timeline_path))
        return timeline_path

    def create_demo_timelines(self) -> dict[str, Path]:
        """Create all demo timelines."""
        print("\nCreating demo timelines...")

        timelines = {}

        # Initial cut - basic shots
        timelines['initial_cut'] = self.create_timeline(
            "initial_cut",
            [
                "shot_010_anim_v001.mov",
                "shot_020_anim_v001.mov",
                "bg_forest_001.mov",
            ]
        )
        print("  Created: initial_cut.otio")

        # Revised cut - added more shots
        timelines['revised_cut'] = self.create_timeline(
            "revised_cut",
            [
                "shot_010_anim_v001.mov",
                "shot_020_anim_v001.mov",
                "shot_030_anim_v001.mov",
                "bg_forest_001.mov",
                "shot_040_anim_v001.mov",
            ]
        )
        print("  Created: revised_cut.otio")

        # Final cut - replaced some shots, removed others
        timelines['final_cut'] = self.create_timeline(
            "final_cut",
            [
                "shot_010_comp_v001.mov",  # Upgraded to comp
                "shot_020_comp_v001.mov",  # Upgraded to comp
                "shot_030_anim_v001.mov",
                "bg_city_001.mov",  # Changed background
                "shot_050_anim_v001.mov",  # New shot
            ]
        )
        print("  Created: final_cut.otio")

        return timelines


class DemoRunner:
    """Runs demo scenarios for the dashboard."""

    def __init__(self, demo_dir: Path, db_path: Path):
        self.demo_dir = demo_dir
        self.db = Database(db_path)
        self.generator = DemoDataGenerator(demo_dir)

    def run_scenario_1_initial_scan(self) -> None:
        """Scenario 1: Initial directory scan."""
        print("\n" + "=" * 70)
        print("SCENARIO 1: Initial Directory Scan")
        print("=" * 70)
        print("\nYou've just received rendered animation files from your team.")
        print("Let's scan the directory to see what we have...\n")

        files = self.generator.create_media_files()

        state = TrackerState()
        tracker = TimelineTracker(state)
        transitions = tracker.scan_directory(self.generator.media_dir)

        self.db.save(tracker.state)

        print(f"\n✅ Found {len(transitions)} media files")
        print(f"   All files are in 'NEW' state (not yet used in timeline)")

        self._print_stats(tracker)

    def run_scenario_2_first_timeline(self) -> None:
        """Scenario 2: First timeline update."""
        print("\n" + "=" * 70)
        print("SCENARIO 2: Editorial Sends First Cut")
        print("=" * 70)
        print("\nEditorial has sent you the initial cut of the sequence.")
        print("Let's see which shots made it into the timeline...\n")

        timelines = self.generator.create_demo_timelines()

        state = self.db.load()
        tracker = TimelineTracker(state)
        transitions = tracker.update_from_timeline(timelines['initial_cut'])

        self.db.save(tracker.state)

        print(f"\n✅ Updated from timeline: initial_cut.otio")
        print(f"   {len(transitions)} files changed state:")
        for t in transitions:
            print(f"   - {t.path.name}: {t.old_state} → {t.new_state}")

        self._print_stats(tracker)
        print("\n💡 Tip: Focus your work on files that are IN_USE in the timeline!")

    def run_scenario_3_revised_cut(self) -> None:
        """Scenario 3: Revised cut with more shots."""
        print("\n" + "=" * 70)
        print("SCENARIO 3: Editorial Adds More Shots")
        print("=" * 70)
        print("\nEditorial has revised the cut and added more shots.")
        print("Let's see what changed...\n")

        timelines = self.generator.create_demo_timelines()

        state = self.db.load()
        tracker = TimelineTracker(state)
        transitions = tracker.update_from_timeline(timelines['revised_cut'])

        self.db.save(tracker.state)

        print(f"\n✅ Updated from timeline: revised_cut.otio")
        print(f"   {len(transitions)} files changed state:")
        for t in transitions:
            print(f"   - {t.path.name}: {t.old_state} → {t.new_state}")

        self._print_stats(tracker)
        print("\n💡 Tip: Start working on the newly added shots!")

    def run_scenario_4_final_cut(self) -> None:
        """Scenario 4: Final cut with replacements and removals."""
        print("\n" + "=" * 70)
        print("SCENARIO 4: Final Cut with Changes")
        print("=" * 70)
        print("\nEditorial has sent the final cut.")
        print("Some shots were upgraded, some removed, some changed...")
        print("Let's see the final state...\n")

        timelines = self.generator.create_demo_timelines()

        state = self.db.load()
        tracker = TimelineTracker(state)
        transitions = tracker.update_from_timeline(timelines['final_cut'])

        self.db.save(tracker.state)

        print(f"\n✅ Updated from timeline: final_cut.otio")
        print(f"   {len(transitions)} files changed state:")
        for t in transitions:
            print(f"   - {t.path.name}: {t.old_state} → {t.new_state}")

        self._print_stats(tracker)

        print("\n" + "=" * 70)
        print("FINAL STATE SUMMARY")
        print("=" * 70)
        print(f"\n📋 NOT YET USED ({len(tracker.state.new_files)} files):")
        for f in tracker.state.new_files:
            print(f"   - {f.path.name}")

        print(f"\n✅ IN USE ({len(tracker.state.in_use_files)} files):")
        for f in tracker.state.in_use_files:
            print(f"   - {f.path.name}")

        print(f"\n🗑️  REMOVED ({len(tracker.state.removed_files)} files):")
        for f in tracker.state.removed_files:
            print(f"   - {f.path.name}")

        print("\n💡 Production insights:")
        print("   - Focus work on the 5 IN_USE files")
        print("   - Stop work on the 3 REMOVED files")
        print("   - Monitor NEW files for future timeline updates")

    def _print_stats(self, tracker: TimelineTracker) -> None:
        """Print statistics in a formatted way."""
        stats = tracker.get_stats()
        print(f"\n📊 Current Statistics:")
        print(f"   Total files: {stats['total']}")
        print(f"   Not yet used: {stats['new']}")
        print(f"   In use: {stats['in_use']}")
        print(f"   Removed: {stats['removed']}")

    def run_all_scenarios(self, delay: float = 3.0) -> None:
        """Run all demo scenarios with delays between them."""
        print("\n" + "🎬" * 35)
        print(" " * 20 + "SHOTS DASHBOARD DEMO")
        print("🎬" * 35)
        print("\nThis demo showcases an animation studio workflow:")
        print("- Scan media files from your render farm")
        print("- Track which shots are used in editorial's timeline")
        print("- See which shots were added, kept, or removed")
        print("\nPress Ctrl+C to exit at any time.\n")

        time.sleep(2)

        try:
            self.run_scenario_1_initial_scan()
            time.sleep(delay)

            self.run_scenario_2_first_timeline()
            time.sleep(delay)

            self.run_scenario_3_revised_cut()
            time.sleep(delay)

            self.run_scenario_4_final_cut()

            print("\n" + "=" * 70)
            print("DEMO COMPLETE!")
            print("=" * 70)
            print(f"\nDemo data created in: {self.demo_dir}")
            print(f"Database saved to: {self.db.db_path}")
            print("\nYou can now:")
            print("  - Start the web interface: python -m shots_dashboard")
            print("  - View the demo data in your browser")
            print("  - Try scanning and updating with the demo timelines")

        except KeyboardInterrupt:
            print("\n\nDemo interrupted by user.")


def run_demo(demo_dir: Path | None = None, db_path: Path | None = None) -> None:
    """Run the demo mode."""
    if demo_dir is None:
        demo_dir = Path.home() / ".shots_dashboard" / "demo"

    if db_path is None:
        db_path = demo_dir / "demo_state.json"

    demo_dir.mkdir(parents=True, exist_ok=True)

    runner = DemoRunner(demo_dir, db_path)
    runner.run_all_scenarios()


if __name__ == "__main__":
    run_demo()
