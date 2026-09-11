/**
 * Persist BrowserWindow bounds in Electron userData.
 *
 * Owner: this module (main + traderWindows callers).
 * Invalidation: schema_version bump, or bounds that no longer overlap a display.
 * schema_version: 1
 */
import fs from 'node:fs';
import path from 'node:path';

export const WINDOW_BOUNDS_SCHEMA_VERSION = 1;
export const WINDOW_BOUNDS_FILENAME = 'window-bounds.json';
export const WINDOW_ID_MAIN = 'main';
export const WINDOW_BOUNDS_MIN_OVERLAP_PX = 8000;

export function traderWindowId(symbol) {
  return `trader:${String(symbol || '').trim().toUpperCase()}`;
}

export function boundsFilePath(userDataDir) {
  return path.join(userDataDir, WINDOW_BOUNDS_FILENAME);
}

export function emptyBoundsStore() {
  return { schema_version: WINDOW_BOUNDS_SCHEMA_VERSION, windows: {} };
}

function isFiniteRect(value) {
  return (
    value
    && Number.isFinite(value.x)
    && Number.isFinite(value.y)
    && Number.isFinite(value.width)
    && Number.isFinite(value.height)
    && value.width >= 200
    && value.height >= 200
  );
}

export function overlapArea(a, b) {
  const x1 = Math.max(a.x, b.x);
  const y1 = Math.max(a.y, b.y);
  const x2 = Math.min(a.x + a.width, b.x + b.width);
  const y2 = Math.min(a.y + a.height, b.y + b.height);
  if (x2 <= x1 || y2 <= y1) return 0;
  return (x2 - x1) * (y2 - y1);
}

export function boundsVisibleOnDisplays(bounds, displays, minOverlap = WINDOW_BOUNDS_MIN_OVERLAP_PX) {
  if (!isFiniteRect(bounds) || !Array.isArray(displays) || displays.length === 0) {
    return false;
  }
  return displays.some((d) => isFiniteRect(d) && overlapArea(bounds, d) >= minOverlap);
}

export function parseBoundsStore(raw) {
  if (!raw || typeof raw !== 'object' || raw.schema_version !== WINDOW_BOUNDS_SCHEMA_VERSION) {
    return emptyBoundsStore();
  }
  const windows = raw.windows && typeof raw.windows === 'object' ? raw.windows : {};
  return { schema_version: WINDOW_BOUNDS_SCHEMA_VERSION, windows: { ...windows } };
}

export function readBoundsStore(userDataDir) {
  const file = boundsFilePath(userDataDir);
  try {
    if (!fs.existsSync(file)) return emptyBoundsStore();
    return parseBoundsStore(JSON.parse(fs.readFileSync(file, 'utf8')));
  } catch (err) {
    console.error('[nova] window-bounds read failed', err);
    return emptyBoundsStore();
  }
}

export function writeBoundsStore(userDataDir, store) {
  const file = boundsFilePath(userDataDir);
  const payload = parseBoundsStore(store);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(payload, null, 2)}\n`, 'utf8');
}

export function pickStoredBounds(store, windowId, displays) {
  const raw = store?.windows?.[windowId];
  if (!isFiniteRect(raw)) return null;
  const bounds = {
    x: Math.round(raw.x),
    y: Math.round(raw.y),
    width: Math.round(raw.width),
    height: Math.round(raw.height),
  };
  if (!boundsVisibleOnDisplays(bounds, displays)) return null;
  return bounds;
}

export function upsertWindowBounds(store, windowId, bounds) {
  if (!windowId || !isFiniteRect(bounds)) return parseBoundsStore(store);
  const next = parseBoundsStore(store);
  next.windows[windowId] = {
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    width: Math.round(bounds.width),
    height: Math.round(bounds.height),
  };
  return next;
}

export function persistWindowBounds(userDataDir, windowId, bounds) {
  const store = upsertWindowBounds(readBoundsStore(userDataDir), windowId, bounds);
  writeBoundsStore(userDataDir, store);
}

export function restoreWindowBounds(userDataDir, windowId, displays) {
  return pickStoredBounds(readBoundsStore(userDataDir), windowId, displays);
}

export function bindWindowBoundsPersist(win, userDataDir, idGetter, debounceMs = 250) {
  let timer = null;
  const flush = () => {
    if (typeof win.isDestroyed === 'function' && win.isDestroyed()) return;
    const id = typeof idGetter === 'function' ? idGetter() : idGetter;
    persistWindowBounds(userDataDir, id, win.getBounds());
  };
  const save = () => {
    clearTimeout(timer);
    timer = setTimeout(flush, debounceMs);
  };
  win.on('moved', save);
  win.on('resized', save);
  win.on('close', () => {
    clearTimeout(timer);
    flush();
  });
}
