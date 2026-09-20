/** Isolated sample-data route: ?view=sample (& optional &symbol= for Trader). */

export const SAMPLE_VIEW_QUERY_VALUE = 'sample';
export const SAMPLE_VIEW_QUERY_KEY = 'view';
export const SAMPLE_SYMBOL_KEY = 'symbol';

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

export function buildSampleDashboardUrl(baseHref = window.location.href): string {
  const url = new URL(baseHref);
  url.searchParams.set(SAMPLE_VIEW_QUERY_KEY, SAMPLE_VIEW_QUERY_VALUE);
  url.searchParams.delete(SAMPLE_SYMBOL_KEY);
  return url.toString();
}

export function buildSampleTraderUrl(symbol: string, baseHref = window.location.href): string {
  const url = new URL(baseHref);
  url.searchParams.set(SAMPLE_VIEW_QUERY_KEY, SAMPLE_VIEW_QUERY_VALUE);
  url.searchParams.set(SAMPLE_SYMBOL_KEY, symbol.trim().toUpperCase());
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
  const path = `${url.pathname}${url.search}${url.hash}` || '/';
  window.history.pushState({}, '', path);
  window.dispatchEvent(new PopStateEvent('popstate'));
}

export function replaceSampleTraderUrl(symbol: string): void {
  window.history.replaceState({}, '', buildSampleTraderUrl(symbol));
}

export function leaveSampleTraderUrl(): void {
  window.history.replaceState({}, '', buildSampleDashboardUrl());
}
