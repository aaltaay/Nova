/**
 * Isolated sample-data route: ?view=sample (& optional &symbol= for Trader;
 * & popout=1 for a sample Trader tab popped out into its own window, #449).
 */

export const SAMPLE_VIEW_QUERY_VALUE = 'sample';
export const SAMPLE_VIEW_QUERY_KEY = 'view';
export const SAMPLE_SYMBOL_KEY = 'symbol';
/** Marks a sample pop-out window. The live pop-out's `view=stock` would leave the sample desk. */
export const SAMPLE_POPOUT_KEY = 'popout';
export const SAMPLE_POPOUT_VALUE = '1';

/**
 * '' when there is no browser. `isSampleView` is read by transport guards and
 * by GlobalAppBar, both of which are imported by suites that declare
 * `@vitest-environment node`; reading window.location there would throw inside
 * the guard instead of failing an assertion. Every caller gets the safe answer
 * here rather than each repeating a `typeof window` check (#357).
 */
function currentSearch(): string {
  return typeof window === 'undefined' ? '' : window.location.search;
}

export function isSampleView(search = currentSearch()): boolean {
  const params = new URLSearchParams(search);
  return params.get(SAMPLE_VIEW_QUERY_KEY) === SAMPLE_VIEW_QUERY_VALUE;
}

export function parseSampleSymbol(search = currentSearch()): string | null {
  if (!isSampleView(search)) return null;
  const symbol = (new URLSearchParams(search).get(SAMPLE_SYMBOL_KEY) || '')
    .trim()
    .toUpperCase();
  return symbol || null;
}

/** A sample Trader tab popped out into its own window (?view=sample&symbol=X&popout=1). */
export function isSamplePopOut(search = currentSearch()): boolean {
  return isSampleView(search) && new URLSearchParams(search).get(SAMPLE_POPOUT_KEY) === SAMPLE_POPOUT_VALUE;
}

export function buildSampleDashboardUrl(baseHref = window.location.href): string {
  const url = new URL(baseHref);
  url.searchParams.set(SAMPLE_VIEW_QUERY_KEY, SAMPLE_VIEW_QUERY_VALUE);
  url.searchParams.delete(SAMPLE_SYMBOL_KEY);
  url.searchParams.delete(SAMPLE_POPOUT_KEY);
  return url.toString();
}

export function buildSampleTraderUrl(symbol: string, baseHref = window.location.href): string {
  const url = new URL(baseHref);
  url.searchParams.set(SAMPLE_VIEW_QUERY_KEY, SAMPLE_VIEW_QUERY_VALUE);
  url.searchParams.set(SAMPLE_SYMBOL_KEY, symbol.trim().toUpperCase());
  return url.toString();
}

/** The sample pop-out for `symbol`: the sample Trader URL plus the pop-out mark. */
export function buildSamplePopOutUrl(symbol: string, baseHref = window.location.href): string {
  const url = new URL(buildSampleTraderUrl(symbol, baseHref));
  url.searchParams.set(SAMPLE_POPOUT_KEY, SAMPLE_POPOUT_VALUE);
  return url.toString();
}

export function enterSampleView(): void {
  window.history.pushState({}, '', buildSampleDashboardUrl());
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function leaveSampleView(): void {
  const url = new URL(window.location.href);
  url.searchParams.delete(SAMPLE_VIEW_QUERY_KEY);
  url.searchParams.delete(SAMPLE_SYMBOL_KEY);
  url.searchParams.delete(SAMPLE_POPOUT_KEY);
  const path = `${url.pathname}${url.search}${url.hash}` || '/';
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function replaceSampleTraderUrl(symbol: string): void {
  window.history.replaceState({}, '', buildSampleTraderUrl(symbol));
}

/** A sample pop-out's URL follows its tab, so a reload reopens the same symbol there. */
export function replaceSamplePopOutUrl(symbol: string): void {
  window.history.replaceState({}, '', buildSamplePopOutUrl(symbol));
}

export function leaveSampleTraderUrl(): void {
  window.history.replaceState({}, '', buildSampleDashboardUrl());
}
