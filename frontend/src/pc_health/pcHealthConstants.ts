/** The PC's own warnings on the desk (operator ask, 2026-10-15). Schema: architecture/schema/desk-ops.md. */

/** The low-memory notice's backend answer (`perf/memory_notice.py`). */
export const PC_MEMORY_NOTICE_PATH = '/api/perf/memory-notice';

/** The memory watch reads the PC once a minute; reading its answer twice as often keeps the strip at most ~30 s behind. */
export const PC_MEMORY_POLL_MS = 30_000;

export const PC_MEMORY_LATER_LABEL = 'Later';
