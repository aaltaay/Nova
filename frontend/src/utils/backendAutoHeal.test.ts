/**
 * @vitest-environment jsdom
 */
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';
import {
  BACKEND_AUTO_HEAL_SESSION_KEY,
  canAutoHealBackendFlag,
  clearBackendAutoHealSlot,
  hasBackendAutoHealSlot,
  markBackendAutoHealUsed,
  maybeAutoHealBackend,
} from './backendAutoHeal';

vi.mock('./startLocalApi', () => ({
  startLocalApi: vi.fn(async () => ({ ok: true, mode: 'vite-dev' as const })),
}));

import { startLocalApi } from './startLocalApi';

describe('backendAutoHeal', () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.mocked(startLocalApi).mockClear();
    vi.stubGlobal('fetch', vi.fn(async () => {
      throw new TypeError('Failed to fetch');
    }));
  });

  afterEach(() => {
    sessionStorage.clear();
    vi.unstubAllGlobals();
  });

  it('never restarts a backend that answers /api/health -- the flag was stale', async () => {
    // 2026-09-29: the auto-heal's reload stopped the engine a restart had just brought up.
    vi.stubGlobal('fetch', vi.fn(async () => new Response('{}', { status: 200 })));
    const result = await maybeAutoHealBackend('API_DOWN');
    expect(result).toBeNull();
    expect(startLocalApi).not.toHaveBeenCalled();
    expect(hasBackendAutoHealSlot()).toBe(true);
  });

  it('only heals DOWN -- never WEDGED', () => {
    expect(canAutoHealBackendFlag('API_WEDGED')).toBe(false);
    expect(canAutoHealBackendFlag('API_DOWN')).toBe(true);
    expect(canAutoHealBackendFlag('API_HTTP')).toBe(false);
  });

  it('maybeAutoHealBackend(API_WEDGED) is null', async () => {
    const result = await maybeAutoHealBackend('API_WEDGED');
    expect(result).toBeNull();
    expect(startLocalApi).not.toHaveBeenCalled();
  });

  it('consumes one session slot on API_DOWN', async () => {
    expect(hasBackendAutoHealSlot()).toBe(true);
    const first = await maybeAutoHealBackend('API_DOWN');
    expect(first?.ok).toBe(true);
    expect(sessionStorage.getItem(BACKEND_AUTO_HEAL_SESSION_KEY)).toBe('1');
    expect(startLocalApi).toHaveBeenCalledOnce();

    const second = await maybeAutoHealBackend('API_DOWN');
    expect(second).toBeNull();
    expect(startLocalApi).toHaveBeenCalledOnce();

    clearBackendAutoHealSlot();
    markBackendAutoHealUsed();
    expect(hasBackendAutoHealSlot()).toBe(false);
  });
});
