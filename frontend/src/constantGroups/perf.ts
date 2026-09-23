/**
 * Performance recorder, the desk's half (ADR 026) -- tunables for the report
 * each window posts to `POST /api/perf/client`. The Electron main process
 * keeps its own copy of the cadence (`electron/perfMetrics.mjs` cannot import
 * TS; `perfMetrics.test.ts` pins the two equal). Wire shape: AGENTS.md sec. 3,
 * "Performance recorder".
 */

export const PERF_SCHEMA_VERSION = 1;
export const PERF_CLIENT_PATH = '/api/perf/client';

/** How often each window posts its summary. */
export const PERF_REPORT_MS = 5_000;
/** How often the Electron main process posts its per-process CPU / memory. */
export const PERF_ELECTRON_REPORT_MS = 5_000;

/** A frame interval above this (two 60 Hz frames) counts as slow. */
export const PERF_SLOW_FRAME_MS = 33;
/** Frame intervals kept per report for the p95 (a 240 Hz screen fills ~1,200). */
export const PERF_FRAME_SAMPLES_MAX = 2_048;

/** Scripts named per report from the long animation frames. */
export const PERF_LONG_FRAME_TOP = 3;
/** Distinct scripts tallied per report before new ones are ignored. */
export const PERF_LONG_FRAME_SCRIPTS_MAX = 200;
/** A `longtask` entry blocks for its duration past this (the long-task line). */
export const PERF_LONGTASK_BUDGET_MS = 50;

export const PERF_MAX_SOCKET_KEYS = 40;
export const PERF_MAX_RENDER_KEYS = 60;
/** Longest counter name, script source or invoker the report carries. */
export const PERF_MAX_NAME_CHARS = 200;
/** The server refuses a larger body. */
export const PERF_MAX_BODY_BYTES = 16_384;

/** A failing post is logged at most this often (console.debug). */
export const PERF_FAIL_LOG_MS = 60_000;
