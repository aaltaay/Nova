/**
 * Keep BrowserWindows off chrome-error://chromewebdata/ and recover a
 * crashed renderer instead of leaving File/Edit/View on a dark empty shell.
 *
 * Owner: main.mjs (main window) and traderWindows.mjs (pop-outs).
 */
import { isAllowedRendererUrl } from './traderWindowLoad.mjs';

const RELOAD_GONE_REASONS = new Set([
  'crashed',
  'oom',
  'launch-failed',
  'abnormal-exit',
  'integrity-failure',
]);

/** True when webContents is empty, chrome-error, or not our renderer. */
export function needsRendererRecover(url) {
  if (typeof url !== 'string' || !url.trim()) return true;
  return !isAllowedRendererUrl(url);
}

/**
 * Block navigations that would leave the Vite / packaged origin
 * (including chrome-error interstitials).
 */
export function shouldBlockNavigation(url, allowedBase) {
  if (!isAllowedRendererUrl(url)) return true;
  if (!allowedBase) return false;
  try {
    const next = new URL(url);
    if (allowedBase === 'file:' || String(allowedBase).startsWith('file:')) {
      return next.protocol !== 'file:';
    }
    const base = new URL(allowedBase);
    return next.origin !== base.origin;
  } catch {
    return true;
  }
}

export function shouldReloadAfterRendererGone(reason) {
  return RELOAD_GONE_REASONS.has(String(reason || ''));
}

export function reloadRenderer(win, { reloadUrl, loadFilePath } = {}) {
  if (typeof win?.isDestroyed === 'function' && win.isDestroyed()) return false;
  if (reloadUrl) {
    void win.loadURL(reloadUrl);
    return true;
  }
  if (loadFilePath) {
    void win.loadFile(loadFilePath);
    return true;
  }
  return false;
}

export function recoverWindowIfErrorPage(win, opts) {
  if (typeof win?.isDestroyed === 'function' && win.isDestroyed()) return false;
  const url = win.webContents?.getURL?.() ?? '';
  if (!needsRendererRecover(url)) return false;
  console.error('[nova] recovering error-page window', url || '(empty)');
  return reloadRenderer(win, opts);
}

/** Wake a compositor that left File/Edit/View on a black client area. */
export function pulseWindowPaint(win) {
  if (typeof win?.isDestroyed === 'function' && win.isDestroyed()) return false;
  const wc = win.webContents;
  if (!wc) return false;
  if (typeof wc.invalidate === 'function') wc.invalidate();
  return true;
}

/**
 * @param {{ webContents: { on: Function, getURL?: Function }, loadURL?: Function, loadFile?: Function, isDestroyed?: Function }} win
 * @param {{ allowedBase?: string, reloadUrl?: string | null, loadFilePath?: string | null, retryFail?: boolean }} opts
 */
export function attachRendererGuards(win, opts = {}) {
  const { allowedBase, reloadUrl, loadFilePath, retryFail = false } = opts;
  const contents = win.webContents;
  let failRetried = false;
  const recover = () => reloadRenderer(win, { reloadUrl, loadFilePath });

  contents.on('will-navigate', (event, url) => {
    if (!shouldBlockNavigation(url, allowedBase)) return;
    event.preventDefault();
    console.error('[nova] blocked navigation', url);
    if (needsRendererRecover(url)) recover();
  });

  if (retryFail) {
    contents.on('did-fail-load', (_event, code, desc, _url, isMainFrame) => {
      if (!isMainFrame || failRetried) return;
      if (typeof win.isDestroyed === 'function' && win.isDestroyed()) return;
      failRetried = true;
      console.error('[nova] window failed to load', code, desc);
      recover();
    });
  }

  contents.on('render-process-gone', (_event, details) => {
    const reason = details?.reason;
    console.error('[nova] render-process-gone', reason, details?.exitCode);
    if (shouldReloadAfterRendererGone(reason)) recover();
  });

  const paint = () => pulseWindowPaint(win);
  if (typeof win.on === 'function') {
    win.on('show', paint);
    win.on('restore', paint);
    win.on('focus', paint);
  }
}
