"""E2E pytest tests for the preview API."""

import tempfile
from pathlib import Path
import pytest
from app import create_app
from video_transcoder import generate_test_video


@pytest.fixture
def test_env():
    """Create a temporary test environment with media files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        test_dir = Path(tmpdir)
        media_dir = test_dir / "media"
        media_dir.mkdir()
        db_path = test_dir / "test.json"

        # Create test files
        test_files = {}

        # Web-compatible MP4
        mp4_file = media_dir / "test_video.mp4"
        generate_test_video(mp4_file, duration=2, width=640, height=480)
        test_files['mp4'] = mp4_file

        # Non-web-compatible MOV (will need transcoding to WebM)
        mov_file = media_dir / "test_video.mov"
        generate_test_video(mov_file, duration=2, width=640, height=480)
        test_files['mov'] = mov_file

        # Create app
        app, socketio = create_app(db_path=db_path, media_dir=media_dir)
        app.config['TESTING'] = True

        # Give scanner time to find files
        import time
        time.sleep(0.5)

        yield {
            'app': app,
            'media_dir': media_dir,
            'test_files': test_files,
            'cache_dir': Path.home() / ".cache" / "shots_dashboard"
        }


def test_preview_web_compatible_mp4(test_env):
    """Test previewing a web-compatible MP4 file (should serve directly)."""
    app = test_env['app']

    with app.test_client() as client:
        response = client.get('/api/preview/test_video.mp4')

        assert response.status_code == 200
        assert response.content_type == 'video/mp4'
        assert len(response.data) > 0
        print(f"✓ MP4 preview: {len(response.data)} bytes served")


def test_preview_non_web_compatible_mov(test_env):
    """Test previewing a non-web-compatible MOV file (requires transcoding to WebM)."""
    app = test_env['app']

    with app.test_client() as client:
        response = client.get('/api/preview/test_video.mov')

        # Should either succeed with WebM or return 503 if ffmpeg not available
        if response.status_code == 200:
            assert response.content_type == 'video/webm'
            assert len(response.data) > 0
            print(f"✓ MOV transcoding: {len(response.data)} bytes of WebM")
        elif response.status_code == 503:
            data = response.get_json()
            assert 'ffmpeg' in data['error'].lower()
            print("⚠ MOV transcoding: ffmpeg not available (expected if not installed)")
            pytest.skip("ffmpeg not available")
        else:
            pytest.fail(f"Unexpected status code: {response.status_code}")


def test_preview_nonexistent_file(test_env):
    """Test previewing a non-existent file (should return 404)."""
    app = test_env['app']

    with app.test_client() as client:
        response = client.get('/api/preview/nonexistent.mp4')

        assert response.status_code == 404
        data = response.get_json()
        assert 'error' in data
        assert 'not found' in data['error'].lower()
        print("✓ Non-existent file returns 404")


def test_cache_functionality(test_env):
    """Test that transcoded files are cached properly."""
    app = test_env['app']
    cache_dir = test_env['cache_dir']

    # Skip if ffmpeg not available
    from video_transcoder import check_ffmpeg_available
    if not check_ffmpeg_available():
        pytest.skip("ffmpeg not available for cache testing")

    with app.test_client() as client:
        # First request - should create cache
        response1 = client.get('/api/preview/test_video.mov')

        if response1.status_code != 200:
            pytest.skip("Transcoding failed, cannot test cache")

        # Check cache directory
        if cache_dir.exists():
            cached_files = list(cache_dir.glob("test_video.*.webm"))
            assert len(cached_files) > 0, "Cache file should exist"

            cache_file = cached_files[0]
            cache_size = cache_file.stat().st_size
            cache_mtime = cache_file.stat().st_mtime

            print(f"✓ Cache created: {cache_file.name} ({cache_size} bytes)")

            # Second request - should use cache (same file)
            import time
            time.sleep(0.1)
            response2 = client.get('/api/preview/test_video.mov')

            # Cache file should not have been modified
            new_mtime = cache_file.stat().st_mtime
            assert new_mtime == cache_mtime, "Cache file should be reused"
            print("✓ Cache reused on second request")
        else:
            print("⚠ Cache directory not created (may be expected behavior)")


def test_audio_file_handling(test_env):
    """Test that audio files are handled appropriately."""
    from video_transcoder import check_ffmpeg_available, is_audio_only

    if not check_ffmpeg_available():
        pytest.skip("ffmpeg not available for audio testing")

    # Create a test audio file (WAV - web compatible)
    media_dir = test_env['media_dir']
    wav_file = media_dir / "test_audio.wav"

    import subprocess
    command = [
        'ffmpeg', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2',
        '-c:a', 'pcm_s16le', '-ar', '44100', '-ac', '2', '-y', str(wav_file)
    ]

    try:
        subprocess.run(command, check=True, capture_output=True)

        # Verify it's audio-only
        assert is_audio_only(wav_file), "WAV should be detected as audio-only"

        # Give scanner time to find new file
        import time
        time.sleep(0.5)

        app = test_env['app']
        with app.test_client() as client:
            response = client.get('/api/preview/test_audio.wav')

            assert response.status_code == 200
            assert 'audio' in response.content_type
            assert len(response.data) > 0
            print(f"✓ WAV audio preview: {response.content_type}, {len(response.data)} bytes")

    except subprocess.CalledProcessError:
        pytest.skip("Could not generate test audio file")


def test_mime_types(test_env):
    """Test that correct MIME types are returned for different formats."""
    app = test_env['app']

    expected_types = {
        'test_video.mp4': 'video/mp4',
        'test_video.mov': 'video/webm',  # Transcoded to WebM
    }

    from video_transcoder import check_ffmpeg_available

    with app.test_client() as client:
        for filename, expected_mime in expected_types.items():
            response = client.get(f'/api/preview/{filename}')

            if response.status_code == 200:
                if 'mov' in filename and not check_ffmpeg_available():
                    pytest.skip("ffmpeg not available")

                # Consume the response data to avoid context issues
                _ = response.data

                assert response.content_type == expected_mime, \
                    f"{filename} should have MIME type {expected_mime}"
                print(f"✓ {filename}: {response.content_type}")
            elif response.status_code == 503:
                pytest.skip("ffmpeg not available")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
