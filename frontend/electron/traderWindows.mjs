/**
 * Per-symbol Trader BrowserWindows. OS-window cap stays 3 (TRADER_MAX_WINDOWS).
 * In-window strip length is unbounded; live L2 is TRADER_MAX_LIVE_TABS.
 * Prefer one window per display; cascade when monitors < windows.
 *
 * Dock/extract SoT is ADR 011 in the renderer (`traderDesk/`). This file
 * only creates/focuses windows. A future adapter may emit the same
 * dock-request when a float is released over the host -- do not add a
 * second Electron-only dock model here.
 */
import { app, BrowserWindow, screen } from 'electron';
import {
  bindWindowBoundsPersist,
  restoreWindowBounds,
  traderWindowId,
} from './windowBounds.mjs';
import { formatElectronTraderTitle } from './appTitle.mjs';
import { novaDesktopReleaseTag } from './loadReleaseTag.mjs';

export const TRADER_MAX_WINDOWS = 3;
const EDGE_PAD = 24;
const CASCADE = 36;

/** @type {Map<string, import('electron').BrowserWindow>} */
const traderWindows = new Map();

export function symbolFromTraderUrl(url) {
  try {
    const parsed = new URL(url);
    if (parsed.searchParams.get('view') !== 'stock') return '';
    return (parsed.searchParams.get('symbol') || '').trim().toUpperCase();
  } catch {
    return '';
  }
}

export function boundsForTraderWindow(displays, index, width, height) {
  if (!displays.length) {
    return { x: EDGE_PAD + index * CASCADE, y: EDGE_PAD + index * CASCADE, width, height };
  }
  const sorted = [...displays].sort((a, b) => a.x - b.x || a.y - b.y);
  const slot = Math.min(Math.max(index, 0), sorted.length - 1);
  const extra = Math.max(0, index - slot);
  const d = sorted[slot];
  const w = Math.min(width, Math.max(640, d.width - EDGE_PAD * 2));
  const h = Math.min(height, Math.max(480, d.height - EDGE_PAD * 2));
  return {
    x: d.x + EDGE_PAD + extra * CASCADE,
    y: d.y + EDGE_PAD + extra * CASCADE,
    width: w,
    height: h,
  };
}

function displayWorkAreas() {
  return screen.getAllDisplays().map((d) => ({
    x: d.workArea.x,
    y: d.workArea.y,
    width: d.workArea.width,
    height: d.workArea.height,
  }));
}

/**
 * Focus an existing symbol window, or open a new one on the next display.
 * @returns {boolean} false when the 3-window cap is full (focuses an existing).
 */
export function openOrFocusTraderWindow(url, windowOptions, attachHandler) {
  const sym = symbolFromTraderUrl(url);
  if (!sym) {
    throw new Error('Invalid Trader URL');
  }
  const existing = traderWindows.get(sym);
  if (existing && !existing.isDestroyed()) {
    existing.focus();
    return true;
  }
  if (traderWindows.size >= TRADER_MAX_WINDOWS) {
    const first = traderWindows.values().next().value;
    if (first && !first.isDestroyed()) first.focus();
    return false;
  }
  const userData = app.getPath('userData');
  const displays = displayWorkAreas();
  const saved = restoreWindowBounds(userData, traderWindowId(sym), displays);
  const bounds = saved || boundsForTraderWindow(
    displays,
    traderWindows.size,
    windowOptions.width ?? 1440,
    windowOptions.height ?? 900,
  );
  const child = new BrowserWindow({ ...windowOptions, ...bounds });
  let currentSym = sym;
  bindWindowBoundsPersist(child, userData, () => traderWindowId(currentSym));
  const releaseTag = novaDesktopReleaseTag(app);
  child.setTitle(formatElectronTraderTitle(currentSym, releaseTag));
  attachHandler?.(child);
  traderWindows.set(currentSym, child);
  const remapIfNeeded = (nextUrl) => {
    const next = symbolFromTraderUrl(nextUrl);
    if (!next || next === currentSym) return;
    const other = traderWindows.get(next);
    if (other && other !== child && !other.isDestroyed()) {
      other.focus();
      return;
    }
    if (traderWindows.get(currentSym) === child) traderWindows.delete(currentSym);
    currentSym = next;
    traderWindows.set(currentSym, child);
    if (!child.isDestroyed()) {
      child.setTitle(formatElectronTraderTitle(currentSym, releaseTag));
    }
  };
  child.webContents.on('did-navigate-in-page', (_event, nextUrl) => {
    remapIfNeeded(nextUrl);
  });
  child.webContents.on('did-navigate', (_event, nextUrl) => {
    remapIfNeeded(nextUrl);
  });
  child.on('closed', () => {
    if (traderWindows.get(currentSym) === child) traderWindows.delete(currentSym);
  });
  void child.loadURL(url).then(() => {
    if (!child.isDestroyed()) {
      child.show();
      child.focus();
    }
  });
  return true;
}
