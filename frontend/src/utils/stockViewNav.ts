/** URL helpers for the detachable Stock View window (?view=stock&symbol=LVLU). */

import {
  STOCK_VIEW_WINDOW_FEATURES,
} from '../constants';

export const STOCK_VIEW_QUERY_VIEW = 'stock';
export const STOCK_VIEW_QUERY_KEY = 'view';
export const STOCK_VIEW_SYMBOL_KEY = 'symbol';

export function buildStockViewUrl(symbol: string, baseHref = window.location.href): string {
  const url = new URL(baseHref);
  url.searchParams.set(STOCK_VIEW_QUERY_KEY, STOCK_VIEW_QUERY_VIEW);
  url.searchParams.set(STOCK_VIEW_SYMBOL_KEY, symbol.trim().toUpperCase());
  return url.toString();
}

export function parseStockViewSymbol(search = window.location.search): string | null {
  const params = new URLSearchParams(search);
  if (params.get(STOCK_VIEW_QUERY_KEY) !== STOCK_VIEW_QUERY_VIEW) return null;
  const symbol = (params.get(STOCK_VIEW_SYMBOL_KEY) || '').trim().toUpperCase();
  return symbol || null;
}

/** Named target so re-opening the same symbol focuses the existing window. */
export function stockViewWindowName(symbol: string): string {
  return `nova-stock-${symbol.trim().toUpperCase()}`;
}

/**
 * Opens Stock View in a detached OS window (not a browser tab).
 * Returns true when a separate window was opened.
 *
 * Browser: pass width/height/`popup=yes` — bare `_blank` opens a tab.
 * Do NOT pass `noopener` — that makes window.open return null even when a
 * window opens, which we used to misread as "popup blocked" and then
 * navigated the *current* tab instead.
 * Desktop: prefer IPC so Electron creates a real BrowserWindow.
 */
export async function openStockViewWindow(symbol: string): Promise<boolean> {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return false;
  const url = buildStockViewUrl(sym);

  if (typeof window.novaDesktop?.openStockView === 'function') {
    try {
      await window.novaDesktop.openStockView(url);
      return true;
    } catch {
      // fall through to window.open
    }
  }

  const win = window.open(url, stockViewWindowName(sym), STOCK_VIEW_WINDOW_FEATURES);
  if (!win) return false;
  try {
    win.opener = null;
  } catch {
    /* ignore cross-origin / locked opener */
  }
  try {
    win.focus();
  } catch {
    /* ignore */
  }
  return true;
}

export function replaceStockViewUrl(symbol: string): void {
  const next = buildStockViewUrl(symbol);
  window.history.replaceState({}, '', next);
}

export function leaveStockViewUrl(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete(STOCK_VIEW_QUERY_KEY);
  url.searchParams.delete(STOCK_VIEW_SYMBOL_KEY);
  const path = `${url.pathname}${url.search}${url.hash}` || '/';
  window.history.replaceState({}, '', path);
}
