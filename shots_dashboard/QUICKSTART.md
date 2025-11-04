# Quick Start Guide

This guide will help you get the Shots Dashboard up and running quickly.

## Prerequisites

- Python 3.10 or higher
- uv (recommended) or pip

## Installation

### Option 1: Using uv (Recommended)

```bash
# Install uv if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh

# From the OpenTimelineIO root directory
cd OpenTimelineIO

# Create virtual environment
uv venv

# Activate virtual environment
source .venv/bin/activate  # On Unix/macOS
# or
.venv\Scripts\activate  # On Windows

# Install all dependencies (including OpenTimelineIO from PyPI)
uv pip install -r shots_dashboard_requirements.txt
```

### Option 2: Using pip

```bash
# From the OpenTimelineIO root directory
cd OpenTimelineIO

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate  # On Unix/macOS

# Install dependencies
pip install -r shots_dashboard_requirements.txt
```

## Quick Test

Run the core tests to verify everything is working:

```bash
python test_dashboard_core.py
```

You should see:
```
✅ All core tests passed!
```

## Running the Dashboard

### Start the Web Server

```bash
# From the OpenTimelineIO root directory
python -m shots_dashboard
```

Or alternatively:
```bash
cd shots_dashboard
python app.py
```

The dashboard will be available at: http://localhost:5000

### Using the Dashboard

1. **Scan Your Media Directory**
   - Enter the full path to your media files directory
   - Click "Scan"
   - All files will appear in the "Not Yet Used" section

2. **Update from Timeline**
   - Enter the path to your OTIO timeline file
   - Click "Update"
   - Files used in the timeline move to "In Use"
   - Files removed from timeline move to "Removed"

3. **Track Changes**
   - Re-scan and update as your timeline evolves
   - The "Recent Changes" section shows state transitions
   - Statistics update in real-time

## Example Workflow

```bash
# 1. Start the dashboard
python -m shots_dashboard

# In your browser:
# - Navigate to http://localhost:5000
# - Scan directory: /path/to/your/media/files
# - Update timeline: /path/to/your/timeline.otio

# 2. Or use programmatically
python shots_dashboard/example.py
```

## Example Timeline File

If you don't have a timeline file yet, you can create one:

```python
import opentimelineio as otio

timeline = otio.schema.Timeline(name="my_timeline")
track = otio.schema.Track(name="video")

clip = otio.schema.Clip(
    name="shot_001.mov",  # This name should match your media file
    source_range=otio.opentime.TimeRange(
        start_time=otio.opentime.RationalTime(0, 24),
        duration=otio.opentime.RationalTime(100, 24)
    )
)

track.append(clip)
timeline.tracks.append(track)
otio.adapters.write_to_file(timeline, "timeline.otio")
```

## Troubleshooting

### "Module not found" errors

Make sure you've installed the dependencies:
```bash
uv pip install -r shots_dashboard_requirements.txt
```

### Port 5000 already in use

Change the port in `app.py`:
```python
app.run(debug=True, host='0.0.0.0', port=5001)
```

### Files not matching

The dashboard matches files by filename. Make sure:
- Clip names in your timeline match your media file names
- Or media reference URLs in clips point to your files

## Development

### Run Tests (requires pytest)

```bash
# Install test dependencies
uv pip install -r shots_dashboard_requirements-dev.txt

# Run all tests
pytest tests/test_shots_dashboard_*.py -v

# Run with coverage
pytest tests/test_shots_dashboard_*.py --cov=shots_dashboard
```

### Type Check (requires basedpyright)

```bash
# Install dev dependencies (includes basedpyright)
uv pip install -r shots_dashboard_requirements-dev.txt

# Run type checker
basedpyright shots_dashboard
```

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Check out [example.py](example.py) for programmatic usage
- Explore the API endpoints in [app.py](app.py)
- Customize the UI in [templates/](templates/) and [static/](static/)

## Getting Help

If you encounter issues:
1. Check the console output for error messages
2. Verify your file paths are correct and accessible
3. Ensure OpenTimelineIO can read your timeline format
4. Open an issue in the OpenTimelineIO repository
