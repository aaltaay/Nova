/**
 * Windows Electron could paint a black webContents while JS still ran
 * (native title updates -- `AEMD · Trader · Nova · v477`, 2026-09-17).
 * Chromium's `CalculateNativeWinOcclusion` stops presenting frames, so it is
 * off on Windows whatever else is chosen.
 *
 * Whether the desk draws with the graphics card is graphicsChoice.mjs's: the
 * graphics card by default (2026-10-05), software when the operator, a crash
 * of the graphics process or a blank window (graphicsWatch.mjs) turned it off,
 * and `NOVA_ELECTRON_GPU=1` / `0` over both.
 *
 * Must run before `app.whenReady()`. Do not set `backgroundThrottling:
 * false` for the life of the window -- that can evict frames after idle
 * (Electron #42378).
 */
import { decideGraphics, readChoice } from './graphicsChoice.mjs';

export const WIN32_DISABLE_FEATURES = 'CalculateNativeWinOcclusion';

export function mergeDisableFeatures(existing, extra) {
  const parts = new Set(
    String(existing || '')
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean),
  );
  for (const item of String(extra || '').split(',')) {
    const t = item.trim();
    if (t) parts.add(t);
  }
  return [...parts].join(',');
}

export function applyWin32PaintSwitches(app, platform = process.platform) {
  if (platform !== 'win32') return false;
  const cmd = app.commandLine;
  if (!cmd?.appendSwitch) return false;
  const existing =
    typeof cmd.getSwitchValue === 'function' ? cmd.getSwitchValue('disable-features') : '';
  cmd.appendSwitch(
    'disable-features',
    mergeDisableFeatures(existing, WIN32_DISABLE_FEATURES),
  );
  cmd.appendSwitch('disable-backgrounding-occluded-windows');
  return true;
}

export function applySoftwareRasterSwitches(app) {
  app.disableHardwareAcceleration();
  app.commandLine?.appendSwitch?.('disable-gpu-compositing');
  app.commandLine?.appendSwitch?.('disable-direct-composition');
}

/**
 * Apply how this start draws; returns graphicsChoice.decideGraphics's decision. `dir` is the
 * app's userData, where the operator's choice is kept (none: the graphics card unless the env says).
 */
export function applyGpuPolicy(app, env = process.env, platform = process.platform, dir = null) {
  applyWin32PaintSwitches(app, platform);
  const decision = decideGraphics({ env, read: dir ? readChoice(dir) : { choice: null, error: null } });
  if (decision.error) console.warn(`[nova] graphics: ${decision.error}${decision.gpu ? '' : '; drawing in software'}`);
  if (!decision.gpu) applySoftwareRasterSwitches(app);
  return decision;
}
