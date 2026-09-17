import { describe, expect, it, vi } from 'vitest';
import { fetchAccountCluster, fetchOrdersCluster } from './ibkrAccountFetch';

describe('ibkrAccountFetch', () => {
  it('reads account + positions together', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (String(url).includes('/account')) {
          return { ok: true, json: async () => ({ connected: true, NetLiquidation: 1 }) };
        }
        return { ok: true, json: async () => [{ symbol: 'SPCX', qty: 1 }] };
      }),
    );
    const snap = await fetchAccountCluster('http://test');
    expect(snap.summary?.NetLiquidation).toBe(1);
    expect(snap.positions?.[0]?.symbol).toBe('SPCX');
    expect(snap.failures).toEqual([]);
    vi.unstubAllGlobals();
  });

  it('records HTTP failures without throwing', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503 })));
    const snap = await fetchOrdersCluster('http://test');
    expect(snap.orders).toBeNull();
    expect(snap.failures).toEqual(['orders (HTTP 503)', 'closed orders (HTTP 503)']);
    vi.unstubAllGlobals();
  });
});
