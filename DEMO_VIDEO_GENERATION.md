# Demo Mode Video Generation

## Overview

When running the shots dashboard in demo mode (`python -m shots_dashboard --demo`), the system now automatically generates real video files with synthetic content instead of creating empty placeholder files.

## Features

### Automatic Video Generation

**When ffmpeg is available:**
- Creates actual video files with visual test patterns
- Includes 1000 Hz sine wave audio track
- Videos are 5 seconds long with 640x480 resolution at 30 fps
- Files can be previewed using the hover-based clip preview feature

**When ffmpeg is not available:**
- Gracefully falls back to creating empty placeholder files
- Demo functionality continues to work normally
- Video previews will not work (requires actual video content)

### Supported Formats

The demo generates videos in the format specified by the file extension:

| Format | Video Codec | Audio Codec | Browser Playback | Notes |
|--------|-------------|-------------|------------------|-------|
| `.mp4` | H.264 | AAC | Direct | No transcoding needed |
| `.webm` | VP8 | Vorbis | Direct | No transcoding needed |
| `.mov` | H.264 | AAC | Transcoded | Converted to WebM for browser |
| `.avi` | H.264 | AAC | Transcoded | Converted to WebM for browser |
| `.mkv` | VP8 | Vorbis | Transcoded | Converted to WebM for browser |

## Codec Detection

The system uses `ffprobe` to detect the actual video and audio codecs in files, not just the file extension. This ensures accurate browser compatibility detection.

### Web-Compatible Codecs

**Video:**
- H.264 (h264)
- VP8 (vp8)
- VP9 (vp9)
- AV1 (av1)
- Theora (theora)

**Audio:**
- AAC (aac)
- MP3 (mp3)
- Vorbis (vorbis)
- Opus (opus)
- FLAC (flac)

### Example: Why MOV Files Need Transcoding

Even if a `.mov` file contains H.264/AAC (web-compatible codecs), the MOV container format itself is not universally supported by browsers. Therefore, MOV files are transcoded to WebM (VP8/Vorbis) for reliable browser playback.

## Installation

### Installing ffmpeg

**Ubuntu/Debian:**
```bash
sudo apt-get install ffmpeg
```

**macOS:**
```bash
brew install ffmpeg
```

**Local installation (no sudo):**
```bash
mkdir -p ~/.local/bin
cd ~/.local/bin
wget https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz
tar -xf ffmpeg-release-amd64-static.tar.xz --strip-components=1
rm ffmpeg-release-amd64-static.tar.xz
export PATH=$HOME/.local/bin:$PATH
```

The shots dashboard automatically adds `~/.local/bin` to PATH when checking for ffmpeg.

## Usage in Demo Mode

```bash
# Start demo mode
python -m shots_dashboard --demo

# The demo will:
# 1. Start the web server
# 2. Wait for you to open http://localhost:5000
# 3. Press ENTER to start scenario execution
# 4. Generate real video files as part of the scenario
# 5. Update the timeline and track file states
# 6. All changes visible in real-time via auto-refresh
```

## Implementation Details

### Video Generation Function

**File:** `shots_dashboard/video_transcoder.py`

```python
def generate_test_video(
    output_path: Path,
    duration: int = 5,
    width: int = 640,
    height: int = 480,
    fps: int = 30,
    pattern: str = "testsrc"
) -> None:
    """Generate a test video file with synthetic content."""
```

**Test Pattern Options:**
- `testsrc`: Colorful test pattern with moving objects
- `smptebars`: SMPTE color bars
- `rgbtestsrc`: RGB test pattern

### Codec Detection Function

**File:** `shots_dashboard/video_transcoder.py`

```python
def get_video_codec_info(file_path: Path) -> dict[str, str]:
    """
    Get video and audio codec information using ffprobe.

    Returns:
        Dictionary with 'video_codec' and 'audio_codec' keys
    """
```

### File Creation in Scenarios

**File:** `shots_dashboard/scenario_interpreters.py`

The `FileSystemInterpreter._create_file()` method automatically detects video/audio file extensions and generates appropriate content:

```python
def _create_file(self, action: CreateFile) -> None:
    """Actually create a file."""
    video_extensions = {'.mp4', '.mov', '.webm', '.avi', '.mkv', '.m4v', '.mxf'}

    if ext in video_extensions and check_ffmpeg_available():
        generate_test_video(action.path, duration=5)
    else:
        action.path.touch()  # Fallback to empty file
```

## Testing

### Unit Tests

All existing tests continue to pass with the new video generation:

```bash
# Run video transcoding tests
pytest tests/test_video_transcoding.py -v

# Run demo mode tests
pytest tests/test_demo_mode.py -v

# Run scenario integration tests
pytest tests/test_scenario_integration.py -v
```

**Results:** 19/19 tests passing

### Manual Testing

1. **Generate a test video:**
   ```python
   from pathlib import Path
   from shots_dashboard.video_transcoder import generate_test_video

   generate_test_video(Path("test.mp4"), duration=5)
   ```

2. **Check codec compatibility:**
   ```python
   from pathlib import Path
   from shots_dashboard.video_transcoder import get_video_codec_info, is_web_compatible

   info = get_video_codec_info(Path("test.mp4"))
   print(f"Video codec: {info['video_codec']}")
   print(f"Audio codec: {info['audio_codec']}")
   print(f"Web-compatible: {is_web_compatible(Path('test.mp4'))}")
   ```

## Performance Considerations

### Video Generation Speed

- Generating a 5-second test video typically takes 1-3 seconds
- Generation happens sequentially during demo scenario execution
- Videos are generated once and reused if the demo is run multiple times

### File Sizes

Typical file sizes for 5-second test videos:
- **MP4 (H.264/AAC):** ~120 KB
- **WebM (VP8/Vorbis):** ~150 KB
- **MOV (H.264/AAC):** ~120 KB

## Troubleshooting

### Videos Not Being Generated

**Check ffmpeg installation:**
```bash
ffmpeg -version
```

**Check PATH:**
```bash
echo $PATH | tr ':' '\n' | grep -i local/bin
```

**Verify Python can find ffmpeg:**
```python
from shots_dashboard.video_transcoder import check_ffmpeg_available
print(check_ffmpeg_available())  # Should print: True
```

### Empty Files Being Created

If files are created but have 0 bytes:
1. ffmpeg is not available or not in PATH
2. ffmpeg execution failed (check error logs)
3. Disk space issue (unlikely for test videos)

The system will log which path it took:
- "Created video file: ..." = Video content generated
- "Created file: ..." = Empty file (ffmpeg unavailable or failed)

## Benefits

### For Demo Mode
- **Realistic demonstration:** Shows actual video previews working
- **End-to-end testing:** Verifies entire pipeline from file creation to browser playback
- **Better UX:** Users can immediately see and interact with video content

### For Development
- **Automated testing:** No need to manually create test videos
- **Consistent results:** Generated videos have known properties
- **CI/CD friendly:** Works in environments where ffmpeg is installed

### For Users
- **Quick start:** Demo works out of the box with ffmpeg installed
- **Visual feedback:** Hover previews actually show video content
- **Codec testing:** Verify transcoding works with different formats

## Summary

The demo mode video generation feature enhances the shots dashboard demo experience by creating actual video content instead of placeholder files. This allows users to:

- ✅ See the clip preview feature working with real video
- ✅ Verify on-the-fly transcoding for different formats
- ✅ Test the complete workflow from file creation to browser playback
- ✅ Experience the dashboard as it would be used in production

With intelligent codec detection and graceful fallback, the system works reliably whether ffmpeg is available or not.
