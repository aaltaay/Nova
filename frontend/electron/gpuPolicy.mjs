/**
 * Windows Electron can paint a black webContents while JS still runs
 * (native title updates -- `AEMD · Trader · Nova · v477`). Two traps:
 *
 * 1. Chromium `CalculateNativeWinOcclusion` stops presenting frames.
 * 2. GPU compositor + lightweight-charts canvases go black on win32.
 *
 * Software raster is the default on Windows. `NOVA_ELECTRON_GPU=1` keeps
 * GPU (occlusion switches still apply). `NOVA_ELECTRON_GPU=0` forces
 * software on any platform.
 *
 * Must run before `app.whenReady()`. Do not set `backgroundThrottling:
 * false` for the life of the window -- that can evict frames after idle
 * (Electron #42378).
 */

export const WIN32_DISABLE_FEATURES = 'CalculateNativeWinOcclusion';

export function shouldDisableHardwareAcceleration(
  env = process.env,
  platform = process.platform,
) {
  const raw = String(env.NOVA_ELECTRON_GPU ?? '').trim().toLowerCase();
  if (raw === '1' || raw === 'true' || raw === 'yes') return false;
  if (raw === '0' || raw === 'false' || raw === 'no') return true;
  return platform === 'win32';
}

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

export function applyGpuPolicy(app, env = process.env, platform = process.platform) {
  applyWin32PaintSwitches(app, platform);
  if (!shouldDisableHardwareAcceleration(env, platform)) return false;
  applySoftwareRasterSwitches(app);
  return true;
}
