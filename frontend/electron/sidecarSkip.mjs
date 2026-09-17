/**
 * Lock A: daily UI roll-out attaches to an already-running API.
 * When set, Electron must not spawn, recycle, or Stop-NovaPorts :8000.
 */
export function skipApiSidecar(env = process.env) {
  const raw = String(env.NOVA_SKIP_API_SIDECAR ?? '').trim().toLowerCase();
  return raw === '1' || raw === 'true' || raw === 'yes';
}
