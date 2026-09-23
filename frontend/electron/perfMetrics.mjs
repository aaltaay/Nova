/**
 * Performance recorder, the Electron main process's half (ADR 026): every
 * PERF_ELECTRON_REPORT_MS post `app.getAppMetrics()` -- CPU and working set
 * of every Chromium process -- to `POST /api/perf/client` as role `electron`.
 * A window's renderer process is named by the same `window_id` that window's
 * own report carries (perfWindowId.mjs), so a janky window and the CPU its
 * process burned line up in one report.
 *
 * `percentCPUUsage` covers the time since the previous getAppMetrics() call,
 * so each post is that interval's average. Measurement only: a failed post is
 * logged at debug level at most once a minute and never throws.
 *
 * Electron and the API are passed in (main.mjs) so this module stays testable
 * without an Electron runtime.
 */
import { perfWindowIdForUrl } from './perfWindowId.mjs';

/** Mirrors frontend constantGroups/perf.ts PERF_ELECTRON_REPORT_MS (pinned by perfMetrics.test.ts). */
export const PERF_ELECTRON_REPORT_MS = 5_000;
const PERF_CLIENT_PATH = '/api/perf/client';
const PERF_SCHEMA_VERSION = 1;
export const PERF_ELECTRON_WINDOW_ID = 'electron-main';
const PERF_MAX_PROCESSES = 40;
const PERF_FAIL_LOG_MS = 60_000;
/** Mirrors constantGroups/api_auth.ts NOVA_API_KEY_HEADER. */
const NOVA_API_KEY_HEADER = 'X-Nova-Api-Key';
const KB_PER_MB = 1024;

const round1 = (n) => Math.round(n * 10) / 10;

/** pid -> window_id for every live BrowserWindow's renderer process. */
export function windowIdsByPid(windows) {
  const byPid = new Map();
  for (const win of windows) {
    try {
      if (!win || win.isDestroyed()) continue;
      const pid = win.webContents.getOSProcessId();
      if (!pid || byPid.has(pid)) continue;
      byPid.set(pid, perfWindowIdForUrl(win.webContents.getURL()));
    } catch {
      /* a window closing mid-read has no process to name */
    }
  }
  return byPid;
}

export function buildElectronPerfReport({ metrics, windows, intervalSec, uiTag = null }) {
  const byPid = windowIdsByPid(windows);
  const processes = metrics.slice(0, PERF_MAX_PROCESSES).map((m) => ({
    type: String(m.type ?? 'unknown'),
    window_id: byPid.get(m.pid) ?? null,
    pid: m.pid,
    cpu_pct: round1(m.cpu?.percentCPUUsage ?? 0),
    working_set_mb: round1((m.memory?.workingSetSize ?? 0) / KB_PER_MB),
  }));
  return {
    schema_version: PERF_SCHEMA_VERSION,
    window_id: PERF_ELECTRON_WINDOW_ID,
    role: 'electron',
    visible: null,
    interval_sec: Math.round(intervalSec * 1000) / 1000,
    ui_tag: uiTag || null,
    frames: null,
    long_frames: null,
    sockets: {},
    renders: {},
    heap_mb: null,
    dom_nodes: null,
    processes,
  };
}

/**
 * Start the report loop; returns the stop. `apiKey` is a function so a key
 * the sidecar resolves after start is still sent.
 */
export function startPerfMetrics({
  app,
  BrowserWindow,
  apiBase,
  apiKey = () => '',
  releaseTag = null,
  fetchImpl = globalThis.fetch,
  now = () => Date.now(),
  intervalMs = PERF_ELECTRON_REPORT_MS,
}) {
  let lastTs = now();
  let lastFailLog = -Infinity;
  let inFlight = false;

  const noteFailure = (why) => {
    const t = now();
    if (t - lastFailLog < PERF_FAIL_LOG_MS) return;
    lastFailLog = t;
    console.debug('[nova] perf report not delivered', why);
  };

  // The first reading is CPU since process start; take it now so the first post covers one interval.
  try {
    app.getAppMetrics();
  } catch (err) {
    noteFailure(err);
  }

  const tick = () => {
    const t = now();
    const intervalSec = (t - lastTs) / 1000;
    lastTs = t;
    if (inFlight) {
      noteFailure('previous report still in flight');
      return;
    }
    try {
      const report = buildElectronPerfReport({
        metrics: app.getAppMetrics(),
        windows: BrowserWindow.getAllWindows(),
        intervalSec,
        uiTag: releaseTag,
      });
      const headers = { 'Content-Type': 'application/json' };
      const key = apiKey();
      if (key) headers[NOVA_API_KEY_HEADER] = key;
      inFlight = true;
      Promise.resolve(
        fetchImpl(`${apiBase}${PERF_CLIENT_PATH}`, {
          method: 'POST',
          headers,
          body: JSON.stringify(report),
          signal: AbortSignal.timeout(intervalMs),
        }),
      )
        .then((res) => {
          if (!res.ok) noteFailure(`HTTP ${res.status}`);
        }, noteFailure)
        .finally(() => {
          inFlight = false;
        });
    } catch (err) {
      inFlight = false;
      noteFailure(err);
    }
  };

  const timer = setInterval(tick, intervalMs);
  timer.unref?.();
  return () => clearInterval(timer);
}
