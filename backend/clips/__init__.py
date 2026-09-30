"""Share clips as the desktop app reports them (ADR 039).

The Electron main process owns every clip -- the marks on the screen recording,
the high-quality captures and the exports (``frontend/electron/clipService.mjs``);
this package only keeps its newest view for the diagnostics checklist and for
agents. Read-only: nothing here can start, stop, export or delete a clip.
"""
