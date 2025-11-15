"""
Flask application for the shots dashboard.

Provides REST API and web interface for tracking timeline file usage.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from flask import Flask, jsonify, render_template, request, Response, stream_with_context
from flask_socketio import SocketIO, emit

# Set up logger
logger = logging.getLogger(__name__)

# Try relative imports first (when used as package), fall back to absolute
try:
    from .database import Database, DatabaseError
    from .models import FileState, TrackerState
    from .timeline_tracker import TimelineTracker
    from .timeline_watcher import TimelineWatcher, MediaWatcher
    from .video_transcoder import (
        is_web_compatible,
        check_ffmpeg_available,
        stream_transcode_webm,
        TranscodingError
    )
except ImportError:
    from database import Database, DatabaseError
    from models import FileState, TrackerState
    from timeline_tracker import TimelineTracker
    from timeline_watcher import TimelineWatcher, MediaWatcher
    from video_transcoder import (
        is_web_compatible,
        is_audio_only,
        check_ffmpeg_available,
        transcode_to_webm,
        transcode_to_ogg,
        TranscodingError
    )


def create_app(
    db_path: Path | None = None,
    watch_dir: Path | None = None,
    media_dir: Path | None = None
) -> tuple[Flask, SocketIO]:
    """
    Application factory for creating Flask app with SocketIO.

    Args:
        db_path: Path to database file (for testing)
        watch_dir: Optional directory to watch for .otio timeline files
        media_dir: Optional directory to recursively scan and watch for media files

    Returns:
        Tuple of (Flask application, SocketIO instance)
    """
    app = Flask(__name__)

    # Configuration
    if db_path is None:
        db_path = Path.home() / ".shots_dashboard" / "state.json"

    app.config['DATABASE_PATH'] = db_path
    app.config['JSON_SORT_KEYS'] = False
    app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'

    # Initialize SocketIO
    socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

    # Initialize database
    db = Database(db_path)

    def get_tracker() -> TimelineTracker:
        """Get tracker instance with current state."""
        state = db.load()
        return TimelineTracker(state)

    def save_tracker(tracker: TimelineTracker) -> None:
        """Save tracker state to database."""
        db.save(tracker.state)

    def emit_state_update(event_type: str = 'state_update') -> None:
        """
        Emit state update to all connected clients.

        Args:
            event_type: Type of event ('state_update', 'scan', 'timeline_update', etc.)
        """
        try:
            tracker = get_tracker()

            # Get all current state
            stats = tracker.get_stats()
            files = {
                "new": [{"path": str(f.path), "name": f.path.name, "last_updated": f.last_updated.isoformat()}
                        for f in tracker.state.new_files],
                "in_use": [{"path": str(f.path), "name": f.path.name, "last_updated": f.last_updated.isoformat()}
                          for f in tracker.state.in_use_files],
                "removed": [{"path": str(f.path), "name": f.path.name, "last_updated": f.last_updated.isoformat()}
                           for f in tracker.state.removed_files],
            }

            # Get timeline history
            history = tracker.state.timeline_history
            current_snapshot = history.get_current()
            historical_snapshots = history.get_historical()
            historical_clips = history.get_all_historical_clips()

            timeline_history = {
                "current": {
                    "timeline_path": str(current_snapshot.timeline_path) if current_snapshot else None,
                    "timestamp": current_snapshot.timestamp.isoformat() if current_snapshot else None,
                    "clips": list(current_snapshot.clip_names) if current_snapshot else []
                } if current_snapshot else None,
                "historical_clips": sorted(list(historical_clips)),
                "snapshots": [
                    {
                        "timeline_path": str(snapshot.timeline_path),
                        "timestamp": snapshot.timestamp.isoformat(),
                        "clips": list(snapshot.clip_names),
                        "clip_count": len(snapshot.clip_names)
                    }
                    for snapshot in historical_snapshots
                ]
            }

            # Get visual timeline data
            timeline_visual = None
            if tracker.state.timeline_path and tracker.state.timeline_path.exists():
                try:
                    import opentimelineio as otio
                    timeline = otio.adapters.read_from_file(str(tracker.state.timeline_path))

                    if isinstance(timeline, otio.schema.Timeline):
                        duration = timeline.duration()
                        duration_seconds = float(duration.value) / float(duration.rate)

                        tracks_data = []
                        for track_idx, track in enumerate(timeline.tracks):
                            clips_data = []

                            for item_idx, item in enumerate(track):
                                if isinstance(item, otio.schema.Clip):
                                    range_in_parent = track.range_of_child_at_index(item_idx)
                                    start_time = range_in_parent.start_time
                                    duration_clip = range_in_parent.duration

                                    start_seconds = float(start_time.value) / float(start_time.rate)
                                    duration_seconds_clip = float(duration_clip.value) / float(duration_clip.rate)

                                    clips_data.append({
                                        "name": item.name or "Unnamed Clip",
                                        "start": start_seconds,
                                        "duration": duration_seconds_clip,
                                        "end": start_seconds + duration_seconds_clip
                                    })

                            if clips_data:
                                # Handle track.kind - can be enum or string depending on adapter
                                track_kind = "Video"  # default
                                if track.kind:
                                    if hasattr(track.kind, 'name'):
                                        track_kind = track.kind.name
                                    else:
                                        track_kind = str(track.kind)

                                tracks_data.append({
                                    "name": track.name or f"Track {track_idx + 1}",
                                    "kind": track_kind,
                                    "clips": clips_data
                                })

                        timeline_visual = {
                            "name": timeline.name,
                            "duration": duration_seconds,
                            "tracks": tracks_data
                        }
                except Exception as e:
                    logger.warning(f"⚠️  Error extracting timeline visual data: {e}")
                    logger.debug("Timeline visual extraction error:", exc_info=True)
                    # Timeline visual data is optional, continue without it

            # Emit to all connected clients
            socketio.emit(event_type, {
                "stats": stats,
                "files": files,
                "timeline_history": timeline_history,
                "timeline_visual": timeline_visual,
                "timeline_path": str(tracker.state.timeline_path) if tracker.state.timeline_path else None,
                "last_scan": tracker.state.last_scan.isoformat() if tracker.state.last_scan else None,
                "timestamp": datetime.now().isoformat()
            })
        except Exception as e:
            socketio.emit('error', {"message": str(e)})

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

            # Emit state update to all connected clients
            emit_state_update('scan_complete')

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

            # Emit state update to all connected clients
            emit_state_update('timeline_update_complete')

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

            # Emit state update to all connected clients
            emit_state_update('reset_complete')

            return jsonify({
                "success": True,
                "message": "State reset successfully"
            }), 200

        except DatabaseError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/timeline_history')
    def api_timeline_history() -> tuple[Any, int]:
        """
        Get timeline history showing current and historical timeline contents.

        Returns:
            JSON with current timeline clips and historical clips
        """
        try:
            tracker = get_tracker()
            history = tracker.state.timeline_history

            current_snapshot = history.get_current()
            historical_snapshots = history.get_historical()
            historical_clips = history.get_all_historical_clips()

            return jsonify({
                "success": True,
                "current": {
                    "timeline_path": str(current_snapshot.timeline_path) if current_snapshot else None,
                    "timestamp": current_snapshot.timestamp.isoformat() if current_snapshot else None,
                    "clips": list(current_snapshot.clip_names) if current_snapshot else []
                } if current_snapshot else None,
                "historical_clips": sorted(list(historical_clips)),
                "snapshots": [
                    {
                        "timeline_path": str(snapshot.timeline_path),
                        "timestamp": snapshot.timestamp.isoformat(),
                        "clips": list(snapshot.clip_names),
                        "clip_count": len(snapshot.clip_names)
                    }
                    for snapshot in historical_snapshots
                ]
            }), 200

        except DatabaseError as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/timeline_visual')
    def api_timeline_visual() -> tuple[Any, int]:
        """
        Get visual timeline data with clip positions and timing.

        Returns:
            JSON with timeline tracks, clips, and timing information
        """
        try:
            import opentimelineio as otio

            tracker = get_tracker()

            if not tracker.state.timeline_path or not tracker.state.timeline_path.exists():
                return jsonify({
                    "success": True,
                    "timeline": None
                }), 200

            # Load timeline with OTIO
            timeline = otio.adapters.read_from_file(str(tracker.state.timeline_path))

            if not isinstance(timeline, otio.schema.Timeline):
                return jsonify({
                    "success": False,
                    "error": "Invalid timeline format"
                }), 400

            # Extract timeline data
            duration = timeline.duration()
            duration_seconds = float(duration.value) / float(duration.rate)

            tracks_data = []
            for track_idx, track in enumerate(timeline.tracks):
                clips_data = []

                for item_idx, item in enumerate(track):
                    if isinstance(item, otio.schema.Clip):
                        # Get timeline position
                        range_in_parent = track.range_of_child_at_index(item_idx)
                        start_time = range_in_parent.start_time
                        duration = range_in_parent.duration

                        start_seconds = float(start_time.value) / float(start_time.rate)
                        duration_seconds_clip = float(duration.value) / float(duration.rate)

                        clips_data.append({
                            "name": item.name or "Unnamed Clip",
                            "start": start_seconds,
                            "duration": duration_seconds_clip,
                            "end": start_seconds + duration_seconds_clip
                        })

                if clips_data:  # Only include tracks with clips
                    # Handle track.kind - can be enum or string depending on adapter
                    track_kind = "Video"  # default
                    if track.kind:
                        if hasattr(track.kind, 'name'):
                            track_kind = track.kind.name
                        else:
                            track_kind = str(track.kind)

                    tracks_data.append({
                        "name": track.name or f"Track {track_idx + 1}",
                        "kind": track_kind,
                        "clips": clips_data
                    })

            return jsonify({
                "success": True,
                "timeline": {
                    "name": timeline.name,
                    "duration": duration_seconds,
                    "tracks": tracks_data
                }
            }), 200

        except Exception as e:
            return jsonify({
                "success": False,
                "error": str(e)
            }), 500

    @app.route('/api/preview/<path:filename>')
    def api_preview(filename: str) -> Response | tuple[Any, int]:
        """
        Serve media clip preview with on-the-fly transcoding if needed.

        For web-compatible formats (mp4, webm, ogg), serves file directly.
        For audio-only files, transcodes to OGG Vorbis.
        For video files, transcodes to WebM (VP8/Vorbis).

        Args:
            filename: Name of the clip file to preview

        Returns:
            Media stream (OGG or WebM format)
        """
        try:
            logger.debug(f"Preview request for: {filename}")
            tracker = get_tracker()

            # Find file in tracked files
            logger.debug(f"Searching through {len(tracker.state.files)} tracked files")
            file_path = None
            for record in tracker.state.files.values():
                if record.path.name == filename:
                    file_path = record.path
                    logger.debug(f"Found match: {file_path}")
                    break

            if file_path is None:
                logger.warning(f"File not found in tracked files: {filename}")
                logger.debug(f"Available files: {[r.path.name for r in list(tracker.state.files.values())[:10]]}")
                return jsonify({
                    "success": False,
                    "error": f"File not found: {filename}"
                }), 404

            if not file_path.exists():
                logger.warning(f"File path exists in tracker but not on disk: {file_path}")
                return jsonify({
                    "success": False,
                    "error": f"File not found on disk: {filename}"
                }), 404

            # Check if web-compatible
            if is_web_compatible(file_path):
                logger.debug(f"Serving web-compatible file directly: {file_path.suffix}")
                # Serve directly
                def generate():
                    with open(file_path, 'rb') as f:
                        while chunk := f.read(8192):
                            yield chunk

                # Determine appropriate MIME type
                ext = file_path.suffix.lower()
                if ext == '.webm':
                    mimetype = 'video/webm'
                elif ext == '.mp4':
                    mimetype = 'video/mp4'
                elif ext in {'.ogg', '.oga'}:
                    mimetype = 'audio/ogg'
                elif ext == '.mp3':
                    mimetype = 'audio/mpeg'
                elif ext == '.wav':
                    mimetype = 'audio/wav'
                elif ext == '.m4a':
                    mimetype = 'audio/mp4'
                else:
                    mimetype = 'application/octet-stream'

                return Response(
                    stream_with_context(generate()),
                    mimetype=mimetype,
                    headers={
                        'Accept-Ranges': 'bytes',
                        'Content-Type': mimetype
                    }
                )

            # Check if ffmpeg is available
            logger.debug(f"File requires transcoding: {file_path.suffix}")
            if not check_ffmpeg_available():
                logger.error("ffmpeg not available for transcoding")
                return jsonify({
                    "success": False,
                    "error": "Media transcoding not available (ffmpeg not installed)"
                }), 503

            # Check if audio-only file
            audio_only = is_audio_only(file_path)

            if audio_only:
                # Transcode to OGG Vorbis for audio-only files
                logger.debug(f"Starting audio transcode to OGG: {file_path}")
                try:
                    output_path = transcode_to_ogg(file_path)

                    def generate():
                        with open(output_path, 'rb') as f:
                            while chunk := f.read(8192):
                                yield chunk

                    return Response(
                        stream_with_context(generate()),
                        mimetype='audio/ogg',
                        headers={
                            'Content-Type': 'audio/ogg',
                            'Accept-Ranges': 'bytes'
                        }
                    )

                except TranscodingError as e:
                    return jsonify({
                        "success": False,
                        "error": f"Audio transcoding failed: {str(e)}"
                    }), 500
            else:
                # Transcode to WebM for video files (with caching)
                logger.debug(f"Starting video transcode to WebM: {file_path}")
                try:
                    output_path = transcode_to_webm(file_path)

                    def generate():
                        with open(output_path, 'rb') as f:
                            while chunk := f.read(8192):
                                yield chunk

                    return Response(
                        stream_with_context(generate()),
                        mimetype='video/webm',
                        headers={
                            'Content-Type': 'video/webm',
                            'Accept-Ranges': 'bytes'
                        }
                    )

                except TranscodingError as e:
                    return jsonify({
                        "success": False,
                        "error": f"Video transcoding failed: {str(e)}"
                    }), 500

        except Exception as e:
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

    # WebSocket event handlers
    @socketio.on('connect')
    def handle_connect() -> None:
        """Handle client connection."""
        logger.info("Client connected")
        # Send current state to newly connected client
        emit_state_update('initial_state')

    @socketio.on('disconnect')
    def handle_disconnect() -> None:
        """Handle client disconnection."""
        logger.info("Client disconnected")

    @socketio.on('request_state')
    def handle_request_state() -> None:
        """Handle explicit state request from client."""
        emit_state_update('state_update')

    # Scan for timeline files and load most recent if watch_dir is provided
    if watch_dir:
        logger.info(f"📝 Scanning for timeline files in: {watch_dir}")
        logger.debug(f"Timeline scan directory: {watch_dir}")
        try:
            # Find all timeline files (non-recursive, top level only)
            timeline_files = []
            for ext in ['.otio', '.xml']:
                timeline_files.extend(watch_dir.glob(f'*{ext}'))
                timeline_files.extend(watch_dir.glob(f'*{ext.upper()}'))

            logger.debug(f"Found timeline files: {[f.name for f in timeline_files]}")

            if timeline_files:
                # Sort by modification time, most recent first
                timeline_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                most_recent = timeline_files[0]

                logger.info(f"   Found {len(timeline_files)} timeline(s)")
                logger.info(f"   Loading most recent: {most_recent.name}")
                logger.debug(f"Most recent timeline: {most_recent} (mtime: {most_recent.stat().st_mtime})")

                tracker = get_tracker()
                transitions = tracker.update_from_timeline(most_recent)
                save_tracker(tracker)

                logger.info(f"   ✓ Loaded {most_recent.name}")
                logger.info(f"   {len(transitions)} state transitions")
                logger.debug(f"State transitions: {[(t.path.name, t.old_state, t.new_state) for t in transitions[:5]]}")

                # Emit state update
                emit_state_update('timeline_update_complete')
            else:
                logger.info(f"   No timeline files found")
                logger.warning(f"No .otio or .xml files in {watch_dir}")
        except Exception as e:
            logger.error(f"   ✗ Error scanning timelines: {e}")
            logger.exception(f"Timeline scan error: {e}")

        # Set up timeline watcher
        def on_timeline_file_detected(timeline_path: Path) -> None:
            """Handle new or modified timeline file."""
            try:
                logger.info(f"📝 Detected timeline file: {timeline_path.name}")
                tracker = get_tracker()
                transitions = tracker.update_from_timeline(timeline_path)
                save_tracker(tracker)

                # Emit state update
                emit_state_update('timeline_update_complete')

                logger.info(f"   ✓ Updated from {timeline_path.name}")
                logger.info(f"   {len(transitions)} state transitions")
            except Exception as e:
                logger.error(f"   ✗ Error processing {timeline_path.name}: {e}")

        timeline_watcher = TimelineWatcher(watch_dir, on_timeline_file_detected)
        timeline_watcher.start()
        app.timeline_watcher = timeline_watcher  # Store on app for cleanup

    # Perform initial recursive scan if media_dir is provided
    if media_dir:
        logger.info(f"📁 Scanning media directory: {media_dir}")
        logger.debug(f"Media scan directory: {media_dir}")
        try:
            tracker = get_tracker()
            transitions = tracker.scan_directory(media_dir)
            save_tracker(tracker)

            logger.info(f"   ✓ Found {len(transitions)} media files")
            logger.debug(f"Media files found: {[t.path.name for t in transitions[:10]]}")

            # Emit state update
            emit_state_update('scan_complete')
        except Exception as e:
            logger.error(f"   ✗ Error scanning directory: {e}")
            logger.exception(f"Media scan error: {e}")

    # Set up media watcher if media_dir is provided
    if media_dir:
        def on_media_file_detected(media_path: Path) -> None:
            """Handle new media file."""
            try:
                logger.info(f"🎬 Detected media file: {media_path.name}")
                tracker = get_tracker()

                # Track the new file by scanning its parent directory
                # This will pick up the new file and mark it as NEW
                transitions = tracker.scan_directory(media_path.parent, extensions={media_path.suffix.lower()})
                save_tracker(tracker)

                # Emit state update
                if transitions:
                    emit_state_update('scan_complete')
                    logger.info(f"   ✓ Tracked new file: {media_path.name}")
                    logger.info(f"   File state: NEW")
            except Exception as e:
                logger.error(f"   ✗ Error tracking {media_path.name}: {e}")

        media_watcher = MediaWatcher(media_dir, on_media_file_detected)
        media_watcher.start()
        app.media_watcher = media_watcher  # Store on app for cleanup

    return app, socketio


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
        "--auto-start",
        action="store_true",
        help="Auto-start demo scenario without waiting for ENTER (only with --demo)"
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
    parser.add_argument(
        "--watch-dir",
        type=Path,
        default=None,
        help="Directory to watch for .otio and .xml timeline files"
    )
    parser.add_argument(
        "--media-dir",
        type=Path,
        default=None,
        help="Directory to recursively scan and watch for media files"
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging for debugging"
    )

    args = parser.parse_args()

    # Configure logging based on verbose flag
    if args.verbose:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%H:%M:%S'
        )
        logger.info("Verbose logging enabled")
    else:
        logging.basicConfig(
            level=logging.INFO,
            format='%(message)s'
        )

    if args.demo:
        # Run visual demo mode (server + scenario playback)
        try:
            from demo_visual import run_visual_demo
        except ImportError:
            from shots_dashboard.demo_visual import run_visual_demo

        demo_dir = Path.home() / ".shots_dashboard" / "demo"
        db_path = demo_dir / "demo_state.json"

        run_visual_demo(demo_dir, db_path, args.port, auto_start=args.auto_start)
        return  # Visual demo handles its own server

    else:
        # Normal mode
        app, socketio = create_app(watch_dir=args.watch_dir, media_dir=args.media_dir)

    logger.info("Starting Shots Dashboard...")
    logger.info(f"Database: {app.config['DATABASE_PATH']}")
    logger.info(f"Navigate to http://localhost:{args.port}")

    if args.demo:
        logger.info("\n💡 Demo mode is active! Sample data has been created.")

    socketio.run(app, debug=True, host=args.host, port=args.port, allow_unsafe_werkzeug=True)


if __name__ == '__main__':
    main()
