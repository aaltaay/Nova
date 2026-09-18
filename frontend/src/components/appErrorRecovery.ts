/**
 * Detect fatal React shell/context errors that soft-remount cannot heal
 * (classic Vite HMR duplicate-module context skew, missing provider).
 */

export const APP_SHELL_RELOAD_SESSION_KEY = 'nova:auto-reload:shell';

const FATAL_SHELL_RE =
  /must be used within|Invalid hook call|Rendered more hooks than during|Rendered fewer hooks than during/i;

export function isFatalShellError(error: unknown): boolean {
  const msg =
    error instanceof Error
      ? error.message
      : typeof error === 'string'
        ? error
        : '';
  return FATAL_SHELL_RE.test(msg);
}

/** Only the outer app-shell boundary may hard-reload. A Trader/dashboard
 * pane that throws "must be used within" / Invalid hook call must keep the
 * header mounted -- a full reload while Vite is compiling the Stock View
 * chunk is how Electron ended on chrome-error://chromewebdata/. */
export const APP_SHELL_AUTO_RELOAD_SOURCE = 'app-shell';

export function shouldAutoReloadShell(
  source: string | undefined,
  error: unknown,
): boolean {
  return source === APP_SHELL_AUTO_RELOAD_SOURCE && isFatalShellError(error);
}

export function consumeShellAutoReloadSlot(
  storage: Storage | null = typeof sessionStorage !== 'undefined' ? sessionStorage : null,
): boolean {
  if (!storage) return false;
  try {
    if (storage.getItem(APP_SHELL_RELOAD_SESSION_KEY)) return false;
    storage.setItem(APP_SHELL_RELOAD_SESSION_KEY, '1');
    return true;
  } catch {
    return false;
  }
}

export function clearShellAutoReloadSlot(
  storage: Storage | null = typeof sessionStorage !== 'undefined' ? sessionStorage : null,
): void {
  if (!storage) return;
  try {
    storage.removeItem(APP_SHELL_RELOAD_SESSION_KEY);
  } catch {
    // ignore quota / private mode
  }
}
