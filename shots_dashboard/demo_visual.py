"""
Visual demo mode that starts the server and plays scenarios.

Users can watch the dashboard update in real-time as scenarios execute.
"""

from __future__ import annotations

import multiprocessing
import os
import sys
import time
from pathlib import Path

import opentimelineio as otio

try:
    from .app import create_app
    from .video_transcoder import generate_test_video, check_ffmpeg_available
except ImportError:
    from app import create_app
    from video_transcoder import generate_test_video, check_ffmpeg_available


def run_flask_server(db_path: Path, watch_dir: Path, port: int = 5000) -> None:
    """Run Flask server with WebSocket support and file watching in a separate process."""
    app, socketio = create_app(db_path, watch_dir=watch_dir)
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)


def create_media_files(media_dir: Path) -> list[Path]:
    """Create demo media files with actual video content."""
    media_dir.mkdir(parents=True, exist_ok=True)

    files = [
        "bg_city_001.mov",
        "bg_city_002.mov",
        "shot_010_anim_v001.mov",
        "shot_010_anim_v002.mov",
        "shot_020_anim_v001.mov",
        "shot_030_anim_v001.mov",
        "temp_reference.mp4",
    ]

    created = []
    for filename in files:
        filepath = media_dir / filename
        if not filepath.exists() and check_ffmpeg_available():
            try:
                print(f"   Generating video: {filename}")
                generate_test_video(filepath, duration=5)
                created.append(filepath)
            except Exception as e:
                print(f"   Warning: Could not generate {filename}: {e}")
                filepath.touch()
                created.append(filepath)
        elif not filepath.exists():
            filepath.touch()
            created.append(filepath)

    return created


def create_timeline(timeline_path: Path, clip_names: list[str]) -> Path:
    """Create an OTIO timeline file with the given clips."""
    timeline = otio.schema.Timeline(name=timeline_path.stem)
    track = otio.schema.Track(name="video")
    timeline.tracks.append(track)

    for clip_name in clip_names:
        clip = otio.schema.Clip(
            name=clip_name,
            source_range=otio.opentime.TimeRange(
                start_time=otio.opentime.RationalTime(0, 24),
                duration=otio.opentime.RationalTime(120, 24)  # 5 seconds at 24fps
            )
        )
        track.append(clip)

    timeline_path.parent.mkdir(parents=True, exist_ok=True)
    otio.adapters.write_to_file(timeline, str(timeline_path))
    print(f"   Created timeline: {timeline_path.name} with {len(clip_names)} clips")
    return timeline_path


def run_visual_demo(
    demo_dir: Path,
    db_path: Path,
    port: int = 5000,
    auto_start: bool = False
) -> None:
    """
    Run visual demo mode.

    1. Start Flask server in background
    2. Wait for user to open browser (unless auto_start=True)
    3. Create timeline files and make API calls to demonstrate workflow
    4. Keep server running for exploration

    Args:
        demo_dir: Directory for demo files
        db_path: Path to database file
        port: Port for web server
        auto_start: Skip waiting for ENTER, start immediately
    """
    # Ensure ffmpeg is in PATH for video generation
    local_bin = os.path.expanduser('~/.local/bin')
    if local_bin not in os.environ.get('PATH', ''):
        os.environ['PATH'] = f"{local_bin}:{os.environ.get('PATH', '')}"

    print("\n" + "🎬" * 35)
    print(" " * 15 + "VISUAL DEMO MODE")
    print("🎬" * 35)

    # Create demo directory
    demo_dir.mkdir(parents=True, exist_ok=True)

    print(f"\n📁 Demo files will be created in: {demo_dir}")
    print(f"📁 Media files location: {demo_dir / 'media'}")

    # Start server in background with file watching
    print(f"\n1. Starting web server on http://localhost:{port}...")
    server_process = multiprocessing.Process(
        target=run_flask_server,
        args=(db_path, demo_dir, port),  # Watch demo_dir for .otio files
        daemon=True
    )
    server_process.start()

    # Wait for server to start
    time.sleep(3)

    print("\n" + "=" * 70)
    print("SERVER READY!")
    print("=" * 70)
    print(f"\n🌐 Open your browser to: http://localhost:{port}")
    print("\nThe dashboard updates in real-time via WebSocket.")
    print("You'll see changes instantly as the scenario executes.")

    if not auto_start:
        print("\nPress ENTER when you're ready to start the scenario...")

        try:
            input()
        except KeyboardInterrupt:
            print("\n\nCancelled by user.")
            server_process.terminate()
            sys.exit(0)
    else:
        print("\n🚀 Auto-starting scenario in 2 seconds...")
        time.sleep(2)

    print("\n" + "=" * 70)
    print("EXECUTING DEMO: Production Workflow")
    print("=" * 70)
    print("\nThis demo simulates a typical animation production workflow.")
    print("The server watches for new .otio files and automatically updates!")
    print("Watch the browser to see real-time WebSocket updates!\n")

    try:
        media_dir = demo_dir / "media"

        # Step 1: Create media files
        print("\n[1/4] Creating media files...")
        create_media_files(media_dir)
        print("   You can manually scan the media directory from the web UI")
        time.sleep(4)

        # Step 2: Create first timeline version
        print("\n[2/4] Creating timeline_v1.otio...")
        timeline_v1 = demo_dir / "timeline_v1.otio"
        create_timeline(timeline_v1, [
            "shot_010_anim_v001.mov",
            "shot_020_anim_v001.mov",
        ])
        print("   Server will automatically detect and process this timeline...")
        time.sleep(5)  # Give server time to detect and process

        # Step 3: Create second timeline version (add more shots)
        print("\n[3/4] Creating timeline_v2.otio (adding shot_030)...")
        timeline_v2 = demo_dir / "timeline_v2.otio"
        create_timeline(timeline_v2, [
            "shot_010_anim_v001.mov",
            "shot_020_anim_v001.mov",
            "shot_030_anim_v001.mov",
        ])
        print("   Server will automatically detect and process this timeline...")
        time.sleep(5)

        # Step 4: Create third timeline version (artist revision)
        print("\n[4/4] Creating timeline_v3.otio (artist updated shot_010 to v002)...")
        timeline_v3 = demo_dir / "timeline_v3.otio"
        create_timeline(timeline_v3, [
            "shot_010_anim_v002.mov",  # Updated version!
            "shot_020_anim_v001.mov",
            "shot_030_anim_v001.mov",
        ])
        print("   Server will automatically detect and process this timeline...")
        print("   shot_010_anim_v001.mov should be marked as REMOVED")
        print("   shot_010_anim_v002.mov should move to IN_USE")
        time.sleep(5)

        print("\n" + "=" * 70)
        print("DEMO COMPLETE!")
        print("=" * 70)
        print("\n✅ All workflow steps executed successfully")
        print(f"\n📁 Demo data location: {demo_dir}")
        print(f"📁 Media files: {media_dir}")
        print(f"📁 Timeline files: {demo_dir}/*.otio")

        print("\n" + "=" * 70)
        print("The server will keep running so you can explore the dashboard.")
        print("Try:")
        print(f"  - Refreshing the page to see the final state")
        print(f"  - Scanning: {demo_dir / 'media'}")
        print(f"  - Updating from different timelines in: {demo_dir}")
        print("\nPress Ctrl+C to stop the server...")
        print("=" * 70)

        # Keep server running
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n\nStopping server...")
    except Exception as e:
        print(f"\n\n❌ Error during scenario execution: {e}")
        import traceback
        traceback.print_exc()
    finally:
        server_process.terminate()
        server_process.join(timeout=5)
        if server_process.is_alive():
            server_process.kill()


def main() -> None:
    """Entry point for visual demo."""
    import argparse

    parser = argparse.ArgumentParser(description="Visual demo mode for shots dashboard")
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port for web server (default: 5000)"
    )
    parser.add_argument(
        "--demo-dir",
        type=Path,
        default=None,
        help="Directory for demo data (default: ~/.shots_dashboard/demo)"
    )
    parser.add_argument(
        "--auto-start",
        action="store_true",
        help="Auto-start demo without waiting for ENTER"
    )

    args = parser.parse_args()

    demo_dir = args.demo_dir or (Path.home() / ".shots_dashboard" / "demo")
    db_path = demo_dir / "demo_state.json"

    try:
        run_visual_demo(demo_dir, db_path, args.port, args.auto_start)
    except KeyboardInterrupt:
        print("\n\nDemo cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
