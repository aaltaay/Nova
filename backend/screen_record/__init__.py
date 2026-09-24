"""The trading screen recording as the desktop app reports it (ADR 035).

The Electron main process records every monitor and owns the files
(``frontend/electron/screenRecorder.mjs``); this package only keeps its newest
report for the diagnostics checklist and for agents. Read-only: nothing here
can start, stop or pause the recording.
"""
