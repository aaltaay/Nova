/**
 * Persist BrowserWindow bounds in Electron userData.
 *
 * Owner: this module (main + traderWindows callers).
 * Invalidation: schema_version bump, or bounds that no longer overlap a display.
 * schema_version: 1 -- entries are {x, y, width, height, maximized?}; the rect
 * is the window's normal (restored) bounds and `maximized` whether it closed
 * maximized (absent in older files: read as false).
 *
 * Restoring on a mixed-DPI desk: Electron scales constructor bounds that land
 * on a display whose scale factor differs from the primary's (a 1600x1000 rect
 * on a 150% monitor opens 2400x1500). Saving that and restoring it again grew
 * the window every launch until it spanned every monitor. So a restored rect
 * is clamped to the display it sits on and applied again with setBounds once
 * the window exists (which lands exactly), and a maximized window is saved as
 * its normal bounds plus the flag, never as its maximized size.
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

/** The display the rect overlaps most, or null when it overlaps none. */
export function displayForBounds(bounds, displays) {
  let best = null;
  let bestArea = 0;
  for (const d of Array.isArray(displays) ? displays : []) {
    if (!isFiniteRect(d)) continue;
    const area = overlapArea(bounds, d);
    if (area > bestArea) {
      best = d;
      bestArea = area;
    }
  }
  return best;
}

/** Shrink the rect to fit one display and move it fully onto that display. */
export function clampBoundsToDisplay(bounds, display) {
  const width = Math.min(bounds.width, display.width);
  const height = Math.min(bounds.height, display.height);
  const x = Math.min(Math.max(bounds.x, display.x), display.x + display.width - width);
  const y = Math.min(Math.max(bounds.y, display.y), display.y + display.height - height);
  return { x, y, width, height };
}

/** @returns {{bounds: {x: number, y: number, width: number, height: number}, maximized: boolean} | null} */
export function pickStoredPlacement(store, windowId, displays) {
  const raw = store?.windows?.[windowId];
  if (!isFiniteRect(raw)) return null;
  const bounds = {
    x: Math.round(raw.x),
    y: Math.round(raw.y),
    width: Math.round(raw.width),
    height: Math.round(raw.height),
  };
  if (!boundsVisibleOnDisplays(bounds, displays)) return null;
  const display = displayForBounds(bounds, displays);
  return {
    bounds: display ? clampBoundsToDisplay(bounds, display) : bounds,
    maximized: raw.maximized === true,
  };
}

export function pickStoredBounds(store, windowId, displays) {
  return pickStoredPlacement(store, windowId, displays)?.bounds ?? null;
}

export function upsertWindowBounds(store, windowId, bounds, maximized = false) {
  if (!windowId || !isFiniteRect(bounds)) return parseBoundsStore(store);
  const next = parseBoundsStore(store);
  next.windows[windowId] = {
    x: Math.round(bounds.x),
    y: Math.round(bounds.y),
    width: Math.round(bounds.width),
    height: Math.round(bounds.height),
    maximized: maximized === true,
  };
  return next;
}

export function persistWindowBounds(userDataDir, windowId, bounds, maximized = false) {
  const store = upsertWindowBounds(readBoundsStore(userDataDir), windowId, bounds, maximized);
  writeBoundsStore(userDataDir, store);
}

export function restoreWindowPlacement(userDataDir, windowId, displays) {
  return pickStoredPlacement(readBoundsStore(userDataDir), windowId, displays);
}

/** Restored bounds per window, so a DIP rounding echo is not saved as a resize. */
const appliedBounds = new WeakMap();
export const WINDOW_BOUNDS_ROUNDING_PX = 1;

/**
 * The rect to save: the one restored, when the window reports it back within a
 * pixel. On a 150% display a 1000 px tall window reads back 1001, and saving
 * that grew it a pixel every launch.
 */
export function settleRoundTrip(applied, current) {
  if (!applied || !isFiniteRect(current)) return current;
  const near = ['x', 'y', 'width', 'height'].every(
    (k) => Math.abs(current[k] - applied[k]) <= WINDOW_BOUNDS_ROUNDING_PX,
  );
  return near ? applied : current;
}

/**
 * Re-apply a restored placement to a window built with its bounds. This second
 * setBounds is what lands the size on a display whose scale factor differs
 * from the primary's; a window saved maximized maximizes when first shown.
 */
export function applyStoredPlacement(win, placement) {
  if (!placement) return;
  appliedBounds.set(win, placement.bounds);
  win.setBounds(placement.bounds);
  if (placement.maximized) {
    win.once('show', () => {
      if (typeof win.isDestroyed === 'function' && win.isDestroyed()) return;
      win.maximize();
    });
  }
}

export function bindWindowBoundsPersist(win, userDataDir, idGetter, debounceMs = 250) {
  let timer = null;
  const flush = () => {
    if (typeof win.isDestroyed === 'function' && win.isDestroyed()) return;
    const id = typeof idGetter === 'function' ? idGetter() : idGetter;
    // Normal bounds, never the maximized rect: restored as a plain window,
    // a maximized size covers its whole display and then some.
    const normal = settleRoundTrip(appliedBounds.get(win), win.getNormalBounds());
    persistWindowBounds(userDataDir, id, normal, win.isMaximized());
  };
  const save = () => {
    clearTimeout(timer);
    timer = setTimeout(flush, debounceMs);
  };
  win.on('moved', save);
  win.on('resized', save);
  win.on('maximize', save);
  win.on('unmaximize', save);
  win.on('close', () => {
    clearTimeout(timer);
    flush();
  });
}
