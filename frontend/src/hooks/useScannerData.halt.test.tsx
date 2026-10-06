// @vitest-environment jsdom
import { act, cleanup, renderHook, waitFor } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import { useScannerData } from './useScannerData';
import type { ScannerRosterHandlers } from './useScannerPriceStream';

const stream = vi.hoisted(() => ({ handlers: null as ScannerRosterHandlers | null }));
vi.mock('./useScannerPriceStream', () => ({
  useScannerPriceStream: (handlers: ScannerRosterHandlers) => {
    stream.handlers = handlers;
    return { pricesStale: false, flashSymbols: {}, lastPriceTs: 0, rowQuoteTs: {}, subscriptionError: null };
  },
}));
vi.mock('../scanner/useScannerEnvelopePoll', () => ({ useScannerEnvelopePoll: () => {} }));
afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

function envelope(price = 4.3, halted: boolean | null = false) {
  return { dates: ['2026-09-23'], gappers: [{ symbol: 'PFSA', price, halted }],
    gainers: [], losers: [], afterhours: [], large_cap: [], catalysts: [],
    table_state: 'frozen', last_scan: 100 };
}

function pendingBody() {
  let resolve!: (value: unknown) => void;
  const promise = new Promise<unknown>(accept => { resolve = accept; });
  const response = new Response('{}', { status: 200 });
  const read = vi.spyOn(response, 'json').mockImplementation(() => promise);
  return { response, read, resolve };
}

function scannerFetch(pending: ReturnType<typeof pendingBody>[]) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('/history/')) return new Response(JSON.stringify(envelope(4.2)), { status: 200 });
    if (url.endsWith('/gappers') && pending.length) return pending.shift()!.response;
    return new Response(JSON.stringify(envelope()), { status: 200 });
  }));
}

it.each([true, false, null])('preserves newer %s halt evidence across a pending live JSON body, then accepts fresh REST', async halted => {
  const initial = pendingBody();
  scannerFetch([initial]);
  const { result } = renderHook(() => useScannerData({ discoveryProvider: 'ibkr', scannerPersistentAuthoritative: true }));
  await waitFor(() => expect(initial.read).toHaveBeenCalled());
  act(() => stream.handlers!.onHaltPatch!([{ symbol: 'PFSA', halted }]));
  await act(async () => initial.resolve(envelope(4.3, halted === false ? true : false)));
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  expect(result.current.gappers[0].halted).toBe(halted);
  expect(result.current.gappers[0].price).toBe(4.3);
  expect(result.current.scanAges.gappers).toBe(100);
  expect(result.current.tableMeta.gappers.state).toBe('frozen');
  await act(async () => result.current.fetchData());
  expect(result.current.gappers[0].halted).toBe(false);
});

it('rejects a live reply whose body finishes decoding after history is selected', async () => {
  scannerFetch([]);
  const { result } = renderHook(() => useScannerData({ discoveryProvider: 'ibkr', scannerPersistentAuthoritative: true }));
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  const pending = pendingBody();
  scannerFetch([pending]);
  let request!: Promise<void>;
  act(() => { request = result.current.fetchData(); });
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  act(() => result.current.setHistoryDate('2026-09-23'));
  await waitFor(() => expect(result.current.gappers[0].price).toBe(4.2));
  const meta = result.current.tableMeta;
  const ages = result.current.scanAges;
  await act(async () => { pending.resolve(envelope(9.9, true)); await request; });
  expect(result.current.gappers[0]).toMatchObject({ price: 4.2, halted: false });
  expect(result.current.tableMeta).toBe(meta);
  expect(result.current.scanAges).toBe(ages);
});

it('rejects an older pending live body after a history round trip back into live', async () => {
  scannerFetch([]);
  const { result } = renderHook(() => useScannerData({ discoveryProvider: 'ibkr', scannerPersistentAuthoritative: true }));
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  const pending = pendingBody();
  scannerFetch([pending]);
  let request!: Promise<void>;
  act(() => { request = result.current.fetchData(); });
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  act(() => result.current.setHistoryDate('2026-09-23'));
  await waitFor(() => expect(result.current.gappers[0].price).toBe(4.2));
  act(() => result.current.setHistoryDate(null));
  await waitFor(() => expect(result.current.gappers[0].price).toBe(4.3));
  act(() => stream.handlers!.onHaltPatch!([{ symbol: 'PFSA', halted: null }]));
  await act(async () => { pending.resolve(envelope(9.9, true)); await request; });
  expect(result.current.gappers[0]).toMatchObject({ price: 4.3, halted: null });
});

it('rejects an older live body after switching providers back to the original provider', async () => {
  scannerFetch([]);
  const { result, rerender } = renderHook(({ provider }) => useScannerData({ discoveryProvider: provider, scannerPersistentAuthoritative: true }),
    { initialProps: { provider: 'ibkr' } });
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  const pending = pendingBody();
  scannerFetch([pending]);
  let request!: Promise<void>;
  act(() => { request = result.current.fetchData(); });
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  rerender({ provider: 'other' });
  rerender({ provider: 'ibkr' });
  await act(async () => { pending.resolve(envelope(9.9, true)); await request; });
  expect(result.current.gappers[0]).toMatchObject({ price: 4.3, halted: false });
});

it('ignores a queued IBKR halt callback after selecting a different provider', async () => {
  scannerFetch([]);
  const { result, rerender } = renderHook(({ provider }) => useScannerData({ discoveryProvider: provider, scannerPersistentAuthoritative: true }),
    { initialProps: { provider: 'ibkr' } });
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  const oldHalt = stream.handlers!.onHaltPatch!;
  const pending = pendingBody();
  scannerFetch([pending]);
  rerender({ provider: 'other' });
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  act(() => oldHalt([{ symbol: 'PFSA', halted: true }]));
  expect(result.current.gappers[0].halted).toBe(false);
  await act(async () => pending.resolve(envelope()));
  expect(result.current.gappers[0].halted).toBe(false);
});

it('does not paint old catalysts or failure state after history is chosen during catalyst decoding', async () => {
  scannerFetch([]);
  const { result } = renderHook(() => useScannerData({ discoveryProvider: 'ibkr', scannerPersistentAuthoritative: true }));
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  const pending = pendingBody();
  const regularFetch = fetch;
  vi.stubGlobal('fetch', vi.fn((url: string) => url.endsWith('/news-catalysts') ? Promise.resolve(pending.response) : regularFetch(url)));
  let request!: Promise<void>;
  act(() => { request = result.current.fetchData(); });
  await waitFor(() => expect(pending.read).toHaveBeenCalled());
  act(() => result.current.setHistoryDate('2026-09-23'));
  await waitFor(() => expect(result.current.gappers[0].price).toBe(4.2));
  await act(async () => { pending.resolve({ catalysts: 'unreadable' }); await request; });
  expect(result.current.catalystsError).toBeNull();
  expect(result.current.restError).toBeNull();
});

it.each(['headers', 'body'])('names and retries a current bootstrap timeout during %s', async stage => {
  const controller = new AbortController();
  vi.spyOn(AbortSignal, 'timeout').mockReturnValueOnce(controller.signal);
  let attempts = 0;
  const pending = pendingBody();
  vi.stubGlobal('fetch', vi.fn((url: string, options?: RequestInit) => {
    if (url.endsWith('/gappers') && ++attempts === 1) {
      const aborted = new Promise<never>((_resolve, reject) => {
        options!.signal!.addEventListener('abort', () => reject(options!.signal!.reason), { once: true });
      });
      if (stage === 'headers') return aborted;
      pending.read.mockImplementation(() => aborted);
      return Promise.resolve(pending.response);
    }
    return Promise.resolve(new Response(JSON.stringify(envelope()), { status: 200 }));
  }));
  const { result } = renderHook(() => useScannerData({ discoveryProvider: 'ibkr', scannerPersistentAuthoritative: true }));
  if (stage === 'body') await waitFor(() => expect(pending.read).toHaveBeenCalled());
  else await waitFor(() => expect(attempts).toBe(1));
  act(() => controller.abort(new DOMException('bootstrap timed out', 'TimeoutError')));
  await waitFor(() => expect(result.current.restError).not.toBeNull());
  if (stage === 'headers') expect(result.current.health.status).toBe('connected');
  else expect(result.current.restError).toContain('/api/gappers');
  await waitFor(() => expect(attempts).toBe(2), { timeout: 4000 });
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  expect(result.current.restError).toBeNull();
});

it('updates halt alone on a frozen served row and rejects queued live evidence after choosing history', async () => {
  vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify({ dates: ['2026-09-23'],
    gappers: [{ symbol: 'PFSA', price: 4.3, halted: false }], gainers: [], losers: [],
    afterhours: [], large_cap: [], catalysts: [], table_state: 'frozen', last_scan: 100,
  }), { status: 200 })));
  const { result } = renderHook(() => useScannerData({ discoveryProvider: 'ibkr', scannerPersistentAuthoritative: true }));
  await waitFor(() => expect(result.current.gappers).toHaveLength(1));
  const meta = result.current.tableMeta;
  const ages = result.current.scanAges;
  act(() => stream.handlers!.onHaltPatch!([{ symbol: 'PFSA', halted: true }]));
  expect(result.current.gappers[0].halted).toBe(true);
  expect(result.current.gappers[0].price).toBe(4.3);
  expect(result.current.tableMeta).toBe(meta);
  expect(result.current.scanAges).toBe(ages);
  act(() => result.current.setHistoryDate('2026-09-23'));
  await waitFor(() => expect(result.current.gappers[0].halted).toBe(false));
  act(() => stream.handlers!.onHaltPatch!([{ symbol: 'PFSA', halted: true }]));
  expect(result.current.gappers[0].halted).toBe(false);
});
