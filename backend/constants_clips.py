"""Share clips (ADR 039): the desktop app records them; the backend keeps its view for agents and the checklist.

Operator ask 2026-09-29: a red button that records a clip of a Trader tab to share,
cut from the always-on screen recording (ADR 035), with High quality on demand. The
Electron main process owns the clips and their files (frontend/electron/clipService.mjs)
and posts its view here every ``CLIPS_REPORT_SEC``; nothing on the backend starts,
stops or exports a clip.
"""
CLIPS_SCHEMA_VERSION = 1
CLIPS_REPORT_MAX_BODY_BYTES = 256 * 1024
CLIPS_REPORT_SEC = 10.0                  # mirrors clipPlan.mjs CLIP_REPORT_MS
CLIPS_STALE_SEC = 35.0                   # three missed reports: no desktop app is reporting clips
CLIPS_MAX_OPEN = 20
CLIPS_MAX_ROWS = 50                      # the bridge sends at most 50 of the list
CLIPS_DIR_SOURCES = ("env", "data_drive", "fallback")
CLIPS_OPEN_STATES = ("ok", "hidden", "hq_lost", "no_picture")
CLIPS_DIR_ENV = "NOVA_CLIPS_DIR"         # read by the desktop app, named here for the fix text
