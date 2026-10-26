"""The trading screen recording as the desktop app reports it (ADR 035, ADR 067).

The Electron main process records every monitor and owns the files
(``frontend/electron/screenRecorder.mjs``) -- only when ``NOVA_SCREEN_RECORD``
is on; it is paused by default (ADR 067) and then reports ``state: "paused"``.
This package only keeps its newest report for the diagnostics checklist and
for agents. Read-only: nothing here can start, stop or pause the recording.
"""
