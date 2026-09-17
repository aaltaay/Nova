import { describe, expect, it, vi } from 'vitest';
import { syncTraderLive } from './api';

describe('bot api', () => {
  it('posts trader live symbols for Eyes honesty', async () => {
    const fetchMock = vi.fn(async () => ({ ok: true, json: async () => ({}) }));
    vi.stubGlobal('fetch', fetchMock);
    await syncTraderLive(['AAPL', 'MSFT']);
    expect(fetchMock).toHaveBeenCalled();
    const [url, init] = fetchMock.mock.calls[0];
    expect(String(url)).toContain('/bot/focus/sync');
    expect((init as RequestInit).method).toBe('POST');
    expect(String((init as RequestInit).body)).toContain('AAPL');
    vi.unstubAllGlobals();
  });
});
