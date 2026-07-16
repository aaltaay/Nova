/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  BACKEND_DIAG_FLAG_DOWN,
  BACKEND_DIAG_FLAG_HTTP,
  BACKEND_DIAG_FLAG_WEDGED,
} from '../constants';
import { diagnoseBackend } from './diagnoseBackend';

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
    expect(diag.flag).toBe(BACKEND_DIAG_FLAG_HTTP);
    expect(diag.http_status).toBe(503);
  });
});
