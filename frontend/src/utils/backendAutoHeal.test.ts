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
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('only heals WEDGED / DOWN flags', () => {
    expect(canAutoHealBackendFlag('API_WEDGED')).toBe(true);
    expect(canAutoHealBackendFlag('API_DOWN')).toBe(true);
    expect(canAutoHealBackendFlag('API_HTTP')).toBe(false);
  });

  it('consumes one session slot', async () => {
    expect(hasBackendAutoHealSlot()).toBe(true);
    const first = await maybeAutoHealBackend('API_WEDGED');
    expect(first?.ok).toBe(true);
    expect(sessionStorage.getItem(BACKEND_AUTO_HEAL_SESSION_KEY)).toBe('1');
    expect(startLocalApi).toHaveBeenCalledOnce();

    const second = await maybeAutoHealBackend('API_WEDGED');
    expect(second).toBeNull();
    expect(startLocalApi).toHaveBeenCalledOnce();

    clearBackendAutoHealSlot();
    markBackendAutoHealUsed();
    expect(hasBackendAutoHealSlot()).toBe(false);
  });
});
