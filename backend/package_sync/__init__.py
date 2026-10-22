"""The backend's own Python packages: installed from ``backend/requirements.txt`` at start.

Owns bringing the interpreter that runs a checkout backend up to its ``requirements.txt`` before
the app imports anything, so a release that changes the packages never holds an update (operator
report 2026-10-21: "i never want to see this issue during update ever again").
"""
