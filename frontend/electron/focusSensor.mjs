/**
 * The operator's focus, the Electron main process's half (ADR 031): which Nova
 * window Windows has in front, and the monitor each window sits on -- only the
 * main process can know either. Posted to `POST /sensors/focus` as role
 * `electron` on every focus change, move, minimize and display change (settled
 * FOCUS_SETTLE_MS, so a switch between two windows is one post) and every
 * FOCUS_ELECTRON_HEARTBEAT_MS. Each window is named by the `window_id` its own
 * focus report carries (perfWindowId.mjs), so the backend joins the two.
 *
 * Monitors are numbered left to right from 1. Measurement only: a failed post
 * is logged at debug level at most once a minute and never throws. Electron and
 * the API are passed in (main.mjs) so this module stays testable without an
 * Electron runtime.
 */
import { perfWindowIdForUrl } from './perfWindowId.mjs';

/** Mirrors frontend constantGroups/focus.ts (pinned by src/electron/focusSensor.test.ts). */
export const FOCUS_ELECTRON_HEARTBEAT_MS = 5_000;
export const FOCUS_SETTLE_MS = 150;
const FOCUS_REPORT_PATH = '/sensors/focus';
const FOCUS_SCHEMA_VERSION = 1;
export const FOCUS_ELECTRON_WINDOW_ID = 'electron-main';
const FOCUS_MAX_WINDOWS = 16;
const FOCUS_FAIL_LOG_MS = 60_000;
/** Mirrors constantGroups/api_auth.ts NOVA_API_KEY_HEADER. */
const NOVA_API_KEY_HEADER = 'X-Nova-Api-Key';
/** A desk window loads the UI; the starting splash is a data: page and devtools is not the desk. */
const DESK_URL = /^(https?|file):/i;

function windowUrl(win) {
  try {
    return String(win.webContents.getURL() || '');
  } catch {
    return '';
  }
}

/** Displays left to right (then top to bottom): the leftmost is monitor 1. */
export function displayOrder(displays) {
  return [...(displays || [])].sort((a, b) => a.bounds.x - b.bounds.x || a.bounds.y - b.bounds.y);
}

export function describeDisplay(display, ordered, primaryId) {
  if (!display) return null;
  const index = ordered.findIndex((d) => d.id === display.id) + 1;
  const scale = display.scaleFactor;
  return {
    id: String(display.id),
    label: display.label ? String(display.label).slice(0, 120) : null,
    index: index || 1,
    count: Math.max(1, ordered.length),
    primary: display.id === primaryId,
    scale_factor: typeof scale === 'number' && scale > 0 ? scale : null,
  };
}

export function buildElectronFocusReport({ windows, screen, reason }) {
  const ordered = displayOrder(screen.getAllDisplays());
  const primaryId = screen.getPrimaryDisplay()?.id;
  const rows = [];
  let focusedId = null;
  for (const win of windows) {
    if (rows.length >= FOCUS_MAX_WINDOWS) break;
    if (win.isDestroyed?.()) continue;
    const url = windowUrl(win);
    if (!DESK_URL.test(url)) continue;
    const windowId = perfWindowIdForUrl(url);
    const focused = Boolean(win.isFocused());
    const minimized = Boolean(win.isMinimized());
    let display = null;
    try {
      display = describeDisplay(screen.getDisplayMatching(win.getBounds()), ordered, primaryId);
    } catch {
      display = null; // a window between displays mid-move: the next report places it
    }
    rows.push({ window_id: windowId, focused, visible: Boolean(win.isVisible()) && !minimized, minimized, display });
    if (focused) focusedId = windowId;
  }
  return {
    schema_version: FOCUS_SCHEMA_VERSION,
    role: 'electron',
    window_id: FOCUS_ELECTRON_WINDOW_ID,
    app_focused: focusedId !== null,
    focused_window_id: focusedId,
    windows: rows,
    reason,
  };
}

const WINDOW_EVENTS = ['moved', 'minimize', 'restore', 'show', 'hide'];
const SCREEN_EVENTS = ['display-added', 'display-removed', 'display-metrics-changed'];

/** Start the focus reports; returns the stop. `apiKey` is a function so a late key is still sent. */
export function startFocusSensor({
  app,
  BrowserWindow,
  screen,
  apiBase,
  apiKey = () => '',
  fetchImpl = globalThis.fetch,
  now = () => Date.now(),
  intervalMs = FOCUS_ELECTRON_HEARTBEAT_MS,
}) {
  let lastFailLog = -Infinity;
  let inFlight = false;
  let queued = null;
  let settleTimer = null;
  let settleReason = null;

  const noteFailure = (why) => {
    const t = now();
    if (t - lastFailLog < FOCUS_FAIL_LOG_MS) return;
    lastFailLog = t;
    console.debug('[nova] focus report not delivered', why);
  };

  const report = (reason) => {
    if (inFlight) {
      if (queued === null || queued === 'heartbeat') queued = reason;
      return;
    }
    try {
      const body = JSON.stringify(
        buildElectronFocusReport({ windows: BrowserWindow.getAllWindows(), screen, reason }),
      );
      const headers = { 'Content-Type': 'application/json' };
      const key = apiKey();
      if (key) headers[NOVA_API_KEY_HEADER] = key;
      inFlight = true;
      Promise.resolve(
        fetchImpl(`${apiBase}${FOCUS_REPORT_PATH}`, {
          method: 'POST',
          headers,
          body,
          signal: AbortSignal.timeout(intervalMs),
        }),
      )
        .then((res) => {
          if (!res.ok) noteFailure(`HTTP ${res.status}`);
        }, noteFailure)
        .finally(() => {
          inFlight = false;
          const next = queued;
          queued = null;
          if (next) report(next);
        });
    } catch (err) {
      inFlight = false;
      noteFailure(err);
    }
  };

  const settle = (reason) => {
    if (settleReason !== 'focus') settleReason = reason;
    if (settleTimer) return;
    settleTimer = setTimeout(() => {
      settleTimer = null;
      const r = settleReason || reason;
      settleReason = null;
      report(r);
    }, FOCUS_SETTLE_MS);
  };

  const onFocus = () => settle('focus');
  const onBlur = () => settle('blur');
  const onDisplay = () => settle('display');
  const watchWindow = (_event, win) => {
    for (const name of WINDOW_EVENTS) win.on?.(name, onDisplay);
  };

  app.on('browser-window-focus', onFocus);
  app.on('browser-window-blur', onBlur);
  app.on('browser-window-created', watchWindow);
  for (const win of BrowserWindow.getAllWindows()) watchWindow(null, win);
  for (const name of SCREEN_EVENTS) screen.on?.(name, onDisplay);
  const timer = setInterval(() => report('heartbeat'), intervalMs);
  timer.unref?.();
  report('start');

  return () => {
    clearInterval(timer);
    if (settleTimer) clearTimeout(settleTimer);
    app.removeListener?.('browser-window-focus', onFocus);
    app.removeListener?.('browser-window-blur', onBlur);
    app.removeListener?.('browser-window-created', watchWindow);
    for (const name of SCREEN_EVENTS) screen.removeListener?.(name, onDisplay);
  };
}
