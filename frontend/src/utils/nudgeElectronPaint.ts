/** True in the Electron renderer (not Vite-in-Chrome). */
export function isElectronRenderer(ua = globalThis.navigator?.userAgent ?? ''): boolean {
  return /Electron/i.test(ua);
}

/**
 * Wake a stuck Chromium compositor after Scanner→Trader.
 * Title can update while the client area stays `--bg-color` (#000).
 */
export function nudgeElectronPaint(doc: Document | null = globalThis.document): void {
  const root = doc?.documentElement;
  if (!root) return;
  const prev = root.style.transform;
  root.style.transform = 'translateZ(0)';
  void root.offsetHeight;
  const clear = () => {
    root.style.transform = prev;
  };
  if (typeof requestAnimationFrame === 'function') {
    requestAnimationFrame(clear);
    return;
  }
  clear();
}
