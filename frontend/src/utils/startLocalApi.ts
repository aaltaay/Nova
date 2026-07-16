/**
 * Bring the local Nova API back when the UI shows "Backend unreachable".
 *
 * Order:
 * 1) Electron desktop — restart the sidecar via IPC
 * 2) Vite dev — POST /__nova/start-api (kills port 8000, opens Nova — API window)
 * 3) Otherwise — probe /api/health only (Reconnect; cannot spawn processes in prod web)
 */
import {
  API_URL,
  NOVA_START_API_DEV_PATH,
  NOVA_START_API_HEALTH_TIMEOUT_MS,
} from '../constants';

export type StartLocalApiResult =
  | { ok: true; mode: 'electron' | 'vite-dev' | 'health-only' }
  | { ok: false; mode: 'electron' | 'vite-dev' | 'health-only'; error: string };

async function waitForHealth(timeoutMs: number): Promise<boolean> {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    try {
      const res = await fetch(`${API_URL}/health`, { cache: 'no-store' });
      if (res.ok) return true;
    } catch {
      // still down
    }
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

export async function startLocalApi(): Promise<StartLocalApiResult> {
  const desktop = typeof window !== 'undefined' ? window.novaDesktop : undefined;
  if (desktop?.isDesktop && typeof desktop.restartApi === 'function') {
    try {
      const result = await desktop.restartApi();
      if (result && result.ok === false) {
        return {
          ok: false,
          mode: 'electron',
          error: result.error || 'Electron restartApi failed',
        };
      }
      const up = await waitForHealth(NOVA_START_API_HEALTH_TIMEOUT_MS);
      if (!up) {
        return { ok: false, mode: 'electron', error: 'API restarted but health check timed out' };
      }
      return { ok: true, mode: 'electron' };
    } catch (err) {
      return {
        ok: false,
        mode: 'electron',
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }

  // Vite only exposes this middleware in `npm run dev` (same origin as the UI).
  if (import.meta.env.DEV) {
    try {
      const res = await fetch(NOVA_START_API_DEV_PATH, { method: 'POST' });
      const body = (await res.json().catch(() => ({}))) as { ok?: boolean; error?: string };
      if (!res.ok || !body.ok) {
        return {
          ok: false,
          mode: 'vite-dev',
          error: body.error || `Start API failed (HTTP ${res.status})`,
        };
      }
      return { ok: true, mode: 'vite-dev' };
    } catch (err) {
      return {
        ok: false,
        mode: 'vite-dev',
        error: err instanceof Error ? err.message : String(err),
      };
    }
  }

  const up = await waitForHealth(8_000);
  if (up) return { ok: true, mode: 'health-only' };
  return {
    ok: false,
    mode: 'health-only',
    error: 'Backend still unreachable. Double-click Run Nova.bat in the Nova folder.',
  };
}
