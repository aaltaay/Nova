/**
 * The operator's focus, the desk's half (ADR 031) -- tunables for the report
 * each window posts to `POST /sensors/focus`. The Electron main process keeps
 * its own copy of the cadence (`electron/focusSensor.mjs` cannot import TS;
 * `src/electron/focusSensor.test.ts` pins the two equal). Wire shape:
 * AGENTS.md sec. 3, "The operator's focus and the book watcher".
 */

export const FOCUS_SCHEMA_VERSION = 1;
export const FOCUS_REPORT_PATH = '/sensors/focus';

/** A window reports at least this often, so the backend knows it is still open. */
export const FOCUS_HEARTBEAT_MS = 5_000;
/** How often the Electron main process reports which window has Windows focus. */
export const FOCUS_ELECTRON_HEARTBEAT_MS = 5_000;
/** A click or keypress is reported at most this often (its time always rides on the next report). */
export const FOCUS_INPUT_REPORT_MIN_MS = 2_000;
/** Page and symbol changes settle this long before they are reported (one render burst, one post). */
export const FOCUS_SETTLE_MS = 150;
/** A failed post is logged at most this often. */
export const FOCUS_FAIL_LOG_MS = 60_000;
/** Trader tabs listed per report (the server refuses more). */
export const FOCUS_MAX_TABS = 40;
