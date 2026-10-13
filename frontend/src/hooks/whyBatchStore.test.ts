import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { catalystKey, WhyBatchStore } from './whyBatchStore';

function answer(symbol: string, kind = 'low_float_momentum') {
  return { schema_version: 1, symbol, generated_at: 1, rules_version: 'v5', replay: false,
    likely: { kind, label: kind, detail: null, confidence: 'likely', steps: [] }, checks: [], facts: {} };
}

function ok(body: unknown): Response {
  return { ok: true, status: 200, json: async () => body } as unknown as Response;
}

describe('WhyBatchStore', () => {
  beforeEach(() => { vi.useFakeTimers(); });
  afterEach(() => { vi.useRealTimers(); });

  it('reads every cell of a board in one request, per board', async () => {
    const urls: string[] = [];
    const store = new WhyBatchStore(async url => {
      urls.push(url);
      const q = new URL(url, 'http://x').searchParams;
      const syms = (q.get('symbols') ?? '').split(',');
      return ok({ reads: Object.fromEntries(syms.map(s => [s, answer(s)])), errors: {} });
    });
    const seen: string[] = [];
    store.subscribe(catalystKey('MNDR', 'gappers'), () => seen.push('MNDR'));
    store.subscribe(catalystKey('LNKS', 'gappers'), () => seen.push('LNKS'));
    store.subscribe(catalystKey('CLWT', null), () => seen.push('CLWT'));
    await vi.advanceTimersByTimeAsync(100);
    expect(urls).toHaveLength(2);
    expect(urls.find(u => u.includes('board=gappers'))).toContain('symbols=MNDR%2CLNKS');
    expect(urls.find(u => !u.includes('board='))).toContain('symbols=CLWT');
    expect(store.getSnapshot(catalystKey('MNDR', 'gappers')).read?.likely.kind).toBe('low_float_momentum');
    expect(seen.sort()).toEqual(['CLWT', 'LNKS', 'MNDR']);
  });

  it('one failed read says so and keeps the last good one; a 404 falls back to the news mark', async () => {
    let fail = false;
    const store = new WhyBatchStore(async () => ok(fail
      ? { reads: { MNDR: null }, errors: { MNDR: 'RuntimeError: no row' } }
      : { reads: { MNDR: answer('MNDR') }, errors: {} }));
    const key = catalystKey('MNDR', 'gappers');
    store.subscribe(key, () => {});
    await vi.advanceTimersByTimeAsync(100);
    fail = true;
    await vi.advanceTimersByTimeAsync(60_000 + 100);
    const state = store.getSnapshot(key);
    expect(state.read?.symbol).toBe('MNDR');
    expect(state.error).toBe('Read failed: RuntimeError: no row');

    const old = new WhyBatchStore(async () => ({ ok: false, status: 404, json: async () => ({}) }) as unknown as Response);
    old.subscribe(key, () => {});
    await vi.advanceTimersByTimeAsync(100);
    expect(old.isUnavailable()).toBe(true);
  });

  it('a Sim rewind drops every read and throws away an answer in flight', async () => {
    const resolvers: Array<(r: Response) => void> = [];
    const store = new WhyBatchStore(() => new Promise<Response>(resolve => { resolvers.push(resolve); }));
    const key = catalystKey('SDEV', 'gainers');
    store.setPlayhead(1_000_000);
    store.subscribe(key, () => {});
    await vi.advanceTimersByTimeAsync(100);
    expect(resolvers).toHaveLength(1);
    store.setPlayhead(999_000);  // rewind while the first read is in flight
    resolvers[0](ok({ reads: { SDEV: answer('SDEV', 'unexplained') }, errors: {} }));
    await vi.advanceTimersByTimeAsync(0);
    expect(store.getSnapshot(key).read).toBeNull();
    await vi.advanceTimersByTimeAsync(100);
    expect(resolvers).toHaveLength(2);
    resolvers[1](ok({ reads: { SDEV: answer('SDEV', 'news') }, errors: {} }));
    await vi.advanceTimersByTimeAsync(0);
    expect(store.getSnapshot(key).read?.likely.kind).toBe('news');
  });
});
