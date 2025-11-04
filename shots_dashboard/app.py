"""
Flask application for the shots dashboard.

Provides REST API and web interface for tracking timeline file usage.
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request

# Try relative imports first (when used as package), fall back to absolute
try:
    from .database import Database, DatabaseError
    from .models import FileState, TrackerState
    from .timeline_tracker import TimelineTracker
except ImportError:
    from database import Database, DatabaseError
    from models import FileState, TrackerState
    from timeline_tracker import TimelineTracker


def create_app(db_path: Path | None = None) -> Flask:
    """
    Application factory for creating Flask app.

    Args:
        db_path: Path to database file (for testing)

    Returns:
        Configured Flask application
    """
    app = Flask(__name__)

    # Configuration
    if db_path is None:
        db_path = Path.home() / ".shots_dashboard" / "state.json"

    app.config['DATABASE_PATH'] = db_path
    app.config['JSON_SORT_KEYS'] = False

    # Initialize database
    db = Database(db_path)

    def get_tracker() -> TimelineTracker:
        """Get tracker instance with current state."""
        state = db.load()
        return TimelineTracker(state)

    def save_tracker(tracker: TimelineTracker) -> None:
        """Save tracker state to database."""
        db.save(tracker.state)

    @app.route('/')
    def index() -> str:
        """Render main dashboard."""
        return render_template('index.html')

    @app.route('/api/status')
    def api_status() -> tuple[Any, int]:
        """Get current status and statistics."""
        try:
            tracker = get_tracker()
            state = tracker.state

            return jsonify({
                "success": True,
                "stats": tracker.get_stats(),
                "timeline_path": str(state.timeline_path) if state.timeline_path else None,
                "last_scan": state.last_scan.isoformat() if state.last_scan else None
            }), 200

        except DatabaseError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/files')
    def api_files() -> tuple[Any, int]:
        """Get all files grouped by state."""
        try:
            tracker = get_tracker()
            state = tracker.state

            def serialize_file(record: Any) -> dict[str, Any]:
                return {
                    "path": str(record.path),
                    "name": record.path.name,
                    "state": record.state.name,
                    "last_updated": record.last_updated.isoformat()
                }

            return jsonify({
                "success": True,
                "files": {
                    "new": [serialize_file(f) for f in state.new_files],
                    "in_use": [serialize_file(f) for f in state.in_use_files],
                    "removed": [serialize_file(f) for f in state.removed_files]
                }
            }), 200

        except DatabaseError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/scan', methods=['POST'])
    def api_scan() -> tuple[Any, int]:
        """Scan a directory for media files."""
        try:
            data = request.get_json()
            if not data or 'directory' not in data:
                return jsonify({
                    "success": False,
                    "error": "Missing 'directory' parameter"
                }), 400

            directory = Path(data['directory'])
            extensions = set(data.get('extensions', []))

            tracker = get_tracker()
            transitions = tracker.scan_directory(
                directory,
                extensions if extensions else None
            )
            save_tracker(tracker)

            return jsonify({
                "success": True,
                "message": f"Scanned {directory}",
                "transitions": [
                    {
                        "path": str(t.path),
                        "name": t.path.name,
                        "old_state": t.old_state.name if t.old_state else None,
                        "new_state": t.new_state.name,
                        "timestamp": t.timestamp.isoformat()
                    }
                    for t in transitions
                ],
                "stats": tracker.get_stats()
            }), 200

        except ValueError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 400
        except DatabaseError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/update_timeline', methods=['POST'])
    def api_update_timeline() -> tuple[Any, int]:
        """Update state based on timeline file."""
        try:
            data = request.get_json()
            if not data or 'timeline_path' not in data:
                return jsonify({
                    "success": False,
                    "error": "Missing 'timeline_path' parameter"
                }), 400

            timeline_path = Path(data['timeline_path'])

            tracker = get_tracker()
            transitions = tracker.update_from_timeline(timeline_path)
            save_tracker(tracker)

            return jsonify({
                "success": True,
                "message": f"Updated from timeline: {timeline_path.name}",
                "transitions": [
                    {
                        "path": str(t.path),
                        "name": t.path.name,
                        "old_state": t.old_state.name if t.old_state else None,
                        "new_state": t.new_state.name,
                        "timestamp": t.timestamp.isoformat()
                    }
                    for t in transitions
                ],
                "stats": tracker.get_stats()
            }), 200

        except ValueError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 400
        except DatabaseError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/reset', methods=['POST'])
    def api_reset() -> tuple[Any, int]:
        """Reset all state."""
        try:
            db.reset()
            return jsonify({
                "success": True,
                "message": "State reset successfully"
            }), 200

        except DatabaseError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.errorhandler(404)
    def not_found(e: Any) -> tuple[Any, int]:
        """Handle 404 errors."""
        if request.path.startswith('/api/'):
            return jsonify({
                "success": False,
                "error": "Endpoint not found"
            }), 404
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def server_error(e: Any) -> tuple[Any, int]:
        """Handle 500 errors."""
        return jsonify({
            "success": False,
            "error": "Internal server error"
        }), 500

    return app


def main() -> None:
    """Run the Flask development server."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Shots Dashboard - Track timeline file usage"
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run in demo mode with sample data and automated scenarios"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Port to run the server on (default: 5000)"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host to bind to (default: 0.0.0.0)"
    )

    args = parser.parse_args()

    if args.demo:
        # Run demo mode
        from pathlib import Path
        try:
            from demo import run_demo
        except ImportError:
            from shots_dashboard.demo import run_demo

        print("\n" + "=" * 70)
        print("DEMO MODE")
        print("=" * 70)
        print("\nRunning automated demo scenarios...")
        print("This will create sample data and show you how the dashboard works.\n")

        demo_dir = Path.home() / ".shots_dashboard" / "demo"
        db_path = demo_dir / "demo_state.json"

        run_demo(demo_dir, db_path)

        print("\n" + "=" * 70)
        print("Demo complete! Now starting the web interface...")
        print("=" * 70)
        print(f"\nTo view the demo data:")
        print(f"  1. Navigate to http://localhost:{args.port}")
        print(f"  2. Click 'Refresh' to load the demo data")
        print(f"  3. Or scan: {demo_dir / 'media'}")
        print(f"  4. Or update from: {demo_dir / 'timelines' / 'final_cut.otio'}")
        print()

        # Create app with demo database
        app = create_app(db_path)
    else:
        # Normal mode
        app = create_app()

    print("Starting Shots Dashboard...")
    print(f"Database: {app.config['DATABASE_PATH']}")
    print(f"Navigate to http://localhost:{args.port}")

    if args.demo:
        print("\n💡 Demo mode is active! Sample data has been created.")

    app.run(debug=True, host=args.host, port=args.port)


if __name__ == '__main__':
    main()
