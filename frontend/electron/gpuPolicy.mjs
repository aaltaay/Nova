/**
 * Windows Electron + Trader charts can paint a black webContents while JS
 * still runs (native title updates). Software raster is the safe default.
 *
 * Opt back into GPU with NOVA_ELECTRON_GPU=1.
 * Force software with NOVA_ELECTRON_GPU=0.
 *
 * Must run before app.whenReady().
 */

export function shouldDisableHardwareAcceleration(
  env = process.env,
  platform = process.platform,
) {
  const raw = String(env.NOVA_ELECTRON_GPU ?? '').trim().toLowerCase();
  if (raw === '1' || raw === 'true' || raw === 'yes') return false;
  if (raw === '0' || raw === 'false' || raw === 'no') return true;
  return platform === 'win32';
}

export function applyGpuPolicy(app, env = process.env, platform = process.platform) {
  if (!shouldDisableHardwareAcceleration(env, platform)) return false;
  app.disableHardwareAcceleration();
  return true;
}
