#!/usr/bin/env python3
"""Story Status — thin launcher.

Delegates to ``story_status.cli.main`` so the package is always the
authoritative source of the CLI logic.

Usage:
    python story_status.py <JIRA_ID>

Example:
    python story_status.py AI-1
    python story_status.py SCRUM-9
"""

from story_status.cli import main

if __name__ == "__main__":
    main()

