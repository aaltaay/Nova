/**
 * The sample desk's pop-out (#449): a sample Trader tab in its own browser
 * window, on the sample route (`?view=sample&symbol=X&popout=1`) -- never the
 * live `?view=stock` window, which would leave the sample desk.
 *
 * The desktop app opens pop-outs through its main process, and only for live
 * Trader URLs (electron/traderWindows.mjs refuses any other, and so does its
 * window-open handler). There the control is locked with
 * SAMPLE_POPOUT_DESKTOP_WHY rather than failing on a press.
 */
import { STOCK_VIEW_WINDOW_FEATURES } from '../constants';
import { SAMPLE_POPOUT_DESKTOP_WHY } from './sampleCopy';
import { buildSamplePopOutUrl } from './sampleNav';

/** window.open name: one window per symbol, never a live Trader window's (`nova-trader-SMPL`). */
export const SAMPLE_WINDOW_NAME_PREFIX = 'nova-sample-trader';

export function samplePopOutWindowName(symbol: string): string {
  return `${SAMPLE_WINDOW_NAME_PREFIX}-${symbol.trim().toUpperCase()}`;
}

/** Why a sample tab cannot pop out in this window, or null when it can. */
export function samplePopOutWhy(win: Pick<Window, 'novaDesktop'> = window): string | null {
  return win.novaDesktop ? SAMPLE_POPOUT_DESKTOP_WHY : null;
}

/**
 * Open `symbol` in a sample pop-out. False when it cannot pop out here or the
 * browser blocked the window, so the caller can say so.
 */
export function openSamplePopOut(symbol: string, win: Window = window): boolean {
  const sym = symbol.trim().toUpperCase();
  if (!sym || samplePopOutWhy(win)) return false;
  const opened = win.open(
    buildSamplePopOutUrl(sym, win.location.href),
    samplePopOutWindowName(sym),
    STOCK_VIEW_WINDOW_FEATURES,
  );
  if (!opened) return false;
  try {
    opened.opener = null;
  } catch {
    /* a locked opener: the window is open either way */
  }
  try {
    opened.focus();
  } catch {
    /* focus is best effort */
  }
  return true;
}
