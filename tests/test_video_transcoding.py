"""
Tests for video transcoding and preview functionality.

Tests the video_transcoder module and preview API endpoint.
"""

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
import subprocess

from shots_dashboard.video_transcoder import (
    is_web_compatible,
    check_ffmpeg_available,
    TranscodingError
)


class TestVideoTranscoder(unittest.TestCase):
    """Tests for video transcoding functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_is_web_compatible_mp4(self):
        """Test that MP4 files are recognized as web-compatible."""
        test_file = self.base_dir / "test.mp4"
        test_file.touch()

        self.assertTrue(is_web_compatible(test_file))

    def test_is_web_compatible_webm(self):
        """Test that WebM files are recognized as web-compatible."""
        test_file = self.base_dir / "test.webm"
        test_file.touch()

        self.assertTrue(is_web_compatible(test_file))

    def test_is_web_compatible_ogg(self):
        """Test that OGG files are recognized as web-compatible."""
        test_file = self.base_dir / "test.ogg"
        test_file.touch()

        self.assertTrue(is_web_compatible(test_file))

    def test_is_not_web_compatible_mov(self):
        """Test that MOV files are not recognized as web-compatible."""
        test_file = self.base_dir / "test.mov"
        test_file.touch()

        self.assertFalse(is_web_compatible(test_file))

    def test_is_not_web_compatible_mxf(self):
        """Test that MXF files are not recognized as web-compatible."""
        test_file = self.base_dir / "test.mxf"
        test_file.touch()

        self.assertFalse(is_web_compatible(test_file))

    @patch('subprocess.run')
    def test_check_ffmpeg_available_success(self, mock_run):
        """Test ffmpeg availability check when ffmpeg is available."""
        mock_run.return_value = MagicMock(returncode=0)

        result = check_ffmpeg_available()

        self.assertTrue(result)
        mock_run.assert_called_once()

    @patch('subprocess.run')
    def test_check_ffmpeg_available_not_found(self, mock_run):
        """Test ffmpeg availability check when ffmpeg is not found."""
        mock_run.side_effect = FileNotFoundError()

        result = check_ffmpeg_available()

        self.assertFalse(result)

    @patch('subprocess.run')
    def test_check_ffmpeg_available_error(self, mock_run):
        """Test ffmpeg availability check when ffmpeg returns error."""
        mock_run.side_effect = subprocess.CalledProcessError(1, 'ffmpeg')

        result = check_ffmpeg_available()

        self.assertFalse(result)


class TestPreviewAPI(unittest.TestCase):
    """Tests for video preview API endpoint."""

    def setUp(self):
        """Set up test fixtures."""
        from shots_dashboard.app import create_app

        self.temp_dir = TemporaryDirectory()
        self.base_dir = Path(self.temp_dir.name)
        self.media_dir = self.base_dir / "media"
        self.media_dir.mkdir()
        self.db_path = self.base_dir / "test.json"

        # Create Flask app
        self.app = create_app(self.db_path)
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()

        # Create and scan test files
        self.test_file = self.media_dir / "test.mp4"
        self.test_file.write_bytes(b'fake video data')

        self.client.post('/api/scan', json={'directory': str(self.media_dir)})

    def tearDown(self):
        """Clean up."""
        self.temp_dir.cleanup()

    def test_preview_endpoint_exists(self):
        """Test that preview endpoint is registered."""
        response = self.client.get('/api/preview/nonexistent.mp4')

        # Should return 404, not 405 (method not allowed)
        self.assertIn(response.status_code, [404, 500])

    def test_preview_file_not_found(self):
        """Test preview endpoint with non-existent file."""
        response = self.client.get('/api/preview/nonexistent.mp4')
        data = response.get_json()

        self.assertEqual(response.status_code, 404)
        self.assertFalse(data['success'])
        self.assertIn('not found', data['error'].lower())

    def test_preview_web_compatible_file(self):
        """Test preview endpoint with web-compatible file."""
        response = self.client.get('/api/preview/test.mp4')

        # Should return video data or transcoding response
        self.assertIn(response.status_code, [200, 503])

        if response.status_code == 200:
            # Check content type is video
            self.assertIn('video/', response.content_type)


if __name__ == '__main__':
    unittest.main()
