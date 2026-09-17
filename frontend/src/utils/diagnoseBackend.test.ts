/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_HTTP,
  BACKEND_DIAG_FLAG_UNREACHABLE,
  BACKEND_DIAG_FLAG_WEDGED,
} from '../constants';
import { diagnoseBackend, healthAfterFailedRoute } from './diagnoseBackend';

describe('diagnoseBackend', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('flags API_DOWN on fast network failure', async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError('Failed to fetch'));
    const diag = await diagnoseBackend(500);
    expect(diag.flag).toBe(BACKEND_DIAG_FLAG_DOWN);
    expect(diag.message).toMatch(/not running/i);
  });

  it('flags API_WEDGED on AbortError / timeout', async () => {
    vi.mocked(fetch).mockRejectedValue(
      Object.assign(new Error('The operation was aborted'), { name: 'AbortError' }),
    );
    const diag = await diagnoseBackend(500);
    expect(diag.flag).toBe(BACKEND_DIAG_FLAG_WEDGED);
    expect(diag.message).toMatch(/hung/i);
  });

  it('flags API_HTTP on non-OK health status', async () => {
    vi.mocked(fetch).mockResolvedValue({ ok: false, status: 503 } as Response);
    const diag = await diagnoseBackend(500);
    expect(diag.ok).toBe(false);
    expect(diag.flag).toBe(BACKEND_DIAG_FLAG_HTTP);
    expect(diag.http_status).toBe(503);
  });

  it('treats HTTP 200 as ok -- never "Backend unreachable"', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ status: 'connected', latency_ms: 4 }),
    } as Response);
    const diag = await diagnoseBackend(500);
    expect(diag.ok).toBe(true);
    expect(diag.http_status).toBe(200);
    expect(diag.message).not.toMatch(/unreachable/i);
    expect(diag.health?.status).toBe('connected');
    expect(diag.flag).toBe(BACKEND_DIAG_FLAG_UNREACHABLE);
  });
});

describe('healthAfterFailedRoute', () => {
  it('keeps connected when health probe succeeded', () => {
    const next = healthAfterFailedRoute(
      { status: 'connected', latency_ms: 3, health_source: 'nova_process' },
      {
        ok: true,
        flag: BACKEND_DIAG_FLAG_UNREACHABLE,
        message: 'Nova API is reachable',
        hint: 'ok',
        http_status: 200,
        health: { status: 'connected', latency_ms: 5 },
      },
    );
    expect(next.status).toBe('connected');
    expect(next.flag).toBeUndefined();
    expect(next.latency_ms).toBe(5);
  });

  it('paints disconnected only when the probe failed', () => {
    const next = healthAfterFailedRoute(
      { status: 'connected', latency_ms: 3 },
      {
        ok: false,
        flag: BACKEND_DIAG_FLAG_DOWN,
        message: 'Backend not running',
        hint: 'start',
      },
    );
    expect(next.status).toBe('disconnected');
    expect(next.flag).toBe(BACKEND_DIAG_FLAG_DOWN);
  });
});
