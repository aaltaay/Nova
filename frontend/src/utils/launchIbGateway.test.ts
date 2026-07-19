/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { launchIbGateway } from './launchIbGateway';

describe('launchIbGateway', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('posts to launch-gateway and returns the API payload', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ok: true,
        action: 'launched',
        message: 'Started IB Gateway',
        path: 'C:\\\\Jts\\\\ibgateway\\\\1045\\\\ibgateway.exe',
      }),
    });
    vi.stubGlobal('fetch', fetchMock);

    const result = await launchIbGateway();
    expect(result.ok).toBe(true);
    expect(result.action).toBe('launched');
    expect(fetchMock).toHaveBeenCalledOnce();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(String(url)).toContain('/api/ibkr/launch-gateway');
    expect(init.method).toBe('POST');
  });

  it('falls back to Vite middleware when API returns 404', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({
        ok: false,
        status: 404,
        json: async () => ({ detail: 'Not Found' }),
      })
      .mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          ok: true,
          action: 'launched',
          message: 'Started via Vite',
        }),
      });
    vi.stubGlobal('fetch', fetchMock);

    const result = await launchIbGateway();
    expect(result.ok).toBe(true);
    expect(result.message).toMatch(/Vite/i);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1][0])).toContain('/__nova/launch-gateway');
  });

  it('surfaces non-404 HTTP failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 503,
        json: async () => ({ message: 'API key required' }),
      }),
    );
    const result = await launchIbGateway();
    expect(result.ok).toBe(false);
    expect(result.message).toMatch(/API key/);
  });
});
