/**
 * Daily Electron→Vite should not detach DevTools (main-thread cost).
 * Packaged builds never open them. Opt in with NOVA_ELECTRON_DEVTOOLS=1.
 */
export function shouldOpenDetachedDevTools(isDev, env = process.env) {
  if (!isDev) return false;
  const raw = String(env.NOVA_ELECTRON_DEVTOOLS ?? '').trim().toLowerCase();
  return raw === '1' || raw === 'true' || raw === 'yes';
}
