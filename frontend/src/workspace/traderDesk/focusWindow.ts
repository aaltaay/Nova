/**
 * Bring this window forward after another window asked it to act (the Top 9 pop-up's double-click).
 * The desktop app raises the BrowserWindow; a browser may ignore `window.focus()`.
 */
export function focusThisWindow(): void {
  try {
    if (typeof window.novaDesktop?.focusWindow === 'function') {
      void window.novaDesktop.focusWindow();
      return;
    }
  } catch (err) {
    console.debug('[nova] the desktop app did not raise this window', err);
  }
  try {
    window.focus();
  } catch {
    /* a browser that refuses focus leaves the window where it is */
  }
}
