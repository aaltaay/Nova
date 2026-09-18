/**
 * One unpackaged Electron app at a time. Start-NovaDevDesktop.ps1 launches
 * `electron .` on every run; without a lock those pile up and a dead
 * chrome-error window stays focused.
 */

export function applySingleInstance(app, onSecondInstance) {
  if (!app.requestSingleInstanceLock()) return false;
  app.on('second-instance', () => {
    onSecondInstance?.();
  });
  return true;
}

export function focusExistingWindow(win, recover) {
  if (!win || (typeof win.isDestroyed === 'function' && win.isDestroyed())) {
    return false;
  }
  recover?.(win);
  if (typeof win.isMinimized === 'function' && win.isMinimized()) {
    win.restore();
  }
  win.show();
  win.focus();
  return true;
}
