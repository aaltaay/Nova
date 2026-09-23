/**
 * The `window_id` both halves of the performance recorder report (ADR 026),
 * so the Electron main process's CPU / memory row for a renderer process names
 * the same window as that window's own report. Pure -- no electron or node
 * imports -- because the renderer imports it too (src/perf/perfReporter.ts).
 *
 * The host window (and a plain browser tab) is `main`; a Trader pop-out
 * (`?view=stock&symbol=SYM`, traderWindows.mjs) is `trader:SYM`, the key
 * windowBounds.mjs keeps its bounds under. Both follow the window's current
 * URL, so a pop-out that switches its active symbol reports the new one on
 * both sides.
 */
export const PERF_WINDOW_ID_MAIN = 'main';
export const PERF_WINDOW_ID_MAX = 64;

/** The server accepts [A-Za-z0-9_.:-] only (a `BRK/B` pop-out becomes `trader:BRK_B`). */
const UNSAFE_CHARS = /[^A-Za-z0-9_.:-]/g;

export function perfWindowIdForUrl(url) {
  let parsed;
  try {
    parsed = new URL(String(url ?? ''));
  } catch {
    return PERF_WINDOW_ID_MAIN;
  }
  if (parsed.searchParams.get('view') !== 'stock') return PERF_WINDOW_ID_MAIN;
  const symbol = (parsed.searchParams.get('symbol') || '').trim().toUpperCase();
  if (!symbol) return PERF_WINDOW_ID_MAIN;
  return `trader:${symbol}`.replace(UNSAFE_CHARS, '_').slice(0, PERF_WINDOW_ID_MAX);
}
