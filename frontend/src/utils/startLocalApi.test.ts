/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { canReloadLocalBackend, startLocalApi } from './startLocalApi';

describe('startLocalApi', () => {
  const originalDesktop = window.novaDesktop;

  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn());
    delete (window as { novaDesktop?: unknown }).novaDesktop;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    window.novaDesktop = originalDesktop;
  });

  it('uses Electron restartApi when desktop bridge is present', async () => {
    const restartApi = vi.fn().mockResolvedValue({ ok: true });
    window.novaDesktop = {
      isDesktop: true,
      apiBase: 'http://127.0.0.1:8000',
      getVersion: async () => 'test',
      restartApi,
    };
    vi.mocked(fetch).mockResolvedValue({ ok: true } as Response);

    const result = await startLocalApi();

    expect(restartApi).toHaveBeenCalledOnce();
    expect(result).toEqual({ ok: true, mode: 'electron' });
  });

  it('posts to Vite start-api path in dev when not desktop', async () => {
    vi.mocked(fetch).mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
    } as Response);

    const result = await startLocalApi();

    expect(fetch).toHaveBeenCalledWith('/__nova/start-api', { method: 'POST' });
    expect(result).toEqual({ ok: true, mode: 'vite-dev' });
  });

  it('canReloadLocalBackend is true in dev without desktop bridge', () => {
    expect(canReloadLocalBackend()).toBe(true);
  });

  it('canReloadLocalBackend is true on Electron desktop', () => {
    window.novaDesktop = {
      isDesktop: true,
      apiBase: 'http://127.0.0.1:8000',
      getVersion: async () => 'test',
      restartApi: async () => ({ ok: true }),
    };
    expect(canReloadLocalBackend()).toBe(true);
  });
});
