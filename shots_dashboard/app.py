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


def get_actual_source_duration(item) -> tuple[float | None, float | None, float | None]:
    """
    Get the actual source start, end, and duration for a clip.

    For clips with Time Remap effects, this extracts the actual media range being used,
    not the timeline range. For normal clips, returns the source_range values.

    Returns:
        Tuple of (source_start, source_end, source_duration) in seconds, or (None, None, None)
    """
    if not hasattr(item, 'source_range') or not item.source_range:
        return None, None, None

    # Check for Time Remap effect
    time_remap_effect = None
    if hasattr(item, 'effects'):
        for effect in item.effects:
            if hasattr(effect, 'effect_name') or (
                hasattr(effect, 'metadata') and
                'fcp_xml' in effect.metadata and
                effect.metadata['fcp_xml'].get('effectid') == 'timeremap'
            ):
                time_remap_effect = effect
                break

    if time_remap_effect and hasattr(time_remap_effect, 'metadata'):
        # Extract source range from Time Remap effect
        fcp_xml = time_remap_effect.metadata.get('fcp_xml', {})
        parameters = fcp_xml.get('parameter', [])

        # Look for graphdict parameter with keyframes
        for param in parameters:
            # Skip if param doesn't have dict-like behavior
            if not hasattr(param, 'get'):
                continue
            try:
                if param.get('parameterid') == 'graphdict' and 'keyframe' in param:
                    keyframes = param['keyframe']
                    if len(keyframes) >= 2:
                        # First and last keyframes define the mapping
                        # 'when' = timeline frame, 'value' = source frame
                        first_kf = keyframes[0]
                        last_kf = keyframes[-1]

                        # Get source frame range
                        source_start_frame = float(first_kf.get('value', 0))
                        source_end_frame = float(last_kf.get('value', 0))

                        # Convert to seconds using the source rate
                        rate = float(item.source_range.start_time.rate)
                        source_start = source_start_frame / rate
                        source_end = source_end_frame / rate
                        source_duration = abs(source_end - source_start)

                        return source_start, source_end, source_duration
            except (AttributeError, KeyError, TypeError):
                # Skip parameters that don't have the expected structure
                continue

    # No Time Remap effect or couldn't parse it - use source_range
    source_start = float(item.source_range.start_time.value) / float(item.source_range.start_time.rate)
    source_duration = float(item.source_range.duration.value) / float(item.source_range.duration.rate)
    source_end = source_start + source_duration

    return source_start, source_end, source_duration


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
    app.config['WATCH_DIR'] = watch_dir
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

            # Get all current state (grouped as sequences where appropriate)
            stats = tracker.get_stats()

            # Import FileState to use with get_files_as_sequences
            from models import FileState

            def get_display_name(file_record):
                """Get a friendly display name for a file or sequence."""
                # For sequences (paths like "folder/*.png"), show "folder/*.png"
                if file_record.path.name.startswith('*'):
                    return f"{file_record.path.parent.name}/{file_record.path.name}"
                # For regular files, just show the filename
                return file_record.path.name

            # Split NEW files into audio and video (like api_files does)
            new_files = tracker.state.get_files_as_sequences(FileState.NEW)
            new_audio = [f for f in new_files if f.is_audio()]
            new_video = [f for f in new_files if f.is_video() or not (f.is_audio() or f.is_video())]

            files = {
                "new_audio": [{"path": str(f.path), "name": get_display_name(f), "last_updated": f.last_updated.isoformat()}
                             for f in new_audio],
                "new_video": [{"path": str(f.path), "name": get_display_name(f), "last_updated": f.last_updated.isoformat()}
                             for f in new_video],
                "in_use": [{"path": str(f.path), "name": get_display_name(f), "last_updated": f.last_updated.isoformat()}
                          for f in tracker.state.get_files_as_sequences(FileState.IN_USE)],
                "removed": [{"path": str(f.path), "name": get_display_name(f), "last_updated": f.last_updated.isoformat()}
                           for f in tracker.state.get_files_as_sequences(FileState.REMOVED)],
                "newer_project": [{"path": str(f.path), "name": get_display_name(f), "last_updated": f.last_updated.isoformat()}
                                 for f in tracker.state.get_files_as_sequences(FileState.NEWER_PROJECT)],
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

                                    # Get actual source range (considers Time Remap effects)
                                    source_start, source_end, source_duration = get_actual_source_duration(item)

                                    clips_data.append({
                                        "name": item.name or "Unnamed Clip",
                                        "start": start_seconds,
                                        "duration": duration_seconds_clip,
                                        "end": start_seconds + duration_seconds_clip,
                                        "source_start": source_start,
                                        "source_end": source_end
                                    })

                            # Merge adjacent clips with the same name (preserving segment info)
                            merged_clips = []
                            for clip in clips_data:
                                if merged_clips and \
                                   merged_clips[-1]["name"] == clip["name"] and \
                                   abs(merged_clips[-1]["end"] - clip["start"]) < 0.01:
                                    # Extend the previous clip (adjacent clips with same source)
                                    merged_clips[-1]["end"] = clip["end"]
                                    merged_clips[-1]["duration"] = merged_clips[-1]["end"] - merged_clips[-1]["start"]
                                    # Add segment info
                                    if "segments" not in merged_clips[-1]:
                                        # Convert first clip to segments format
                                        merged_clips[-1]["segments"] = [{
                                            "timeline_start": merged_clips[-1]["start"],
                                            "timeline_end": merged_clips[-1]["segments_end"] if "segments_end" in merged_clips[-1] else clip["start"],
                                            "source_start": merged_clips[-1]["source_start"],
                                            "source_end": merged_clips[-1]["source_end"]
                                        }]
                                    # Add current clip as a segment
                                    merged_clips[-1]["segments"].append({
                                        "timeline_start": clip["start"],
                                        "timeline_end": clip["end"],
                                        "source_start": clip["source_start"],
                                        "source_end": clip["source_end"]
                                    })
                                    merged_clips[-1]["segments_end"] = clip["end"]
                                else:
                                    # Add as new clip
                                    merged_clips.append(clip.copy())

                            # Clean up temporary fields but keep segments
                            for clip in merged_clips:
                                clip.pop("source_start", None)
                                clip.pop("source_end", None)
                                clip.pop("segments_end", None)

                            clips_data = merged_clips

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
                            "name": tracker.state.timeline_path.name,
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

            # Import FileState for sequence grouping
            from models import FileState

            def serialize_file_with_display_name(record):
                """Serialize a file record with a friendly display name."""
                # For sequences, show "folder/*.png" instead of just "*.png"
                name = record.path.name
                if name.startswith('*'):
                    name = f"{record.path.parent.name}/{name}"

                return {
                    "path": str(record.path),
                    "name": name,
                    "last_updated": record.last_updated.isoformat()
                }

            # Split NEW files into audio and video
            new_files = state.get_files_as_sequences(FileState.NEW)
            new_audio = [f for f in new_files if f.is_audio()]
            new_video = [f for f in new_files if f.is_video() or not (f.is_audio() or f.is_video())]  # video + other

            return jsonify({
                "success": True,
                "files": {
                    "new_audio": [serialize_file_with_display_name(f) for f in new_audio],
                    "new_video": [serialize_file_with_display_name(f) for f in new_video],
                    "in_use": [serialize_file_with_display_name(f) for f in state.get_files_as_sequences(FileState.IN_USE)],
                    "removed": [serialize_file_with_display_name(f) for f in state.get_files_as_sequences(FileState.REMOVED)],
                    "newer_project": [serialize_file_with_display_name(f) for f in state.get_files_as_sequences(FileState.NEWER_PROJECT)]
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
                extensions if extensions else None,
                watch_dir=app.config.get('WATCH_DIR')
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

                        # Get actual source range (considers Time Remap effects)
                        source_start, source_end, source_duration = get_actual_source_duration(item)

                        # Calculate speed factor (source_duration / timeline_duration)
                        # speed > 1.0: sped up, speed < 1.0: slowed down, speed = 1.0: normal
                        speed = None
                        if source_duration is not None and duration_seconds_clip > 0:
                            speed = source_duration / duration_seconds_clip

                        clips_data.append({
                            "name": item.name or "Unnamed Clip",
                            "start": start_seconds,
                            "duration": duration_seconds_clip,
                            "end": start_seconds + duration_seconds_clip,
                            "source_start": source_start,
                            "source_end": source_end,
                            "source_duration": source_duration,
                            "speed": speed
                        })

                # Merge adjacent clips with the same name (preserving segment info)
                merged_clips = []
                for clip in clips_data:
                    if merged_clips and \
                       merged_clips[-1]["name"] == clip["name"] and \
                       abs(merged_clips[-1]["end"] - clip["start"]) < 0.01:
                        # Extend the previous clip (adjacent clips with same source)
                        merged_clips[-1]["end"] = clip["end"]
                        merged_clips[-1]["duration"] = merged_clips[-1]["end"] - merged_clips[-1]["start"]
                        # Add segment info
                        if "segments" not in merged_clips[-1]:
                            # Convert first clip to segments format
                            first_timeline_end = merged_clips[-1]["segments_end"] if "segments_end" in merged_clips[-1] else clip["start"]
                            first_timeline_duration = first_timeline_end - merged_clips[-1]["start"]
                            first_source_duration = merged_clips[-1]["source_end"] - merged_clips[-1]["source_start"] if merged_clips[-1]["source_end"] and merged_clips[-1]["source_start"] else None
                            first_speed = merged_clips[-1].get("speed")

                            merged_clips[-1]["segments"] = [{
                                "timeline_start": merged_clips[-1]["start"],
                                "timeline_end": first_timeline_end,
                                "timeline_duration": first_timeline_duration,
                                "source_start": merged_clips[-1]["source_start"],
                                "source_end": merged_clips[-1]["source_end"],
                                "source_duration": first_source_duration,
                                "speed": first_speed
                            }]

                        # Add current clip as a segment
                        segment_timeline_duration = clip["end"] - clip["start"]
                        segment_source_duration = clip.get("source_duration")
                        segment_speed = clip.get("speed")

                        merged_clips[-1]["segments"].append({
                            "timeline_start": clip["start"],
                            "timeline_end": clip["end"],
                            "timeline_duration": segment_timeline_duration,
                            "source_start": clip["source_start"],
                            "source_end": clip["source_end"],
                            "source_duration": segment_source_duration,
                            "speed": segment_speed
                        })
                        merged_clips[-1]["segments_end"] = clip["end"]
                    else:
                        # Add as new clip
                        merged_clips.append(clip.copy())

                # Clean up temporary fields but keep source ranges and segments
                # Keep source_start/source_end for non-merged clips (needed for preview)
                # Keep segments for merged clips (they already have source ranges)
                for clip in merged_clips:
                    clip.pop("segments_end", None)

                clips_data = merged_clips

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

                    # Debug: log what we're sending for BoiteAGant
                    for clip in clips_data:
                        if "BoiteAGant-001" in clip.get("name", ""):
                            logger.info(f"API returning clip: {clip.get('name')}")
                            logger.info(f"  Fields: {list(clip.keys())}")
                            logger.info(f"  Has speed: {'speed' in clip}")
                            if 'speed' in clip:
                                logger.info(f"  Speed value: {clip['speed']}")

            return jsonify({
                "success": True,
                "timeline": {
                    "name": tracker.state.timeline_path.name,
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
                elif ext == '.m4a':
                    mimetype = 'audio/mp4'
                elif ext in {'.jpg', '.jpeg'}:
                    mimetype = 'image/jpeg'
                elif ext == '.png':
                    mimetype = 'image/png'
                elif ext == '.gif':
                    mimetype = 'image/gif'
                elif ext == '.webp':
                    mimetype = 'image/webp'
                elif ext == '.svg':
                    mimetype = 'image/svg+xml'
                else:
                    mimetype = 'application/octet-stream'

                return Response(
                    stream_with_context(generate()),
                    mimetype=mimetype,
                    headers={
                        'Accept-Ranges': 'bytes',
                        'Content-Type': mimetype,
                        'Content-Disposition': 'inline'
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
                            'Accept-Ranges': 'bytes',
                            'Content-Disposition': 'inline'
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
                            'Accept-Ranges': 'bytes',
                            'Content-Disposition': 'inline'
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

    @app.route('/api/preview/clip', methods=['POST'])
    def api_clip_preview() -> Response | tuple[Any, int]:
        """
        Generate clip-accurate preview for a timeline clip.

        Expects JSON body with:
        {
            "path": "/path/to/source/file.mov",
            "clip_data": {
                "source_start": 5.0,
                "source_end": 10.0,
                OR
                "segments": [
                    {"source_start": 0.0, "source_end": 2.0},
                    {"source_start": 4.0, "source_end": 6.0}
                ]
            }
        }

        Returns the generated preview file with appropriate mime type.
        """
        try:
            from clip_preview import ClipPreviewGenerator, PreviewGenerationError

            data = request.get_json()
            if not data or 'path' not in data or 'clip_data' not in data:
                return jsonify({
                    "success": False,
                    "error": "Missing 'path' or 'clip_data' in request"
                }), 400

            filename = data['path']
            clip_data = data['clip_data']

            # Debug logging to see what frontend is sending
            logger.info(f"Clip preview request for: {filename}")
            logger.info(f"Clip data received: {clip_data}")
            logger.info(f"  - Has duration: {'duration' in clip_data}")
            logger.info(f"  - Has speed: {'speed' in clip_data}")
            if 'duration' in clip_data:
                logger.info(f"  - Duration value: {clip_data['duration']}")
            if 'speed' in clip_data:
                logger.info(f"  - Speed value: {clip_data['speed']}")

            # Resolve filename to full path using tracker's file list
            tracker = get_tracker()
            source_path = None

            # Search for file in tracker's files
            for file_path, record in tracker.state.files.items():
                if file_path.name == filename:
                    source_path = file_path
                    break

            # If not found in tracker, try as direct path (for testing)
            if not source_path:
                source_path = Path(filename)

            # Validate source file exists and is within media_dir
            if media_dir:
                try:
                    source_path_resolved = source_path.resolve()
                    media_dir_resolved = media_dir.resolve()

                    if not source_path_resolved.is_relative_to(media_dir_resolved):
                        return jsonify({
                            "success": False,
                            "error": f"Access denied: file outside media directory ({source_path})"
                        }), 403
                except (ValueError, OSError) as e:
                    return jsonify({
                        "success": False,
                        "error": f"Invalid path: {str(e)}"
                    }), 400

            if not source_path.exists():
                return jsonify({
                    "success": False,
                    "error": f"Source file not found: {source_path}"
                }), 404

            # Generate preview
            logger.info(f"Generating clip preview for {source_path.name}")
            generator = ClipPreviewGenerator()

            try:
                preview_path = generator.generate_preview(
                    clip_data,
                    source_path,
                    timeout=300
                )
            except PreviewGenerationError as e:
                logger.error(f"Preview generation failed: {e}")
                return jsonify({
                    "success": False,
                    "error": f"Preview generation failed: {str(e)}"
                }), 500
            except TimeoutError:
                logger.error("Preview generation timed out")
                return jsonify({
                    "success": False,
                    "error": "Preview generation timed out (exceeded 5 minutes)"
                }), 504

            # Stream the preview file
            def generate():
                with open(preview_path, 'rb') as f:
                    while chunk := f.read(8192):
                        yield chunk

            # Determine mime type
            ext = preview_path.suffix.lower()
            if ext == '.mp4':
                mimetype = 'video/mp4'
            elif ext == '.webm':
                mimetype = 'video/webm'
            elif ext in {'.m4a', '.aac'}:
                mimetype = 'audio/mp4'
            elif ext == '.ogg':
                mimetype = 'audio/ogg'
            elif ext == '.mp3':
                mimetype = 'audio/mpeg'
            elif ext == '.wav':
                mimetype = 'audio/wav'
            else:
                mimetype = 'application/octet-stream'

            return Response(
                stream_with_context(generate()),
                mimetype=mimetype,
                headers={
                    'Accept-Ranges': 'bytes',
                    'Content-Type': mimetype,
                    'Content-Disposition': 'inline'
                }
            )

        except Exception as e:
            logger.exception("Clip preview API error")
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

            # Filter out dotfiles (hidden files starting with .)
            timeline_files = [f for f in timeline_files if not f.name.startswith('.')]

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
            transitions = tracker.scan_directory(media_dir, watch_dir=watch_dir)
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
                # State will be NEW or REMOVED based on .prproj history
                transitions = tracker.scan_directory(
                    media_path.parent,
                    extensions={media_path.suffix.lower()},
                    watch_dir=watch_dir
                )
                save_tracker(tracker)

                # Emit state update
                if transitions:
                    emit_state_update('scan_complete')
                    logger.info(f"   ✓ Tracked new file: {media_path.name}")
                    if transitions:
                        logger.info(f"   File state: {transitions[0].new_state.name}")
            except Exception as e:
                logger.error(f"   ✗ Error tracking {media_path.name}: {e}")

        media_watcher = MediaWatcher(media_dir, on_media_file_detected)
        media_watcher.start()
        app.media_watcher = media_watcher  # Store on app for cleanup

    # Set up periodic scan to catch any missed file changes
    if media_dir or watch_dir:
        import threading
        import time

        def periodic_scan():
            """Scan directories every 60 seconds to catch missed updates."""
            while True:
                time.sleep(60)
                try:
                    logger.debug("Running periodic scan...")
                    tracker = get_tracker()
                    transitions = []

                    # Scan media directory if configured
                    if media_dir:
                        media_transitions = tracker.scan_directory(media_dir, watch_dir=watch_dir)
                        transitions.extend(media_transitions)

                    if transitions:
                        save_tracker(tracker)
                        emit_state_update('scan_complete')
                        logger.info(f"Periodic scan: {len(transitions)} state changes detected")
                    else:
                        logger.debug("Periodic scan: no changes")

                except Exception as e:
                    logger.error(f"Periodic scan error: {e}")

        scan_thread = threading.Thread(target=periodic_scan, daemon=True)
        scan_thread.start()
        logger.info("⏱️  Periodic scan enabled (every 60 seconds)")

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
    parser.add_argument(
        "--no-reload",
        action="store_true",
        help="Disable auto-reload on code changes (enabled by default)"
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

    # Enable auto-reload by default unless --no-reload is specified
    enable_reload = not args.no_reload
    if enable_reload:
        logger.info("🔄 Auto-reload enabled - server will restart on code changes")

        # Add extra files to watch for changes (templates, static files)
        import os
        extra_files = []

        # Watch template files
        template_dir = Path(__file__).parent / 'templates'
        if template_dir.exists():
            for root, dirs, files in os.walk(template_dir):
                for file in files:
                    extra_files.append(str(Path(root) / file))

        # Watch static files
        static_dir = Path(__file__).parent / 'static'
        if static_dir.exists():
            for root, dirs, files in os.walk(static_dir):
                for file in files:
                    extra_files.append(str(Path(root) / file))

        logger.info(f"   Watching {len(extra_files)} additional files for changes")
    else:
        extra_files = None

    # Use explicit use_reloader parameter for better SocketIO compatibility
    socketio.run(
        app,
        debug=enable_reload,
        use_reloader=enable_reload,
        host=args.host,
        port=args.port,
        allow_unsafe_werkzeug=True,
        log_output=True,
        extra_files=extra_files
    )


if __name__ == '__main__':
    main()
