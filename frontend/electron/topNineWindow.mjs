/**
 * The one Top 9 pop-up window (top_nine/, operator ask 2026-10-26). A second open focuses it; the
 * list it shows is the renderer's (a shared localStorage key), so focusing never reloads it and
 * its rank marks survive. Its place on screen is kept like every Nova window (windowBounds.mjs).
 *
 * The window shows the desk's lists and asks the desk to open a symbol; it holds no Trader tabs,
 * so it never counts toward TRADER_MAX_WINDOWS. Owner: main.mjs wires it.
 */
import { attachRendererGuards } from './rendererGuards.mjs';
import { isAllowedRendererUrl, loadRendererWindow } from './traderWindowLoad.mjs';
import {
  applyStoredPlacement,
  bindWindowBoundsPersist,
  restoreWindowPlacement,
} from './windowBounds.mjs';
import { withReleaseTag } from './appTitle.mjs';

export const TOP_NINE_WINDOW_ID = 'top-nine';
export const TOP_NINE_VIEW = 'top9';
const TOP_NINE_TITLE = 'Nova — Top 9';

/** @type {import('electron').BrowserWindow | null} */
let topNineWindow = null;

/** A Nova renderer URL that loads the Top 9 page (`?view=top9`), nothing else. */
export function isTopNineUrl(url) {
  if (!isAllowedRendererUrl(url)) return false;
  try {
    return new URL(url).searchParams.get('view') === TOP_NINE_VIEW;
  } catch {
    return false;
  }
}

/**
 * Focus the Top 9 window, or open it.
 * @param {{ BrowserWindow: typeof import('electron').BrowserWindow, userData: string,
 *   displays: Array<{x:number,y:number,width:number,height:number}>, releaseTag?: string | null }} deps
 * @returns {Promise<boolean>}
 */
export async function openOrFocusTopNineWindow(url, windowOptions, deps) {
  if (!isTopNineUrl(url)) throw new Error('Invalid Top 9 URL');
  if (topNineWindow && !topNineWindow.isDestroyed()) {
    if (topNineWindow.isMinimized()) topNineWindow.restore();
    topNineWindow.show();
    topNineWindow.focus();
    return true;
  }
  const saved = restoreWindowPlacement(deps.userData, TOP_NINE_WINDOW_ID, deps.displays);
  const win = new deps.BrowserWindow({
    ...windowOptions,
    width: 1600,
    height: 960,
    minWidth: 900,
    minHeight: 560,
    ...(saved?.bounds ?? {}),
    title: withReleaseTag(TOP_NINE_TITLE, deps.releaseTag ?? null),
    show: false,
  });
  applyStoredPlacement(win, saved);
  attachRendererGuards(win, { allowedBase: url, reloadUrl: url });
  bindWindowBoundsPersist(win, deps.userData, () => TOP_NINE_WINDOW_ID);
  // It opens nothing itself: a double-click asks the desk window over the desk bus.
  win.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  // The page sets its own document title; the OS title stays "Nova — Top 9".
  win.on('page-title-updated', (event) => event.preventDefault());
  win.on('closed', () => {
    if (topNineWindow === win) topNineWindow = null;
  });
  topNineWindow = win;
  const loaded = await loadRendererWindow(win, { reloadUrl: url, closeOnFail: true, label: 'top 9 window' });
  if (!loaded && topNineWindow === win) topNineWindow = null;
  return loaded;
}
