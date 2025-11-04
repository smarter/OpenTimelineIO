"""
Entry point for running shots_dashboard as a module.

Usage:
    python -m shots_dashboard              # Normal mode
    python -m shots_dashboard --demo       # Demo mode with sample data
    python -m shots_dashboard --port 8000  # Custom port
"""

from shots_dashboard.app import main

if __name__ == '__main__':
    main()
