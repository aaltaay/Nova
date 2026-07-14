/** URL helpers for the detachable Stock View tab (?view=stock&symbol=LVLU). */

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

/** Opens Stock View in a new browser / Electron tab. Returns null if blocked. */
export function openStockViewWindow(symbol: string): Window | null {
  const sym = symbol.trim().toUpperCase();
  if (!sym) return null;
  return window.open(buildStockViewUrl(sym), '_blank', 'noopener,noreferrer');
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
