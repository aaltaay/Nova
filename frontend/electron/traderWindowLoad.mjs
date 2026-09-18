/**
 * Pure URL + load helpers for Trader BrowserWindows.
 * Owner: traderWindows.mjs (child) and main.mjs (main-window fail retry).
 */

export function isAllowedRendererUrl(url, { requireStockView = false } = {}) {
  if (typeof url !== 'string' || !url.trim()) return false;
  try {
    const parsed = new URL(url);
    if (parsed.protocol === 'chrome-error:' || parsed.protocol === 'chrome:') {
      return false;
    }
    if (
      parsed.protocol !== 'http:'
      && parsed.protocol !== 'https:'
      && parsed.protocol !== 'file:'
    ) {
      return false;
    }
    if (!requireStockView) return true;
    if (parsed.searchParams.get('view') !== 'stock') return false;
    return Boolean((parsed.searchParams.get('symbol') || '').trim());
  } catch {
    return false;
  }
}

/**
 * Load `url` into an already-created window. Resolves true only after a
 * successful load; failed loads close the window so a blank chrome-error
 * shell does not stay focused.
 *
 * @param {{ loadURL: (url: string) => Promise<unknown>, show: () => void, focus: () => void, close: () => void, isDestroyed?: () => boolean, webContents: { once: Function, removeListener: Function } }} win
 */
export function loadTraderWindow(win, url) {
  return new Promise((resolve) => {
    let settled = false;
    const done = (ok) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };
    const destroyed = () => typeof win.isDestroyed === 'function' && win.isDestroyed();
    const onFail = (_event, code, desc) => {
      console.error('[nova] trader window load failed', url, code, desc);
      done(false);
      if (!destroyed()) win.close();
    };
    win.webContents.once('did-fail-load', onFail);
    Promise.resolve(win.loadURL(url))
      .then(() => {
        win.webContents.removeListener('did-fail-load', onFail);
        if (destroyed()) {
          done(false);
          return;
        }
        win.show();
        win.focus();
        done(true);
      })
      .catch((err) => {
        const message = err instanceof Error ? err.message : String(err);
        onFail(null, -1, message);
      });
  });
}
