/** @vitest-environment jsdom */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { replayPollResource } from './replayPollResource';
import { replayRequest } from './replayRequest';

const mocks = vi.hoisted(() => ({ fetch: vi.fn() }));
vi.mock('../api/novaFetch', () => ({ novaFetch: mocks.fetch }));

const json = (body: unknown, status = 200) => ({
  ok: status < 400, status, headers: new Headers({ 'content-type': 'application/json' }),
  text: async () => JSON.stringify(body),
});
const plain = (body: string, status: number, type = 'text/plain; charset=utf-8') => ({
  ok: false, status, headers: new Headers({ 'content-type': type }), text: async () => body,
});

beforeEach(() => {
  vi.useFakeTimers();
  mocks.fetch.mockReset();
});
afterEach(() => vi.useRealTimers());

describe('replayRequest failure messages (C57)', () => {
  it('quotes a short text/plain body (a Starlette 500) and names no feature it is not', async () => {
    mocks.fetch.mockResolvedValueOnce(plain('Internal Server Error', 500));
    await expect(replayRequest('/api/capture/sessions')).rejects.toThrow('Nova request failed (500): Internal Server Error');
  });

  it('never pastes an HTML error page; the server detail wins when there is one', async () => {
    mocks.fetch.mockResolvedValueOnce(plain('<html><body>Bad Gateway</body></html>', 502, 'text/html'));
    await expect(replayRequest('/clock', {}, 'Sim clock request failed')).rejects.toThrow(/^Sim clock request failed \(502\)$/);
    mocks.fetch.mockResolvedValueOnce(json({ detail: 'No data for that window' }, 422));
    await expect(replayRequest('/history/select')).rejects.toThrow(/^No data for that window$/);
  });
});

describe('replayPollResource', () => {
  it('parses every answer at the boundary; an unparsable one is a failed poll that keeps the last good data', async () => {
    const parse = vi.fn((raw: unknown) => {
      if (!raw || typeof raw !== 'object' || !('n' in raw)) throw new Error('unreadable');
      return raw as { n: number };
    });
    mocks.fetch.mockResolvedValueOnce(json({ n: 1 })).mockResolvedValueOnce(json({ other: true }));
    const resource = replayPollResource<{ n: number }>('/x', () => 1000, { parse });
    const listener = vi.fn();
    const unsubscribe = resource.subscribe(listener);
    await vi.advanceTimersByTimeAsync(0);
    expect(resource.getSnapshot()).toEqual({ data: { n: 1 }, error: null, stale: false });
    await vi.advanceTimersByTimeAsync(1000);
    expect(resource.getSnapshot()).toEqual({ data: { n: 1 }, error: 'unreadable', stale: true });
    unsubscribe();
  });

  it('stamps kept data stale on a failed poll, and drops it once older than maxStaleMs (C44)', async () => {
    mocks.fetch.mockResolvedValueOnce(json({ n: 1 })).mockResolvedValue(plain('Internal Server Error', 500));
    const resource = replayPollResource<{ n: number }>('/api/practice/account?venue=paper', () => 1000,
      { failure: 'Practice account request failed', maxStaleMs: 2500 });
    const unsubscribe = resource.subscribe(() => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(resource.getSnapshot().data).toEqual({ n: 1 });
    await vi.advanceTimersByTimeAsync(1000);
    expect(resource.getSnapshot()).toMatchObject({ data: { n: 1 }, stale: true, error: 'Practice account request failed (500): Internal Server Error' });
    await vi.advanceTimersByTimeAsync(2000);
    expect(resource.getSnapshot()).toMatchObject({ data: null, stale: false });
    expect(resource.getSnapshot().error).toMatch(/Practice account request failed \(500\)/);
    unsubscribe();
  });

  it('command replies handed in with setData pass the same parse; a bad one keeps the good data', async () => {
    mocks.fetch.mockResolvedValue(json({ n: 1 }));
    const parse = (raw: unknown) => {
      if (!raw || typeof raw !== 'object' || !('n' in raw)) throw new Error('unreadable reply');
      return raw as { n: number };
    };
    const resource = replayPollResource<{ n: number }>('/x', () => 60_000, { parse });
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
    const unsubscribe = resource.subscribe(() => {});
    await vi.advanceTimersByTimeAsync(0);
    resource.setData({ n: 2 });
    expect(resource.getSnapshot().data).toEqual({ n: 2 });
    resource.setData({ wrong: true } as unknown as { n: number });
    expect(resource.getSnapshot()).toMatchObject({ data: { n: 2 }, error: 'unreadable reply', stale: true });
    expect(warn).toHaveBeenCalled();
    unsubscribe();
  });
});
