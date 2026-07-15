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

export function reportClientError(report: ClientErrorReport): void {
  if (!CLIENT_ERROR_REPORT_ENABLED) return;
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
    }).catch(() => {
      /* never throw from reporter */
    });
  } catch {
    /* never throw from reporter */
  }
}
