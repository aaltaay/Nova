import { beforeEach, describe, expect, it, vi } from 'vitest';

const novaFetch = vi.fn();

vi.mock('../api/novaFetch', () => ({
  novaFetch: (...args: unknown[]) => novaFetch(...args),
}));

import { flattenAccount } from './flattenAccount';

describe('flattenAccount', () => {
  beforeEach(() => {
    novaFetch.mockReset();
  });

  it('POSTs the existing breaker flatten door', async () => {
    novaFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, attempt: 1, results: [], error: null }),
    });
    const result = await flattenAccount();
    expect(novaFetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/ibkr\/flatten-account$/),
      { method: 'POST' },
    );
    expect(result).toEqual({
      ok: true,
      error: null,
      results: [],
      cancels: undefined,
      attempt: 1,
    });
  });

  it('surfaces a failed flatten without inventing a second place path', async () => {
    novaFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ ok: false, error: 'IBKR not connected -- cannot flatten' }),
    });
    const result = await flattenAccount();
    expect(result.ok).toBe(false);
    expect(result.error).toMatch(/IBKR not connected/);
  });
});
