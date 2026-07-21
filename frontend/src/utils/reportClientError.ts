/**
 * POST browser errors to the API for structured logging (fire-and-forget).
 */
import { API_URL, CLIENT_ERROR_REPORT_ENABLED } from '../constants';

export type ClientErrorReport = {
  message: string;
  stack?: string | null;
  componentStack?: string | null;
  source: string;
  url?: string;
};

/** Vite HMR / overlay internals — not product bugs; do not POST. */
export function isDevToolingNoise(message: string, stack?: string | null): boolean {
  const msg = String(message || '');
  const stk = String(stack || '');
  if (stk.includes('@vite/client') || stk.includes('/@vite/client')) return true;
  // Vite throws this when its error-overlay WS is not open yet.
  if (msg === 'send was called before connect') return true;
  if (msg.includes("reading 'send'") && stk.toLowerCase().includes('vite')) return true;
  return false;
}

export function reportClientError(report: ClientErrorReport): void {
  if (!CLIENT_ERROR_REPORT_ENABLED) return;
  if (isDevToolingNoise(report.message, report.stack)) return;
  try {
    const payload = {
      message: String(report.message || '').slice(0, 2000),
      stack: report.stack ? String(report.stack).slice(0, 2000) : null,
      component_stack: report.componentStack
        ? String(report.componentStack).slice(0, 2000)
        : null,
      source: String(report.source || 'unknown').slice(0, 64),
      url: typeof window !== 'undefined' ? window.location.href.slice(0, 512) : report.url,
      user_agent: typeof navigator !== 'undefined' ? navigator.userAgent.slice(0, 512) : null,
      ts: Date.now() / 1000,
    };
    void fetch(`${API_URL}/client-errors`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch((err) => {
      /* never throw from reporter — console only */
      console.debug('[Nova] client-error report POST failed', err);
    });
  } catch (err) {
    console.debug('[Nova] reportClientError swallowed', err);
  }
}
