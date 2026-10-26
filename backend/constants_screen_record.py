"""The trading screen recording (ADR 035, ADR 067): the desktop app records every monitor; the backend keeps its report.

ADR 035 (operator decision 2026-09-24) recorded every monitor from launch to quit. Since the
operator's decision of 2026-10-24 (ADR 067) it is paused by default: the desktop app records only
when ``SCREEN_RECORD_ENV`` says yes, read once at launch, and otherwise reports ``state: "paused"``.
The Electron main process records (frontend/electron/screenRecorder.mjs) and posts its status here
every ``SCREEN_RECORD_REPORT_SEC``; nothing on the backend starts or stops it.
"""
SCREEN_RECORD_SCHEMA_VERSION = 1
SCREEN_RECORD_REPORT_MAX_BODY_BYTES = 64 * 1024
SCREEN_RECORD_REPORT_SEC = 10.0                # mirrors screenRecordPlan.mjs SCREEN_RECORD_REPORT_MS
SCREEN_RECORD_STALE_SEC = 35.0                 # three missed reports: no desktop app is recording
SCREEN_RECORD_MAX_DISPLAYS = 16
SCREEN_RECORD_MAX_PROBLEMS = 20
SCREEN_RECORD_STATES = ("starting", "recording", "partial", "failed", "suspended", "stopped", "paused")
SCREEN_RECORD_DIR_SOURCES = ("env", "data_drive", "fallback")
SCREEN_RECORD_DIR_ENV = "NOVA_SCREEN_RECORD_DIR"  # read by the desktop app, named here for the fix text
# The flag (ADR 067): read by the desktop app at launch; the checklist reads it only when no app reports.
SCREEN_RECORD_ENV = "NOVA_SCREEN_RECORD"
SCREEN_RECORD_ON_VALUES = ("1", "true", "yes", "on")  # mirrors screenRecordPlan.mjs screenRecordOn
# The drive guard, as the leaderboard's (#485); mirrors screenRecordPlan.mjs.
SCREEN_RECORD_FREE_WARN_BYTES = 50 * 1024**3
SCREEN_RECORD_FREE_FAIL_BYTES = 10 * 1024**3
