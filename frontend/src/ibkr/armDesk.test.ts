/**
 * @vitest-environment jsdom
 *
 * ADR 018 -- the padlock drives a backend latch, not a per-tab flag.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest';

const mocks = vi.hoisted(() => ({
  fetch: vi.fn(),
  refresh: vi.fn(),
}));

vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));
vi.mock('./ibkrStatusPoller', () => ({ refreshIbkrStatusNow: mocks.refresh }));

import { armDesk } from './armDesk';

describe('armDesk', () => {
  beforeEach(() => {
    mocks.fetch.mockReset();
    mocks.refresh.mockReset();
  });

  it('posts the requested latch state to the backend', async () => {
    mocks.fetch.mockResolvedValue({ ok: true });
    await expect(armDesk(true)).resolves.toBe(true);

    expect(mocks.fetch).toHaveBeenCalledTimes(1);
    const [url, init] = mocks.fetch.mock.calls[0];
    expect(String(url)).toContain('/api/ibkr/arm');
    expect(init.method).toBe('POST');
    expect(JSON.parse(init.body)).toEqual({ armed: true });
  });

  it('posts a disarm as its own call', async () => {
    mocks.fetch.mockResolvedValue({ ok: true });
    await armDesk(false);
    expect(JSON.parse(mocks.fetch.mock.calls[0][1].body)).toEqual({ armed: false });
  });

  it('never throws when the backend is unreachable', async () => {
    mocks.fetch.mockRejectedValue(new Error('backend down'));
    await expect(armDesk(true)).resolves.toBe(false);
  });

  it('reports a refused arm as false rather than assuming success', async () => {
    mocks.fetch.mockResolvedValue({ ok: false });
    await expect(armDesk(true)).resolves.toBe(false);
  });

  it('re-reads status either way, so the padlock cannot drift from the server', async () => {
    mocks.fetch.mockRejectedValue(new Error('backend down'));
    await armDesk(false);
    expect(mocks.refresh).toHaveBeenCalledTimes(1);
  });
});
