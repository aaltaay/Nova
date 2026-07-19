/**
 * Ask the local Nova API to start or focus IB Gateway (Windows).
 * Browser cannot spawn desktop apps — the API (or Vite-dev middleware) does.
 */
import { API_URL, NOVA_LAUNCH_GATEWAY_DEV_PATH } from '../constants';
import { novaFetch } from '../api/novaFetch';

export type LaunchIbGatewayResult = {
  ok: boolean;
  action?: string;
  message: string;
  path?: string;
};

function parseBody(body: Record<string, unknown>): LaunchIbGatewayResult {
  const detail = typeof body.detail === 'string' ? body.detail : undefined;
  const message =
    (typeof body.message === 'string' && body.message) ||
    detail ||
    'Launch failed.';
  return {
    ok: Boolean(body.ok),
    action: typeof body.action === 'string' ? body.action : undefined,
    message,
    path: typeof body.path === 'string' ? body.path : undefined,
  };
}

async function postLaunch(url: string): Promise<{ httpOk: boolean; result: LaunchIbGatewayResult }> {
  const res = await novaFetch(url, { method: 'POST' });
  const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
  const parsed = parseBody(body);
  if (!res.ok) {
    return {
      httpOk: false,
      result: {
        ok: false,
        action: parsed.action,
        message: parsed.message.includes('Launch failed')
          ? `Launch failed (HTTP ${res.status})`
          : parsed.message,
        path: parsed.path,
      },
    };
  }
  return {
    httpOk: true,
    result: {
      ok: parsed.ok,
      action: parsed.action,
      message:
        parsed.message ||
        (parsed.ok ? 'IB Gateway launch requested.' : 'Launch failed.'),
      path: parsed.path,
    },
  };
}

async function launchViaViteDev(): Promise<LaunchIbGatewayResult | null> {
  if (!import.meta.env.DEV) return null;
  try {
    const res = await fetch(NOVA_LAUNCH_GATEWAY_DEV_PATH, { method: 'POST' });
    const body = (await res.json().catch(() => ({}))) as Record<string, unknown>;
    const parsed = parseBody(body);
    if (!res.ok) {
      return {
        ok: false,
        action: parsed.action,
        message: parsed.message || `Vite launch failed (HTTP ${res.status})`,
      };
    }
    return {
      ok: parsed.ok,
      action: parsed.action ?? 'launched_vite',
      message: parsed.message || 'IB Gateway launch requested (Vite).',
      path: parsed.path,
    };
  } catch {
    return null;
  }
}

export async function launchIbGateway(): Promise<LaunchIbGatewayResult> {
  try {
    const primary = await postLaunch(`${API_URL}/ibkr/launch-gateway`);
    if (primary.httpOk) return primary.result;

    // Stale API without the route → Vite can still spawn Gateway in local dev.
    if (primary.result.message.includes('404') || primary.result.message.includes('Not Found')) {
      const viaVite = await launchViaViteDev();
      if (viaVite) return viaVite;
      return {
        ok: false,
        action: 'api_stale',
        message:
          'API is missing launch-gateway (restart Nova API), then double-click Gateway again.',
      };
    }
    return primary.result;
  } catch (err) {
    const viaVite = await launchViaViteDev();
    if (viaVite) return viaVite;
    return {
      ok: false,
      message: err instanceof Error ? err.message : String(err),
    };
  }
}
