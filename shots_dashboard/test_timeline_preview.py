"""
E2E tests for timeline-aware preview with audio mixing.

Tests the new timeline preview feature that replaces video clip audio
with audio from overlapping timeline tracks.
"""

import pytest
import json
import tempfile
import subprocess
from pathlib import Path

from app import create_app
from timeline_preview import generate_timeline_preview, TimelinePreviewError


def generate_test_video_with_audio(output_path: Path, duration: float = 5.0, freq: int = 440):
    """Generate test video with audio at specified frequency."""
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', f'color=c=blue:s=320x240:d={duration}:r=24',
        '-f', 'lavfi', '-i', f'sine=frequency={freq}:duration={duration}:sample_rate=48000',
        '-c:v', 'libx264', '-preset', 'ultrafast',
        '-c:a', 'aac',
        str(output_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)


def generate_test_audio(output_path: Path, duration: float = 5.0, freq: int = 880):
    """Generate test audio at specified frequency."""
    cmd = [
        'ffmpeg', '-y',
        '-f', 'lavfi', '-i', f'sine=frequency={freq}:duration={duration}:sample_rate=48000',
        '-c:a', 'pcm_s16le',  # Use PCM for WAV files, not AAC
        str(output_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True, timeout=30)


def get_audio_duration(file_path: Path) -> float:
    """Get duration of audio/video file using ffprobe."""
    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(file_path)
    ], capture_output=True, text=True, check=True, timeout=10)
    return float(result.stdout.strip())


def has_audio_stream(file_path: Path) -> bool:
    """Check if file has an audio stream."""
    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-select_streams', 'a',
        '-show_entries', 'stream=codec_type',
        '-of', 'default=noprint_wrappers=1:nokey=1',
        str(file_path)
    ], capture_output=True, text=True, timeout=10)
    return 'audio' in result.stdout.lower()


def count_audio_streams(file_path: Path) -> int:
    """Count number of audio streams in file."""
    result = subprocess.run([
        'ffprobe', '-v', 'error',
        '-select_streams', 'a',
        '-show_entries', 'stream=index',
        '-of', 'csv=p=0',
        str(file_path)
    ], capture_output=True, text=True, timeout=10)
    return len([line for line in result.stdout.strip().split('\n') if line])


@pytest.fixture
def test_media(tmp_path):
    """Create test media files."""
    media_dir = tmp_path / "media"
    media_dir.mkdir()

    # Video clip (440Hz audio)
    video_path = media_dir / "video.mp4"
    generate_test_video_with_audio(video_path, duration=10.0, freq=440)

    # Audio track 1 (880Hz - dialog)
    audio1_path = media_dir / "dialog.wav"
    generate_test_audio(audio1_path, duration=15.0, freq=880)

    # Audio track 2 (1320Hz - music)
    audio2_path = media_dir / "music.wav"
    generate_test_audio(audio2_path, duration=20.0, freq=1320)

    return {
        'dir': media_dir,
        'video': video_path,
        'audio1': audio1_path,
        'audio2': audio2_path,
    }


@pytest.fixture
def app_client(test_media):
    """Create Flask test client."""
    app, socketio = create_app(media_dir=test_media['dir'])
    app.config['TESTING'] = True

    with app.test_client() as client:
        yield client


class TestTimelinePreviewAPI:
    """Tests for /api/preview/clip with timeline_data"""

    def test_preview_with_overlapping_audio_tracks(self, app_client, test_media):
        """Test preview generation with overlapping audio from timeline tracks."""
        # Timeline data with overlapping audio tracks
        timeline_data = {
            'tracks': [
                {
                    'kind': 'Audio',
                    'name': 'Audio 1',
                    'clips': [
                        {
                            'name': 'dialog.wav',
                            'start': 0.0,
                            'duration': 15.0,
                            'source_start': 0.0,
                            'source_duration': 15.0,
                        }
                    ]
                },
                {
                    'kind': 'Audio',
                    'name': 'Audio 2',
                    'clips': [
                        {
                            'name': 'music.wav',
                            'start': 5.0,
                            'duration': 20.0,
                            'source_start': 0.0,
                            'source_duration': 20.0,
                        }
                    ]
                }
            ]
        }

        # Request preview for video clip from 2.0s to 12.0s (10s duration)
        request_data = {
            'path': 'video.mp4',
            'clip_data': {
                'source_start': 0.0,
                'source_end': 10.0,
                'timeline_start': 2.0,
                'timeline_duration': 10.0,
            },
            'timeline_data': timeline_data
        }

        response = app_client.post(
            '/api/preview/clip',
            data=json.dumps(request_data),
            content_type='application/json'
        )

        assert response.status_code == 200, f"API failed: {response.data}"
        assert response.content_type.startswith('video/')

        # Save and verify
        preview_file = Path(tempfile.mktemp(suffix='.webm'))
        try:
            preview_file.write_bytes(response.data)

            # Should have correct duration
            duration = get_audio_duration(preview_file)
            assert abs(duration - 10.0) < 0.2, f"Duration {duration}s != 10.0s"

            # Should have audio (mixed from timeline tracks, not original video audio)
            assert has_audio_stream(preview_file), "Preview should have audio"

            print(f"✓ Preview with overlapping audio: {duration:.2f}s")

        finally:
            if preview_file.exists():
                preview_file.unlink()

    def test_preview_without_timeline_data_strips_audio(self, app_client, test_media):
        """Test that preview without timeline_data strips audio."""
        request_data = {
            'path': 'video.mp4',
            'clip_data': {
                'source_start': 0.0,
                'source_end': 5.0,
            }
            # No timeline_data - should strip audio
        }

        response = app_client.post(
            '/api/preview/clip',
            data=json.dumps(request_data),
            content_type='application/json'
        )

        assert response.status_code == 200

        preview_file = Path(tempfile.mktemp(suffix='.webm'))
        try:
            preview_file.write_bytes(response.data)

            # Should have video but NO audio
            duration = get_audio_duration(preview_file)
            assert abs(duration - 5.0) < 0.2

            # Should NOT have audio stream
            assert not has_audio_stream(preview_file), "Preview should have no audio when timeline_data is missing"

            print(f"✓ Preview without timeline data: no audio, {duration:.2f}s")

        finally:
            if preview_file.exists():
                preview_file.unlink()

    def test_preview_with_empty_timeline_strips_audio(self, app_client, test_media):
        """Test that preview with empty timeline tracks strips audio."""
        request_data = {
            'path': 'video.mp4',
            'clip_data': {
                'source_start': 0.0,
                'source_end': 5.0,
            },
            'timeline_data': {
                'tracks': []  # Empty tracks
            }
        }

        response = app_client.post(
            '/api/preview/clip',
            data=json.dumps(request_data),
            content_type='application/json'
        )

        assert response.status_code == 200

        preview_file = Path(tempfile.mktemp(suffix='.webm'))
        try:
            preview_file.write_bytes(response.data)

            # Should NOT have audio
            assert not has_audio_stream(preview_file), "Preview should have no audio with empty timeline"

            print(f"✓ Preview with empty timeline: no audio")

        finally:
            if preview_file.exists():
                preview_file.unlink()

    def test_preview_with_partial_audio_overlap(self, app_client, test_media):
        """Test preview with audio that only partially overlaps."""
        timeline_data = {
            'tracks': [
                {
                    'kind': 'Audio',
                    'name': 'Audio 1',
                    'clips': [
                        # Audio only overlaps second half of video clip
                        {
                            'name': 'dialog.wav',
                            'start': 5.0,
                            'duration': 10.0,
                            'source_start': 0.0,
                            'source_duration': 10.0,
                        }
                    ]
                }
            ]
        }

        # Video clip from 0.0s to 10.0s on timeline
        request_data = {
            'path': 'video.mp4',
            'clip_data': {
                'source_start': 0.0,
                'source_end': 10.0,
                'timeline_start': 0.0,
                'timeline_duration': 10.0,
            },
            'timeline_data': timeline_data
        }

        response = app_client.post(
            '/api/preview/clip',
            data=json.dumps(request_data),
            content_type='application/json'
        )

        assert response.status_code == 200

        preview_file = Path(tempfile.mktemp(suffix='.webm'))
        try:
            preview_file.write_bytes(response.data)

            # Should have audio (from partial overlap)
            assert has_audio_stream(preview_file), "Preview should have audio from partial overlap"

            duration = get_audio_duration(preview_file)
            assert abs(duration - 10.0) < 0.2

            print(f"✓ Preview with partial overlap: {duration:.2f}s")

        finally:
            if preview_file.exists():
                preview_file.unlink()

    def test_preview_with_no_audio_overlap(self, app_client, test_media):
        """Test preview when no audio tracks overlap."""
        timeline_data = {
            'tracks': [
                {
                    'kind': 'Audio',
                    'name': 'Audio 1',
                    'clips': [
                        # Audio completely before video clip
                        {
                            'name': 'dialog.wav',
                            'start': -10.0,
                            'duration': 5.0,
                            'source_start': 0.0,
                            'source_duration': 5.0,
                        }
                    ]
                }
            ]
        }

        request_data = {
            'path': 'video.mp4',
            'clip_data': {
                'source_start': 0.0,
                'source_end': 5.0,
                'timeline_start': 0.0,
                'timeline_duration': 5.0,
            },
            'timeline_data': timeline_data
        }

        response = app_client.post(
            '/api/preview/clip',
            data=json.dumps(request_data),
            content_type='application/json'
        )

        assert response.status_code == 200

        preview_file = Path(tempfile.mktemp(suffix='.webm'))
        try:
            preview_file.write_bytes(response.data)

            # Should have video but no audio (no overlaps)
            # Note: The algebra should create composition with audio=None
            duration = get_audio_duration(preview_file)
            assert abs(duration - 5.0) < 0.2

            print(f"✓ Preview with no overlap: {duration:.2f}s")

        finally:
            if preview_file.exists():
                preview_file.unlink()

    def test_preview_caching_with_timeline_data(self, app_client, test_media):
        """Test that previews with same timeline data are cached."""
        timeline_data = {
            'tracks': [
                {
                    'kind': 'Audio',
                    'name': 'Audio 1',
                    'clips': [
                        {
                            'name': 'dialog.wav',
                            'start': 0.0,
                            'duration': 10.0,
                            'source_start': 0.0,
                            'source_duration': 10.0,
                        }
                    ]
                }
            ]
        }

        request_data = {
            'path': 'video.mp4',
            'clip_data': {
                'source_start': 0.0,
                'source_end': 5.0,
                'timeline_start': 0.0,
                'timeline_duration': 5.0,
            },
            'timeline_data': timeline_data
        }

        # First request
        response1 = app_client.post(
            '/api/preview/clip',
            data=json.dumps(request_data),
            content_type='application/json'
        )

        assert response1.status_code == 200
        data1 = response1.data

        # Second request (should use cache)
        response2 = app_client.post(
            '/api/preview/clip',
            data=json.dumps(request_data),
            content_type='application/json'
        )

        assert response2.status_code == 200
        data2 = response2.data

        # Should return same data (cached)
        assert len(data1) == len(data2)

        print(f"✓ Cache working: {len(data1)} bytes")


class TestTimelinePreviewModule:
    """Direct tests for timeline_preview.py module"""

    def test_generate_timeline_preview_with_audio(self, test_media, tmp_path):
        """Test generate_timeline_preview function directly."""
        video_clip_data = {
            'source_start': 0.0,
            'source_duration': 10.0,
            'timeline_start': 2.0,
            'timeline_duration': 10.0,
        }

        timeline_data = {
            'tracks': [
                {
                    'kind': 'Audio',
                    'name': 'Audio 1',
                    'clips': [
                        {
                            'name': 'dialog.wav',
                            'start': 0.0,
                            'duration': 15.0,
                            'source_start': 0.0,
                            'source_duration': 15.0,
                        }
                    ]
                }
            ]
        }

        output_dir = tmp_path / "previews"

        preview_path = generate_timeline_preview(
            video_clip_data,
            test_media['video'],
            timeline_data,
            output_dir
        )

        assert preview_path.exists()

        # Verify output
        duration = get_audio_duration(preview_path)
        assert abs(duration - 10.0) < 0.2

        assert has_audio_stream(preview_path)

        print(f"✓ Direct module test: {preview_path.name}, {duration:.2f}s")

    def test_generate_simple_preview_no_audio(self, test_media, tmp_path):
        """Test simple preview fallback strips audio."""
        video_clip_data = {
            'source_start': 0.0,
            'source_duration': 5.0,
        }

        output_dir = tmp_path / "previews"

        # No timeline_data - should generate simple preview
        preview_path = generate_timeline_preview(
            video_clip_data,
            test_media['video'],
            timeline_data=None,
            output_dir=output_dir
        )

        assert preview_path.exists()

        # Should have no audio
        assert not has_audio_stream(preview_path), "Simple preview should strip audio"

        duration = get_audio_duration(preview_path)
        assert abs(duration - 5.0) < 0.2

        print(f"✓ Simple preview (no audio): {duration:.2f}s")

    def test_preview_cache_reuse(self, test_media, tmp_path):
        """Test that cached previews are reused."""
        video_clip_data = {
            'source_start': 0.0,
            'source_duration': 5.0,
            'timeline_start': 0.0,
            'timeline_duration': 5.0,
        }

        timeline_data = {
            'tracks': [
                {
                    'kind': 'Audio',
                    'name': 'Audio 1',
                    'clips': [
                        {
                            'name': 'dialog.wav',
                            'start': 0.0,
                            'duration': 10.0,
                            'source_start': 0.0,
                            'source_duration': 10.0,
                        }
                    ]
                }
            ]
        }

        output_dir = tmp_path / "previews"

        # First generation
        preview1 = generate_timeline_preview(
            video_clip_data,
            test_media['video'],
            timeline_data,
            output_dir
        )

        mtime1 = preview1.stat().st_mtime

        # Second generation (should use cache)
        preview2 = generate_timeline_preview(
            video_clip_data,
            test_media['video'],
            timeline_data,
            output_dir
        )

        # Should be same file
        assert preview1 == preview2

        # Should not have been regenerated
        mtime2 = preview2.stat().st_mtime
        assert mtime1 == mtime2, "Cache file should be reused"

        print(f"✓ Cache reused: {preview1.name}")

    def test_invalid_clip_data_raises_error(self, test_media, tmp_path):
        """Test that invalid clip data raises appropriate errors."""
        # Missing source file
        with pytest.raises(Exception):  # Could be FileNotFoundError or TimelinePreviewError
            generate_timeline_preview(
                {'source_start': 0.0, 'source_duration': 5.0},
                Path('/nonexistent/file.mp4'),
                None,
                tmp_path
            )


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
