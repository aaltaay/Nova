/**
 * Opening the Top 9 pop-up, and which list it shows.
 *
 * The list lives in one shared key (TOP_NINE_LIST_KEY), not in the URL: a grid button on the rail
 * writes it and then opens or focuses the one pop-up, which follows the key -- so a second button
 * switches the open window's tab without reloading it (its rank marks survive).
 */
import { readPref, writePref } from '../utils/prefStore';
import {
  TOP_NINE_DEFAULT_LIST,
  TOP_NINE_LIST_KEY,
  TOP_NINE_QUERY_VIEW,
  TOP_NINE_WINDOW_FEATURES,
  TOP_NINE_WINDOW_NAME,
  isTopNineList,
  type TopNineList,
} from './topNineConstants';

export function isTopNineView(search = window.location.search): boolean {
  return new URLSearchParams(search).get('view') === TOP_NINE_QUERY_VIEW;
}

export function buildTopNineUrl(baseHref = window.location.href): string {
  const url = new URL(baseHref);
  url.search = '';
  url.hash = '';
  url.searchParams.set('view', TOP_NINE_QUERY_VIEW);
  return url.toString();
}

export function readTopNineList(storage: Pick<Storage, 'getItem'> = localStorage): TopNineList {
  return readPref<TopNineList>(
    TOP_NINE_LIST_KEY,
    TOP_NINE_DEFAULT_LIST,
    (raw) => (isTopNineList(raw) ? raw : null),
    storage,
  );
}

export function writeTopNineList(list: TopNineList, storage: Pick<Storage, 'setItem'> = localStorage): void {
  writePref(TOP_NINE_LIST_KEY, list, storage);
}

/**
 * Show `list` in the pop-up, opening it when it is not up. Desktop: one BrowserWindow (IPC).
 * Browser: a named popup; `window.open('', name)` returns the open one without reloading it.
 * Returns false when no window could be opened (a blocked popup).
 */
export async function openTopNineWindow(list: TopNineList): Promise<boolean> {
  writeTopNineList(list);
  const url = buildTopNineUrl();
  if (typeof window.novaDesktop?.openTopNine === 'function') {
    try {
      return Boolean(await window.novaDesktop.openTopNine(url));
    } catch (err) {
      console.warn('[nova] the desktop app did not open the Top 9 window', err);
      return false;
    }
  }
  const win = window.open('', TOP_NINE_WINDOW_NAME, TOP_NINE_WINDOW_FEATURES);
  if (!win) return false;
  try {
    if (!isTopNineView(win.location.search)) win.location.href = url;
  } catch {
    win.location.href = url;
  }
  try {
    win.focus();
  } catch {
    /* the browser keeps focus where it is */
  }
  return true;
}
