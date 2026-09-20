/**
 * @vitest-environment jsdom
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { novaFetch, resolveNovaApiKey } from './novaFetch';
import { NOVA_API_KEY_HEADER, NOVA_API_KEY_STORAGE } from '../constantGroups/api_auth';

describe('novaFetch', () => {
  beforeEach(() => {
    // State the precondition instead of inheriting it (#293): resolveNovaApiKey
    // prefers an env key over localStorage, so an operator key leaking into
    // import.meta.env used to fail the localStorage case -- and print that key
    // in the assertion diff.
    vi.stubEnv('VITE_NOVA_API_KEY', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    delete (window as { novaDesktop?: unknown }).novaDesktop;
    localStorage.clear();
  });

  it('resolves no key when nothing is configured', () => {
    // Guards the pinned Vitest env: this fails the moment a real machine's
    // NOVA_API_KEY reaches import.meta.env again.
    vi.unstubAllEnvs();
    expect(resolveNovaApiKey()).toBe('');
  });

  it('prefers a Vite-injected key over localStorage', () => {
    vi.stubEnv('VITE_NOVA_API_KEY', 'vite-injected-key');
    localStorage.setItem(NOVA_API_KEY_STORAGE, 'vite-stored-key');
    expect(resolveNovaApiKey()).toBe('vite-injected-key');
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

  it('sends localStorage nova_api_key when Desktop is absent', async () => {
    localStorage.setItem(NOVA_API_KEY_STORAGE, 'vite-stored-key');
    expect(resolveNovaApiKey()).toBe('vite-stored-key');
    const fetchMock = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetchMock);

    await novaFetch('http://127.0.0.1:8000/api/bot/session', { method: 'PATCH' });

    const headers = new Headers(fetchMock.mock.calls[0][1].headers);
    expect(headers.get(NOVA_API_KEY_HEADER)).toBe('vite-stored-key');
  });
});
