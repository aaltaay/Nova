/**
 * Pure URL + load helpers for Electron BrowserWindows.
 * Owner: traderWindows.mjs (child, close on fail) and main.mjs (host,
 * keep the window so rendererGuards can retry Vite).
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
 * @param {{
 *   loadURL?: (url: string) => Promise<unknown>,
 *   loadFile?: (path: string) => Promise<unknown>,
 *   show: () => void,
 *   focus: () => void,
 *   close: () => void,
 *   isDestroyed?: () => boolean,
 *   webContents: { once: Function, removeListener: Function },
 * }} win
 * @param {{ reloadUrl?: string | null, loadFilePath?: string | null, closeOnFail?: boolean, label?: string }} opts
 */
export function loadRendererWindow(win, opts = {}) {
  const {
    reloadUrl = null,
    loadFilePath = null,
    closeOnFail = false,
    label = 'window',
  } = opts;
  const target = reloadUrl || loadFilePath || '';
  return new Promise((resolve) => {
    let settled = false;
    const done = (ok) => {
      if (settled) return;
      settled = true;
      resolve(ok);
    };
    const destroyed = () => typeof win.isDestroyed === 'function' && win.isDestroyed();
    const start = () => {
      if (reloadUrl) return win.loadURL(reloadUrl);
      if (loadFilePath) return win.loadFile(loadFilePath);
      return Promise.reject(new Error('no renderer URL'));
    };
    const onFail = (_event, code, desc) => {
      console.error('[nova]', label, 'load failed', target, code, desc);
      done(false);
      if (closeOnFail && !destroyed()) win.close();
    };
    win.webContents.once('did-fail-load', onFail);
    Promise.resolve(start())
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

/** Child Trader window: hide until load; close on chrome-error. */
export function loadTraderWindow(win, url) {
  return loadRendererWindow(win, {
    reloadUrl: url,
    closeOnFail: true,
    label: 'trader window',
  });
}

/** Host desk: hide until Vite/file loads; keep the window so guards can retry. */
export function loadHostWindow(win, { reloadUrl = null, loadFilePath = null } = {}) {
  return loadRendererWindow(win, {
    reloadUrl,
    loadFilePath,
    closeOnFail: false,
    label: 'host window',
  });
}
