"""Playwright configuration for E2E tests."""

import os

# Use headless mode by default, unless HEADED env var is set
os.environ.setdefault("PLAYWRIGHT_HEADLESS", "1")
