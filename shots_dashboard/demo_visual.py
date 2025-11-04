"""
Visual demo mode that starts the server and plays scenarios.

Users can watch the dashboard update in real-time as scenarios execute.
"""

from __future__ import annotations

import multiprocessing
import sys
import time
from pathlib import Path

try:
    from .app import create_app
    from .scenario_dsl import create_production_workflow_scenario, STANDARD_SCENARIOS
    from .scenario_interpreters import FileSystemInterpreter
except ImportError:
    from app import create_app
    from scenario_dsl import create_production_workflow_scenario, STANDARD_SCENARIOS
    from scenario_interpreters import FileSystemInterpreter


def run_flask_server(db_path: Path, port: int = 5000) -> None:
    """Run Flask server in a separate process."""
    app = create_app(db_path)
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)


def run_visual_demo(
    demo_dir: Path,
    db_path: Path,
    port: int = 5000,
    scenario_name: str = "production"
) -> None:
    """
    Run visual demo mode.

    1. Start Flask server in background
    2. Wait for user to open browser
    3. Execute scenario with delays so user can watch
    4. Keep server running for exploration
    """
    print("\n" + "🎬" * 35)
    print(" " * 15 + "VISUAL DEMO MODE")
    print("🎬" * 35)

    # Create demo directory
    demo_dir.mkdir(parents=True, exist_ok=True)

    # Start server in background
    print(f"\n1. Starting web server on http://localhost:{port}...")
    server_process = multiprocessing.Process(
        target=run_flask_server,
        args=(db_path, port),
        daemon=True
    )
    server_process.start()

    # Wait for server to start
    time.sleep(3)

    print("\n" + "=" * 70)
    print("SERVER READY!")
    print("=" * 70)
    print(f"\n🌐 Open your browser to: http://localhost:{port}")
    print("\nThe dashboard will auto-refresh every 2 seconds.")
    print("You'll see changes happen in real-time as the scenario executes.")
    print("\nPress ENTER when you're ready to start the scenario...")

    try:
        input()
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")
        server_process.terminate()
        sys.exit(0)

    # Get scenario
    if scenario_name in STANDARD_SCENARIOS:
        scenario = STANDARD_SCENARIOS[scenario_name](demo_dir)
    else:
        scenario = create_production_workflow_scenario(demo_dir)

    print("\n" + "=" * 70)
    print(f"EXECUTING SCENARIO: {scenario.name}")
    print("=" * 70)
    print(f"\n{scenario.description}\n")
    print("Watch the browser as the scenario executes...\n")

    # Execute scenario with filesystem interpreter
    interpreter = FileSystemInterpreter(db_path)

    try:
        # Execute actions one by one with delays
        print("\nExecuting actions with 3-second delays between each step...")
        print("(Watch the browser to see changes in real-time)\n")

        for i, action in enumerate(scenario.actions, 1):
            print(f"[{i}/{len(scenario.actions)}] {action.__class__.__name__}: {action}")
            interpreter._execute_action(action)

            # Save state after each action so UI updates
            interpreter.db.save(interpreter.tracker.state)

            # Delay so user can see the change
            if i < len(scenario.actions):
                print("   Waiting 3 seconds for you to see the changes...")
                time.sleep(3)

        # Get final result
        result = {
            "success": True,
            "final_state": {
                "stats": interpreter.tracker.get_stats(),
                "files": {
                    "new": [{"path": str(f.path), "name": f.path.name} for f in interpreter.tracker.state.new_files],
                    "in_use": [{"path": str(f.path), "name": f.path.name} for f in interpreter.tracker.state.in_use_files],
                    "removed": [{"path": str(f.path), "name": f.path.name} for f in interpreter.tracker.state.removed_files],
                }
            }
        }

        print("\n" + "=" * 70)
        print("SCENARIO COMPLETE!")
        print("=" * 70)

        if result["success"]:
            print("\n✅ All actions executed successfully")
            print(f"\n📊 Final State:")
            state = result["final_state"]
            print(f"   Total files: {state['stats']['total']}")
            print(f"   Not yet used: {state['stats']['new']}")
            print(f"   In use: {state['stats']['in_use']}")
            print(f"   Removed: {state['stats']['removed']}")

        print(f"\n📁 Demo data location: {demo_dir}")
        print(f"🗄️  Database: {db_path}")

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
        "--scenario",
        choices=list(STANDARD_SCENARIOS.keys()),
        default="production",
        help="Scenario to run (default: production)"
    )
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

    args = parser.parse_args()

    demo_dir = args.demo_dir or (Path.home() / ".shots_dashboard" / "demo")
    db_path = demo_dir / "demo_state.json"

    try:
        run_visual_demo(demo_dir, db_path, args.port, args.scenario)
    except KeyboardInterrupt:
        print("\n\nDemo cancelled by user.")
        sys.exit(0)


if __name__ == "__main__":
    main()
