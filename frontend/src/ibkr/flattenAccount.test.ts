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

  it('POSTs the existing whole-account flatten door', async () => {
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

  it('names the venue KILL was pressed on', async () => {
    novaFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, attempt: 1, results: [], error: null }),
    });
    await flattenAccount('paper');
    expect(novaFetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/ibkr\/flatten-account\?venue=paper$/),
      { method: 'POST' },
    );
  });

  it('names none before a status has said one', async () => {
    novaFetch.mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true, attempt: 1, results: [], error: null }),
    });
    await flattenAccount(null);
    expect(novaFetch).toHaveBeenCalledWith(
      expect.stringMatching(/\/api\/ibkr\/flatten-account$/),
      { method: 'POST' },
    );
  });

  it('passes on what a stopped flatten says is still open', async () => {
    const error = 'The desk moved from Live to Paper, so KILL stopped and sent nothing to Paper. '
      + 'Still open on Live: ABCD 100.';
    novaFetch.mockResolvedValue({ ok: true, json: async () => ({ ok: false, error }) });
    const result = await flattenAccount('live');
    expect(result).toMatchObject({ ok: false, error });
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
