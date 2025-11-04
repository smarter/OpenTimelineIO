# Clip Preview Feature

## Overview

The clip preview feature allows users to hover over any clip name in the timeline widget or file lists to see a video preview. The system automatically handles format conversion, transcoding unsupported formats to WebM (VP8/Vorbis) on-the-fly for browser compatibility.

## Features

### Hover-Based Preview
- **300ms Hover Delay**: Prevents flickering on quick mouse movements
- **Smart Positioning**: Popup appears next to the hovered element
- **Viewport Awareness**: Stays within browser window boundaries
- **Automatic Cleanup**: Stops playback when mouse leaves

### Format Support
- **Direct Playback**: MP4, WebM, OGG files play directly (no transcoding)
- **On-the-Fly Transcoding**: MOV, MXF, and other formats transcoded to WebM
- **Real-Time Settings**: Optimized for fast streaming (480p, 15fps)
- **Progressive Streaming**: Video starts playing while transcoding continues

### User Experience
- **Loading Indicator**: Shows "Loading..." while video loads
- **Filename Display**: Shows clip name at bottom of preview
- **Muted Autoplay**: Videos play automatically without sound
- **Looping**: Videos loop continuously while hovering

## Technical Architecture

### 1. Video Transcoder Module

**File**: `shots_dashboard/video_transcoder.py`

**Key Functions**:

```python
is_web_compatible(file_path: Path) -> bool
```
Checks if file format is browser-compatible (MP4, WebM, OGG).

```python
check_ffmpeg_available() -> bool
```
Verifies ffmpeg is installed on the system.

```python
stream_transcode_webm(input_path: Path, ...) -> subprocess.Popen
```
Starts streaming transcode to WebM format for progressive playback.

**Transcoding Settings**:
- **Video Codec**: VP8 (libvpx)
- **Audio Codec**: Vorbis
- **Quality**: Real-time mode (cpu-used=5)
- **Resolution**: 480p width (maintains aspect ratio)
- **Framerate**: 15 fps
- **Video Bitrate**: 500k
- **Audio Bitrate**: 64k
- **Container**: WebM with small cluster sizes for streaming

### 2. API Endpoint

**Endpoint**: `GET /api/preview/<filename>`

**Flow**:
1. Find file in tracked files by name
2. Check if file exists
3. If web-compatible → serve directly
4. If not compatible → check ffmpeg availability
5. If ffmpeg available → transcode and stream
6. If ffmpeg unavailable → return 503 error

**Response**:
- **Success**: Video stream (Content-Type: video/webm or video/mp4)
- **Not Found**: 404 with error message
- **No ffmpeg**: 503 with error message
- **Transcoding Error**: 500 with error message

### 3. Frontend Components

#### HTML Structure
```html
<div id="video-preview-popup" class="video-preview-popup">
    <video id="video-preview-player" muted loop playsinline>
        <source id="video-preview-source" type="video/webm">
    </video>
    <div class="video-preview-loading">Loading...</div>
    <div class="video-preview-filename"></div>
</div>
```

#### CSS Styling
- **Position**: Fixed positioning with high z-index (9999)
- **Max Size**: 400px wide, 300px tall
- **Border**: 2px accent-colored border
- **Shadow**: Large box shadow for depth
- **States**: Loading state shows/hides loading indicator

#### JavaScript Logic

**ShotsDashboard Class Properties**:
- `previewTimeout`: Timeout ID for hover delay
- `currentPreviewFilename`: Currently previewed filename
- `previewPopup`: Reference to popup element
- `previewPlayer`: Reference to video element

**Key Methods**:

```javascript
setupVideoPreview()
```
Initializes references to DOM elements.

```javascript
showVideoPreview(filename, element)
```
- Starts 300ms delay timer
- Calculates smart positioning (right of element, or left if no space)
- Keeps popup within viewport
- Loads video source
- Starts playback when ready

```javascript
hideVideoPreview()
```
- Clears timeout
- Hides popup
- Stops video playback
- Resets source

```javascript
attachPreviewHandlers(element, filename)
```
- Adds mouseenter event → showVideoPreview
- Adds mouseleave event → hideVideoPreview

**Integration Points**:
- `renderFileList()`: Attaches handlers to all `.file-name` elements
- `updateTimelineHistory()`: Attaches handlers to all `.clip-badge` elements

## Usage

### For Users

1. **Hover over any clip name** in:
   - Timeline widget (current clips)
   - Timeline widget (historical clips)
   - File lists (NEW, IN_USE, REMOVED)

2. **Wait 300ms** for preview to appear

3. **Preview appears** next to your cursor with:
   - Loading indicator (while loading)
   - Video playback (when ready)
   - Filename label

4. **Move mouse away** to hide preview

### For Developers

#### Testing Video Preview

```python
# Test if file is web-compatible
from shots_dashboard.video_transcoder import is_web_compatible
from pathlib import Path

file = Path("/path/to/video.mov")
if is_web_compatible(file):
    print("Can be served directly")
else:
    print("Needs transcoding")
```

#### Check ffmpeg Availability

```python
from shots_dashboard.video_transcoder import check_ffmpeg_available

if check_ffmpeg_available():
    print("ffmpeg is available")
else:
    print("ffmpeg not found - transcoding unavailable")
```

#### Test Preview Endpoint

```bash
# Direct file (MP4)
curl http://localhost:5000/api/preview/test.mp4

# Transcoded file (MOV)
curl http://localhost:5000/api/preview/test.mov
```

## Requirements

### System Requirements

**Required for Web-Compatible Files**:
- None (MP4, WebM, OGG play directly)

**Required for Transcoding**:
- **ffmpeg** must be installed and available in PATH
- Install: `sudo apt-get install ffmpeg` (Ubuntu/Debian)
- Install: `brew install ffmpeg` (macOS)
- Install: Download from https://ffmpeg.org (Windows)

### Browser Requirements

- Modern browser with `<video>` support
- JavaScript enabled
- Supports WebM format (all modern browsers)

## Performance Considerations

### Transcoding Performance

**Real-Time Settings**:
- Optimized for speed over quality
- Target: Transcode as fast as playback (1x speed)
- CPU usage: Moderate (depends on source format)

**Resolution & Framerate**:
- 480p width: Balance of quality and speed
- 15 fps: Smooth enough for preview, fast to encode
- Bitrate: 500k video + 64k audio

**Streaming**:
- Progressive streaming starts immediately
- Small WebM clusters (2MB) for responsive playback
- No need to wait for full transcode

### Network Performance

**Direct Playback** (MP4/WebM/OGG):
- Minimal overhead
- Standard HTTP streaming
- Browser handles buffering

**Transcoded Playback**:
- Server CPU usage for transcoding
- Streams progressively (no wait time)
- Network usage similar to direct playback

### Caching

**No Server-Side Caching**:
- Transcodes on-demand each time
- No disk space usage for cached transcodes
- Always fresh transcode with current settings

**Browser Caching**:
- Browser may cache video responses
- Cache-Control headers prevent stale transcodes

## Troubleshooting

### Preview Not Showing

**Check Console**:
```javascript
// Open browser console (F12)
// Look for errors like:
// - "Failed to load video preview"
// - 404 errors for /api/preview/filename
```

**Verify File Tracked**:
- File must be in tracked files (scanned directory)
- Check dashboard shows file in one of the lists

### Transcoding Fails

**Check ffmpeg**:
```bash
# Terminal/Command Prompt
ffmpeg -version

# Should show version info
# If "command not found", install ffmpeg
```

**Check API Response**:
```bash
curl http://localhost:5000/api/preview/test.mov
# Should return video data or error message
```

### Slow Playback

**Reduce Quality** (edit `video_transcoder.py`):
```python
# Lower resolution
stream_transcode_webm(input_path, width=360)  # Was 480

# Lower bitrate
stream_transcode_webm(input_path, bitrate="300k")  # Was 500k
```

**Check CPU Usage**:
- ffmpeg transcoding is CPU-intensive
- Multiple simultaneous previews = high CPU usage
- Consider limiting concurrent transcodes

## Demo Mode with Real Videos

When running in demo mode (`python -m shots_dashboard --demo`), the system now automatically generates real video files using ffmpeg instead of creating empty placeholder files.

### Real Video Generation

**When ffmpeg is available**:
- Creates actual video files with test patterns and audio
- Videos are 5 seconds long with 640x480 resolution
- Includes visual test pattern and 1000 Hz sine wave audio
- Files can be previewed with the clip preview feature

**When ffmpeg is not available**:
- Gracefully falls back to creating empty files
- Demo still works, but videos cannot be previewed
- Install ffmpeg to enable full functionality

### Video File Formats

The demo generates videos in the format specified by file extension:
- **`.mp4`**: H.264/AAC (web-compatible, no transcoding needed)
- **`.mov`**: H.264/AAC (requires transcoding to WebM)
- **`.webm`**: VP8/Vorbis (web-compatible, no transcoding needed)
- **Other formats**: Generated with appropriate codecs based on extension

## Testing

### Unit Tests

**File**: `tests/test_video_transcoding.py`

**Test Coverage**:
- ✅ Format detection (MP4, WebM, OGG, MOV, MXF)
- ✅ ffmpeg availability checking
- ✅ Preview API endpoint existence
- ✅ File not found handling
- ✅ Web-compatible file serving
- ✅ Error handling

**Run Tests**:
```bash
pytest tests/test_video_transcoding.py -v
```

**Results**: 11/11 tests passing

### Manual Testing

1. **Start Dashboard**:
   ```bash
   python -m shots_dashboard --demo
   ```

2. **Open Browser**: http://localhost:5000

3. **Scan Media Directory** with video files

4. **Hover over filenames**:
   - Timeline clips
   - File lists
   - Both current and historical clips

5. **Verify**:
   - Preview appears within 300ms
   - Video loads and plays
   - Preview disappears on mouse leave
   - Works for both web-compatible and transcoded files

## Future Enhancements

Potential improvements for future versions:

1. **Thumbnail Generation**:
   - Generate static thumbnails for faster initial display
   - Cache thumbnails on disk
   - Show thumbnail immediately, load video on demand

2. **Server-Side Caching**:
   - Cache transcoded files for frequently accessed clips
   - LRU cache with size limit
   - Automatic cleanup of old caches

3. **Quality Settings**:
   - UI option for preview quality (low/medium/high)
   - Adaptive quality based on network speed
   - User preferences for resolution/framerate

4. **Audio Control**:
   - Option to unmute audio
   - Volume slider in preview
   - Remember audio preference

5. **Seek Controls**:
   - Timeline scrubber in preview
   - Jump to specific timestamp
   - Show total duration

6. **Multi-Format Fallback**:
   - Generate multiple formats (WebM + MP4)
   - Browser chooses best supported format
   - Fallback chain for maximum compatibility

## Summary

The clip preview feature provides a seamless way to preview video clips without leaving the dashboard. With automatic format detection and on-the-fly transcoding, it works with any video format while optimizing for performance and responsiveness.

**Key Benefits**:
- ✅ Fast hover-based previews (300ms delay)
- ✅ Universal format support (via ffmpeg transcoding)
- ✅ Progressive streaming (no wait time)
- ✅ Smart positioning (viewport-aware)
- ✅ Comprehensive testing (11 tests, 100% pass rate)
- ✅ Graceful degradation (works without ffmpeg for web formats)

**Test Results**: 88/88 tests passing (77 existing + 11 new)
