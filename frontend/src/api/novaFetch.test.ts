/**
 * @vitest-environment jsdom
 */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { novaFetch } from './novaFetch';
import { NOVA_API_KEY_HEADER } from '../constantGroups/api_auth';

describe('novaFetch', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    delete (window as { novaDesktop?: unknown }).novaDesktop;
    localStorage.clear();
  });

  it('sends the desktop sidecar key first', async () => {
    window.novaDesktop = {
      isDesktop: true,
      apiBase: 'http://127.0.0.1:8000',
      apiKey: 'desktop-secret',
      getVersion: async () => 'test',
    };
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await novaFetch('http://127.0.0.1:8000/api/config', { method: 'POST' });

    const headers = new Headers(fetchMock.mock.calls[0][1].headers);
    expect(headers.get(NOVA_API_KEY_HEADER)).toBe('desktop-secret');
  });
});
