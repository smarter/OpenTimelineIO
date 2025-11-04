"""
End-to-end tests for the shots dashboard using Playwright.

Tests the complete user workflow through the web interface.
"""

import time
from pathlib import Path

import pytest
from playwright.sync_api import Page, expect


pytestmark = pytest.mark.e2e


def test_dashboard_loads(page: Page, live_server: str) -> None:
    """Test that the dashboard loads successfully."""
    page.goto(live_server)

    # Check page title
    expect(page).to_have_title("Shots Dashboard - Timeline File Tracker")

    # Check main heading
    heading = page.locator("h1")
    expect(heading).to_have_text("🎬 Shots Dashboard")

    # Check that all main sections are present
    expect(page.locator(".controls")).to_be_visible()
    expect(page.locator(".stats")).to_be_visible()
    expect(page.locator(".file-lists")).to_be_visible()


def test_initial_state_is_empty(page: Page, live_server: str) -> None:
    """Test that initial state shows zero files."""
    page.goto(live_server)

    # Check all statistics are zero
    expect(page.locator("#stat-total")).to_have_text("0")
    expect(page.locator("#stat-new")).to_have_text("0")
    expect(page.locator("#stat-in-use")).to_have_text("0")
    expect(page.locator("#stat-removed")).to_have_text("0")

    # Check status shows Ready
    expect(page.locator("#status-text")).to_contain_text("Ready")


def test_scan_directory_workflow(
    page: Page,
    live_server: str,
    test_media_dir: Path
) -> None:
    """Test scanning a directory and seeing files appear."""
    page.goto(live_server)

    # Fill in directory path
    page.locator("#scan-directory").fill(str(test_media_dir))

    # Click scan button
    page.locator("#scan-btn").click()

    # Wait for scan to complete
    time.sleep(1)

    # Check statistics updated
    expect(page.locator("#stat-total")).to_have_text("5")
    expect(page.locator("#stat-new")).to_have_text("5")

    # Check files appear in "Not Yet Used" section
    new_files_section = page.locator("#files-new")
    expect(new_files_section.locator(".file-item")).to_have_count(5)

    # Verify specific file names are visible
    expect(new_files_section).to_contain_text("shot_001_anim_v001.mov")
    expect(new_files_section).to_contain_text("shot_002_anim_v001.mov")


def test_update_from_timeline_workflow(
    page: Page,
    live_server: str,
    test_media_dir: Path,
    test_timeline_v1: Path
) -> None:
    """Test updating from timeline and seeing state changes."""
    page.goto(live_server)

    # First scan directory
    page.locator("#scan-directory").fill(str(test_media_dir))
    page.locator("#scan-btn").click()
    time.sleep(1)

    # Then update from timeline
    page.locator("#timeline-path").fill(str(test_timeline_v1))
    page.locator("#update-btn").click()
    time.sleep(1)

    # Check statistics: 2 in use, 3 still new
    expect(page.locator("#stat-in-use")).to_have_text("2")
    expect(page.locator("#stat-new")).to_have_text("3")
    expect(page.locator("#stat-removed")).to_have_text("0")

    # Check files are in correct sections
    in_use_section = page.locator("#files-in-use")
    expect(in_use_section.locator(".file-item")).to_have_count(2)
    expect(in_use_section).to_contain_text("shot_001_anim_v001.mov")
    expect(in_use_section).to_contain_text("shot_002_anim_v001.mov")

    new_section = page.locator("#files-new")
    expect(new_section.locator(".file-item")).to_have_count(3)

    # Check transitions are shown
    transitions_list = page.locator("#transitions-list")
    expect(transitions_list.locator(".transition-item")).to_have_count(2)


def test_state_transitions_workflow(
    page: Page,
    live_server: str,
    test_media_dir: Path,
    test_timeline_v1: Path,
    test_timeline_v2: Path
) -> None:
    """Test complete state transition workflow: NEW → IN_USE → REMOVED → IN_USE."""
    page.goto(live_server)

    # Scan directory
    page.locator("#scan-directory").fill(str(test_media_dir))
    page.locator("#scan-btn").click()
    time.sleep(1)

    # Update with timeline v1 (shots 1 and 2 go to IN_USE)
    page.locator("#timeline-path").fill(str(test_timeline_v1))
    page.locator("#update-btn").click()
    time.sleep(1)

    expect(page.locator("#stat-in-use")).to_have_text("2")
    expect(page.locator("#stat-removed")).to_have_text("0")

    # Update with timeline v2 (shot 1 removed, shot 3 added)
    page.locator("#timeline-path").fill(str(test_timeline_v2))
    page.locator("#update-btn").click()
    time.sleep(1)

    # Shot 1 should be REMOVED, shot 2 still IN_USE, shot 3 now IN_USE
    expect(page.locator("#stat-in-use")).to_have_text("2")
    expect(page.locator("#stat-removed")).to_have_text("1")
    expect(page.locator("#stat-new")).to_have_text("2")

    # Check removed section
    removed_section = page.locator("#files-removed")
    expect(removed_section.locator(".file-item")).to_have_count(1)
    expect(removed_section).to_contain_text("shot_001_anim_v001.mov")

    # Check in use section
    in_use_section = page.locator("#files-in-use")
    expect(in_use_section).to_contain_text("shot_002_anim_v001.mov")
    expect(in_use_section).to_contain_text("shot_003_anim_v001.mov")

    # Update back to timeline v1 (shot 1 comes back)
    page.locator("#timeline-path").fill(str(test_timeline_v1))
    page.locator("#update-btn").click()
    time.sleep(1)

    # Shot 1 should be back IN_USE
    expect(page.locator("#stat-in-use")).to_have_text("2")
    expect(page.locator("#stat-removed")).to_have_text("1")  # shot 3 now removed

    in_use_section = page.locator("#files-in-use")
    expect(in_use_section).to_contain_text("shot_001_anim_v001.mov")


def test_reset_workflow(
    page: Page,
    live_server: str,
    test_media_dir: Path
) -> None:
    """Test reset functionality."""
    page.goto(live_server)

    # Scan directory
    page.locator("#scan-directory").fill(str(test_media_dir))
    page.locator("#scan-btn").click()
    time.sleep(1)

    expect(page.locator("#stat-total")).to_have_text("5")

    # Click reset button (will trigger confirm dialog)
    page.on("dialog", lambda dialog: dialog.accept())
    page.locator("#reset-btn").click()
    time.sleep(1)

    # Check everything is reset
    expect(page.locator("#stat-total")).to_have_text("0")
    expect(page.locator("#stat-new")).to_have_text("0")
    expect(page.locator("#stat-in-use")).to_have_text("0")
    expect(page.locator("#stat-removed")).to_have_text("0")

    # Check lists are empty
    expect(page.locator("#files-new")).to_contain_text("No files")


def test_error_handling_invalid_directory(
    page: Page,
    live_server: str
) -> None:
    """Test error handling for invalid directory."""
    page.goto(live_server)

    # Try to scan non-existent directory
    page.locator("#scan-directory").fill("/nonexistent/directory")
    page.locator("#scan-btn").click()
    time.sleep(1)

    # Check error is displayed in status bar
    status_bar = page.locator("#status-bar")
    expect(status_bar).to_have_class(lambda class_name: "error" in class_name)
    expect(page.locator("#status-text")).to_contain_text("Error")


def test_error_handling_invalid_timeline(
    page: Page,
    live_server: str,
    test_media_dir: Path
) -> None:
    """Test error handling for invalid timeline."""
    page.goto(live_server)

    # Scan directory first
    page.locator("#scan-directory").fill(str(test_media_dir))
    page.locator("#scan-btn").click()
    time.sleep(1)

    # Try to update with non-existent timeline
    page.locator("#timeline-path").fill("/nonexistent/timeline.otio")
    page.locator("#update-btn").click()
    time.sleep(1)

    # Check error is displayed
    expect(page.locator("#status-text")).to_contain_text("Error")


def test_auto_refresh_indicator(
    page: Page,
    live_server: str,
    test_media_dir: Path
) -> None:
    """Test auto-refresh indicator is visible."""
    page.goto(live_server)

    # Check auto-refresh indicator is present
    expect(page.locator(".auto-refresh-indicator")).to_be_visible()
    expect(page.locator(".pulse-dot")).to_be_visible()
    expect(page.locator(".auto-refresh-text")).to_contain_text("Auto-updating")


def test_multiple_updates_show_transitions(
    page: Page,
    live_server: str,
    test_media_dir: Path,
    test_timeline_v1: Path,
    test_timeline_v2: Path
) -> None:
    """Test that multiple updates accumulate in transitions list."""
    page.goto(live_server)

    # Scan directory
    page.locator("#scan-directory").fill(str(test_media_dir))
    page.locator("#scan-btn").click()
    time.sleep(1)

    # Update with timeline v1
    page.locator("#timeline-path").fill(str(test_timeline_v1))
    page.locator("#update-btn").click()
    time.sleep(1)

    # Update with timeline v2
    page.locator("#timeline-path").fill(str(test_timeline_v2))
    page.locator("#update-btn").click()
    time.sleep(1)

    # Check that transitions list has multiple entries
    transitions_list = page.locator("#transitions-list")
    transition_items = transitions_list.locator(".transition-item")

    # Should have multiple transitions visible
    expect(transition_items).to_have_count(lambda count: count >= 3)

    # Check for state badges
    expect(transitions_list.locator(".state-badge")).to_have_count(lambda count: count >= 3)


def test_keyboard_navigation(
    page: Page,
    live_server: str,
    test_media_dir: Path
) -> None:
    """Test that Enter key works in input fields."""
    page.goto(live_server)

    # Fill directory and press Enter
    scan_input = page.locator("#scan-directory")
    scan_input.fill(str(test_media_dir))
    scan_input.press("Enter")
    time.sleep(1)

    # Should have scanned
    expect(page.locator("#stat-total")).to_have_text("5")


@pytest.mark.slow
def test_persistence_across_sessions(
    page: Page,
    live_server: str,
    test_media_dir: Path,
    test_timeline_v1: Path
) -> None:
    """Test that data persists across page reloads."""
    page.goto(live_server)

    # Scan and update
    page.locator("#scan-directory").fill(str(test_media_dir))
    page.locator("#scan-btn").click()
    time.sleep(1)

    page.locator("#timeline-path").fill(str(test_timeline_v1))
    page.locator("#update-btn").click()
    time.sleep(1)

    # Get current stats
    total_before = page.locator("#stat-total").inner_text()
    in_use_before = page.locator("#stat-in-use").inner_text()

    # Reload page
    page.reload()
    time.sleep(1)

    # Check stats are still the same
    expect(page.locator("#stat-total")).to_have_text(total_before)
    expect(page.locator("#stat-in-use")).to_have_text(in_use_before)
